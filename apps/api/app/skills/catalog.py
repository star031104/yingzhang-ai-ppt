import hashlib
import json
from pathlib import Path

from app.db.models import InstalledSkill, ProjectSkill
from app.db.session import SessionLocal
from sqlalchemy import delete

LEGACY_PIPELINE_SKILLS = {
    "pdf",
    "pptx",
    "knowledge-cat-ppt-skill",
    "presentation-skill",
}


def _directory_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def seed_visual_skill_catalog(root: Path | None = None) -> None:
    """Install the reviewed, data-only visual catalog and retire old pipeline pseudo-skills."""
    catalog_root = (root or Path("skills/visual")).resolve()
    with SessionLocal() as db:
        db.execute(delete(ProjectSkill).where(ProjectSkill.skill_id.in_(LEGACY_PIPELINE_SKILLS)))
        for skill_id in LEGACY_PIPELINE_SKILLS:
            existing = db.get(InstalledSkill, skill_id)
            if existing:
                db.delete(existing)
        if catalog_root.is_dir():
            for manifest_path in sorted(catalog_root.glob("*/skill.json")):
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("kind") != "visual":
                    continue
                skill_id = str(manifest["id"])
                existing = db.get(InstalledSkill, skill_id)
                values = {
                    "version": str(manifest["version"]),
                    "manifest": manifest,
                    "sha256": _directory_digest(manifest_path.parent),
                    "path": str(manifest_path.parent.resolve()),
                    "scripts_enabled": False,
                }
                if existing:
                    for key, value in values.items():
                        setattr(existing, key, value)
                else:
                    db.add(InstalledSkill(id=skill_id, **values))
        db.commit()
