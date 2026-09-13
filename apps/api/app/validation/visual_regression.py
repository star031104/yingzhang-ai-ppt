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
