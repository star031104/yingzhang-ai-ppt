import copy
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select

from app.config import settings
from app.db.models import (
    DeckSpecRecord,
    Job,
    PersonalBinding,
    PersonalFeedback,
    PersonalIdentity,
    PersonalMemory,
    PersonalProfile,
    PersonalReset,
    PersonalCase,
    PersonalReference,
    PersonalOutbox,
    PersonalComparison,
    Project,
    SlideSpecRecord,
    SlideVersion,
)
from app.personalization.runtime import lock
from app.personalization.schemas import LABELS, OPTIONS, preference_description, validate_preference


def require_local():
    if settings.public_test_mode:
        raise HTTPException(403, "个人经验仅在本机个人工作区开放；共享测试模式不采集私人记忆")


def identity(db):
    require_local()
    from app.security.accounts import owner_context
    requested = owner_context.get()
    if settings.private_accounts_mode and not requested:
        raise HTTPException(401, "缺少个人账号上下文")
    row = db.get(PersonalIdentity, requested) if requested else db.scalar(select(PersonalIdentity))
    if not row:
        row = PersonalIdentity()
        db.add(row)
        db.flush()
    return row


def profile(db, profile_id):
    owner = identity(db)
    row = db.get(PersonalProfile, profile_id)
    if not row or row.owner_id != owner.id:
        raise HTTPException(404, "个人档案不存在")
    return row


def check_revision(row, revision):
    if row.revision != revision:
        raise HTTPException(409, "档案已更新，请刷新后再保存")


def memory_view(row):
    value = row.value.get("choice", "")
    return {
        "id": row.id,
        "key": row.key,
        "value": value,
        "label": LABELS.get(row.key, row.key),
        "description": preference_description(row.key, value),
        "status": row.status,
        "origin": row.origin,
        "revision": row.revision,
        "evidenceCount": len(row.evidence),
        "createdAt": row.created_at.isoformat() if row.created_at else None,
    }


def profile_view(db, row):
    memories = db.scalars(
        select(PersonalMemory)
        .where(PersonalMemory.owner_id == row.owner_id, PersonalMemory.profile_id == row.id)
        .order_by(PersonalMemory.created_at)
    ).all()
    return {
        "id": row.id,
        "name": row.name,
        "scenario": row.scenario,
        "revision": row.revision,
        "use_memory": row.use_memory,
        "capture_feedback": row.capture_feedback,
        "memories": [memory_view(item) for item in memories],
    }


def put_memory(db, row, key, value, *, origin="explicit", status="confirmed", evidence=None):
    try:
        value = validate_preference(key, value)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if status == "confirmed":
        db.execute(
            delete(PersonalMemory).where(
                PersonalMemory.profile_id == row.id, PersonalMemory.key == key
            )
        )
    item = PersonalMemory(
        owner_id=row.owner_id,
        profile_id=row.id,
        key=key,
        value={"choice": value},
        origin=origin,
        status=status,
        evidence=evidence or [],
    )
    db.add(item)
    row.revision += 1
    db.flush()
    return item


def freeze(db, row, preset):
    owner = identity(db)
    active = row.use_memory and row.scenario in {"all", preset}
    records = (
        db.scalars(
            select(PersonalMemory).where(
                PersonalMemory.owner_id == owner.id,
                PersonalMemory.profile_id == row.id,
                PersonalMemory.status == "confirmed",
            )
        ).all()
        if active
        else []
    )
    choices = {
        item.key: validate_preference(item.key, item.value.get("choice")) for item in records
    }
    snapshot = {
        "version": 1,
        "ownerId": owner.id,
        "profileId": row.id,
        "profileRevision": row.revision,
        "epoch": owner.epoch,
        "scenario": preset,
        "active": active,
        "preferences": choices,
        "ruleIds": [item.id for item in records],
        "policyVersion": "quality-constrained-v1",
    }
    from app.personalization.cases import retrieve_cases
    snapshot["examples"] = retrieve_cases(db, row, preset) if active else []
    reference = db.scalar(select(PersonalReference).where(PersonalReference.profile_id == row.id, PersonalReference.owner_id == owner.id, PersonalReference.active.is_(True))) if active else None
    snapshot["reference"] = {"id": reference.id, "sha256": reference.sha256} if reference else None
    snapshot["digest"] = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    return snapshot


