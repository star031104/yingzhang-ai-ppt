import secrets
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from app.api.dependencies import project_or_404
from app.api.quality_routes import validate as validate_project
from app.db.models import ApprovalRecord, ProjectMember, PublishedDeck
from app.db.session import get_db
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


@router.post("/projects/{project_id}/members", status_code=201)
def add_project_member(project_id: str, body: MemberRequest, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    existing = db.scalar(select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.name == body.name.strip()))
    if existing:
        existing.role = body.role
        row = existing
    else:
        row = ProjectMember(project_id=project_id, name=body.name.strip(), role=body.role)
        db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "role": row.role}


@router.post("/projects/{project_id}/approvals", status_code=201)
def record_approval(project_id: str, body: ApprovalRequest, request: Request, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    actor = (current_user(request) or {}).get("name", "本机管理员")
    row = ApprovalRecord(project_id=project_id, stage=body.stage, status=body.status, actor=actor, comment=body.comment.strip())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "stage": row.stage, "status": row.status, "actor": row.actor, "comment": row.comment}


@router.post("/projects/{project_id}/publish", status_code=201)
def publish_project(project_id: str, body: PublishRequest, request: Request, db: Session = Depends(get_db)):
    project = project_or_404(project_id, db)
    approval = db.scalar(
        select(ApprovalRecord).where(ApprovalRecord.project_id == project_id, ApprovalRecord.stage == "final").order_by(ApprovalRecord.created_at.desc())
    )
    if not approval or approval.status != "approved":
        raise HTTPException(409, "发布前需要完成最终审批")
    report = validate_project(project_id, db)
    if not report.get("passed"):
        raise HTTPException(409, "质量门禁未通过，不能发布")
    source = Path(project.artifact_path) / "slides" / "rendered"
    if not (source / "index.html").is_file():
        raise HTTPException(409, "请先生成完整演示")
    token = secrets.token_urlsafe(24)
    target = Path(project.artifact_path) / "published" / token
    shutil.copytree(source, target)
    actor = (current_user(request) or {}).get("name", "本机管理员")
    row = PublishedDeck(
        project_id=project_id, token=token, artifact_path=str(target / "index.html"),
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=body.expires_days),
        created_by=actor,
    )
    db.add(row)
    db.commit()
    return {"id": row.id, "token": token, "url": f"/api/v1/public/decks/{token}", "expiresAt": row.expires_at.isoformat()}


@router.delete("/projects/{project_id}/publications/{publication_id}", status_code=204)
def revoke_publication(project_id: str, publication_id: str, db: Session = Depends(get_db)):
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
    return HTMLResponse(target.read_text(encoding="utf-8"), headers={"Cache-Control": "private, max-age=60"})



