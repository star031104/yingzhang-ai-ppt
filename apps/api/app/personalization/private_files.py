import hashlib
import io
import shutil
import zipfile
from xml.etree import ElementTree as ET
from pathlib import Path

from fastapi import HTTPException

from app.config import settings
from app.db.models import PersonalReference


def validate_pptx(data):
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "PPTX 不能超过 20 MB")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 5000 or sum(item.file_size for item in entries) > 100 * 1024 * 1024:
                raise ValueError("压缩包超出限制")
            if "ppt/presentation.xml" not in archive.namelist():
                raise ValueError("不是 PPTX")
            if any("vbaproject" in item.filename.lower() for item in entries):
                raise ValueError("不接受宏")
            for item in entries:
                if "/embeddings/" in item.filename.lower():
                    if not item.filename.lower().endswith(".xlsx"):
                        raise ValueError("仅支持图表使用的内嵌 XLSX，不接受嵌入程序")
                    with zipfile.ZipFile(io.BytesIO(archive.read(item))) as workbook:
                        if sum(part.file_size for part in workbook.infolist()) > 20 * 1024 * 1024 or any("vbaproject" in part.filename.lower() for part in workbook.infolist()):
                            raise ValueError("内嵌工作簿超限或含宏")
                if item.filename.endswith(".rels"):
                    for relationship in ET.fromstring(archive.read(item)):
                        if relationship.get("TargetMode") == "External" and not relationship.get("Type", "").endswith("/hyperlink"):
                            raise ValueError("请先将外部链接的媒体或数据嵌入 PPTX")
    except (ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise HTTPException(422, str(exc)) from exc


def reference_root(row):
    allowed = (settings.artifact_root / ".personal" / row.owner_id / row.id).absolute()
    root = Path(row.artifact_path).absolute()
    if root != allowed or root.resolve() != allowed or any(
        part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction())
        for part in [root, *root.parents] if part != settings.artifact_root.resolve()
    ):
        raise HTTPException(409, "私人参考稿路径异常，清理已停止")
    return root


def save_reference(db, profile, name, data, analysis):
    validate_pptx(data)
    row = PersonalReference(owner_id=profile.owner_id, profile_id=profile.id, name=name[:180],
                            artifact_path="", sha256=hashlib.sha256(data).hexdigest(), analysis=analysis)
    db.add(row)
    db.flush()
    row.artifact_path = str((settings.artifact_root / ".personal" / row.owner_id / row.id).resolve())
    root = reference_root(row)
    root.mkdir(parents=True, exist_ok=True)
    (root / "reference.pptx").write_bytes(data)
    return row


def erase_private_reference(row):
    root = reference_root(row)
    if root.exists():
        shutil.rmtree(root)


def reference_view(row):
    return {"id": row.id, "name": row.name, "active": row.active, "sha256": row.sha256,
            "analysis": row.analysis, "retainedOriginal": True}


def erase_comparison_files(db, owner_id):
    from sqlalchemy import select
    from app.db.models import PersonalComparison, Project
    for row in db.scalars(select(PersonalComparison).where(PersonalComparison.owner_id == owner_id)):
        project = db.get(Project, row.project_id)
        if not project:
            continue
        allowed = Path(project.artifact_path).resolve()
        root = allowed / "personal-comparisons" / row.id
        if allowed not in root.resolve().parents or settings.artifact_root.resolve() not in root.resolve().parents or root.is_symlink():
            raise HTTPException(409, "对照文件路径异常")
        if root.exists():
            shutil.rmtree(root)
