import copy
import json
import shutil
from pathlib import Path

from app.api.dependencies import project_or_404
from app.db.models import (
    ApprovalRecord,
    BrandAsset,
    DeckSpecRecord,
    EvaluationRun,
    ExportRecord,
    ImportedDeck,
    Job,
    LicensedAsset,
    ProjectMember,
    PublishedDeck,
    SlideCandidate,
    SlideSpecRecord,
    SourceDocument,
)
from app.db.session import get_db
from app.documents.review import source_reading_view
from app.presentation_intelligence.art_director import build_design_system
from app.presentation_intelligence.brand_kit import compile_brand_kit
from app.presentation_intelligence.research_assets import build_research_manifest
from app.professional import audit_delivery_profile, permission_model
from app.skills.project import load_project_skills, set_project_skills
from app.slides import load_slides
from app.sources import load_sources
from app.validation.visual_regression import compare_render_roots
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1")


class ProjectSkillsRequest(BaseModel):
    skill_ids: list[str] = Field(default_factory=list, max_length=20)


class VisualRegressionRequest(BaseModel):
    accept_current: bool = False
    threshold: float = Field(default=0.025, ge=0.0, le=0.5)


@router.get("/projects/{project_id}/workspace")
def get_project_workspace(project_id: str, db: Session = Depends(get_db)):
    from app.config import settings
    from app.db.models import PersonalBinding, PersonalProfile
    from app.personalization.service import describe
    project = project_or_404(project_id, db)
    deck = db.get(DeckSpecRecord, project_id)
    slides = load_slides(project_id, db)
    slide_versions = {
        row.id: row.current_version
        for row in db.scalars(
            select(SlideSpecRecord).where(SlideSpecRecord.project_id == project_id)
        )
    }
    slide_views = [
        {**copy.deepcopy(slide), "revision": slide_versions.get(slide["id"], 1)}
        for slide in slides
    ]
    skills = load_project_skills(project_id, db)
    rendered = Path(project.artifact_path) / "slides" / "rendered" / "index.html"
    slide_ids = [slide["id"] for slide in slides]
    candidate_rows = list(
        db.scalars(
            select(SlideCandidate)
            .where(SlideCandidate.slide_id.in_(slide_ids))
            .order_by(SlideCandidate.created_at.asc())
        )
    ) if slide_ids else []
    export_rows = list(
        db.scalars(
            select(ExportRecord)
            .where(ExportRecord.project_id == project_id)
            .order_by(ExportRecord.created_at.desc())
        )
    )
    imported = db.scalar(select(ImportedDeck).where(ImportedDeck.project_id == project_id))
    evaluation_rows = list(
        db.scalars(
            select(EvaluationRun)
            .where(EvaluationRun.project_id == project_id)
            .order_by(EvaluationRun.created_at.desc())
        )
    )
    plan_options = copy.deepcopy((deck.reproducibility or {}).get("request", {})) if deck else {}
    binding = db.get(PersonalBinding, project_id) if not settings.public_test_mode else None
    personal_profile = db.get(PersonalProfile, binding.profile_id) if binding else None
    if personal_profile:
        plan_options.setdefault("professionalBrief", {}).update({"profileId": personal_profile.id, "profileRevision": personal_profile.revision})
    return {
        "personalizationAvailable": not settings.public_test_mode,
        "personalization": describe(binding.snapshot if binding else None) if not settings.public_test_mode else {"active": False, "rules": []},
        "project": {
            "id": project.id,
            "name": project.name,
            "status": project.status,
        },
        "narrative": deck.narrative if deck else None,
        "designSystem": deck.design_system if deck else None,
        "planOptions": plan_options,
        "orchestration": (deck.reproducibility or {}).get("orchestration", {}) if deck else {},
        "modelPlanning": (deck.reproducibility or {}).get("model", {}) if deck else {},
        "gates": (deck.reproducibility or {}).get("gates", {"enabled": False, "outline": "approved", "sample": "approved"}) if deck else None,
        "slides": slide_views,
        "candidates": [
            {
                "id": row.id,
                "slideId": row.slide_id,
                "variant": row.variant,
                "score": row.score,
                "selected": row.selected,
                "previewAvailable": Path(row.artifact_path).with_suffix(".png").is_file(),
            }
            for row in candidate_rows
        ],
        "sources": [
            source_reading_view(row)
            for row in db.scalars(
                select(SourceDocument).where(SourceDocument.project_id == project_id)
            )
        ],
        "skillIds": [row.id for row in skills],
        "previewAvailable": rendered.exists(),
        "sampleAvailable": (Path(project.artifact_path) / "slides" / "sample" / "index.html").exists(),
        "exports": list(dict.fromkeys(row.format for row in export_rows)),
        "licensedAssets": [
            {
                "id": row.id, "name": row.name, "kind": row.kind, "slideId": row.slide_id,
                "provider": row.provider, "sourceUrl": row.source_url, "license": row.license,
                "attribution": row.attribution, "approved": row.approved,
            }
            for row in db.scalars(select(LicensedAsset).where(LicensedAsset.project_id == project_id))
        ],
        "brandAssets": [
            {"id": row.id, "name": row.name, "kind": row.kind, "metadata": row.metadata_json}
            for row in db.scalars(select(BrandAsset).where(BrandAsset.project_id == project_id))
        ],
        "members": [
            {"id": row.id, "name": row.name, "role": row.role}
            for row in db.scalars(select(ProjectMember).where(ProjectMember.project_id == project_id))
        ],
        "approvals": [
            {"id": row.id, "stage": row.stage, "status": row.status, "actor": row.actor, "comment": row.comment}
            for row in db.scalars(
                select(ApprovalRecord).where(ApprovalRecord.project_id == project_id).order_by(ApprovalRecord.created_at.desc())
            )
        ],
        "publications": [
            {"id": row.id, "token": row.token, "status": row.status, "expiresAt": row.expires_at.isoformat() if row.expires_at else None}
            for row in db.scalars(
                select(PublishedDeck).where(PublishedDeck.project_id == project_id).order_by(PublishedDeck.created_at.desc())
            )
        ],
        "importedPowerPoint": {
            "id": imported.id,
            "sourceName": imported.source_name,
            "version": imported.current_version,
            "analysis": {key: value for key, value in (imported.analysis or {}).items() if not key.startswith("_")},
        } if imported else None,
        "evaluationRuns": [
            {
                "id": row.id, "suite": row.suite, "status": row.status,
                "metrics": {key: value for key, value in (row.metrics or {}).items() if not key.startswith("_")},
                "blindToken": row.blind_token,
            }
            for row in evaluation_rows
        ],
    }


