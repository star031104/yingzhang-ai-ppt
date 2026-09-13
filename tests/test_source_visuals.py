import io
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

from app.documents import PARSER_VERSION, parse_source
from app.presentation_intelligence.assets import bind_source_figures, normalize_visual_intent
from app.presentation_intelligence.planner import plan_deck


def make_pdf_with_figure() -> bytes:
    image = Image.new("RGB", (800, 420), "white")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((40, 60, 240, 360), radius=20, fill="#625BF6")
    draw.rounded_rectangle((300, 60, 500, 360), radius=20, fill="#78E3C5")
    draw.rounded_rectangle((560, 60, 760, 360), radius=20, fill="#20284D")
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(80, 180, 515, 410), stream=stream.getvalue())
    page.insert_text((95, 438), "Figure 1-1 System architecture and evidence flow", fontsize=12)
    return document.tobytes()


def test_pdf_parser_extracts_renderable_figures_with_caption_and_provenance(tmp_path: Path):
    model = parse_source(
        "paper.pdf",
        make_pdf_with_figure(),
        "application/pdf",
        asset_dir=tmp_path / "assets",
    )
    assert model["parserVersion"] == PARSER_VERSION == "5.5"
    assert len(model["figures"]) == 1
    figure = model["figures"][0]
    assert Path(figure["path"]).is_file()
    assert figure["caption"].startswith("Figure 1-1")
    assert figure["kind"] == "diagram"
    assert figure["provenance"].startswith("paper.pdf · 第 1 页")


def test_source_figure_is_bound_once_and_forces_source_first_visual(tmp_path: Path):
    image = tmp_path / "framework.png"
    Image.new("RGB", (1000, 600), "white").save(image)
    source = {
        "name": "paper.pdf",
        "sections": [{"id": "S013", "title": "总体框架", "text": "系统总体研究框架。", "page": 13}],
        "figures": [{
            "id": "FIG-013-01", "document": "paper.pdf", "page": 13,
            "path": str(image), "caption": "图3-1 总体研究框架图", "kind": "diagram",
            "provenance": "paper.pdf · 第 13 页 · 图3-1 总体研究框架图",
            "width": 1000, "height": 600,
        }],
    }
    plan = {"slides": [
        {
            "position": 1, "role": "architecture", "purpose": "总体框架",
            "message": "总体框架连接知识库与合规分析任务",
            "content": {"title": "总体研究框架", "bullets": ["结构化国标知识", "组织多源应用信息"]},
            "sourceRefs": [{"document": "paper.pdf", "section": "S013", "page": 13}],
            "assetBindings": [], "visualIntent": {"primaryVisual": "diagram"},
        },
        {
            "position": 2, "role": "method", "purpose": "其他方法",
            "message": "方法说明", "content": {"title": "其他方法", "bullets": ["步骤一", "步骤二"]},
            "sourceRefs": [], "assetBindings": [], "visualIntent": {"primaryVisual": "diagram"},
        },
    ]}
    assert bind_source_figures(plan, [source]) == 1
    normalize_visual_intent(plan)
    assert plan["slides"][0]["assetBindings"][0]["type"] == "source-image"
    assert plan["slides"][0]["visualIntent"]["primaryVisual"] == "source-image"
    assert plan["slides"][1]["assetBindings"] == []


def test_refreshing_source_figure_keeps_adjacent_metric_references(tmp_path: Path):
    image = tmp_path / "efficiency.png"
    Image.new("RGB", (1000, 600), "white").save(image)
    source = {
        "name": "paper.pdf",
        "sections": [
            {"id": "S044", "title": "质量", "text": "结构完整率为1.000。", "page": 44},
            {"id": "S045", "title": "效率", "text": "平均耗时为61.87秒。", "page": 45},
            {"id": "S046", "title": "成本", "text": "平均成本为0.0135元。", "page": 46},
        ],
        "figures": [{
            "id": "FIG-045-01", "document": "paper.pdf", "page": 45,
            "path": str(image), "caption": "图5-7 系统效率与时间成本", "kind": "chart",
            "provenance": "paper.pdf · 第45页", "width": 1000, "height": 600,
        }],
    }
    refs = [
        {"document": "paper.pdf", "section": "S044", "page": 44},
        {"document": "paper.pdf", "section": "S045", "page": 45},
        {"document": "paper.pdf", "section": "S046", "page": 46},
    ]
    plan = {"slides": [{
        "position": 1, "role": "insight", "purpose": "系统性能与效率",
        "message": "效率验证", "content": {"title": "系统效率", "bullets": ["平均成本为0.0135元"]},
        "sourceRefs": refs, "assetBindings": [{
            "type": "source-image", "path": str(image), "sourcePage": 45,
        }],
        "visualIntent": {"primaryVisual": "source-image"},
    }]}
    assert bind_source_figures(plan, [source]) == 1
    assert plan["slides"][0]["sourceRefs"] == refs


