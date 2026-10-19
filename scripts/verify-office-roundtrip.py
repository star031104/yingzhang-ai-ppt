"""Render each automated benchmark deck in LibreOffice and measure cross-format fidelity.

For every fixture the planner output is rendered to HTML candidates (the same
build used by the product), the selected candidates are exported to PPTX in the
scene-driven mode (and, for comparison, the legacy mode), LibreOffice renders
the PPTX to PDF/PNG and every page is scored against the HTML screenshot of its
selected candidate.

    uv run python scripts/verify-office-roundtrip.py [--mode both|scene|legacy]
        [--min-fidelity 90] [--keep DIR] [--json] [--skip-if-unavailable]
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

import pymupdf
from app.documents import parse_source
from app.presentation_engine.service import load_export_report, presentation_engine
from app.presentation_intelligence.planner import plan_deck
from app.validation.visual_regression import (
    cross_format_fidelity,
    office_executable,
    render_pptx_pages,
    selected_candidate_screenshots,
)

FIXTURES = {
    "business": ("business-report/fixture.md", "business"),
    "data": ("data-dashboard/fixture.md", "data"),
    "product": ("product-launch/fixture.md", "product"),
    "academic": ("academic-thesis/fixture.md", "academic"),
}


def build_family(family: str, fixture: str, preset: str, root: Path) -> tuple[list[dict], Path]:
    fixture_path = ROOT / "benchmarks" / fixture
    source = parse_source(fixture_path.name, fixture_path.read_bytes(), "text/markdown")
    slides = plan_deck([source], family, preset, 8)["slides"]
    rendered = root / family / "rendered"
    presentation_engine.run("build", slides, rendered)
    for slide in slides:
        current = json.loads((rendered / "slides" / str(slide["position"]) / "current.json").read_text(encoding="utf-8"))
        slide.setdefault("visualIntent", {})["selectedVariant"] = current["variant"]
    return slides, rendered


def export_and_measure(family: str, slides: list[dict], rendered: Path, mode: str, root: Path) -> dict:
    pptx = root / family / f"{family}-{mode}.pptx"
    previous = os.environ.get("YINGZHANG_PPTX_MODE")
    os.environ["YINGZHANG_PPTX_MODE"] = mode
    try:
        presentation_engine.run("pptx", slides, pptx, scene_root=rendered)
    finally:
        if previous is None:
            os.environ.pop("YINGZHANG_PPTX_MODE", None)
        else:
            os.environ["YINGZHANG_PPTX_MODE"] = previous
    pages = render_pptx_pages(pptx, root / family / f"office-{mode}")
    if pages is None:
        raise SystemExit(f"LibreOffice failed to render the {family} benchmark deck ({mode})")
    if len(pages) != len(slides):
        raise SystemExit(f"{family} ({mode}): expected {len(slides)} pages, got {len(pages)}")
    with pymupdf.open(root / family / f"office-{mode}" / f"{pptx.stem}.pdf") as document:
        page_text = ["".join(page.get_text().split()) for page in document]
    missing_titles = [
        slide["position"] for slide in slides
        if (title := "".join(str(slide.get("content", {}).get("title", "")).split()))
        and title not in page_text[slide["position"] - 1]
    ]
    fidelity = cross_format_fidelity(selected_candidate_screenshots(rendered, slides), pages)
    export = load_export_report(pptx) or {}
    return {
        "mode": mode,
        "fidelity": fidelity,
        "missingTitles": missing_titles,
        "sceneSlides": export.get("sceneSlides"),
        "legacySlides": export.get("legacySlides"),
        "fallbacks": [
            {"position": item["position"], "reason": item.get("fallbackReason")}
            for item in export.get("slides", []) if item.get("renderer") == "legacy" and item.get("fallbackReason")
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("both", "scene", "legacy"), default="both")
    parser.add_argument("--min-fidelity", type=float, default=90.0,
                        help="minimum average fidelity of the scene-driven export per deck")
    parser.add_argument("--keep", type=Path, help="keep renders (HTML, PPTX, PNG) in this directory")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    parser.add_argument("--skip-if-unavailable", action="store_true",
                        help="exit successfully when LibreOffice is not installed")
    parser.add_argument("--families", nargs="*", default=list(FIXTURES))
    args = parser.parse_args()

    if not office_executable():
        if args.skip_if_unavailable:
            print("LibreOffice not found; cross-format fidelity check skipped.")
            return 0
        raise SystemExit("LibreOffice is required for the delivery round-trip check")

    modes = ("scene", "legacy") if args.mode == "both" else (args.mode,)
    failures: list[str] = []
    results: dict[str, dict] = {}
    with tempfile.TemporaryDirectory(prefix="yingzhang-office-") as directory:
        root = args.keep.resolve() if args.keep else Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        for family in args.families:
            fixture, preset = FIXTURES[family]
            if args.keep:
                shutil.rmtree(root / family, ignore_errors=True)
            slides, rendered = build_family(family, fixture, preset, root)
            results[family] = {}
            for mode in modes:
                outcome = export_and_measure(family, slides, rendered, mode, root)
                results[family][mode] = outcome
                fidelity = outcome["fidelity"]
                scores = " ".join(f"{page['score']:.1f}" if page["score"] is not None else "--" for page in fidelity["pages"])
                print(f"{family:9} {mode:6} average {fidelity['average']:6.2f}  minimum {fidelity['minimum']:6.2f}  "
                      f"scene/legacy slides {outcome['sceneSlides']}/{outcome['legacySlides']}  pages [{scores}]")
                if outcome["missingTitles"]:
                    failures.append(f"{family} ({mode}): titles missing on pages {outcome['missingTitles']}")
                if mode == "scene" and (fidelity["average"] or 0) < args.min_fidelity:
                    failures.append(f"{family}: scene fidelity {fidelity['average']} is below {args.min_fidelity}")
                if mode == "scene" and outcome["fallbacks"]:
                    print(f"{family:9} fallbacks: {outcome['fallbacks']}")
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    for failure in failures:
        print(f"FAILED: {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
