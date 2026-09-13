from app.db.models import InstalledSkill, ProjectSkill
from app.skills.constants import VISUAL_SKILL_KINDS
from app.skills.manager import resolve_skill_context
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session


def load_project_skills(project_id: str, db: Session) -> list[InstalledSkill]:
    return list(
        db.scalars(
            select(InstalledSkill)
            .join(ProjectSkill, ProjectSkill.skill_id == InstalledSkill.id)
            .where(ProjectSkill.project_id == project_id)
            .order_by(InstalledSkill.id)
        )
    )


def set_project_skills(project_id: str, skill_ids: list[str], db: Session) -> list[InstalledSkill]:
    unique_ids = list(dict.fromkeys(skill_ids))
    installed = list(
        db.scalars(select(InstalledSkill).where(InstalledSkill.id.in_(unique_ids)))
    ) if unique_ids else []
    if len(installed) != len(unique_ids):
        found = {row.id for row in installed}
        missing = [skill_id for skill_id in unique_ids if skill_id not in found]
        raise HTTPException(422, f"技能未安装：{', '.join(missing)}")
    unsupported = [
        row.id for row in installed
        if str((row.manifest or {}).get("kind", "workflow")).lower() not in VISUAL_SKILL_KINDS
    ]
    if unsupported:
        raise HTTPException(422, f"只能为项目启用视觉、布局或品牌技能：{', '.join(unsupported)}")
    db.execute(delete(ProjectSkill).where(ProjectSkill.project_id == project_id))
    for skill_id in unique_ids:
        db.add(ProjectSkill(project_id=project_id, skill_id=skill_id))
    return sorted(installed, key=lambda row: row.id)


def skill_context(skills: list[InstalledSkill]) -> str:
    resolved = resolve_skill_context(skills)
    if not resolved:
        return "未选择额外视觉风格，使用映章默认设计系统"
    blocks = []
    for skill in resolved:
        resources = "\n".join(
            f"[资源 {item['path']}]\n{item['content']}" for item in skill["resources"]
        )
        blocks.append(
            f"【视觉技能 {skill['id']}｜{skill['name']}】\n"
            f"说明：{skill['description']}\n视觉规则：\n{skill['workflow']}\n{resources}"
        )
    return "\n\n".join(blocks)



