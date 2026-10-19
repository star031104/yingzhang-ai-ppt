from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageStat


def compare_images(baseline: Path, current: Path, threshold: float = 0.025) -> dict:
    with Image.open(baseline).convert("RGB") as left, Image.open(current).convert("RGB") as right:
        size_changed = left.size != right.size
        if size_changed:
            right = right.resize(left.size)
        difference = ImageChops.difference(left, right)
        mean = sum(ImageStat.Stat(difference).mean) / (3 * 255)
        changed_bbox = difference.getbbox()
        return {
            "baseline": str(baseline),
            "current": str(current),
            "differenceRatio": round(mean, 6),
            "sizeChanged": size_changed,
            "changed": size_changed or mean > threshold,
            "changedBounds": list(changed_bbox) if changed_bbox else None,
        }


def compare_render_roots(baseline_root: Path, current_root: Path, threshold: float = 0.025) -> dict:
    baseline = {path.name: path for path in baseline_root.glob("*.png")}
    current = {path.name: path for path in current_root.glob("*.png")}
    names = sorted(set(baseline) | set(current))
    slides = []
    for name in names:
        if name not in baseline or name not in current:
            slides.append({"name": name, "changed": True, "code": "snapshot-missing"})
        else:
            slides.append(
                {"name": name, **compare_images(baseline[name], current[name], threshold)}
            )
    changed = [item for item in slides if item.get("changed")]
    return {
        "version": "visual-regression-v1",
        "threshold": threshold,
        "checked": len(slides),
        "changed": len(changed),
        "passed": not changed,
        "slides": slides,
    }


# --------------------------------------------------------------------------
# Cross-format fidelity: HTML candidate screenshot vs. Office-rendered PPTX.
# --------------------------------------------------------------------------

FIDELITY_VERSION = "cross-format-fidelity-v1"
_GRID = (320, 180)
_BLOCK = 8

# Chromium resolves "Microsoft YaHei" through its own fallback list when the
# font is absent (Linux CI). LibreOffice would pick fontconfig's default face.
# The harness gives both renderers the same fallback so the comparison measures
# layout fidelity rather than which fonts happen to be installed.
FONT_EMULATION_CONF = """<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>
  <match target="pattern"><test name="family"><string>Microsoft YaHei</string></test>
    <edit name="family" mode="assign" binding="strong"><string>Liberation Sans</string><string>Noto Sans CJK SC</string></edit></match>
  <match target="pattern"><test name="family"><string>SimSun</string></test>
    <edit name="family" mode="assign" binding="strong"><string>DejaVu Serif</string><string>Noto Serif CJK SC</string></edit></match>
  <match target="pattern"><test name="family"><string>Georgia</string></test>
    <edit name="family" mode="assign" binding="strong"><string>DejaVu Serif</string></edit></match>
</fontconfig>
"""


def _gray(image: Image.Image) -> list[int]:
    return list(image.convert("L").resize(_GRID, Image.Resampling.BOX).getdata())


def _block_ssim(left: list[int], right: list[int]) -> float:
    width, height = _GRID
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    total, blocks = 0.0, 0
    for top in range(0, height - _BLOCK + 1, _BLOCK):
        for start in range(0, width - _BLOCK + 1, _BLOCK):
            xs, ys = [], []
            for row in range(top, top + _BLOCK):
                offset = row * width + start
                xs.extend(left[offset:offset + _BLOCK])
                ys.extend(right[offset:offset + _BLOCK])
            count = len(xs)
            mean_x, mean_y = sum(xs) / count, sum(ys) / count
            var_x = sum((x - mean_x) ** 2 for x in xs) / count
            var_y = sum((y - mean_y) ** 2 for y in ys) / count
            cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / count
            total += ((2 * mean_x * mean_y + c1) * (2 * cov + c2)) / (
                (mean_x ** 2 + mean_y ** 2 + c1) * (var_x + var_y + c2)
            )
            blocks += 1
    return total / max(1, blocks)


def fidelity_score(reference: Path | Image.Image, candidate: Path | Image.Image) -> dict:
    """Perceptual similarity (0-100) between an HTML screenshot and an Office render."""
    left = reference if isinstance(reference, Image.Image) else Image.open(reference)
    right = candidate if isinstance(candidate, Image.Image) else Image.open(candidate)
    left, right = left.convert("RGB"), right.convert("RGB").resize(left.size)
    structure = max(0.0, _block_ssim(_gray(left), _gray(right)))
    small = (160, 90)
    difference = ImageChops.difference(
        left.resize(small, Image.Resampling.BOX), right.resize(small, Image.Resampling.BOX)
    )
    color = 1 - sum(ImageStat.Stat(difference).mean) / (3 * 255)
    mask = difference.convert("L").point(lambda value: 255 if value > 48 else 0)
    bounds = mask.getbbox()
    scale = left.size[0] / small[0]
    return {
        "score": round(100 * (0.7 * structure + 0.3 * color), 2),
        "structure": round(structure, 4),
        "color": round(color, 4),
        "changedBounds": [round(value * scale) for value in bounds] if bounds else None,
    }


