from typing import Any

import pytest
from app.workflows.bounded import BoundedWorkflowRunner, NodeContract
from pydantic import BaseModel


class ExampleInput(BaseModel):
    project_id: str
    revision: int


class ExampleOutput(BaseModel):
    value: str
    artifacts: list[str]


@pytest.mark.asyncio
async def test_node_declares_contract_retries_and_reuses_completed_output():
    attempts = 0
    updates: list[dict[str, Any]] = []

    async def handler(input_value: ExampleInput) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("temporary")
        return {"value": input_value.project_id, "artifacts": ["deck.json"]}

    async def observe(state: dict[str, Any]) -> None:
        updates.append(state)

    contract = NodeContract(
        name="plan",
        input_model=ExampleInput,
        output_model=ExampleOutput,
        handler=handler,
        max_attempts=2,
        retry_for=(TimeoutError,),
        artifact_paths=lambda _input, output: output.artifacts if output else ["deck.json"],
    )
    runner = BoundedWorkflowRunner(retry_base_seconds=0)
    result = await runner.run_node(
        contract,
        {"project_id": "project-1", "revision": 3},
        on_update=observe,
    )

    assert result.output.value == "project-1"
    assert result.attempts == 2
    assert [state["status"] for state in updates] == ["running", "retrying", "running", "completed"]
    assert updates[-1]["inputSchema"] == "ExampleInput"
    assert updates[-1]["outputSchema"] == "ExampleOutput"
    assert updates[-1]["artifactPaths"] == ["deck.json"]
    assert updates[-1]["retryFor"] == ["TimeoutError"]

    async def must_not_run(_input: ExampleInput) -> ExampleOutput:
        raise AssertionError("completed node should be reused")

    reusable_contract = NodeContract(
        name="plan",
        input_model=ExampleInput,
        output_model=ExampleOutput,
        handler=must_not_run,
    )
    reused = await runner.run_node(
        reusable_contract,
        {"project_id": "project-1", "revision": 3},
        checkpoint={"nodes": {"plan": updates[-1]}},
    )
    assert reused.reused is True
    assert reused.output.artifacts == ["deck.json"]


@pytest.mark.asyncio
async def test_node_does_not_retry_undeclared_failure():
    attempts = 0
    updates: list[dict[str, Any]] = []

    async def handler(_input: ExampleInput) -> ExampleOutput:
        nonlocal attempts
        attempts += 1
        raise ValueError("invalid business input")

    async def observe(state: dict[str, Any]) -> None:
        updates.append(state)

    contract = NodeContract(
        name="evidence_gate",
        input_model=ExampleInput,
        output_model=ExampleOutput,
        handler=handler,
        max_attempts=3,
        retry_for=(TimeoutError,),
    )
    with pytest.raises(ValueError, match="invalid business input"):
        await BoundedWorkflowRunner(retry_base_seconds=0).run_node(
            contract,
            ExampleInput(project_id="project-1", revision=1),
            on_update=observe,
        )

    assert attempts == 1
    assert updates[-1]["status"] == "failed"
