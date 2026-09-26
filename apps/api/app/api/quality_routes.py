import copy
import hashlib
import json
import secrets
import shutil
from pathlib import Path
from typing import Literal

from app.api.dependencies import project_or_404
from app.db.models import (
    BlindReview,
    DeckSpecRecord,
    EvaluationRun,
    ExportRecord,
    ImportedDeck,
    PersonalBinding,
)
from app.db.session import get_db
from app.evaluation import build_evaluation_metrics
from app.evaluation.fingerprints import export_source_fingerprint
from app.slides import load_slides
from app.sources import build_brief_source, load_sources
from app.validation.accessibility import audit_accessibility
from app.validation.quality import build_professional_audit, validate_deck
from app.validation.render_freshness import matches_render_stamp
from app.validation.render_safety import hard_render_failures
from app.validation.visual_maturity import assess_visual_maturity, variant_family
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

router = APIRouter(prefix="/api/v1")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BlindReviewRequest(BaseModel):
    reviewer_alias: str = Field(default="匿名评审", max_length=80)
    candidate_label: Literal["A", "B"] = "A"
    scores: dict[str, int] = Field(default_factory=dict)
    comment: str = Field(default="", max_length=2000)


def export_path(project, format_name: str) -> Path:
    return Path(project.artifact_path) / "exports" / f"presentation.{format_name}"