@router.get("/projects/{project_id}/professional-platform")
def professional_platform(project_id: str, db: Session = Depends(get_db)):
    project = project_or_404(project_id, db)
    deck = db.get(DeckSpecRecord, project_id)
    slides = load_slides(project_id, db)
    assets = list(db.scalars(select(BrandAsset).where(BrandAsset.project_id == project_id)))
    design = copy.deepcopy(deck.design_system or {}) if deck else {}
    research_path = Path(project.artifact_path) / "analysis" / "research-manifest.json"
    research = json.loads(research_path.read_text(encoding="utf-8")) if research_path.is_file() else build_research_manifest(load_sources(project_id, db), slides)
    latest_job = db.scalar(select(Job).where(Job.project_id == project_id).order_by(Job.created_at.desc()))
    layout = (deck.reproducibility or {}).get("layoutPlanning", {}) if deck else {}
    delivery = {
        profile: audit_delivery_profile(slides, profile)
        for profile in ("powerpoint-windows", "powerpoint-macos", "wps", "libreoffice")
    }
    return {
        "version": "professional-platform-v1",
        "p0": {
            "researchManifest": research,
            "layoutPlanning": layout,
            "brandKit": compile_brand_kit(design, assets),
            "canvasObjectModel": "composition-plan-v1",
            "visualRegression": "scene-and-pixel-snapshot-ready",
        },
        "p1": {
            "stageTrace": (latest_job.checkpoint or {}).get("trace", []) if latest_job else [],
            "reviewDiff": "slide-review-diff-v1",
            "governance": {**permission_model(), "members": True, "publicationSnapshots": True},
            "benchmarkFamilies": ["academic", "business", "product", "pitch", "training"],
        },
        "p2": {"deliveryProfiles": delivery, "templateConstraintLearning": "reference-analysis-v3", "media": True},
    }


