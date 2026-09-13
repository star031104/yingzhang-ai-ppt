import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings


class ArtifactStore:
    folders = ("analysis", "plan", "slides", "validation", "exports")

    def create_project(self, project_id, metadata):
        root = settings.artifact_root.resolve() / project_id
        for folder in self.folders:
            (root / folder).mkdir(parents=True, exist_ok=True)
        (root / "project.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return root

    def trash_project(self, project_id, artifact_path):
        root = settings.artifact_root.resolve()
        target = Path(artifact_path).resolve()
        if target.parent != root or target.name != project_id:
            raise ValueError("项目产物路径校验失败")
        if not target.exists():
            return None
        trash_root = (root.parent / "trash").resolve()
        trash_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = trash_root / f"{project_id}-{stamp}"
        shutil.move(str(target), str(destination))
        return destination


artifact_store = ArtifactStore()
