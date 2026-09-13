import json
import uuid
from pathlib import Path

from app.artifacts.store import artifact_store
from app.config import settings
from app.db.models import (
    DeckSpecRecord,
    ExportRecord,
    Job,
    ModelConfig,
    Project,
    ProjectSkill,
    Provider,
    RoleAssignment,
    SlideCandidate,
    SlideSpecRecord,
    SlideVersion,
    SourceDocument,
)
from app.db.session import SessionLocal, get_db
from app.jobs.manager import job_manager
from app.providers.openai_compatible import OpenAICompatibleClient, ProviderError, ImageGenerationPending
from app.schemas import (
    ConnectionResult,
    JobCreate,
    JobOut,
    ModelOut,
    ModelRegister,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    ProviderCreate,
    ProviderDiscovery,
    ProviderOut,
    RoleMapping,
)
from app.security.secrets import secret_store
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1")
ROLE_REQUIREMENTS = {
    "vision_critic": {"vision"},
    "embedding": {"embedding"},
    "image_generation": {"image_generation"},
}


@router.get("/health")
def health():
    return {"status": "ok", "phase": 1}


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    project_id = str(uuid.uuid4())
    root = artifact_store.create_project(project_id, {"id": project_id, "name": body.name})
    project = Project(id=project_id, name=body.name, artifact_path=str(root))
    db.add(project)
    if settings.private_accounts_mode:
        from app.db.models import ProjectOwner
        from app.security.accounts import owner_context
        if not owner_context.get():
            raise HTTPException(401, "请登录")
        db.flush()
        db.add(ProjectOwner(project_id=project.id, owner_id=owner_context.get()))
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    query = select(Project).order_by(Project.updated_at.desc())
    if settings.private_accounts_mode:
        from app.db.models import ProjectOwner
        from app.security.accounts import owner_context
        query = query.join(ProjectOwner).where(ProjectOwner.owner_id == owner_context.get())
    return list(db.scalars(query))


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, body: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    project.name = body.name.strip()
    db.commit()
    db.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    from app.personalization.data_management import delete_project_records
    delete_project_records(db, project_id)
    slide_ids = list(
        db.scalars(
            select(SlideSpecRecord.id).where(SlideSpecRecord.project_id == project_id)
        )
    )
    if slide_ids:
        db.execute(delete(SlideCandidate).where(SlideCandidate.slide_id.in_(slide_ids)))
        db.execute(delete(SlideVersion).where(SlideVersion.slide_id.in_(slide_ids)))
    db.execute(delete(SlideSpecRecord).where(SlideSpecRecord.project_id == project_id))
    db.execute(delete(DeckSpecRecord).where(DeckSpecRecord.project_id == project_id))
    db.execute(delete(SourceDocument).where(SourceDocument.project_id == project_id))
    db.execute(delete(ExportRecord).where(ExportRecord.project_id == project_id))
    db.execute(delete(ProjectSkill).where(ProjectSkill.project_id == project_id))
    db.execute(delete(Job).where(Job.project_id == project_id))
    trashed = artifact_store.trash_project(project_id, project.artifact_path)
    try:
        db.delete(project)
        db.commit()
    except Exception:
        db.rollback()
        if trashed and trashed.exists():
            trashed.replace(Path(project.artifact_path))
        raise


def provider_out(p):
    return ProviderOut.model_validate(p).model_copy(update={"has_api_key": bool(p.api_key_ref)})


def get_provider(provider_id, db):
    p = db.get(Provider, provider_id)
    if not p:
        raise HTTPException(404, "Provider not found")
    return p


@router.post("/providers", response_model=ProviderOut, status_code=201)
def create_provider(body: ProviderCreate, db: Session = Depends(get_db)):
    p = Provider(
        id=str(uuid.uuid4()),
        name=body.name,
        base_url=str(body.base_url).rstrip("/"),
        extra_headers=body.extra_headers,
    )
    if body.api_key:
        p.api_key_ref = f"provider:{p.id}"
        secret_store.set(p.api_key_ref, body.api_key)
    db.add(p)
    db.commit()
    db.refresh(p)
    return provider_out(p)


@router.get("/providers", response_model=list[ProviderOut])
def list_providers(db: Session = Depends(get_db)):
    return [provider_out(p) for p in db.scalars(select(Provider))]


@router.post("/providers/discover", response_model=ConnectionResult)
async def discover_provider(body: ProviderDiscovery):
    client = OpenAICompatibleClient(
        str(body.base_url).rstrip("/"),
        body.api_key,
        body.extra_headers,
        settings.request_timeout_seconds,
    )
    try:
        models, latency = await client.list_models(body.model_type)
        return ConnectionResult(ok=True, latency_ms=latency, models=models)
    except ProviderError as exc:
        return ConnectionResult(ok=False, latency_ms=0, models=[], error=str(exc))


