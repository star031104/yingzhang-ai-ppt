from pathlib import Path

import httpx
from app.api.dependencies import project_or_404
from app.db.models import SourceDocument
from app.db.session import get_db
from app.documents.review import source_reading_view
from app.sources import safe_upload_name, store_source
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1")
MAX_SOURCE_BYTES = 100 * 1024 * 1024


class UrlSource(BaseModel):
    url: HttpUrl


def _source_view(row: SourceDocument) -> dict:
    return source_reading_view(row)


@router.post("/projects/{project_id}/sources", status_code=201)
async def upload_source(
    project_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)
):
    project = project_or_404(project_id, db)
    data = await file.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise HTTPException(413, "Source exceeds 100 MB")
    filename = safe_upload_name(file.filename)
    row = store_source(
        project_id=project_id,
        project_root=project.artifact_path,
        data=data,
        parse_name=filename,
        stored_name=filename,
        media_type=file.content_type or "application/octet-stream",
        db=db,
    )
    return _source_view(row)


@router.post("/projects/{project_id}/sources/url", status_code=201)
async def add_url_source(project_id: str, body: UrlSource, db: Session = Depends(get_db)):
    from app.config import settings
    if settings.local_only_mode:
        raise HTTPException(403, "完全本地模式请上传本地文件，不读取外部网页")
    project = project_or_404(project_id, db)
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        response = await client.get(str(body.url), headers={"User-Agent": "YingZhang/0.2"})
        response.raise_for_status()
    if len(response.content) > MAX_SOURCE_BYTES:
        raise HTTPException(413, "Source exceeds 100 MB")
    row = store_source(
        project_id=project_id,
        project_root=project.artifact_path,
        data=response.content,
        parse_name=Path(body.url.path).name or "webpage.html",
        stored_name="source.html",
        media_type=response.headers.get("content-type", "text/html"),
        display_name=str(body.url),
        db=db,
    )
    return _source_view(row)


@router.get("/projects/{project_id}/sources")
def source_review(project_id: str, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    return [
        source_reading_view(row)
        for row in db.scalars(select(SourceDocument).where(SourceDocument.project_id == project_id))
    ]
