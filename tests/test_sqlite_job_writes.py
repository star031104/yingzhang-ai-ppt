import asyncio
import sqlite3
import threading
import time

import pytest
from app.db.models import Job
from app.db.session import SessionLocal, engine
from app.jobs import sqlite_writes
from app.jobs.local import SQLiteJobStore
from app.jobs.manager import JobManager
from app.jobs.progress import set_job_stage
from sqlalchemy.exc import OperationalError


def _database_file() -> str:
    return engine.url.database


def _create_job(client) -> str:
    project = client.post("/api/v1/projects", json={"name": "并发写入"}).json()
    with SessionLocal() as db:
        job = Job(project_id=project["id"], kind="outline", status="running", checkpoint={})
        db.add(job)
        db.commit()
        return job.id


def _hold_write_lock(seconds: float, started: threading.Event) -> None:
    connection = sqlite3.connect(_database_file(), timeout=30)
    try:
        connection.execute("BEGIN IMMEDIATE")
        started.set()
        time.sleep(seconds)
        connection.rollback()
    finally:
        connection.close()


def test_sqlite_connection_pragmas_favour_concurrent_progress_writes():
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar().lower() == "wal"
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 15000
        # 1 == NORMAL
        assert connection.exec_driver_sql("PRAGMA synchronous").scalar() == 1


def test_lock_errors_are_recognised_without_matching_other_failures():
    locked = OperationalError("UPDATE jobs SET progress=?", {}, sqlite3.OperationalError("database is locked"))
    assert sqlite_writes.is_sqlite_lock_error(locked)
    assert sqlite_writes.is_sqlite_lock_error(sqlite3.OperationalError("database table is locked"))
    assert not sqlite_writes.is_sqlite_lock_error(OperationalError("x", {}, sqlite3.OperationalError("no such table")))
    assert not sqlite_writes.is_sqlite_lock_error(RuntimeError("database is locked"))
    assert sqlite_writes.backoff_delay(0) == pytest.approx(0.05)
    assert sqlite_writes.backoff_delay(20) == sqlite_writes.MAX_DELAY_SECONDS


def test_job_write_retries_transient_lock_then_succeeds(client, monkeypatch):
    job_id = _create_job(client)
    monkeypatch.setattr(sqlite_writes, "backoff_delay", lambda _attempt: 0)
    calls = []

    def write(db):
        calls.append(True)
        if len(calls) < 3:
            raise OperationalError("UPDATE jobs", {}, sqlite3.OperationalError("database is locked"))
        job = db.get(Job, job_id)
        job.progress = 0.5
        db.commit()
        return job.progress

    assert sqlite_writes.run_job_write(write) == 0.5
    assert len(calls) == 3
    with pytest.raises(OperationalError):
        sqlite_writes.run_job_write(
            lambda _db: (_ for _ in ()).throw(
                OperationalError("x", {}, sqlite3.OperationalError("database is locked"))
            ),
            attempts=2,
        )


def test_async_stage_write_survives_writer_holding_lock_beyond_attempt_timeout(client, monkeypatch):
    job_id = _create_job(client)
    monkeypatch.setattr(sqlite_writes, "ASYNC_ATTEMPT_BUSY_TIMEOUT_MS", 200)
    started = threading.Event()
    holder = threading.Thread(target=_hold_write_lock, args=(0.8, started))
    holder.start()
    assert started.wait(5)
    manager = JobManager()

    async def scenario():
        ticks = 0

        async def heartbeat():
            nonlocal ticks
            while True:
                ticks += 1
                await asyncio.sleep(0.05)

        beat = asyncio.create_task(heartbeat())
        await set_job_stage(job_id, 0.42, "planning", "正在规划", manager)
        beat.cancel()
        return ticks

    ticks = asyncio.run(scenario())
    holder.join()
    # The event loop kept running between short busy attempts.
    assert ticks >= 2
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        assert job.progress == pytest.approx(0.42)
        assert job.checkpoint["stage"] == "planning"
    with engine.connect() as connection:
        # The shortened timeout never leaks back into the connection pool.
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 15000


def test_concurrent_job_store_writers_do_not_fail(client):
    job_id = _create_job(client)
    store = SQLiteJobStore()
    errors: list[BaseException] = []

    def writer(offset: int) -> None:
        try:
            for step in range(15):
                snapshot = store.get(job_id)
                snapshot["progress"] = (offset * 100 + step) / 10000
                snapshot["checkpoint"] = {**snapshot["checkpoint"], f"w{offset}": step}
                store.save(snapshot)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    started = threading.Event()
    holder = threading.Thread(target=_hold_write_lock, args=(0.3, started))
    holder.start()
    started.wait(5)
    threads = [threading.Thread(target=writer, args=(index,)) for index in range(6)]
    for thread in threads:
        thread.start()

    async def async_writer():
        for step in range(10):
            await set_job_stage(job_id, 0.5, "working", f"进度 {step}", JobManager())

    asyncio.run(async_writer())
    for thread in threads:
        thread.join()
    holder.join()
    assert errors == []
    snapshot = store.get(job_id)
    assert snapshot["status"] == "running"
