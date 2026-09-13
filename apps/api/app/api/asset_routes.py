import copy
import json
import re
import secrets
from pathlib import Path
from typing import Literal

import httpx
from app.api.dependencies import project_or_404
from app.db.models import (
    BrandAsset,
    DeckSpecRecord,
    LicensedAsset,
    SlideSpecRecord,
    SlideVersion,
    SourceDocument,
)
from app.db.session import get_db
from app.presentation_intelligence.brand_kit import compile_brand_kit
from app.presentation_intelligence.research_assets import build_research_manifest, discover_research
from app.slides import load_slides
from app.sources import load_sources
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1")


class BrandKitRequest(BaseModel):
    name: str = Field(default="", max_length=120)
    palette: dict[str, str] = Field(default_factory=dict)
    font_family: str = Field(default="", max_length=120)
    imagery_style: str = Field(default="documentary", max_length=120)
    icon_style: str = Field(default="outline", max_length=80)
    forbidden_effects: list[str] = Field(default_factory=list, max_length=20)


APPROVED_ASSET_LICENSES = {
    "owned", "internal", "cc0", "cc-by", "cc-by-sa", "unsplash", "pexels", "pixabay"
}


@router.get("/projects/{project_id}/research/manifest")
def research_manifest(project_id: str, db: Session = Depends(get_db)):
    project = project_or_404(project_id, db)
    target = Path(project.artifact_path) / "analysis" / "research-manifest.json"
    if target.is_file():
        return json.loads(target.read_text(encoding="utf-8"))
    deck = db.get(DeckSpecRecord, project_id)
    slides = load_slides(project_id, db)
    request = ((deck.reproducibility or {}).get("request") or {}).get("professionalBrief", {}) if deck else {}
    return build_research_manifest(load_sources(project_id, db), slides, request)


@router.get("/projects/{project_id}/research/discover")
async def research_discover(
    project_id: str,
    q: str,
    kind: Literal["works", "images"] = "works",
    limit: int = 8,
    db: Session = Depends(get_db),
):
    project_or_404(project_id, db)
    try:
        return {"query": q, "kind": kind, "results": await discover_research(q, kind, limit)}
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, f"研究源暂时不可用：{exc}") from exc


