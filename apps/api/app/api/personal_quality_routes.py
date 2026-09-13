import asyncio
import copy
import hashlib
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.api.dependencies import project_or_404
from app.db.models import PersonalBinding, PersonalComparison, DeliveryVerification
from app.db.session import get_db
from app.personalization import service
from app.personalization.runtime import generation_snapshot, lock, assert_current
from app.presentation_engine.service import presentation_engine
from app.slides import load_slides

router = APIRouter(prefix="/api/v1", dependencies=[Depends(service.require_local)])


@router.get("/projects/{project_id}/desktop-capabilities")
def desktop_capabilities(project_id: str, db=Depends(get_db)):
    project_or_404(project_id, db)
    from app.personalization.office import capabilities
    return capabilities()


def comparison_record(db, project_id, comparison_id):
    project_or_404(project_id, db)
    owner = service.identity(db)
    row = db.get(PersonalComparison, comparison_id)
    if not row or row.owner_id != owner.id or row.project_id != project_id or row.epoch != owner.epoch:
        raise HTTPException(404, "对照记录不存在或已失效")
    return row


@router.get("/projects/{project_id}/personal-comparisons")
def comparison_list(project_id: str, db=Depends(get_db)):
    project_or_404(project_id, db)
    owner = service.identity(db)
    return [{"id": row.id, "status": row.status, "labels": ["A", "B"],
             "modelComparison": row.payload.get("modelComparison"), "reviews": row.reviews,
             "revealed": row.payload.get("labels") if row.status == "reviewed" else None}
            for row in db.scalars(select(PersonalComparison).where(PersonalComparison.project_id == project_id,
                PersonalComparison.owner_id == owner.id, PersonalComparison.epoch == owner.epoch).order_by(PersonalComparison.created_at.desc()).limit(10))]


@router.post("/projects/{project_id}/personal-comparisons/{comparison_id}/render")
async def render_comparison(project_id: str, comparison_id: str, db=Depends(get_db)):
    row = comparison_record(db, project_id, comparison_id)
    project = project_or_404(project_id, db)
    token = generation_snapshot.set({"ownerId": row.owner_id, "epoch": row.epoch})
    try:
        root = Path(project.artifact_path) / "personal-comparisons" / row.id
        for label, key in row.payload["labels"].items():
            slides = copy.deepcopy(row.payload[key]["slides"])
            await asyncio.to_thread(presentation_engine.run, "build", slides, root / label)
            # Use the effective baseline-fallback style and selected variant in exported PPTX.
            for slide in slides:
                current = json.loads((root / label / "slides" / str(slide["position"]) / "current.json").read_text(encoding="utf-8"))
                slide.setdefault("visualIntent", {})["selectedVariant"] = current["variant"]
                slide["designSystem"] = current.get("designSystem", slide.get("designSystem", {}))
            await asyncio.to_thread(presentation_engine.run, "pptx", slides, root / label / "presentation.pptx")
        with lock:
            assert_current()
            row.status = "rendered"
            db.commit()
        return {"id": row.id, "status": row.status, "labels": ["A", "B"]}
    finally:
        generation_snapshot.reset(token)


@router.get("/projects/{project_id}/personal-comparisons/{comparison_id}/{label}/{format}")
def comparison_file(project_id: str, comparison_id: str, label: Literal["A", "B"],
                    format: Literal["html", "pptx"], db=Depends(get_db)):
    row = comparison_record(db, project_id, comparison_id)
    project = project_or_404(project_id, db)
    target = Path(project.artifact_path) / "personal-comparisons" / row.id / label / ("index.html" if format == "html" else "presentation.pptx")
    if not target.is_file():
        raise HTTPException(409, "请先生成 A/B 对照")
    return FileResponse(target, filename=f"candidate-{label}.{format}")


class ComparisonReview(BaseModel):
    label: Literal["A", "B"]
    scores: dict[str, int]


@router.post("/projects/{project_id}/personal-comparisons/{comparison_id}/review")
def review_comparison(project_id: str, comparison_id: str, body: ComparisonReview, db=Depends(get_db)):
    row = comparison_record(db, project_id, comparison_id)
    required = {"logic", "visual", "completeness", "accuracy", "personalFit"}
    if set(body.scores) != required or any(type(value) is not int or not 0 <= value <= 100 for value in body.scores.values()):
        raise HTTPException(422, "请填写五项 0—100 分评分")
    if row.status not in {"rendered", "reviewed"}:
        raise HTTPException(409, "请先生成并查看对照")
    row.reviews = {**row.reviews, body.label: body.scores}
    if set(row.reviews) == {"A", "B"}:
        row.status = "reviewed"
    db.commit()
    return {"status": row.status, "revealed": row.payload["labels"] if row.status == "reviewed" else None,
            "reviews": row.reviews}


