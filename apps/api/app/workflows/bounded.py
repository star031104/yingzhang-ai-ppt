from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

InputModel = TypeVar("InputModel", bound=BaseModel)
OutputModel = TypeVar("OutputModel", bound=BaseModel)
NodeHandler = Callable[[InputModel], Awaitable[OutputModel | dict[str, Any]]]
NodeObserver = Callable[[dict[str, Any]], Awaitable[None]]
ArtifactResolver = Callable[[InputModel, OutputModel | None], list[str]]


@dataclass(frozen=True)
class NodeContract(Generic[InputModel, OutputModel]):
    name: str
    input_model: type[InputModel]
    output_model: type[OutputModel]
    handler: NodeHandler[InputModel, OutputModel]
    max_attempts: int = 1
    retry_for: tuple[type[Exception], ...] = ()
    artifact_paths: ArtifactResolver[InputModel, OutputModel] | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Node name cannot be empty")
        if self.max_attempts < 1:
            raise ValueError("Node max_attempts must be at least 1")


@dataclass(frozen=True)
class NodeResult(Generic[OutputModel]):
    output: OutputModel
    idempotency_key: str
    reused: bool
    attempts: int


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _idempotency_key(name: str, input_value: BaseModel) -> str:
    canonical = json.dumps(
        input_value.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(f"{name}:{canonical}".encode()).hexdigest()
    return f"{name}:{digest}"


class BoundedWorkflowRunner:
    """Validate, observe, retry, and safely reuse a single workflow node."""

    def __init__(self, retry_base_seconds: float = 1) -> None:
        self.retry_base_seconds = max(0, retry_base_seconds)

    async def run_node(
        self,
        contract: NodeContract[InputModel, OutputModel],
        payload: InputModel | dict[str, Any],
        *,
        checkpoint: dict[str, Any] | None = None,
        on_update: NodeObserver | None = None,
    ) -> NodeResult[OutputModel]:
        input_value = (
            payload
            if isinstance(payload, contract.input_model)
            else contract.input_model.model_validate(payload)
        )
        key = _idempotency_key(contract.name, input_value)
        prior = ((checkpoint or {}).get("nodes") or {}).get(contract.name) or {}
        if prior.get("status") == "completed" and prior.get("idempotencyKey") == key:
            output = contract.output_model.model_validate(prior.get("output") or {})
            return NodeResult(
                output=output,
                idempotency_key=key,
                reused=True,
                attempts=int(prior.get("attempts") or 1),
            )

        retry_names = [error.__name__ for error in contract.retry_for]
        base_state = {
            "name": contract.name,
            "idempotencyKey": key,
            "inputSchema": contract.input_model.__name__,
            "outputSchema": contract.output_model.__name__,
            "maxAttempts": contract.max_attempts,
            "retryFor": retry_names,
            "artifactPaths": contract.artifact_paths(input_value, None)
            if contract.artifact_paths
            else [],
        }

        for attempt in range(1, contract.max_attempts + 1):
            running = {**base_state, "status": "running", "attempts": attempt, "at": _timestamp()}
            if on_update:
                await on_update(running)
            try:
                raw_output = await contract.handler(input_value)
                output = (
                    raw_output
                    if isinstance(raw_output, contract.output_model)
                    else contract.output_model.model_validate(raw_output)
                )
            except Exception as exc:
                can_retry = isinstance(exc, contract.retry_for) and attempt < contract.max_attempts
                failed = {
                    **base_state,
                    "status": "retrying" if can_retry else "failed",
                    "attempts": attempt,
                    "error": str(exc)[:500],
                    "at": _timestamp(),
                }
                if on_update:
                    await on_update(failed)
                if not can_retry:
                    raise
                await asyncio.sleep(min(self.retry_base_seconds * 2 ** (attempt - 1), 4))
                continue

            completed = {
                **base_state,
                "status": "completed",
                "attempts": attempt,
                "artifactPaths": contract.artifact_paths(input_value, output)
                if contract.artifact_paths
                else [],
                "output": output.model_dump(mode="json"),
                "at": _timestamp(),
            }
            if on_update:
                await on_update(completed)
            return NodeResult(
                output=output,
                idempotency_key=key,
                reused=False,
                attempts=attempt,
            )

        raise RuntimeError(f"Node {contract.name} exhausted without a result")
