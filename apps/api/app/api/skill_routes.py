import hashlib
import io
import ipaddress
import json
import socket
import zipfile
from pathlib import Path

import httpx
from app.db.models import InstalledSkill, ProjectSkill
from app.db.session import get_db
from app.skills.constants import VISUAL_SKILL_KINDS
from app.skills.manager import install_skill
from app.templates.analyzer import analyze_reference_pptx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, HttpUrl
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1")


class SkillUrlRequest(BaseModel):
    url: HttpUrl
    allow_scripts: bool = False


def skill_record(result: dict) -> dict:
    return {
        key: result[key]
        for key in ("id", "version", "manifest", "sha256", "path", "scripts_enabled")
    }


def skill_download_urls(value: str) -> list[str]:
    url = value.rstrip("/")
    if "github.com/" in url and not url.endswith(".zip"):
        parts = url.split("github.com/", 1)[1].split("/")
        if len(parts) >= 2:
            owner, repo = parts[0], parts[1].removesuffix(".git")
            if len(parts) >= 5 and parts[2] == "tree":
                return [f"https://codeload.github.com/{owner}/{repo}/zip/{parts[3]}"]
            return [
                f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/main",
                f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/master",
            ]
    if "gitlab.com/" in url and not url.endswith(".zip"):
        project = url.split("gitlab.com/", 1)[1]
        name = project.rsplit("/", 1)[-1].removesuffix(".git")
        return [
            f"https://gitlab.com/{project}/-/archive/main/{name}-main.zip",
            f"https://gitlab.com/{project}/-/archive/master/{name}-master.zip",
        ]
    return [url]


def select_github_skill_subtree(data: bytes, source_url: str) -> bytes:
    """Turn a GitHub /tree/<ref>/<path> archive into a standalone skill bundle."""
    url = source_url.rstrip("/")
    if "github.com/" not in url:
        return data
    parts = url.split("github.com/", 1)[1].split("/")
    if len(parts) < 5 or parts[2] != "tree":
        return data
    subtree = "/".join(parts[4:]).strip("/")
    if not subtree:
        return data
    source = io.BytesIO(data)
    target = io.BytesIO()
    found = False
    with zipfile.ZipFile(source) as archive, zipfile.ZipFile(
        target, "w", compression=zipfile.ZIP_DEFLATED
    ) as bundle:
        for info in archive.infolist():
            normalized = info.filename.replace("\\", "/")
            _, _, relative = normalized.partition("/")
            prefix = f"{subtree}/"
            if relative == subtree or not relative.startswith(prefix):
                continue
            output_name = relative[len(prefix):]
            if not output_name or info.is_dir():
                continue
            bundle.writestr(output_name, archive.read(info.filename))
            found = True
    if not found:
        raise ValueError(f"项目中未找到技能目录：{subtree}")
    return target.getvalue()


