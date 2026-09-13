import copy
import json
from pathlib import Path
from typing import Literal

from app.personalization.runtime import guarded_sync_generation, lock, assert_current
from app.api.dependencies import project_or_404
from app.db.models import (
    ExportRecord,
    DeckSpecRecord,
    DeliveryVerification,
    ImportedDeck,
    ImportedObjectEdit,
    Project,
    SlideSpecRecord,
    SlideVersion,
)
from app.db.session import get_db
from app.powerpoint import (
    apply_generated_effects,
    export_roundtrip,
    inspect_pptx,
    update_imported_object,
)
from app.presentation_engine.service import EngineError, presentation_engine
from app.professional import audit_delivery_profile
from app.security.public_access import current_user
from app.slides import load_slides
from app.templates.native_fill import fill_native_template
from app.validation.render_freshness import matches_render_stamp
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1")


class PowerPointEffectsRequest(BaseModel):
    transition: Literal["none", "fade", "push", "wipe"] = "fade"
    transition_speed: Literal["slow", "med", "fast"] = "med"
    animation: Literal["none", "fade"] = "none"


class ImportedObjectRequest(BaseModel):
    value: str = Field(max_length=4000)


class NarrationRequest(BaseModel):
    slide_id: str | None = None
    locale: Literal["zh-CN", "en-US"] = "zh-CN"
    words_per_minute: int = Field(default=220, ge=100, le=320)


def export_path(project: Project, format_name: str) -> Path:
    return Path(project.artifact_path) / "exports" / f"presentation.{format_name}"


