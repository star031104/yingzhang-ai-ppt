import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path

FORBIDDEN = re.compile(
    r"(?:subprocess|os\.system|child_process|powershell|cmd\.exe|/bin/sh)", re.IGNORECASE
)
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,119}$")
SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,39}$")
RUNTIME_TEXT_LIMIT = 12000


def manifest_from_skill_md(bundle: zipfile.ZipFile, names: list[str], digest: str) -> dict:
    candidates = [name for name in names if Path(name).name.lower() == "skill.md"]
    if not candidates:
        raise ValueError("需要 skill.json 或带 YAML 头信息的 SKILL.md")
    candidates.sort(key=lambda value: (len(Path(value).parts), value.lower()))
    skill_name = candidates[0]
    content = bundle.read(skill_name).decode("utf-8", errors="replace")
    frontmatter = re.match(r"^---\s*\r?\n([\s\S]*?)\r?\n---", content)
    if not frontmatter:
        raise ValueError("SKILL.md 缺少 YAML 头信息")
    fields = {}
    for line in frontmatter.group(1).splitlines():
        match = re.match(r"^([A-Za-z][\w-]*):\s*[\"']?(.*?)[\"']?\s*$", line)
        if match:
            fields[match.group(1).lower()] = match.group(2).strip()
    raw_name = fields.get("name") or Path(skill_name).parent.name
    skill_id = re.sub(r"[^a-z0-9._-]+", "-", raw_name.lower()).strip("-.")
    version_name = next(
        (name for name in names if Path(name).name.upper() == "VERSION"), None
    )
    version = (
        bundle.read(version_name).decode("utf-8", errors="ignore").strip()
        if version_name
        else f"community-{digest[:8]}"
    )
    return {
        "id": skill_id,
        "version": version,
        "kind": "workflow",
        "name": raw_name,
        "description": fields.get("description", "社区 Agent Skill"),
        "entrypoint": skill_name,
        "sourceFormat": "SKILL.md",
    }


def install_skill(data: bytes, root: Path, allow_scripts: bool = False) -> dict:
    digest = hashlib.sha256(data).hexdigest()
    archive = root / f"incoming-{digest[:12]}.zip"
    root.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(data)
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        if len(names) > 12000 or sum(info.file_size for info in bundle.infolist()) > 300 * 1024 * 1024:
            raise ValueError("技能压缩包展开后过大")
        if any(Path(name).is_absolute() or ".." in Path(name).parts for name in names):
            raise ValueError("Unsafe archive path")
        manifest_name = next((name for name in names if name.endswith("skill.json")), None)
        manifest = (
            json.loads(bundle.read(manifest_name))
            if manifest_name
            else manifest_from_skill_md(bundle, names, digest)
        )
        skill_id, version = manifest.get("id"), manifest.get("version")
        if not skill_id or not version:
            raise ValueError("Skill id and version are required")
        skill_id, version = str(skill_id), str(version)
        if not SAFE_ID.fullmatch(skill_id) or not SAFE_VERSION.fullmatch(version):
            raise ValueError("技能 id 或版本号格式不安全")
        scripts = [
            name
            for name in names
            if Path(name).suffix.lower() in {".py", ".js", ".mjs", ".ps1", ".sh"}
        ]
        if allow_scripts:
            for script in scripts:
                if FORBIDDEN.search(bundle.read(script).decode("utf-8", errors="ignore")):
                    raise ValueError(f"Static scan rejected {script}")
        destination = root / skill_id / version
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True)
        bundle.extractall(destination)
        if not manifest_name:
            (destination / "skill.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    archive.unlink(missing_ok=True)
    return {
        "id": skill_id,
        "version": version,
        "manifest": manifest,
        "sha256": digest,
        "path": str(destination),
        "scripts_enabled": bool(scripts and allow_scripts),
        "script_count": len(scripts),
    }


def _safe_skill_file(root: Path, relative: str) -> Path | None:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def resolve_skill_context(skills: list, total_limit: int = 24000) -> list[dict]:
    """Load approved text workflow resources; executable files remain quarantined."""
    resolved: list[dict] = []
    used = 0
    per_skill_limit = min(
        RUNTIME_TEXT_LIMIT,
        max(3000, total_limit // max(1, len(skills))),
    )
    for skill in skills:
        root = Path(skill.path).resolve()
        manifest = skill.manifest or {}
        entrypoint = str(manifest.get("entrypoint", "SKILL.md"))
        entry = _safe_skill_file(root, entrypoint)
        workflow = ""
        resources: list[dict] = []
        if entry:
            workflow = entry.read_text(encoding="utf-8", errors="replace")
            workflow = re.sub(r"^---\s*\n[\s\S]*?\n---\s*", "", workflow).strip()
            workflow = workflow[:per_skill_limit]
        candidates = sorted(
            path for path in root.rglob("*.md")
            if path != entry and any(part.lower() in {"docs", "prompts", "references"} for part in path.parts)
        )
        for path in candidates[:8]:
            remaining = min(3000, per_skill_limit - len(workflow), total_limit - used - len(workflow))
            if remaining <= 0:
                break
            resources.append({
                "path": str(path.relative_to(root)),
                "content": path.read_text(encoding="utf-8", errors="replace")[:remaining],
            })
        size = len(workflow) + sum(len(item["content"]) for item in resources)
        if used + size > total_limit:
            workflow = workflow[: max(0, total_limit - used)]
            resources = []
            size = len(workflow)
        resolved.append({
            "id": skill.id,
            "name": manifest.get("name", skill.id),
            "description": manifest.get("description", "演示工作流"),
            "workflow": workflow,
            "resources": resources,
            "scriptsEnabled": bool(skill.scripts_enabled),
            "scriptsExecuted": False,
        })
        used += size
        if used >= total_limit:
            break
    return resolved