@router.get("/projects/{project_id}/assets/search")
def search_project_assets(project_id: str, q: str = "", db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    query = q.strip().lower()
    results = []
    for row in db.scalars(select(LicensedAsset).where(LicensedAsset.project_id == project_id)):
        haystack = f"{row.name} {row.attribution} {row.provider}".lower()
        if query and query not in haystack:
            continue
        results.append({
            "id": row.id, "type": "licensed", "name": row.name, "kind": row.kind,
            "license": row.license, "attribution": row.attribution, "approved": row.approved,
            "bindable": row.approved and bool(row.artifact_path),
        })
    for source in db.scalars(select(SourceDocument).where(SourceDocument.project_id == project_id)):
        for figure in (source.model or {}).get("figures", []):
            name = str(figure.get("caption") or figure.get("id") or source.name)
            if query and query not in name.lower():
                continue
            results.append({
                "id": figure.get("id"), "type": "source", "name": name, "kind": figure.get("kind", "image"),
                "license": "source-document", "attribution": source.name, "approved": True,
                "bindable": bool(figure.get("path")),
            })
    return results[:60]


@router.post("/projects/{project_id}/assets", status_code=201)
async def register_licensed_asset(
    project_id: str,
    name: str = Form(...),
    kind: str = Form("image"),
    provider: str = Form("uploaded"),
    source_url: str = Form(""),
    license: str = Form("unknown"),
    attribution: str = Form(""),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    project = project_or_404(project_id, db)
    license_key = license.strip().lower()
    approved = license_key in APPROVED_ASSET_LICENSES and bool(attribution.strip() or license_key in {"owned", "internal"})
    artifact_path = ""
    if file and file.filename:
        suffix = Path(file.filename).suffix.lower()
        allowed_suffixes = {
            "image": {".png", ".jpg", ".jpeg", ".webp", ".svg"},
            "video": {".mp4", ".webm", ".mov"},
            "audio": {".mp3", ".wav", ".m4a"},
        }
        if suffix not in allowed_suffixes.get(kind, allowed_suffixes["image"]):
            raise HTTPException(415, "素材格式与所选类型不匹配")
        root = Path(project.artifact_path) / "assets" / "licensed"
        root.mkdir(parents=True, exist_ok=True)
        target = root / f"{secrets.token_hex(8)}{suffix}"
        target.write_bytes(await file.read())
        artifact_path = str(target)
    row = LicensedAsset(
        project_id=project_id, name=name.strip(), kind=kind.strip()[:40], provider=provider.strip()[:120],
        source_url=source_url.strip(), license=license_key, attribution=attribution.strip(),
        artifact_path=artifact_path, approved=approved,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "approved": row.approved, "license": row.license, "bindable": bool(row.artifact_path) and row.approved}


@router.post("/projects/{project_id}/slides/{slide_id}/assets/{asset_id}/bind")
def bind_licensed_asset(project_id: str, slide_id: str, asset_id: str, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    slide = db.get(SlideSpecRecord, slide_id)
    asset = db.get(LicensedAsset, asset_id)
    if not slide or slide.project_id != project_id or not asset or asset.project_id != project_id:
        raise HTTPException(404, "素材或页面不存在")
    if not asset.approved or not asset.artifact_path or not Path(asset.artifact_path).is_file():
        raise HTTPException(409, "素材尚未完成授权或缺少可用文件")
    spec = copy.deepcopy(slide.spec)
    binding_type = {"video": "licensed-video", "audio": "licensed-audio"}.get(asset.kind, "licensed-image")
    bindings = [item for item in spec.get("assetBindings", []) if item.get("type") not in {"licensed-image", "licensed-video", "licensed-audio"}]
    bindings.append({
        "type": binding_type, "path": asset.artifact_path, "alt": asset.name,
        "provenance": asset.attribution, "sourceUrl": asset.source_url, "license": asset.license,
    })
    spec["assetBindings"] = bindings
    spec["visualIntent"] = {
        **(spec.get("visualIntent") or {}),
        "primaryVisual": "media" if binding_type != "licensed-image" else "source-image",
        "archetypeCandidates": ["media-focus", "split"] if binding_type != "licensed-image" else ["figure-wide", "figure-analysis", "image-story"],
    }
    if binding_type != "licensed-image":
        spec.setdefault("layoutPlan", {})["candidateOrder"] = ["media-focus", "split"]
    slide.current_version += 1
    slide.spec = spec
    asset.slide_id = slide_id
    db.add(SlideVersion(slide_id=slide_id, version=slide.current_version, spec=spec, reason=f"绑定合规素材：{asset.name}"))
    db.commit()
    return {"slide": spec, "assetId": asset.id}


@router.post("/projects/{project_id}/brand-assets", status_code=201)
async def upload_brand_asset(
    project_id: str,
    name: str = Form(...),
    kind: Literal["logo", "font", "template", "image"] = Form("logo"),
    metadata: str = Form("{}"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    project = project_or_404(project_id, db)
    suffix = Path(file.filename or "").suffix.lower()
    allowed = {"logo": {".png", ".jpg", ".jpeg", ".svg"}, "font": {".ttf", ".otf", ".woff", ".woff2"}, "template": {".pptx"}, "image": {".png", ".jpg", ".jpeg", ".webp"}}
    if suffix not in allowed[kind]:
        raise HTTPException(415, "品牌资产格式不受支持")
    root = Path(project.artifact_path) / "assets" / "brand"
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{secrets.token_hex(8)}{suffix}"
    target.write_bytes(await file.read())
    try:
        metadata_json = json.loads(metadata or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(422, "品牌元数据必须是 JSON") from exc
    row = BrandAsset(project_id=project_id, name=name.strip(), kind=kind, artifact_path=str(target), metadata_json=metadata_json)
    db.add(row)
    db.flush()
    deck = db.get(DeckSpecRecord, project_id)
    if deck:
        design = copy.deepcopy(deck.design_system or {})
        brand = dict(design.get("brand") or {})
        if kind == "logo":
            brand["logoPath"] = str(target)
        brand.update({key: value for key, value in metadata_json.items() if key in {"name", "primary", "accent", "fontFamily"}})
        design["brand"] = brand
        brand_assets = list(db.scalars(select(BrandAsset).where(BrandAsset.project_id == project_id)))
        design["brandKit"] = compile_brand_kit(design, brand_assets)
        deck.design_system = design
        for slide_row in db.scalars(select(SlideSpecRecord).where(SlideSpecRecord.project_id == project_id)):
            spec = copy.deepcopy(slide_row.spec)
            spec["designSystem"] = design
            slide_row.spec = spec
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "kind": row.kind}


@router.get("/projects/{project_id}/brand-kit")
def get_brand_kit(project_id: str, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    deck = db.get(DeckSpecRecord, project_id)
    design = copy.deepcopy(deck.design_system or {}) if deck else {}
    assets = list(db.scalars(select(BrandAsset).where(BrandAsset.project_id == project_id)))
    return compile_brand_kit(design, assets)


@router.put("/projects/{project_id}/brand-kit")
def update_brand_kit(project_id: str, body: BrandKitRequest, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    deck = db.get(DeckSpecRecord, project_id)
    if not deck:
        raise HTTPException(409, "请先生成大纲")
    design = copy.deepcopy(deck.design_system or {})
    palette = dict(design.get("palette") or {})
    for key, value in body.palette.items():
        if key in {"bg", "ink", "primary", "accent", "deep", "line"} and re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
            palette[key] = value.upper()
    design["palette"] = palette
    brand = dict(design.get("brand") or {})
    brand.update({
        "name": body.name.strip(), "fontFamily": body.font_family.strip(),
        "imageryStyle": body.imagery_style.strip(), "iconStyle": body.icon_style.strip(),
        "forbiddenEffects": body.forbidden_effects,
    })
    design["brand"] = brand
    if body.font_family.strip():
        design.setdefault("typography", {})["fontFamily"] = body.font_family.strip()
    assets = list(db.scalars(select(BrandAsset).where(BrandAsset.project_id == project_id)))
    design["brandKit"] = compile_brand_kit(design, assets)
    deck.design_system = design
    for slide_row in db.scalars(select(SlideSpecRecord).where(SlideSpecRecord.project_id == project_id)):
        spec = copy.deepcopy(slide_row.spec)
        spec["designSystem"] = design
        slide_row.spec = spec
    db.commit()
    return design["brandKit"]