def bind(db, project_id, profile_id, preset, revision=None):
    row = profile(db, profile_id)
    if revision is not None:
        check_revision(row, revision)
    snapshot = freeze(db, row, preset)
    db.merge(
        PersonalBinding(
            project_id=project_id, owner_id=row.owner_id, profile_id=row.id, snapshot=snapshot
        )
    )
    db.commit()
    return snapshot


def describe(snapshot):
    if not snapshot:
        return {"active": False, "rules": [], "message": "本次未使用个人经验"}
    return {
        "active": snapshot["active"],
        "profileId": snapshot["profileId"],
        "profileRevision": snapshot["profileRevision"],
        "digest": snapshot["digest"],
        "rules": [
            {
                "key": key,
                "label": LABELS[key],
                "value": value,
                "description": preference_description(key, value),
            }
            for key, value in snapshot["preferences"].items()
        ],
        "message": "个人偏好受事实和显示质量约束"
        if snapshot["active"]
        else "档案暂停或场景不匹配，本次使用默认流程",
    }


def compile_brief(brief, snapshot, explicit_instructions=""):
    result = copy.deepcopy(brief)
    prefs = snapshot.get("preferences", {}) if snapshot else {}
    # Free-form current instructions take precedence over inferred defaults.
    if (
        prefs.get("tone")
        and result.get("tone", "auto") == "auto"
        and not re.search(
            r"语气|严谨|活泼|克制|风格|tone|formal", explicit_instructions, re.IGNORECASE
        )
    ):
        result["tone"] = prefs["tone"]
        result["toneLabel"] = OPTIONS["tone"][prefs["tone"]]
    if not re.search(
        r"顺序|结构|大纲|结论|先.*后|order|structure", explicit_instructions, re.IGNORECASE
    ):
        result["narrativeOrder"] = prefs.get("narrative_order", "default")
    if not re.search(r"标题|title", explicit_instructions, re.IGNORECASE):
        result["titleStyle"] = prefs.get("title_style", "auto")
    if snapshot and snapshot.get("active"):
        result["personalExamples"] = snapshot.get("examples", [])
    return result


def compile_design(design, snapshot, *, explicit_style=False):
    from app.presentation_intelligence.art_director import PALETTES
    from app.presentation_intelligence.brand_kit import compile_brand_kit

    result = copy.deepcopy(design)
    prefs = snapshot.get("preferences", {}) if snapshot else {}
    if not prefs:
        return result
    reference = json.loads(prefs.get("reference_style", "{}")) if not explicit_style else {}
    if not explicit_style:
        if "cardRadius" in reference:
            result["radius"]["card"] = reference["cardRadius"]
        if reference.get("palette"):
            result["palette"] = reference["palette"]
        if reference.get("fontFamily"):
            result["typography"]["fontFamily"] = reference["fontFamily"]
        if prefs.get("palette"):
            result["palette"] = {
                key: value for key, value in PALETTES[prefs["palette"]].items() if key != "name"
            }
        palette = result["palette"]
        result["chart"]["series"] = [palette["primary"], palette["accent"], palette["deep"]]
        if prefs.get("font_family"):
            result["typography"]["fontFamily"] = prefs["font_family"]
    # This preference is a constrained candidate tie-break, never an override.
    result["personalization"] = {
        "preferredVariant": None if explicit_style else prefs.get("preferred_variant"),
        "preferredByRole": reference.get("preferredByRole", {}),
        "density": "balanced" if explicit_style else prefs.get("density", "balanced"),
    }
    if reference.get("layouts"):
        result["referenceLayouts"] = reference["layouts"]
    result["brandKit"] = compile_brand_kit(result)
    return result


