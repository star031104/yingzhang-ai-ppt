import base64
import time

from app.db.models import DeckSpecRecord, SlideSpecRecord
from app.db.session import SessionLocal
from app.presentation_intelligence.object_edit import apply_object_edit
from app.validation.accessibility import audit_accessibility


def slide_spec(project_id: str, slide_id: str = "slide-p1") -> dict:
    return {
        "id": slide_id,
        "projectId": project_id,
        "position": 1,
        "role": "content",
        "message": "证据支持结论",
        "content": {"title": "原始标题", "bullets": ["第一条", "第二条"]},
        "sourceRefs": [],
        "assetBindings": [],
        "visualIntent": {"primaryVisual": "typography"},
        "designSystem": {},
    }


def seed_slide(project_id: str) -> str:
    spec = slide_spec(project_id)
    with SessionLocal() as db:
        db.add(DeckSpecRecord(project_id=project_id, narrative={}, design_system={}, reproducibility={}))
        db.add(SlideSpecRecord(id=spec["id"], project_id=project_id, position=1, spec=spec))
        db.commit()
    return spec["id"]


def test_object_edit_is_scoped_to_the_selected_slide_object():
    spec = slide_spec("project")
    edited, changes = apply_object_edit(
        spec, "修改第二条要点", {"kind": "bullet", "index": 1}, "replace", "新的第二条"
    )
    assert edited["content"]["title"] == "原始标题"
    assert edited["content"]["bullets"] == ["第一条", "新的第二条"]
    assert changes["target"] == {"kind": "bullet", "index": 1}
    assert spec["content"]["bullets"] == ["第一条", "第二条"]


def test_accessibility_audit_blocks_images_without_alt_text():
    spec = slide_spec("project")
    spec["assetBindings"] = [{"type": "licensed-image", "path": "image.png", "license": "cc0"}]
    report = audit_accessibility([spec])
    assert report["passed"] is False
    assert any(issue["code"] == "missing-alt-text" for issue in report["issues"])


def test_p1_chat_assets_members_and_single_slide_job(client):
    project = client.post("/api/v1/projects", json={"name": "P1 workflow"}).json()
    slide_id = seed_slide(project["id"])

    edited = client.post(
        f"/api/v1/projects/{project['id']}/slides/{slide_id}/chat",
        json={
            "instruction": "把第二条要点改得更具体",
            "target": {"kind": "bullet", "index": 1},
            "operation": "replace",
            "value": "第二条已经对象级更新",
            "rerender": False,
        },
    )
    assert edited.status_code == 200
    assert edited.json()["slide"]["content"]["bullets"][1] == "第二条已经对象级更新"
    history = client.get(f"/api/v1/projects/{project['id']}/slides/{slide_id}/chat").json()
    assert history[-1]["version"] == 2

    asset = client.post(
        f"/api/v1/projects/{project['id']}/assets",
        data={"name": "自有主视觉", "kind": "image", "provider": "uploaded", "license": "owned", "attribution": "项目团队"},
        files={"file": ("hero.png", base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="), "image/png")},
    )
    assert asset.status_code == 201 and asset.json()["approved"] is True
    bound = client.post(f"/api/v1/projects/{project['id']}/slides/{slide_id}/assets/{asset.json()['id']}/bind")
    assert bound.status_code == 200
    assert bound.json()["slide"]["assetBindings"][-1]["license"] == "owned"

    member = client.post(
        f"/api/v1/projects/{project['id']}/members",
        json={"name": "王审阅", "role": "reviewer"},
    )
    assert member.status_code == 201 and member.json()["role"] == "reviewer"
    approval = client.post(
        f"/api/v1/projects/{project['id']}/approvals",
        json={"stage": "final", "status": "approved", "comment": "可以发布"},
    )
    assert approval.status_code == 201 and approval.json()["status"] == "approved"

    job = client.post(f"/api/v1/projects/{project['id']}/slides/{slide_id}/jobs/regenerate").json()
    for _ in range(80):
        current = client.get(f"/api/v1/jobs/{job['id']}").json()
        if current["status"] not in {"queued", "running"}:
            break
        time.sleep(0.1)
    assert current["status"] == "completed"
    assert current["checkpoint"]["result"]["candidateCount"] >= 1
    partial = client.get(f"/api/v1/projects/{project['id']}/slides/{slide_id}/export/pptx")
    assert partial.status_code == 200
    assert partial.content.startswith(b"PK")
