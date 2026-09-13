import copy
from typing import Literal

from app.api.dependencies import project_slide_or_404
from app.db.models import SlideSpecRecord, SlideVersion
from app.db.session import get_db
from app.personalization.service import record_feedback
from app.professional import diff_slide_specs
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1")


class CanvasRegionRequest(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    x: float = Field(ge=0, le=12)
    y: float = Field(ge=0, le=12)
    w: float = Field(gt=0, le=12)
    h: float = Field(gt=0, le=12)
    priority: int = Field(default=50, ge=0, le=100)
    locked: bool = False


class CanvasLayoutRequest(BaseModel):
    regions: list[CanvasRegionRequest] = Field(min_length=1, max_length=20)
    focal_point: Literal["left", "right", "full"] = "right"
    revision: int | None = Field(default=None, ge=1)


def ensure_slide_revision(row: SlideSpecRecord, revision: int | None) -> None:
    """Reject stale editor writes while keeping older API clients compatible."""
    if revision is not None and row.current_version != revision:
        raise HTTPException(
            409,
            {
                "code": "slide_revision_conflict",
                "message": "页面已被其他操作更新，请刷新后再修改",
                "expected": revision,
                "current": row.current_version,
            },
        )


@router.get("/projects/{project_id}/slides/{slide_id}/versions")
def list_versions(project_id: str, slide_id: str, db: Session = Depends(get_db)):
    project_slide_or_404(project_id, slide_id, db)
    return [
        {"version": row.version, "reason": row.reason, "spec": row.spec}
        for row in db.scalars(
            select(SlideVersion)
            .where(SlideVersion.slide_id == slide_id)
            .order_by(SlideVersion.version)
        )
    ]


@router.get("/projects/{project_id}/slides/{slide_id}/versions/diff")
def compare_versions(
    project_id: str,
    slide_id: str,
    from_version: int,
    to_version: int,
    db: Session = Depends(get_db),
):
    project_slide_or_404(project_id, slide_id, db)
    rows = list(
        db.scalars(
            select(SlideVersion).where(
                SlideVersion.slide_id == slide_id,
                SlideVersion.version.in_({from_version, to_version}),
            )
        )
    )
    by_version = {row.version: row.spec for row in rows}
    if from_version not in by_version or to_version not in by_version:
        raise HTTPException(404, "Slide version not found")
    return diff_slide_specs(by_version[from_version], by_version[to_version])


@router.put("/projects/{project_id}/slides/{slide_id}/layout")
def update_slide_canvas_layout(
    project_id: str,
    slide_id: str,
    body: CanvasLayoutRequest,
    db: Session = Depends(get_db),
):
    row = project_slide_or_404(project_id, slide_id, db)
    ensure_slide_revision(row, body.revision)
    regions = [item.model_dump() for item in body.regions]
    if any(item["x"] + item["w"] > 12.001 or item["y"] + item["h"] > 12.001 for item in regions):
        raise HTTPException(422, "画布区域不能超出 12×12 规划网格")
    spec = copy.deepcopy(row.spec)
    before_spec = copy.deepcopy(row.spec)
    layout = dict(spec.get("layoutPlan") or {})
    layout.update(
        {
            "version": layout.get("version", "composition-plan-v1"),
            "regions": regions,
            "focalPoint": body.focal_point,
            "manualOverride": True,
        }
    )
    spec["layoutPlan"] = layout
    row.current_version += 1
    row.spec = spec
    record_feedback(db, row, before_spec, "canvas-edit")
    db.add(
        SlideVersion(
            slide_id=row.id,
            version=row.current_version,
            spec=spec,
            reason="canvas-layout-edited",
        )
    )
    db.commit()
    return {
        "slide": {**spec, "revision": row.current_version},
        "version": row.current_version,
        "layoutPlan": layout,
    }


@router.post("/projects/{project_id}/slides/{slide_id}/rollback/{version}")
def rollback_slide(project_id: str, slide_id: str, version: int, db: Session = Depends(get_db)):
    slide = project_slide_or_404(project_id, slide_id, db)
    target = db.scalar(
        select(SlideVersion).where(
            SlideVersion.slide_id == slide_id,
            SlideVersion.version == version,
        )
    )
    if target is None:
        raise HTTPException(404, "Slide version not found")
    before_spec = copy.deepcopy(slide.spec)
    slide.current_version += 1
    slide.spec = copy.deepcopy(target.spec)
    record_feedback(db, slide, before_spec, "rollback")
    db.add(
        SlideVersion(
            slide_id=slide_id,
            version=slide.current_version,
            spec=slide.spec,
            reason=f"rollback to {version}",
        )
    )
    db.commit()
    return {
        "slide": {**slide.spec, "revision": slide.current_version},
        "version": slide.current_version,
    }
