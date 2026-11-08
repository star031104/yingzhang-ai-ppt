"""Perturbation tests for the quality gates themselves.

A gate is only trustworthy if it fires on the defect it claims to catch. Each
perturbation injects one known defect into an otherwise clean deck (or render
score) and checks that the targeted gate reports it on the targeted page while
it stayed silent on the clean input. The suite is deterministic and runs in CI
on the synthetic benchmark fixtures.
"""

from __future__ import annotations

import asyncio
import copy
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.evaluation.faithfulness import evaluate_faithfulness
from app.presentation_engine.page_repair import diagnose
from app.validation.quality import validate_deck
from app.validation.render_safety import safe_render_candidate

VERSION = "gate-perturbation-v1"
NAV = {"cover", "agenda", "section", "questions"}
NUMBER_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)(\s*(?:%|个百分点|倍|万|亿|元|人|家|天|小时|分钟|秒))")

SAFE_SCORE = {
    "geometry": 96, "readability": 92, "hierarchy": 92, "whitespace": 88, "alignment": 90,
    "semanticFit": 90, "contentFit": 90, "visualEvidence": 86, "planningFit": 90,
    "styleConsistency": 96, "deckRhythm": 90, "overall": 91, "bulletCount": 3, "issues": [],
}


@dataclass
class Perturbation:
    name: str
    gate: str
    expected: str
    apply: Callable[[list[dict]], tuple[list[dict], int] | None]


def _content_slides(slides: list[dict]) -> list[dict]:
    return [slide for slide in slides if slide.get("role") not in NAV and (slide.get("content") or {}).get("bullets")]


def _numeric_bullet(slides: list[dict]) -> tuple[dict, int, re.Match] | None:
    for slide in _content_slides(slides):
        for index, bullet in enumerate(slide["content"]["bullets"]):
            match = NUMBER_RE.search(str(bullet))
            if match:
                return slide, index, match
    return None


def _alter_number(slides: list[dict]):
    deck = copy.deepcopy(slides)
    found = _numeric_bullet(deck)
    if not found:
        return None
    slide, index, match = found
    original = float(match.group(1))
    altered = f"{original * 3 + 17:g}"
    bullet = str(slide["content"]["bullets"][index])
    slide["content"]["bullets"][index] = bullet[: match.start(1)] + altered + bullet[match.end(1):]
    return deck, int(slide["position"])


