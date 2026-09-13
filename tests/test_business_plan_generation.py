import copy

from app.api.workflow_routes import repair_outline_from_builtin
from app.documents import parse_source
from app.documents.parser import _is_contents_page, _is_page_marker
from app.documents.structure import table_record
from app.presentation_intelligence.planner import _record_score, _section_records, plan_deck
from app.validation.quality import validate_deck
from collections import Counter


BUSINESS_PLAN = """
# 第一章 项目介绍
项目面向稀有血型应急保障，建立从科普、登记到紧急招募的服务闭环。
# 第二章 市场分析
政策要求提升血液保障数字化能力，目标用户需要更及时的供需匹配。
# 第三章 产品概况
产品包含知识问答、个性化推荐、献血预约、紧急招募和库存预警。
# 第四章 市场营销
项目通过校园科普、机构合作和用户转介绍形成持续增长渠道。
# 第五章 创业团队
团队覆盖产品、研发、运营和医学顾问，并按迭代周期协同交付。
# 第六章 财务预测
收入来自机构服务和科普合作，成本主要包括研发、服务器和推广。
# 第七章 资本结构
启动资金用于产品研发、试点运营和合规保障，资金按阶段投入。
# 第八章 风险分析
主要风险包括技术稳定性、市场认知和组织管理，并设置对应措施。
""".strip()


def business_source():
    return parse_source("献血服务商业计划书.md", BUSINESS_PLAN.encode("utf-8"), "text/markdown")


def test_pdf_navigation_text_is_not_treated_as_evidence():
    assert _is_page_marker("第 1 页")
    assert _is_page_marker("- 12 -")
    assert _is_contents_page(
        "目录\n第一章项目介绍........1\n第二章市场分析........3\n"
        "第三章产品概况........6\n第四章市场营销........9\n第五章创业团队........12\n"
    )


def test_business_plan_uses_defense_story_and_populates_agenda():
    source = business_source()
    assert source["documentProfile"]["presentationMode"] == "business-plan"
    plan = plan_deck([source], "献血服务项目", "academic", 20)
    assert len(plan["slides"]) == 20
    assert plan["slides"][1]["content"]["title"] == "答辩逻辑"
    assert len(plan["slides"][1]["content"]["bullets"]) == 4
    purposes = " ".join(slide["purpose"] for slide in plan["slides"])
    for expected in ("产品", "市场营销", "团队", "财务", "风险"):
        assert expected in purposes
    titles = [slide["content"]["title"] for slide in plan["slides"]]
    assert not any(title.replace(" ", "") == "第1页" for title in titles)


def test_invalid_model_pages_are_automatically_recovered_from_source_plan():
    source = business_source()
    builtin = plan_deck([source], "献血服务项目", "academic", 20)
    degraded = copy.deepcopy(builtin)
    degraded["slides"][1]["content"]["bullets"] = []
    degraded["slides"][2]["content"]["title"] = "第 1 页"
    degraded["slides"][4]["content"] = copy.deepcopy(degraded["slides"][3]["content"])
    degraded["slides"][4]["message"] = degraded["slides"][3]["message"]
    degraded["slides"][5]["sourceRefs"] = [
        {"document": source["name"], "section": section["id"], "page": section.get("page")}
        for section in source["sections"]
    ] * 2
    degraded["slides"][6]["content"]["bullets"][0] += "，预计增长98765%"

    before = validate_deck(degraded["slides"], [source])
    assert before["blockingErrors"] >= 4
    repaired = repair_outline_from_builtin(degraded, builtin, [source])

    assert {2, 3, 5, 6, 7}.issubset(set(repaired["repairedPositions"]))
    after = validate_deck(degraded["slides"], [source])
    remaining = {
        issue["code"] for issue in after["issues"] if issue["severity"] == "error"
    }
    assert not remaining.intersection({
        "empty-agenda", "placeholder-slide-title", "duplicate-slide-content",
        "repeated-message", "excessive-source-window", "weak-source-grounding",
        "unsupported-metric",
    })


