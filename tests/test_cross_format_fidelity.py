import json
import shutil
import subprocess
from pathlib import Path

import pytest
from app.presentation_engine import service as engine_service
from app.presentation_engine.service import (
    PresentationEngine,
    load_export_report,
    presentation_engine,
)
from app.validation import visual_regression
from app.validation.visual_regression import (
    cross_format_fidelity,
    fidelity_score,
    office_fidelity_report,
    render_pptx_pages,
    selected_candidate_screenshots,
)
from PIL import Image, ImageDraw


def _slide_image(path: Path, offset: int = 0, color: str = "#20284D") -> Path:
    image = Image.new("RGB", (1280, 720), "#F6F7FB")
    draw = ImageDraw.Draw(image)
    draw.rectangle((68 + offset, 120, 600 + offset, 180), fill=color)
    draw.rectangle((68, 240, 1212, 520), outline="#E3E7F0", width=2)
    for row in range(5):
        draw.rectangle((100 + offset, 270 + row * 45, 900 + offset, 290 + row * 45), fill="#182033")
    image.save(path)
    return path


def test_fidelity_score_rewards_identical_layouts_and_flags_drift(tmp_path):
    reference = _slide_image(tmp_path / "html.png")
    same = _slide_image(tmp_path / "same.png")
    shifted = _slide_image(tmp_path / "shifted.png", offset=40)
    recolored = _slide_image(tmp_path / "recolored.png", color="#E23D28")
    assert fidelity_score(reference, same)["score"] == 100
    assert fidelity_score(reference, shifted)["score"] < fidelity_score(reference, same)["score"]
    assert fidelity_score(reference, recolored)["color"] < 1
    report = cross_format_fidelity([reference, reference, None], [same, shifted, same], threshold=99)
    assert report["version"] == "cross-format-fidelity-v1"
    assert report["pages"][0]["flagged"] is False
    assert report["flaggedPages"] == [2, 3]
    assert report["pages"][2]["code"] == "render-missing"
    assert report["passed"] is False
    mismatch = cross_format_fidelity([reference, reference], [same])
    assert mismatch["pages"][-1]["code"] == "page-count-mismatch"


def test_selected_candidate_screenshots_follow_selection(tmp_path):
    root = tmp_path / "rendered"
    page = root / "slides" / "1"
    page.mkdir(parents=True)
    (page / "chart-focus.png").write_bytes(b"png")
    (page / "split.png").write_bytes(b"png")
    (page / "current.json").write_text(json.dumps({"variant": "split"}), encoding="utf-8")
    assert selected_candidate_screenshots(root, [{"position": 1}]) == [page / "split.png"]
    chosen = [{"position": 1, "visualIntent": {"selectedVariant": "chart-focus"}}]
    assert selected_candidate_screenshots(root, chosen) == [page / "chart-focus.png"]
    assert selected_candidate_screenshots(root, [{"position": 2}]) == [None]


def test_fidelity_degrades_gracefully_without_libreoffice(tmp_path, monkeypatch):
    monkeypatch.setattr(visual_regression, "office_executable", lambda: None)
    assert render_pptx_pages(tmp_path / "deck.pptx", tmp_path / "out") is None
    report = office_fidelity_report(tmp_path / "deck.pptx", tmp_path, [], tmp_path / "out")
    assert report["status"] == "unavailable"


def test_engine_passes_scene_root_and_reads_export_report(tmp_path, monkeypatch):
    calls = []

    def fake_run(arguments, **_kwargs):
        calls.append(arguments)
        Path(arguments[4]).with_suffix(".export.json").write_text(
            json.dumps({"mode": "scene", "sceneSlides": 1, "legacySlides": 0}), encoding="utf-8")
        return subprocess.CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr(engine_service.subprocess, "run", fake_run)
    engine = PresentationEngine()
    target = tmp_path / "deck.pptx"
    engine.run("pptx", [{"id": "a", "position": 1}], target, scene_root=tmp_path / "rendered")
    assert calls[0][-1] == str(tmp_path / "rendered")
    assert load_export_report(target)["sceneSlides"] == 1
    engine.run("build", [{"id": "a", "position": 1}], tmp_path / "build", scene_root=tmp_path / "rendered")
    assert calls[1][-1] == str(tmp_path / "build")
    assert load_export_report(tmp_path / "missing.pptx") is None


@pytest.mark.skipif(not (shutil.which("soffice") or shutil.which("libreoffice")), reason="LibreOffice not installed")
def test_scene_driven_pptx_matches_the_html_candidate_in_libreoffice(tmp_path):
    slides = [{
        "id": "metrics", "position": 1, "role": "data", "message": "三项指标说明转化与留存表现",
        "content": {"title": "核心经营指标", "bullets": ["转化率达到12%", "七日留存率为82%", "满意度达到91%"]},
        "visualIntent": {"archetypeCandidates": ["metric-wall"]},
        "designSystem": {"palette": {}, "typography": {"fontFamily": "Microsoft YaHei"}},
    }]
    rendered = tmp_path / "rendered"
    presentation_engine.run("build", slides, rendered)
    current = json.loads((rendered / "slides" / "1" / "current.json").read_text(encoding="utf-8"))
    slides[0]["visualIntent"]["selectedVariant"] = current["variant"]
    target = tmp_path / "deck.pptx"
    presentation_engine.run("pptx", slides, target, scene_root=rendered)
    export = load_export_report(target)
    assert export["slides"][0]["renderer"] == "scene"
    assert export["slides"][0]["sceneSource"] == "stored"
    report = office_fidelity_report(target, rendered, slides, tmp_path / "office")
    assert report["status"] == "measured"
    assert report["pages"][0]["score"] >= 95, report
