"""Multi-turn edit drift (DECKBench-style) computed from slide version history.

A person edits a deck over many turns. Two promises are checked:

1. **Scope** – an edit turn only changes what it targeted. Changing a page's copy
   must not silently rebind its sources, evidence or theme, and must not touch
   other pages.
2. **Persistence** – what a person decided (edited copy, a chosen candidate) is
   not reverted by a later automatic step such as regeneration, render repair or
   recovery.

``deck_drift`` compares two deck snapshots around one turn; ``history_drift``
replays the stored ``SlideVersion`` rows of a project.
"""

from __future__ import annotations

from itertools import pairwise
from typing import Any

VERSION = "edit-drift-v1"
RENDER_FIELDS = ("role", "message", "content", "sourceRefs", "assetBindings", "designSystem", "layoutPlan")
EDITABLE_FIELDS = {"message", "content", "visualIntent", "layoutPlan", "constraints", "speakerIntent"}
PROTECTED_FIELDS = {"sourceRefs", "evidenceBindings", "designSystem", "role", "position"}
AUTOMATIC_REASONS = {
    "initial outline",
    "automatic outline recovery",
    "automatic render repair",
    "narration-generated",
    "powerpoint-effects",
}


def _visual(spec: dict) -> dict:
    intent = dict(spec.get("visualIntent") or {})
    intent.pop("criticIssues", None)
    return intent


def changed_fields(before: dict, after: dict) -> list[str]:
    fields = [field for field in (*RENDER_FIELDS, "evidenceBindings", "speakerIntent", "constraints") if before.get(field) != after.get(field)]
    if _visual(before) != _visual(after):
        fields.append("visualIntent")
    return fields


def deck_drift(before: list[dict], after: list[dict], targets: set[str], allowed: set[str] | None = None) -> dict:
    """Changes one edit turn made outside its targets or outside the editable fields."""
    allowed = allowed or EDITABLE_FIELDS
    before_map = {slide["id"]: slide for slide in before}
    after_map = {slide["id"]: slide for slide in after}
    off_target = []
    out_of_scope = []
    for slide_id, new in after_map.items():
        old = before_map.get(slide_id)
        if old is None:
            off_target.append({"slideId": slide_id, "fields": ["added"]})
            continue
        fields = changed_fields(old, new)
        if not fields:
            continue
        if slide_id not in targets:
            off_target.append({"slideId": slide_id, "position": new.get("position"), "fields": fields})
        else:
            unexpected = [field for field in fields if field not in allowed]
            if unexpected:
                out_of_scope.append({"slideId": slide_id, "position": new.get("position"), "fields": unexpected})
    removed = [slide_id for slide_id in before_map if slide_id not in after_map]
    return {
        "offTarget": off_target,
        "outOfScope": out_of_scope,
        "removed": removed,
        "drifted": bool(off_target or out_of_scope or removed),
    }


def _is_user(reason: str) -> bool:
    return bool(reason) and reason not in AUTOMATIC_REASONS


def history_drift(versions: list[dict[str, Any]]) -> dict[str, Any]:
    """Replay version rows ``{slideId, position, version, reason, spec, createdAt}``."""
    by_slide: dict[str, list[dict]] = {}
    for row in sorted(versions, key=lambda item: (str(item.get("slideId")), int(item.get("version") or 0))):
        by_slide.setdefault(str(row.get("slideId")), []).append(row)
    turns = []
    overwritten = []
    for slide_id, rows in by_slide.items():
        user_copy: dict | None = None
        user_selection: str | None = None
        for previous, current in pairwise(rows):
            reason = str(current.get("reason") or "")
            before, after = previous.get("spec") or {}, current.get("spec") or {}
            fields = changed_fields(before, after)
            if _is_user(reason):
                allowed = set(EDITABLE_FIELDS)
                if "素材" in reason:
                    allowed.add("assetBindings")
                unexpected = [field for field in fields if field not in allowed]
                turns.append({
                    "slideId": slide_id,
                    "position": after.get("position"),
                    "version": current.get("version"),
                    "reason": reason[:80],
                    "changed": fields,
                    "outOfScope": unexpected,
                    "drifted": bool(unexpected),
                })
                if {"content", "message"} & set(fields):
                    user_copy = {"content": after.get("content"), "message": after.get("message")}
                intent = after.get("visualIntent") or {}
                if intent.get("variantSelectionSource") == "user":
                    user_selection = intent.get("selectedVariant")
                continue
            if user_copy and (after.get("content") != user_copy["content"] or after.get("message") != user_copy["message"]):
                overwritten.append({
                    "slideId": slide_id, "position": after.get("position"), "version": current.get("version"),
                    "kind": "copy", "by": reason[:80],
                })
                user_copy = None
            intent = after.get("visualIntent") or {}
            if user_selection and intent.get("selectedVariant") and intent.get("selectedVariant") != user_selection:
                overwritten.append({
                    "slideId": slide_id, "position": after.get("position"), "version": current.get("version"),
                    "kind": "selection", "by": reason[:80],
                })
                user_selection = None
    drifted_turns = [turn for turn in turns if turn["drifted"]]
    return {
        "version": VERSION,
        "status": "completed" if turns else "no-edits",
        "turns": len(turns),
        "driftedTurns": len(drifted_turns),
        "driftRate": round(len(drifted_turns) / len(turns), 3) if turns else None,
        "overwritten": overwritten[:20],
        "persistence": round(1 - min(len(overwritten), len(turns)) / len(turns), 3) if turns else None,
        "details": drifted_turns[:20],
    }
