import asyncio
import json
from pathlib import Path

import pytest
from app.db.models import Job, Project
from app.db.session import SessionLocal
from app.jobs.manager import JobManager


def test_job_event_stream_starts_with_durable_snapshot(client):
    created = client.post("/api/v1/jobs", json={"kind": "event-stream-check"}).json()
    with client.stream("GET", f"/api/v1/jobs/{created['id']}/events") as response:
        assert response.status_code == 200
        payloads = [
            json.loads(line.removeprefix("data: "))
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]

    assert payloads
    assert payloads[0]["job_id"] == created["id"]
    assert payloads[-1]["status"] == "completed"


def test_job_cancel_request_is_persisted(client):
    with SessionLocal() as db:
        job = Job(kind="cancel-check", status="running", checkpoint={"stage": "working"})
        db.add(job)
        db.commit()
        job_id = job.id

    response = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert response.status_code == 202
    assert response.json()["checkpoint"]["cancelRequested"] is True
    with SessionLocal() as db:
        persisted = db.get(Job, job_id)
        assert persisted.checkpoint["cancelRequested"] is True


def test_ready_page_preview_is_served_from_project_artifacts(client):
    project_data = client.post("/api/v1/projects", json={"name": "逐页预览"}).json()
    with SessionLocal() as db:
        project = db.get(Project, project_data["id"])
        candidate_root = Path(project.artifact_path) / "slides" / "rendered" / "slides" / "1"
        candidate_root.mkdir(parents=True, exist_ok=True)
        (candidate_root / "current.json").write_text(
            json.dumps({"variant": "cards"}), encoding="utf-8"
        )
        (candidate_root / "cards.png").write_bytes(b"page-preview")
        job = Job(
            kind="project:generate",
            project_id=project.id,
            status="running",
            checkpoint={
                "pages": [
                    {
                        "slideId": "slide-1",
                        "position": 1,
                        "status": "ready",
                        "artifactRoot": str(candidate_root),
                    }
                ]
            },
        )
        db.add(job)
        db.commit()
        job_id = job.id

    response = client.get(f"/api/v1/jobs/{job_id}/pages/slide-1/preview")
    assert response.status_code == 200
    assert response.content == b"page-preview"


@pytest.mark.asyncio
async def test_resumable_job_is_requeued_from_persisted_workflow_context(client):
    resumed = asyncio.Event()
    manager = JobManager()

    async def runner(snapshot: dict):
        assert snapshot["checkpoint"]["workflow"]["payload"] == {"title": "恢复测试"}
        resumed.set()

    manager.register_runner(lambda kind: kind == "recoverable-test", runner)
    with SessionLocal() as db:
        job = Job(
            kind="recoverable-test",
            status="running",
            progress=0.4,
            checkpoint={
                "stage": "working",
                "workflow": {
                    "version": "durable-generation-v1",
                    "resumable": True,
                    "payload": {"title": "恢复测试"},
                    "resumeCount": 0,
                },
            },
        )
        db.add(job)
        db.commit()
        job_id = job.id

    assert manager.recover_interrupted() == 1
    await asyncio.wait_for(resumed.wait(), timeout=1)
    with SessionLocal() as db:
        recovered = db.get(Job, job_id)
        assert recovered.status == "queued"
        assert recovered.checkpoint["recovered"] is True
        assert recovered.checkpoint["workflow"]["resumeCount"] == 1


def test_slide_revision_conflict_prevents_stale_overwrite(client):
    project = client.post("/api/v1/projects", json={"name": "版本冲突测试"}).json()
    outline = client.post(
        f"/api/v1/projects/{project['id']}/outline",
        json={"title": "版本冲突", "preset": "academic", "slide_count": 6},
    ).json()
    slide_id = outline["slides"][0]["id"]
    slide = client.get(f"/api/v1/projects/{project['id']}/workspace").json()["slides"][0]

    first = client.post(
        f"/api/v1/projects/{project['id']}/slides/{slide_id}/repair",
        json={
            "instruction": "第一次修改",
            "revision": slide["revision"],
            "patch": {"message": "已保存的新结论"},
        },
    )
    assert first.status_code == 200

    stale = client.post(
        f"/api/v1/projects/{project['id']}/slides/{slide_id}/repair",
        json={
            "instruction": "过期页面修改",
            "revision": slide["revision"],
            "patch": {"message": "不应覆盖"},
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "slide_revision_conflict"

    current = client.get(f"/api/v1/projects/{project['id']}/workspace").json()["slides"][0]
    assert current["message"] == "已保存的新结论"
    assert current["revision"] == slide["revision"] + 1
