import io
import json
import zipfile

import pytest
from app.api.workflow_routes import select_github_skill_subtree, skill_download_urls
from app.skills.manager import install_skill


def bundle(files: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


def test_installs_versioned_data_only_skill(tmp_path):
    data = bundle(
        {
            "skill.json": json.dumps({"id": "clean-style", "version": "1.0.0", "kind": "visual"}),
            "tokens.json": "{}",
        }
    )
    result = install_skill(data, tmp_path)
    assert result["scripts_enabled"] is False
    assert (tmp_path / "clean-style" / "1.0.0" / "tokens.json").exists()


def test_scripts_are_installed_but_disabled_without_authorization(tmp_path):
    data = bundle(
        {
            "skill.json": json.dumps({"id": "scripted", "version": "1", "kind": "workflow"}),
            "run.py": "print('hello')",
        }
    )
    result = install_skill(data, tmp_path)
    assert result["scripts_enabled"] is False
    assert result["script_count"] == 1


def test_skill_md_community_bundle_gets_safe_manifest(tmp_path):
    data = bundle(
        {
            "presentation-skill-main/SKILL.md": "---\nname: presentation-skill\ndescription: Deck QA\n---\n# Skill",
            "presentation-skill-main/VERSION": "0.9.0",
            "presentation-skill-main/scripts/build.js": "console.log('disabled')",
        }
    )
    result = install_skill(data, tmp_path)
    assert result["id"] == "presentation-skill"
    assert result["version"] == "0.9.0"
    assert result["scripts_enabled"] is False
    assert (tmp_path / "presentation-skill" / "0.9.0" / "skill.json").exists()


def test_authorized_forbidden_script_is_rejected(tmp_path):
    data = bundle(
        {
            "skill.json": json.dumps({"id": "scripted", "version": "1", "kind": "workflow"}),
            "run.py": "import subprocess",
        }
    )
    with pytest.raises(ValueError, match="Static scan rejected"):
        install_skill(data, tmp_path, allow_scripts=True)


def test_github_project_link_resolves_to_branch_archives():
    urls = skill_download_urls("https://github.com/example/presentation-skill")
    assert urls[0].endswith("/zip/refs/heads/main")
    assert urls[1].endswith("/zip/refs/heads/master")


def test_github_tree_link_resolves_and_extracts_only_selected_skill():
    source_url = "https://github.com/example/skills/tree/main/skills/pdf"
    assert skill_download_urls(source_url) == [
        "https://codeload.github.com/example/skills/zip/main"
    ]
    data = bundle(
        {
            "skills-main/skills/pdf/SKILL.md": "---\nname: pdf\n---\n# PDF",
            "skills-main/skills/pdf/REFERENCE.md": "reference",
            "skills-main/skills/pptx/SKILL.md": "---\nname: pptx\n---\n# PPTX",
        }
    )
    selected = select_github_skill_subtree(data, source_url)
    with zipfile.ZipFile(io.BytesIO(selected)) as archive:
        assert set(archive.namelist()) == {"SKILL.md", "REFERENCE.md"}


def test_builtin_catalog_contains_only_visual_extensions(client):
    skills = client.get("/api/v1/skills").json()
    ids = {skill["id"] for skill in skills}
    assert {"swiss-grid-pro", "data-consulting", "editorial-story", "nebula-tech", "oriental-minimal", "playful-bento"} <= ids
    assert all(skill["kind"] == "visual" for skill in skills)
