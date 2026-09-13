import hashlib
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.dependencies import project_or_404
from app.db.models import PersonalCase, PersonalReference
from app.db.session import get_db
from app.personalization import cases, service
from app.personalization.private_files import reference_root, reference_view, save_reference, validate_pptx
from app.personalization.runtime import lock
from app.personalization.schemas import RevisionRequest
from app.slides import load_slides

router = APIRouter(prefix="/api/v1", dependencies=[Depends(service.require_local)])


class CaptureCase(BaseModel):
    project_id: str
    label: str = Field(min_length=1, max_length=120)
    revision: int = Field(ge=1)


class AcceptCaseRequest(RevisionRequest):
    reviewed_imported_example: bool = False


@router.get("/me/profiles/{profile_id}/experience")
def experience(profile_id: str, db=Depends(get_db)):
    profile = service.profile(db, profile_id)
    return {"cases": [cases.case_view(row) for row in db.scalars(select(PersonalCase).where(PersonalCase.profile_id == profile.id))],
            "references": [reference_view(row) for row in db.scalars(select(PersonalReference).where(PersonalReference.profile_id == profile.id))]}


@router.post("/me/profiles/{profile_id}/cases", status_code=201)
def capture_case(profile_id: str, body: CaptureCase, db=Depends(get_db)):
    from app.api.quality_routes import validate
    with lock:
        config = service.profile(db, profile_id)
        service.check_revision(config, body.revision)
        project = project_or_404(body.project_id, db)
        slides = load_slides(project.id, db)
        if not slides:
            raise HTTPException(409, "请先完成一份作品")
        quality = validate(project.id, db)
        row = cases.capture_project_case(db, config, project, slides, body.label, quality)
        db.commit()
        return cases.case_view(row)