def test_shortened_business_agenda_is_restored_to_all_planned_phases():
    source = business_source()
    builtin = plan_deck([source], "献血服务项目", "academic", 20)
    degraded = copy.deepcopy(builtin)
    degraded["slides"][1]["content"]["bullets"] = degraded["slides"][1]["content"]["bullets"][:3]
    repaired = repair_outline_from_builtin(degraded, builtin, [source])
    assert 2 in repaired["repairedPositions"]
    assert degraded["slides"][1]["content"]["bullets"] == builtin["slides"][1]["content"]["bullets"]


def test_accounting_parentheses_support_negative_cashflow_values():
    source = {
        "name": "finance.pdf",
        "sections": [{"id": "S1", "title": "现金流量表", "text": "技术成本（10.0），经营活动净流量（2.0）。"}],
    }
    slide = {
        "position": 1, "role": "data", "message": "现金流量",
        "content": {"title": "现金流量表", "bullets": ["技术成本：-10.0", "经营活动净流量：-2.0"]},
        "sourceRefs": [{"document": "finance.pdf", "section": "S1"}],
        "evidenceBindings": ["F1"], "visualIntent": {"primaryVisual": "table"},
        "constraints": {"maxTextDensity": 420},
    }
    report = validate_deck([slide], [source])
    assert not any(issue["code"] == "unsupported-metric" for issue in report["issues"])


def test_model_cannot_replace_structured_source_table_rows():
    source = {"name": "finance.pdf", "sections": [{"id": "S1", "title": "销售预测", "text": "第一年5万元，第二年8万元。"}]}
    baseline_slide = {
        "id": "s1", "position": 1, "role": "data", "message": "销售预测按原始表格口径呈现",
        "content": {"title": "销售预测", "bullets": [
            "公益采购：第一年：5.0；第二年：8.0",
            "企业合作：第一年：3.0；第二年：5.0",
        ]},
        "sourceRefs": [{"document": "finance.pdf", "section": "S1"}],
        "evidenceBindings": ["F1"], "constraints": {"maxTextDensity": 420},
    }
    model_slide = copy.deepcopy(baseline_slide)
    model_slide["content"]["bullets"] = ["收入将持续增长"]
    plan, builtin = {"slides": [model_slide]}, {"slides": [baseline_slide]}
    repaired = repair_outline_from_builtin(plan, builtin, [source])
    assert repaired["repairedPositions"] == [1]
    assert plan["slides"][0]["content"]["bullets"] == baseline_slide["content"]["bullets"]


def test_merged_table_title_row_uses_real_column_headers():
    table = table_record([
        ["销售预测表（三年明细）", "", "", ""],
        ["收入来源", "第一年", "第二年", "第三年"],
        ["政府公益采购", "5.0", "8.0", "10.0"],
        ["总收入", "8.0", "15.0", "25.0"],
    ], table_id="T1", document="plan.pdf", section="S1")
    assert table["headers"] == ["收入来源", "第一年", "第二年", "第三年"]
    assert table["headerRowIndex"] == 1
    assert table["rowStatements"] == [
        "政府公益采购：第一年：5.0；第二年：8.0；第三年：10.0",
        "总收入：第一年：8.0；第二年：15.0；第三年：25.0",
    ]


def test_financial_contract_rejects_heading_with_unrelated_management_body():
    source = {
        "name": "plan.pdf",
        "sections": [
            {"id": "S1", "title": "第六章财务预测", "text": "Scrum双周迭代，产品经理评审需求，团队使用Jira管理任务。", "semanticRole": "data", "importance": .6},
            {"id": "S2", "title": "（一）现金流量表", "text": "政府资金流入8万元，推广成本10万元，经营活动净流量-2万元。", "semanticRole": "data", "importance": .6},
        ],
        "tables": [],
    }
    records = _section_records([source])
    contract = {"role": "data", "responsibility": "财务预测、现金流与增长路径", "targets": ["data"], "keywords": ["财务预测", "现金流量"]}
    scores = {record["section"]["id"]: _record_score(record, contract, Counter()) for record in records}
    assert scores["S2"] > scores["S1"]
