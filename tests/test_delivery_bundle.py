"""Verify that large-media delivery contains its rendered page and source media."""

import hashlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

from app.api.delivery_routes import create_html_bundle
from app.validation.render_freshness import render_input


def test_large_media_html_bundle_uses_portable_paths(tmp_path: Path):
    media = tmp_path / "素材 演示.mp4"
    with media.open("wb") as stream:
        stream.truncate(50 * 1024 * 1024 + 1)
    with media.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()

    slide = {
        "id": "media-slide",
        "position": 1,
        "role": "content",
        "message": "离线交付",
        "content": {"title": "媒体演示", "bullets": ["保留媒体文件"]},
        "assetBindings": [{"type": "licensed-video", "path": str(media)}],
        "visualIntent": {"selectedVariant": "media-focus"},
    }
    stamp = {"version": 2, "input": render_input(slide), "assets": {str(media): digest}}
    root = tmp_path / "project"
    rendered = root / "slides" / "rendered"
    page = rendered / "slides" / "1"
    page.mkdir(parents=True)
    (page / "media-focus.html").write_text(
        f'<div class="slide"><video src="{media.as_uri()}"></video></div>',
        encoding="utf-8",
    )
    (page / "media-focus.scene.json").write_text(json.dumps({"nodes": []}), encoding="utf-8")
    (page / "media-focus.score.json").write_text(
        json.dumps({"overall": 90, "renderStamp": stamp}), encoding="utf-8"
    )
    (page / "current.json").write_text(json.dumps({"variant": "media-focus"}), encoding="utf-8")
    target = root / "exports" / "versions" / "large-media.zip"

    create_html_bundle(SimpleNamespace(artifact_path=str(root)), [slide], target)

    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
        page_html = archive.read("presentation.html").decode("utf-8")
        assert len(names) == 2
        assert names[1].startswith("assets/") and names[1].endswith(".mp4")
        assert names[1] in page_html
        assert "file:" not in page_html
        assert archive.getinfo(names[1]).file_size == media.stat().st_size
    assert not (root / "exports" / "presentation.html").exists()
    assert (root / "exports" / "presentation-html.zip").read_bytes() == target.read_bytes()
