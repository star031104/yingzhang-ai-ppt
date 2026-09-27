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