@router.post("/projects/{project_id}/external-feedback")
async def external_feedback(project_id: str, file: UploadFile = File(...), db=Depends(get_db)):
    from app.personalization.roundtrip_learning import compare_external
    from app.personalization.reference import extract_reference
    project = project_or_404(project_id, db)
    owner = service.identity(db)
    binding = db.get(PersonalBinding, project_id)
    if not binding or binding.owner_id != owner.id:
        raise HTTPException(409, "项目未绑定个人档案")
    original = Path(project.artifact_path) / "exports" / "presentation.pptx"
    if not original.is_file():
        raise HTTPException(409, "请先从映章导出原始 PPTX，再上传修改稿")
    data = await file.read(20 * 1024 * 1024 + 1)
    alignment = compare_external(original.read_bytes(), data, project_id)
    before, _ = extract_reference(original.read_bytes())
    after, _ = extract_reference(data)
    changes = {key: value for key, value in json.loads(after).items() if json.loads(before).get(key) != value}
    with lock:
        config = service.profile(db, binding.profile_id)
        suggestions = []
        if alignment["canSuggest"] and changes:
            value = json.dumps(changes, ensure_ascii=False)
            item = service.put_memory(db, config, "reference_style", value, origin="external-edit", status="candidate")
            suggestions.append(service.memory_view(item))
        db.commit()
        return {"alignment": alignment, "suggestions": suggestions, "retainedOriginal": False}


class DesktopRequest(BaseModel):
    software: Literal["libreoffice", "powerpoint-windows", "powerpoint-macos", "wps"] = "libreoffice"


@router.get("/projects/{project_id}/desktop-verifications")
def verification_list(project_id: str, db=Depends(get_db)):
    project_or_404(project_id, db)
    return [{"id": row.id, "software": row.software, "status": row.status, "fileHash": row.file_hash,
             "report": row.report} for row in db.scalars(select(DeliveryVerification).where(
                 DeliveryVerification.project_id == project_id).order_by(DeliveryVerification.created_at.desc()).limit(10))]


@router.post("/projects/{project_id}/desktop-verifications")
async def desktop_verify(project_id: str, body: DesktopRequest, db=Depends(get_db)):
    from app.personalization.office import render_office
    project = project_or_404(project_id, db)
    target = Path(project.artifact_path) / "exports" / "presentation.pptx"
    if not target.is_file():
        raise HTTPException(409, "请先导出检查草稿")
    source_bytes = target.read_bytes()
    row = DeliveryVerification(project_id=project_id, file_hash=hashlib.sha256(source_bytes).hexdigest(), software=body.software)
    db.add(row)
    db.flush()
    output = Path(project.artifact_path) / "desktop-verifications" / row.id
    output.mkdir(parents=True, exist_ok=True)
    frozen = output / "presentation.pptx"
    frozen.write_bytes(source_bytes)
    db.commit()
    result = await asyncio.to_thread(render_office, frozen, output, body.software)
    slides = load_slides(project_id, db)
    pages = result.get("pages", [])
    problems = []
    if result["status"] == "rendered-needs-review":
        if len(pages) != len(slides):
            problems.append("实际页数与页面规格不一致")
        for spec, page in zip(slides, pages):
            title = "".join(str(spec.get("content", {}).get("title", "")).split())
            text = "".join(page.get("text", "").split())
            expected = [title, *["".join(str(point).split()) for point in spec.get("content", {}).get("bullets", [])]]
            if any(value and value not in text for value in expected):
                problems.append(f"第 {spec['position']} 页标题或正文未完整读取，请核对替代字体、图表呈现或截断")
        if problems:
            result["status"] = "needs-repair"
    result["problems"] = problems
    result["pages"] = [{key: value for key, value in page.items() if key != "text"} for page in pages]
    row.report = result
    row.status = result["status"]
    db.commit()
    return {"id": row.id, "status": row.status, "report": result}


