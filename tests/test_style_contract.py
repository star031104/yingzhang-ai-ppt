import json
from pathlib import Path

from app.presentation_engine.page_pipeline import select_deck_variants
from app.presentation_intelligence.art_director import build_design_system
from app.presentation_intelligence.style_contract import (
    build_style_contract,
    continuity_score,
    style_summary,
)
from PIL import Image

SAFE = {"geometry": 96, "readability": 92, "hierarchy": 90, "whitespace": 88, "alignment": 90,
        "semanticFit": 90, "contentFit": 90, "visualEvidence": 86, "planningFit": 90,
        "styleConsistency": 96, "deckRhythm": 90, "overall": 90}


def _png(path: Path, shade: int) -> None:
    Image.new("RGB", (1280, 720), (shade, shade, shade)).save(path)


def test_contract_is_derived_once_from_design_system():
    design = build_design_system("academic", [], {"tone": "formal"})
    contract = build_style_contract(design, "academic", {"tone": "formal"})
    assert contract["palette"]["primary"] == design["palette"]["primary"]
    assert contract["maxContentDarkArea"] <= 0.34 and contract["density"] in {"compact", "balanced", "airy"}


def test_style_summary_measures_luminance(tmp_path):
    _png(tmp_path / "dark.png", 20)
    summary = style_summary(tmp_path / "dark.png", {"occupied": 0.4, "variantFamily": "cards"})
    assert summary["darkArea"] == 1.0 and summary["luminance"] < 0.1


def test_continuity_penalizes_dark_content_pages_and_jumps():
    contract = build_style_contract(build_design_system("business", [], {}), "business", {})
    light = {"occupied": 0.42, "luminance": 0.93, "darkArea": 0.05}
    dark = {"occupied": 0.42, "luminance": 0.15, "darkArea": 0.9}
    assert continuity_score(light, {**light, "role": "data"}, contract, "data")[0] == 100
    score, reasons = continuity_score(dark, {**light, "role": "data"}, contract, "data")
    assert score < 80 and "content-page-dark-surface" in reasons and "luminance-jump" in reasons
    # Navigation pages may be dark.
    assert continuity_score(dark, {**light, "role": "data"}, contract, "section")[0] == 100
    # Decks without a contract are unaffected.
    assert continuity_score(dark, None, None, "data") == (100, [])


def _page(root: Path, variants: dict[str, int], current: str, contract: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for variant, shade in variants.items():
        (root / f"{variant}.score.json").write_text(json.dumps({**SAFE, "occupied": 0.42}), encoding="utf-8")
        _png(root / f"{variant}.png", shade)
    (root / "current.json").write_text(json.dumps({"variant": current, "designSystem": {"styleContract": contract}}), encoding="utf-8")


def test_deck_selection_swaps_to_smoother_candidate(tmp_path):
    contract = build_style_contract(build_design_system("business", [], {}), "business", {})
    output = tmp_path / "rendered"
    slides = [
        {"id": "a", "position": 1, "role": "data", "visualIntent": {"selectedVariant": "cards"},
         "designSystem": {"styleContract": contract}},
        {"id": "b", "position": 2, "role": "data", "visualIntent": {"selectedVariant": "metric-wall"},
         "designSystem": {"styleContract": contract}},
    ]
    _page(output / "slides" / "1", {"cards": 245}, "cards", contract)
    _page(output / "slides" / "2", {"metric-wall": 25, "chart-focus": 240}, "metric-wall", contract)
    select_deck_variants(slides, output)
    assert slides[1]["visualIntent"]["selectedVariant"] == "chart-focus"
    current = json.loads((output / "slides" / "2" / "current.json").read_text(encoding="utf-8"))
    assert current["scoreDetail"]["styleSwapFrom"] == "metric-wall"


def test_user_selection_is_never_swapped(tmp_path):
    contract = build_style_contract(build_design_system("business", [], {}), "business", {})
    output = tmp_path / "rendered"
    slides = [
        {"id": "a", "position": 1, "role": "data", "visualIntent": {"selectedVariant": "cards"}, "designSystem": {"styleContract": contract}},
        {"id": "b", "position": 2, "role": "data", "designSystem": {"styleContract": contract},
         "visualIntent": {"selectedVariant": "metric-wall", "variantSelectionSource": "user"}},
    ]
    _page(output / "slides" / "1", {"cards": 245}, "cards", contract)
    _page(output / "slides" / "2", {"metric-wall": 25, "chart-focus": 240}, "metric-wall", contract)
    select_deck_variants(slides, output)
    assert slides[1]["visualIntent"]["selectedVariant"] == "metric-wall"
