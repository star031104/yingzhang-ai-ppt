from app.documents import parse_source
from app.presentation_intelligence.planner import plan_deck
from app.validation.quality import validate_deck


def test_academic_benchmark_quality_gate():
    data = Path("benchmarks/academic-thesis/fixture.md").read_bytes()
    source = parse_source("fixture.md", data, "text/markdown")
    plan = plan_deck([source], "Efficient evidence systems", "academic", 8)
    report = validate_deck(plan["slides"], [source])
    assert report["contentCoverage"] >= 0.9
    assert report["blockingErrors"] == 0
    assert plan["evidence"]["facts"]


from pathlib import Path
