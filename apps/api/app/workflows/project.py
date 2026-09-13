from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

ProjectJobKind = Literal["outline", "sample", "generate", "full"]


class ProjectActionInput(BaseModel):
    job_id: str
    project_id: str
    kind: ProjectJobKind
    payload: dict[str, Any] = Field(default_factory=dict)
    artifact_root: str


class ProjectActionOutput(BaseModel):
    summary: dict[str, Any]
    success_status: str
    artifacts: list[str] = Field(default_factory=list)


class ProjectGateInput(ProjectActionInput):
    summary: dict[str, Any] = Field(default_factory=dict)


class ProjectGateOutput(BaseModel):
    passed: bool
    status: str
    details: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)


def project_node_name(kind: ProjectJobKind) -> str:
    return {
        "outline": "plan",
        "sample": "render_sample",
        "generate": "render_candidates",
        "full": "full_generation",
    }[kind]


def expected_project_artifacts(
    input_value: ProjectActionInput, output: ProjectActionOutput | None
) -> list[str]:
    root = Path(input_value.artifact_root)
    expected = {
        "outline": [
            root / "plan" / "deck-spec.json",
            root / "analysis" / "evidence-graph.json",
            root / "analysis" / "content-architecture.json",
        ],
        "sample": [root / "slides" / "sample" / "index.html"],
        "generate": [
            root / "slides" / "rendered" / "index.html",
            root / "slides" / "rendered" / "scene-ir.json",
        ],
        "full": [
            root / "plan" / "deck-spec.json",
            root / "analysis" / "evidence-graph.json",
            root / "analysis" / "content-architecture.json",
            root / "slides" / "rendered" / "index.html",
            root / "slides" / "rendered" / "scene-ir.json",
        ],
    }[input_value.kind]
    if output is None:
        return [str(path) for path in expected]
    declared = [Path(path) for path in output.artifacts]
    return [str(path) for path in declared or expected if path.exists()]


def gate_artifacts(
    input_value: ProjectGateInput, output: ProjectGateOutput | None
) -> list[str]:
    if output is not None:
        return output.artifacts
    return expected_project_artifacts(
        ProjectActionInput(**input_value.model_dump(exclude={"summary"})), None
    )
