import json
from pathlib import Path

from app.db.models import DeckSpecRecord, SlideSpecRecord
from app.db.session import SessionLocal

ISSUE = {"position": 1, "code": "unsupported-number", "severity": "repaired", "field": "bullets",
         "message": "出现事实白名单之外的数字，已替换或删除", "detail": {}}


def test_workspace_exposes_proposal_validation_and_uncertain_roles(client):
    project = client.post("/api/v1/projects", json={"name": "规划校验"}).json()
    spec = {"id": "slide-v", "projectId": project["id"], "position": 1, "role": "cover", "message": "结论",
            "content": {"title": "封面", "bullets": []}, "proposalIssues": [ISSUE]}
    with SessionLocal() as db:
        db.add(DeckSpecRecord(project_id=project["id"], narrative={}, design_system={}, reproducibility={
            "proposalValidation": {"version": "page-proposal-validation-v1", "issues": [ISSUE], "fallbackPositions": [],
                                   "summary": {"pages": 1, "accepted": 0, "repaired": 1, "fallback": 0, "byCode": {"unsupported-number": 1}}},
        }))
        db.add(SlideSpecRecord(id=spec["id"], project_id=project["id"], position=1, spec=spec))
        db.commit()
    analysis = Path(project["artifact_path"]) / "analysis" / "content-architecture.json"
    analysis.parent.mkdir(parents=True, exist_ok=True)
    analysis.write_text(json.dumps({"materialAnalysis": {"documents": [
        {"name": "报告.pdf", "kind": "论文/报告", "keyPoints": ["不应返回"],
         "uncertainRoles": [{"section": "S003", "title": "附录", "role": "evidence", "confidence": 0.4}]},
    ]}}, ensure_ascii=False), encoding="utf-8")

    workspace = client.get(f"/api/v1/projects/{project['id']}/workspace").json()
    assert workspace["proposalValidation"]["summary"]["repaired"] == 1
    assert workspace["proposalValidation"]["issues"][0]["code"] == "unsupported-number"
    assert workspace["slides"][0]["proposalIssues"][0]["message"].startswith("出现事实")
    assert workspace["materialAnalysis"] == {"documents": [{"name": "报告.pdf", "kind": "论文/报告", "uncertainRoles": [
        {"section": "S003", "title": "附录", "role": "evidence", "confidence": 0.4}]}]}


def test_workspace_planning_fields_are_empty_without_plan(client):
    project = client.post("/api/v1/projects", json={"name": "空项目"}).json()
    workspace = client.get(f"/api/v1/projects/{project['id']}/workspace").json()
    assert workspace["proposalValidation"] is None
    assert workspace["materialAnalysis"] == {"documents": []}