@router.post("/projects/{project_id}/validate")
def validate(project_id: str, db: Session = Depends(get_db)):
    project = project_or_404(project_id, db)
    slides = load_slides(project_id, db)
    sources = load_sources(project_id, db)
    if not sources:
        deck = db.get(DeckSpecRecord, project_id)
        request = (deck.reproducibility or {}).get("request", {}) if deck else {}
        sources = [build_brief_source(str(request.get("title", project.name)), str(request.get("instructions", "")))]
    report = validate_deck(slides, sources)
    rendered = Path(project.artifact_path) / "slides" / "rendered" / "slides"
    visual_slides = []
    stale_positions = []
    digest_cache = {}
    if rendered.exists():
        for slide in slides:
            current = rendered / str(slide["position"]) / "current.json"
            if not current.is_file():
                continue
            try:
                value = json.loads(current.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            # Read older page-selection artifacts as well as the canonical engine format.
            detail = value.get("scoreDetail") or (value.get("score") if isinstance(value.get("score"), dict) else {})
            selected = (slide.get("visualIntent") or {}).get("selectedVariant")
            if not matches_render_stamp(detail.get("renderStamp"), slide, digest_cache) or (selected and selected != value.get("variant")):
                stale_positions.append(slide["position"])
                continue
            candidate_families = {
                str(json.loads(score_path.read_text(encoding="utf-8")).get("variantFamily")
                    or variant_family(score_path.name.removesuffix(".score.json")))
                for score_path in current.parent.glob("*.score.json")
            }
            visual_slides.append({
                "position": int(current.parent.name), "variant": value.get("variant"),
                "family": detail.get("variantFamily") or variant_family(value.get("variant")),
                "candidateFamilyCount": len(candidate_families),
                "overall": detail.get("overall", value.get("score", 0)),
                "geometry": detail.get("geometry", 0),
                "readability": detail.get("readability", 0),
                "hierarchy": detail.get("hierarchy", 0),
                "semanticFit": detail.get("semanticFit", detail.get("semantic", 0)),
                "contentFit": detail.get("contentFit", 0),
                "visualEvidence": detail.get("visualEvidence", 0),
                "deckRhythm": detail.get("deckRhythm", 0),
                "issues": detail.get("issues", []),
                "hardFailures": hard_render_failures(detail),
            })
    checked_positions = {item["position"] for item in visual_slides}
    missing_positions = [slide["position"] for slide in slides if slide["position"] not in checked_positions]
    visual_blocking = [
        item for item in visual_slides
        if item["hardFailures"] or item["overall"] < 70 or item["geometry"] < 70
    ]
    report["visualQA"] = {
        "checked": len(visual_slides), "blocking": len(visual_blocking),
        "expected": len(slides), "missingPositions": missing_positions, "stalePositions": stale_positions,
        "complete": bool(slides) and not missing_positions,
        "average": round(sum(item["overall"] for item in visual_slides) / len(visual_slides), 1) if visual_slides else None,
        "slides": visual_slides,
    }
    rendered_maturity = assess_visual_maturity(slides, visual_slides)
    report["visualMaturity"] = rendered_maturity
    existing_issue_codes = {str(item.get("code")) for item in report.get("issues", [])}
    for issue in rendered_maturity["issues"]:
        if issue["code"] not in existing_issue_codes:
            report["issues"].append({"slide": 0, **issue})
            report["warningCount"] = report.get("warningCount", 0) + 1
            existing_issue_codes.add(issue["code"])
    critic_path = Path(project.artifact_path) / "validation" / "visual-critic.json"
    if critic_path.exists():
        try:
            critic_report = json.loads(critic_path.read_text(encoding="utf-8"))
            applied = critic_report.get("applied", 0)
            report["visualReflection"] = {
                "checked": critic_report.get("checked", len(visual_slides)),
                "applied": len(applied) if isinstance(applied, list) else applied,
                "visionStatus": critic_report.get("visionStatus", "deterministic"),
            }
        except (OSError, json.JSONDecodeError):
            report["visualReflection"] = {
                "checked": len(visual_slides), "applied": 0, "visionStatus": "report-unavailable"
            }
    for item in visual_blocking:
        report["issues"].append({
            "slide": item["position"], "code": "render-error", "severity": "error",
            "message": "页面存在显示问题，请修复后重新检查",
            "details": item["issues"], "failures": item["hardFailures"],
        })
    if missing_positions or not slides:
        report["issues"].append({
            "slide": 0, "code": "render-incomplete", "severity": "error",
            "message": "尚未完成全部页面的渲染检查", "positions": missing_positions,
        })
    if stale_positions:
        report["issues"].append({
            "slide": 0, "code": "render-stale", "severity": "error",
            "message": "内容、版式或素材已更新，请重新生成这些页面后再检查", "positions": stale_positions,
        })
    if visual_blocking or missing_positions or not slides:
        report["blockingErrors"] += len(visual_blocking) + int(bool(missing_positions) or not slides) + int(bool(stale_positions))
        report["passed"] = False
    scene_path = Path(project.artifact_path) / "slides" / "rendered" / "scene-ir.json"
    scene_ir = None
    if scene_path.exists():
        try:
            scene_ir = json.loads(scene_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            scene_ir = None
    accessibility = audit_accessibility(slides, scene_ir)
    report["accessibility"] = accessibility
    report["warningCount"] = report.get("warningCount", 0) + accessibility["warnings"]
    if accessibility["errors"]:
        report["blockingErrors"] += accessibility["errors"]
        report["passed"] = False
    report["professionalAudit"] = build_professional_audit(report, report["visualQA"])
    target = Path(project.artifact_path) / "validation" / "quality-report.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


@router.post("/projects/{project_id}/evaluations", status_code=201)
def run_professional_evaluation(project_id: str, db: Session = Depends(get_db)):
    project = project_or_404(project_id, db)
    quality = validate(project_id, db)
    imported = db.scalar(select(ImportedDeck).where(ImportedDeck.project_id == project_id))
    metrics = build_evaluation_metrics(project, db, quality, imported.analysis if imported else None)
    slides = load_slides(project_id, db)
    deck_record = db.get(DeckSpecRecord, project_id)
    requested = (deck_record.reproducibility or {}).get("request", {}) if deck_record else {}
    explicit_visual = bool(requested.get("skillIds") or (requested.get("professionalBrief") or {}).get("brandName"))
    binding = db.get(PersonalBinding, project_id)
    reference = (binding.snapshot or {}).get("reference") if binding and not explicit_visual else None
    fingerprint = export_source_fingerprint(slides, reference)
    version_root = (Path(project.artifact_path) / "exports" / "versions").resolve()
    current_export = next((record for record in db.scalars(
        select(ExportRecord).where(ExportRecord.project_id == project_id, ExportRecord.format == "pptx")
        .order_by(ExportRecord.created_at.desc())
    ) if (record.report or {}).get("sourceFingerprint") == fingerprint
        and (record.report or {}).get("artifactSha256")
        and Path(record.artifact_path).is_file()
        and Path(record.artifact_path).resolve().parent == version_root
        and file_sha256(Path(record.artifact_path)) == (record.report or {}).get("artifactSha256")), None)
    generated = Path(current_export.artifact_path) if current_export else None
    imported_path = Path((imported.analysis or {}).get("_workingPath", imported.artifact_path)) if imported else None
    candidates = [path for path in (generated, imported_path) if path and path.is_file()]
    if len(candidates) == 2 and secrets.randbelow(2):
        candidates.reverse()
    metrics["blindReady"] = len(candidates) == 2
    if len(candidates) != 2:
        metrics["blindReadinessReason"] = (
            "当前页面内容尚无匹配且可校验的 PPTX 导出；请重新导出后创建评估"
            if not generated else "双盲评审需要两份候选文件，当前候选不足"
        )
    row = EvaluationRun(project_id=project_id, suite=metrics["suite"], metrics=metrics)
    db.add(row)
    db.flush()
    frozen_candidates = {}
    candidate_root = Path(project.artifact_path) / "evaluations" / row.id / "candidates"
    candidate_root.mkdir(parents=True, exist_ok=True)
    for label, source in zip(("A", "B"), candidates):
        frozen = candidate_root / f"{label}.pptx"
        shutil.copyfile(source, frozen)
        digest = file_sha256(frozen)
        frozen_candidates[label] = {"path": str(frozen), "sha256": digest}
    row.metrics = {**metrics, "_blindCandidates": frozen_candidates}
    db.commit()
    visible = {key: value for key, value in metrics.items() if not key.startswith("_")}
    return {"id": row.id, "suite": row.suite, "metrics": visible, "blindToken": row.blind_token}


@router.get("/evaluations/blind/{token}")
def get_blind_evaluation(token: str, db: Session = Depends(get_db)):
    row = db.scalar(select(EvaluationRun).where(EvaluationRun.blind_token == token))
    if not row:
        raise HTTPException(404, "Blind evaluation not found")
    candidates = (row.metrics or {}).get("_blindCandidates", {})
    return {
        "token": token, "suite": row.suite, "candidateLabels": list(candidates),
        "dimensions": ["fundamentals", "visualDesign", "completeness", "correctness", "fidelity"],
        "instructions": "请独立查看 A/B 两份演示，不判断生成系统，只按五维标准评分。",
    }


@router.get("/evaluations/blind/{token}/candidate/{label}")
def download_blind_candidate(token: str, label: Literal["A", "B"], db: Session = Depends(get_db)):
    row = db.scalar(select(EvaluationRun).where(EvaluationRun.blind_token == token))
    candidate = ((row.metrics or {}).get("_blindCandidates", {}) if row else {}).get(label)
    if isinstance(candidate, str):
        raise HTTPException(410, "此旧评估未冻结候选文件，请重新创建评估以确保盲评内容一致")
    if not row or not isinstance(candidate, dict):
        raise HTTPException(404, "Blind candidate not found")
    path = Path(candidate.get("path", ""))
    if not path.is_file():
        raise HTTPException(404, "Blind candidate not found")
    digest = file_sha256(path)
    if digest != candidate.get("sha256"):
        raise HTTPException(409, "盲评候选文件完整性校验失败")
    return FileResponse(path, filename=f"candidate-{label}.pptx")


@router.post("/evaluations/blind/{token}/reviews", status_code=201)
def submit_blind_review(
    token: str, body: BlindReviewRequest, db: Session = Depends(get_db)
):
    row = db.scalar(select(EvaluationRun).where(EvaluationRun.blind_token == token))
    if not row:
        raise HTTPException(404, "Blind evaluation not found")
    required = {"fundamentals", "visualDesign", "completeness", "correctness", "fidelity"}
    candidates = (row.metrics or {}).get("_blindCandidates", {})
    if candidates and any(not isinstance(item, dict) for item in candidates.values()):
        raise HTTPException(410, "此旧评估未冻结候选文件，请重新创建评估后提交评分")
    if len(candidates) != 2:
        raise HTTPException(409, "此评估没有两份有效候选文件，无法进行双盲评分")
    if body.candidate_label not in candidates:
        raise HTTPException(422, "该评估中不存在此候选项")
    for candidate in candidates.values():
        path = Path(candidate.get("path", ""))
        if not path.is_file() or file_sha256(path) != candidate.get("sha256"):
            raise HTTPException(409, "盲评候选文件缺失或已改变，无法提交评分")
    if set(body.scores) != required or any(not isinstance(value, int) or value < 0 or value > 100 for value in body.scores.values()):
        raise HTTPException(422, "All five scores must be integers from 0 to 100")
    review = BlindReview(
        evaluation_run_id=row.id, reviewer_alias=body.reviewer_alias,
        candidate_label=body.candidate_label, scores=body.scores, comment=body.comment,
    )
    db.add(review)
    db.flush()
    reviews = list(db.scalars(select(BlindReview).where(BlindReview.evaluation_run_id == row.id)))
    averages = {
        dimension: round(sum(item.scores.get(dimension, 0) for item in reviews) / len(reviews), 1)
        for dimension in required
    }
    metrics = copy.deepcopy(row.metrics or {})
    metrics["blindReviewCount"] = len(reviews)
    metrics["blindAverage"] = averages
    metrics["blindByCandidate"] = {
        label: {"reviewCount": len(group), "average": {
            dimension: round(sum(item.scores[dimension] for item in group) / len(group), 1)
            for dimension in required}}
        for label in ("A", "B")
        if (group := [item for item in reviews if item.candidate_label == label])
    }
    row.metrics = metrics
    flag_modified(row, "metrics")
    db.commit()
    return {"id": review.id, "reviewCount": len(reviews), "average": averages, "byCandidate": metrics["blindByCandidate"]}
