from __future__ import annotations

from collections import Counter
from itertools import pairwise

VARIANT_FAMILIES = {
    "evidence-brief": "typography",
    "hero": "cover",
    "editorial-cover": "cover-editorial",
    "minimal-cover": "typography",
    "numbered-list": "list",
    "section-map": "map",
    "agenda-cards": "cards",
    "chapter-divider": "section",
    "section-statement": "typography",
    "minimal-section": "minimal",
    "big-statement": "typography",
    "context-cards": "cards",
    "timeline": "timeline",
    "problem-cards": "cards",
    "contrast": "comparison",
    "before-after": "comparison",
    "workflow": "flow",
    "three-stage": "stages",
    "process": "flow",
    "layered-architecture": "layers",
    "pipeline": "flow",
    "hub-spoke": "map",
    "evidence-chain": "flow",
    "source-map": "map",
    "claim-map": "layers",
    "chart-focus": "chart",
    "metric-wall": "metrics",
    "table-highlight": "table",
    "comparison-bars": "chart",
    "two-column": "comparison",
    "scorecard": "metrics",
    "finding-cards": "cards",
    "ablation": "chart",
    "takeaways": "list",
    "summary-grid": "cards",
    "next-steps": "timeline",
    "minimal-qa": "minimal",
    "closing-statement": "typography",
    "contact": "contact",
    "split": "split",
    "statement": "typography",
    "cards": "cards",
    "figure-wide": "image-wide",
    "figure-analysis": "image-analysis",
    "figure-focus": "image-focus",
    "image-story": "image-split",
    "media-focus": "media",
}

PRIMARY_FAMILIES = {
    "chart": "chart",
    "table": "table",
    "data": "chart",
    "diagram": "flow",
    "source-image": "image-analysis",
    "generated-image": "image-split",
    "typography": "typography",
    "cards": "cards",
    "media": "media",
}


def variant_family(variant: str | None, primary_visual: str | None = None) -> str:
    value = str(variant or "").strip()
    if value:
        return VARIANT_FAMILIES.get(value, value)
    return PRIMARY_FAMILIES.get(str(primary_visual or "").strip(), "unspecified")


def _longest_run(values: list[str]) -> int:
    longest = current = 0
    previous = None
    for value in values:
        current = current + 1 if value == previous else 1
        longest = max(longest, current)
        previous = value
    return longest


def _semantic_match(slide: dict, family: str) -> bool:
    role = str(slide.get("role", "content"))
    primary = str((slide.get("visualIntent") or {}).get("primaryVisual", ""))
    item_count = len((slide.get("content") or {}).get("bullets", []))
    if slide.get("visualIntent", {}).get("contentRelation") == "explanation" and family == "typography":
        return True
    if item_count <= 1 and family in {"split", "typography"}:
        return True
    if any(
        item.get("type") in {"licensed-video", "licensed-audio"}
        for item in slide.get("assetBindings", [])
    ):
        return family == "media"
    if any(
        item.get("type") in {"source-image", "licensed-image"}
        for item in slide.get("assetBindings", [])
    ):
        return family.startswith("image-")
    if primary == "generated-image":
        return family.startswith("image-") or family == "typography"
    expected = {
        "data": {"chart", "metrics", "table"},
        "comparison": {"chart", "comparison", "metrics", "table"},
        "method": {"flow", "stages", "timeline", "layers", "map"},
        "architecture": {"flow", "layers", "map"},
        "evidence": {"flow", "layers", "map", "image-analysis", "image-focus", "image-wide"},
        "background": {"typography", "cards", "timeline", "image-split", "image-wide"},
        "problem": {"cards", "comparison", "typography"},
        "insight": {
            "cards",
            "chart",
            "metrics",
            "typography",
            "image-analysis",
            "image-split",
            "media",
        },
        "conclusion": {"list", "cards", "timeline", "typography"},
        "content": {"split", "cards", "typography", "flow", "image-split"},
    }
    return family in expected.get(role, {family})


