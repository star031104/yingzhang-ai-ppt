"""Layout grammar carried by visual skills (tokens.json).

All grammar fields are optional so tokens written before the grammar existed
remain valid. Mirrors ``packages/skill-schema/src/index.js``.
"""

from __future__ import annotations

import math
import re
from typing import Any

GRAMMAR_VERSION = "visual-grammar-v1"
GRAMMAR_FIELDS = (
    "grid", "typeScale", "density", "decoration", "titleStyle", "chartStyle", "iconStyle", "forbidden",
)
DENSITIES = ("compact", "balanced", "airy")
MOTIFS = ("orb", "glow", "rule", "corner", "grid-lines", "quote-mark", "seal", "band", "dots", "frame")
TITLE_ACCENTS = ("none", "bar", "underline", "kicker", "numeral")
FORBIDDEN_PATTERNS = (
    "gradient", "shadow", "orb", "rounded-card", "dark-card", "icons", "centered-body",
    "all-caps", "serif-title", "glow", "decorative-quote",
)
PALETTE_KEYS = ("primary", "accent", "deep", "ink", "line", "bg", "muted")
TYPE_RANGES = {
    "display": (36, 104), "title": (26, 68), "subtitle": (15, 36), "body": (14, 28), "caption": (9, 16),
}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def _within(value: float | None, bounds: tuple[float, float]) -> bool:
    return value is not None and bounds[0] <= value <= bounds[1]


def _grid(value: Any, errors: list[str]) -> dict | None:
    if not isinstance(value, dict):
        errors.append("grid must be an object")
        return None
    margin = value.get("margin")
    margin = margin if isinstance(margin, dict) else {"x": margin, "top": margin, "bottom": margin}
    columns, gutter = _number(value.get("columns")), _number(value.get("gutter"))
    x = _number(margin.get("x"))
    top = _number(margin.get("top", margin.get("x")))
    bottom = _number(margin.get("bottom", margin.get("x")))
    if columns is None or columns != int(columns) or not _within(columns, (4, 16)):
        errors.append("grid.columns must be an integer between 4 and 16")
    elif not (_within(x, (32, 140)) and _within(top, (24, 120)) and _within(bottom, (24, 100))):
        errors.append("grid.margin is outside the safe slide area")
    elif not _within(gutter, (8, 64)):
        errors.append("grid.gutter must be between 8 and 64 px")
    else:
        return {"columns": int(columns), "margin": {"x": x, "top": top, "bottom": bottom}, "gutter": gutter}
    return None


def _type_scale(value: Any, errors: list[str]) -> dict | None:
    if not isinstance(value, dict):
        errors.append("typeScale must be an object")
        return None
    scale = {}
    for key, bounds in TYPE_RANGES.items():
        size = _number(value.get(key))
        if not _within(size, bounds):
            errors.append(f"typeScale.{key} must be between {bounds[0]} and {bounds[1]} px")
        else:
            scale[key] = size
    order = list(TYPE_RANGES)
    if len(scale) != len(order):
        return None
    if any(scale[order[index]] > scale[order[index - 1]] for index in range(1, len(order))):
        errors.append("typeScale must descend from display to caption")
        return None
    return scale


def _title_style(value: Any, errors: list[str]) -> dict | None:
    value = value if isinstance(value, dict) else {}
    style = {
        "align": value.get("align", "left"), "weight": _number(value.get("weight", 800)),
        "tracking": _number(value.get("tracking", -0.03)), "case": value.get("case", "none"),
        "font": value.get("font", "sans"), "accent": value.get("accent", "none"),
    }
    if style["align"] not in ("left", "center"):
        errors.append("titleStyle.align must be left or center")
    elif not _within(style["weight"], (300, 900)):
        errors.append("titleStyle.weight must be between 300 and 900")
    elif not _within(style["tracking"], (-0.08, 0.2)):
        errors.append("titleStyle.tracking must be between -0.08 and 0.2 em")
    elif style["case"] not in ("none", "upper"):
        errors.append("titleStyle.case must be none or upper")
    elif style["font"] not in ("sans", "serif"):
        errors.append("titleStyle.font must be sans or serif")
    elif style["accent"] not in TITLE_ACCENTS:
        errors.append(f"titleStyle.accent must be one of {', '.join(TITLE_ACCENTS)}")
    else:
        return style
    return None


