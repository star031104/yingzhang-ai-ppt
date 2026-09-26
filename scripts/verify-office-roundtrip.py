"""Render planner output from each automated benchmark in LibreOffice."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

import pymupdf
from app.documents import parse_source
from app.presentation_engine.service import presentation_engine
from app.presentation_intelligence.planner import plan_deck

FIXTURES = {
    "business": ("business-report/fixture.md", "business"),
    "data": ("data-dashboard/fixture.md", "data"),
    "product": ("product-launch/fixture.md", "product"),
    "academic": ("academic-thesis/fixture.md", "academic"),
}


def main() -> int:
    office = shutil.which("libreoffice") or shutil.which("soffice")
    if not office:
        raise SystemExit("LibreOffice is required for the delivery round-trip check")

    with tempfile.TemporaryDirectory(prefix="yingzhang-office-") as directory:
        root = Path(directory)
        output = root / "rendered"
        output.mkdir()
        for family, (fixture, preset) in FIXTURES.items():
            fixture_path = ROOT / "benchmarks" / fixture
            source = parse_source(fixture_path.name, fixture_path.read_bytes(), "text/markdown")
            plan = plan_deck([source], family, preset, 8)
            slides = plan["slides"]
            pptx = root / f"{family}.pptx"
            presentation_engine.run("pptx", slides, pptx)
            family_output = output / family
            family_output.mkdir()
            profile = (root / f"lo-profile-{family}").as_uri()
            result = subprocess.run(
                [office, f"-env:UserInstallation={profile}", "--headless", "--convert-to", "pdf",
                 "--outdir", str(family_output), str(pptx)],
                capture_output=True,
                timeout=240,
                check=False,
            )
            pdf = family_output / f"{family}.pdf"
            if result.returncode or not pdf.is_file():
                raise SystemExit(f"LibreOffice failed to render the {family} benchmark deck")
            with pymupdf.open(pdf) as rendered:
                if len(rendered) != len(slides):
                    raise SystemExit(
                        f"{family}: expected {len(slides)} pages, got {len(rendered)}"
                    )
                page_text = ["".join(page.get_text().split()) for page in rendered]
                for slide in slides:
                    title = "".join(str(slide.get("content", {}).get("title", "")).split())
                    if title and title not in page_text[slide["position"] - 1]:
                        raise SystemExit(
                            f"{family} page {slide['position']} is missing its title after rendering"
                        )
            print(f"LibreOffice rendered {family}: {len(slides)} generated slides.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
