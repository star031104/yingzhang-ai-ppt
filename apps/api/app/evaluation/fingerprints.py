import hashlib
import json
from pathlib import Path


def export_source_fingerprint(slides: list[dict], reference: dict | None = None) -> str:
    assets = {}
    paths = sorted({
        str(path)
        for slide in slides
        for path in (
            [item.get("path") for item in (slide.get("assetBindings") or [])]
            + [((slide.get("designSystem") or {}).get("brand") or {}).get("logoPath")]
        )
        if path
    })
    for name in paths:
        digest = hashlib.sha256()
        try:
            with Path(name).open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            assets[name] = digest.hexdigest()
        except OSError:
            assets[name] = None
    payload = json.dumps(
        {"slides": slides, "reference": reference, "assets": assets},
        sort_keys=True,
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
