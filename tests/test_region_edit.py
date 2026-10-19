import json
import time
from pathlib import Path

import pytest
from app.db.models import DeckSpecRecord, SlideCandidate, SlideSpecRecord
from app.db.session import SessionLocal
from app.presentation_intelligence.object_edit import apply_object_edit, infer_edit_target
from app.presentation_intelligence.region_edit import (
    RegionEditError,
    plan_region_edit,
    targets_in_region,
)
from sqlalchemy import select

SPEC = {
    "id": "slide-region",
    "position": 1,
    "role": "data",
    "message": "订阅收入占比 62%，是增长主引擎",
    "content": {
        "title": "收入结构",
        "bullets": ["订阅收入占比 62%，是增长主引擎", "服务收入 38% 主要来自实施", "渠道合作仍在试点"],
    },
    "visualIntent": {"primaryVisual": "typography", "selectedVariant": "evidence-brief"},
}


def node(node_id, text, x, y, width, height, tag="p", node_type="text", region="content"):
    return {
        "id": node_id, "type": node_type, "tag": tag, "region": region, "isTextLeaf": node_type == "text",
        "text": text, "bbox": {"x": x, "y": y, "width": width, "height": height}, "classes": [],
    }


SCENE = {
    "width": 1280,
    "height": 720,
    "nodes": [
        node("n1", "数据", 68, 52, 40, 18, tag="span", region="header"),
        node("n2", "收入结构", 68, 94, 600, 50, tag="h1", region="title"),
        node("n3", "01", 68, 240, 30, 30, tag="b"),
        node("n4", "订阅收入占比 62%，是增长主引擎", 112, 240, 900, 32),
        node("n5", "服务收入 38% 主要来自实施", 112, 300, 900, 32),
        node("n6", "38%", 1040, 296, 120, 40, tag="strong"),
        node("n7", "渠道合作仍在试点", 112, 360, 900, 32),
        node("n8", "", 700, 420, 500, 200, tag="div", node_type="chart"),
        node("n9", "订阅收入占比 62%，是增长主引擎", 91, 560, 1100, 50),
        node("n10", "fixture.md", 68, 680, 1144, 12, tag="footer", region="footer"),
    ],
}


def test_region_maps_nodes_to_content_targets():
    title = targets_in_region(SCENE, SPEC, {"x": 60, "y": 80, "width": 700, "height": 80})
    assert [target["kind"] for target in title] == ["title"]
    # The message restates bullet 1, yet the lower node still resolves to the message.
    message = targets_in_region(SCENE, SPEC, {"x": 80, "y": 550, "width": 1120, "height": 70})
    assert [target["kind"] for target in message] == ["message"]
    metric = targets_in_region(SCENE, SPEC, {"x": 1030, "y": 290, "width": 140, "height": 50})
    assert metric[0] == {**metric[0], "kind": "bullet", "index": 1, "metric": True, "label": "第 2 条要点（数字）"}
    several = targets_in_region(SCENE, SPEC, {"x": 100, "y": 230, "width": 1000, "height": 170})
    assert {(target["kind"], target.get("index")) for target in several} == {("bullet", 0), ("bullet", 1), ("bullet", 2)}
    chart = targets_in_region(SCENE, SPEC, {"x": 750, "y": 450, "width": 200, "height": 100})
    assert chart[0]["kind"] == "visual" and chart[0]["object"] == "chart"
    assert targets_in_region(SCENE, SPEC, {"x": 1180, "y": 10, "width": 60, "height": 30}) == []
    with pytest.raises(RegionEditError):
        targets_in_region(SCENE, SPEC, {"x": 10, "y": 10, "width": 2, "height": 2})


def test_region_instruction_is_planned_deterministically():
    title = [{"kind": "title", "label": "页面标题"}]
    bullet = [{"kind": "bullet", "index": 1, "metric": True}]
    assert plan_region_edit("改为：2026 收入结构", title, SPEC) == [
        {"target": {"kind": "title"}, "operation": "replace", "value": "2026 收入结构"}
    ]
    assert plan_region_edit("把这里改成三步流程", bullet, SPEC)[0]["target"] == {"kind": "visual", "variant": "three-stage"}
    # Literal text that merely contains a layout word stays text.
    assert plan_region_edit("改成 Q3 营收对比", title, SPEC)[0]["value"] == "Q3 营收对比"
    emphasis = plan_region_edit("这个数字加粗突出", bullet, SPEC)
    assert emphasis[0] == {"target": {"kind": "bullet", "index": 1, "to": 0}, "operation": "move", "value": None}
    assert emphasis[1]["target"]["variant"] == "metric-wall"
    deleted = plan_region_edit("删除这些", [{"kind": "bullet", "index": 0}, {"kind": "bullet", "index": 2}], SPEC)
    assert [edit["target"]["index"] for edit in deleted] == [2, 0]
    with pytest.raises(RegionEditError):
        plan_region_edit("删除", title, SPEC)
    with pytest.raises(RegionEditError):
        plan_region_edit("随便看看", title, SPEC)
    with pytest.raises(RegionEditError):
        plan_region_edit("改为：新标题", [], SPEC)