def assess_visual_maturity(slides: list[dict], visual_slides: list[dict] | None = None) -> dict:
    """Measure whether the deck uses genuinely varied, role-appropriate compositions.

    This deliberately avoids treating a technically valid render as a professional design.
    It looks at the selected composition families, narrative rhythm and evidence-bearing visuals.
    """
    rendered_by_position = {
        int(item.get("position", 0)): item
        for item in (visual_slides or [])
        if item.get("position") is not None
    }
    body = [
        slide
        for slide in slides
        if slide.get("role") not in {"cover", "agenda", "section", "questions"}
    ]
    if not body:
        return {
            "version": "visual-maturity-v1",
            "score": 100,
            "silhouetteDiversity": 100,
            "narrativeRhythm": 100,
            "semanticAdaptation": 100,
            "evidenceVisualCoverage": 100,
            "candidateDepth": None,
            "families": [],
            "issues": [],
        }

    families = []
    candidate_depths = []
    meaningful = 0
    semantic_matches = 0
    for slide in body:
        rendered = rendered_by_position.get(int(slide.get("position", 0)), {})
        visual = slide.get("visualIntent") or {}
        family = str(
            rendered.get("family")
            or variant_family(
                rendered.get("variant") or visual.get("selectedVariant"),
                visual.get("primaryVisual"),
            )
        )
        families.append(family)
        semantic_matches += int(_semantic_match(slide, family))
        if (
            family in {"chart", "metrics", "table", "flow", "stages", "timeline", "layers", "map"}
            or family.startswith("image-")
            or family == "media"
        ):
            meaningful += 1
        candidate_family_count = rendered.get("candidateFamilyCount")
        if isinstance(candidate_family_count, (int, float)):
            candidate_depths.append(float(candidate_family_count))

    counts = Counter(families)
    unique_target = min(6, max(2, len(body)))
    silhouette_diversity = round(min(100, len(counts) / unique_target * 100))
    adjacent_repeats = sum(left == right for left, right in pairwise(families))
    adjacent_repeat_rate = adjacent_repeats / max(1, len(families) - 1)
    longest_run = _longest_run(families)
    narrative_rhythm = round(max(0, 100 - adjacent_repeat_rate * 62 - max(0, longest_run - 2) * 12))
    semantic_adaptation = round(semantic_matches / len(body) * 100)
    evidence_visual_coverage = round(meaningful / len(body) * 100)
    candidate_depth = (
        round(sum(candidate_depths) / len(candidate_depths), 2) if candidate_depths else None
    )
    score = round(
        silhouette_diversity * 0.25
        + narrative_rhythm * 0.25
        + semantic_adaptation * 0.30
        + evidence_visual_coverage * 0.20
    )

    dominant_family, dominant_count = counts.most_common(1)[0]
    dominant_share = dominant_count / len(families)
    issues = []
    if len(body) >= 6 and dominant_share > 0.45:
        issues.append(
            {
                "code": "repetitive-layout-silhouette",
                "severity": "warning",
                "family": dominant_family,
                "share": round(dominant_share, 3),
            }
        )
    if len(body) >= 5 and adjacent_repeat_rate > 0.34:
        issues.append(
            {
                "code": "flat-deck-rhythm",
                "severity": "warning",
                "repeatRate": round(adjacent_repeat_rate, 3),
                "longestRun": longest_run,
            }
        )
    if len(body) >= 6 and evidence_visual_coverage < 45:
        issues.append(
            {
                "code": "low-evidence-visual-coverage",
                "severity": "warning",
                "coverage": evidence_visual_coverage,
            }
        )
    if candidate_depth is not None and len(body) >= 4 and candidate_depth < 2:
        issues.append(
            {
                "code": "shallow-candidate-diversity",
                "severity": "warning",
                "candidateDepth": candidate_depth,
            }
        )

    return {
        "version": "visual-maturity-v1",
        "score": score,
        "silhouetteDiversity": silhouette_diversity,
        "narrativeRhythm": narrative_rhythm,
        "semanticAdaptation": semantic_adaptation,
        "evidenceVisualCoverage": evidence_visual_coverage,
        "candidateDepth": candidate_depth,
        "families": families,
        "uniqueFamilies": len(counts),
        "dominantFamily": dominant_family,
        "dominantShare": round(dominant_share, 3),
        "adjacentRepeatRate": round(adjacent_repeat_rate, 3),
        "longestRun": longest_run,
        "issues": issues,
    }
