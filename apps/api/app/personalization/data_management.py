"""Dependency-aware deletion and a bounded, offline workspace reset manifest."""

from pathlib import Path

from sqlalchemy import delete, select

from app.db.models import Base, PersonalBinding, PersonalFeedback, PersonalMemory


def delete_project_records(db, project_id):
    """Resolve dependent IDs before deleting, including later feature tables."""
    from app.db.models import PersonalCase, PersonalProfile
    from app.personalization.lifecycle import delete_derived_rules, invalidate_profile
    cases = list(db.scalars(select(PersonalCase).where(PersonalCase.project_id == project_id)))
    for profile_id in {case.profile_id for case in cases}:
        profile = db.get(PersonalProfile, profile_id)
        if profile:
            delete_derived_rules(db, profile, [case.id for case in cases if case.profile_id == profile.id])
            invalidate_profile(db, profile)
    db.execute(delete(PersonalCase).where(PersonalCase.project_id == project_id))
    tables = Base.metadata.tables
    project = tables["projects"]
    predicates = {"projects": project.c.id == project_id}
    for table in Base.metadata.sorted_tables:
        if table.name == "projects":
            continue
        conditions = []
        for foreign in table.foreign_keys:
            parent = foreign.column.table
            if parent.name in predicates:
                conditions.append(
                    foreign.parent.in_(select(foreign.column).where(predicates[parent.name]))
                )
        if conditions:
            from sqlalchemy import or_

            predicates[table.name] = or_(*conditions)
    # Materialize child primary keys before any parent subquery loses its rows.
    ids = {}
    for table in Base.metadata.sorted_tables:
        if table.name in predicates:
            keys = list(table.primary_key.columns)
            ids[table.name] = (keys, list(db.execute(select(*keys).where(predicates[table.name]))))
    for table in reversed(Base.metadata.sorted_tables):
        if table.name not in ids or table.name == "projects":
            continue
        keys, values = ids[table.name]
        if values:
            from sqlalchemy import tuple_

            db.execute(delete(table).where(tuple_(*keys).in_([tuple(value) for value in values])))
    event_ids = list(
        db.scalars(select(PersonalFeedback.id).where(PersonalFeedback.project_id == project_id))
    )
    if event_ids:
        for memory in db.scalars(select(PersonalMemory)):
            if set(memory.evidence or []) & set(event_ids):
                db.delete(memory)
    db.execute(delete(PersonalFeedback).where(PersonalFeedback.project_id == project_id))
    db.execute(delete(PersonalBinding).where(PersonalBinding.project_id == project_id))


def managed_reset_paths(settings, workspace: Path):
    workspace = workspace.resolve()
    database = settings.database_url
    if not database.startswith("sqlite:///") or ":memory:" in database:
        raise ValueError("离线恢复出厂仅支持本地 SQLite 工作区")
    database_path = Path(database.removeprefix("sqlite:///")).resolve()
    roots = [
        settings.artifact_root.resolve(),
        database_path,
        workspace / "runtime" / "trash",
        workspace / "runtime" / "logs",
        workspace / "skills" / "generated",
        workspace / "skills" / "installed",
        workspace / ".yingzhang",
        workspace / ".env",
    ]
    roots.extend(Path(str(database_path) + suffix) for suffix in ("-wal", "-shm", "-journal"))
    for path in roots:
        resolved = path.resolve()
        if resolved == workspace or workspace not in resolved.parents:
            raise ValueError(f"数据位于工作区之外，请自行核对并处理：{path}")
        if any(
            item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction())
            for item in [path, *path.parents]
            if item != workspace and workspace in item.parents
        ):
            raise ValueError(f"清理路径不能是链接或联接：{path}")
    return roots


def scrub_personal_hints(value):
    if isinstance(value, list):
        return [scrub_personal_hints(item) for item in value]
    if isinstance(value, dict):
        return {
            key: scrub_personal_hints(item)
            for key, item in value.items()
            if key
            not in {
                "personalization",
                "personalizationBaseline",
                "profileId",
                "profile_id",
                "profile_revision",
                "personalizationEpoch", "personalExamples",
            }
        }
    return value


def scrub_project_cache(root, artifact_root):
    """Keep finished work, but prevent cached generation instructions being reused."""
    import json

    root, allowed = Path(root).resolve(), Path(artifact_root).resolve()
    if root == allowed or allowed not in root.parents:
        return {"cleaned": 0, "failed": 1}
    cleaned = failed = 0
    for path in root.rglob("*.json"):
        if any(part.startswith((".personal-render-", ".style-baseline-")) for part in path.parts):
            continue  # Active workers own and remove their unpublished staging files.
        if path.is_symlink() or root not in path.resolve().parents:
            failed += 1
            continue
        try:
            original = json.loads(path.read_text(encoding="utf-8"))
            updated = scrub_personal_hints(original)
            if updated != original:
                path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
                cleaned += 1
        except (OSError, ValueError):
            failed += 1
    return {"cleaned": cleaned, "failed": failed}
