import asyncio
import copy
import json
import shutil
from pathlib import Path
from typing import Literal

from app.api.dependencies import project_or_404
from app.api.slide_version_routes import ensure_slide_revision
from app.db.models import Job, SlideCandidate, SlideEditMessage, SlideSpecRecord, SlideVersion
from app.db.session import SessionLocal, get_db
from app.jobs.manager import JobCancelled, job_manager
from app.jobs.progress import friendly_job_error as _friendly_job_error
from app.jobs.progress import job_view as _job_view
from app.jobs.progress import set_job_stage as _set_job_stage
from app.personalization.runtime import assert_current, guarded_sync_generation
from app.personalization.runtime import lock as personal_lock
from app.personalization.service import record_feedback
from app.presentation_engine.service import EngineError, presentation_engine
from app.presentation_intelligence.object_edit import apply_object_edit
from app.professional import append_stage_trace, diff_slide_specs
from app.security.public_access import current_user
from app.slides import load_slides
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1")


class EditRequest(BaseModel):
    instruction: str = Field(min_length=2)
    patch: dict = Field(default_factory=dict)
    revision: int | None = Field(default=None, ge=1)


class ObjectEditRequest(BaseModel):
    instruction: str = Field(min_length=2, max_length=1200)
    target: dict = Field(default_factory=dict)
    operation: Literal["replace", "append", "delete", "move"] = "replace"
    value: str | list[str] | None = None
    rerender: bool = True
    revision: int | None = Field(default=None, ge=1)


@guarded_sync_generation
def _regenerate_slide_core(project_id: str, slide_id: str, db: Session) -> dict:
    project = project_or_404(project_id, db)
    row = db.get(SlideSpecRecord, slide_id)
    if not row or row.project_id != project_id:
        raise HTTPException(404, "Slide not found")
    partial_root = Path(project.artifact_path) / "slides" / "partial" / slide_id
    presentation_engine.run("build", [copy.deepcopy(row.spec)], partial_root)
    with personal_lock:
        assert_current()
        generated_root = partial_root / "slides" / str(row.position)
        current = json.loads((generated_root / "current.json").read_text(encoding="utf-8"))
        main_output = Path(project.artifact_path) / "slides" / "rendered"
        main_root = main_output / "slides" / str(row.position)
        main_root.mkdir(parents=True, exist_ok=True)
        for pattern in ("*.html", "*.png", "*.scene.json", "*.score.json", "current.json"):
            for old in main_root.glob(pattern):
                old.unlink(missing_ok=True)
        for source in generated_root.iterdir():
            if source.is_file():
                shutil.copy2(source, main_root / source.name)
        spec = copy.deepcopy(row.spec)
        if current.get("designSystem"):
            spec["designSystem"] = current["designSystem"]
        visual = dict(spec.get("visualIntent") or {})
        visual["selectedVariant"] = current["variant"]
        if visual.get("variantSelectionSource") != "user":
            visual["variantSelectionSource"] = "partial-regenerate"
        spec["visualIntent"] = visual
        row.spec = spec
        db.execute(delete(SlideCandidate).where(SlideCandidate.slide_id == slide_id))
        count = 0
        for score_path in generated_root.glob("*.score.json"):
            variant = score_path.name.removesuffix(".score.json")
            db.add(SlideCandidate(
                slide_id=slide_id,
                variant=variant,
                artifact_path=str(main_root / f"{variant}.html"),
                score=json.loads(score_path.read_text(encoding="utf-8")),
                selected=variant == current["variant"],
            ))
            count += 1
        presentation_engine.run("assemble", load_slides(project_id, db), main_output)
        assert_current()
        db.commit()
        return {"slideId": slide_id, "position": row.position, "candidateCount": count, "variant": current["variant"]}


