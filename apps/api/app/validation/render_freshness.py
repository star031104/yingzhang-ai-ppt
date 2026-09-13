"""Match checked previews to current content and actual local asset bytes."""
import copy
import hashlib
from pathlib import Path


def render_input(slide: dict) -> dict:
    fields = ("id", "position", "role", "message", "content", "sourceRefs", "assetBindings", "designSystem", "layoutPlan")
    value = {key: copy.deepcopy(slide.get(key)) for key in fields}
    value["visualIntent"] = {
        key: copy.deepcopy(item) for key, item in (slide.get("visualIntent") or {}).items()
        if key not in {"selectedVariant", "variantSelectionSource", "criticIssues"}
    }
    return value


def matches_render_stamp(stamp: dict | None, slide: dict, digest_cache: dict | None = None) -> bool:
    if not isinstance(stamp, dict) or stamp.get("version") != 2 or stamp.get("input") != render_input(slide):
        return False
    cache = digest_cache if digest_cache is not None else {}
    paths = [asset.get("path") for asset in slide.get("assetBindings", [])]
    paths.append(((slide.get("designSystem") or {}).get("brand") or {}).get("logoPath"))
    assets = {}
    for name in filter(None, paths):
        if name not in cache:
            try:
                with Path(name).open("rb") as stream:
                    cache[name] = hashlib.file_digest(stream, "sha256").hexdigest()
            except OSError:
                cache[name] = None
        assets[name] = cache[name]
    return stamp.get("assets") == assets