@router.post("/providers/{provider_id}/test", response_model=ConnectionResult)
async def test_provider(provider_id: str, db: Session = Depends(get_db)):
    p = get_provider(provider_id, db)
    client = OpenAICompatibleClient(
        p.base_url,
        secret_store.get(p.api_key_ref),
        p.extra_headers,
        settings.request_timeout_seconds,
    )
    try:
        models, latency = await client.list_models()
        return ConnectionResult(ok=True, latency_ms=latency, models=models)
    except ProviderError as exc:
        return ConnectionResult(ok=False, latency_ms=0, models=[], error=str(exc))


@router.get("/providers/{provider_id}/models", response_model=list[str])
async def discover_models(provider_id: str, db: Session = Depends(get_db)):
    p = get_provider(provider_id, db)
    try:
        models, _ = await OpenAICompatibleClient(
            p.base_url,
            secret_store.get(p.api_key_ref),
            p.extra_headers,
            settings.request_timeout_seconds,
        ).list_models()
        return models
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/providers/{provider_id}/models", response_model=ModelOut, status_code=201)
def register_model(provider_id: str, body: ModelRegister, db: Session = Depends(get_db)):
    get_provider(provider_id, db)
    if "image_generation" in body.capabilities:
        from app.providers.image_models import image_model_problem
        problem = image_model_problem(body.model_id)
        if problem:
            raise HTTPException(422, problem)
    model = ModelConfig(
        provider_id=provider_id,
        model_id=body.model_id,
        capabilities=sorted(body.capabilities),
        quality_profile=body.quality_profile,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


@router.get("/models", response_model=list[ModelOut])
def list_models(db: Session = Depends(get_db)):
    return list(db.scalars(select(ModelConfig)))


@router.delete("/providers/{provider_id}", status_code=204)
def delete_provider(provider_id: str, db: Session = Depends(get_db)):
    provider = get_provider(provider_id, db)
    model_ids = list(
        db.scalars(select(ModelConfig.id).where(ModelConfig.provider_id == provider_id))
    )
    if model_ids:
        db.execute(
            delete(RoleAssignment).where(RoleAssignment.model_config_id.in_(model_ids))
        )
        db.execute(delete(ModelConfig).where(ModelConfig.id.in_(model_ids)))
    secret_ref = provider.api_key_ref
    db.delete(provider)
    db.commit()
    secret_store.delete(secret_ref)


@router.delete("/models/{model_id}", status_code=204)
def delete_model(model_id: str, db: Session = Depends(get_db)):
    model = db.get(ModelConfig, model_id)
    if not model:
        raise HTTPException(404, "Model configuration not found")
    db.execute(delete(RoleAssignment).where(RoleAssignment.model_config_id == model_id))
    db.delete(model)
    db.commit()


@router.post("/models/{model_id}/test-image")
async def test_image_model(model_id: str, db: Session = Depends(get_db)):
    model = db.get(ModelConfig, model_id)
    if not model or "image_generation" not in model.capabilities:
        raise HTTPException(404, "Image model configuration not found")
    provider = get_provider(model.provider_id, db)
    client = OpenAICompatibleClient(
        provider.base_url,
        secret_store.get(provider.api_key_ref),
        provider.extra_headers,
        settings.request_timeout_seconds,
    )
    prompt = (
        "Professional 16:9 presentation hero image, abstract evidence network becoming a clear narrative, "
        "deep indigo and mint editorial style, strong focal point, generous negative space on the left, "
        "no text, no letters, no numbers, no logo, no watermark"
    )
    size = "1664x928" if "qwen" in model.model_id.lower() else "1024x1024"
    try:
        data = await client.image_generation(
            model.model_id, prompt, size,
            task_state_path=settings.artifact_root / "model-tests" / f"{model.id}.task.json",
            wait_seconds=45,
        )
    except ImageGenerationPending as exc:
        return JSONResponse(status_code=202, content={"status": "pending", "message": str(exc)})
    except ProviderError as exc:
        raise HTTPException(502, f"生图模型测试失败：{exc}") from exc
    media_type = "image/jpeg" if data.startswith(b"\xff\xd8\xff") else "image/png"
    return Response(content=data, media_type=media_type)


@router.get("/model-routing")
def list_model_routing(db: Session = Depends(get_db)):
    return [
        {"role": row.role, "model_config_id": row.model_config_id}
        for row in db.scalars(select(RoleAssignment))
    ]


@router.put("/model-routing", response_model=RoleMapping)
def map_role(body: RoleMapping, db: Session = Depends(get_db)):
    model = db.get(ModelConfig, body.model_config_id)
    if not model:
        raise HTTPException(404, "Model configuration not found")
    missing = ROLE_REQUIREMENTS.get(body.role, set()) - set(model.capabilities)
    if missing:
        raise HTTPException(
            422, f"Role {body.role} requires capabilities: {', '.join(sorted(missing))}"
        )
    assignment = db.get(RoleAssignment, body.role)
    if assignment:
        assignment.model_config_id = body.model_config_id
    else:
        db.add(RoleAssignment(role=body.role, model_config_id=body.model_config_id))
    db.commit()
    return body


@router.post("/jobs", response_model=JobOut, status_code=202)
async def create_job(body: JobCreate, db: Session = Depends(get_db)):
    from app.security.accounts import authorize_project
    authorize_project(db, body.project_id)
    if body.project_id and not db.get(Project, body.project_id):
        raise HTTPException(404, "Project not found")
    job = Job(kind=body.kind, project_id=body.project_id)
    db.add(job)
    db.commit()
    db.refresh(job)
    job_manager.spawn(job_manager.run_demo(job.id), job_id=job.id)
    return job


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=JobOut, status_code=202)
async def cancel_job(job_id: str):
    job = await job_manager.request_cancel(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/jobs/{job_id}/pages/{slide_id}/preview")
def preview_completed_job_page(job_id: str, slide_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    project = db.get(Project, job.project_id) if job.project_id else None
    if not project:
        raise HTTPException(404, "Project not found")
    page = next(
        (
            item
            for item in (job.checkpoint or {}).get("pages", [])
            if item.get("slideId") == slide_id and item.get("status") == "ready"
        ),
        None,
    )
    if not page or not page.get("artifactRoot"):
        raise HTTPException(404, "Page preview is not ready")
    project_root = Path(project.artifact_path).resolve()
    candidate_root = Path(page["artifactRoot"]).resolve()
    if not candidate_root.is_relative_to(project_root):
        raise HTTPException(403, "Invalid page artifact path")
    current_path = candidate_root / "current.json"
    if not current_path.is_file():
        raise HTTPException(404, "Page preview is not ready")
    current = json.loads(current_path.read_text(encoding="utf-8"))
    preview = (candidate_root / f"{current['variant']}.png").resolve()
    if not preview.is_relative_to(candidate_root) or not preview.is_file():
        raise HTTPException(404, "Page preview is not ready")
    return FileResponse(preview, media_type="image/png", headers={"Cache-Control": "no-store"})


def _sse_payload(job: Job, event_type: str = "snapshot") -> dict:
    return {
        "type": event_type,
        "id": job.id,
        "job_id": job.id,
        "project_id": job.project_id,
        "kind": job.kind,
        "status": job.status,
        "progress": job.progress,
        "checkpoint": job.checkpoint or {},
        "error": job.error,
    }


@router.get("/jobs/{job_id}/events")
async def stream_job_events(job_id: str, request: Request, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    queue = job_manager.open_subscription(job_id)
    initial = _sse_payload(job)

    async def events():
        try:
            yield f"data: {json.dumps(initial, ensure_ascii=False)}\n\n"
            if initial["status"] in {"completed", "failed", "cancelled"}:
                return
            while not await request.is_disconnected():
                payload = await job_manager.next_event(queue)
                if settings.private_accounts_mode:
                    from app.security.accounts import private_user
                    if not private_user(request):
                        return
                if payload is None:
                    # Re-read the durable snapshot on heartbeat as an additional
                    # safeguard against process-local transport loss.
                    with SessionLocal() as snapshot_db:
                        current = snapshot_db.get(Job, job_id)
                        if current and current.status in {"completed", "failed", "cancelled"}:
                            final = _sse_payload(current, current.status)
                            yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
                            return
                    yield ": heartbeat\n\n"
                    continue
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if payload.get("status") in {"completed", "failed", "cancelled"}:
                    return
        finally:
            job_manager.close_subscription(job_id, queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.websocket("/jobs/{job_id}/events")
async def job_events(job_id: str, websocket: WebSocket):
    from app.security.public_access import current_user
    from app.security.accounts import authorize_project
    if settings.private_accounts_mode or settings.public_test_mode:
        user = current_user(websocket)
        if not user:
            await websocket.close(code=4401)
            return
        if settings.private_accounts_mode:
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                try:
                    authorize_project(db, job.project_id if job else None, user.get("id"))
                except HTTPException:
                    await websocket.close(code=4404)
                    return
    await job_manager.connect(job_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        job_manager.disconnect(job_id, websocket)
