"""Render-grounded review of the exported PPTX (LibreOffice → PDF → PNG), not the HTML preview.

Pages are checked deterministically (blank pages, near-empty regions, edge-touching content,
very low contrast, page-count and title presence) and, when a vision model is configured,
judged by it on the real page images. Missing LibreOffice degrades to ``unavailable``.
"""

import asyncio
import json
from pathlib import Path

from app.evaluation.common import clamp_score, parse_json_object, short

VERSION = "render-review-v1"
ANALYSIS_WIDTH = 320
_GRID = 3


def _luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        value = value / 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = rgb
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def contrast_ratio(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    a, b = sorted((_luminance(first), _luminance(second)), reverse=True)
    return round((a + 0.05) / (b + 0.05), 2)


def analyze_page_image(path: Path) -> dict:
    """Deterministic image metrics and issues for one rendered page."""
    from PIL import Image

    with Image.open(path) as source:
        image = source.convert("RGB")
        # PDF rasterization can leave a 1px white seam at the page edge; it is not slide content.
        trim = max(1, round(image.width * 0.002))
        image = image.crop((trim, trim, image.width - trim, image.height - trim))
        height = max(1, round(image.height * ANALYSIS_WIDTH / max(1, image.width)))
        image = image.resize((ANALYSIS_WIDTH, height))
    width = image.width
    pixels = list(image.getdata())
    border = [pixels[index] for index in range(width)] + [pixels[-index - 1] for index in range(width)]
    border += [pixels[row * width] for row in range(height)] + [pixels[row * width + width - 1] for row in range(height)]
    counts: dict[tuple[int, int, int], int] = {}
    for red, green, blue in border:
        key = (red // 8 * 8, green // 8 * 8, blue // 8 * 8)
        counts[key] = counts.get(key, 0) + 1
    modal = max(counts, key=counts.get)
    members = [pixel for pixel in border if (pixel[0] // 8 * 8, pixel[1] // 8 * 8, pixel[2] // 8 * 8) == modal]
    background = tuple(round(sum(pixel[index] for pixel in members) / len(members)) for index in range(3))

    def distance(pixel) -> int:
        return max(abs(pixel[0] - background[0]), abs(pixel[1] - background[1]), abs(pixel[2] - background[2]))

    distances = [distance(pixel) for pixel in pixels]
    mask = [value > 28 for value in distances]
    content_ratio = sum(mask) / max(1, len(mask))
    # Barely distinguishable pixels: present on the page but nearly invisible when projected.
    faint = [6 < value <= 28 for value in distances]
    faint_ratio = sum(faint) / max(1, len(faint))
    # Faint text is made of thin strokes; a pale panel or tinted band is a solid area and is
    # legitimate design. Measure how many faint pixels sit on a horizontal stroke boundary.
    faint_edges = sum(
        1 for index, flag in enumerate(faint)
        if flag and (index % width in {0, width - 1} or not faint[index - 1] or not faint[index + 1])
    )
    faint_texture = faint_edges / max(1, sum(faint))
    cells = []
    for row in range(_GRID):
        for column in range(_GRID):
            x0, x1 = column * width // _GRID, (column + 1) * width // _GRID
            y0, y1 = row * height // _GRID, (row + 1) * height // _GRID
            total = max(1, (x1 - x0) * (y1 - y0))
            filled = sum(mask[y * width + x] for y in range(y0, y1) for x in range(x0, x1))
            cells.append(filled / total)
    strip = 1  # content in the outermost ~0.3% of the page is touching or crossing the edge
    edges = {
        "top": [mask[y * width + x] for y in range(strip) for x in range(width)],
        "bottom": [mask[y * width + x] for y in range(height - strip, height) for x in range(width)],
        "left": [mask[y * width + x] for y in range(height) for x in range(strip)],
        "right": [mask[y * width + x] for y in range(height) for x in range(width - strip, width)],
    }
    edge_ratios = {name: round(sum(values) / max(1, len(values)), 3) for name, values in edges.items()}
    luminance_background = _luminance(background)
    content_pixels = [pixel for pixel, flag in zip(pixels, mask) if flag]
    contrast = None
    if content_pixels:
        ranked = sorted(content_pixels, key=lambda pixel: abs(_luminance(pixel) - luminance_background))
        strongest = ranked[min(len(ranked) - 1, int(len(ranked) * 0.95))]
        contrast = contrast_ratio(strongest, background)
    issues = []
    if 0.002 < faint_ratio < 0.2 and faint_ratio > content_ratio * 0.6 and faint_texture > 0.35:
        issues.append({"code": "low-contrast", "severity": "error",
                       "message": "页面存在与背景几乎同色的内容，投影时难以辨认"})
    elif content_ratio < 0.004:
        issues.append({"code": "blank-page", "severity": "error", "message": "导出页面几乎空白"})
    elif content_ratio < 0.008:
        issues.append({"code": "near-empty-page", "severity": "warning", "message": "页面内容极少"})
    empty_cells = sum(value < 0.004 for value in cells)
    if content_ratio >= 0.004 and empty_cells >= 6:
        issues.append({"code": "large-empty-region", "severity": "warning",
                       "message": f"{empty_cells}/9 个区域没有内容，构图失衡"})
    touching = [name for name, value in edge_ratios.items() if 0.008 < value < 0.6]
    if touching:
        labels = {"top": "上", "bottom": "下", "left": "左", "right": "右"}
        issues.append({"code": "edge-touching", "severity": "warning",
                       "message": "内容贴近或超出" + "、".join(labels[name] for name in touching) + "边缘"})
    if contrast is not None and content_ratio >= 0.004 and contrast < 2.0 and not any(
        issue["code"] == "low-contrast" for issue in issues
    ):
        issues.append({"code": "low-contrast", "severity": "error", "message": f"前景与背景对比度仅 {contrast}:1"})
    penalty = sum(2 if issue["severity"] == "error" else 1 for issue in issues)
    return {
        "metrics": {
            "contentRatio": round(content_ratio, 4),
            "faintRatio": round(faint_ratio, 4),
            "faintTexture": round(faint_texture, 3),
            "emptyRegions": empty_cells,
            "edgeRatios": edge_ratios,
            "contrast": contrast,
            "background": "#{:02x}{:02x}{:02x}".format(*background),
        },
        "issues": issues,
        "score": max(1, 5 - penalty),
    }


def _text_checks(slides: list[dict], pages: list[dict]) -> tuple[list[dict], dict[int, list[dict]]]:
    deck_issues = []
    per_page: dict[int, list[dict]] = {}
    if slides and len(pages) != len(slides):
        deck_issues.append({
            "code": "page-count-mismatch", "severity": "error", "page": 0,
            "message": f"PPTX 渲染得到 {len(pages)} 页，页面规格为 {len(slides)} 页",
        })
    for spec, page in zip(slides, pages):
        title = "".join(str((spec.get("content") or {}).get("title", "")).split())
        text = "".join(str(page.get("text", "")).split())
        if title and text and title[:12] not in text:
            per_page.setdefault(page["page"], []).append({
                "code": "missing-title-text", "severity": "warning", "message": "标题未在导出页面中完整读取",
            })
    return deck_issues, per_page


def _vision_prompt(batch: list[dict]) -> str:
    pages = [{"page": item["page"], "title": item.get("title", "")} for item in batch]
    schema = {"pages": [{
        "page": "页码", "score": "1-5 的整数，5 为最好",
        "issues": [{"type": "overflow|overlap|contrast|empty|alignment|readability|other",
                    "severity": "error|warning", "message": "中文问题描述", "suggestion": "具体修改建议"}],
    }]}
    return (
        "你是演示文稿视觉质检员。随附图片依次是一份 PPTX 在 LibreOffice 中的实际渲染页面。"
        "请检查文字溢出或裁切、元素重叠、对比度、空白失衡、对齐和可读性，只报告确实可见的问题。\n"
        f"页面：{json.dumps(pages, ensure_ascii=False)}\n"
        f"只输出 JSON：{json.dumps(schema, ensure_ascii=False)}"
    )


async def _vision_review(judge, pages: list[dict], output: Path) -> tuple[dict[int, dict], list[str]]:
    reviews: dict[int, dict] = {}
    errors: list[str] = []
    for start in range(0, len(pages), 4):
        batch = pages[start:start + 4]
        try:
            images = [(output / item["image"]).read_bytes() for item in batch]
            payload = parse_json_object(await judge.see(_vision_prompt(batch), images))
        except Exception as exc:  # noqa: BLE001 - provider failures fall back to deterministic checks
            errors.append(short(f"视觉检查失败：{exc}", 200))
            break
        allowed = {item["page"] for item in batch}
        for entry in payload.get("pages", []) if isinstance(payload.get("pages"), list) else []:
            if not isinstance(entry, dict):
                continue
            try:
                page = int(entry.get("page"))
            except (TypeError, ValueError):
                continue
            if page not in allowed:
                continue
            issues = []
            for issue in entry.get("issues", []) if isinstance(entry.get("issues"), list) else []:
                if isinstance(issue, dict) and issue.get("message"):
                    issues.append({
                        "code": f"vision-{short(issue.get('type') or 'other', 20)}",
                        "severity": "error" if issue.get("severity") == "error" else "warning",
                        "message": short(issue["message"], 120),
                        "suggestion": short(issue.get("suggestion"), 160),
                        "source": "vision",
                    })
            reviews[page] = {"score": clamp_score(entry.get("score")), "issues": issues[:6]}
    return reviews, errors


def render_pptx(pptx: Path, output: Path) -> dict:
    """LibreOffice → PDF → PNG via the shared desktop-verification renderer."""
    from app.personalization.office import render_office

    return render_office(pptx, output, "libreoffice")


async def review_rendered_pptx(
    pptx: Path | None,
    slides: list[dict],
    output: Path,
    *,
    vision_judge=None,
    renderer=render_pptx,
) -> dict:
    if not pptx or not pptx.is_file():
        return {"version": VERSION, "status": "no-export", "message": "尚无可检查的 PPTX 导出，请先导出 PPTX",
                "pages": [], "issues": []}
    output.mkdir(parents=True, exist_ok=True)
    rendered = await asyncio.to_thread(renderer, pptx, output)
    if rendered.get("status") != "rendered-needs-review":
        return {"version": VERSION, "status": "unavailable" if rendered.get("status") == "unavailable" else "failed",
                "message": rendered.get("message", "PPTX 渲染失败"), "pages": [], "issues": [],
                "fileHash": rendered.get("fileHash")}
    pages_raw = rendered.get("pages", [])
    deck_issues, text_issues = _text_checks(slides, pages_raw)
    pages = []
    for page in pages_raw:
        analysis = await asyncio.to_thread(analyze_page_image, output / page["image"])
        issues = [*analysis["issues"], *text_issues.get(page["page"], [])]
        spec = slides[page["page"] - 1] if page["page"] - 1 < len(slides) else {}
        pages.append({
            "page": page["page"], "image": page["image"], "imagePath": str(output / page["image"]),
            "slideId": spec.get("id"), "title": short((spec.get("content") or {}).get("title", ""), 60),
            "metrics": analysis["metrics"], "issues": issues,
            "score": max(1, analysis["score"] - (1 if text_issues.get(page["page"]) else 0)),
            "source": "deterministic",
        })
    mode = "deterministic"
    errors: list[str] = []
    if vision_judge and pages:
        reviews, errors = await _vision_review(vision_judge, pages, output)
        for page in pages:
            review = reviews.get(page["page"])
            if not review:
                continue
            mode = "vision"
            page["issues"].extend(review["issues"])
            if review["score"] is not None:
                page["score"] = min(page["score"], review["score"]) if page["issues"] else review["score"]
            page["source"] = "vision+deterministic"
    flattened = [*deck_issues]
    for page in pages:
        flattened.extend({"page": page["page"], **issue} for issue in page["issues"])
    errors_count = sum(issue.get("severity") == "error" for issue in flattened)
    return {
        "version": VERSION,
        "status": "completed",
        "mode": mode,
        "model": getattr(vision_judge, "model_id", None) if mode == "vision" else None,
        "fileHash": rendered.get("fileHash"),
        "pageCount": len(pages),
        "slideCount": len(slides),
        "averageScore": round(sum(page["score"] for page in pages) / len(pages), 1) if pages else None,
        "errorCount": errors_count,
        "warningCount": len(flattened) - errors_count,
        "pages": pages,
        "issues": flattened,
        "errors": errors,
    }
