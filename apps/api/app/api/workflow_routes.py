"""HTTP routes for planning, approval gates, generation and durable project jobs.

Business logic lives in ``app.workflows``; this module wires HTTP inputs to those
operations and keeps backwards-compatible names for integrations and tests.
"""

from collections.abc import Awaitable, Callable
from pathlib import Path

from app.api.dependencies import project_or_404
from app.api.skill_routes import (
    select_github_skill_subtree as _select_github_skill_subtree,
)
from app.api.skill_routes import skill_download_urls as _skill_download_urls
from app.db.models import DeckSpecRecord, Job
from app.db.session import get_db
from app.jobs.manager import job_manager
from app.jobs.progress import job_view as _job_view
from app.personalization import service as personal
from app.presentation_intelligence.content_claims import (  # noqa: F401  (compatibility re-exports)
    clean_audience_bullet,
    fit_audience_bullet,
    referenced_metric_claims,
    sanitize_numeric_claims,
)
from app.providers.openai_compatible import OpenAICompatibleClient  # noqa: F401
from app.providers.structured import parse_model_json  # noqa: F401
from app.slides import load_slides
from app.sources import load_sources
from app.sources import safe_upload_name as _safe_upload_name
from app.workflows.generation import _generate_core, _generate_sample_core, _set_gate
from app.workflows.images import ensure_generated_images  # noqa: F401
from app.workflows.model_planning import (  # noqa: F401
    builtin_strategy_memory,
    compact_strategy_material,
    enhance_plan_with_routed_model,
    normalized_strategy,
)
from app.workflows.outline import _plan_project_core
from app.workflows.outline_repair import (  # noqa: F401
    OUTLINE_AUTO_REPAIR_CODES,
    academic_result_source_refs,
    academic_result_topics,
    best_source_refs,
    repair_outline_from_builtin,
)
from app.workflows.planning_brief import (  # noqa: F401
    PRESET_LABELS,
    TONE_LABELS,
    PlanRequest,
    enriched_instructions,
    page_responsibilities,
    professional_brief,
)
from app.workflows.project_jobs import (
    JOB_LABELS,
    ProjectJobOperations,
    ProjectJobService,
)
from app.workflows.visual_reflection import run_visual_reflection  # noqa: F401
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1")

# Compatibility import for integrations that used the former workflow helper.
safe_upload_name = _safe_upload_name
select_github_skill_subtree = _select_github_skill_subtree
skill_download_urls = _skill_download_urls


@router.post("/projects/{project_id}/analyze")
@router.post("/projects/{project_id}/narrative")
@router.post("/projects/{project_id}/outline")
async def plan_project(project_id: str, body: PlanRequest, db: Session = Depends(get_db)):
    """保留同步接口供本机自动化使用；公网界面使用后台任务接口。"""
    return await _plan_project_core(project_id, body, db)