async def _run_slide_job(job_id: str, project_id: str, slide_id: str):
    try:
        await _set_job_stage(job_id, 0.12, "preparing", "正在隔离当前页面并准备候选")
        await _set_job_stage(job_id, 0.32, "rendering", "正在重新渲染当前页面")
        def regenerate_in_worker():
            with SessionLocal() as db:
                return _regenerate_slide_core(project_id, slide_id, db)

        result = await asyncio.to_thread(regenerate_in_worker)
        await _set_job_stage(job_id, 0.88, "assembling", "正在合并页面并保持其他页面不变")
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if not job:
                return
            checkpoint = dict(job.checkpoint or {})
            checkpoint.update({"stage": "completed", "label": "当前页面已重新生成", "result": result})
            job.status, job.progress, job.checkpoint, job.error = "completed", 1.0, checkpoint, None
            db.commit()
            snapshot = _job_view(job)
        await job_manager.publish(job_id, {**snapshot, "type": "completed"})
    except JobCancelled as exc:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if not job:
                return
            checkpoint = append_stage_trace(
                job.checkpoint or {}, "cancelled", str(exc), job.progress
            )
            job.status, job.error, job.checkpoint = "cancelled", None, checkpoint
            db.commit()
            snapshot = _job_view(job)
        await job_manager.publish(job_id, {**snapshot, "type": "cancelled"})
    except Exception as exc:  # noqa: BLE001 - job boundary must persist every failure
        message = _friendly_job_error(exc)
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job:
                job.status, job.error = "failed", message
                job.checkpoint = {**(job.checkpoint or {}), "stage": "failed", "label": message}
                db.commit()
                snapshot = _job_view(job)
            else:
                snapshot = {"status": "failed", "progress": 0, "checkpoint": {}, "error": message}
        await job_manager.publish(job_id, {**snapshot, "type": "failed"})


