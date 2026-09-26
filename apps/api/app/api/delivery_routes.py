import copy
import hashlib
import json
import os
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Literal

from app.api.dependencies import project_or_404
from app.db.models import (
    DeckSpecRecord,
    DeliveryVerification,
    ExportRecord,
    ImportedDeck,
    ImportedObjectEdit,
    Project,
    SlideSpecRecord,
    SlideVersion,
)
from app.db.session import get_db
from app.evaluation.fingerprints import export_source_fingerprint
from app.personalization.runtime import assert_current, guarded_sync_generation, lock
from app.powerpoint import (
    apply_generated_effects,
    export_roundtrip,
    inspect_pptx,
    update_imported_object,
)
from app.presentation_engine.service import EngineError, presentation_engine
from app.professional import audit_delivery_profile
from app.security.public_access import current_user
from app.security.uploads import read_upload_limited
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


def immutable_export_path(project: Project, format_name: str) -> Path:
    """Allocate a unique artifact path so an export record never points at mutable bytes."""
    root = Path(project.artifact_path) / "exports" / "versions"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{uuid.uuid4().hex}.{format_name}"


def publish_latest_export(source: Path, latest: Path) -> None:
    """Keep the legacy latest-export path for desktop verification workflows."""
    latest.parent.mkdir(parents=True, exist_ok=True)
    temporary = latest.with_name(f".{latest.name}.{uuid.uuid4().hex}.tmp")
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, latest)
    finally:
        temporary.unlink(missing_ok=True)


def artifact_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_versioned_export(project: Project, path: Path) -> bool:
    version_root = (Path(project.artifact_path) / "exports" / "versions").resolve()
    try:
        return path.resolve().parent == version_root
    except OSError:
        return False


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


def assemble_delivery_html(project: Project, slides: list[dict], command: str = "assemble") -> Path:
    source = Path(project.artifact_path) / "slides" / "rendered"
    try:
        presentation_engine.run(command, slides, source)
    except EngineError as exc:
        if "超过 50 MB" in str(exc):
            raise HTTPException(413, "音视频素材总量超过单文件 HTML 的 50 MB 限制，请压缩或减少素材") from exc
        raise HTTPException(409, "页面预览无法组装，请重新生成页面后重试") from exc
    return source / "index.html"


def html_media_bytes(slides: list[dict]) -> int:
    total = 0
    for slide in slides:
        for asset in slide.get("assetBindings") or []:
            if asset.get("type") not in {"licensed-video", "licensed-audio"}:
                continue
            try:
                total += Path(asset["path"]).stat().st_size
            except (KeyError, OSError):
                raise HTTPException(409, "绑定的音视频素材缺失，请重新绑定素材")
    return total


