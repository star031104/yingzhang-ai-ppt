import json
import re

import pytest
from app.intelligence.contract_library import (
    ACADEMIC_PRESETS,
    PRESET_CONTRACT_LIBRARIES,
    allowed_roles,
    general_contracts,
)
from app.intelligence.proposal_validator import near_duplicate, validate_page_proposals
from app.intelligence.retrieval import DOMAIN_TERMS
from app.intelligence.role_classifier import classify_section
from app.presentation_intelligence.planner import ROLE_LABELS, classify_role, plan_deck


def source(name, sections):
    return {"name": name, "sha256": "fixture", "sections": sections}


PITCH = source("路演材料.md", [
    {"id": "S001", "title": "行业痛点", "text": "中小商家获客成本持续上升，传统渠道难以触达年轻用户。"},
    {"id": "S002", "title": "市场规模", "text": "目标市场覆盖三百万家门店，线上化率仍然较低。"},
    {"id": "S003", "title": "产品方案", "text": "产品提供会员运营、智能营销和数据看板三项能力。"},
    {"id": "S004", "title": "商业模式", "text": "按门店订阅收费，年费 2,400 元，增值服务另行计费。"},
    {"id": "S005", "title": "增长数据", "text": "试点期间付费门店达到 1,200 家，月留存率 92%。"},
    {"id": "S006", "title": "竞争格局", "text": "相比通用 SaaS，产品聚焦本地生活场景，数据接入更完整。"},
    {"id": "S007", "title": "核心团队", "text": "创始团队来自头部互联网公司，覆盖产品、技术和销售。"},
    {"id": "S008", "title": "融资计划", "text": "本轮计划融资 3,000 万元，用于研发与市场拓展。"},
])


def test_scored_classifier_keeps_title_rules_and_adds_confidence():
    assert classify_role({"title": "实验结果", "text": "准确率 89.6%"}) == "data"
    assert classify_role({"title": "背景", "text": "说明"}) == "background"
    explicit = classify_section({"title": "任意", "text": "", "semanticRole": "evidence"}, labels=set(ROLE_LABELS))
    assert explicit == {"role": "evidence", "confidence": 1.0, "signal": "explicit", "scores": {"evidence": 1.0}}
    titled = classify_section({"title": "竞争格局", "text": "普通说明文字。"})
    assert titled["role"] == "comparison" and titled["signal"] == "title" and titled["confidence"] >= 0.9


@pytest.mark.parametrize(("title", "role"), [
    ("商业模式", "data"), ("市场规模与时机", "background"), ("客户证言", "evidence"),
    ("核心概念", "architecture"), ("经验教训", "insight"), ("路线图", "conclusion"),
    ("渠道策略与排期", "method"), ("常见误区", "problem"),
])
def test_prototype_similarity_classifies_non_academic_headings(title, role):
    result = classify_section({"title": title, "text": "这里是一段普通说明文字，介绍相关情况。"}, 3, 10)
    assert result["role"] == role
    assert result["signal"] == "title-prototype"


def test_uninformative_sections_fall_back_to_content_with_low_confidence():
    result = classify_section({"title": "附注", "text": "略。"})
    assert result["role"] == "content" and result["signal"] == "fallback"


def test_every_domain_preset_has_a_valid_contract_library():
    assert set(DOMAIN_TERMS) - ACADEMIC_PRESETS <= set(PRESET_CONTRACT_LIBRARIES)
    for library in PRESET_CONTRACT_LIBRARIES.values():
        assert library["body"] and library["conclusion"]["title"] and library["agenda"]["bullets"]
        assert {entry["role"] for entry in library["body"]} <= set(ROLE_LABELS)


@pytest.mark.parametrize("preset", sorted(set(DOMAIN_TERMS) - ACADEMIC_PRESETS))
def test_each_preset_plans_cover_first_conclusion_last(preset):
    plan = plan_deck([PITCH], "本地生活增长方案", preset, 10)
    roles = [slide["role"] for slide in plan["slides"]]
    library = PRESET_CONTRACT_LIBRARIES[preset]
    assert roles[0] == "cover" and roles[-1] == "conclusion" and roles.count("cover") == 1
    assert set(roles) <= allowed_roles(preset)
    assert plan["slides"][1]["content"]["title"] == library["agenda"]["title"]
    assert plan["slides"][-1]["content"]["title"] == library["conclusion"]["title"]
    assert [contract["responsibility"] for contract in plan["pageContracts"]][-1] == library["conclusion"]["responsibility"]


def test_pitch_library_routes_team_and_business_model_sections():
    plan = plan_deck([PITCH], "本地生活增长方案", "pitch", 10)
    by_purpose = {slide["purpose"]: slide for slide in plan["slides"]}
    team = by_purpose["团队背景与执行能力"]
    assert team["sourceRefs"][0]["section"] == "S007"
    model = by_purpose["商业模式与收入来源"]
    assert model["sourceRefs"][0]["section"] == "S004"
    assert plan["slides"][1]["content"]["bullets"] == PRESET_CONTRACT_LIBRARIES["pitch"]["agenda"]["bullets"]


