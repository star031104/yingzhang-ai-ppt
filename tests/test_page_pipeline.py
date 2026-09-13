import json
import threading
import time
from pathlib import Path

import pytest
from app.presentation_engine.page_pipeline import render_deck_pages, select_deck_variants


def _score(value: int = 90) -> dict:
    return {
        "geometry": value,
        "readability": value,
        "hierarchy": value,
        "whitespace": value,
        "alignment": value,
        "semanticFit": value,
        "contentFit": value,
        "visualEvidence": value,
        "planningFit": value,
        "styleConsistency": value,
        "deckRhythm": value,
        "overflow": 0,
        "overall": value,
    }


def _write_candidate(root: Path, variant: str = "cards") -> None:
    root.mkdir(parents=True, exist_ok=True)
    score = _score()
    (root / f"{variant}.html").write_text(f"<section>{variant}</section>", encoding="utf-8")
    (root / f"{variant}.png").write_bytes(b"png")
    (root / f"{variant}.scene.json").write_text("{}", encoding="utf-8")
    (root / f"{variant}.score.json").write_text(json.dumps(score), encoding="utf-8")
    (root / "current.json").write_text(
        json.dumps({"variant": variant, "score": score["overall"], "scoreDetail": score}),
        encoding="utf-8",
    )


class FakeEngine:
    def __init__(self, fail_positions: set[int] | None = None):
        self.fail_positions = fail_positions or set()
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()
        self.assembled = False

    def run(self, command: str, slides: list[dict], output: Path) -> None:
        if command == "assemble":
            self.assembled = True
            (output / "index.html").write_text("assembled", encoding="utf-8")
            return
        slide = slides[0]
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.02)
            if int(slide["position"]) in self.fail_positions:
                raise RuntimeError(f"slide {slide['position']} failed")
            _write_candidate(output / "slides" / str(slide["position"]))
        finally:
            with self.lock:
                self.active -= 1


def _slides(count: int = 3) -> list[dict]:
    return [
        {"id": f"slide-{position}", "position": position, "visualIntent": {}}
        for position in range(1, count + 1)
    ]


@pytest.mark.asyncio
async def test_page_pipeline_renders_concurrently_and_assembles(tmp_path):
    engine = FakeEngine()
    events: list[dict] = []

    async def collect(event: dict) -> None:
        events.append(event)

    result = await render_deck_pages(
        _slides(4), tmp_path / "rendered", engine, concurrency=2, on_event=collect
    )

    assert result["assembled"] is True
    assert result["readySlides"] == 4
    assert engine.assembled is True
    assert engine.max_active == 2
    assert (tmp_path / "rendered" / "index.html").is_file()
    assert sum(event["status"] == "ready" for event in events) == 4


@pytest.mark.asyncio
async def test_page_pipeline_isolates_failure_and_promotes_healthy_pages(tmp_path):
    engine = FakeEngine({2})
    result = await render_deck_pages(
        _slides(3), tmp_path / "rendered", engine, concurrency=2
    )

    assert result["assembled"] is False
    assert result["readySlides"] == 2
    assert [item["position"] for item in result["failedPages"]] == [2]
    assert engine.assembled is False
    assert (tmp_path / "rendered" / "slides" / "1" / "current.json").is_file()
    assert not (tmp_path / "rendered" / "slides" / "2" / "current.json").exists()
    assert (tmp_path / "rendered" / "slides" / "3" / "current.json").is_file()


def test_deck_selection_penalizes_repeated_variant_families(tmp_path):
    slides = _slides(2)
    output = tmp_path / "rendered"
    for slide in slides:
        root = output / "slides" / str(slide["position"])
        _write_candidate(root, "cards")
        _write_candidate(root, "split")

    selections = select_deck_variants(slides, output)

    assert [item["variant"] for item in selections] == ["cards", "split"]
