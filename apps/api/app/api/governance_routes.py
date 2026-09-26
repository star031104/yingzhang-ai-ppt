import hashlib
import json
import secrets
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from app.api.dependencies import project_or_404
from app.api.quality_routes import validate as validate_project
from app.config import settings
from app.db.models import (
    ApprovalRecord,
    DeckSpecRecord,
    PersonalAccount,
    ProjectMember,
    PublishedDeck,
    SlideSpecRecord,
)
from app.db.session import get_db
from app.professional.governance import can
from app.security.public_access import current_user
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1")


class MemberRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    role: Literal["owner", "editor", "reviewer", "viewer"] = "viewer"


class ApprovalRequest(BaseModel):
    stage: Literal["content", "design", "final"] = "final"
    status: Literal["requested", "approved", "changes_requested"] = "requested"
    comment: str = Field(default="", max_length=1000)


class PublishRequest(BaseModel):
    expires_days: int = Field(default=14, ge=1, le=180)


def _require_project_action(request: Request, action: str) -> None:
    user = current_user(request) or {}
    if settings.public_test_mode and user.get("role") != "admin":
        raise HTTPException(403, "共享测试模式下该治理操作仅管理员可用")
    if settings.private_accounts_mode and not can(
        getattr(request.state, "project_role", ""), action
    ):
        raise HTTPException(403, "当前项目角色无权执行此操作")


def _release_snapshot_hash(project, db: Session, rendered_root: Path | None = None) -> str:
    rendered = rendered_root or (Path(project.artifact_path) / "slides" / "rendered")
    index = rendered / "index.html"
    if not index.is_file():
        raise HTTPException(409, "请先生成完整演示")
    digest = hashlib.sha256()
    deck = db.get(DeckSpecRecord, project.id)
    slides = list(
        db.scalars(
            select(SlideSpecRecord)
            .where(SlideSpecRecord.project_id == project.id)
            .order_by(SlideSpecRecord.position, SlideSpecRecord.id)
        )
    )
    canonical = {
        "deck": {
            "narrative": deck.narrative if deck else {},
            "designSystem": deck.design_system if deck else {},
        },
        "slides": [
            {"id": row.id, "version": row.current_version, "spec": row.spec}
            for row in slides
        ],
    }
    digest.update(json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode())
    for path in sorted(item for item in rendered.rglob("*") if item.is_file()):
        digest.update(path.relative_to(rendered).as_posix().encode())
        digest.update(b"\0")
        file_digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                file_digest.update(chunk)
        digest.update(file_digest.digest())
    return digest.hexdigest()


@router.post("/projects/{project_id}/members", status_code=201)
def add_project_member(project_id: str, body: MemberRequest, request: Request, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    _require_project_action(request, "manage-members")
    member_name = body.name.strip()
    account = None
    if settings.private_accounts_mode:
        account = db.scalar(
            select(PersonalAccount).where(
                PersonalAccount.username == member_name.casefold(),
                PersonalAccount.enabled.is_(True),
            )
        )
        if not account:
            raise HTTPException(404, "独立账号模式下请填写已启用成员的登录账号名称")
        member_name = account.username
    existing = db.scalar(select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.name == member_name))
    if existing:
        existing.role = body.role
        existing.account_id = account.id if account else None
        row = existing
    else:
        row = ProjectMember(
            project_id=project_id,
            name=member_name,
            role=body.role,
            account_id=account.id if account else None,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "role": row.role}


@router.post("/projects/{project_id}/approvals", status_code=201)
def record_approval(project_id: str, body: ApprovalRequest, request: Request, db: Session = Depends(get_db)):
    project = project_or_404(project_id, db)
    _require_project_action(request, "approve")
    snapshot_hash = None
    if body.status == "approved" and body.stage == "final":
        report = validate_project(project_id, db)
        if not report.get("passed"):
            raise HTTPException(409, "质量门禁未通过，不能批准发布")
        snapshot_hash = _release_snapshot_hash(project, db)
    actor = (current_user(request) or {}).get("name", "本机管理员")
    row = ApprovalRecord(
        project_id=project_id,
        stage=body.stage,
        status=body.status,
        actor=actor,
        comment=body.comment.strip(),
        snapshot_hash=snapshot_hash,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "stage": row.stage, "status": row.status, "actor": row.actor, "comment": row.comment}


@router.post("/projects/{project_id}/publish", status_code=201)
def publish_project(project_id: str, body: PublishRequest, request: Request, db: Session = Depends(get_db)):
    project = project_or_404(project_id, db)
    _require_project_action(request, "publish")
    approval = db.scalar(
        select(ApprovalRecord).where(ApprovalRecord.project_id == project_id, ApprovalRecord.stage == "final").order_by(ApprovalRecord.created_at.desc())
    )
    if not approval or approval.status != "approved":
        raise HTTPException(409, "发布前需要完成最终审批")
    report = validate_project(project_id, db)
    if not report.get("passed"):
        raise HTTPException(409, "质量门禁未通过，不能发布")
    if not approval.snapshot_hash or approval.snapshot_hash != _release_snapshot_hash(project, db):
        raise HTTPException(409, "审批后演示内容已变化，请重新审阅并批准当前版本")
    source = Path(project.artifact_path) / "slides" / "rendered"
    index = source / "index.html"
    if "file:" in index.read_text(encoding="utf-8"):
        raise HTTPException(409, "发布页面包含无法独立访问的本机媒体素材，请减少媒体体积后重新生成")
    token = secrets.token_urlsafe(24)
    target = Path(project.artifact_path) / "published" / token
    shutil.copytree(source, target)
    if approval.snapshot_hash != _release_snapshot_hash(project, db, target):
        shutil.rmtree(target, ignore_errors=True)
        raise HTTPException(409, "发布快照生成期间内容发生变化，请重新审阅并批准当前版本")
    actor = (current_user(request) or {}).get("name", "本机管理员")
    row = PublishedDeck(
        project_id=project_id, token=token, artifact_path=str(target / "index.html"),
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=body.expires_days),
        created_by=actor,
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        shutil.rmtree(target, ignore_errors=True)
        raise
    return {"id": row.id, "token": token, "url": f"/api/v1/public/decks/{token}", "expiresAt": row.expires_at.isoformat()}


@router.delete("/projects/{project_id}/publications/{publication_id}", status_code=204)
def revoke_publication(project_id: str, publication_id: str, request: Request, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    _require_project_action(request, "revoke")
    row = db.get(PublishedDeck, publication_id)
    if not row or row.project_id != project_id:
        raise HTTPException(404, "发布记录不存在")
    row.status = "revoked"
    db.commit()


@router.get("/public/decks/{token}", response_class=HTMLResponse)
def public_deck(token: str, db: Session = Depends(get_db)):
    row = db.scalar(select(PublishedDeck).where(PublishedDeck.token == token))
    now = datetime.now(UTC).replace(tzinfo=None)
    if not row or row.status != "active" or (row.expires_at and row.expires_at <= now):
        raise HTTPException(404, "发布链接不存在或已失效")
    target = Path(row.artifact_path)
    if not target.is_file():
        raise HTTPException(404, "发布快照不存在")
    content = target.read_text(encoding="utf-8")
    if "file:" in content:
        raise HTTPException(410, "发布页面引用的本机媒体不可访问，请由项目编辑者重新生成并发布")
    return HTMLResponse(content, headers={"Cache-Control": "private, max-age=60"})
