"""Optional creative pages: AI poster backgrounds for cover, section and Q&A pages.

Image-first generators (Nano Banana style) make striking pages, but their text is
baked into pixels. YingZhang keeps the hybrid: only navigation pages may get a
generated full-bleed poster background, the title stays native editable text on
top, and every such page is labelled as AI imagery that is not evidence. Data,
evidence and comparison pages are never eligible.
"""

from __future__ import annotations

CREATIVE_ROLES = ("cover", "section", "questions")
MAX_CREATIVE_PAGES = 4
NOTICE = "背景为 AI 生成图片，在 PowerPoint 中是不可编辑的图片；标题与副标题仍是可编辑文本，不作为事实证据"


def mark_creative_pages(slides: list[dict], limit: int = MAX_CREATIVE_PAGES) -> list[int]:
    """Flag at most ``limit`` navigation pages (cover first) for a poster background."""
    ranked = sorted(
        (slide for slide in slides if slide.get("role") in CREATIVE_ROLES),
        key=lambda slide: (CREATIVE_ROLES.index(slide["role"]), int(slide.get("position") or 0)),
    )[:limit]
    chosen = {id(slide) for slide in ranked}
    positions = []
    for slide in slides:
        visual = dict(slide.get("visualIntent") or {})
        if id(slide) in chosen and visual.get("allowGeneratedImage", True):
            visual.update({"creativePoster": True, "primaryVisual": "generated-image", "allowGeneratedImage": True})
            positions.append(int(slide.get("position") or 0))
        else:
            visual.pop("creativePoster", None)
        slide["visualIntent"] = visual
    return positions


def poster_prompt(slide: dict) -> str:
    design = slide.get("designSystem") or {}
    palette = design.get("palette") or {}
    title = (slide.get("content") or {}).get("title", "")
    role = {"cover": "封面", "section": "章节页", "questions": "问答页"}.get(slide.get("role"), "页面")
    colors = "、".join(value for value in (palette.get("deep"), palette.get("primary"), palette.get("accent")) if value)
    return (
        f"为中文专业演示的{role}制作一张 16:9 海报风格背景图。主题：{title}。"
        f"主色调参考 {colors or '深色背景配一个强调色'}，左侧 55% 区域保持暗部和简洁，留给标题文字；"
        "主体放在右侧，构图有纵深和光影层次，适合作为全幅背景。"
    )


def annotate_creative(slide: dict, binding: dict) -> None:
    slide["creativePage"] = {
        "kind": "poster-background",
        "editable": "text-only",
        "notice": NOTICE,
        "provenance": binding.get("provenance"),
        "model": binding.get("model"),
    }