def test_long_academic_plan_has_section_rhythm_without_losing_conclusion():
    source = {
        "name": "paper.md",
        "sections": [
            {"id": f"S{index:03d}", "title": f"第 {index} 节方法与实验", "text": "研究方法连接实验验证，并保留来源。", "page": index}
            for index in range(1, 30)
        ],
    }
    plan = plan_deck([source], "本科毕业答辩", "academic", 20)
    roles = [slide["role"] for slide in plan["slides"]]
    assert [roles[index - 1] for index in (3, 7, 13)] == ["section", "section", "section"]
    assert plan["slides"][1]["content"]["bullets"][:3] == [
        "第一部分｜研究背景与目标",
        "第二部分｜技术方案与系统实现",
        "第三部分｜实验设计与结果验证",
    ]
    assert "conclusion" in roles[-2:]
    assert roles[-2:] == ["conclusion", "questions"]
    assert "问题" not in plan["slides"][-1]["content"]["title"]


def test_figure_type_contract_blocks_prompt_screenshot_on_result_page(tmp_path: Path):
    prompt_image = tmp_path / "prompt.png"
    chart_image = tmp_path / "chart.png"
    Image.new("RGB", (1000, 600), "white").save(prompt_image)
    Image.new("RGB", (1000, 600), "white").save(chart_image)
    source = {
        "name": "paper.pdf",
        "sections": [{"id": "S020", "title": "实验结果", "text": "准确率为89.6%。", "page": 20}],
        "figures": [
            {"id": "PROMPT", "document": "paper.pdf", "page": 20, "path": str(prompt_image), "caption": "图3-6 Prompt设计", "kind": "prompt"},
            {"id": "CHART", "document": "paper.pdf", "page": 20, "path": str(chart_image), "caption": "图5-1 应用分类实验结果", "kind": "chart"},
        ],
    }
    plan = {"slides": [{
        "position": 1, "role": "data", "purpose": "呈现应用分类实验结果",
        "message": "准确率为89.6%", "content": {"title": "应用分类结果", "bullets": ["准确率为89.6%"]},
        "sourceRefs": [{"document": "paper.pdf", "section": "S020", "page": 20}],
        "assetBindings": [], "visualIntent": {"expectedFigureKinds": ["chart"], "forbiddenFigureKinds": ["prompt"]},
    }]}
    assert bind_source_figures(plan, [source]) == 1
    assert plan["slides"][0]["assetBindings"][0]["sourceFigureId"] == "CHART"


def test_research_gap_page_does_not_borrow_an_unrelated_result_chart(tmp_path: Path):
    chart = tmp_path / "distribution.png"
    Image.new("RGB", (1000, 600), "white").save(chart)
    source = {
        "name": "paper.pdf",
        "sections": [{"id": "S005", "title": "研究现状", "text": "现有方法仍有不足。", "page": 5}],
        "figures": [{"id": "DIST", "document": "paper.pdf", "page": 5, "path": str(chart), "caption": "图5-11 任务标签分布", "kind": "chart"}],
    }
    plan = {"slides": [{
        "position": 1, "role": "comparison", "purpose": "比较现有研究并明确技术缺口",
        "message": "现有方法存在局限", "content": {"title": "现有方法的局限", "bullets": ["尚未解决多源协同问题"]},
        "sourceRefs": [{"document": "paper.pdf", "section": "S005", "page": 5}],
        "assetBindings": [], "visualIntent": {"expectedFigureKinds": ["chart"]},
    }]}
    assert bind_source_figures(plan, [source]) == 0