def record_feedback(db, row, before, kind, instruction=""):
    if settings.public_test_mode:
        return
    binding = db.get(PersonalBinding, row.project_id)
    if not binding:
        return
    owner = db.get(PersonalIdentity, binding.owner_id)
    config = db.get(PersonalProfile, binding.profile_id)
    if (
        not owner
        or not config
        or not config.use_memory
        or not config.capture_feedback
        or not binding.snapshot.get("active")
    ):
        return
    if owner.epoch != binding.snapshot.get("epoch"):
        return
    # Store abstract operations, never a copy of business text or metrics.
    after = row.spec
    proposal = None
    if kind == "candidate-select":
        variant = (after.get("visualIntent") or {}).get("selectedVariant")
        if variant in OPTIONS["preferred_variant"]:
            proposal = {"key": "preferred_variant", "value": variant}
    elif re.search(r"结论式标题|标题.*(?:结论|判断)|结论先行", instruction):
        proposal = {"key": "title_style", "value": "takeaway"}
    elif re.search(r"主题式标题|标题.*主题", instruction):
        proposal = {"key": "title_style", "value": "topic"}
    if proposal is None:
        from app.personalization.cases import additional_edit_proposal
        proposal = additional_edit_proposal(before, after)
    from app.professional.review_diff import diff_slide_specs

    diff = diff_slide_specs(before, after)
    features = {
        "changedFields": diff["changedFields"],
        "requiresEvidenceReview": diff["requiresEvidenceReview"],
        "proposal": proposal,
    }
    if features["requiresEvidenceReview"]:
        features["proposal"] = None
    existing = db.scalar(
        select(PersonalFeedback).where(
            PersonalFeedback.slide_id == row.id,
            PersonalFeedback.revision == row.current_version,
            PersonalFeedback.kind == kind,
        )
    )
    if existing:
        return
    # Later edits supersede a pending observation from the same editing session.
    for pending in db.scalars(
        select(PersonalFeedback).where(
            PersonalFeedback.slide_id == row.id, PersonalFeedback.status == "pending"
        )
    ):
        pending.status = "superseded"
    event = PersonalFeedback(
            owner_id=owner.id,
            profile_id=config.id,
            project_id=row.project_id,
            slide_id=row.id,
            revision=row.current_version,
            epoch=owner.epoch,
            kind=kind,
            features=features,
            status="pending" if features["proposal"] and kind != "rollback" else "observed",
        )
    db.add(event)
    db.flush()
    db.add(PersonalOutbox(feedback_id=event.id, owner_id=owner.id, epoch=owner.epoch))


def feedback_view(row):
    return {
        "id": row.id,
        "projectId": row.project_id,
        "slideId": row.slide_id,
        "revision": row.revision,
        "kind": row.kind,
        "status": row.status,
        "features": row.features,
        "createdAt": row.created_at.isoformat(),
    }


def confirm_feedback(db, event_id):
    owner = identity(db)
    event = db.get(PersonalFeedback, event_id)
    if not event or event.owner_id != owner.id:
        raise HTTPException(404, "修改建议不存在")
    slide = db.get(SlideSpecRecord, event.slide_id)
    if (
        event.epoch != owner.epoch
        or not slide
        or slide.current_version != event.revision
        or event.status != "pending"
    ):
        raise HTTPException(409, "这次修改已被后续版本替代，不能作为当前偏好保存")
    row = profile(db, event.profile_id)
    if not row.capture_feedback or not row.use_memory:
        raise HTTPException(409, "请先启用该档案的使用与修改学习")
    proposal = event.features.get("proposal")
    if not proposal:
        raise HTTPException(422, "本次修改没有可安全提取的长期规则")
    item = put_memory(
        db, row, proposal["key"], proposal["value"], origin="accepted-edit", evidence=[event.id]
    )
    event.status = "confirmed"
    db.commit()
    return memory_view(item)