@router.post("/projects/{project_id}/visual-regression")
def visual_regression(
    project_id: str,
    body: VisualRegressionRequest,
    db: Session = Depends(get_db),
):
    project = project_or_404(project_id, db)
    rendered = Path(project.artifact_path) / "slides" / "rendered" / "slides"
    if not rendered.is_dir():
        raise HTTPException(409, "请先生成完整演示")
    validation_root = Path(project.artifact_path) / "validation"
    current_root = validation_root / "visual-current"
    baseline_root = validation_root / "visual-baseline"
    current_root.mkdir(parents=True, exist_ok=True)
    for stale in current_root.glob("*.png"):
        stale.unlink()
    for slide in load_slides(project_id, db):
        slide_root = rendered / str(slide["position"])
        current_path = slide_root / "current.json"
        if not current_path.is_file():
            continue
        selected = json.loads(current_path.read_text(encoding="utf-8"))
        image_path = slide_root / f"{selected['variant']}.png"
        if image_path.is_file():
            shutil.copy2(image_path, current_root / f"slide-{slide['position']:02d}.png")
    if body.accept_current or not baseline_root.is_dir() or not any(baseline_root.glob("*.png")):
        baseline_root.mkdir(parents=True, exist_ok=True)
        for stale in baseline_root.glob("*.png"):
            stale.unlink()
        for image_path in current_root.glob("*.png"):
            shutil.copy2(image_path, baseline_root / image_path.name)
        return {"version": "visual-regression-v1", "status": "baseline-created", "slides": len(list(baseline_root.glob('*.png')))}
    report = compare_render_roots(baseline_root, current_root, body.threshold)
    (validation_root / "visual-regression.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


@router.put("/projects/{project_id}/skills")
def update_project_skills(
    project_id: str, body: ProjectSkillsRequest, db: Session = Depends(get_db)
):
    project_or_404(project_id, db)
    skills = set_project_skills(project_id, body.skill_ids, db)
    deck = db.get(DeckSpecRecord, project_id)
    if deck:
        request = (deck.reproducibility or {}).get("request", {})
        design = build_design_system(
            str(request.get("preset", "academic")),
            skills,
            request.get("professionalBrief", {}),
        )
        deck.design_system = design
        for row in db.scalars(select(SlideSpecRecord).where(SlideSpecRecord.project_id == project_id)):
            spec = copy.deepcopy(row.spec)
            spec["designSystem"] = design
            row.spec = spec
    db.commit()
    return {"skillIds": [row.id for row in skills]}


@router.get("/projects/{project_id}/outline")
def get_outline(project_id: str, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    deck = db.get(DeckSpecRecord, project_id)
    return {"narrative": deck.narrative if deck else None, "slides": load_slides(project_id, db)}


@router.post("/projects/{project_id}/calibrate")
def calibrate(project_id: str, db: Session = Depends(get_db)):
    slides = load_slides(project_id, db)
    if not slides:
        raise HTTPException(409, "Generate an outline first")
    picks = [slides[0], slides[len(slides) // 2], slides[-1]]
    return {"slides": picks, "themes": ["forest", "ocean", "ember"], "recommended": "forest"}