def _chart_style(value: Any, errors: list[str]) -> dict | None:
    value = value if isinstance(value, dict) else {}
    palette = value.get("palette", ["primary", "accent", "deep", "muted"])
    style = {
        "palette": palette, "gridlines": value.get("gridlines", "horizontal"),
        "dataLabels": value.get("dataLabels") is not False, "barRadius": _number(value.get("barRadius", 2)),
    }
    if not isinstance(palette, list) or not 2 <= len(palette) <= 8 or any(
        item not in PALETTE_KEYS and not _HEX.match(str(item)) for item in palette
    ):
        errors.append("chartStyle.palette must list 2-8 palette keys or #RRGGBB colours")
    elif style["gridlines"] not in ("none", "horizontal", "both"):
        errors.append("chartStyle.gridlines must be none, horizontal or both")
    elif not _within(style["barRadius"], (0, 12)):
        errors.append("chartStyle.barRadius must be between 0 and 12")
    else:
        return style
    return None


def normalize_visual_grammar(tokens: Any) -> tuple[dict | None, list[str]]:
    """Return the validated grammar (or None for legacy tokens) and validation errors."""
    if not isinstance(tokens, dict):
        return None, ["tokens.json must be an object"]
    errors: list[str] = []
    grammar: dict[str, Any] = {}
    if "grid" in tokens and (grid := _grid(tokens["grid"], errors)):
        grammar["grid"] = grid
    if "typeScale" in tokens and (scale := _type_scale(tokens["typeScale"], errors)):
        grammar["typeScale"] = scale
    if "density" in tokens:
        if tokens["density"] in DENSITIES:
            grammar["density"] = tokens["density"]
        else:
            errors.append(f"density must be one of {', '.join(DENSITIES)}")
    if "decoration" in tokens:
        decoration = tokens["decoration"] if isinstance(tokens["decoration"], dict) else {}
        motifs, intensity = decoration.get("motifs", []), decoration.get("intensity", "subtle")
        if not isinstance(motifs, list) or any(motif not in MOTIFS for motif in motifs):
            errors.append(f"decoration.motifs must use {', '.join(MOTIFS)}")
        elif intensity not in ("none", "subtle", "bold"):
            errors.append("decoration.intensity must be none, subtle or bold")
        else:
            grammar["decoration"] = {"motifs": list(dict.fromkeys(motifs)), "intensity": intensity}
    if "titleStyle" in tokens and (title := _title_style(tokens["titleStyle"], errors)):
        grammar["titleStyle"] = title
    if "chartStyle" in tokens and (chart := _chart_style(tokens["chartStyle"], errors)):
        grammar["chartStyle"] = chart
    if "iconStyle" in tokens:
        icon = tokens["iconStyle"] if isinstance(tokens["iconStyle"], dict) else {}
        stroke = _number(icon.get("stroke", 1.75))
        if not _within(stroke, (1, 2.5)):
            errors.append("iconStyle.stroke must be between 1 and 2.5")
        elif icon.get("container", "none") not in ("none", "circle", "square"):
            errors.append("iconStyle.container must be none, circle or square")
        else:
            grammar["iconStyle"] = {"use": icon.get("use") is not False, "stroke": stroke,
                                    "container": icon.get("container", "none")}
    if "forbidden" in tokens:
        forbidden = tokens["forbidden"]
        if not isinstance(forbidden, list) or any(item not in FORBIDDEN_PATTERNS for item in forbidden):
            errors.append(f"forbidden must list {', '.join(FORBIDDEN_PATTERNS)}")
        else:
            grammar["forbidden"] = list(dict.fromkeys(forbidden))
    if "decoration" in grammar and "forbidden" in grammar:
        grammar["decoration"]["motifs"] = [
            motif for motif in grammar["decoration"]["motifs"] if motif not in grammar["forbidden"]
        ]
    return ({"version": GRAMMAR_VERSION, **grammar} if grammar else None), errors
