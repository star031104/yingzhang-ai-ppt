from typing import Literal

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    document: str
    section: str
    page: int | None = None


class Fact(BaseModel):
    id: str
    claim: str
    source_ref: SourceRef
    strict: bool = True


class DiagramNode(BaseModel):
    id: str
    label: str
    kind: Literal["process", "decision", "entity", "group"] = "process"


class DiagramEdge(BaseModel):
    source: str
    target: str
    label: str | None = None


class DiagramIR(BaseModel):
    nodes: list[DiagramNode]
    edges: list[DiagramEdge]
    direction: Literal["RIGHT", "DOWN"] = "RIGHT"


class ChartSeries(BaseModel):
    name: str
    values: list[float]


class ChartIR(BaseModel):
    kind: Literal["bar", "line", "area", "pie", "scatter"]
    categories: list[str]
    series: list[ChartSeries]
    source_refs: list[SourceRef]


class SceneNode(BaseModel):
    id: str
    type: Literal[
        "text", "shape", "image", "svg", "group", "chart", "diagram", "table", "video", "raster"
    ]
    bbox: dict[str, float]
    preferred_export: Literal["native", "svg", "raster"] = "native"
    fallback: list[Literal["svg", "raster"]] = Field(default_factory=lambda: ["svg", "raster"])


class SceneIR(BaseModel):
    width: float
    height: float
    nodes: list[SceneNode]