@router.post("/projects/{project_id}/gates/outline/approve")
def approve_outline(project_id: str, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    deck = db.get(DeckSpecRecord, project_id)
    if not deck or not load_slides(project_id, db):
        raise HTTPException(409, "请先生成大纲")
    gates = _set_gate(deck, "outline", "approved")
    db.commit()
    return {"gates": gates}



@router.post("/projects/{project_id}/sample")
async def generate_sample(project_id: str, db: Session = Depends(get_db)):
    return await _generate_sample_core(project_id, db)


@router.get("/projects/{project_id}/sample/html")
def preview_sample(project_id: str, db: Session = Depends(get_db)):
    project = project_or_404(project_id, db)
    target = Path(project.artifact_path) / "slides" / "sample" / "index.html"
    if not target.exists():
        raise HTTPException(409, "请先生成代表样张")
    return FileResponse(target)


@router.post("/projects/{project_id}/gates/sample/approve")
def approve_sample(project_id: str, db: Session = Depends(get_db)):
    project = project_or_404(project_id, db)
    deck = db.get(DeckSpecRecord, project_id)
    if not deck:
        raise HTTPException(409, "请先生成大纲")
    if not (Path(project.artifact_path) / "slides" / "sample" / "index.html").exists():
        raise HTTPException(409, "请先检查代表样张")
    gates = _set_gate(deck, "sample", "approved")
    db.commit()
    return {"gates": gates}



@router.post("/projects/{project_id}/generate")
async def generate(project_id: str, db: Session = Depends(get_db)):
    return await _generate_core(project_id, db)


async def _project_job_plan(project_id: str, payload: dict, db: Session) -> dict:
    result = await _plan_project_core(project_id, PlanRequest.model_validate(payload), db)
    return {"slides": len(result.get("slides", []))}


async def _project_job_sample(project_id: str, db: Session) -> dict:
    return await _generate_sample_core(project_id, db, propagate_engine_error=True)


async def _project_job_generate(
    project_id: str,
    db: Session,
    on_page_event: Callable[[dict], Awaitable[None]],
    is_cancelled: Callable[[], bool],
) -> dict:
    return await _generate_core(
        project_id,
        db,
        on_page_event=on_page_event,
        is_cancelled=is_cancelled,
    )


project_job_service = ProjectJobService(
    ProjectJobOperations(
        plan=_project_job_plan,
        sample=_project_job_sample,
        generate=_project_job_generate,
        load_slides=load_slides,
        load_sources=load_sources,
    )
)




def _start_project_job(
    project_id: str,
    kind: str,
    db: Session,
    payload: dict | None = None,
) -> dict:
    from app.api.project_lifecycle import project_lifecycle_lock

    with project_lifecycle_lock(project_id):
        return _start_project_job_locked(project_id, kind, db, payload)


def _start_project_job_locked(
    project_id: str,
    kind: str,
    db: Session,
    payload: dict | None = None,
) -> dict:
    project = project_or_404(project_id, db)
    active = db.scalar(
        select(Job)
        .where(Job.project_id == project_id, Job.kind == kind, Job.status.in_({"queued", "running"}))
        .order_by(Job.created_at.desc())
    )
    if active:
        return _job_view(active)
    if not job_manager.has_capacity():
        raise HTTPException(503, "生成队列已满，请稍后再提交任务")
    from app.db.models import PersonalBinding
    if kind in {"outline", "full"} and (payload or {}).get("personalization_mode") == "profile":
        personal.bind(db, project_id, payload.get("profile_id"), payload.get("preset", "academic"), payload.get("profile_revision"))
    binding = db.get(PersonalBinding, project_id)
    job = Job(
        project_id=project_id,
        kind=kind,
        status="queued",
        progress=0.0,
        checkpoint={
            "stage": "queued",
            "label": "任务已提交，正在排队",
            "workflow": {
                "version": "durable-generation-v1",
                "personalizationEpoch": binding.snapshot.get("epoch") if binding else None,
                "resumable": True,
                "payload": payload or {},
                "resumeCount": 0,
                "previousProjectStatus": project.status,
            },
        },
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    job_manager.spawn(project_job_service.run(job.id, project_id, kind, payload), job_id=job.id)
    return _job_view(job)


@router.post("/projects/{project_id}/jobs/outline", status_code=202)
async def start_outline_job(project_id: str, body: PlanRequest, db: Session = Depends(get_db)):
    return _start_project_job(project_id, "outline", db, body.model_dump())


@router.post("/projects/{project_id}/jobs/sample", status_code=202)
async def start_sample_job(project_id: str, db: Session = Depends(get_db)):
    return _start_project_job(project_id, "sample", db)


@router.post("/projects/{project_id}/jobs/generate", status_code=202)
async def start_generate_job(project_id: str, db: Session = Depends(get_db)):
    return _start_project_job(project_id, "generate", db)


@router.post("/projects/{project_id}/jobs/full", status_code=202)
async def start_full_generation_job(
    project_id: str, body: PlanRequest, db: Session = Depends(get_db)
):
    """Plan and render a complete deck without pausing for approval gates."""
    payload = body.model_dump()
    payload["approval_mode"] = False
    return _start_project_job(project_id, "full", db, payload)


def _resume_project_job(snapshot: dict):
    return project_job_service.resume(snapshot)


job_manager.register_runner(lambda kind: kind in JOB_LABELS, _resume_project_job)
