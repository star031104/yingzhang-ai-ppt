import asyncio
import copy
from collections.abc import Awaitable
from typing import Any

import pytest
from app.jobs.contracts import JobSnapshot
from app.jobs.local import InMemoryEventBus
from app.jobs.manager import JobManager


class MemoryJobStore:
    def __init__(self, *snapshots: JobSnapshot):
        self.snapshots = {item["id"]: copy.deepcopy(item) for item in snapshots}

    def get(self, job_id: str) -> JobSnapshot | None:
        item = self.snapshots.get(job_id)
        return copy.deepcopy(item) if item else None

    def list_active(self) -> list[JobSnapshot]:
        return [
            copy.deepcopy(item)
            for item in self.snapshots.values()
            if item["status"] in {"queued", "running"}
        ]

    def save(self, snapshot: JobSnapshot) -> JobSnapshot | None:
        if snapshot["id"] not in self.snapshots:
            return None
        self.snapshots[snapshot["id"]] = copy.deepcopy(snapshot)
        return copy.deepcopy(snapshot)


class RecordingExecutor:
    def __init__(self):
        self.job_ids: list[str | None] = []

    def submit(
        self, coroutine: Awaitable[Any], job_id: str | None = None
    ) -> asyncio.Task[Any]:
        self.job_ids.append(job_id)
        return asyncio.create_task(coroutine)


def _job(job_id: str = "job-1") -> JobSnapshot:
    return {
        "id": job_id,
        "project_id": "project-1",
        "kind": "project:generate",
        "status": "running",
        "progress": 0.4,
        "checkpoint": {"stage": "working"},
        "error": None,
    }


@pytest.mark.asyncio
async def test_manager_uses_injected_store_executor_and_event_bus():
    store = MemoryJobStore(_job())
    executor = RecordingExecutor()
    bus = InMemoryEventBus(heartbeat_seconds=0.01)
    manager = JobManager(store=store, executor=executor, event_bus=bus)
    queue = manager.open_subscription("job-1")

    cancelled = await manager.request_cancel("job-1")
    event = await manager.next_event(queue)

    assert cancelled["checkpoint"]["cancelRequested"] is True
    assert store.get("job-1")["checkpoint"]["cancelRequested"] is True
    assert event["type"] == "cancel_requested"

    completed = asyncio.Event()

    async def work() -> None:
        completed.set()

    task = manager.spawn(work(), job_id="job-1")
    await task
    assert completed.is_set()
    assert executor.job_ids == ["job-1"]


@pytest.mark.asyncio
async def test_in_memory_event_bus_bounds_slow_subscribers():
    bus = InMemoryEventBus()
    queue = bus.open_subscription("job-1")

    for sequence in range(40):
        await bus.publish("job-1", {"sequence": sequence})

    assert queue.qsize() == 32
    assert (await queue.get())["sequence"] == 8
