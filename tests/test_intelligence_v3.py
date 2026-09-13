from pathlib import Path
from types import SimpleNamespace

from app.api.workflow_routes import (
    academic_metric_story_bullets,
    academic_result_source_refs,
    academic_result_topics,
    best_source_refs,
    clean_audience_bullet,
    sanitize_numeric_claims,
)
from app.intelligence.evidence import extract_evidence_graph, split_sentences
from app.intelligence.retrieval import retrieve_source_context
from app.presentation_intelligence.art_director import build_design_system
from app.presentation_intelligence.planner import plan_deck
from app.presentation_intelligence.small_model import (
    bounded_batch_context,
    build_execution_contract,
    compatible_primary_visual,
    infer_model_policy,
    safe_role_proposal,
    stable_primary_visual,
)
from app.presentation_intelligence.visual_critic import apply_safe_repairs, deterministic_review
from app.skills.manager import resolve_skill_context
from app.validation.quality import validate_deck
from app.validation.visual_maturity import assess_visual_maturity


def source(name: str, sections: list[dict]) -> dict:
    return {"name": name, "sections": sections, "metadata": {}}


def test_decimal_metrics_are_not_split_and_are_bound_to_sources():
    text = "基线准确率为 71.2%，改进后达到 89.6%。其余描述保持不变。"
    sentences = split_sentences(text)
    assert "71.2%" in sentences[0] and "89.6%" in sentences[0]
    assert not any(item in sentences for item in ("2%", "6%"))
    graph = extract_evidence_graph([
        source("report.md", [{"id": "S001", "title": "结果", "text": text}])
    ])
    values = {metric["raw"] for metric in graph["metrics"]}
    assert {"71.2%", "89.6%"}.issubset(values)
    assert any(edge["type"] == "MetricToSource" for edge in graph["edges"])
    attached = extract_evidence_graph([
        source("attached.md", [{"id": "S002", "title": "结果", "text": "准确率达到0.8981，F1-score为0.9333。"}])
    ])
    attached_values = {metric["raw"] for metric in attached["metrics"]}
    assert {"0.8981", "0.9333"}.issubset(attached_values)
    assert "1" not in attached_values


def test_pdf_soft_line_breaks_are_rejoined_before_evidence_extraction():
    sentences = split_sentences(
        "模型在二分类任务中表现稳定，其中 Accuracy 达到0.8981，\n"
        "Precision 为0.9390，Recall 为0.9277。\n"
        "5.2.2 多分类性能分析\n"
        "多分类 Accuracy 为0.8554。"
    )
    assert any("0.8981" in item and "0.9390" in item and "0.9277" in item for item in sentences)
    assert any(item.startswith("5.2.2") for item in sentences)


def test_model_section_numbers_and_table_references_are_not_audience_bullets():
    assert clean_audience_bullet("5.3.1 整体检索性能对比分析") == ""
    assert clean_audience_bullet("检索整体性能对比结果如表5-3所示") == ""
    assert clean_audience_bullet("（1）多任务合规分析评估集构建") == "多任务合规分析评估集构建"
    assert clean_audience_bullet("端到端模型存在上下文限制（S003）") == "端到端模型存在上下文限制"
    assert clean_audience_bullet("应用分类准确率提升 (S)") == "应用分类准确率提升"


def test_visual_reflection_only_applies_safe_existing_candidates():
    snapshots = [{
        "slideId": "slide-1", "position": 1, "title": "结果",
        "selectedVariant": "metric-wall", "selectionSource": "auto", "imagePath": "",
        "candidates": [
            {"variant": "metric-wall", "score": {"overall": 82, "geometry": 92, "readability": 72, "hierarchy": 90, "whitespace": 80, "semanticFit": 100, "tooSmall": 2}},
            {"variant": "chart-focus", "score": {"overall": 86, "geometry": 94, "readability": 91, "hierarchy": 92, "whitespace": 84, "semanticFit": 100}},
        ],
    }]
    reviews = deterministic_review(snapshots)
    slides = [{"id": "slide-1", "position": 1, "visualIntent": {"selectedVariant": "metric-wall"}}]
    applied = apply_safe_repairs(slides, snapshots, reviews)
    assert applied == [{"position": 1, "from": "metric-wall", "to": "chart-focus"}]
    assert slides[0]["visualIntent"]["variantSelectionSource"] == "critic"

    snapshots[0]["selectionSource"] = "user"
    slides[0]["visualIntent"] = {"selectedVariant": "metric-wall"}
    assert apply_safe_repairs(slides, snapshots, reviews) == []

    snapshots[0]["selectionSource"] = "critic"
    slides[0]["visualIntent"] = {"selectedVariant": "chart-focus", "variantSelectionSource": "critic"}
    assert apply_safe_repairs(slides, snapshots, reviews) == []


