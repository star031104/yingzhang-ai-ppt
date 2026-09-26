from pathlib import Path
from urllib.parse import urlsplit

from app.api.dependencies import project_or_404
from app.db.models import SourceDocument
from app.db.session import get_db
from app.documents.review import source_reading_view
from app.security.public_fetch import PublicFetchError, fetch_public_bytes
from app.security.uploads import read_upload_limited
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
    data = await read_upload_limited(file, MAX_SOURCE_BYTES, "资料文件")
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
    try:
        content, media_type, current_url = await fetch_public_bytes(
            str(body.url), max_bytes=MAX_SOURCE_BYTES, timeout=20
        )
    except PublicFetchError as exc:
        status = 403 if "非公网" in str(exc) else 413 if "上限" in str(exc) else 422
        raise HTTPException(status, str(exc)) from exc
    if not content:
        raise HTTPException(422, "网页没有返回可读取的内容")
    final_url = urlsplit(current_url)
    row = store_source(
        project_id=project_id,
        project_root=project.artifact_path,
        data=content,
        parse_name=Path(final_url.path).name or "webpage.html",
        stored_name="source.html",
        media_type=media_type,
        display_name=current_url,
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