def test_object_edit_accepts_explicit_targets_and_layout_variants():
    candidates = [{"kind": "bullet", "index": 2}, {"kind": "title"}]
    assert infer_edit_target("把标题再写短一点", candidates) == {"kind": "title"}
    assert infer_edit_target("换个说法", candidates) == {"kind": "bullet", "index": 2}
    edited, _ = apply_object_edit(SPEC, "改成三步流程", {"kind": "visual", "variant": "three-stage"}, "replace", "diagram")
    assert edited["visualIntent"]["selectedVariant"] == "three-stage"
    assert edited["visualIntent"]["variantSelectionSource"] == "user"
    with pytest.raises(ValueError):
        apply_object_edit(SPEC, "x", {"kind": "visual", "variant": "<script>"}, "replace", "diagram")


def _seed(project_id: str) -> str:
    spec = {**json.loads(json.dumps(SPEC)), "projectId": project_id, "sourceRefs": [], "assetBindings": [], "designSystem": {}}
    with SessionLocal() as db:
        db.add(DeckSpecRecord(project_id=project_id, narrative={}, design_system={}, reproducibility={}))
        db.add(SlideSpecRecord(id=spec["id"], project_id=project_id, position=1, spec=spec))
        db.commit()
    return spec["id"]


def test_region_edit_endpoint_edits_objects_under_selection(client):
    project = client.post("/api/v1/projects", json={"name": "框选修改"}).json()
    slide_id = _seed(project["id"])
    url = f"/api/v1/projects/{project['id']}/slides/{slide_id}/region-edit"
    box = {"x": 0, "y": 0, "width": 1280, "height": 720}
    not_rendered = client.post(url, json={"bbox": box, "instruction": "改为：新标题"})
    assert not_rendered.status_code == 409

    job = client.post(f"/api/v1/projects/{project['id']}/slides/{slide_id}/jobs/regenerate").json()
    for _ in range(120):
        current = client.get(f"/api/v1/jobs/{job['id']}").json()
        if current["status"] not in {"queued", "running"}:
            break
        time.sleep(0.1)
    assert current["status"] == "completed"
    with SessionLocal() as db:
        chosen = db.scalar(select(SlideCandidate).where(SlideCandidate.slide_id == slide_id, SlideCandidate.selected))
        scene = json.loads(Path(chosen.artifact_path).with_suffix(".scene.json").read_text(encoding="utf-8"))
    heading = next(item for item in scene["nodes"] if item["tag"] == "h1")["bbox"]
    title_box = {"x": heading["x"] - 4, "y": heading["y"] - 4, "width": heading["width"] + 8, "height": heading["height"] + 8}

    stale = client.post(url, json={"bbox": title_box, "instruction": "改为：新标题", "revision": 99})
    assert stale.status_code == 409
    edited = client.post(url, json={"bbox": title_box, "instruction": "改为：2026 收入结构", "rerender": False, "revision": 1})
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["slide"]["content"]["title"] == "2026 收入结构"
    assert body["slide"]["content"]["bullets"] == SPEC["content"]["bullets"]
    assert body["edited"][0]["kind"] == "title" and body["edited"][0]["label"] == "页面标题"
    assert body["region"]["targets"][0]["kind"] == "title"
    assert body["version"] == 2
    versions = client.get(f"/api/v1/projects/{project['id']}/slides/{slide_id}/versions").json()
    assert versions[-1]["reason"] == "框选修改：改为：2026 收入结构"
    history = client.get(f"/api/v1/projects/{project['id']}/slides/{slide_id}/chat").json()
    assert history[-1]["target"]["kind"] == "region"

    unclear = client.post(url, json={"bbox": title_box, "instruction": "随便看看", "rerender": False})
    assert unclear.status_code == 422
    assert "改为" in unclear.json()["detail"]
