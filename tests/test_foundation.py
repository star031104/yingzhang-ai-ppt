from pathlib import Path

from app.api.workflow_routes import safe_upload_name


def test_health(client):
    health = client.get("/api/v1/health").json()
    assert health["status"] == "ok" and health["phase"] == 1
    # Launchers match this against SHA-256 of the lower-cased project root.
    import hashlib
    from pathlib import Path
    root = str(Path(__file__).resolve().parents[1]).lower()
    assert health["instance"] == hashlib.sha256(root.encode("utf-8")).hexdigest().upper()


def test_project_creates_recoverable_artifacts(client):
    response = client.post("/api/v1/projects", json={"name": "Thesis defense"})
    assert response.status_code == 201
    root = Path(response.json()["artifact_path"])
    assert (root / "project.json").exists()
    assert all((root / x).is_dir() for x in ("analysis", "plan", "slides", "validation", "exports"))


def test_job_completes(client):
    import time

    created = client.post("/api/v1/jobs", json={"kind": "foundation_check"}).json()
    for _ in range(20):
        job = client.get(f"/api/v1/jobs/{created['id']}").json()
        if job["status"] == "completed":
            break
        time.sleep(0.02)
    assert job["progress"] == 1


def test_windows_upload_name_decodes_and_removes_invalid_path_characters():
    encoded = "=?utf-8?B?MDFf5q+V5Lia562U6L6p5rWL6K+V5p2Q5paZLm1k?="
    assert safe_upload_name(encoded) == "01_毕业答辩测试材料.md"
    assert safe_upload_name("bad?:name.md") == "bad__name.md"
