"""Reusable library of reference-slide layouts, matched to planned pages.

Analyzed reference decks contribute text-free layout entries (function,
silhouette, regions, text/metric/image counts, master layout). At planning time
each page's content signature (role, bullet count, metrics, figures, density) is
matched to the closest reference slide; the winner is exposed as the slide's
``referenceLayout`` so the layout planner and native template fill follow it.
"""

from __future__ import annotations

import re
from collections import Counter

LIBRARY_VERSION = "reference-layout-library-v1"
MATCH_THRESHOLD = 30.0
ROLE_FUNCTION = {
    "cover": "cover", "agenda": "agenda", "section": "section", "questions": "conclusion",
    "data": "data", "comparison": "comparison", "method": "process", "architecture": "process",
    "evidence": "content", "conclusion": "conclusion", "background": "content",
    "problem": "content", "insight": "content", "content": "content",
}
FUNCTION_COMPATIBLE = {
    "cover": {"cover"},
    "agenda": {"agenda"},
    "section": {"section", "questions"},
    "data": {"data", "comparison", "insight", "evidence"},
    "comparison": {"comparison", "problem", "data", "insight"},
    "process": {"method", "architecture", "evidence", "content"},
    "image-story": {"background", "evidence", "content", "insight", "problem"},
    "conclusion": {"conclusion", "questions"},
    "content": {"background", "problem", "insight", "content", "method", "evidence", "architecture", "comparison"},
}
DENSITY_ORDER = ["low", "medium", "high"]
METRIC_RE = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s*(?:%|倍|万|亿|ms|秒|分钟|小时|MB|GB)|"
    r"(?:Accuracy|Precision|Recall|F1|准确率|召回率)\D{0,10}\d",
    re.IGNORECASE,
)


def _variant_hint(function: str, signature: dict, silhouette: dict) -> str:
    if function == "data":
        if signature.get("tableCount"):
            return "table-highlight"
        if signature.get("chartCount"):
            return "chart-focus"
        return "metric-wall"
    if function == "process":
        return "workflow"
    if function == "image-story":
        return "image-story"
    if function == "comparison":
        return "two-column"
    if function == "conclusion":
        return "takeaways"
    if function == "cover":
        return "minimal-cover" if signature.get("textCount", 0) <= 2 else "hero"
    if function == "section":
        return "chapter-divider"
    if function == "agenda":
        return "numbered-list"
    if signature.get("textCount", 0) <= 2 and signature.get("bulletCount", 0) <= 2:
        return "statement"
    if silhouette.get("columnBalance") == "balanced" and signature.get("bulletCount", 0) >= 3:
        return "cards"
    return "split"


def build_layout_library(slides: list[dict], constraint_grammar: dict, slide_size: dict) -> dict:
    """Turn analyzer slide records into text-free library entries."""
    entries = []
    for slide in slides:
        signature = slide.get("signature")
        if not signature:
            continue
        silhouette = slide.get("silhouette", {})
        entries.append({
            "slidePosition": slide.get("position"),
            "function": slide.get("function", "content"),
            "layout": slide.get("layout", ""),
            "layoutIndex": slide.get("layoutIndex"),
            "silhouette": {
                key: silhouette.get(key)
                for key in ("titleBand", "columnBalance", "objectCount", "mediaAreaRatio", "safeMargins")
            },
            "variantHint": _variant_hint(slide.get("function", "content"), signature, silhouette),
            **signature,
        })
    return {
        "version": LIBRARY_VERSION,
        "slideSize": slide_size,
        "constraintGrammar": {
            key: constraint_grammar.get(key)
            for key in ("safeMargins", "alignmentGrid", "objectCountRange", "mediaAreaRange")
        },
        "entries": entries,
    }


def reference_layout_library(data: bytes) -> dict:
    from app.templates.analyzer import analyze_reference_pptx

    return analyze_reference_pptx(data)["layoutLibrary"]


def content_signature(slide: dict) -> dict:
    content = slide.get("content") or {}
    bullets = [str(item) for item in content.get("bullets", [])]
    characters = len(str(content.get("title", ""))) + len(str(slide.get("message", ""))) + sum(map(len, bullets))
    expected = set((slide.get("visualIntent") or {}).get("expectedFigureKinds", []))
    role = str(slide.get("role", "content"))
    return {
        "role": role,
        "bulletCount": len(bullets),
        "metricCount": sum(bool(METRIC_RE.search(item)) for item in bullets),
        "hasImage": any(
            item.get("type") in {"source-image", "licensed-image", "generated-image"}
            for item in slide.get("assetBindings", [])
        ),
        "wantsChart": role in {"data", "comparison"} and bool(expected & {"chart", "table"}),
        "density": "low" if characters < 120 else "medium" if characters < 420 else "high",
    }