def _fabricated_claim(slides: list[dict]):
    deck = copy.deepcopy(slides)
    targets = _content_slides(deck)
    if not targets:
        return None
    slide = targets[len(targets) // 2]
    slide["content"]["bullets"] = [*slide["content"]["bullets"][:3], "海外渠道贡献营收提升 437%，客户满意度达到 99.7%"]
    return deck, int(slide["position"])


def _duplicate_title(slides: list[dict]):
    deck = copy.deepcopy(slides)
    targets = _content_slides(deck)
    if len(targets) < 2:
        return None
    targets[1]["content"]["title"] = targets[0]["content"]["title"]
    return deck, int(targets[1]["position"])


def _broken_source(slides: list[dict]):
    deck = copy.deepcopy(slides)
    targets = [slide for slide in _content_slides(deck) if slide.get("sourceRefs")]
    if not targets:
        return None
    slide = targets[0]
    slide["sourceRefs"] = [{**ref, "section": "S-NOT-IN-SOURCE"} for ref in slide["sourceRefs"]]
    return deck, int(slide["position"])


def _empty_content(slides: list[dict]):
    deck = copy.deepcopy(slides)
    targets = _content_slides(deck)
    if not targets:
        return None
    slide = targets[-1]
    slide["content"]["bullets"] = []
    slide["message"] = ""
    return deck, int(slide["position"])


DECK_PERTURBATIONS = [
    Perturbation("altered-number", "validate_deck", "unsupported-metric", _alter_number),
    Perturbation("altered-number", "faithfulness", "unsupported-or-partial", _alter_number),
    Perturbation("fabricated-claim", "validate_deck", "unsupported-metric", _fabricated_claim),
    Perturbation("fabricated-claim", "faithfulness", "unsupported-or-partial", _fabricated_claim),
    Perturbation("duplicate-title", "validate_deck", "duplicate-slide-title", _duplicate_title),
    Perturbation("broken-source-ref", "validate_deck", "broken-source-ref", _broken_source),
    Perturbation("empty-content", "validate_deck", "empty-content-slide", _empty_content),
]

RENDER_PERTURBATIONS: dict[str, tuple[dict, str]] = {
    "text-overflow": ({"textOverflow": 1, "geometry": 70}, "text-overflow"),
    "canvas-overflow": ({"overflow": 2, "geometry": 30}, "text-overflow"),
    "low-contrast": ({"lowContrast": 1, "issues": [{"code": "low-text-contrast", "severity": "error"}]}, "low-contrast"),
    "missing-asset": ({"missingAssets": 1, "geometry": 65}, "missing-asset"),
    "missing-content": ({"missingContent": 1, "issues": [{"code": "missing-content", "severity": "error"}]}, "missing-content"),
    "too-dense": ({"readability": 60, "bulletCount": 8}, "dense"),
}


def _codes_at(report: dict, position: int) -> set[str]:
    return {str(issue.get("code")) for issue in report.get("issues", []) if int(issue.get("slide") or 0) == position}


def _flagged_claims(result: dict, position: int) -> int:
    for slide in result.get("slides", []):
        if int(slide.get("position") or 0) == position:
            return sum(1 for claim in slide["claims"] if claim["verdict"] != "supported")
    return 0


def _faithfulness_score(result: dict, position: int) -> float | None:
    for slide in result.get("slides", []):
        if int(slide.get("position") or 0) == position:
            return slide.get("score")
    return None


def run_deck_perturbations(slides: list[dict], sources: list[dict]) -> list[dict[str, Any]]:
    baseline_report = validate_deck(copy.deepcopy(slides), sources)
    baseline_faith = asyncio.run(evaluate_faithfulness(slides, sources)) if _needs_loop() else None
    rows = []
    for item in DECK_PERTURBATIONS:
        applied = item.apply(slides)
        if not applied:
            rows.append({"name": item.name, "gate": item.gate, "status": "not-applicable"})
            continue
        deck, position = applied
        if item.gate == "validate_deck":
            before = item.expected in _codes_at(baseline_report, position)
            after_report = validate_deck(deck, sources)
            detected = item.expected in _codes_at(after_report, position)
            rows.append({
                "name": item.name, "gate": item.gate, "expected": item.expected, "position": position,
                "baselineClean": not before, "detected": detected,
                "status": "detected" if detected and not before else "missed" if not detected else "baseline-noisy",
            })
        else:
            if baseline_faith is None:
                baseline_faith = asyncio.run(evaluate_faithfulness(slides, sources))
            after = asyncio.run(evaluate_faithfulness(deck, sources))
            before_flags, after_flags = _flagged_claims(baseline_faith, position), _flagged_claims(after, position)
            before_score, after_score = _faithfulness_score(baseline_faith, position), _faithfulness_score(after, position)
            detected = after_flags > before_flags
            rows.append({
                "name": item.name, "gate": item.gate, "expected": item.expected, "position": position,
                "baselineClean": True, "detected": detected,
                "scoreDrop": round((before_score or 0) - (after_score or 0), 3) if after_score is not None else None,
                "status": "detected" if detected else "missed",
            })
    return rows


def _needs_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return True
    return False


def run_render_perturbations() -> list[dict[str, Any]]:
    rows = []
    clean = {"candidates": [{"variant": "cards", "score": dict(SAFE_SCORE), "safe": safe_render_candidate(SAFE_SCORE)}]}
    clean["safeVariants"] = [item["variant"] for item in clean["candidates"] if item["safe"]]
    baseline_codes = diagnose(clean)
    for name, (patch, expected) in RENDER_PERTURBATIONS.items():
        score = {**SAFE_SCORE, **patch}
        snapshot = {"candidates": [{"variant": "cards", "score": score, "safe": safe_render_candidate(score)}]}
        snapshot["safeVariants"] = [item["variant"] for item in snapshot["candidates"] if item["safe"]]
        codes = diagnose(snapshot)
        detected = expected in codes and not snapshot["safeVariants"]
        rows.append({
            "name": name, "gate": "render-safety", "expected": expected,
            "baselineClean": not baseline_codes, "detected": detected, "codes": codes,
            "status": "detected" if detected and not baseline_codes else "missed",
        })
    return rows


def run_perturbation_suite(slides: list[dict], sources: list[dict]) -> dict[str, Any]:
    """Synchronous entry point (scripts and tests); do not call from a running event loop."""
    rows = [*run_deck_perturbations(slides, sources), *run_render_perturbations()]
    applicable = [row for row in rows if row["status"] != "not-applicable"]
    detected = [row for row in applicable if row["status"] == "detected"]
    return {
        "version": VERSION,
        "perturbations": rows,
        "applicable": len(applicable),
        "detected": len(detected),
        "detectionRate": round(len(detected) / len(applicable), 3) if applicable else None,
        "missed": [f"{row['name']}→{row['gate']}" for row in applicable if row["status"] != "detected"],
    }