@router.post("/me/profiles/{profile_id}/cases/{case_id}/confirm")
def accept_case(profile_id: str, case_id: str, body: AcceptCaseRequest, db=Depends(get_db)):
    with lock:
        profile = service.profile(db, profile_id)
        service.check_revision(profile, body.revision)
        row = db.get(PersonalCase, case_id)
        if not row or row.profile_id != profile.id or row.owner_id != profile.owner_id:
            raise HTTPException(404, "案例不存在")
        if row.project_id:
            from app.api.quality_routes import validate
            slides = load_slides(row.project_id, db)
            digest = hashlib.sha256(json.dumps(slides, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if digest != row.source_hash:
                raise HTTPException(409, "来源作品已修改，请重新采集案例")
            if not validate(row.project_id, db).get("passed"):
                raise HTTPException(409, "来源作品当前尚未通过质量检查")
        if not row.project_id and row.features.get("quality", {}).get("imported"):
            if not body.reviewed_imported_example:
                raise HTTPException(422, "请先查看导入案例并明确确认其适用性")
            row.features = {**row.features, "quality": {"passed": True, "imported": True, "humanReviewed": True}}
        cases.confirm_case(db, profile, row)
        db.commit()
        return cases.case_view(row)


@router.delete("/me/profiles/{profile_id}/cases/{case_id}")
def forget_case(profile_id: str, case_id: str, db=Depends(get_db)):
    with lock:
        profile = service.profile(db, profile_id)
        cases.delete_case(db, profile, case_id)
        # Invalidate frozen examples and queued learning, not the remaining rules.
        from app.personalization.lifecycle import invalidate_profile
        invalidate_profile(db, profile)
        db.commit()
        return {"status": "forgotten"}


@router.post("/me/profiles/{profile_id}/reference-template", status_code=201)
async def retain_template(profile_id: str, file: UploadFile = File(...), revision: int = Form(...),
                          retain_original: bool = Form(False), db=Depends(get_db)):
    if not retain_original:
        raise HTTPException(422, "保存原生模板需要明确选择保留原文件")
    data = await file.read(20 * 1024 * 1024 + 1)
    validate_pptx(data)
    from app.personalization.reference import extract_reference
    value, metadata = extract_reference(data)
    with lock:
        profile = service.profile(db, profile_id)
        service.check_revision(profile, revision)
        reference = save_reference(db, profile, file.filename or "参考稿.pptx", data, metadata)
        service.put_memory(db, profile, "reference_style", value, origin="reference", status="candidate", evidence=[reference.id])
        db.commit()
        return reference_view(reference)


@router.post("/me/profiles/{profile_id}/references/{reference_id}/activate")
def activate_reference(profile_id: str, reference_id: str, body: RevisionRequest, db=Depends(get_db)):
    with lock:
        profile = service.profile(db, profile_id)
        service.check_revision(profile, body.revision)
        row = db.get(PersonalReference, reference_id)
        if not row or row.profile_id != profile.id or row.owner_id != profile.owner_id:
            raise HTTPException(404, "参考稿不存在")
        for other in db.scalars(select(PersonalReference).where(PersonalReference.profile_id == profile.id)):
            other.active = other.id == row.id
        profile.revision += 1
        db.commit()
        return reference_view(row)


@router.delete("/me/profiles/{profile_id}/references/{reference_id}")
def forget_reference(profile_id: str, reference_id: str, db=Depends(get_db)):
    from app.personalization.private_files import erase_private_reference
    from app.personalization.lifecycle import invalidate_profile, delete_derived_rules
    with lock:
        profile = service.profile(db, profile_id)
        row = db.get(PersonalReference, reference_id)
        if not row or row.profile_id != profile.id or row.owner_id != profile.owner_id:
            raise HTTPException(404, "参考稿不存在")
        erase_private_reference(row)
        delete_derived_rules(db, profile, [reference_id])
        db.delete(row)
        profile.revision += 1
        invalidate_profile(db, profile)
        db.commit()
        return {"status": "forgotten"}


class ReferencePreview(BaseModel):
    software: Literal["libreoffice", "powerpoint-windows", "wps"] = "libreoffice"


@router.post("/me/profiles/{profile_id}/references/{reference_id}/preview")
async def preview_reference(profile_id: str, reference_id: str, body: ReferencePreview = ReferencePreview(), db=Depends(get_db)):
    import asyncio
    from app.personalization.office import render_office
    from app.personalization.runtime import generation_snapshot, assert_current
    profile = service.profile(db, profile_id)
    row = db.get(PersonalReference, reference_id)
    if not row or row.profile_id != profile.id or row.owner_id != profile.owner_id:
        raise HTTPException(404, "参考稿不存在")
    snapshot = service.freeze(db, profile, profile.scenario)
    token = generation_snapshot.set(snapshot)
    try:
        root = reference_root(row)
        # Render in a temporary sibling directory, promote only under current epoch.
        import tempfile
        import shutil
        with tempfile.TemporaryDirectory(prefix=".reference-preview-", dir=root.parent) as folder:
            staged = Path(folder)
            shutil.copy2(root / "reference.pptx", staged / "reference.pptx")
            result = await asyncio.to_thread(render_office, staged / "reference.pptx", staged / "preview", body.software)
            with lock:
                assert_current()
                target = root / "preview"
                if target.exists():
                    shutil.rmtree(target)
                if (staged / "preview").exists():
                    shutil.copytree(staged / "preview", target)
                safe = {**result, "pages": [{k: v for k, v in page.items() if k != "text"} for page in result.get("pages", [])]}
                row.analysis = {**row.analysis, "preview": safe}
                db.commit()
                return safe
    finally:
        generation_snapshot.reset(token)


@router.get("/me/profiles/{profile_id}/references/{reference_id}/pages/{page}")
def reference_page(profile_id: str, reference_id: str, page: int, db=Depends(get_db)):
    profile = service.profile(db, profile_id)
    row = db.get(PersonalReference, reference_id)
    if not row or row.profile_id != profile.id or row.owner_id != profile.owner_id or not 1 <= page <= 100:
        raise HTTPException(404, "参考页不存在")
    target = reference_root(row) / "preview" / f"page-{page}.png"
    if not target.is_file():
        raise HTTPException(404, "请先生成参考预览")
    return FileResponse(target, headers={"Cache-Control": "no-store"})


@router.get("/me/capabilities")
def local_capabilities():
    from app.personalization.office import capabilities
    return capabilities()


class PackExport(BaseModel):
    include_original_references: bool = False


@router.post("/me/profiles/{profile_id}/experience-pack")
def export_experience_pack(profile_id: str, body: PackExport, db=Depends(get_db)):
    from app.personalization.experience_pack import export_pack
    profile = service.profile(db, profile_id)
    return export_pack(db, profile, body.include_original_references)


@router.post("/me/experience-pack-import", status_code=201)
async def import_experience_pack(file: UploadFile = File(...), retain_originals: bool = Form(False), db=Depends(get_db)):
    import base64
    from app.db.models import PersonalProfile
    from app.personalization.experience_pack import validate_pack
    from app.personalization.schemas import ProfileCreate
    from app.personalization.reference import extract_reference
    data = await file.read(30 * 1024 * 1024 + 1)
    if len(data) > 30 * 1024 * 1024:
        raise HTTPException(413, "经验包不能超过 30 MB")
    try:
        payload = validate_pack(json.loads(data))
        config = ProfileCreate(name=payload["name"], scenario=payload["scenario"], use_memory=False)
        for example in payload.get("cases", []):
            ProfileCreate(name=example["label"], scenario=example["scenario"])
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, "经验包不完整或包含不支持的内容") from exc
    if payload.get("references") and not retain_originals:
        raise HTTPException(422, "经验包含原始参考文件，请明确选择保留原文件")
    with lock:
        owner = service.identity(db)
        profile = PersonalProfile(owner_id=owner.id, **config.model_dump())
        db.add(profile)
        db.flush()
        saved = []
        try:
            for rule in payload.get("memories", []):
                service.put_memory(db, profile, rule["key"], rule["value"], origin="import", status="candidate")
            for example in payload.get("cases", []):
                digest = hashlib.sha256(json.dumps(example["features"], sort_keys=True).encode()).hexdigest()
                db.add(PersonalCase(owner_id=owner.id, profile_id=profile.id, label=example["label"], scenario=example["scenario"],
                                    features=example["features"], source_hash=digest))
            for reference in payload.get("references", []):
                original = base64.b64decode(reference["pptx"], validate=True)
                _, analysis = extract_reference(original)
                saved.append(save_reference(db, profile, reference["name"], original, analysis))
            db.commit()
        except Exception:
            from app.personalization.private_files import erase_private_reference
            for reference in saved:
                erase_private_reference(reference)
            db.rollback()
            raise
        return service.profile_view(db, profile)
