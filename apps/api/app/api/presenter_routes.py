"""Guided intake (before planning) and rehearsal (after generation)."""

import json
from pathlib import Path
from typing import Any, Literal

from app.api.dependencies import project_or_404
from app.db.models import DeckSpecRecord
from app.db.session import get_db
from app.slides import load_slides
from app.sources import load_sources
from app.workflows.intake import build_intake, compile_intake
from app.workflows.planning_brief import PlanRequest
from app.workflows.rehearsal import build_rehearsal, rehearsal_markdown
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1")


class IntakeRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    instructions: str = Field(default="", max_length=4000)
    preset: str = "academic"
    slide_count: int = Field(default=12, ge=6, le=60)
    duration_minutes: int | None = Field(default=None, ge=3, le=180)
    audience: str = Field(default="", max_length=240)
    objective: str = Field(default="", max_length=500)
    tone: Literal["auto", "formal", "executive", "editorial", "energetic"] = "auto"
    brand_name: str = Field(default="", max_length=120)


class IntakeCompileRequest(BaseModel):
    base: dict[str, Any]
    answers: dict[str, Any] = Field(default_factory=dict)
    intake: dict[str, Any] | None = None


@router.post("/projects/{project_id}/intake")
def guided_intake(project_id: str, body: IntakeRequest, db: Session = Depends(get_db)):
    """Five-phase guide (strategy, substance, structure, design, build) with suggested answers."""
    project_or_404(project_id, db)
    return build_intake(**body.model_dump(), sources=load_sources(project_id, db))


@router.post("/projects/{project_id}/intake/compile")
def compile_guided_intake(project_id: str, body: IntakeCompileRequest, db: Session = Depends(get_db)):
    """Turn intake answers into a validated planning request (and keep a record of them)."""
    project = project_or_404(project_id, db)
    payload = compile_intake(body.base, body.answers, body.intake)
    try:
        request = PlanRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(422, f"引导答案无法组成有效的生成请求：{exc.errors()[0].get('msg', '')}") from exc
    record = Path(project.artifact_path) / "analysis" / "intake.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"answers": body.answers, "request": request.model_dump()}, ensure_ascii=False, indent=2), encoding="utf-8")
    return request.model_dump()


class RehearsalRequest(BaseModel):
    duration_minutes: float | None = Field(default=None, ge=1, le=240)


def _requested_minutes(project_id: str, db: Session) -> float | None:
    deck = db.get(DeckSpecRecord, project_id)
    brief = ((deck.reproducibility or {}).get("request") or {}).get("professionalBrief") if deck else None
    value = (brief or {}).get("durationMinutes")
    return float(value) if value else None


@router.post("/projects/{project_id}/rehearsal")
def build_project_rehearsal(project_id: str, body: RehearsalRequest | None = None, db: Session = Depends(get_db)):
    """Per-slide time budget plus likely audience questions answered from the sources."""
    project = project_or_404(project_id, db)
    slides = load_slides(project_id, db)
    if not slides:
        raise HTTPException(409, "请先生成页面再排练")
    minutes = (body.duration_minutes if body else None) or _requested_minutes(project_id, db)
    rehearsal = build_rehearsal(slides, load_sources(project_id, db), minutes)
    folder = Path(project.artifact_path) / "plan"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "rehearsal.json").write_text(json.dumps(rehearsal, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "rehearsal.md").write_text(rehearsal_markdown(project.name, rehearsal), encoding="utf-8")
    return rehearsal


@router.get("/projects/{project_id}/rehearsal/card")
def download_rehearsal_card(project_id: str, db: Session = Depends(get_db)):
    project = project_or_404(project_id, db)
    target = Path(project.artifact_path) / "plan" / "rehearsal.md"
    if not target.is_file():
        raise HTTPException(409, "请先生成排练卡")
    return FileResponse(target, media_type="text/markdown; charset=utf-8", filename="rehearsal.md")
