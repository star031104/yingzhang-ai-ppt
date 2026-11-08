"""Per-page render -> check -> patch loop.

Reflection is grounded in the rendered page, not in the model's reasoning: after a
page is built, the measured candidate scores are diagnosed; if no candidate is safe
the page spec is patched deterministically and rendered again, at most
``settings.page_repair_rounds`` times.

Patches never invent content. They only

* move surplus bullets or the tail of an over-long bullet into the speaker notes
  (a tail carrying a qualifier such as "不含" or "试点" is never split off, so a
  number is never shown without its boundary);
* steer candidate selection away from variants that measured as unsafe and
  towards text-tolerant layouts;
* drop asset bindings whose files are missing.

A page whose content was edited by a person (``contentLocked``) only receives
layout-steering patches.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from app.validation.render_safety import hard_render_failures, safe_render_candidate

PageInspector = Callable[[dict, dict], Awaitable[list[str]]]

TEXT_TOLERANT_VARIANTS = ("evidence-brief", "content-list")
NAVIGATION_ROLES = {"cover", "agenda", "section", "questions"}
QUALIFIER_RE = re.compile(
    r"不含|不包括|除外|除去|仅|只在|未|尚未|假设|预计|预测|估算|约|左右|样本|试点|口径|条件|前提|若|如果|但|然而|同比|环比|基期|以内|以上|以下"
)
CLAUSE_BREAK_RE = re.compile(r"[，；,;：:]")
VISION_TEXT_ISSUES = {"overflow", "small-text", "awkward-wrap"}
VISION_LAYOUT_ISSUES = {"weak-hierarchy", "imbalance", "low-contrast", "weak-semantic-fit", "repetition"}


def page_snapshot(page_root: Path) -> dict[str, Any]:
    """Read the candidates one page build produced."""
    current = {}
    current_path = page_root / "current.json"
    if current_path.is_file():
        current = json.loads(current_path.read_text(encoding="utf-8"))
    candidates = []
    for score_path in sorted(page_root.glob("*.score.json")):
        score = json.loads(score_path.read_text(encoding="utf-8"))
        variant = score_path.name.removesuffix(".score.json")
        candidates.append({"variant": variant, "score": score, "safe": safe_render_candidate(score)})
    selected = str(current.get("variant") or "")
    image = page_root / f"{selected}.png" if selected else None
    return {
        "selectedVariant": selected,
        "selectedScore": next((item["score"] for item in candidates if item["variant"] == selected), {}),
        "candidates": candidates,
        "safeVariants": [item["variant"] for item in candidates if item["safe"]],
        "imagePath": str(image) if image and image.is_file() else None,
    }


def diagnose(snapshot: dict[str, Any]) -> list[str]:
    """Return repair codes for a page with no safe candidate; an empty list means pass."""
    if snapshot["safeVariants"] or not snapshot["candidates"]:
        return []
    codes: list[str] = []
    for candidate in snapshot["candidates"]:
        score = candidate["score"]
        failures = set(hard_render_failures(score))
        if failures & {"overflow", "clipping", "textOverflow", "text-clipped"}:
            codes.append("text-overflow")
        if failures & {"missingContent", "missing-content"}:
            codes.append("missing-content")
        if failures & {"missingAssets", "missing-asset"}:
            codes.append("missing-asset")
        if score.get("lowContrast") or "low-text-contrast" in failures:
            codes.append("low-contrast")
        if float(score.get("readability", 100)) < 78 or int(score.get("bulletCount", 0)) > 4:
            codes.append("dense")
        if float(score.get("geometry", 100)) < 80:
            codes.append("geometry")
    return list(dict.fromkeys(codes)) or ["unsafe"]


def _bullet_budget(slide: dict, round_number: int) -> int:
    role = slide.get("role")
    if role in NAVIGATION_ROLES:
        return 6 if role == "agenda" else 2
    return 4 if round_number <= 1 else 3


def _char_limit(round_number: int) -> int:
    return 64 if round_number <= 1 else 46


def split_long_bullet(text: str, limit: int) -> tuple[str, str] | None:
    """Split at the last clause boundary before ``limit`` if the tail has no qualifier."""
    value = str(text).strip()
    if len(value) <= limit:
        return None
    breaks = [match.start() for match in CLAUSE_BREAK_RE.finditer(value) if 12 <= match.start() <= limit]
    if not breaks:
        return None
    cut = breaks[-1]
    head, tail = value[:cut].rstrip("，；,;：: "), value[cut + 1:].strip()
    if not tail or QUALIFIER_RE.search(tail):
        return None
    return head, tail


def _move_to_notes(slide: dict, items: list[str]) -> None:
    if not items:
        return
    intent = slide.setdefault("speakerIntent", {})
    points = list(intent.get("talkingPoints") or [])
    for item in items:
        if item and item not in points:
            points.append(item)
    intent["talkingPoints"] = points
    moved = list(intent.get("movedFromSlide") or [])
    intent["movedFromSlide"] = [*moved, *[item for item in items if item not in moved]]


def plan_patch(
    slide: dict, codes: list[str], snapshot: dict[str, Any], round_number: int
) -> tuple[dict, list[dict]]:
    """Return a patched copy of ``slide`` and the actions taken (empty when nothing helps)."""
    patched = copy.deepcopy(slide)
    actions: list[dict] = []
    content = patched.setdefault("content", {})
    bullets = [str(item) for item in content.get("bullets") or [] if str(item).strip()]
    locked = bool(patched.get("contentLocked"))
    text_pressure = bool({"text-overflow", "dense", "missing-content", "geometry", "unsafe", "wrap"} & set(codes))

    if text_pressure and not locked and bullets:
        budget = _bullet_budget(patched, round_number)
        if len(bullets) > budget:
            moved = bullets[budget:]
            bullets = bullets[:budget]
            _move_to_notes(patched, moved)
            actions.append({"action": "move-bullets-to-notes", "count": len(moved)})
        limit = 40 if "wrap" in codes else _char_limit(round_number)
        shortened, tails = [], []
        for item in bullets:
            split = split_long_bullet(item, limit)
            if split:
                shortened.append(split[0])
                tails.append(item)
            else:
                shortened.append(item)
        if tails:
            bullets = shortened
            _move_to_notes(patched, tails)
            actions.append({"action": "shorten-bullets", "count": len(tails), "limit": limit})
        content["bullets"] = bullets

    if "missing-asset" in codes:
        kept = [item for item in patched.get("assetBindings") or [] if not item.get("path") or Path(item["path"]).exists()]
        if len(kept) != len(patched.get("assetBindings") or []):
            patched["assetBindings"] = kept
            actions.append({"action": "drop-missing-assets"})

    unsafe = [item["variant"] for item in snapshot["candidates"] if not item["safe"]]
    if unsafe:
        layout = dict(patched.get("layoutPlan") or {})
        order = list(layout.get("candidateOrder") or (patched.get("visualIntent") or {}).get("archetypeCandidates") or [])
        steered = [variant for variant in order if variant not in unsafe]
        for variant in TEXT_TOLERANT_VARIANTS:
            if variant not in steered and patched.get("role") not in NAVIGATION_ROLES:
                steered.append(variant)
        if steered and steered != order:
            layout["candidateOrder"] = steered
            if layout.get("recommendedVariant") in unsafe:
                layout["recommendedVariant"] = steered[0]
            patched["layoutPlan"] = layout
            intent = dict(patched.get("visualIntent") or {})
            if intent.get("variantSelectionSource") not in {"user", "critic"} and intent.get("selectedVariant") in unsafe:
                intent.pop("selectedVariant", None)
            patched["visualIntent"] = intent
            actions.append({"action": "steer-layouts", "excluded": unsafe[:6]})
    return patched, actions


def vision_patch_codes(issues: list[str]) -> list[str]:
    """Translate vision critic issues on an otherwise safe page into repair codes."""
    codes = []
    if set(issues) & VISION_TEXT_ISSUES:
        codes.append("wrap")
    return codes


def summarize_repair(history: list[dict], final_snapshot: dict[str, Any]) -> dict:
    return {
        "version": "page-repair-v1",
        "rounds": len(history),
        "history": history,
        "final": "pass" if final_snapshot.get("safeVariants") else "needs-review",
        "selectedVariant": final_snapshot.get("selectedVariant"),
    }