def _entry_score(entry: dict, signature: dict) -> tuple[float, list[str]] | None:
    role = signature["role"]
    function = str(entry.get("function", "content"))
    if role not in FUNCTION_COMPATIBLE.get(function, set()):
        return None
    reasons = []
    if ROLE_FUNCTION.get(role) == function:
        score, reasons = 50.0, [f"页面功能一致：{function}"]
    else:
        score, reasons = 25.0, [f"页面功能兼容：{function}"]
    if role in {"cover", "agenda", "section", "questions"}:
        return score + 10, reasons
    gap = abs(int(entry.get("bulletCount", 0)) - signature["bulletCount"])
    score -= min(30, gap * 6)
    if gap <= 1:
        reasons.append("要点数量接近")
    has_data_visual = bool(entry.get("chartCount") or entry.get("tableCount"))
    if signature["metricCount"] or signature["wantsChart"]:
        if has_data_visual:
            score += 15
            reasons.append("参考页含图表或表格")
        elif entry.get("metricCount"):
            score += 5
    elif has_data_visual:
        score -= 20
    media = float((entry.get("silhouette") or {}).get("mediaAreaRatio") or 0)
    if signature["hasImage"]:
        score += 15 if entry.get("pictureCount") else -10
        if entry.get("pictureCount"):
            reasons.append("参考页含图片区域")
    elif media > 0.3 or function == "image-story":
        score -= 15
    density_gap = abs(DENSITY_ORDER.index(entry.get("density", "medium")) - DENSITY_ORDER.index(signature["density"]))
    score += 8 if density_gap == 0 else -10 if density_gap == 2 else 0
    return score, reasons


def match_reference_layout(slide: dict, entries: list[dict], used: Counter | None = None,
                           previous: str | None = None) -> dict | None:
    """Best matching library entry for one planned page, or ``None`` below the threshold."""
    signature = content_signature(slide)
    used = used or Counter()
    best = None
    for entry in entries:
        scored = _entry_score(entry, signature)
        if not scored:
            continue
        score, reasons = scored
        key = f"{entry.get('sourceId', '')}:{entry.get('slidePosition')}"
        score -= used[key] * 4 + (10 if key == previous else 0)
        if best is None or score > best[0]:
            best = (score, key, entry, reasons)
    if not best or best[0] < MATCH_THRESHOLD:
        return None
    score, key, entry, reasons = best
    return {
        "version": "reference-layout-v1",
        "key": key,
        "source": {"kind": entry.get("sourceKind", ""), "id": entry.get("sourceId", ""), "name": entry.get("sourceName", "")},
        "slidePosition": entry.get("slidePosition"),
        "function": entry.get("function"),
        "layout": entry.get("layout"),
        "layoutIndex": entry.get("layoutIndex"),
        "variantHint": entry.get("variantHint"),
        "silhouette": entry.get("silhouette", {}),
        "regions": entry.get("regions", []),
        "score": round(score, 1),
        "reasons": reasons,
        "contentSignature": signature,
    }


def attach_reference_layouts(slides: list[dict], library: dict | None) -> dict:
    """Set ``slide['referenceLayout']`` for every page with a good reference match."""
    entries = (library or {}).get("entries", [])
    if not entries:
        return {"version": LIBRARY_VERSION, "entries": 0, "matched": 0, "sources": []}
    used: Counter = Counter()
    previous = None
    matched = 0
    for slide in slides:
        match = match_reference_layout(slide, entries, used, previous)
        if match:
            match["constraintGrammar"] = (library or {}).get("constraintGrammar", {})
            slide["referenceLayout"] = match
            used[match["key"]] += 1
            previous = match["key"]
            matched += 1
        else:
            slide.pop("referenceLayout", None)
            previous = None
    return {
        "version": LIBRARY_VERSION,
        "entries": len(entries),
        "matched": matched,
        "sources": (library or {}).get("sources", []),
    }


def _tag(library: dict, kind: str, source_id: str, name: str) -> list[dict]:
    return [
        {**entry, "sourceKind": kind, "sourceId": source_id, "sourceName": name}
        for entry in (library or {}).get("entries", [])
    ]


def load_reference_layout_library(db, skills: list, snapshot: dict | None) -> dict:
    """Collect layout entries from the active personal reference and selected reference skills."""
    entries: list[dict] = []
    sources: list[dict] = []
    grammar: dict = {}
    reference = (snapshot or {}).get("reference") or {}
    if reference.get("id"):
        from app.db.models import PersonalReference

        row = db.get(PersonalReference, reference["id"])
        library = (row.analysis or {}).get("layoutLibrary") if row else None
        if row and not library:
            # References analysed before the library existed are re-read from the retained original.
            try:
                from app.personalization.private_files import reference_root

                library = reference_layout_library((reference_root(row) / "reference.pptx").read_bytes())
            except Exception:  # noqa: BLE001 - a missing or invalid original only disables matching
                library = None
        if row and library:
            entries += _tag(library, "personal-reference", row.id, row.name)
            sources.append({"kind": "personal-reference", "id": row.id, "name": row.name})
            grammar = grammar or library.get("constraintGrammar", {})
    for skill in skills or []:
        library = ((getattr(skill, "manifest", None) or {}).get("analysis") or {}).get("layoutLibrary")
        if library:
            entries += _tag(library, "skill", skill.id, (skill.manifest or {}).get("name", skill.id))
            sources.append({"kind": "skill", "id": skill.id})
            grammar = grammar or library.get("constraintGrammar", {})
    return {"version": LIBRARY_VERSION, "entries": entries, "sources": sources, "constraintGrammar": grammar}
