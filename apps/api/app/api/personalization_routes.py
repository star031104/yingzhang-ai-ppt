from app.db.models import PersonalBinding, PersonalFeedback, PersonalMemory, PersonalProfile
from app.db.session import get_db
from app.personalization import service
from app.personalization.runtime import lock
from app.personalization.schemas import (
    LABELS,
    OPTIONS,
    MemoryCreate,
    ProfileCreate,
    ProfileImport,
    ProfileUpdate,
    ResetExecute,
    ResetPreview,
    RevisionRequest,
)
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import delete, select

router = APIRouter(prefix="/api/v1", dependencies=[Depends(service.require_local)])


@router.get("/me/profiles")
def list_profiles(db=Depends(get_db)):
    with lock:
        owner = service.identity(db)
        from app.personalization.cases import drain_outbox
        drain_outbox(db, owner)
        rows = db.scalars(
            select(PersonalProfile)
            .where(PersonalProfile.owner_id == owner.id)
            .order_by(PersonalProfile.created_at)
        ).all()
        result = {
            "profiles": [service.profile_view(db, row) for row in rows],
            "epoch": owner.epoch,
            "options": OPTIONS,
            "labels": LABELS,
            "mode": "local-personal",
        }
        db.commit()
        return result


@router.post("/me/profiles", status_code=201)
def create_profile(body: ProfileCreate, db=Depends(get_db)):
    with lock:
        owner = service.identity(db)
        row = PersonalProfile(owner_id=owner.id, **body.model_dump())
        db.add(row)
        db.commit()
        return service.profile_view(db, row)


@router.patch("/me/profiles/{profile_id}")
def update_profile(profile_id: str, body: ProfileUpdate, db=Depends(get_db)):
    with lock:
        row = service.profile(db, profile_id)
        service.check_revision(row, body.revision)
        for key, value in body.model_dump(exclude={"revision"}).items():
            setattr(row, key, value)
        row.revision += 1
        if not row.capture_feedback or not row.use_memory:
            db.execute(
                delete(PersonalFeedback).where(
                    PersonalFeedback.profile_id == row.id, PersonalFeedback.status == "pending"
                )
            )
        db.commit()
        return service.profile_view(db, row)


@router.post("/me/profiles/{profile_id}/memories", status_code=201)
def teach(profile_id: str, body: MemoryCreate, db=Depends(get_db)):
    with lock:
        row = service.profile(db, profile_id)
        service.check_revision(row, body.revision)
        item = service.put_memory(db, row, body.key, body.value)
        db.commit()
        return service.memory_view(item)


@router.post("/me/memories/{memory_id}/confirm")
def confirm_memory(memory_id: str, body: RevisionRequest, db=Depends(get_db)):
    with lock:
        owner = service.identity(db)
        item = db.get(PersonalMemory, memory_id)
        if not item or item.owner_id != owner.id:
            raise HTTPException(404, "经验不存在")
        row = service.profile(db, item.profile_id)
        service.check_revision(row, body.revision)
        service.put_memory(
            db, row, item.key, item.value["choice"], origin=item.origin, evidence=item.evidence
        )
        db.commit()
        return service.profile_view(db, row)


@router.get("/me/profiles/{profile_id}/feedback")
def feedback(profile_id: str, db=Depends(get_db)):
    row = service.profile(db, profile_id)
    return [
        service.feedback_view(item)
        for item in db.scalars(
            select(PersonalFeedback)
            .where(
                PersonalFeedback.owner_id == row.owner_id,
                PersonalFeedback.profile_id == row.id,
                PersonalFeedback.status == "pending",
            )
            .order_by(PersonalFeedback.created_at.desc())
            .limit(50)
        )
    ]


@router.post("/me/feedback/{event_id}/confirm")
def confirm_feedback(event_id: str, db=Depends(get_db)):
    with lock:
        return service.confirm_feedback(db, event_id)


@router.delete("/me/feedback/{event_id}")
def reject_feedback(event_id: str, db=Depends(get_db)):
    with lock:
        owner = service.identity(db)
        event = db.get(PersonalFeedback, event_id)
        if not event or event.owner_id != owner.id:
            raise HTTPException(404, "修改建议不存在")
        event.status = "rejected"
        db.commit()
        return {"status": "rejected"}


@router.get("/projects/{project_id}/personalization")
def project_personalization(project_id: str, db=Depends(get_db)):
    from app.api.dependencies import project_or_404

    project_or_404(project_id, db)
    owner = service.identity(db)
    row = db.get(PersonalBinding, project_id)
    return service.describe(row.snapshot if row and row.owner_id == owner.id else None)


@router.post("/me/memory-reset/preview")
def preview_reset(body: ResetPreview, db=Depends(get_db)):
    with lock:
        return service.preview_reset(db, body.scope, body.target_id)


@router.post("/me/memory-reset")
async def execute_reset(body: ResetExecute, db=Depends(get_db)):
    return service.execute_reset(db, body.preview_id, body.digest)


@router.get("/me/profiles/{profile_id}/export")
def export_profile(profile_id: str, db=Depends(get_db)):
    row = service.profile(db, profile_id)
    return {
        "version": 1,
        "name": row.name,
        "scenario": row.scenario,
        "memories": [
            {"key": item.key, "value": item.value["choice"]}
            for item in db.scalars(
                select(PersonalMemory).where(
                    PersonalMemory.profile_id == row.id,
                    PersonalMemory.owner_id == row.owner_id,
                    PersonalMemory.status == "confirmed",
                )
            )
        ],
    }


@router.post("/me/profile-import", status_code=201)
def import_profile(body: ProfileImport, db=Depends(get_db)):
    from app.personalization.schemas import validate_preference

    with lock:
        try:
            config = ProfileCreate(name=body.name, scenario=body.scenario, use_memory=False)
            for item in body.memories:
                if set(item) != {"key", "value"}:
                    raise ValueError("经验包仅允许经验类型和值")
                validate_preference(item["key"], item["value"])
            if len({item["key"] for item in body.memories}) != len(body.memories):
                raise ValueError("经验包包含冲突的重复规则")
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        owner = service.identity(db)
        row = PersonalProfile(owner_id=owner.id, **config.model_dump())
        db.add(row)
        db.flush()
        for item in body.memories:
            service.put_memory(
                db, row, item["key"], item["value"], origin="import", status="candidate"
            )
        db.commit()
        return service.profile_view(db, row)


@router.post("/me/profiles/{profile_id}/reference", status_code=201)
async def learn_reference(
    profile_id: str, file: UploadFile = File(...), revision: int = Form(...), db=Depends(get_db)
):
    from app.personalization.reference import extract_reference

    if not (file.filename or "").lower().endswith(".pptx"):
        raise HTTPException(415, "请选择 PPTX 参考稿")
    data = await file.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "参考稿不能超过 20 MB")
    try:
        value, metadata = extract_reference(data)
    except Exception as exc:
        raise HTTPException(422, "无法读取参考稿，请检查文件完整性及大小（最多 100 页）") from exc
    with lock:
        row = service.profile(db, profile_id)
        service.check_revision(row, revision)
        item = service.put_memory(
            db, row, "reference_style", value, origin="reference", status="candidate"
        )
        db.commit()
        return {
            "suggestions": [service.memory_view(item)],
            **metadata,
            "message": "已提取字体、配色及可支持的页型建议；原文与原文件不保存，请确认后使用。",
        }