def test_business_library_keeps_historical_general_contracts():
    records = [{"role": role, "section": {"title": role}} for role in ("background", "problem", "data", "conclusion")]
    contracts = general_contracts("business", 6, records)
    assert [item["role"] for item in contracts] == ["cover", "background", "problem", "data", "background", "conclusion"]
    assert contracts[1]["responsibility"] == "交代受众背景与核心矛盾"
    assert "keywords" not in contracts[1]
    assert general_contracts("unknown-preset", 6, records) == contracts


def test_material_analysis_reports_uncertain_roles():
    plan = plan_deck([source("notes.md", [
        {"id": "S001", "title": "附注", "text": "略作补充，供参考使用的说明。"},
        {"id": "S002", "title": "实验结果", "text": "准确率 89.6%。"},
    ])], "笔记", "business", 6)
    uncertain = plan["materialAnalysis"]["documents"][0]["uncertainRoles"]
    assert [item["section"] for item in uncertain] == ["S001"]


# --- proposal validation -------------------------------------------------------------------

RESULTS = source("results.md", [
    {"id": "S001", "title": "背景", "text": "人工复核等待时间较长，影响交付效率。"},
    {"id": "S002", "title": "方法", "text": "首先解析资料，然后绑定证据，最后生成候选页面。"},
    {"id": "S003", "title": "验证结果", "text": "新方案准确率达到 89.6%，基线为 71.2%。"},
    {"id": "S004", "title": "风险", "text": "样本仅来自一个部门，不能外推到其他行业。"},
    {"id": "S005", "title": "结论", "text": "建议先在内部推广，再扩大验证范围。"},
])


def base_plan(count=6):
    return plan_deck([RESULTS], "复核提效", "business", count)


def proposal(slide, **changes):
    item = {"position": slide["position"], "role": slide["role"], "title": slide["content"]["title"],
            "message": slide["message"], "bullets": list(slide["content"]["bullets"])}
    item.update(changes)
    return item


def codes(result, position=None):
    return [issue["code"] for issue in result["issues"] if position is None or issue["position"] == position]


def test_clean_proposals_pass_without_issues():
    plan = base_plan()
    proposals = {slide["position"]: proposal(slide) for slide in plan["slides"]}
    result = validate_page_proposals(plan, proposals, preset="business", deck_title="复核提效")
    assert result["issues"] == []
    assert result["summary"]["accepted"] == len(plan["slides"]) and result["summary"]["fallback"] == 0


def test_unsupported_numbers_are_removed_or_replaced():
    plan = base_plan()
    data = next(slide for slide in plan["slides"] if slide["role"] == "data")
    proposals = {data["position"]: proposal(
        data, title="准确率提升到 95%", message="准确率达到 89.6%",
        bullets=["新方案准确率达到 89.6%", "成本降低 40%", "基线准确率 71.2"],
    )}
    result = validate_page_proposals(plan, proposals, preset="business")
    repaired = result["proposals"][data["position"]]
    assert repaired["title"] == data["content"]["title"]
    assert repaired["message"] == "准确率达到 89.6%"
    assert repaired["bullets"] == ["新方案准确率达到 89.6%", "基线准确率 71.2"]
    assert codes(result, data["position"]).count("unsupported-number") == 2
    assert data["proposalIssues"] and data["proposalIssues"][0]["message"]


def test_structure_rules_cover_first_conclusion_last_and_allowed_roles():
    plan = base_plan(6)
    first, middle, last = plan["slides"][0], plan["slides"][2], plan["slides"][-1]
    proposals = {
        1: proposal(first, role="content"),
        3: proposal(middle, role="cover"),
        4: proposal(plan["slides"][3], role="conclusion"),
        5: proposal(plan["slides"][4], role="banana"),
        6: proposal(last, role="method"),
    }
    result = validate_page_proposals(plan, proposals, preset="business")
    assert result["proposals"][1]["role"] == "cover"
    assert result["proposals"][3]["role"] == middle["role"]
    assert result["proposals"][4]["role"] == plan["slides"][3]["role"]
    assert result["proposals"][5]["role"] == plan["slides"][4]["role"]
    assert result["proposals"][6]["role"] == "conclusion"
    assert {"first-page-not-cover", "cover-not-first", "conclusion-not-last", "role-not-allowed",
            "last-page-not-conclusion", "missing-page"} <= set(codes(result))
    assert 2 in result["fallbackPositions"]


