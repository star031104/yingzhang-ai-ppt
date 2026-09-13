import math
import re


def _rgb(value: str) -> tuple[int, int, int] | None:
    value = (value or "").strip()
    if re.fullmatch(r"#?[0-9a-fA-F]{6}", value):
        cleaned = value.removeprefix("#")
        return tuple(int(cleaned[index:index + 2], 16) for index in (0, 2, 4))
    if value.lower().startswith("rgba"):
        alpha = re.search(r",\s*([\d.]+)\s*\)$", value)
        if alpha and float(alpha.group(1)) < 0.95:
            return None
    match = re.search(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", value)
    return tuple(map(int, match.groups())) if match else None


def _luminance(rgb: tuple[int, int, int]) -> float:
    values = []
    for channel in rgb:
        value = channel / 255
        values.append(value / 12.92 if value <= 0.03928 else math.pow((value + 0.055) / 1.055, 2.4))
    return values[0] * 0.2126 + values[1] * 0.7152 + values[2] * 0.0722


def contrast_ratio(foreground: str, background: str) -> float | None:
    fg, bg = _rgb(foreground), _rgb(background)
    if not fg or not bg:
        return None
    high, low = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def audit_accessibility(slides: list[dict], scene_ir: dict | None = None) -> dict:
    scene_map = {int(item.get("position", 0)): item for item in (scene_ir or {}).get("slides", [])}
    issues = []
    palette = (slides[0].get("designSystem") or {}).get("palette", {}) if slides else {}
    for foreground, background, label, minimum in (
        (palette.get("ink", ""), palette.get("bg", ""), "正文与背景", 4.5),
        (palette.get("accent", ""), palette.get("deep", ""), "强调色与深色背景", 3.0),
    ):
        ratio = contrast_ratio(str(foreground), str(background))
        if ratio is not None and ratio < minimum:
            issues.append({"slide": 0, "code": "low-palette-contrast", "severity": "warning", "ratio": round(ratio, 2), "message": f"{label}对比度不足"})
    for slide in slides:
        position = int(slide.get("position", 0))
        title = str(slide.get("content", {}).get("title", "")).strip()
        if not title:
            issues.append({"slide": position, "code": "missing-reading-title", "severity": "error", "message": "页面缺少阅读顺序起点"})
        for asset in slide.get("assetBindings", []):
            asset_type = asset.get("type")
            if asset_type in {"source-image", "generated-image", "licensed-image", "licensed-video", "licensed-audio"} and not str(asset.get("alt") or asset.get("caption") or "").strip():
                issues.append({"slide": position, "code": "missing-alt-text", "severity": "error", "message": "视觉或媒体素材缺少替代说明"})
            if asset_type in {"licensed-image", "licensed-video", "licensed-audio"} and not asset.get("license"):
                issues.append({"slide": position, "code": "missing-asset-license", "severity": "error", "message": "外部素材缺少授权记录"})
            if asset_type == "licensed-audio" and not str(asset.get("transcript") or "").strip():
                issues.append({"slide": position, "code": "missing-audio-transcript", "severity": "warning", "message": "音频素材缺少文字稿"})
        scene = scene_map.get(position, {})
        for node in scene.get("nodes", []):
            if not str(node.get("text") or "").strip():
                continue
            size = float(node.get("style", {}).get("fontSize", 0) or 0)
            y = float(node.get("bbox", {}).get("y", 0) or 0)
            if 0 < size < 14 and y < 650:
                issues.append({"slide": position, "code": "small-accessible-text", "severity": "warning", "fontSizePx": size, "message": "正文文字可能过小"})
            foreground = node.get("style", {}).get("color", "")
            background = node.get("style", {}).get("backgroundColor", "")
            ratio = contrast_ratio(foreground, background)
            if ratio is not None and ratio < 3:
                issues.append({"slide": position, "code": "low-text-contrast", "severity": "warning", "ratio": round(ratio, 2), "message": "文字对比度不足"})
    errors = sum(item["severity"] == "error" for item in issues)
    warnings = sum(item["severity"] == "warning" for item in issues)
    score = max(0, 100 - errors * 18 - warnings * 6)
    return {
        "standard": "WCAG-inspired-slide-a11y-v1",
        "score": score,
        "errors": errors,
        "warnings": warnings,
        "passed": errors == 0 and score >= 78,
        "issues": issues,
    }