def test_visual_reflection_preserves_structured_data_objects_when_varying_layouts():
    snapshots = [{
        "slideId": "slide-1", "position": 1, "title": "结果",
        "selectedVariant": "table-highlight", "selectionSource": "auto", "imagePath": "",
        "candidates": [
            {"variant": "table-highlight", "score": {"overall": 99, "geometry": 100, "readability": 100, "hierarchy": 100, "whitespace": 92, "semanticFit": 100}},
            {"variant": "process", "score": {"overall": 96, "geometry": 100, "readability": 100, "hierarchy": 100, "whitespace": 73, "semanticFit": 100}},
        ],
    }]
    slides = [{"id": "slide-1", "position": 1, "visualIntent": {"primaryVisual": "table", "selectedVariant": "table-highlight"}}]
    reviews = [{"position": 1, "issues": ["repetition"], "recommendedVariant": "process", "confidence": 0.9}]
    assert apply_safe_repairs(slides, snapshots, reviews) == []
    assert slides[0]["visualIntent"]["selectedVariant"] == "table-highlight"


def test_visual_reflection_keeps_multi_year_series_as_chart():
    snapshots = [{
        "slideId": "slide-15", "position": 15, "title": "销售预测",
        "selectedVariant": "chart-focus", "selectionSource": "auto", "imagePath": "",
        "candidates": [
            {"variant": "chart-focus", "score": {"overall": 91, "geometry": 95, "readability": 92, "hierarchy": 94, "whitespace": 68, "semanticFit": 100}},
            {"variant": "metric-wall", "score": {"overall": 94, "geometry": 98, "readability": 96, "hierarchy": 96, "whitespace": 90, "semanticFit": 100}},
        ],
    }]
    slides = [{
        "id": "slide-15", "position": 15,
        "content": {"bullets": [
            "政府公益采购：第一年：5.0；第二年：8.0；第三年：10.0",
            "企业合作收入：第一年：3.0；第二年：5.0；第三年：8.0",
            "总收入：第一年：8.0；第二年：15.0；第三年：25.0",
        ]},
        "visualIntent": {"primaryVisual": "chart", "selectedVariant": "chart-focus"},
    }]
    reviews = [{"position": 15, "issues": ["imbalance"], "recommendedVariant": "metric-wall", "confidence": 0.9}]
    assert apply_safe_repairs(slides, snapshots, reviews) == []
    assert slides[0]["visualIntent"]["selectedVariant"] == "chart-focus"


def test_academic_result_page_uses_complete_cited_metrics_instead_of_half_sentences():
    materials = [source("paper.pdf", [
        {
            "id": "S034", "title": "第34页", "page": 34,
            "text": (
                "5.2 应用分类实验结果分析。模型在二分类任务中表现稳定，"
                "Accuracy达到0.8981，Precision为0.9390，Recall为0.9277，F1-score为0.9333。"
            ),
        },
        {
            "id": "S035", "title": "第35页", "page": 35,
            "text": (
                "模型在多分类任务中的Accuracy为0.8554，Weighted F1达到0.8818。"
                "Macro Precision、Macro Recall和Macro F1分别为0.5424、0.5037和0.5128。"
            ),
        },
        {
            "id": "S036", "title": "第36页", "page": 36,
            "text": (
                "部分类别的F1-score接近1.0；中等类别的F1-score集中在0.8至0.9之间；"
                "较难类别的F1-score则下降至0.7左右；个别类别甚至接近0。"
            ),
        },
    ])]
    refs = academic_result_source_refs("应用分类实验结果与误差分析", materials)
    bullets = academic_metric_story_bullets("应用分类实验结果与误差分析", refs, materials)
    assert [ref["section"] for ref in refs] == ["S034", "S035", "S036"]
    assert len(bullets) == 4
    assert bullets[0].endswith("F1 0.9333")
    assert any("Weighted F1 0.8818" in bullet for bullet in bullets)
    assert all(not bullet.endswith(("至", "为", "，")) for bullet in bullets)


def test_academic_metric_story_does_not_activate_without_matching_source_values():
    materials = [source("other.pdf", [{
        "id": "S001", "title": "结果", "page": 1,
        "text": "本研究完成了另一类实验，但没有应用分类指标。",
    }])]
    assert academic_metric_story_bullets(
        "应用分类实验结果", [{"document": "other.pdf", "section": "S001"}], materials
    ) == []


