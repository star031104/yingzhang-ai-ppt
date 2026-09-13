import copy
import secrets

from app.db.models import PersonalComparison


def compare_quality(ordinary, personal):
    reasons = []
    if personal.get("blockingErrors", 0) > ordinary.get("blockingErrors", 0):
        reasons.append("blockingErrors")
    for key in ("claimCoverage", "contentCoverage"):
        if personal.get(key, 0) < ordinary.get(key, 0):
            reasons.append(key)
    for key, value in ordinary.get("scorecard", {}).items():
        if personal.get("scorecard", {}).get(key, 0) < value:
            reasons.append(f"scorecard.{key}")
    return reasons


def record_comparison(db, project_id, snapshot, baseline, personal, baseline_model, personal_model, reasons):
    labels = ["ordinary", "personal"]
    secrets.SystemRandom().shuffle(labels)
    row = PersonalComparison(project_id=project_id, owner_id=snapshot["ownerId"], epoch=snapshot["epoch"], payload={
        "version": 1, "labels": dict(zip(["A", "B"], labels, strict=True)),
        "ordinary": copy.deepcopy(baseline), "personal": copy.deepcopy(personal),
        "baselineModel": baseline_model, "personalModel": personal_model,
        "fallbackReasons": reasons, "snapshotDigest": snapshot["digest"],
        "modelComparison": ("both-model" if all(run and run.get("returnedSlides", 0) > 0 and not run.get("batchErrors") for run in (baseline_model, personal_model))
                            else "partial-model" if baseline_model or personal_model else "builtin"),
    })
    db.add(row)
    db.flush()
    return row.id