@router.get("/projects/{project_id}/desktop-verifications/{verification_id}/pages/{page}")
def desktop_page(project_id: str, verification_id: str, page: int, db=Depends(get_db)):
    project = project_or_404(project_id, db)
    row = db.get(DeliveryVerification, verification_id)
    if not row or row.project_id != project.id or not 1 <= page <= 100:
        raise HTTPException(404, "验收页面不存在")
    target = Path(project.artifact_path) / "desktop-verifications" / row.id / f"page-{page}.png"
    if not target.is_file():
        raise HTTPException(404, "该页尚未渲染")
    return FileResponse(target)


class DesktopAccept(BaseModel):
    file_hash: str
    checked_fonts: bool
    checked_layout: bool
    checked_content: bool


@router.post("/projects/{project_id}/desktop-verifications/{verification_id}/accept")
def accept_desktop(project_id: str, verification_id: str, body: DesktopAccept, db=Depends(get_db)):
    project = project_or_404(project_id, db)
    row = db.get(DeliveryVerification, verification_id)
    target = Path(project.artifact_path) / "exports" / "presentation.pptx"
    if not row or row.project_id != project_id or not target.is_file() or row.file_hash != body.file_hash or hashlib.sha256(target.read_bytes()).hexdigest() != row.file_hash:
        raise HTTPException(409, "文件已改变，请重新验收")
    if row.status != "rendered-needs-review" or not all([body.checked_fonts, body.checked_layout, body.checked_content]):
        raise HTTPException(409, "请先修复自动检查问题，并逐项核对字体、布局和内容")
    row.status = "accepted"
    row.report = {**row.report, "humanVerified": True}
    db.commit()
    return {"status": row.status, "fileHash": row.file_hash}


@router.post("/projects/{project_id}/desktop-verifications/manual")
async def upload_desktop_pdf(project_id: str, file: UploadFile = File(...),
                            software: Literal["libreoffice", "powerpoint-windows", "powerpoint-macos", "wps"] = Form(...),
                            file_hash: str = Form(...), db=Depends(get_db)):
    import pymupdf
    project = project_or_404(project_id, db)
    target = Path(project.artifact_path) / "exports" / "presentation.pptx"
    if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != file_hash:
        raise HTTPException(409, "PPTX 已更新，请下载最新草稿后重新生成验收 PDF")
    data = await file.read(30 * 1024 * 1024 + 1)
    if len(data) > 30 * 1024 * 1024 or not data.startswith(b"%PDF-"):
        raise HTTPException(422, "请选择不超过 30 MB 的 PDF")
    row = DeliveryVerification(project_id=project_id, file_hash=file_hash, software=software)
    db.add(row)
    db.flush()
    output = Path(project.artifact_path) / "desktop-verifications" / row.id
    output.mkdir(parents=True, exist_ok=True)
    pages, problems = [], []
    slides = load_slides(project_id, db)
    try:
        with pymupdf.open(stream=data, filetype="pdf") as document:
            if len(document) > 100 or len(document) != len(slides):
                raise HTTPException(422, "验收 PDF 页数必须与当前 PPTX 一致，且不超过 100 页")
            for index, page in enumerate(document):
                page.get_pixmap(matrix=pymupdf.Matrix(1.3, 1.3)).save(output / f"page-{index+1}.png")
                text = "".join(page.get_text().split())
                title = "".join(str(slides[index].get("content", {}).get("title", "")).split())
                expected = [title, *["".join(str(point).split()) for point in slides[index].get("content", {}).get("bullets", [])]]
                if any(value and value not in text for value in expected):
                    problems.append(f"第 {index+1} 页标题或正文未完整读取")
                pages.append({"page": index+1, "image": f"page-{index+1}.png"})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, "无法读取验收 PDF") from exc
    (output / "verification.pdf").write_bytes(data)
    row.status = "needs-repair" if problems else "rendered-needs-review"
    row.report = {"status": row.status, "pages": pages, "problems": problems,
                  "manualUpload": True, "message": "此 PDF 由用户从目标软件导出；软件来源为用户声明，需人工核对"}
    db.commit()
    return {"id": row.id, "status": row.status, "report": row.report}


@router.get("/projects/{project_id}/desktop-file")
def desktop_file_hash(project_id: str, db=Depends(get_db)):
    project = project_or_404(project_id, db)
    target = Path(project.artifact_path) / "exports" / "presentation.pptx"
    return {"fileHash": hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None}