def test_duplicate_and_near_duplicate_titles_are_repaired():
    assert near_duplicate("新方案显著提升复核准确率", "新方案显著提升了复核准确率")
    assert not near_duplicate("背景与现状", "风险与边界")
    plan = base_plan(6)
    proposals = {slide["position"]: proposal(slide) for slide in plan["slides"]}
    proposals[3]["title"] = "新方案显著提升复核准确率"
    proposals[4]["title"] = "新方案显著提升了复核准确率"
    proposals[5]["title"] = "新方案显著提升复核准确率"
    result = validate_page_proposals(plan, proposals, preset="business")
    assert set(codes(result)) == {"near-duplicate-title", "duplicate-title"}
    titles = [result["proposals"][position]["title"] for position in (3, 4, 5)]
    assert titles[0] == "新方案显著提升复核准确率"
    assert titles[1] == plan["slides"][3]["content"]["title"]
    assert titles[2] == plan["slides"][4]["content"]["title"]


def test_unknown_evidence_refs_and_budgets_are_enforced():
    plan = base_plan(6)
    slide = plan["slides"][2]
    known = plan["evidence"]["facts"][0]["id"]
    proposals = {3: proposal(
        slide, evidenceRefs=[known, "F9999"],
        bullets=["要点一（F9999）", "要点二", "要点三", "要点四", "要点五", "要点六"],
    )}
    result = validate_page_proposals(plan, proposals, preset="business")
    repaired = result["proposals"][3]
    assert repaired["evidenceRefs"] == [known]
    assert repaired["bullets"][0] == "要点一"
    assert len(repaired["bullets"]) <= 5
    assert {"unknown-evidence-ref", "too-many-bullets"} <= set(codes(result, 3))
    long_page = {3: proposal(slide, bullets=["很长的观众文案" * 20] * 4)}
    budget = validate_page_proposals(plan, long_page, preset="business")
    assert "text-budget" in codes(budget, 3)
    assert len(budget["proposals"][3]["bullets"]) < 4


def test_pages_that_lose_all_copy_fall_back_to_builtin():
    plan = base_plan(6)
    slide = plan["slides"][2]
    result = validate_page_proposals(
        plan, {3: proposal(slide, bullets=["增长 300%", "节省 5000 万元"])}, preset="business", extra_pages=2,
    )
    assert 3 in result["fallbackPositions"] and 3 not in result["proposals"]
    assert "fallback" in codes(result, 3)
    assert result["issues"][0]["code"] == "extra-pages"


def test_planner_model_proposals_are_validated_in_outline_workflow(client, monkeypatch):
    async def fake_chat(_self, _model_id, messages, **_kwargs):
        prompt = messages[-1]["content"]
        if "建立短策略记忆" in prompt:
            return json.dumps({"audience": "管理层", "communicationJob": "决定是否推广", "thesis": "复核提效",
                               "emphasis": ["结果"], "exclusions": [], "sectionGoals": ["问题", "结果"],
                               "visualMood": "克制"})
        if "检查下面的大纲是否围绕中心命题递进" in prompt:
            return json.dumps({"status": "通过", "issues": [], "revisions": []})
        start, end = map(int, re.search(r"本次只规划第 (\d+) 到第 (\d+) 页", prompt).groups())
        return json.dumps({"slides": [
            {"position": position, "role": "cover" if position == 3 else "insight",
             "title": "复核效率提升 300%", "message": "效率显著提升",
             "bullets": ["效率提升 300%", "依据材料组织内容"], "visualType": "typography"}
            for position in range(start, end + 1)
        ]})

    monkeypatch.setattr("app.api.workflow_routes.OpenAICompatibleClient.chat_completion", fake_chat)
    provider = client.post("/api/v1/providers", json={"name": "validator", "base_url": "http://localhost:9000/v1"}).json()
    model = client.post(f"/api/v1/providers/{provider['id']}/models",
                        json={"model_id": "Qwen/Qwen3-8B", "capabilities": ["chat"]}).json()
    client.put("/api/v1/model-routing", json={"role": "planner", "model_config_id": model["id"]})
    project = client.post("/api/v1/projects", json={"name": "校验"}).json()
    upload = client.post(f"/api/v1/projects/{project['id']}/sources", files={"file": (
        "复核.md", "\n".join(f"# {s['title']}\n{s['text']}" for s in RESULTS["sections"]).encode(), "text/markdown",
    )})
    assert upload.status_code == 201, upload.text
    response = client.post(f"/api/v1/projects/{project['id']}/outline",
                           json={"title": "复核提效", "preset": "business", "slide_count": 6})
    assert response.status_code == 200, response.text
    plan = response.json()
    text = json.dumps([slide["content"] for slide in plan["slides"]], ensure_ascii=False)
    assert "300%" not in text
    validation = plan["proposalValidation"]
    assert validation["summary"]["byCode"]["unsupported-number"] >= 6
    assert "cover-not-first" in validation["summary"]["byCode"]
    assert [slide["role"] for slide in plan["slides"]].count("cover") == 1
    assert plan["slides"][-1]["role"] == "conclusion"
    assert any(slide.get("proposalIssues") for slide in plan["slides"])
    assert plan["orchestration"]["policy"]["code"] == "tiny"
