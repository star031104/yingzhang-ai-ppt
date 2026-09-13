from __future__ import annotations

import re
from collections import Counter

from app.validation.visual_maturity import variant_family

VARIANT_SILHOUETTES = {
    "evidence-brief": "editorial-evidence",
    "hero": "center-hero",
    "editorial-cover": "left-editorial",
    "minimal-cover": "center-minimal",
    "numbered-list": "two-column-list",
    "section-map": "horizontal-map",
    "agenda-cards": "grid",
    "chapter-divider": "full-bleed",
    "section-statement": "left-statement",
    "minimal-section": "center-minimal",
    "big-statement": "left-statement",
    "context-cards": "grid",
    "timeline": "horizontal-sequence",
    "problem-cards": "three-column",
    "contrast": "asymmetric-split",
    "before-after": "horizontal-sequence",
    "workflow": "horizontal-flow",
    "three-stage": "three-column",
    "process": "horizontal-flow",
    "layered-architecture": "layer-stack",
    "pipeline": "horizontal-flow",
    "hub-spoke": "radial-map",
    "evidence-chain": "horizontal-flow",
    "source-map": "radial-map",
    "claim-map": "layer-stack",
    "chart-focus": "chart-wide",
    "metric-wall": "metric-grid",
    "table-highlight": "table-wide",
    "comparison-bars": "chart-wide",
    "two-column": "asymmetric-split",
    "scorecard": "metric-grid",
    "finding-cards": "asymmetric-split",
    "ablation": "chart-wide",
    "takeaways": "three-column",
    "summary-grid": "editorial-grid",
    "next-steps": "horizontal-sequence",
    "minimal-qa": "center-minimal",
    "closing-statement": "left-statement",
    "contact": "asymmetric-split",
    "split": "asymmetric-split",
    "statement": "left-statement",
    "cards": "grid",
    "figure-wide": "image-wide",
    "figure-analysis": "image-analysis",
    "figure-focus": "image-focus",
    "image-story": "image-split",
    "media-focus": "media-wide",
}

ROLE_FAMILY_PREFERENCE = {
    "background": ["typography", "timeline", "image-split", "cards"],
    "problem": ["comparison", "typography", "cards"],
    "method": ["flow", "stages", "timeline", "layers"],
    "architecture": ["layers", "map", "flow"],
    "evidence": ["image-analysis", "map", "layers", "flow"],
    "data": ["chart", "table", "metrics"],
    "comparison": ["comparison", "chart", "table", "metrics"],
    "insight": ["chart", "typography", "cards", "image-analysis"],
    "conclusion": ["timeline", "list", "typography", "cards"],
}


def _clean_metric_text(value: str) -> str:
    return re.sub(
        r"[（(]\s*(?:S|SRC)\s*\d*\s*[）)]|\[\s*(?:S|SRC)\s*\d+\s*]",
        "",
        str(value),
        flags=re.IGNORECASE,
    )


def _metric_count(items: list[str]) -> int:
    pattern = re.compile(
        r"\d[\d,]*(?:\.\d+)?\s*(?:%|倍|万|亿|ms|秒|分钟|小时|MB|GB)|"
        r"(?:Accuracy|Precision|Recall|F1|MRR|nDCG|Hit@?\d*|准确率|召回率|完整率|通过率)\D{0,10}\d|"
        r"\b0\.\d{2,}\b",
        re.IGNORECASE,
    )
    return sum(bool(pattern.search(_clean_metric_text(item))) for item in items)


def _payload(slide: dict) -> dict:
    content = slide.get("content") or {}
    items = [str(item) for item in content.get("bullets", [])]
    title = str(content.get("title", ""))
    assets = slide.get("assetBindings", [])
    return {
        "itemCount": len(items),
        "characterCount": len(title) + len(str(slide.get("message", ""))) + sum(map(len, items)),
        "metricCount": _metric_count(items),
        "hasImage": any(
            item.get("type") in {"source-image", "licensed-image", "generated-image"}
            for item in assets
        ),
        "hasMedia": any(
            item.get("type") in {"licensed-video", "licensed-audio"} for item in assets
        ),
        "titleLength": len(title),
        "messageLength": len(str(slide.get("message", ""))),
    }


def _variant_score(
    variant: str, slide: dict, payload: dict, previous_silhouette: str | None, used: Counter
) -> float:
    role = str(slide.get("role", "content"))
    family = variant_family(variant)
    silhouette = VARIANT_SILHOUETTES.get(variant, family)
    preferred = ROLE_FAMILY_PREFERENCE.get(role, [])
    score = 60.0
    relation = slide.get("visualIntent", {}).get("contentRelation")
    if relation == "explanation" and family in {"flow", "timeline", "stages", "layers", "map"} and role not in {"cover", "agenda", "section", "questions"}:
        score -= 60
    if variant == "evidence-brief":
        score += 30 if relation == "explanation" else 0
    if family in preferred:
        score += 24 - preferred.index(family) * 5
    if payload["hasImage"]:
        score += 42 if family.startswith("image-") else -32
    elif family.startswith("image-"):
        score -= 70
    if payload["hasMedia"]:
        score += 42 if family in {"media", "image-wide", "image-split"} else -18
    if family in {"chart", "metrics", "table"}:
        score += min(30, payload["metricCount"] * 10) if payload["metricCount"] else -55
    if family == "cards":
        score -= 8 + max(0, used["cards"] - 1) * 7
    if payload["itemCount"] <= 2 and family in {"typography", "comparison", "image-split"}:
        score += 12
    if 3 <= payload["itemCount"] <= 5 and family in {"flow", "stages", "timeline", "layers", "map"}:
        score += 10
    if payload["itemCount"] < 2 and family in {
        "flow",
        "stages",
        "timeline",
        "layers",
        "map",
        "cards",
    }:
        score -= 46
    if previous_silhouette == silhouette:
        score -= 28
    score -= used[silhouette] * 5
    return score


