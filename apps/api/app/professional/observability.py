from __future__ import annotations

from datetime import UTC, datetime


def append_stage_trace(checkpoint: dict, stage: str, label: str, progress: float) -> dict:
    value = dict(checkpoint or {})
    trace = list(value.get("trace") or [])
    now = datetime.now(UTC)
    previous = trace[-1] if trace else None
    elapsed = None
    if previous and previous.get("at"):
        try:
            elapsed = round((now - datetime.fromisoformat(previous["at"])).total_seconds(), 3)
        except ValueError:
            elapsed = None
    trace.append(
        {
            "stage": stage,
            "label": label,
            "progress": progress,
            "at": now.isoformat(),
            "elapsedFromPreviousSeconds": elapsed,
        }
    )
    value.update({"stage": stage, "label": label, "trace": trace[-40:]})
    return value
