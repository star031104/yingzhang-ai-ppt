from pathlib import Path

from app.db.models import DeckSpecRecord, SlideSpecRecord
from app.db.session import SessionLocal
from app.documents import parse_source
from app.presentation_intelligence.planner import plan_deck
from app.workflows.intake import build_intake, compile_intake, suggested_slide_count
from app.workflows.planning_brief import PlanRequest
from app.workflows.rehearsal import audience_questions, build_rehearsal, pacing_plan

ROOT = Path(__file__).resolve().parents[1]


def _fixture(name="data-dashboard", preset="data"):
    path = ROOT / "benchmarks" / name / "fixture.md"
    source = parse_source(path.name, path.read_bytes(), "text/markdown")
    return source, plan_deck([source], name, preset, 8)["slides"]


def test_intake_has_five_phases_with_material_defaults():
    source, _ = _fixture()
    intake = build_intake(title="经营复盘", preset="business", duration_minutes=20, sources=[source])
    assert [phase["id"] for phase in intake["phases"]] == ["strategy", "substance", "structure", "design", "build"]
    must = next(q for p in intake["phases"] for q in p["questions"] if q["id"] == "mustCover")
    assert must["options"] and set(must["suggested"]) <= {item["value"] for item in must["options"]}
    count = next(q for p in intake["phases"] for q in p["questions"] if q["id"] == "slideCount")
    assert count["suggested"] == suggested_slide_count("business", 20)


def test_compile_intake_produces_valid_plan_request():
    source, _ = _fixture()
    intake = build_intake(title="经营复盘", preset="business", sources=[source])
    must = next(q for p in intake["phases"] for q in p["questions"] if q["id"] == "mustCover")
    payload = compile_intake(
        {"title": "经营复盘", "instructions": "结论先行", "preset": "business", "slide_count": 12},
        {"audience": "管理层", "objective": "批准试点", "tone": "executive", "durationMinutes": 18, "slideCount": 10,
         "narrative": "conclusion-first", "mustCover": must["suggested"][:1], "avoid": "客户名称", "keepBoundaries": "yes",
         "reviewMode": "samples-first"},
        intake,
    )
    request = PlanRequest.model_validate(payload)
    assert request.audience == "管理层" and request.tone == "executive" and request.slide_count == 10
    assert request.approval_mode is True and request.duration_minutes == 18
    assert "优先覆盖" in request.instructions and must["options"][0]["label"][:10] in request.instructions
    assert "回避或不展开：客户名称" in request.instructions


def test_pacing_respects_duration_and_flags_pressure():
    _, slides = _fixture()
    plan = pacing_plan(slides, 10)
    assert abs(plan["totalSeconds"] - 600) <= len(slides) * 15
    assert plan["pages"][0]["startSeconds"] == 0
    cover = plan["pages"][0]["budgetSeconds"]
    body = max(page["budgetSeconds"] for page in plan["pages"][1:])
    assert body > cover
    assert pacing_plan(slides, 1)["pages"][3]["pressure"] == "compress"


def test_questions_are_answered_from_sources_only():
    source, slides = _fixture()
    questions = audience_questions(slides, [source])
    assert questions and all(item["answer"] for item in questions)
    definition = next(item for item in questions if item["kind"] == "definition")
    assert definition["sourceRef"]["document"] == source["name"]
    assert audience_questions(slides, []) == []
    rehearsal = build_rehearsal(slides, [source], 12)
    assert rehearsal["pacing"]["pages"] and rehearsal["questions"]


def test_intake_and_rehearsal_api(client):
    project = client.post("/api/v1/projects", json={"name": "排练"}).json()
    fixture = ROOT / "benchmarks" / "data-dashboard" / "fixture.md"
    client.post(f"/api/v1/projects/{project['id']}/sources",
                files={"file": ("fixture.md", fixture.read_bytes(), "text/markdown")})
    guide = client.post(f"/api/v1/projects/{project['id']}/intake",
                        json={"title": "数据复盘", "preset": "data", "duration_minutes": 15}).json()
    compiled = client.post(f"/api/v1/projects/{project['id']}/intake/compile", json={
        "base": {"title": "数据复盘", "preset": "data", "slide_count": 12}, "answers": {"slideCount": 8}, "intake": guide,
    })
    assert compiled.status_code == 200 and compiled.json()["slide_count"] == 8
    assert client.post(f"/api/v1/projects/{project['id']}/rehearsal", json={}).status_code == 409
    _, slides = _fixture()
    with SessionLocal() as db:
        db.add(DeckSpecRecord(project_id=project["id"], narrative={}, design_system={},
                              reproducibility={"request": {"professionalBrief": {"durationMinutes": 12}}}))
        for slide in slides:
            db.add(SlideSpecRecord(id=slide["id"], project_id=project["id"], position=slide["position"], spec=slide))
        db.commit()
    rehearsal = client.post(f"/api/v1/projects/{project['id']}/rehearsal", json={}).json()
    assert rehearsal["durationMinutes"] == 12 and rehearsal["questions"]
    card = client.get(f"/api/v1/projects/{project['id']}/rehearsal/card")
    assert card.status_code == 200 and "排练卡" in card.text