def test_academic_result_topics_are_discovered_from_document_headings():
    materials = [source("paper.pdf", [{
        "id": "S050", "title": "实验章节", "page": 50,
        "text": (
            "5.1 实验设置\n5.2 应用分类实验结果分析\n"
            "5.3 RAG 检索效果实验结果分析\n5.4 多任务合规分析实验结果分析\n"
            "5.5 合规分析报告质量与系统效率分析\n5.6 消融实验结果分析"
        ),
    }])]
    assert academic_result_topics(materials) == [
        "应用分类实验结果分析",
        "RAG 检索效果实验结果分析与消融分析",
        "多任务合规分析实验结果分析",
        "合规分析报告质量与系统效率分析",
    ]


def test_retrieval_can_reach_sections_after_old_16000_character_limit():
    sections = [
        {"id": "S001", "title": "背景", "text": "背景材料。" * 5000},
        {"id": "S002", "title": "实验结论", "text": "最终实验准确率达到 89.6%，并优于基线。"},
    ]
    context = retrieve_source_context(
        [source("long.md", sections)], "实验准确率 89.6%", "academic", "突出实验结论", limit=24000
    )
    assert "89.6%" in context
    assert "S002" in context


def test_short_material_still_gets_conclusion_without_invented_metrics():
    materials = [source("brief.md", [
        {"id": "S001", "title": "方法", "text": "先解析资料，再绑定证据，最后生成候选页面。"},
        {"id": "S002", "title": "结果", "text": "测试准确率为 89.6%。"},
    ])]
    plan = plan_deck(materials, "证据演示", "academic", 8)
    assert len(plan["slides"]) == 8
    assert plan["slides"][-2]["role"] == "conclusion"
    assert max(
        sum(1 for item in plan["slides"] if item["role"] == role)
        for role in {item["role"] for item in plan["slides"]}
    ) < 6
    report = validate_deck(plan["slides"], materials)
    assert report["blockingErrors"] == 0
    assert set(report["professionalAudit"]["dimensions"]) == {
        "fundamentals", "visualDesign", "completeness", "correctness", "fidelity"
    }


def test_art_direction_adapts_to_preset_tone_and_communication_objective():
    academic = build_design_system("academic", [], {
        "audience": "答辩委员会", "objective": "证明方法有效", "durationMinutes": 15,
    })
    energetic = build_design_system("business", [], {"tone": "energetic"})
    assert academic["layoutProfile"] == "editorial-story"
    assert academic["communication"] == {
        "audience": "答辩委员会",
        "objective": "证明方法有效",
        "durationMinutes": 15,
        "coverStrapline": "证明方法有效",
    }
    assert energetic["layoutProfile"] == "nebula-tech"


def test_visual_maturity_detects_repeated_silhouettes_and_rewards_real_rhythm():
    roles = ["background", "problem", "method", "architecture", "data", "comparison", "insight", "conclusion"]
    repeated = [
        {
            "position": index,
            "role": role,
            "content": {"title": f"页面 {index}", "bullets": ["要点一", "要点二", "要点三"]},
            "visualIntent": {"primaryVisual": "cards", "selectedVariant": "context-cards"},
        }
        for index, role in enumerate(roles, 2)
    ]
    diverse_variants = [
        ("big-statement", "typography"), ("contrast", "diagram"), ("workflow", "diagram"),
        ("layered-architecture", "diagram"), ("chart-focus", "chart"),
        ("two-column", "chart"), ("finding-cards", "cards"), ("next-steps", "diagram"),
    ]
    diverse = [
        {
            **slide,
            "visualIntent": {"selectedVariant": variant, "primaryVisual": primary},
        }
        for slide, (variant, primary) in zip(repeated, diverse_variants)
    ]
    repeated_result = assess_visual_maturity(repeated)
    diverse_result = assess_visual_maturity(diverse)
    assert any(issue["code"] == "repetitive-layout-silhouette" for issue in repeated_result["issues"])
    assert diverse_result["uniqueFamilies"] >= 6
    assert diverse_result["score"] > repeated_result["score"]