@router.post("/projects/{project_id}/slides/{slide_id}/jobs/regenerate", status_code=202)
async def start_slide_regenerate_job(project_id: str, slide_id: str, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    row = db.get(SlideSpecRecord, slide_id)
    if not row or row.project_id != project_id:
        raise HTTPException(404, "Slide not found")
    active = db.scalar(select(Job).where(
        Job.project_id == project_id,
        Job.kind == f"slide-regenerate:{slide_id}",
        Job.status.in_({"queued", "running"}),
    ))
    if active:
        return _job_view(active)
    job = Job(
        project_id=project_id,
        kind=f"slide-regenerate:{slide_id}",
        checkpoint={
            "stage": "queued",
            "label": "当前页已进入重新生成队列",
            "slideId": slide_id,
            "workflow": {
                "version": "durable-generation-v1",
                "resumable": True,
                "payload": {"slideId": slide_id},
                "resumeCount": 0,
            },
        },
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    job_manager.spawn(_run_slide_job(job.id, project_id, slide_id), job_id=job.id)
    return _job_view(job)


def _resume_slide_job(snapshot: dict):
    checkpoint = snapshot.get("checkpoint") or {}
    workflow = checkpoint.get("workflow") or {}
    slide_id = (workflow.get("payload") or {}).get("slideId") or checkpoint.get("slideId")
    return _run_slide_job(snapshot["id"], snapshot["project_id"], slide_id)


job_manager.register_runner(lambda kind: kind.startswith("slide-regenerate:"), _resume_slide_job)


@router.post("/projects/{project_id}/slides/{slide_id}/candidates")
@router.post("/projects/{project_id}/slides/{slide_id}/regenerate")
def regenerate_slide(project_id: str, slide_id: str, db: Session = Depends(get_db)):
    return _regenerate_slide_core(project_id, slide_id, db)


@router.post("/projects/{project_id}/slides/{slide_id}/repair")
def edit_slide(project_id: str, slide_id: str, body: EditRequest, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    row = db.get(SlideSpecRecord, slide_id)
    if not row or row.project_id != project_id:
        raise HTTPException(404, "Slide not found")
    ensure_slide_revision(row, body.revision)
    spec = copy.deepcopy(row.spec)
    before_spec = copy.deepcopy(row.spec)
    allowed = {"message", "content", "visualIntent", "constraints"}
    for key, value in body.patch.items():
        if key in allowed:
            spec[key] = value
    row.current_version += 1
    row.spec = spec
    record_feedback(db, row, before_spec, "patch", body.instruction)
    db.add(
        SlideVersion(
            slide_id=slide_id, version=row.current_version, spec=spec, reason=body.instruction
        )
    )
    db.commit()
    return {"slide": {**spec, "revision": row.current_version}, "version": row.current_version}


@router.get("/projects/{project_id}/slides/{slide_id}/chat")
def slide_edit_history(project_id: str, slide_id: str, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    slide = db.get(SlideSpecRecord, slide_id)
    if not slide or slide.project_id != project_id:
        raise HTTPException(404, "Slide not found")
    return [
        {
            "id": row.id, "actor": row.actor, "instruction": row.instruction,
            "target": row.target, "changeSet": row.change_set, "version": row.version,
            "createdAt": row.created_at.isoformat(),
        }
        for row in db.scalars(
            select(SlideEditMessage)
            .where(SlideEditMessage.slide_id == slide_id)
            .order_by(SlideEditMessage.created_at.asc())
        )
    ]


@router.post("/projects/{project_id}/slides/{slide_id}/chat")
def chat_edit_slide(
    project_id: str,
    slide_id: str,
    body: ObjectEditRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    project = project_or_404(project_id, db)
    row = db.get(SlideSpecRecord, slide_id)
    if not row or row.project_id != project_id:
        raise HTTPException(404, "Slide not found")
    ensure_slide_revision(row, body.revision)
    before_spec = copy.deepcopy(row.spec)
    try:
        spec, change_set = apply_object_edit(
            row.spec, body.instruction, body.target, body.operation, body.value
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    change_set["review"] = diff_slide_specs(before_spec, spec)
    row.current_version += 1
    row.spec = spec
    actor = (current_user(request) or {}).get("name", "本机管理员")
    record_feedback(db, row, before_spec, "object-edit", body.instruction)
    db.add(SlideVersion(
        slide_id=slide_id,
        version=row.current_version,
        spec=copy.deepcopy(spec),
        reason=f"页内对话：{body.instruction}",
    ))
    db.add(SlideEditMessage(
        slide_id=slide_id,
        actor=actor,
        instruction=body.instruction,
        target=body.target,
        change_set=change_set,
        version=row.current_version,
    ))
    db.commit()
    render_result = None
    rendered = Path(project.artifact_path) / "slides" / "rendered" / "index.html"
    if body.rerender and rendered.exists():
        render_result = _regenerate_slide_core(project_id, slide_id, db)
    return {
        "slide": {**row.spec, "revision": row.current_version},
        "version": row.current_version,
        "changeSet": change_set,
        "render": render_result,
    }


@router.post("/projects/{project_id}/slides/{slide_id}/select")
def select_candidate(
    project_id: str,
    slide_id: str,
    candidate_id: str = Form(...),
    revision: int | None = Form(None),
    db: Session = Depends(get_db),
):
    project_or_404(project_id, db)
    candidate = db.get(SlideCandidate, candidate_id)
    if not candidate or candidate.slide_id != slide_id:
        raise HTTPException(404, "Candidate not found")
    slide = db.get(SlideSpecRecord, slide_id)
    if not slide or slide.project_id != project_id:
        raise HTTPException(404, "Slide not found")
    ensure_slide_revision(slide, revision)
    before_spec = copy.deepcopy(slide.spec)
    for row in db.scalars(select(SlideCandidate).where(SlideCandidate.slide_id == slide_id)):
        row.selected = row.id == candidate_id
    spec = copy.deepcopy(slide.spec)
    visual_intent = dict(spec.get("visualIntent") or {})
    visual_intent["selectedVariant"] = candidate.variant
    visual_intent["variantSelectionSource"] = "user"
    spec["visualIntent"] = visual_intent
    slide.current_version += 1
    slide.spec = spec
    record_feedback(db, slide, before_spec, "candidate-select")
    db.add(
        SlideVersion(
            slide_id=slide_id,
            version=slide.current_version,
            spec=spec,
            reason=f"选择候选版式：{candidate.variant}",
        )
    )
    project = project_or_404(project_id, db)
    output = Path(project.artifact_path) / "slides" / "rendered"
    try:
        presentation_engine.run("assemble", load_slides(project_id, db), output)
    except EngineError as exc:
        raise HTTPException(500, str(exc)) from exc
    db.commit()
    return {"selected": candidate_id, "variant": candidate.variant}


@router.get("/projects/{project_id}/slides/{slide_id}/candidates/{candidate_id}/preview")
def candidate_preview(
    project_id: str, slide_id: str, candidate_id: str, db: Session = Depends(get_db)
):
    project = project_or_404(project_id, db)
    slide = db.get(SlideSpecRecord, slide_id)
    candidate = db.get(SlideCandidate, candidate_id)
    if not slide or slide.project_id != project_id or not candidate or candidate.slide_id != slide_id:
        raise HTTPException(404, "Candidate not found")
    target = Path(candidate.artifact_path).with_suffix(".png").resolve()
    artifact_root = Path(project.artifact_path).resolve()
    if not target.is_file() or target != artifact_root and artifact_root not in target.parents:
        raise HTTPException(404, "Candidate preview not found")
    return FileResponse(target, media_type="image/png")