def _regions(silhouette: str, focal_point: str) -> list[dict]:
    title = {"id": "title", "x": 0, "y": 0, "w": 12, "h": 2, "priority": 100}
    footer = {"id": "source", "x": 0, "y": 11.4, "w": 12, "h": 0.6, "priority": 20}
    if silhouette in {"asymmetric-split", "image-split", "image-analysis", "image-focus"}:
        left = 7 if focal_point == "left" else 5
        return [
            title,
            {"id": "primary", "x": 0, "y": 2.2, "w": left, "h": 8.7, "priority": 90},
            {
                "id": "support",
                "x": left + 0.4,
                "y": 2.2,
                "w": 11.6 - left,
                "h": 8.7,
                "priority": 70,
            },
            footer,
        ]
    if silhouette in {
        "horizontal-sequence",
        "horizontal-flow",
        "chart-wide",
        "table-wide",
        "image-wide",
    }:
        return [
            title,
            {"id": "primary", "x": 0, "y": 2.25, "w": 12, "h": 7.8, "priority": 90},
            {"id": "claim", "x": 0, "y": 10.25, "w": 12, "h": 0.9, "priority": 80},
            footer,
        ]
    return [title, {"id": "primary", "x": 0, "y": 2.2, "w": 12, "h": 8.9, "priority": 90}, footer]


def plan_deck_layouts(
    slides: list[dict],
    preset: str,
    brief: dict | None = None,
    reference_grammar: dict | None = None,
) -> dict:
    """Create a deterministic composition contract before rendering candidates."""
    brief = brief or {}
    reference_grammar = reference_grammar or {}
    used: Counter = Counter()
    previous_silhouette = None
    family_sequence = []
    silhouette_sequence = []
    warnings = []
    learned = reference_grammar.get("variantByRole", {})
    reference_constraints = reference_grammar.get("constraintGrammar", {})
    for index, slide in enumerate(slides):
        visual = dict(slide.get("visualIntent") or {})
        payload = _payload(slide)
        candidates = [
            *[str(item) for item in learned.get(str(slide.get("role")), [])],
            *[str(item) for item in visual.get("archetypeCandidates", [])],
        ]
        if visual.get("contentRelation") == "explanation" and slide.get("role") not in {"cover", "agenda", "section", "questions", "data", "comparison"} and not payload["hasImage"]:
            candidates.insert(0, "evidence-brief")
        if payload["itemCount"] <= 1:
            candidates.extend(["statement", "split"])
        elif payload["itemCount"] == 2:
            candidates.append("split")
        candidates = list(dict.fromkeys(item for item in candidates if item)) or [
            "split",
            "statement",
            "cards",
        ]
        ranked = sorted(
            candidates,
            key=lambda variant: (
                -_variant_score(variant, slide, payload, previous_silhouette, used),
                candidates.index(variant),
            ),
        )
        recommended = ranked[0]
        family = variant_family(recommended)
        silhouette = VARIANT_SILHOUETTES.get(recommended, family)
        focal_point = "right" if index % 2 == 0 else "left"
        if family.startswith("image-"):
            focal_point = "right" if index % 2 == 0 else "left"
        elif silhouette in {"horizontal-sequence", "horizontal-flow", "chart-wide", "table-wide"}:
            focal_point = "full"
        title_max = 22 if payload["titleLength"] > 28 else 30
        body_max = 3 if payload["characterCount"] > 300 else 4
        layout_plan = {
            "version": "composition-plan-v1",
            "communicationJob": str(slide.get("purpose") or slide.get("message") or ""),
            "compositionMode": family,
            "recommendedVariant": recommended,
            "candidateOrder": ranked[:5],
            "silhouette": silhouette,
            "focalPoint": focal_point,
            "regions": _regions(silhouette, focal_point),
            "payload": payload,
            "typography": {
                "titleMinPt": 35,
                "bodyMinPt": 16,
                "titleMaxCharacters": title_max,
                "bodyMaxItems": body_max,
                "singleLineTitlePreferred": payload["titleLength"] <= title_max,
            },
            "constraints": {
                "maxObjects": 7,
                "maxCards": 3,
                "minOccupiedRatio": 0.23,
                "maxOccupiedRatio": 0.72,
                "avoidUiChrome": True,
                "preserveEvidenceValues": True,
                "referenceSafeMargins": reference_constraints.get("safeMargins", {}),
                "referenceAlignmentGrid": reference_constraints.get("alignmentGrid", []),
                "referenceObjectCountRange": reference_constraints.get("objectCountRange", []),
            },
            "transitionIntent": "resolve"
            if slide.get("role") in {"conclusion", "questions"}
            else "advance",
        }
        visual["archetypeCandidates"] = ranked[:5]
        visual["plannedFamily"] = family
        slide["visualIntent"] = visual
        slide["layoutPlan"] = layout_plan
        family_sequence.append(family)
        silhouette_sequence.append(silhouette)
        if previous_silhouette == silhouette and slide.get("role") not in {"section", "questions"}:
            warnings.append(
                {
                    "position": slide.get("position"),
                    "code": "planned-silhouette-repeat",
                    "silhouette": silhouette,
                }
            )
        used[silhouette] += 1
        used[family] += 1
        previous_silhouette = silhouette
    return {
        "version": "layout-planning-v1",
        "preset": preset,
        "audience": str(brief.get("audience", "")),
        "objective": str(brief.get("objective", "")),
        "familySequence": family_sequence,
        "silhouetteSequence": silhouette_sequence,
        "uniqueSilhouettes": len(set(silhouette_sequence)),
        "warnings": warnings,
    }
