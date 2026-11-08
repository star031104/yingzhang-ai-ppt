import json
import zipfile

from app.presentation_engine.service import presentation_engine
from app.presentation_intelligence.art_director import build_design_system
from app.presentation_intelligence.creative_pages import mark_creative_pages, poster_prompt
from app.workflows.planning_brief import PlanRequest
from PIL import Image


def test_only_navigation_pages_become_creative():
    slides = [{"position": index + 1, "role": role, "visualIntent": {}} for index, role in enumerate(
        ["cover", "agenda", "section", "data", "evidence", "section", "section", "section", "questions"])]
    positions = mark_creative_pages(slides)
    assert positions == [1, 3, 6, 7]  # cover first, then sections, capped at four pages
    assert not any(slide["visualIntent"].get("creativePoster") for slide in slides if slide["role"] in {"data", "evidence"})
    assert PlanRequest(title="t", image_mode="creative").image_mode == "creative"


def test_poster_prompt_reserves_title_area_and_uses_palette():
    slide = {"role": "cover", "content": {"title": "年度经营复盘"}, "designSystem": {"palette": {"deep": "#123456"}}}
    prompt = poster_prompt(slide)
    assert "年度经营复盘" in prompt and "#123456" in prompt and "标题" in prompt


def test_creative_poster_renders_with_editable_title(tmp_path):
    art = tmp_path / "poster.png"
    Image.new("RGB", (1664, 928), (40, 60, 90)).save(art)
    slide = {
        "id": "c1", "position": 1, "role": "cover", "message": "从数据看增长质量",
        "content": {"title": "年度经营复盘", "bullets": []},
        "visualIntent": {"creativePoster": True, "primaryVisual": "generated-image"},
        "assetBindings": [{"type": "generated-image", "path": str(art), "alt": "海报", "provenance": "AI 生成概念图，不作为事实证据"}],
        "designSystem": build_design_system("business", [], {}),
    }
    presentation_engine.run("build", [slide], tmp_path / "rendered")
    current = json.loads((tmp_path / "rendered" / "slides" / "1" / "current.json").read_text(encoding="utf-8"))
    assert current["variant"] == "creative-poster", current
    assert not current["scoreDetail"]["needsReview"], current["scoreDetail"]
    html = (tmp_path / "rendered" / "slides" / "1.html").read_text(encoding="utf-8")
    assert "poster-art" in html and "不作为事实证据" in html
    slide["visualIntent"]["selectedVariant"] = "creative-poster"
    presentation_engine.run("pptx", [slide], tmp_path / "deck.pptx", scene_root=tmp_path / "rendered")
    with zipfile.ZipFile(tmp_path / "deck.pptx") as archive:
        xml = archive.read("ppt/slides/slide1.xml").decode()
    assert "<p:pic" in xml and "年度经营复盘" in xml  # picture background, native title text
