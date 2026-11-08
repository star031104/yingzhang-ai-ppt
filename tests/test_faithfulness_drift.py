import asyncio
import copy
import json
from pathlib import Path

from app.db.models import SlideSpecRecord, SlideVersion
from app.db.session import SessionLocal
from app.documents import parse_source
from app.evaluation.edit_drift import deck_drift, history_drift
from app.evaluation.faithfulness import evaluate_faithfulness, grade_claim
from app.evaluation.perturbation import run_perturbation_suite
from app.presentation_intelligence.planner import plan_deck

ROOT = Path(__file__).resolve().parents[1]


def _fixture(name="data-dashboard", preset="data"):
    path = ROOT / "benchmarks" / name / "fixture.md"
    source = parse_source(path.name, path.read_bytes(), "text/markdown")
    return source, plan_deck([source], name, preset, 8)["slides"]


def test_grade_claim_requires_every_number_and_keeps_qualifiers():
    chunk = {"text": "2025 年第四季度收入 1.2 亿元，同比增长 8.4%，不含一次性收入。"}
    assert grade_claim("第四季度收入 1.2 亿元，同比增长 8.4%，不含一次性收入", chunk)["verdict"] == "supported"
    altered = grade_claim("第四季度收入 1.2 亿元，同比增长 18.4%", chunk)
    assert altered["verdict"] in {"partial", "unsupported"} and "18.4%" in altered["missingNumbers"]
    dropped = grade_claim("第四季度收入 1.2 亿元，增长 8.4%", chunk)
    assert dropped["verdict"] == "partial" and "不含" in dropped["droppedQualifiers"]
    assert grade_claim("海外渠道贡献营收提升 437%", None)["verdict"] == "unsupported"


def test_faithfulness_on_benchmark_and_fabricated_claim():
    source, slides = _fixture()
    clean = asyncio.run(evaluate_faithfulness(slides, [source]))
    assert clean["status"] == "completed" and clean["claims"] > 5
    assert clean["faithfulness"] >= 0.9
    broken = copy.deepcopy(slides)
    target = next(slide for slide in broken if slide["role"] not in {"cover", "agenda", "section", "questions"})
    target["content"]["bullets"].append("海外渠道贡献营收提升 437%，客户满意度达到 99.7%")
    result = asyncio.run(evaluate_faithfulness(broken, [source]))
    assert result["faithfulness"] < clean["faithfulness"]
    assert any("437%" in item["text"] for item in result["unsupported"])


class Judge:
    model_id = "fake"
    vision = False

    def __init__(self):
        self.prompts = []

    async def complete(self, prompt, max_tokens=2400):
        self.prompts.append(prompt)
        claims = json.loads(prompt[prompt.rfind("[{\"id\": \"c"):])
        return json.dumps({"claims": [{"id": item["id"], "verdict": "supported", "reason": "原文支持"} for item in claims]})


def test_judge_only_sees_uncertain_claims_and_cannot_excuse_missing_numbers():
    source, slides = _fixture()
    broken = copy.deepcopy(slides)
    target = next(slide for slide in broken if slide["role"] not in {"cover", "agenda", "section", "questions"})
    target["content"]["bullets"].append("海外渠道贡献营收提升 437%")
    judge = Judge()
    result = asyncio.run(evaluate_faithfulness(broken, [source], judge=judge))
    assert result["mode"] == "rules+judge" and len(judge.prompts) == 1
    graded = [claim for slide in result["slides"] for claim in slide["claims"] if "437%" in claim["text"]]
    assert graded and graded[0]["verdict"] == "partial"  # judge said supported, the number is still missing


def test_perturbation_suite_detects_every_injected_defect():
    for name, preset in (("data-dashboard", "data"), ("business-report", "business"), ("academic-thesis", "academic")):
        source, slides = _fixture(name, preset)
        report = run_perturbation_suite(slides, [source])
        assert report["detectionRate"] == 1.0, report["missed"]
        assert report["applicable"] >= 10


def test_deck_drift_flags_off_target_and_out_of_scope_changes():
    _, slides = _fixture()
    after = copy.deepcopy(slides)
    after[3]["content"]["title"] = "人工改写的标题"
    assert deck_drift(slides, after, {after[3]["id"]})["drifted"] is False
    after[3]["sourceRefs"] = []
    after[5]["message"] = "被顺手改掉的另一页"
    drift = deck_drift(slides, after, {after[3]["id"]})
    assert drift["outOfScope"][0]["fields"] == ["sourceRefs"]
    assert drift["offTarget"][0]["position"] == after[5]["position"]


def test_history_drift_detects_user_copy_overwritten_by_automation():
    base = {"id": "s1", "position": 2, "content": {"title": "原标题", "bullets": ["a"]}, "message": "m"}
    edited = {**base, "content": {"title": "用户标题", "bullets": ["a"]}}
    overwritten = {**edited, "content": {"title": "原标题", "bullets": ["a"]}}
    versions = [
        {"slideId": "s1", "version": 1, "reason": "initial outline", "spec": base},
        {"slideId": "s1", "version": 2, "reason": "页内对话：改标题", "spec": edited},
        {"slideId": "s1", "version": 3, "reason": "automatic outline recovery", "spec": overwritten},
    ]
    report = history_drift(versions)
    assert report["turns"] == 1 and report["driftRate"] == 0
    assert report["overwritten"][0]["kind"] == "copy" and report["persistence"] == 0


def test_evaluation_api_runs_faithfulness_and_drift(client):
    from test_research_evaluation import _seed_project

    project_id, slides = _seed_project(client)
    target = next(slide for slide in slides if slide["role"] not in {"cover", "agenda", "section", "questions"})
    with SessionLocal() as db:
        row = db.get(SlideSpecRecord, target["id"])
        db.add(SlideVersion(slide_id=row.id, version=1, spec=copy.deepcopy(row.spec), reason="initial outline"))
        spec = copy.deepcopy(row.spec)
        spec["content"]["title"] = "人工修改标题"
        row.spec, row.current_version = spec, 2
        db.add(SlideVersion(slide_id=row.id, version=2, spec=spec, reason="页内对话：修改标题"))
        db.commit()
    response = client.post(f"/api/v1/projects/{project_id}/evaluations",
                           json={"kinds": ["faithfulness", "drift"], "use_models": False})
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["faithfulness"]["status"] == "completed"
    assert run["summary"]["faithfulness"] >= 0.9
    assert run["drift"]["turns"] == 1 and run["summary"]["driftRate"] == 0
