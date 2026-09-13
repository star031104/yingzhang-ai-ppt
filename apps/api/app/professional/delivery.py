from __future__ import annotations

DELIVERY_PROFILES = {
    "powerpoint-windows": {
        "transitions": {"fade", "push", "wipe"},
        "animation": {"fade"},
        "media": True,
        "svg": True,
    },
    "powerpoint-macos": {
        "transitions": {"fade", "push", "wipe"},
        "animation": {"fade"},
        "media": True,
        "svg": True,
    },
    "wps": {"transitions": {"fade", "push"}, "animation": set(), "media": False, "svg": False},
    "libreoffice": {"transitions": {"fade"}, "animation": set(), "media": False, "svg": True},
}


def audit_delivery_profile(slides: list[dict], profile: str) -> dict:
    capabilities = DELIVERY_PROFILES.get(profile, DELIVERY_PROFILES["powerpoint-windows"])
    issues = []
    for slide in slides:
        position = slide.get("position")
        effects = slide.get("powerPoint") or {}
        transition = str(effects.get("transition", "none"))
        animation = str(effects.get("animation", "none"))
        if transition != "none" and transition not in capabilities["transitions"]:
            issues.append(
                {"position": position, "code": "unsupported-transition", "value": transition}
            )
        if animation != "none" and animation not in capabilities["animation"]:
            issues.append(
                {"position": position, "code": "unsupported-animation", "value": animation}
            )
        for asset in slide.get("assetBindings", []):
            kind = str(asset.get("type", ""))
            if kind in {"licensed-video", "licensed-audio"} and not capabilities["media"]:
                issues.append({"position": position, "code": "unsupported-media", "value": kind})
            if str(asset.get("path", "")).lower().endswith(".svg") and not capabilities["svg"]:
                issues.append({"position": position, "code": "unsupported-svg"})
    return {
        "version": "delivery-audit-v1",
        "profile": profile,
        "score": max(0, 100 - len(issues) * 10),
        "capabilities": {
            **capabilities,
            "transitions": sorted(capabilities["transitions"]),
            "animation": sorted(capabilities["animation"]),
        },
        "issues": issues,
    }
