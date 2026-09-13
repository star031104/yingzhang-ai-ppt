import hashlib
import json
import re
from email.header import decode_header
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SourceDocument
from app.documents import PARSER_VERSION, parse_source


def safe_upload_name(value: str | None) -> str:
    """Decode and constrain an uploaded filename before it reaches the filesystem."""
    raw = value or "source"
    try:
        decoded = "".join(
            part.decode(charset or "utf-8", errors="replace")
            if isinstance(part, bytes)
            else part
            for part, charset in decode_header(raw)
        )
    except (LookupError, UnicodeError):
        decoded = raw
    name = Path(decoded.replace("\\", "/")).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name[:240] or "source"


def store_source(
    *,
    project_id: str,
    project_root: str | Path,
    data: bytes,
    parse_name: str,
    stored_name: str,
    media_type: str,
    db: Session,
    display_name: str | None = None,
) -> SourceDocument:
    """Parse a source and persist its original, normalized model, and database record."""
    sha256 = hashlib.sha256(data).hexdigest()
    destination = Path(project_root) / "analysis" / "sources" / sha256
    destination.mkdir(parents=True, exist_ok=True)
    source = parse_source(
        parse_name,
        data,
        media_type,
        asset_dir=destination / "assets",
    )
    original = destination / safe_upload_name(stored_name)
    original.write_bytes(data)
    (destination / "source-model.json").write_text(
        json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    row = SourceDocument(
        project_id=project_id,
        name=display_name or source["name"],
        media_type=source["mediaType"],
        sha256=source["sha256"],
        artifact_path=str(original),
        model=source,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def load_sources(project_id: str, db: Session) -> list[dict]:
    """Load normalized source models and lazily upgrade stale parser output."""
    sources = []
    for row in db.scalars(select(SourceDocument).where(SourceDocument.project_id == project_id)):
        model = row.model or {}
        if model.get("parserVersion") != PARSER_VERSION:
            try:
                original = Path(row.artifact_path)
                model = parse_source(
                    row.name,
                    original.read_bytes(),
                    row.media_type,
                    asset_dir=original.parent / "assets",
                )
                row.model = model
                (original.parent / "source-model.json").write_text(
                    json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except (OSError, ValueError):
                model = row.model
        sources.append(model)
    return sources
