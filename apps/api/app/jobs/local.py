from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable
from typing import Any

from app.db.models import Job
from app.db.session import SessionLocal
from app.jobs.contracts import JobSnapshot
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect


def job_snapshot(job: Job) -> JobSnapshot:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "kind": job.kind,
        "status": job.status,
        "progress": float(job.progress),
        "checkpoint": dict(job.checkpoint or {}),
        "error": job.error,
    }


class SQLiteJobStore:
    """Single-node durable store; replaceable by a PostgreSQL implementation."""

    def get(self, job_id: str) -> JobSnapshot | None:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            return job_snapshot(job) if job else None

    def list_active(self) -> list[JobSnapshot]:
        with SessionLocal() as db:
            jobs = db.scalars(select(Job).where(Job.status.in_({"running", "queued"}))).all()
            return [job_snapshot(job) for job in jobs]

    def save(self, snapshot: JobSnapshot) -> JobSnapshot | None:
        with SessionLocal() as db:
            job = db.get(Job, snapshot["id"])
            if not job:
                return None
            job.status = snapshot["status"]
            job.progress = snapshot["progress"]
            job.checkpoint = dict(snapshot["checkpoint"])
            job.error = snapshot["error"]
            db.commit()
            return job_snapshot(job)


class AsyncioJobExecutor:
    """In-process executor for local use and deterministic tests."""

    def __init__(self) -> None:
        self.tasks: set[asyncio.Task[Any]] = set()
        self.tasks_by_job: dict[str, asyncio.Task[Any]] = {}

    def submit(
        self, coroutine: Awaitable[Any], job_id: str | None = None
    ) -> asyncio.Task[Any]:
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        if job_id:
            self.tasks_by_job[job_id] = task

        def cleanup(completed: asyncio.Task[Any]) -> None:
            self.tasks.discard(completed)
            if job_id and self.tasks_by_job.get(job_id) is completed:
                self.tasks_by_job.pop(job_id, None)

        task.add_done_callback(cleanup)
        return task


class InMemoryEventBus:
    """Best-effort live fan-out; clients recover truth from the durable snapshot."""

    def __init__(self, heartbeat_seconds: float = 15) -> None:
        self.heartbeat_seconds = heartbeat_seconds
        self.connections: dict[str, set[Any]] = defaultdict(set)
        self.subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    async def connect(self, job_id: str, websocket: Any) -> None:
        await websocket.accept()
        self.connections[job_id].add(websocket)

    def disconnect(self, job_id: str, websocket: Any) -> None:
        self.connections[job_id].discard(websocket)

    def open_subscription(self, job_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=32)
        self.subscribers[job_id].add(queue)
        return queue

    def close_subscription(
        self, job_id: str, queue: asyncio.Queue[dict[str, Any]]
    ) -> None:
        self.subscribers[job_id].discard(queue)
        if not self.subscribers[job_id]:
            self.subscribers.pop(job_id, None)

    async def next_event(
        self, queue: asyncio.Queue[dict[str, Any]]
    ) -> dict[str, Any] | None:
        try:
            return await asyncio.wait_for(queue.get(), timeout=self.heartbeat_seconds)
        except TimeoutError:
            return None

    async def subscribe(self, job_id: str) -> AsyncIterator[dict[str, Any] | None]:
        queue = self.open_subscription(job_id)
        try:
            while True:
                yield await self.next_event(queue)
        finally:
            self.close_subscription(job_id, queue)

    async def publish(self, job_id: str, payload: dict[str, Any]) -> None:
        payload = {**payload, "job_id": job_id}
        stale = []
        for websocket in self.connections[job_id]:
            try:
                await websocket.send_json(payload)
            except (RuntimeError, WebSocketDisconnect):
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(job_id, websocket)

        for queue in tuple(self.subscribers.get(job_id, ())):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(payload)