def cross_format_fidelity(
    html_pages: list[Path | None], office_pages: list[Path | None], threshold: float = 85.0
) -> dict:
    pages = []
    for index, (html, office) in enumerate(zip(html_pages, office_pages), start=1):
        if not html or not office or not Path(html).is_file() or not Path(office).is_file():
            pages.append({"page": index, "score": None, "flagged": True, "code": "render-missing"})
            continue
        result = fidelity_score(Path(html), Path(office))
        pages.append({"page": index, **result, "flagged": result["score"] < threshold})
    for index in range(len(pages) + 1, max(len(html_pages), len(office_pages)) + 1):
        pages.append({"page": index, "score": None, "flagged": True, "code": "page-count-mismatch"})
    scores = [page["score"] for page in pages if page["score"] is not None]
    flagged = [page["page"] for page in pages if page["flagged"]]
    return {
        "version": FIDELITY_VERSION,
        "threshold": threshold,
        "pages": pages,
        "average": round(sum(scores) / len(scores), 2) if scores else None,
        "minimum": min(scores) if scores else None,
        "flaggedPages": flagged,
        "passed": bool(scores) and not flagged,
    }


def office_executable() -> str | None:
    import shutil

    return shutil.which("soffice") or shutil.which("libreoffice")


def render_pptx_pages(
    pptx: Path, output: Path, *, emulate_fonts: bool = True, timeout: int = 240
) -> list[Path] | None:
    """Render PPTX → PDF → PNG (1280×720) with LibreOffice; None when unavailable."""
    import os
    import subprocess

    executable = office_executable()
    if not executable:
        return None
    import pymupdf

    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    if emulate_fonts and os.name != "nt":
        conf = output / "fonts.conf"
        conf.write_text(FONT_EMULATION_CONF, encoding="utf-8")
        env["FONTCONFIG_FILE"] = str(conf)
    profile = (output / "lo-profile").resolve().as_uri()
    try:
        result = subprocess.run(
            [executable, f"-env:UserInstallation={profile}", "--headless", "--convert-to", "pdf",
             "--outdir", str(output), str(pptx)],
            capture_output=True, timeout=timeout, check=False, env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    pdf = output / f"{pptx.stem}.pdf"
    if result.returncode or not pdf.is_file():
        return None
    pages = []
    with pymupdf.open(pdf) as document:
        for index, page in enumerate(document, start=1):
            zoom = 1280 / page.rect.width
            target = output / f"page-{index}.png"
            page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).save(target)
            pages.append(target)
    return pages


def selected_candidate_screenshots(rendered_root: Path, slides: list[dict]) -> list[Path | None]:
    """HTML screenshot of the candidate selected for each slide (by position)."""
    import json
    import re

    screenshots: list[Path | None] = []
    for slide in sorted(slides, key=lambda item: int(item["position"])):
        root = rendered_root / "slides" / str(slide["position"])
        variant = (slide.get("visualIntent") or {}).get("selectedVariant")
        if not variant and (root / "current.json").is_file():
            try:
                variant = json.loads((root / "current.json").read_text(encoding="utf-8")).get("variant")
            except (OSError, ValueError):
                variant = None
        path = root / f"{re.sub(r'[^a-z0-9_-]', '-', str(variant or ''), flags=re.IGNORECASE)}.png"
        screenshots.append(path if variant and path.is_file() else None)
    return screenshots


def office_fidelity_report(
    pptx: Path, rendered_root: Path, slides: list[dict], output: Path, threshold: float = 85.0
) -> dict:
    """Render the PPTX in LibreOffice and score each page against its HTML candidate."""
    pages = render_pptx_pages(pptx, output)
    if pages is None:
        return {"version": FIDELITY_VERSION, "status": "unavailable",
                "message": "未找到 LibreOffice，跳过跨格式保真度检查"}
    report = cross_format_fidelity(selected_candidate_screenshots(rendered_root, slides), pages, threshold)
    return {**report, "status": "measured", "renderer": "libreoffice", "fontEmulation": True}


def office_page_fidelity(rendered_root: Path, slides: list[dict], office_pages: list[Path]) -> dict:
    """Advisory fidelity of an existing Office render against the selected HTML candidates."""
    if not office_pages:
        return {"version": FIDELITY_VERSION, "status": "unavailable", "message": "没有可比较的渲染页面"}
    report = cross_format_fidelity(selected_candidate_screenshots(rendered_root, slides), office_pages)
    return {**report, "status": "measured", "advisory": True}
