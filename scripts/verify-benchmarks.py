"""Run deterministic, synthetic-source gates before merging presentation changes."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

PRESETS = {
    "academic": "academic",
    "business": "business",
    "business-report": "business",
    "product": "product",
    "product-launch": "product",
    "data": "data",
    "data-dashboard": "data",
}

from app.documents import parse_source
from app.presentation_intelligence.planner import plan_deck
from app.professional.delivery import audit_delivery_profile
from app.validation.accessibility import audit_accessibility
from app.validation.quality import validate_deck
from app.validation.visual_maturity import variant_family


def main() -> int:
    manifest = json.loads((ROOT / "benchmarks" / "manifest.json").read_text(encoding="utf-8"))
    thresholds = manifest.get("thresholds", {})
    failures: list[str] = []
    results = []
    for family in manifest.get("families", []):
        family_id = family["id"]
        if family.get("automation") == "manual":
            results.append({"family": family_id, "status": "manual", "reason": family.get("reason", "")})
            continue
        if family_id not in PRESETS:
            failures.append(f"{family_id}: no planner preset is configured")
            results.append({"family": family_id, "status": "failed", "reason": "preset missing"})
            continue
        fixture = (ROOT / "benchmarks" / family["fixture"]).resolve()
        if ROOT / "benchmarks" not in fixture.parents or not fixture.is_file():
            failures.append(f"{family_id}: fixture missing or outside benchmark root")
            continue
        source = parse_source(fixture.name, fixture.read_bytes(), "text/markdown")
        plan = plan_deck([source], family_id, PRESETS[family_id], 8)
        report = validate_deck(plan["slides"], [source])
        coverage = report.get("contentCoverage", 0)
        accessibility = audit_accessibility(plan["slides"])
        delivery = {
            profile: audit_delivery_profile(plan["slides"], profile)
            for profile in ("powerpoint-windows", "powerpoint-macos", "wps", "libreoffice")
        }
        delivery_score = min((item["score"] for item in delivery.values()), default=0)
        body_slides = [
            slide for slide in plan["slides"]
            if slide.get("role") not in {"cover", "agenda", "section", "questions"}
        ]
        candidate_families = {
            variant_family(variant)
            for slide in body_slides
            for variant in (slide.get("layoutPlan") or {}).get("candidateOrder", [])
        }
        measured = {
            "professionalScore": report.get("professionalAudit", {}).get("overall", 0),
            "contentCoverage": coverage,
            # This suite only plans slides. Final selected/rendered layouts are
            # measured separately by the project quality and Office checks.
            "plannedVisualMaturity": report.get("visualMaturity", {}).get("score", 0),
            "candidateFamilies": len(candidate_families),
            "accessibility": accessibility.get("score", 0),
            "deliveryProfile": delivery_score,
        }
        family_failures = []
        if not report.get("passed"):
            family_failures.append(
                f"planner/quality gate failed with {report.get('blockingErrors')} blocking issue(s)"
            )
        if not accessibility.get("passed"):
            family_failures.append("accessibility gate failed")
        for metric, minimum in thresholds.items():
            if measured.get(metric, -1) < minimum:
                family_failures.append(
                    f"{metric} {measured.get(metric, 'missing')} is below {minimum}"
                )
        source_sections = {section["id"] for section in source.get("sections", [])}
        if any(
            reference.get("section") not in source_sections
            for slide in plan["slides"]
            for reference in slide.get("sourceRefs", [])
        ):
            family_failures.append("a planned slide references a missing source section")
        fact_text = " ".join(fact.get("claim", "") for fact in plan.get("evidence", {}).get("facts", []))
        planned_text = " ".join(
            " ".join([
                str(slide.get("content", {}).get("title", "")),
                str(slide.get("message", "")),
                *map(str, slide.get("content", {}).get("bullets", [])),
            ])
            for slide in plan["slides"]
        )
        for expected in family.get("requiredValues", []):
            if expected not in fact_text or expected not in planned_text:
                family_failures.append(
                    f"required benchmark value {expected!r} must appear in extracted evidence and planned slides"
                )
        failures.extend(f"{family_id}: {failure}" for failure in family_failures)
        results.append({
            "family": family_id,
            "status": "failed" if family_failures else "passed",
            "metrics": measured,
            "blockingErrors": report.get("blockingErrors", 0),
            "facts": len(plan.get("evidence", {}).get("facts", [])),
            "failures": family_failures,
        })
    print(json.dumps({"suite": manifest.get("version"), "families": results, "failures": failures}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
