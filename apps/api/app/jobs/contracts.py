from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable
from typing import Any, Protocol, TypedDict


class JobSnapshot(TypedDict):
    id: str
    project_id: str | None
    kind: str
    status: str
    progress: float
    checkpoint: dict[str, Any]
    error: str | None


class JobStore(Protocol):
    """Durable source of truth for job state."""

    def get(self, job_id: str) -> JobSnapshot | None: ...

    def list_active(self) -> list[JobSnapshot]: ...

    def save(self, snapshot: JobSnapshot) -> JobSnapshot | None: ...


class JobExecutor(Protocol):
    """Runs a reconstructed workflow without defining its persistence semantics."""

    def submit(
        self, coroutine: Awaitable[Any], job_id: str | None = None
    ) -> asyncio.Task[Any]: ...


class EventBus(Protocol):
    """Fan-out transport for live job updates; durable state remains in JobStore."""

    async def connect(self, job_id: str, websocket: Any) -> None: ...

    def disconnect(self, job_id: str, websocket: Any) -> None: ...

    def open_subscription(self, job_id: str) -> asyncio.Queue[dict[str, Any]]: ...

    def close_subscription(
        self, job_id: str, queue: asyncio.Queue[dict[str, Any]]
    ) -> None: ...

    async def next_event(
        self, queue: asyncio.Queue[dict[str, Any]]
    ) -> dict[str, Any] | None: ...

    def subscribe(self, job_id: str) -> AsyncIterator[dict[str, Any] | None]: ...

    async def publish(self, job_id: str, payload: dict[str, Any]) -> None: ...
