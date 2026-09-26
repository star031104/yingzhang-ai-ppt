from pathlib import Path

import pytest
from app.documents import parse_source
from app.presentation_intelligence.planner import plan_deck
from app.validation.quality import validate_deck

FAMILY_CASES = [
    ("academic-thesis/fixture.md", "academic"),
    ("business-report/fixture.md", "business"),
    ("product-launch/fixture.md", "product"),
    ("data-dashboard/fixture.md", "data"),
]


def test_academic_benchmark_quality_gate():
    data = Path("benchmarks/academic-thesis/fixture.md").read_bytes()
    source = parse_source("fixture.md", data, "text/markdown")
    plan = plan_deck([source], "Efficient evidence systems", "academic", 8)
    report = validate_deck(plan["slides"], [source])
    assert report["contentCoverage"] >= 0.9
    assert report["blockingErrors"] == 0
    assert plan["evidence"]["facts"]


@pytest.mark.parametrize("relative_path,preset", FAMILY_CASES)
def test_benchmark_families_preserve_evidence_contract(relative_path, preset):
    path = Path("benchmarks") / relative_path
    source = parse_source(path.name, path.read_bytes(), "text/markdown")
    plan = plan_deck([source], path.parent.name, preset, 8)
    report = validate_deck(plan["slides"], [source])
    source_ids = {section["id"] for section in source["sections"]}

    assert len(plan["slides"]) == 8
    assert plan["evidence"]["facts"]
    assert report["contentCoverage"] >= 0.9
    assert all(slide.get("content", {}).get("title") for slide in plan["slides"])
    assert all(
        ref["section"] in source_ids
        for slide in plan["slides"]
        for ref in slide.get("sourceRefs", [])
    )


def test_data_benchmark_covers_distinct_metrics_and_units():
    path = Path("benchmarks/data-dashboard/fixture.md")
    source = parse_source(path.name, path.read_bytes(), "text/markdown")
    plan = plan_deck([source], "data-dashboard", "data", 8)
    fact_text = " ".join(item["claim"] for item in plan["evidence"]["facts"])

    assert "12%" in fact_text
    assert "78%" in fact_text
    assert "91%" in fact_text
