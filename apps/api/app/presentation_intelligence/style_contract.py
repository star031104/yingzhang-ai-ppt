"""Deck-level style contract and Markov-style page continuity.

UniPPTAgent fills one fixed style schema per deck; DeepSlide conditions every
slide on the previous slide's style summary. YingZhang already shares one design
system across pages, but each page still picks its own candidate, which can make
neighbouring pages jump between a dark, dense card wall and an airy statement.

The contract is computed once at outline time and stored in
``designSystem.styleContract``. During deck-level candidate selection every page
gets a ``styleSummary`` (measured from the rendered PNG and the candidate score)
and a ``styleContinuity`` score against the previously selected page. Layout
families may vary (that is rhythm); surface tone, density and visual weight
should change gradually.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

NAVIGATION_ROLES = {"cover", "agenda", "section", "questions"}
VERSION = "style-contract-v1"

DENSITY_RANGES = {
    "compact": (0.30, 0.78),
    "balanced": (0.22, 0.70),
    "airy": (0.16, 0.58),
}


def build_style_contract(design_system: dict, preset: str = "", brief: dict | None = None) -> dict[str, Any]:
    """One fixed style schema per deck, derived from the compiled design system."""
    brief = brief or {}
    grammar = design_system.get("grammar") or {}
    density = str(grammar.get("density") or design_system.get("densityBias") or "balanced")
    if density not in DENSITY_RANGES:
        density = "balanced"
    low, high = DENSITY_RANGES[density]
    forbidden = set(grammar.get("forbidden") or [])
    tone = str(brief.get("tone") or (design_system.get("brand") or {}).get("tone") or "auto")
    restrained = tone in {"formal", "executive"} or preset in {"academic", "public", "executive", "review"}
    title_style = grammar.get("titleStyle") or {}
    palette = design_system.get("palette") or {}
    return {
        "version": VERSION,
        "palette": {key: palette.get(key) for key in ("bg", "ink", "primary", "accent", "deep") if palette.get(key)},
        "fontFamily": (design_system.get("typography") or {}).get("fontFamily"),
        "titleAlign": title_style.get("align", "left"),
        "density": density,
        "occupancyRange": [low, high],
        "maxOccupancyJump": 0.26 if restrained else 0.34,
        "surface": "light",
        # Dark, full-bleed content pages are reserved for navigation pages; content
        # pages may use dark accents but not as the dominant surface.
        "maxContentDarkArea": 0.34 if ("dark-card" in forbidden or restrained) else 0.48,
        "maxDarkContentShare": 0.15 if restrained else 0.25,
        "maxLuminanceJump": 0.30 if restrained else 0.38,
        "decoration": (grammar.get("decoration") or {}).get("intensity", "subtle"),
        "chartStyle": design_system.get("chart", {}),
        "rules": [
            "版式家族可以变化，但相邻内容页的明暗、留白和视觉重量应渐变",
            "大面积深色底只用于封面、章节和问答页",
            "整套字体、主色、标题对齐方式不变",
        ],
    }


def style_summary(png_path: str | Path | None, score: dict) -> dict[str, Any]:
    """Measured style of one rendered candidate (PNG luminance plus engine geometry)."""
    summary: dict[str, Any] = {
        "family": score.get("variantFamily"),
        "occupied": float(score.get("occupied") or 0.0),
        "luminance": None,
        "darkArea": None,
    }
    if not png_path or not Path(png_path).is_file():
        return summary
    try:
        from PIL import Image

        with Image.open(png_path) as image:
            small = image.convert("L").resize((128, 72))
            pixels = list(small.getdata())
    except (OSError, ValueError):
        return summary
    if not pixels:
        return summary
    summary["luminance"] = round(sum(pixels) / (255 * len(pixels)), 3)
    summary["darkArea"] = round(sum(1 for value in pixels if value < 80) / len(pixels), 3)
    return summary


def continuity_score(
    summary: dict[str, Any],
    previous: dict[str, Any] | None,
    contract: dict[str, Any] | None,
    role: str | None,
    dark_content_pages: int = 0,
    content_pages_seen: int = 0,
) -> tuple[int, list[str]]:
    """Score 40-100 for how well a candidate continues the deck; returns reasons."""
    if not contract:
        return 100, []
    score = 100.0
    reasons: list[str] = []
    navigation = role in NAVIGATION_ROLES
    dark_area = summary.get("darkArea")
    if not navigation and dark_area is not None:
        if dark_area > contract["maxContentDarkArea"]:
            score -= 22
            reasons.append("content-page-dark-surface")
        share = (dark_content_pages + (1 if dark_area > contract["maxContentDarkArea"] else 0)) / max(1, content_pages_seen + 1)
        if dark_area > contract["maxContentDarkArea"] and share > contract["maxDarkContentShare"]:
            score -= 12
            reasons.append("dark-page-budget")
    low, high = contract.get("occupancyRange", [0.0, 1.0])
    occupied = float(summary.get("occupied") or 0.0)
    if not navigation and occupied and not (low <= occupied <= high):
        score -= min(18, abs(occupied - (low if occupied < low else high)) * 90)
        reasons.append("density-outside-contract")
    if previous and not navigation and previous.get("role") not in NAVIGATION_ROLES:
        jump = abs(occupied - float(previous.get("occupied") or occupied))
        if jump > contract["maxOccupancyJump"]:
            score -= min(20, (jump - contract["maxOccupancyJump"]) * 100)
            reasons.append("density-jump")
        lum, prev_lum = summary.get("luminance"), previous.get("luminance")
        if lum is not None and prev_lum is not None and abs(lum - prev_lum) > contract["maxLuminanceJump"]:
            score -= 12
            reasons.append("luminance-jump")
    return max(40, round(score)), reasons