def ensure_current_preview(project: Project, slides: list[dict]) -> None:
    root = Path(project.artifact_path) / "slides" / "rendered" / "slides"
    stale = []
    cache = {}
    for slide in slides:
        try:
            current = json.loads((root / str(slide["position"]) / "current.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            current = {}
        detail = current.get("scoreDetail") or {}
        selected = (slide.get("visualIntent") or {}).get("selectedVariant")
        if not matches_render_stamp(detail.get("renderStamp"), slide, cache) or (selected and selected != current.get("variant")):
            stale.append(slide["position"])
    if stale or not slides:
        raise HTTPException(409, {"message": "页面预览尚未生成或已过期，请重新生成后导出", "positions": stale})


def require_final_quality(project_id, db, stage):
    if stage == "final":
        from app.api.quality_routes import validate
        report = validate(project_id, db)
        if not report.get("passed"):
            raise HTTPException(409, "正式交付质量检查未通过，请在质量中心完成修复；草稿仍可导出供检查")


def verify_pptx_file(target, slides):
    import hashlib
    analysis = inspect_pptx(target.read_bytes())
    if analysis["slideCount"] != len(slides) or any(not item["objects"] for item in analysis["slides"]):
        raise HTTPException(409, "PPTX 实际文件检查失败：页面或对象缺失")
    return {"sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "verifiedSlideCount": analysis["slideCount"],
            "inspection": "实际 OOXML 页面与对象检查；目标桌面软件的最终显示仍需核对"}


@router.get("/projects/{project_id}/export/html")
@router.post("/projects/{project_id}/export/html")
def export_html(project_id: str, stage: Literal["draft", "final"] = "draft", db: Session = Depends(get_db)):
    require_final_quality(project_id, db, stage)
    project = project_or_404(project_id, db)
    source = Path(project.artifact_path) / "slides" / "rendered" / "index.html"
    if not source.exists():
        raise HTTPException(409, "Generate slides first")
    ensure_current_preview(project, load_slides(project_id, db))
    # Assemble selected candidates so partial edits cannot leave an older deck index.
    presentation_engine.run("assemble", load_slides(project_id, db), source.parent)
    target = export_path(project, "html")
    target.write_bytes(source.read_bytes())
    db.add(ExportRecord(project_id=project_id, format="html", artifact_path=str(target), report={}))
    db.commit()
    return FileResponse(target)


@router.get("/projects/{project_id}/export/pptx")
@router.post("/projects/{project_id}/export/pptx")
@guarded_sync_generation
def export_pptx(
    project_id: str,
    profile: Literal["powerpoint-windows", "powerpoint-macos", "wps", "libreoffice"] | None = None,
    stage: Literal["draft", "final"] = "draft",
    db: Session = Depends(get_db),
):
    require_final_quality(project_id, db, stage)
    from app.db.models import PersonalBinding
    binding = db.get(PersonalBinding, project_id)
    profile = profile or ((binding.snapshot.get("preferences") or {}).get("delivery_profile") if binding else None) or "powerpoint-windows"
    project = project_or_404(project_id, db)
    slides = load_slides(project_id, db)
    target = export_path(project, "pptx")
    if not slides:
        raise HTTPException(409, "Generate an outline first")
    reference_report = None
    deck_record = db.get(DeckSpecRecord, project_id)
    requested = (deck_record.reproducibility or {}).get("request", {}) if deck_record else {}
    explicit_visual = bool(requested.get("skillIds") or requested.get("professionalBrief", {}).get("brandName"))
    native_reference = binding.snapshot.get("reference") if binding and not explicit_visual else None
    import hashlib
    source_fingerprint = hashlib.sha256(json.dumps({"slides": slides, "reference": native_reference}, sort_keys=True).encode()).hexdigest()
    if native_reference and stage == "final":
        digest = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else ""
        approved = db.scalar(select(DeliveryVerification).where(DeliveryVerification.project_id == project_id,
            DeliveryVerification.file_hash == digest, DeliveryVerification.software == profile, DeliveryVerification.status == "accepted"))
        exported = db.scalar(select(ExportRecord).where(ExportRecord.project_id == project_id, ExportRecord.format == "pptx").order_by(ExportRecord.created_at.desc()))
        if not approved or not exported or exported.report.get("sourceFingerprint") != source_fingerprint:
            raise HTTPException(409, "原生参考母版需要先导出草稿，在所选交付软件中完成实际验收，再下载正式稿")
        return FileResponse(target, filename=target.name)
    with lock:
        assert_current()
        if native_reference:
            from app.db.models import PersonalReference, PersonalIdentity
            from app.personalization.private_files import reference_root
            reference = db.get(PersonalReference, native_reference["id"])
            owner = db.get(PersonalIdentity, binding.owner_id)
            if not reference or reference.owner_id != binding.owner_id or owner.epoch != binding.snapshot.get("epoch"):
                raise HTTPException(409, "参考模板已失效，请重新规划")
            reference_report = fill_native_template((reference_root(reference) / "reference.pptx").read_bytes(), slides, target)
        else:
            presentation_engine.run("pptx", slides, target)
        from app.personalization.roundtrip_learning import annotate_export
        annotate_export(target, project_id, slides)
        effects_report = apply_generated_effects(target, slides)
        scene_path = Path(project.artifact_path) / "slides" / "rendered" / "scene-ir.json"
        scene_deck = json.loads(scene_path.read_text(encoding="utf-8")) if scene_path.exists() else {"slides": []}
        nodes = [node for scene in scene_deck.get("slides", []) for node in scene.get("nodes", [])]
        degraded = [node for node in nodes if node.get("preferredExport") != "native"]
        unsupported = [node for node in nodes if node.get("type") in {"image", "svg"}]
        report = {
            "deliveryStage": stage,
            "referenceTemplate": reference_report,
            "sourceFingerprint": source_fingerprint,
            "fileVerification": verify_pptx_file(target, slides),
            "mode": "balanced",
            "sceneIR": scene_deck.get("version"),
            "compilerBackend": "semantic-native-pptx-v2",
            "nativeObjects": sum(node.get("preferredExport") == "native" for node in nodes),
            "fallbackObjects": len(degraded),
            "degradations": [
                "阴影、渐变和复杂 CSS 表面效果会简化为 PowerPoint 原生形状",
                *([f"{len(unsupported)} 个图像或 SVG 对象需要栅格化或人工复核"] if unsupported else []),
            ],
            "majorMissingObjects": len(unsupported),
            "powerPointEffects": effects_report,
            "deliveryAudit": audit_delivery_profile(slides, profile),
        }
        (target.parent / "pptx-degradation-report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        db.add(
            ExportRecord(project_id=project_id, format="pptx", artifact_path=str(target), report=report)
        )
        db.commit()
        return FileResponse(target, filename=target.name)



@router.get("/projects/{project_id}/slides/{slide_id}/export/pptx")
@router.post("/projects/{project_id}/slides/{slide_id}/export/pptx")
def export_single_slide_pptx(project_id: str, slide_id: str, db: Session = Depends(get_db)):
    project = project_or_404(project_id, db)
    row = db.get(SlideSpecRecord, slide_id)
    if not row or row.project_id != project_id:
        raise HTTPException(404, "Slide not found")
    target = Path(project.artifact_path) / "exports" / "slides" / f"slide-{row.position:02d}.pptx"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        presentation_engine.run("pptx", [copy.deepcopy(row.spec)], target)
        effects_report = apply_generated_effects(target, [copy.deepcopy(row.spec)])
    except EngineError as exc:
        raise HTTPException(500, str(exc)) from exc
    db.add(ExportRecord(
        project_id=project_id, format="slide-pptx", artifact_path=str(target),
        report={"slideId": slide_id, "position": row.position, "partial": True, "powerPointEffects": effects_report},
    ))
    db.commit()
    return FileResponse(target, filename=target.name)


@router.get("/projects/{project_id}/export/pdf")
@router.post("/projects/{project_id}/export/pdf")
def export_pdf(project_id: str, stage: Literal["draft", "final"] = "draft", db: Session = Depends(get_db)):
    require_final_quality(project_id, db, stage)
    project = project_or_404(project_id, db)
    source = Path(project.artifact_path) / "slides" / "rendered" / "index.html"
    if not source.exists():
        raise HTTPException(409, "Generate slides first")
    ensure_current_preview(project, load_slides(project_id, db))
    presentation_engine.run("assemble", load_slides(project_id, db), source.parent)
    target = export_path(project, "pdf")
    presentation_engine.export_pdf(source, target)
    db.add(ExportRecord(project_id=project_id, format="pdf", artifact_path=str(target), report={}))
    db.commit()
    return FileResponse(target, filename=target.name)


@router.post("/projects/{project_id}/export/template-pptx")
async def export_template_pptx(
    project_id: str, template: UploadFile = File(...), db: Session = Depends(get_db)
):
    project = project_or_404(project_id, db)
    slides = load_slides(project_id, db)
    if not slides:
        raise HTTPException(409, "Generate an outline first")
    target = Path(project.artifact_path) / "exports" / "template-filled.pptx"
    try:
        report = fill_native_template(await template.read(), slides, target)
    except Exception as exc:
        raise HTTPException(422, f"Invalid PowerPoint template: {exc}") from exc
    db.add(
        ExportRecord(
            project_id=project_id, format="template-pptx", artifact_path=str(target), report=report
        )
    )
    db.commit()
    return FileResponse(target, filename=target.name)


@router.post("/projects/{project_id}/slides/{slide_id}/powerpoint-effects")
def set_powerpoint_effects(
    project_id: str,
    slide_id: str,
    body: PowerPointEffectsRequest,
    db: Session = Depends(get_db),
):
    project_or_404(project_id, db)
    row = db.get(SlideSpecRecord, slide_id)
    if not row or row.project_id != project_id:
        raise HTTPException(404, "Slide not found")
    spec = copy.deepcopy(row.spec)
    spec["powerPoint"] = {
        "transition": body.transition,
        "transitionSpeed": body.transition_speed,
        "animation": body.animation,
    }
    row.current_version += 1
    row.spec = spec
    db.add(SlideVersion(
        slide_id=row.id, version=row.current_version, spec=spec,
        reason="powerpoint-effects",
    ))
    db.commit()
    return {"slide": spec, "version": row.current_version, "effects": spec["powerPoint"]}


@router.post("/projects/{project_id}/narration")
def generate_narration(
    project_id: str, body: NarrationRequest, db: Session = Depends(get_db)
):
    project_or_404(project_id, db)
    rows = list(db.scalars(
        select(SlideSpecRecord)
        .where(SlideSpecRecord.project_id == project_id)
        .order_by(SlideSpecRecord.position)
    ))
    if body.slide_id:
        rows = [row for row in rows if row.id == body.slide_id]
    if not rows:
        raise HTTPException(404, "Slide not found")
    result = []
    for row in rows:
        spec = copy.deepcopy(row.spec)
        title = str(spec.get("content", {}).get("title", ""))
        message = str(spec.get("message", ""))
        bullets = [str(item) for item in spec.get("content", {}).get("bullets", [])[:3]]
        transition = str(spec.get("speakerIntent", {}).get("transition", "继续下一页"))
        if body.locale == "en-US":
            narration = f"This slide explains {title}. {message}. " + " ".join(bullets)
        else:
            details = "；".join(bullets)
            narration = f"这一页说明{title}。{message}"
            if details:
                narration += f"。重点包括：{details}"
            narration += f"。接下来，{transition}。"
        intent = copy.deepcopy(spec.get("speakerIntent", {}))
        intent["narration"] = narration
        intent["narrationLocale"] = body.locale
        intent["estimatedSeconds"] = max(8, round(len(narration) * 60 / body.words_per_minute))
        spec["speakerIntent"] = intent
        row.current_version += 1
        row.spec = spec
        db.add(SlideVersion(
            slide_id=row.id, version=row.current_version, spec=spec,
            reason="narration-generated",
        ))
        result.append({
            "slideId": row.id, "position": row.position,
            "narration": narration, "estimatedSeconds": intent["estimatedSeconds"],
        })
    db.commit()
    return {"locale": body.locale, "slides": result, "totalSeconds": sum(item["estimatedSeconds"] for item in result)}


@router.post("/projects/{project_id}/powerpoint/import", status_code=201)
async def import_powerpoint(
    project_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)
):
    project = project_or_404(project_id, db)
    if Path(file.filename or "").suffix.lower() != ".pptx":
        raise HTTPException(415, "Only .pptx files can be imported")
    payload = await file.read()
    try:
        analysis = inspect_pptx(payload)
    except Exception as exc:
        raise HTTPException(422, f"Invalid PowerPoint file: {exc}") from exc
    folder = Path(project.artifact_path) / "powerpoint" / "imported"
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / "original.pptx"
    source.write_bytes(payload)
    analysis["_workingPath"] = str(source)
    existing = db.scalar(select(ImportedDeck).where(ImportedDeck.project_id == project_id))
    if existing:
        existing.source_name = Path(file.filename or "imported.pptx").name
        existing.artifact_path = str(source)
        existing.analysis = analysis
        existing.current_version = 1
        row = existing
    else:
        row = ImportedDeck(
            project_id=project_id, source_name=Path(file.filename or "imported.pptx").name,
            artifact_path=str(source), analysis=analysis,
        )
        db.add(row)
    db.commit()
    return {
        "id": row.id, "sourceName": row.source_name, "version": row.current_version,
        "analysis": {key: value for key, value in analysis.items() if not key.startswith("_")},
    }


@router.post("/projects/{project_id}/powerpoint/slides/{slide_index}/objects/{object_id}")
def edit_imported_powerpoint_object(
    project_id: str,
    slide_index: int,
    object_id: str,
    body: ImportedObjectRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    project = project_or_404(project_id, db)
    imported = db.scalar(select(ImportedDeck).where(ImportedDeck.project_id == project_id))
    if not imported:
        raise HTTPException(404, "Import a PowerPoint file first")
    current = Path((imported.analysis or {}).get("_workingPath", imported.artifact_path))
    next_version = imported.current_version + 1
    target = Path(project.artifact_path) / "powerpoint" / "imported" / f"working-v{next_version}.pptx"
    try:
        before, after = update_imported_object(current, target, slide_index, object_id, body.value)
        analysis = inspect_pptx(target.read_bytes())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    analysis["_workingPath"] = str(target)
    imported.analysis = analysis
    imported.current_version = next_version
    actor = (current_user(request) or {}).get("name", "本机管理员")
    db.add(ImportedObjectEdit(
        imported_deck_id=imported.id, slide_index=slide_index, object_id=object_id,
        before_text=before, after_text=after, actor=actor, version=next_version,
    ))
    db.commit()
    return {
        "version": next_version, "slide": analysis["slides"][slide_index - 1],
        "fidelity": {"themeCount": analysis["themeCount"], "masterCount": analysis["masterCount"], "layoutCount": analysis["layoutCount"]},
    }


@router.get("/projects/{project_id}/powerpoint/edits")
def imported_powerpoint_edits(project_id: str, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    imported = db.scalar(select(ImportedDeck).where(ImportedDeck.project_id == project_id))
    if not imported:
        return []
    return [
        {
            "id": row.id, "slideIndex": row.slide_index, "objectId": row.object_id,
            "before": row.before_text, "after": row.after_text, "actor": row.actor,
            "version": row.version,
        }
        for row in db.scalars(
            select(ImportedObjectEdit)
            .where(ImportedObjectEdit.imported_deck_id == imported.id)
            .order_by(ImportedObjectEdit.created_at.desc())
        )
    ]


@router.get("/projects/{project_id}/powerpoint/export")
@router.post("/projects/{project_id}/powerpoint/export")
def export_imported_powerpoint(project_id: str, db: Session = Depends(get_db)):
    project = project_or_404(project_id, db)
    imported = db.scalar(select(ImportedDeck).where(ImportedDeck.project_id == project_id))
    if not imported:
        raise HTTPException(404, "Import a PowerPoint file first")
    current = Path((imported.analysis or {}).get("_workingPath", imported.artifact_path))
    target = Path(project.artifact_path) / "exports" / "imported-roundtrip.pptx"
    report = export_roundtrip(current, target, Path(imported.artifact_path))
    db.add(ExportRecord(
        project_id=project_id, format="imported-pptx", artifact_path=str(target), report=report,
    ))
    db.commit()
    return FileResponse(target, filename=target.name, headers={
        "X-PowerPoint-Fidelity": "preserved" if not report["changedFidelityParts"] else "review",
    })

