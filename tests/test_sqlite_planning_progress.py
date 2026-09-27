import asyncio

from app.db.models import Job
from app.db.session import SessionLocal, engine
from app.jobs.progress import friendly_job_error


def test_sqlite_connections_wait_for_brief_writes_without_holding_model_calls():
    with engine.connect() as db:
        assert db.exec_driver_sql("PRAGMA journal_mode").scalar().lower() == "wal"
        assert db.exec_driver_sql("PRAGMA busy_timeout").scalar() == 30000


def test_database_lock_error_is_actionable_without_exposing_sql():
    message = friendly_job_error(
        RuntimeError("(sqlite3.OperationalError) database is locked [SQL: UPDATE jobs SET progress=?]")
    )
    assert "重新发起" in message
    assert "UPDATE jobs" not in message


def test_planning_does_not_lock_progress_writes_while_awaiting_model(client, monkeypatch):
    project = client.post("/api/v1/projects", json={"name": "并发规划"}).json()
    writes = []

    async def fake_enhance(plan, _sources, _title, _preset, _instructions, _skills, _db, _brief):
        def write_progress():
            with SessionLocal() as progress_db:
                progress_db.add(Job(project_id=project["id"], kind="progress-probe", status="running"))
                progress_db.commit()
                writes.append(True)

        await asyncio.wait_for(asyncio.to_thread(write_progress), timeout=2)
        return plan, {"returnedSlides": len(plan["slides"])}

    monkeypatch.setattr(
        "app.api.workflow_routes.enhance_plan_with_routed_model", fake_enhance
    )
    response = client.post(
        f"/api/v1/projects/{project['id']}/outline",
        json={"title": "并发规划", "preset": "academic", "slide_count": 6},
    )
    assert response.status_code == 200, response.text
    assert writes == [True]


def test_failed_full_job_keeps_options_for_retry_without_reupload(client):
    project = client.post("/api/v1/projects", json={"name": "已有材料"}).json()
    with SessionLocal() as db:
        db.add(Job(
            project_id=project["id"], kind="full", status="failed",
            checkpoint={"workflow": {"payload": {
                "title": "毕业答辩", "instructions": "突出研究结果", "preset": "academic",
                "slide_count": 15, "skill_ids": [], "image_mode": "off",
                "audience": "答辩委员会", "tone": "formal",
            }}},
        ))
        db.commit()
    response = client.get(f"/api/v1/projects/{project['id']}/workspace")
    assert response.status_code == 200
    options = response.json()["planOptions"]
    assert options["title"] == "毕业答辩"
    assert options["slideCount"] == 15
    assert options["professionalBrief"]["audience"] == "答辩委员会"