def create_html_bundle(project: Project, slides: list[dict], target: Path) -> Path:
    work = target.with_suffix(".bundle")
    if work.exists():
        shutil.rmtree(work)
    try:
        shutil.copytree(Path(project.artifact_path) / "slides" / "rendered", work)
        presentation_engine.run("assemble-bundle", slides, work)
        index = work / "index.html"
        html = index.read_text(encoding="utf-8")
        media_files = {}
        for slide in slides:
            for asset in slide.get("assetBindings") or []:
                if asset.get("type") not in {"licensed-video", "licensed-audio"}:
                    continue
                media = Path(asset.get("path", "")).resolve()
                if not media.is_file():
                    raise HTTPException(409, "绑定的音视频素材缺失，请重新绑定素材")
                relative = f"assets/{artifact_sha256(media)}{media.suffix.lower()}"
                html = html.replace(media.as_uri(), relative)
                media_files[relative] = media
        if "file:" in html:
            raise HTTPException(409, "无法安全打包本机媒体素材，请重新绑定并生成页面")
        index.write_text(html, encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.write(index, "presentation.html")
            for relative, media in media_files.items():
                archive.write(media, relative)
        publish_latest_export(target, export_path(project, "html").with_name("presentation-html.zip"))
        export_path(project, "html").unlink(missing_ok=True)
        return target
    finally:
        shutil.rmtree(work, ignore_errors=True)


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
def export_html(
    project_id: str,
    request: Request,
    stage: Literal["draft", "final"] = "draft",
    db: Session = Depends(get_db),
):
    project = project_or_404(project_id, db)
    source = Path(project.artifact_path) / "slides" / "rendered" / "index.html"
    if not source.exists():
        raise HTTPException(409, "Generate slides first")
    slides = load_slides(project_id, db)
    if request.query_params.get("preview") is not None:
        if stage == "final":
            require_final_quality(project_id, db, stage)
        ensure_current_preview(project, slides)
        if "file:" in source.read_text(encoding="utf-8"):
            raise HTTPException(413, "音视频素材总量超过单文件 HTML 的 50 MB 限制，请压缩素材后查看便携预览")
        return FileResponse(source, media_type="text/html", headers={"Cache-Control": "no-store"})
    require_final_quality(project_id, db, stage)
    ensure_current_preview(project, slides)
    # Assemble selected candidates so partial edits cannot leave an older deck index.
    bundled = html_media_bytes(slides) > 50 * 1024 * 1024
    if bundled:
        target = immutable_export_path(project, "zip")
        create_html_bundle(project, slides, target)
    else:
        source = assemble_delivery_html(project, slides)
        target = immutable_export_path(project, "html")
        target.write_bytes(source.read_bytes())
        publish_latest_export(target, export_path(project, "html"))
        export_path(project, "html").with_name("presentation-html.zip").unlink(missing_ok=True)
    report = {"sourceFingerprint": export_source_fingerprint(slides), "deliveryStage": stage,
              "artifactSha256": artifact_sha256(target), "portableBundle": bundled}
    db.add(ExportRecord(
        project_id=project_id,
        format="html",
        artifact_path=str(target),
        report=report,
    ))
    db.commit()
    return FileResponse(target, filename="presentation-html.zip" if bundled else "presentation.html")


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
    target = immutable_export_path(project, "pptx")
    if not slides:
        raise HTTPException(409, "Generate an outline first")
    reference_report = None
    deck_record = db.get(DeckSpecRecord, project_id)
    requested = (deck_record.reproducibility or {}).get("request", {}) if deck_record else {}
    explicit_visual = bool(requested.get("skillIds") or (requested.get("professionalBrief") or {}).get("brandName"))
    native_reference = (binding.snapshot or {}).get("reference") if binding and not explicit_visual else None
    source_fingerprint = export_source_fingerprint(slides, native_reference)
    if native_reference and stage == "final":
        latest = export_path(project, "pptx")
        digest = artifact_sha256(latest) if latest.is_file() else ""
        approvals = db.scalars(select(DeliveryVerification).where(
            DeliveryVerification.project_id == project_id,
            DeliveryVerification.file_hash == digest,
            DeliveryVerification.software == profile,
            DeliveryVerification.status == "accepted",
        )).all()
        approved = next((row for row in approvals if
            (row.report or {}).get("humanVerified") is True
            and not (row.report or {}).get("manualUpload")
        ), None)
        exported = next((row for row in db.scalars(
            select(ExportRecord).where(ExportRecord.project_id == project_id, ExportRecord.format == "pptx")
            .order_by(ExportRecord.created_at.desc())
        ) if (row.report or {}).get("sourceFingerprint") == source_fingerprint
            and (row.report or {}).get("artifactSha256") == digest
            and (row.report or {}).get("deliveryProfile") == profile
            and is_versioned_export(project, Path(row.artifact_path))
            and Path(row.artifact_path).is_file()), None)
        if not approved or not exported:
            raise HTTPException(409, "原生参考母版需要先导出草稿，在所选交付软件中完成实际验收，再下载正式稿")
        if artifact_sha256(Path(exported.artifact_path)) != digest:
            raise HTTPException(409, "已验收的导出文件已改变，请重新导出并验收")
        finalized = next((row for row in db.scalars(
            select(ExportRecord).where(ExportRecord.project_id == project_id, ExportRecord.format == "pptx")
            .order_by(ExportRecord.created_at.desc())
        ) if (row.report or {}).get("deliveryStage") == "final"
            and (row.report or {}).get("sourceFingerprint") == source_fingerprint
            and (row.report or {}).get("artifactSha256") == digest
            and Path(row.artifact_path) == Path(exported.artifact_path)), None)
        if not finalized:
            final_report = {**(exported.report or {}), "deliveryStage": "final",
                            "finalizedFromVerification": approved.id}
            db.add(ExportRecord(project_id=project_id, format="pptx",
                                artifact_path=exported.artifact_path, report=final_report))
            db.commit()
        return FileResponse(exported.artifact_path, filename="presentation.pptx")
    with lock:
        assert_current()
        if native_reference:
            from app.db.models import PersonalIdentity, PersonalReference
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
            "deliveryProfile": profile,
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
        (target.with_suffix(".report.json")).write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        report["artifactSha256"] = artifact_sha256(target)
        publish_latest_export(target, export_path(project, "pptx"))
        db.add(
            ExportRecord(project_id=project_id, format="pptx", artifact_path=str(target), report=report)
        )
        db.commit()
        return FileResponse(target, filename="presentation.pptx")



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
    slides = load_slides(project_id, db)
    ensure_current_preview(project, slides)
    source = assemble_delivery_html(project, slides, "assemble-local")
    target = immutable_export_path(project, "pdf")
    presentation_engine.export_pdf(source, target)
    publish_latest_export(target, export_path(project, "pdf"))
    db.add(ExportRecord(
        project_id=project_id,
        format="pdf",
        artifact_path=str(target),
        report={"sourceFingerprint": export_source_fingerprint(slides), "deliveryStage": stage,
                "artifactSha256": artifact_sha256(target)},
    ))
    db.commit()
    return FileResponse(target, filename="presentation.pdf")


@router.get("/projects/{project_id}/downloads/{format_name}")
def download_existing_export(
    project_id: str,
    format_name: Literal["html", "pptx", "pdf"],
    stage: Literal["draft", "final"] = "final",
    db: Session = Depends(get_db),
):
    """Download an existing export only while it still matches current project content."""
    project = project_or_404(project_id, db)
    if stage == "final":
        require_final_quality(project_id, db, stage)
    slides = load_slides(project_id, db)
    reference = None
    if format_name == "pptx":
        from app.db.models import PersonalBinding

        binding = db.get(PersonalBinding, project_id)
        deck_record = db.get(DeckSpecRecord, project_id)
        requested = (deck_record.reproducibility or {}).get("request", {}) if deck_record else {}
        explicit_visual = bool(
            requested.get("skillIds") or (requested.get("professionalBrief") or {}).get("brandName")
        )
        reference = (
            (binding.snapshot or {}).get("reference")
            if binding and not explicit_visual
            else None
        )
    expected_fingerprint = export_source_fingerprint(slides, reference)
    records = db.scalars(
        select(ExportRecord)
        .where(ExportRecord.project_id == project_id, ExportRecord.format == format_name)
        .order_by(ExportRecord.created_at.desc())
    )
    record = next(
        (
            row for row in records
            if (row.report or {}).get("deliveryStage", "draft") == stage
            and (row.report or {}).get("sourceFingerprint") == expected_fingerprint
        ),
        None,
    )
    target = Path(record.artifact_path) if record else None
    expected_sha256 = ((record.report or {}).get("artifactSha256")
                       or (record.report or {}).get("fileVerification", {}).get("sha256")) if record else None
    if (not record or not target or not target.is_file() or not expected_sha256
            or not is_versioned_export(project, target)):
        raise HTTPException(409, "当前内容没有可直接下载的对应导出，请由编辑者重新生成")
    if artifact_sha256(target) != expected_sha256:
        raise HTTPException(409, "导出文件完整性校验失败，请由编辑者重新生成")
    filename = "presentation-html.zip" if format_name == "html" and (record.report or {}).get("portableBundle") else f"presentation.{format_name}"
    return FileResponse(target, filename=filename)


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
        report = fill_native_template(
            await read_upload_limited(template, 20 * 1024 * 1024, "PowerPoint 模板"), slides, target
        )
    except HTTPException:
        raise
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
    payload = await read_upload_limited(file, 20 * 1024 * 1024, "PowerPoint 文件")
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