def assert_public_url(value: str) -> None:
    host = httpx.URL(value).host
    if not host:
        raise ValueError("项目链接缺少有效域名")
    for info in socket.getaddrinfo(host, None):
        address = ipaddress.ip_address(info[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
        ):
            raise ValueError("技能项目链接必须指向公开网络地址")


@router.post("/reference/analyze")
async def analyze_reference(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pptx"):
        raise HTTPException(415, "PPTX required")
    return analyze_reference_pptx(await file.read())


@router.post("/reference/compile-skill", status_code=201)
async def compile_reference_skill(
    file: UploadFile = File(...),
    name: str = Form("reference-style"),
    db: Session = Depends(get_db),
):
    data = await file.read()
    analysis = analyze_reference_pptx(data)
    skill_id = "reference-" + "".join(ch for ch in name.lower() if ch.isalnum() or ch == "-")[:60]
    root = Path("skills/generated") / skill_id / "1.0.0"
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "id": skill_id,
        "version": "1.0.0",
        "kind": "visual",
        "name": name.strip() or "参考稿视觉技能",
        "description": "从参考 PPT 学习页面功能、版式节奏、字体和色彩。",
        "permissions": {"executeScripts": False},
        "analysis": analysis,
    }
    (root / "skill.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    palette = {
        key: f"#{value[0]}"
        for key, value in zip(
            ("primary", "accent", "deep", "ink", "line"),
            analysis.get("palette", []),
        )
    }
    tokens = {
        "fontFamily": (
            analysis.get("fontFamily", [["Microsoft YaHei", 1]])[0][0]
            if analysis.get("fontFamily") else "Microsoft YaHei"
        ),
        "palette": palette,
        "layoutProfile": "reference-function-guided",
        "referenceGrammar": {
            "variantByRole": analysis.get("variantByRole", {}),
            "functionPatterns": analysis.get("functionPatterns", []),
            "functionLayoutMap": analysis.get("functionLayoutMap", {}),
            "rhythm": analysis.get("rhythm", {}),
            "constraintGrammar": analysis.get("constraintGrammar", {}),
        },
    }
    (root / "tokens.json").write_text(
        json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (root / "reference-analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    sequence = " → ".join(analysis.get("rhythm", {}).get("sequence", [])[:16])
    (root / "SKILL.md").write_text(
        "\n".join([
            f"# {manifest['name']}",
            "",
            "优先学习参考稿的页面功能和视觉节奏，不复制原文内容。",
            f"参考稿页面序列：{sequence or '未识别'}。",
            "封面、章节、数据、对比、过程与结论页使用各自学习到的候选版式。",
        ]),
        encoding="utf-8",
    )
    existing = db.get(InstalledSkill, skill_id)
    values = {
        "version": "1.0.0",
        "manifest": manifest,
        "sha256": hashlib.sha256(data).hexdigest(),
        "path": str(root.resolve()),
        "scripts_enabled": False,
    }
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
    else:
        db.add(InstalledSkill(id=skill_id, **values))
    db.commit()
    return {"id": skill_id, "version": "1.0.0", "path": str(root), "analysis": analysis}


@router.post("/skills/install", status_code=201)
async def install_skill_route(
    file: UploadFile = File(...), allow_scripts: bool = Form(False), db: Session = Depends(get_db)
):
    try:
        result = install_skill(await file.read(), Path("skills/installed").resolve(), allow_scripts)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    existing = db.get(InstalledSkill, result["id"])
    if existing:
        db.delete(existing)
        db.flush()
    db.add(InstalledSkill(**skill_record(result)))
    db.commit()
    return result


@router.get("/skills")
def list_skills(db: Session = Depends(get_db)):
    return [
        {
            "id": row.id,
            "version": row.version,
            "sha256": row.sha256,
            "scriptsEnabled": row.scripts_enabled,
            "name": row.manifest.get("name", row.id),
            "description": row.manifest.get("description", "演示技能"),
            "kind": row.manifest.get("kind", "workflow"),
        }
        for row in db.scalars(select(InstalledSkill))
        if str((row.manifest or {}).get("kind", "workflow")).lower() in VISUAL_SKILL_KINDS
    ]


@router.post("/skills/install-url", status_code=201)
async def install_skill_from_url(body: SkillUrlRequest, db: Session = Depends(get_db)):
    from app.config import settings
    if settings.local_only_mode:
        raise HTTPException(403, "完全本地模式请导入本地技能包")
    errors, data = [], None
    async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
        for candidate in skill_download_urls(str(body.url)):
            try:
                assert_public_url(candidate)
                response = await client.get(candidate, headers={"User-Agent": "YingZhang/0.2"})
                response.raise_for_status()
                if len(response.content) > 50 * 1024 * 1024:
                    raise ValueError("技能包超过 50 MB 限制")
                data = select_github_skill_subtree(response.content, str(body.url))
                break
            except (httpx.HTTPError, ValueError, socket.gaierror) as exc:
                errors.append(str(exc))
    if data is None:
        raise HTTPException(422, "下载技能项目失败：" + "；".join(errors[-2:]))
    try:
        result = install_skill(data, Path("skills/installed").resolve(), body.allow_scripts)
    except (ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise HTTPException(422, f"技能包校验失败：{exc}") from exc
    existing = db.get(InstalledSkill, result["id"])
    if existing:
        db.delete(existing)
        db.flush()
    db.add(InstalledSkill(**skill_record(result)))
    db.commit()
    return result


@router.delete("/skills/{skill_id}", status_code=204)
def uninstall_skill(skill_id: str, db: Session = Depends(get_db)):
    row = db.get(InstalledSkill, skill_id)
    if not row:
        raise HTTPException(404, "Skill not found")
    import shutil

    shutil.rmtree(row.path, ignore_errors=True)
    db.execute(delete(ProjectSkill).where(ProjectSkill.skill_id == skill_id))
    db.delete(row)
    db.commit()