def test_qwen_8b_uses_tiny_policy_and_rules_keep_structural_ownership():
    materials = [source("paper.md", [
        {"id": "S001", "title": "背景", "text": "现有流程难以保持数字与来源一致。"},
        {"id": "S002", "title": "方法", "text": "系统先建立页面契约，再让模型填写局部文案。"},
        {"id": "S003", "title": "结果", "text": "测试准确率达到89.6%。"},
    ])]
    plan = plan_deck(materials, "小模型演示编排", "academic", 20)
    policy = infer_model_policy("Qwen/Qwen3-8B")
    contract = build_execution_contract(plan, "Qwen/Qwen3-8B")
    assert policy.code == "tiny"
    assert policy.batch_size == 3
    assert policy.context_limit == 7600
    assert len(contract["batches"]) == 7
    assert contract["batches"][2]["start"] == 7
    assert "总页数、页面顺序与开场收束位置" in contract["ruleOwned"]
    assert "受众、中心命题、重点与章节目标提案" in contract["modelOwned"]


def test_batch_context_is_bounded_to_referenced_evidence():
    materials = [source("long.md", [
        {"id": "S001", "title": "方法", "text": "页面契约和证据白名单。" * 1000},
        {"id": "S002", "title": "无关附录", "text": "这部分不应挤占主要证据窗口。" * 1000},
    ])]
    plan = plan_deck(materials, "受控上下文", "academic", 8)
    context = bounded_batch_context(
        materials, plan["slides"][2:4], "受控上下文", "academic", "突出方法", 1800
    )
    assert len(context) <= 1800
    assert "【资料：" in context


def test_visual_semantics_are_deterministic_not_chosen_by_tiny_model():
    assert stable_primary_visual({"role": "data", "assetBindings": []}) == "chart"
    assert stable_primary_visual({"role": "architecture", "assetBindings": []}) == "diagram"
    assert stable_primary_visual({
        "role": "data", "assetBindings": [{"type": "source-image"}],
    }) == "source-image"
    assert safe_role_proposal(
        {"position": 6, "role": "method", "phase": "method"}, "architecture", "academic", 12
    ) == "architecture"
    assert safe_role_proposal(
        {"position": 6, "role": "method", "phase": "method"}, "data", "academic", 12
    ) == "method"
    assert compatible_primary_visual({"role": "data", "assetBindings": []}, "generated-image") == "chart"


def test_claim_qa_rejects_renderer_or_model_invented_number():
    materials = [source("truth.md", [{"id": "S001", "title": "结果", "text": "准确率为 89.6%。"}])]
    slide = {
        "position": 1, "role": "data", "message": "准确率达到 8.6%",
        "content": {"title": "结果 1", "bullets": ["准确率达到 8.6%"]},
        "sourceRefs": [{"document": "truth.md", "section": "S001"}],
        "evidenceBindings": ["F0001"], "constraints": {"maxTextDensity": 420},
    }
    report = validate_deck([slide], materials)
    assert report["blockingErrors"] > 0
    assert any(issue["code"] == "unsupported-metric" for issue in report["issues"])


def test_numeric_source_matching_and_model_claim_sanitizing():
    materials = [source("truth.md", [{
        "id": "S005", "title": "消融实验",
        "text": "视觉质量评分从 86.3 分下降到 72.8 分。",
    }])]
    refs = best_source_refs("质量评分下降 13.5 分，参见 S005", materials)
    assert refs[0]["section"] == "S005"
    graph = extract_evidence_graph(materials)
    slide = {
        "message": "质量评分下降 13.5 分", "sourceRefs": refs,
        "content": {"title": "消融实验", "bullets": ["质量评分下降 13.5 分（S005）"]},
    }
    sanitize_numeric_claims(slide, graph, materials)
    assert "13.5" not in slide["content"]["bullets"][0]
    assert "86.3" in slide["content"]["bullets"][0]
    slide["content"]["bullets"] = ["视觉质量下降 72.8 分"]
    sanitize_numeric_claims(slide, graph, materials)
    assert "下降到 72.8" in slide["content"]["bullets"][0]


def test_topic_only_brief_removes_model_invented_metrics():
    materials = [source("创作简报（未上传材料）", [{
        "id": "BRIEF-001", "title": "用户创作说明", "text": "围绕会议决策效率给出通用方法。",
    }])]
    slide = {
        "message": "会议需要转向决策",
        "sourceRefs": [{"document": "创作简报（未上传材料）", "section": "BRIEF-001"}],
        "content": {"title": "减少无效同步", "bullets": ["60%时间用于信息重复确认", "会前筛选议题"]},
    }
    sanitize_numeric_claims(slide, extract_evidence_graph(materials), materials)
    assert "60%" not in slide["content"]["bullets"][0]
    assert "时间用于信息重复确认" not in slide["content"]["bullets"]
    assert "会前筛选议题" in slide["content"]["bullets"]


