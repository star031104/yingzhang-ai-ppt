from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

ModelRole = Literal[
    "planner",
    "source_analyst",
    "slide_coder",
    "vision_critic",
    "repair",
    "research",
    "embedding",
    "image_generation",
]
Capability = Literal[
    "chat", "vision", "structured_output", "embedding", "image_generation", "long_context"
]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectOut(ORMModel):
    id: str
    name: str
    status: str
    artifact_path: str


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: HttpUrl
    api_key: str | None = None
    extra_headers: dict[str, str] = Field(default_factory=dict)


class ProviderOut(ORMModel):
    id: str
    name: str
    base_url: str
    enabled: bool
    has_api_key: bool = False


class ModelRegister(BaseModel):
    model_id: str = Field(min_length=1)
    capabilities: set[Capability] = Field(default_factory=lambda: {"chat"})
    quality_profile: dict[str, float] = Field(default_factory=dict)


class ModelOut(ORMModel):
    id: str
    provider_id: str
    model_id: str
    capabilities: list[str]
    quality_profile: dict[str, float]


class RoleMapping(BaseModel):
    role: ModelRole
    model_config_id: str


class ConnectionResult(BaseModel):
    ok: bool
    latency_ms: int
    models: list[str]
    error: str | None = None


class ProviderDiscovery(BaseModel):
    base_url: HttpUrl
    api_key: str | None = None
    extra_headers: dict[str, str] = Field(default_factory=dict)
    model_type: Literal["text", "image"] | None = None


class JobCreate(BaseModel):
    kind: str = Field(min_length=1, max_length=80)
    project_id: str | None = None


JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
PageStatus = Literal["pending", "running", "ready", "failed", "cancelled"]


class PageGenerationState(BaseModel):
    model_config = ConfigDict(extra="allow")

    slideId: str
    position: int = Field(ge=1)
    status: PageStatus
    error: str | None = None
    candidateCount: int | None = Field(default=None, ge=0)
    artifactRoot: str | None = None


class JobWorkflowState(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str | None = None
    resumable: bool = False
    payload: dict = Field(default_factory=dict)
    resumeCount: int = Field(default=0, ge=0)
    previousProjectStatus: str | None = None


class WorkflowNodeState(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    status: Literal["running", "retrying", "completed", "failed"]
    idempotencyKey: str
    inputSchema: str
    outputSchema: str
    attempts: int = Field(ge=1)
    maxAttempts: int = Field(ge=1)
    retryFor: list[str] = Field(default_factory=list)
    artifactPaths: list[str] = Field(default_factory=list)
    output: dict = Field(default_factory=dict)
    error: str | None = None


class JobCheckpoint(BaseModel):
    model_config = ConfigDict(extra="allow")

    stage: str | None = None
    label: str | None = None
    result: dict = Field(default_factory=dict)
    cancelRequested: bool = False
    workflow: JobWorkflowState | None = None
    pages: list[PageGenerationState] = Field(default_factory=list)
    pageCounts: dict[PageStatus, int] = Field(default_factory=dict)
    nodes: dict[str, WorkflowNodeState] = Field(default_factory=dict)


class JobOut(ORMModel):
    id: str
    project_id: str | None
    kind: str
    status: JobStatus
    progress: float
    checkpoint: JobCheckpoint
    error: str | None


class JobEvent(JobOut):
    type: Literal[
        "snapshot",
        "progress",
        "page_progress",
        "cancel_requested",
        "completed",
        "failed",
        "cancelled",
    ]
    job_id: str
