import json
from pathlib import Path
from types import SimpleNamespace

from app.presentation_intelligence.art_director import build_design_system
from app.presentation_intelligence.visual_grammar import GRAMMAR_FIELDS, normalize_visual_grammar

SKILLS = Path(__file__).resolve().parents[1] / "skills" / "visual"


def _skill(name: str) -> SimpleNamespace:
    return SimpleNamespace(path=str(SKILLS / name), id=name, manifest={})


def test_every_builtin_visual_skill_has_a_valid_distinct_grammar():
    fingerprints = set()
    names = sorted(path.name for path in SKILLS.iterdir() if path.is_dir())
    assert {"academic-defense", "finance-research", "gov-briefing"} <= set(names)
    for name in names:
        tokens = json.loads((SKILLS / name / "tokens.json").read_text(encoding="utf-8"))
        grammar, errors = normalize_visual_grammar(tokens)
        assert errors == [], name
        assert all(field in grammar for field in GRAMMAR_FIELDS), name
        fingerprints.add(json.dumps([grammar["typeScale"], grammar["titleStyle"], grammar["decoration"]]))
    assert len(fingerprints) == len(names)


def test_legacy_tokens_keep_the_previous_design_system():
    grammar, errors = normalize_visual_grammar({"palette": {"primary": "#123456"}, "fontFamily": "Microsoft YaHei"})
    assert grammar is None and errors == []
    design = build_design_system("business", [])
    assert "grammar" not in design and "grammarWarnings" not in design
    assert design["typography"]["title"]["size"] == 52
    assert design["grid"] == {"canvas": [1280, 720], "columns": 12, "margin": 68, "gutter": 20}


def test_build_design_system_passes_grammar_through(tmp_path):
    design = build_design_system("business", [_skill("finance-research")])
    grammar = design["grammar"]
    assert grammar["version"] == "visual-grammar-v1"
    assert design["layoutProfile"] == "finance-research"
    assert design["typography"]["title"]["size"] == grammar["typeScale"]["title"] == 36
    assert design["grid"]["margin"] == grammar["grid"]["margin"]["x"]
    assert design["densityBias"] == "compact"
    assert design["chart"]["series"][0] == design["palette"]["deep"]
    assert "icons" in grammar["forbidden"]

    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "tokens.json").write_text(json.dumps({"density": "dense", "typeScale": {"title": 200}}), encoding="utf-8")
    design = build_design_system("business", [SimpleNamespace(path=str(broken), id="broken", manifest={})])
    assert "grammar" not in design
    assert any("density" in warning for warning in design["grammarWarnings"])


def test_forbidden_motifs_are_removed_from_decoration():
    grammar, errors = normalize_visual_grammar({
        "decoration": {"motifs": ["orb", "rule"], "intensity": "bold"}, "forbidden": ["orb"],
    })
    assert errors == []
    assert grammar["decoration"]["motifs"] == ["rule"]
