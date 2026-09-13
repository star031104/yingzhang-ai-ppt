from __future__ import annotations

import re

NUMBER = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?%?")


def _numbers(value) -> list[str]:
    if isinstance(value, list):
        value = " ".join(map(str, value))
    return NUMBER.findall(str(value or ""))


def diff_slide_specs(before: dict, after: dict) -> dict:
    before_content, after_content = before.get("content") or {}, after.get("content") or {}
    changes = []
    for field, old, new in (
        ("title", before_content.get("title"), after_content.get("title")),
        ("message", before.get("message"), after.get("message")),
        ("bullets", before_content.get("bullets", []), after_content.get("bullets", [])),
        ("visualIntent", before.get("visualIntent", {}), after.get("visualIntent", {})),
        ("layoutPlan", before.get("layoutPlan", {}), after.get("layoutPlan", {})),
        ("sourceRefs", before.get("sourceRefs", []), after.get("sourceRefs", [])),
    ):
        if old != new:
            changes.append({"field": field, "before": old, "after": new})
    before_numbers = _numbers(
        [
            before_content.get("title", ""),
            before.get("message", ""),
            *before_content.get("bullets", []),
        ]
    )
    after_numbers = _numbers(
        [
            after_content.get("title", ""),
            after.get("message", ""),
            *after_content.get("bullets", []),
        ]
    )
    added_numbers = [item for item in after_numbers if item not in before_numbers]
    removed_sources = [
        item for item in before.get("sourceRefs", []) if item not in after.get("sourceRefs", [])
    ]
    risks = []
    if added_numbers:
        risks.append({"code": "numeric-claim-added", "values": added_numbers})
    if removed_sources:
        risks.append({"code": "source-removed", "sources": removed_sources})
    return {
        "version": "slide-review-diff-v1",
        "changedFields": [item["field"] for item in changes],
        "changes": changes,
        "risks": risks,
        "requiresEvidenceReview": bool(added_numbers or removed_sources),
    }
