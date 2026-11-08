"""Run deterministic, synthetic-source gates before merging presentation changes."""

import asyncio
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
from app.evaluation.faithfulness import evaluate_faithfulness
from app.evaluation.perturbation import run_perturbation_suite
from app.evaluation.ppteval import evaluate_ppteval
from app.evaluation.quiz import evaluate_quiz
from app.presentation_intelligence.planner import plan_deck
from app.professional.delivery import audit_delivery_profile
from app.validation.accessibility import audit_accessibility
from app.validation.quality import validate_deck
from app.validation.visual_maturity import variant_family


def reference_style_metrics(family: dict) -> tuple[dict, list[str]]:
    """Synthetic enterprise template: learn its grammar, then fill a planned deck into its master."""
    import importlib.util
    import tempfile

    from app.templates.analyzer import analyze_reference_pptx
    from app.templates.native_fill import fill_native_template
    from pptx import Presentation

    generator = (ROOT / "benchmarks" / family["generator"]).resolve()
    spec = importlib.util.spec_from_file_location("reference_template", generator)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as folder:
        template = module.build(Path(folder) / "template.pptx")
        data = template.read_bytes()
        analysis = analyze_reference_pptx(data)
        fixture = (ROOT / "benchmarks" / family["fixture"]).resolve()
        source = parse_source(fixture.name, fixture.read_bytes(), "text/markdown")
        plan = plan_deck([source], "reference-style", "business", 10)
        output = Path(folder) / "filled.pptx"
        report = fill_native_template(data, plan["slides"], output)
        filled = Presentation(output)
        master_names = {shape.name for shape in filled.slide_master.shapes}
        body_filled = sum(
            1 for planned, slide in zip(plan["slides"], filled.slides, strict=True)
            if planned.get("role") not in {"cover", "section", "questions"}
            and any(shape.placeholder_format.idx != 0 and shape.has_text_frame and shape.text_frame.text.strip()
                    for shape in slide.placeholders)
        )
    learned_fonts = [name for name, _ in analysis.get("fontFamily", [])]
    learned_colors = [color for color, _ in analysis.get("palette", [])]
    roles = {slide["position"]: slide.get("role") for slide in plan["slides"]}
    expected_layout = {"cover": "封面", "section": "章节", "questions": "结束"}
    routed = []
    for index, slide in enumerate(filled.slides, 1):
        hint = expected_layout.get(roles.get(index))
        if hint:
            routed.append(hint in slide.slide_layout.name)
    body_pages = [slide for slide in plan["slides"] if slide.get("role") not in {"cover", "section", "questions"}]
    measured = {
        "templateFontLearned": int(module.FONT in learned_fonts),
        "templateBrandColorLearned": int(str(module.PRIMARY) in learned_colors),
        "templateFunctions": len(analysis.get("functionPatterns", [])),
        "templateTitleFill": round(report["titlesFilled"] / max(1, report["slides"]), 3),
        "templateBodyFill": round(body_filled / max(1, len(body_pages)), 3),
        "templateRoleLayoutMatch": round(sum(routed) / len(routed), 3) if routed else 1.0,
        "templateMasterPreserved": int({"Brand Band", "Footer Rule"} <= master_names),
        "templateFidelityParts": report["fidelityPartsRestored"],
    }
    for metric, minimum in (family.get("thresholds") or {}).items():
        if measured.get(metric, -1) < minimum:
            failures.append(f"{metric} {measured.get(metric, 'missing')} is below {minimum}")
    return measured, failures


def main() -> int:
    manifest = json.loads((ROOT / "benchmarks" / "manifest.json").read_text(encoding="utf-8"))
    thresholds = manifest.get("thresholds", {})
    failures: list[str] = []
    results = []
    for family in manifest.get("families", []):
        family_id = family["id"]
        if family.get("automation") == "generated-template":
            measured, family_failures = reference_style_metrics(family)
            failures.extend(f"{family_id}: {failure}" for failure in family_failures)
            results.append({"family": family_id, "status": "failed" if family_failures else "passed",
                            "metrics": measured, "failures": family_failures})
            continue
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
        # Deterministic PPTEval (rule mode) and PaperQuiz (rule questions, lexical answers).
        ppteval = asyncio.run(evaluate_ppteval(plan["slides"], report))
        quiz = asyncio.run(evaluate_quiz(plan["slides"], [source]))
        # Per-claim source seeking, and proof that each quality gate fires on the
        # defect it targets (perturbation suite).
        faithfulness = asyncio.run(evaluate_faithfulness(plan["slides"], [source]))
        perturbations = run_perturbation_suite(plan["slides"], [source])
        measured = {
            "professionalScore": report.get("professionalAudit", {}).get("overall", 0),
            "contentCoverage": coverage,
            # This suite only plans slides. Final selected/rendered layouts are
            # measured separately by the project quality and Office checks.
            "plannedVisualMaturity": report.get("visualMaturity", {}).get("score", 0),
            "candidateFamilies": len(candidate_families),
            "accessibility": accessibility.get("score", 0),
            "deliveryProfile": delivery_score,
            "pptevalContent": ppteval["deck"]["content"]["score"],
            "pptevalDesign": ppteval["deck"]["design"]["score"],
            "pptevalCoherence": ppteval["deck"]["coherence"]["score"],
            "quizRetention": quiz.get("retention") or 0,
            "quizDetailRetention": quiz.get("detailRetention") or 0,
            "faithfulness": faithfulness.get("faithfulness") or 0,
            "gateDetectionRate": perturbations.get("detectionRate") or 0,
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
            "quizQuestions": quiz.get("questionCount", 0),
            "missingFacts": [item["claim"] for item in quiz.get("missingFacts", [])[:3]],
            "unsupportedClaims": faithfulness.get("unsupported", [])[:3],
            "missedPerturbations": perturbations.get("missed", []),
            "failures": family_failures,
        })
    print(json.dumps({"suite": manifest.get("version"), "families": results, "failures": failures}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
