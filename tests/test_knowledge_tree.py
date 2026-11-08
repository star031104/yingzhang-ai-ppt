from pathlib import Path

from app.documents import parse_source
from app.intelligence.evidence import extract_evidence_graph
from app.intelligence.knowledge_base import build_card, build_knowledge_base
from app.intelligence.retrieval import _chunks, propagate_tree_scores, rank_chunks

ROOT = Path(__file__).resolve().parents[1]


def _source(name="academic-thesis"):
    path = ROOT / "benchmarks" / name / "fixture.md"
    return parse_source(path.name, path.read_bytes(), "text/markdown")


def test_tree_propagation_lifts_children_of_relevant_headings():
    chunks = [
        {"document": "d", "section": "S1", "headingPath": ["实验"], "text": ""},
        {"document": "d", "section": "S2", "headingPath": ["实验", "结果"], "text": ""},
        {"document": "d", "section": "S3", "headingPath": ["背景"], "text": ""},
        {"document": "d", "section": "S4", "headingPath": ["背景", "术语"], "text": ""},
    ]
    scores = propagate_tree_scores(chunks, [1.0, 0.2, 0.0, 0.2])
    assert scores[1] > scores[3]  # same own score, but the parent heading matched
    assert scores[0] > 1.0  # a matching child also lifts its parent
    assert propagate_tree_scores([{"document": "d", "section": "x", "text": ""}], [0.5]) == [0.5]


def test_rank_chunks_keeps_heading_paths():
    ranked = rank_chunks(_chunks([_source()]), "evidence precision")
    assert ranked and all("headingPath" in chunk for chunk in ranked)
    assert any(chunk.get("treeBonus") for chunk in ranked)


def test_knowledge_base_levels_are_traceable_and_bounded():
    source = _source("data-dashboard")
    knowledge = build_knowledge_base([source])
    assert knowledge["version"] == "knowledge-base-v1"
    assert knowledge["stats"]["cardChars"] <= 2400
    document = knowledge["card"]["documents"][0]
    assert document["outline"] and document["headlineMetrics"]
    fact = knowledge["facts"][0]
    assert fact["sourceRef"]["document"] == source["name"]
    assert knowledge["chunks"][0]["section"]
    small = build_card([source], extract_evidence_graph([source]), limit=600)
    import json
    assert len(json.dumps(small, ensure_ascii=False)) <= 600 or len(small["documents"]) == 1


def test_knowledge_api(client):
    project = client.post("/api/v1/projects", json={"name": "知识库"}).json()
    assert client.get(f"/api/v1/projects/{project['id']}/knowledge").status_code == 409
    fixture = ROOT / "benchmarks" / "business-report" / "fixture.md"
    client.post(f"/api/v1/projects/{project['id']}/sources",
                files={"file": ("fixture.md", fixture.read_bytes(), "text/markdown")})
    knowledge = client.get(f"/api/v1/projects/{project['id']}/knowledge").json()
    assert knowledge["stats"]["facts"] > 0 and knowledge["card"]["documents"]