def reset_manifest(db, owner, scope, target_id):
    profiles = list(db.scalars(select(PersonalProfile).where(PersonalProfile.owner_id == owner.id)))
    if scope == "profile":
        profiles = [profile(db, target_id)]
    memories = list(db.scalars(select(PersonalMemory).where(PersonalMemory.owner_id == owner.id)))
    if scope == "memory":
        target = next((item for item in memories if item.id == target_id), None)
        if not target:
            raise HTTPException(404, "经验不存在")
        profiles = [profile(db, target.profile_id)]
        memories = [
            item
            for item in memories
            if item.profile_id == target.profile_id and item.key == target.key
        ]
    else:
        memories = [item for item in memories if item.profile_id in {p.id for p in profiles}]
    ids = [item.id for item in profiles]
    source_ids = set(db.scalars(select(PersonalCase.id).where(PersonalCase.profile_id.in_(ids)))) | set(db.scalars(select(PersonalReference.id).where(PersonalReference.profile_id.in_(ids))))
    if scope == "memory" and source_ids:
        inherited = list(db.scalars(select(PersonalMemory).where(PersonalMemory.profile_id.in_(ids))))
        memories = list({item.id: item for item in [*memories, *(item for item in inherited if source_ids.intersection(item.evidence))]}.values())
    feedback = list(
        db.scalars(select(PersonalFeedback.id).where(PersonalFeedback.profile_id.in_(ids)))
    )
    return {
        "scope": scope,
        "targetId": target_id,
        "profiles": [{"id": p.id, "revision": p.revision} for p in profiles],
        "memoryIds": sorted(item.id for item in memories),
        "feedbackIds": sorted(feedback),
        "caseIds": sorted(db.scalars(select(PersonalCase.id).where(PersonalCase.profile_id.in_(ids)))),
        "referenceIds": sorted(db.scalars(select(PersonalReference.id).where(PersonalReference.profile_id.in_(ids)))),
        "epoch": owner.epoch,
        "retained": ["项目、材料、已完成 PPT 与编辑历史", "模型连接与凭据", "用户导出的经验备份"],
    }


