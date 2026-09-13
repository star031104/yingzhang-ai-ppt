from __future__ import annotations

import re

HEX = re.compile(r"^#[0-9A-F]{6}$", re.IGNORECASE)


def compile_brand_kit(design_system: dict, assets: list | None = None) -> dict:
    assets = assets or []
    brand = dict(design_system.get("brand") or {})
    palette = dict(design_system.get("palette") or {})
    asset_rows = []
    for asset in assets:
        if isinstance(asset, dict):
            get = asset.get
        else:
            get = lambda key, default=None, row=asset: getattr(row, key, default)
        asset_rows.append(
            {
                "id": get("id", ""),
                "name": get("name", ""),
                "kind": get("kind", ""),
                "path": get("artifact_path", ""),
                "metadata": get("metadata_json", {}) or {},
            }
        )
    fonts = [item for item in asset_rows if item["kind"] == "font"]
    logos = [item for item in asset_rows if item["kind"] == "logo"]
    images = [item for item in asset_rows if item["kind"] == "image"]
    colors = {
        key: value for key, value in palette.items() if isinstance(value, str) and HEX.match(value)
    }
    score = 25
    score += 20 if brand.get("name") else 0
    score += 20 if logos or brand.get("logoPath") else 0
    score += 15 if len(colors) >= 4 else 0
    score += 10 if fonts or design_system.get("typography", {}).get("fontFamily") else 0
    score += 10 if images else 0
    return {
        "version": "brand-kit-v1",
        "name": brand.get("name", ""),
        "score": min(100, score),
        "palette": colors,
        "typography": {
            "primary": brand.get("fontFamily")
            or design_system.get("typography", {}).get("fontFamily", "Microsoft YaHei"),
            "embeddedFonts": fonts,
        },
        "logos": logos
        or ([{"path": brand["logoPath"], "kind": "logo"}] if brand.get("logoPath") else []),
        "imagery": {"library": images, "style": brand.get("imageryStyle", "documentary")},
        "iconography": {"style": brand.get("iconStyle", "outline"), "strokeConsistency": True},
        "rules": {
            "logoSafeArea": brand.get("logoSafeArea", 0.5),
            "minimumLogoWidth": brand.get("minimumLogoWidth", 72),
            "forbiddenEffects": brand.get("forbiddenEffects", ["neon-glow", "heavy-drop-shadow"]),
            "chartUsesBrandPalette": True,
            "audienceCopyMustNotShowToolBrand": True,
        },
        "assets": asset_rows,
    }


def audit_brand_application(slides: list[dict], brand_kit: dict) -> dict:
    issues = []
    expected = str(brand_kit.get("name", "")).strip()
    for slide in slides:
        actual = str((slide.get("designSystem") or {}).get("brand", {}).get("name", "")).strip()
        if expected and actual != expected:
            issues.append({"position": slide.get("position"), "code": "brand-name-drift"})
    return {"version": "brand-audit-v1", "score": max(0, 100 - len(issues) * 12), "issues": issues}