def test_numeric_sanitizer_never_replaces_a_claim_with_a_bare_page_number():
    materials = [source("paper.pdf", [{
        "id": "S017", "title": "实验结果",
        "text": "第 4 页记录了实验设置，隐私政策检测准确率为 71.46%。",
    }])]
    graph = {
        "facts": [
            {"claim": "4", "sourceRef": {"document": "paper.pdf", "section": "S017"}},
            {"claim": "隐私政策检测准确率为 71.46%。", "sourceRef": {"document": "paper.pdf", "section": "S017"}},
        ]
    }
    slide = {
        "message": "隐私政策检测准确率", 
        "sourceRefs": [{"document": "paper.pdf", "section": "S017"}],
        "content": {"title": "检测结果", "bullets": ["检测准确率达到 70%", "36", "果的准确性与可追溯性[19]"]},
    }
    sanitize_numeric_claims(slide, graph, materials)
    assert slide["content"]["bullets"] == ["隐私政策检测准确率为 71.46%"]


def test_duplicate_non_navigation_titles_are_blocking():
    materials = [source("paper.md", [{"id": "S001", "title": "结论", "text": "系统完成验证。"}])]
    slides = [
        {
            "position": position,
            "role": "content" if position < 11 else "conclusion",
            "message": f"结论 {position}",
            "content": {"title": "重复的研究结论" if position in {2, 9} else f"页面 {position}", "bullets": []},
            "sourceRefs": [{"document": "paper.md", "section": "S001"}],
            "evidenceBindings": [],
            "visualIntent": {"primaryVisual": "diagram"},
            "constraints": {"maxTextDensity": 420},
        }
        for position in range(1, 13)
    ]
    report = validate_deck(slides, materials)
    assert report["passed"] is False
    assert any(issue["code"] == "duplicate-slide-title" for issue in report["issues"])


def test_semantic_completeness_finds_important_unrepresented_sections():
    materials = [source("paper.md", [
        {"id": "S001", "title": "方法", "text": "系统通过证据契约限定模型输出范围并校验数字。", "semanticRole": "method", "importance": 0.9},
        {"id": "S002", "title": "核心结果", "text": "实验表明方法准确率达到 89.6%，明显高于基线。", "semanticRole": "data", "importance": 1.0},
    ])]
    slides = [{
        "position": 1, "role": "conclusion", "message": "证据契约限定模型输出范围",
        "content": {"title": "方法结论", "bullets": ["系统同时校验数字"]},
        "sourceRefs": [{"document": "paper.md", "section": "S001"}],
        "evidenceBindings": [], "visualIntent": {"primaryVisual": "diagram"},
        "constraints": {"maxTextDensity": 420},
    }]
    report = validate_deck(slides, materials)
    semantic = report["semanticCompleteness"]
    assert semantic["coveredSections"] == 1
    assert semantic["requiredSections"] == 2
    assert semantic["missing"][0]["section"] == "S002"
    assert report["professionalAudit"]["dimensions"]["completeness"] < 100


def test_skill_runtime_reads_workflow_and_references_but_never_runs_scripts(tmp_path: Path):
    (tmp_path / "SKILL.md").write_text("---\nname: demo\n---\n# 版式规则\n保持留白。", encoding="utf-8")
    (tmp_path / "references").mkdir()
    (tmp_path / "references" / "colors.md").write_text("主色使用靛蓝。", encoding="utf-8")
    (tmp_path / "run.py").write_text("raise RuntimeError('不应执行')", encoding="utf-8")
    skill = SimpleNamespace(
        id="demo", path=str(tmp_path), manifest={"entrypoint": "SKILL.md", "name": "演示技能"},
        scripts_enabled=False,
    )
    resolved = resolve_skill_context([skill])
    assert "保持留白" in resolved[0]["workflow"]
    assert "主色使用靛蓝" in resolved[0]["resources"][0]["content"]
    assert resolved[0]["scriptsExecuted"] is False


def test_skill_runtime_shares_context_budget_across_selected_skills(tmp_path: Path):
    skills = []
    for index in range(4):
        root = tmp_path / str(index)
        root.mkdir()
        (root / "SKILL.md").write_text("规则" * 10000, encoding="utf-8")
        skills.append(SimpleNamespace(
            id=f"skill-{index}", path=str(root),
            manifest={"entrypoint": "SKILL.md", "name": f"技能 {index}"},
            scripts_enabled=False,
        ))
    resolved = resolve_skill_context(skills, total_limit=24000)
    assert len(resolved) == 4
    assert all(0 < len(item["workflow"]) <= 6000 for item in resolved)