def digest_manifest(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


def preview_reset(db, scope, target_id):
    owner = identity(db)
    manifest = reset_manifest(db, owner, scope, target_id)
    row = PersonalReset(
        owner_id=owner.id, scope=scope, target_id=target_id, epoch=owner.epoch, manifest=manifest
    )
    db.add(row)
    db.commit()
    return {
        "id": row.id,
        "digest": digest_manifest(manifest),
        "memoryCount": len(manifest["memoryIds"]),
        "profileCount": len(manifest["profiles"]),
        "feedbackCount": len(manifest["feedbackIds"]),
        "caseCount": len(manifest.get("caseIds", [])),
        "referenceCount": len(manifest.get("referenceIds", [])),
        "retained": manifest["retained"],
        "message": "旧学习记录将失效；已完成作品保留。清除不会自动创建备份。",
    }


def execute_reset(db, preview_id, digest):
    with lock:
        owner = identity(db)
        row = db.get(PersonalReset, preview_id)
        if not row or row.owner_id != owner.id:
            raise HTTPException(404, "清理预览不存在")
        if digest != digest_manifest(row.manifest):
            raise HTTPException(409, "清理清单不匹配")
        if row.status == "completed":
            return row.receipt
        if row.created_at.replace(tzinfo=None) < datetime.now(UTC).replace(tzinfo=None) - timedelta(
            minutes=10
        ):
            raise HTTPException(409, "清理预览已过期，请重新预览")
        current = reset_manifest(db, owner, row.scope, row.target_id)
        if digest_manifest(current) != digest:
            raise HTTPException(409, "记忆已发生变化，请重新预览清理范围")
        ids = [item["id"] for item in current["profiles"]]
        owner.epoch += 1
        from app.personalization.private_files import erase_private_reference
        for reference in db.scalars(select(PersonalReference).where(PersonalReference.id.in_(current.get("referenceIds", [])))):
            erase_private_reference(reference)
            db.delete(reference)
        db.execute(delete(PersonalCase).where(PersonalCase.id.in_(current.get("caseIds", []))))
        db.execute(delete(PersonalOutbox).where(PersonalOutbox.owner_id == owner.id))
        from app.personalization.private_files import erase_comparison_files
        erase_comparison_files(db, owner.id)
        db.execute(delete(PersonalComparison).where(PersonalComparison.owner_id == owner.id))
        db.execute(delete(PersonalMemory).where(PersonalMemory.id.in_(current["memoryIds"])))
        db.execute(delete(PersonalFeedback).where(PersonalFeedback.profile_id.in_(ids)))
        affected = list(
            db.scalars(
                select(PersonalBinding.project_id).where(PersonalBinding.profile_id.in_(ids))
            )
        )
        db.execute(delete(PersonalBinding).where(PersonalBinding.profile_id.in_(ids)))
        if row.scope == "all":
            db.execute(delete(PersonalProfile).where(PersonalProfile.owner_id == owner.id))
        elif row.scope == "profile":
            config = profile(db, row.target_id)
            config.capture_feedback = False
            config.use_memory = False
            config.revision += 1
        else:
            config = profile(db, ids[0])
            config.revision += 1
        # Surviving profiles retain their state; only new jobs use refreshed snapshots.
        for binding in db.scalars(
            select(PersonalBinding).where(PersonalBinding.owner_id == owner.id)
        ):
            config = db.get(PersonalProfile, binding.profile_id)
            if config:
                binding.snapshot = freeze(db, config, binding.snapshot.get("scenario", "all"))
        cancelled = 0
        for job in db.scalars(select(Job).where(Job.status.in_({"running", "queued"}))):
            workflow = (job.checkpoint or {}).get("workflow", {})
            from app.db.models import ProjectOwner
            project_owner = db.get(ProjectOwner, job.project_id) if job.project_id else None
            same_owner = not settings.private_accounts_mode or (project_owner and project_owner.owner_id == owner.id)
            if same_owner and (job.project_id in affected or workflow.get("personalizationEpoch")):
                job.status = "cancelled"
                job.checkpoint = {
                    "stage": "cancelled",
                    "label": "记忆已清除，任务已失效",
                    "cancelRequested": True,
                    "workflow": {"resumable": False},
                }
                cancelled += 1
        cache_report = {"cleaned": 0, "failed": 0}
        from app.personalization.data_management import scrub_project_cache

        for project_id in affected:
            project_row = db.get(Project, project_id)
            if project_row:
                cleaned = scrub_project_cache(project_row.artifact_path, settings.artifact_root)
                for key in cache_report:
                    cache_report[key] += cleaned[key]
            deck = db.get(DeckSpecRecord, project_id)
            if deck:
                repro = copy.deepcopy(deck.reproducibility or {})
                repro.pop("personalization", None)
                repro.get("request", {}).pop("profileId", None)
                deck.reproducibility = repro
                design = copy.deepcopy(deck.design_system or {})
                design.pop("personalization", None)
                deck.design_system = design
            for slide in db.scalars(
                select(SlideSpecRecord).where(SlideSpecRecord.project_id == project_id)
            ):
                spec = copy.deepcopy(slide.spec)
                spec.get("designSystem", {}).pop("personalization", None)
                spec.pop("personalizationBaseline", None)
                slide.spec = spec
                for version in db.scalars(
                    select(SlideVersion).where(SlideVersion.slide_id == slide.id)
                ):
                    saved = copy.deepcopy(version.spec)
                    saved.get("designSystem", {}).pop("personalization", None)
                    saved.pop("personalizationBaseline", None)
                    version.spec = saved
        row.status = "completed"
        row.receipt = {
            "id": row.id,
            "status": "completed",
            "epoch": owner.epoch,
            "deletedMemories": len(current["memoryIds"]),
            "deletedCases": len(current.get("caseIds", [])),
            "deletedReferences": len(current.get("referenceIds", [])),
            "deletedFeedback": len(current["feedbackIds"]),
            "cancelledJobs": cancelled,
            "cacheCleanup": cache_report,
            "unpublishedFiles": "正在运行的渲染进程退出时删除临时文件；不会发布旧代次结果",
            "retained": current["retained"],
            "verification": "目标经验、反馈与生成绑定已清除；旧任务代次不可提交",
        }
        # Historical previews must not retain identifiers of erased personal items.
        db.execute(
            delete(PersonalReset).where(
                PersonalReset.owner_id == owner.id, PersonalReset.id != row.id
            )
        )
        db.commit()
        return row.receipt
