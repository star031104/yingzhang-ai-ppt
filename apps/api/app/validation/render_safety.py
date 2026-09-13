"""Shared hard gates for candidate selection, repair and delivery inspection."""

HARD_RENDER_FIELDS = (
    "overflow", "clipping", "textOverflow", "missingAssets", "missingContent",
)


def hard_render_failures(score: dict) -> list[str]:
    failures = [key for key in HARD_RENDER_FIELDS if score.get(key, 0)]
    failures.extend(
        str(issue.get("code", "render-error"))
        for issue in score.get("issues", [])
        if isinstance(issue, dict) and issue.get("severity") == "error"
    )
    return list(dict.fromkeys(failures))


def safe_render_candidate(score: dict) -> bool:
    return (
        not hard_render_failures(score)
        and float(score.get("geometry", 0)) >= 80
        and float(score.get("readability", 0)) >= 78
        and float(score.get("contentFit", score.get("semanticFit", 0))) >= 62
    )
