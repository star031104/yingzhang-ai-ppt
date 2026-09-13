import copy
import json
import subprocess
from pathlib import Path

import pytest
from app.presentation_engine.page_pipeline import select_deck_variants
from app.presentation_intelligence.visual_critic import apply_safe_repairs
from app.validation.quality import validate_deck


def evidence_slide():
    return {
        "id": "one", "position": 1, "role": "data", "message": "结果见实验记录",
        "content": {"title": "实验对照", "bullets": ["准确率达到89%"]},
        "sourceRefs": [{"document": "实验.md", "section": "S001"}],
        "evidenceBindings": ["F001"],
    }


def sources():
    return [{"name": "实验.md", "sections": [
        {"id": "S001", "text": "本章节说明方法，未给出实验数值。"},
        {"id": "S002", "text": "准确率达到89%，增长率为-12%。"},
    ]}]


@pytest.mark.parametrize("refs", [[], [{"document": "实验.md", "section": "S001"}]])
def test_number_in_another_section_does_not_support_the_slide(refs):
    slide = evidence_slide()
    slide["sourceRefs"] = refs
    report = validate_deck([slide], sources())
    assert any(issue["code"] == "unsupported-metric" for issue in report["issues"])
    assert report["claimCoverage"] == 0


def test_existing_document_with_nonexistent_section_is_a_broken_reference():
    slide = evidence_slide()
    slide["sourceRefs"][0]["section"] = "S999"
    report = validate_deck([slide], sources())
    assert any(issue["code"] == "broken-source-ref" for issue in report["issues"])


def test_numeric_title_and_negative_sign_are_checked():
    slide = evidence_slide()
    slide["sourceRefs"][0]["section"] = "S002"
    slide["content"] = {"title": "准确率达到99%", "bullets": ["增长率为12%"]}
    report = validate_deck([slide], sources())
    unsupported = {issue.get("value") for issue in report["issues"] if issue["code"] == "unsupported-metric"}
    assert unsupported == {"99%", "12%"}
    slide["content"] = {"title": "第 3 章 实验对照", "bullets": ["增长率为−12%"]}
    assert not any(issue["code"] == "unsupported-metric" for issue in validate_deck([slide], sources())["issues"])


@pytest.mark.parametrize("selection_source, expected", [("auto", "split"), ("user", "cards"), ("critic", "cards")])
def test_safe_selection_does_not_overwrite_human_choices(tmp_path, selection_source, expected):
    score = {key: 96 for key in (
        "geometry", "readability", "contentFit", "hierarchy", "whitespace", "alignment",
        "semanticFit", "visualEvidence", "planningFit", "styleConsistency", "deckRhythm", "overall",
    )}
    root = tmp_path / "slides" / "1"
    root.mkdir(parents=True)
    (root / "cards.score.json").write_text(json.dumps({**score, "textOverflow": 1}))
    (root / "split.score.json").write_text(json.dumps({**score, "overall": 90}))
    slide = evidence_slide()
    slide["visualIntent"] = {"selectedVariant": "cards", "variantSelectionSource": selection_source}
    select_deck_variants([slide], tmp_path)
    assert slide["visualIntent"]["selectedVariant"] == expected
    current = json.loads((root / "current.json").read_text())
    assert isinstance(current["score"], int)
    assert current["scoreDetail"]["geometry"] == 96
    assert current["needsReview"] is (selection_source != "auto")


def test_visual_critic_cannot_trade_clipped_text_for_a_higher_score():
    slide = evidence_slide()
    slide["visualIntent"] = {"selectedVariant": "cards"}
    snapshot = {"position": 1, "selectedVariant": "cards", "selectionSource": "auto", "candidates": [
        {"variant": "cards", "score": {"overall": 80}},
        {"variant": "split", "score": {"overall": 99, "geometry": 99, "readability": 99, "contentFit": 99, "textOverflow": 1}},
    ]}
    review = {"position": 1, "recommendedVariant": "split", "confidence": .99, "issues": ["repetition"]}
    before = copy.deepcopy(slide)
    assert apply_safe_repairs([slide], [snapshot], [review]) == []
    assert slide == before


def test_unrendered_deck_is_not_delivery_ready(client):
    project = client.post("/api/v1/projects", json={"name": "尚未渲染"}).json()
    result = client.post(f"/api/v1/projects/{project['id']}/validate")
    assert result.status_code == 200
    report = result.json()
    assert report["visualQA"]["complete"] is False
    assert report["passed"] is False
    assert report["professionalAudit"]["ready"] is False


def test_node_render_stamp_matches_python_and_tracks_asset_bytes(tmp_path):
    from app.validation.render_freshness import matches_render_stamp

    asset = tmp_path / "材料.txt"
    asset.write_text("原始内容", encoding="utf-8")
    slide = evidence_slide()
    slide["assetBindings"] = [{"path": str(asset)}]
    program = "import {renderStamp} from './packages/presentation-engine/src/render-input.mjs'; let input=''; for await(const chunk of process.stdin) input+=chunk; console.log(JSON.stringify(await renderStamp(JSON.parse(input))));"
    result = subprocess.run(["node", "--input-type=module", "-e", program], input=json.dumps(slide),
                            encoding="utf-8", capture_output=True, check=True)
    stamp = json.loads(result.stdout)
    assert matches_render_stamp(stamp, slide)
    slide["visualIntent"] = {"selectedVariant": "split", "variantSelectionSource": "critic", "criticIssues": ["repetition"]}
    assert matches_render_stamp(stamp, slide)
    asset.write_text("替换内容", encoding="utf-8")
    assert not matches_render_stamp(stamp, slide)
    assert not matches_render_stamp(None, slide)


def test_edited_deck_cannot_reuse_old_visual_pass_or_export_old_html(client):
    from app.db.models import Project, SlideSpecRecord
    from app.db.session import SessionLocal
    from app.validation.render_freshness import render_input

    project = client.post("/api/v1/projects", json={"name": "预览版本验证"}).json()
    slide = {"id": "freshness", "position": 1, "role": "cover", "message": "原结论",
             "content": {"title": "原标题", "bullets": []}, "visualIntent": {"selectedVariant": "hero"}}
    with SessionLocal() as db:
        root = Path(db.get(Project, project["id"]).artifact_path) / "slides" / "rendered"
        db.add(SlideSpecRecord(id=slide["id"], project_id=project["id"], position=1, spec=slide))
        db.commit()
    folder = root / "slides" / "1"
    folder.mkdir(parents=True, exist_ok=True)
    detail = {"overall": 95, "geometry": 100, "issues": [],
              "renderStamp": {"version": 2, "input": render_input(slide), "assets": {}}}
    (folder / "current.json").write_text(json.dumps({"variant": "hero", "score": 95, "scoreDetail": detail}), encoding="utf-8")
    (root / "index.html").write_text("<html>原内容</html>", encoding="utf-8")
    report = client.post(f"/api/v1/projects/{project['id']}/validate").json()
    assert report["visualQA"]["complete"] is True
    with SessionLocal() as db:
        edited = copy.deepcopy(slide)
        edited["content"]["title"] = "新标题"
        db.get(SlideSpecRecord, slide["id"]).spec = edited
        db.commit()
    report = client.post(f"/api/v1/projects/{project['id']}/validate").json()
    assert report["visualQA"]["stalePositions"] == [1]
    assert report["visualQA"]["complete"] is False
    assert report["professionalAudit"]["ready"] is False
    for format_name in ("html", "pdf"):
        response = client.get(f"/api/v1/projects/{project['id']}/export/{format_name}")
        assert response.status_code == 409
        assert response.json()["detail"]["positions"] == [1]
