import json
from pathlib import Path

import pytest
from app.presentation_engine.page_pipeline import render_deck_pages
from app.presentation_engine.page_repair import (
    diagnose,
    page_snapshot,
    plan_patch,
    split_long_bullet,
)

SAFE = {"geometry": 96, "readability": 92, "contentFit": 90, "semanticFit": 90, "overall": 90}


def _write(root: Path, candidates: dict[str, dict], selected: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for stale in root.glob("*"):
        stale.unlink()
    for variant, score in candidates.items():
        (root / f"{variant}.score.json").write_text(json.dumps(score), encoding="utf-8")
        (root / f"{variant}.html").write_text(variant, encoding="utf-8")
        (root / f"{variant}.png").write_bytes(b"png")
    (root / "current.json").write_text(json.dumps({"variant": selected}), encoding="utf-8")


def _overflowing(bullets: int) -> dict:
    return {**SAFE, "geometry": 60, "readability": 70, "textOverflow": 1, "bulletCount": bullets}


def test_split_long_bullet_keeps_qualifiers_on_slide():
    head_tail = split_long_bullet("复核平均耗时从 42 分钟降到 18 分钟，节省的时间主要用于处理异常工单和补充访谈记录" * 1, 30)
    assert head_tail and head_tail[0] == "复核平均耗时从 42 分钟降到 18 分钟"
    # A tail carrying a boundary ("不含", "试点") must never be split off.
    assert split_long_bullet("第四季度收入 1.2 亿元，同比增长 8.4%，不含一次性收入和汇率影响带来的变动部分", 30) is None
    assert split_long_bullet("短句", 30) is None


def test_diagnose_passes_when_any_candidate_is_safe(tmp_path):
    _write(tmp_path, {"cards": _overflowing(6), "content-list": SAFE}, "cards")
    assert diagnose(page_snapshot(tmp_path)) == []
    _write(tmp_path, {"cards": _overflowing(6)}, "cards")
    codes = diagnose(page_snapshot(tmp_path))
    assert "text-overflow" in codes and "dense" in codes


def test_plan_patch_moves_copy_to_notes_and_steers_layouts(tmp_path):
    _write(tmp_path, {"cards": _overflowing(6)}, "cards")
    slide = {
        "id": "s", "position": 3, "role": "content",
        "content": {"title": "标题", "bullets": [f"要点 {index}" for index in range(6)]},
        "layoutPlan": {"candidateOrder": ["cards", "split"], "recommendedVariant": "cards"},
        "visualIntent": {"selectedVariant": "cards"},
    }
    patched, actions = plan_patch(slide, ["text-overflow"], page_snapshot(tmp_path), 1)
    assert patched["content"]["bullets"] == ["要点 0", "要点 1", "要点 2", "要点 3"]
    assert patched["speakerIntent"]["movedFromSlide"] == ["要点 4", "要点 5"]
    assert patched["layoutPlan"]["candidateOrder"][:1] == ["split"]
    assert "evidence-brief" in patched["layoutPlan"]["candidateOrder"]
    assert "selectedVariant" not in patched["visualIntent"]
    assert {item["action"] for item in actions} == {"move-bullets-to-notes", "steer-layouts"}
    assert slide["content"]["bullets"][5] == "要点 5"  # original untouched


def test_human_edited_copy_is_never_trimmed(tmp_path):
    _write(tmp_path, {"cards": _overflowing(6)}, "cards")
    slide = {"id": "s", "position": 2, "role": "content", "contentLocked": True,
             "content": {"title": "t", "bullets": [f"b{index}" for index in range(6)]}}
    patched, actions = plan_patch(slide, ["text-overflow"], page_snapshot(tmp_path), 1)
    assert len(patched["content"]["bullets"]) == 6
    assert [item["action"] for item in actions] == ["steer-layouts"]


class RepairingEngine:
    """Unsafe while a page has more than four bullets; safe afterwards."""

    def __init__(self):
        self.builds = 0

    def run(self, command: str, slides: list[dict], output: Path) -> None:
        if command == "assemble":
            (output / "index.html").write_text("ok", encoding="utf-8")
            return
        self.builds += 1
        slide = slides[0]
        count = len(slide["content"]["bullets"])
        score = SAFE if count <= 4 else _overflowing(count)
        _write(output / "slides" / str(slide["position"]), {"cards": score}, "cards")


@pytest.mark.asyncio
async def test_pipeline_repairs_page_within_round_cap(tmp_path):
    engine = RepairingEngine()
    slide = {"id": "a", "position": 1, "role": "content", "visualIntent": {},
             "content": {"title": "t", "bullets": [f"b{index}" for index in range(7)]}}
    events = []

    async def collect(event):
        events.append(event["status"])

    result = await render_deck_pages([slide], tmp_path / "out", engine, repair_rounds=2, on_event=collect)
    assert result["assembled"] is True
    assert engine.builds == 2
    assert slide["renderRepair"]["final"] == "pass" and slide["renderRepair"]["rounds"] == 1
    assert len(slide["content"]["bullets"]) == 4
    assert "repairing" in events


@pytest.mark.asyncio
async def test_pipeline_stops_at_round_cap(tmp_path):
    class NeverSafe(RepairingEngine):
        def run(self, command, slides, output):
            if command == "assemble":
                (output / "index.html").write_text("ok", encoding="utf-8")
                return
            self.builds += 1
            _write(output / "slides" / str(slides[0]["position"]), {"cards": _overflowing(9)}, "cards")

    engine = NeverSafe()
    slide = {"id": "a", "position": 1, "role": "content", "visualIntent": {},
             "layoutPlan": {"candidateOrder": ["cards"]},
             "content": {"title": "t", "bullets": [f"b{index}" for index in range(7)]}}
    await render_deck_pages([slide], tmp_path / "out", engine, repair_rounds=2)
    assert engine.builds == 3  # initial build + at most two repair rounds
    assert slide["renderRepair"]["final"] == "needs-review"


@pytest.mark.asyncio
async def test_vision_inspector_can_trigger_text_repair(tmp_path):
    engine = RepairingEngine()
    slide = {"id": "a", "position": 1, "role": "content", "visualIntent": {},
             "content": {"title": "t", "bullets": ["复核平均耗时从 42 分钟降到 18 分钟，节省的时间主要用于处理异常工单和补充访谈记录"]}}
    seen = []

    async def inspector(page, snapshot):
        seen.append(snapshot["selectedVariant"])
        return ["awkward-wrap"]

    await render_deck_pages([slide], tmp_path / "out", engine, repair_rounds=2, inspector=inspector)
    assert seen == ["cards"]  # asked once, on the first safe render only
    assert slide["content"]["bullets"] == ["复核平均耗时从 42 分钟降到 18 分钟"]
    assert slide["renderRepair"]["history"][0]["visionIssues"] == ["awkward-wrap"]


@pytest.mark.asyncio
async def test_repair_disabled_by_default(tmp_path):
    engine = RepairingEngine()
    slide = {"id": "a", "position": 1, "role": "content", "visualIntent": {},
             "content": {"title": "t", "bullets": [f"b{index}" for index in range(7)]}}
    await render_deck_pages([slide], tmp_path / "out", engine)
    assert engine.builds == 1 and "renderRepair" not in slide
