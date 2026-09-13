import json
from pathlib import Path

from app.presentation_intelligence.brand_kit import compile_brand_kit

PALETTES = {
    "academic": {"name": "靛青证据", "bg": "#F6F7FB", "ink": "#182033", "primary": "#625BF6", "accent": "#78E3C5", "deep": "#20284D", "line": "#E3E7F0"},
    "conference": {"name": "学术会议", "bg": "#F5F8FB", "ink": "#17233A", "primary": "#3454D1", "accent": "#65D6C1", "deep": "#1A2D52", "line": "#DCE4EE"},
    "business": {"name": "深海决策", "bg": "#F3F8FB", "ink": "#102631", "primary": "#276C89", "accent": "#66D9EF", "deep": "#123C4A", "line": "#DCE9EE"},
    "strategy": {"name": "战略蓝图", "bg": "#F5F7F9", "ink": "#152536", "primary": "#176B87", "accent": "#E5B85C", "deep": "#173B50", "line": "#DCE3E8"},
    "executive": {"name": "高管决策", "bg": "#F6F7F8", "ink": "#17202A", "primary": "#215A72", "accent": "#D7A84B", "deep": "#172D38", "line": "#DDE2E5"},
    "review": {"name": "经营复盘", "bg": "#F6F8FA", "ink": "#17304A", "primary": "#157A6E", "accent": "#F2B84B", "deep": "#174C55", "line": "#D9E4E7"},
    "product": {"name": "紫曜发布", "bg": "#F7F6FC", "ink": "#211A36", "primary": "#7047EB", "accent": "#8CE6D0", "deep": "#2D2252", "line": "#E7E1F2"},
    "pitch": {"name": "融资路演", "bg": "#F7F6FC", "ink": "#201A32", "primary": "#6C4FE0", "accent": "#55D6BE", "deep": "#292247", "line": "#E4E0EF"},
    "marketing": {"name": "营销提案", "bg": "#FFF7F5", "ink": "#342027", "primary": "#D94F70", "accent": "#FFB36B", "deep": "#5A2940", "line": "#F0DDE2"},
    "sales": {"name": "销售方案", "bg": "#F4F8FA", "ink": "#15303A", "primary": "#137C8B", "accent": "#F2B84B", "deep": "#174953", "line": "#D8E5E8"},
    "teaching": {"name": "暖橙课堂", "bg": "#FBF5F1", "ink": "#2B1912", "primary": "#A54B27", "accent": "#FFB36B", "deep": "#5D281C", "line": "#EDDFD7"},
    "training": {"name": "培训工作坊", "bg": "#FBF7F0", "ink": "#2D241B", "primary": "#9B5A2E", "accent": "#F0B45E", "deep": "#51382B", "line": "#EBE0D3"},
    "public": {"name": "公共事务", "bg": "#F5F8FA", "ink": "#172B3A", "primary": "#1D6685", "accent": "#C99B4B", "deep": "#173B50", "line": "#DCE5EA"},
    "keynote": {"name": "主题演讲", "bg": "#F8F5F2", "ink": "#2C2224", "primary": "#A43D54", "accent": "#E4B862", "deep": "#382A35", "line": "#E7DDD8"},
    "portfolio": {"name": "案例作品", "bg": "#F6F4FC", "ink": "#241D34", "primary": "#7356D8", "accent": "#82DCC2", "deep": "#30274A", "line": "#E3DEEE"},
}

PRESET_PROFILES = {
    "academic": "editorial-story",
    "conference": "swiss-grid",
    "business": "data-consulting",
    "strategy": "data-consulting",
    "executive": "swiss-grid",
    "review": "data-consulting",
    "product": "nebula-tech",
    "pitch": "nebula-tech",
    "marketing": "editorial-story",
    "sales": "data-consulting",
    "teaching": "oriental-minimal",
    "training": "oriental-minimal",
    "public": "editorial-story",
    "keynote": "editorial-story",
    "portfolio": "editorial-story",
}

TONE_PROFILES = {
    "executive": "swiss-grid",
    "editorial": "editorial-story",
    "energetic": "nebula-tech",
}


def _skill_tokens(skills: list) -> dict:
    """Merge data-only visual tokens exposed by explicitly selected skills."""
    merged: dict = {}
    for skill in skills:
        root = Path(skill.path)
        for name in ("tokens.json", "design-system.json", "theme.json"):
            candidates = list(root.rglob(name))[:1]
            if not candidates:
                continue
            try:
                value = json.loads(candidates[0].read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(value, dict):
                merged.update(value)
    return merged


def build_design_system(preset: str, skills: list, brief: dict | None = None) -> dict:
    brief = brief or {}
    palette = dict(PALETTES.get(preset, PALETTES["academic"]))
    skill_tokens = _skill_tokens(skills)
    supplied_palette = skill_tokens.get("palette") or skill_tokens.get("colors")
    if isinstance(supplied_palette, dict):
        for key in ("bg", "ink", "primary", "accent", "deep", "line"):
            value = supplied_palette.get(key)
            if isinstance(value, str) and value.startswith("#") and len(value) in {4, 7}:
                palette[key] = value.upper()
    typography = {
        "fontFamily": skill_tokens.get("fontFamily", "Microsoft YaHei"),
        "title": {"size": 52, "weight": 800, "lineHeight": 1.12},
        "body": {"size": 20, "weight": 500, "lineHeight": 1.45},
        "caption": {"size": 11, "weight": 500, "lineHeight": 1.4},
    }
    radius = {"card": 20, "panel": 26}
    if isinstance(skill_tokens.get("radius"), dict):
        radius.update({key: value for key, value in skill_tokens["radius"].items() if key in radius and isinstance(value, (int, float))})
    requested_profile = skill_tokens.get("layoutProfile")
    layout_profile = requested_profile or TONE_PROFILES.get(
        str(brief.get("tone", "auto")), PRESET_PROFILES.get(preset, "swiss-grid")
    )
    design_system = {
        "version": "design-system-v4",
        "artDirection": palette.pop("name", "映章视觉系统"),
        "palette": palette,
        "layoutProfile": layout_profile,
        "typographyMood": skill_tokens.get("typographyMood", "modern"),
        "densityBias": skill_tokens.get("densityBias", "balanced"),
        "typography": typography,
        "grid": {"canvas": [1280, 720], "columns": 12, "margin": 68, "gutter": 20},
        "spacing": {"xs": 8, "sm": 14, "md": 20, "lg": 32, "xl": 52},
        "radius": radius,
        "shadow": {"card": "0 16px 40px rgba(32,40,77,.10)"},
        "chart": {"series": [palette["primary"], palette["accent"], palette["deep"]], "showGrid": False},
        "layoutGrammar": {
            "maxObjects": 7, "maxBullets": 4, "oneMessagePerSlide": True,
            "rhythm": "statement → structure → evidence → conclusion",
        },
        "referenceGrammar": skill_tokens.get("referenceGrammar", {}),
        "brand": {
            "name": str(brief.get("brandName", "")).strip(),
            "tone": brief.get("tone", "auto"),
            "showProductMark": False,
        },
        "communication": {
            "audience": str(brief.get("audience", "")).strip(),
            "objective": str(brief.get("objective", "")).strip(),
            "durationMinutes": brief.get("durationMinutes"),
            "coverStrapline": str(brief.get("objective", "")).strip(),
        },
        "skills": [skill.id for skill in skills],
        "communityAdaptation": [
            skill.manifest.get("communitySource", {}) for skill in skills
            if skill.manifest.get("communitySource")
        ],
    }
    design_system["brandKit"] = compile_brand_kit(design_system)
    return design_system
