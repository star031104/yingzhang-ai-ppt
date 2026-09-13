from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from app.jobs.contracts import EventBus, JobExecutor, JobSnapshot, JobStore
from app.jobs.local import AsyncioJobExecutor, InMemoryEventBus, SQLiteJobStore

TERMINAL_JOB_STATUSES = {"completed", "failed", "cancelled"}
RunnerFactory = Callable[[dict[str, Any]], Awaitable[None]]


class JobCancelled(RuntimeError):
    """Raised at a safe workflow boundary after cooperative cancellation."""


class JobManager:
    """Durable job coordination with live WebSocket and SSE fan-out.

    SQLite remains the source of truth. In-memory tasks and connections are only
    execution/transport details, so reconnecting clients can always recover from
    the persisted job snapshot.
    """

    def __init__(
        self,
        store: JobStore | None = None,
        executor: JobExecutor | None = None,
        event_bus: EventBus | None = None,
    ):
        self.store = store or SQLiteJobStore()
        self.executor = executor or AsyncioJobExecutor()
        self.event_bus = event_bus or InMemoryEventBus()
        self.runners: list[tuple[Callable[[str], bool], RunnerFactory]] = []

    def register_runner(
        self,
        matches: Callable[[str], bool],
        factory: RunnerFactory,
    ) -> None:
        """Register how a persisted job kind is reconstructed after restart."""
        self.runners.append((matches, factory))

    def _runner_for(self, kind: str) -> RunnerFactory | None:
        return next((factory for matches, factory in self.runners if matches(kind)), None)

    def recover_interrupted(self) -> int:
        """Requeue resumable jobs instead of turning every restart into failure."""
        resumable: list[tuple[JobSnapshot, RunnerFactory]] = []
        for snapshot in self.store.list_active():
            runner = self._runner_for(snapshot["kind"])
            checkpoint = dict(snapshot["checkpoint"])
            workflow = dict(checkpoint.get("workflow") or {})
            if not runner or not workflow.get("resumable"):
                snapshot["status"] = "failed"
                snapshot["error"] = "服务在任务执行期间重新启动，任务缺少可恢复上下文"
                checkpoint.update(
                    {
                        "recovered": False,
                        "stage": "failed",
                        "label": "服务已重新启动，此任务需要重新发起",
                    }
                )
                snapshot["checkpoint"] = checkpoint
                self.store.save(snapshot)
                continue

            workflow["resumeCount"] = int(workflow.get("resumeCount") or 0) + 1
            workflow["lastResumedAt"] = datetime.now(UTC).isoformat()
            checkpoint.update(
                {
                    "recovered": True,
                    "stage": "queued",
                    "label": "服务已恢复，正在从持久化任务重新执行",
                    "workflow": workflow,
                }
            )
            snapshot["status"] = "queued"
            snapshot["error"] = None
            snapshot["checkpoint"] = checkpoint
            persisted = self.store.save(snapshot)
            if persisted:
                resumable.append((persisted, runner))

        for snapshot, runner in resumable:
            self.spawn(runner(snapshot), job_id=snapshot["id"])
        return len(resumable)

    def spawn(self, coroutine: Awaitable[Any], job_id: str | None = None):
        return self.executor.submit(coroutine, job_id)

    async def connect(self, job_id, ws):
        await self.event_bus.connect(job_id, ws)

    def disconnect(self, job_id, ws):
        self.event_bus.disconnect(job_id, ws)

    def open_subscription(self, job_id: str) -> asyncio.Queue:
        return self.event_bus.open_subscription(job_id)

    def close_subscription(self, job_id: str, queue: asyncio.Queue) -> None:
        self.event_bus.close_subscription(job_id, queue)

    async def next_event(self, queue: asyncio.Queue) -> dict | None:
        return await self.event_bus.next_event(queue)

    async def subscribe(self, job_id: str) -> AsyncIterator[dict | None]:
        """Yield live events; ``None`` is a transport heartbeat."""
        async for event in self.event_bus.subscribe(job_id):
            yield event

    async def publish(self, job_id, payload):
        snapshot = self.store.get(job_id)
        event = {**snapshot, **payload} if snapshot else payload
        await self.event_bus.publish(job_id, event)

    def cancellation_requested(self, job_id: str) -> bool:
        snapshot = self.store.get(job_id)
        return bool(snapshot and snapshot["checkpoint"].get("cancelRequested"))

    def ensure_active(self, job_id: str) -> None:
        if self.cancellation_requested(job_id):
            raise JobCancelled("任务已由用户取消")

    async def request_cancel(self, job_id: str) -> dict[str, Any] | None:
        snapshot = self.store.get(job_id)
        if not snapshot:
            return None
        if snapshot["status"] in TERMINAL_JOB_STATUSES:
            return snapshot
        checkpoint = dict(snapshot["checkpoint"])
        checkpoint.update(
            {
                "cancelRequested": True,
                "label": "已请求取消，将在当前安全步骤完成后停止",
                "cancelRequestedAt": datetime.now(UTC).isoformat(),
            }
        )
        snapshot["checkpoint"] = checkpoint
        snapshot = self.store.save(snapshot)
        if not snapshot:
            return None
        await self.publish(job_id, {**snapshot, "type": "cancel_requested"})
        return snapshot

    async def run_demo(self, job_id):
        for progress in (0.1, 0.5, 1.0):
            await asyncio.sleep(0.01)
            status = "completed" if progress == 1 else "running"
            snapshot = self.store.get(job_id)
            if not snapshot:
                return
            snapshot["status"] = status
            snapshot["progress"] = progress
            snapshot["checkpoint"] = {"progress": progress}
            self.store.save(snapshot)
            await self.publish(
                job_id,
                {
                    "type": "completed" if status == "completed" else "progress",
                    "status": status,
                    "progress": progress,
                },
            )


job_manager = JobManager()
