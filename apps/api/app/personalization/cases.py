"""Abstract, inspectable examples. Historical business text is never prompt evidence."""
import copy
import hashlib
import json
from collections import Counter

from fastapi import HTTPException
from sqlalchemy import delete, select

from app.db.models import PersonalCase, PersonalFeedback, PersonalMemory, PersonalOutbox, SlideSpecRecord
from app.personalization.schemas import OPTIONS


def extract_case(slides):
    roles = [str(slide.get("role", "content")) for slide in slides]
    variants = Counter()
    fonts = Counter()
    title_lengths = []
    takeaway = 0
    for slide in slides:
        title = str(slide.get("content", {}).get("title", ""))
        title_lengths.append(len(title))
        takeaway += bool(title and title == slide.get("message"))
        variant = slide.get("visualIntent", {}).get("selectedVariant")
        if variant in OPTIONS["preferred_variant"]:
            variants[variant] += 1
        font = slide.get("designSystem", {}).get("typography", {}).get("fontFamily")
        if font in OPTIONS["font_family"]:
            fonts[font] += 1
    rules = {}
    if fonts:
        rules["font_family"] = fonts.most_common(1)[0][0]
    if variants:
        rules["preferred_variant"] = variants.most_common(1)[0][0]
    if len(roles) > 2 and roles[1] in {"insight", "conclusion"}:
        rules["narrative_order"] = "conclusion-first"
    if takeaway >= max(2, len(slides) / 2):
        rules["title_style"] = "takeaway"
    return {"version": 1, "slideCount": len(slides), "roleSequence": roles[:60],
            "averageTitleLength": round(sum(title_lengths) / max(1, len(slides))),
            "rules": rules, "variants": dict(variants), "retainsBusinessText": False}


def case_view(row):
    return {"id": row.id, "label": row.label, "scenario": row.scenario, "status": row.status,
            "features": row.features, "projectId": row.project_id, "createdAt": row.created_at.isoformat()}


def capture_project_case(db, config, project, slides, label, quality):
    digest = hashlib.sha256(json.dumps(slides, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    existing = db.scalar(select(PersonalCase).where(PersonalCase.profile_id == config.id, PersonalCase.source_hash == digest))
    if existing:
        return existing
    features = extract_case(slides)
    features["quality"] = {"passed": bool(quality.get("passed")), "blockingErrors": quality.get("blockingErrors", 0)}
    row = PersonalCase(owner_id=config.owner_id, profile_id=config.id, project_id=project.id,
                       label=label.strip(), scenario=config.scenario, features=features, source_hash=digest)
    db.add(row)
    config.revision += 1
    db.flush()
    return row


def retrieve_cases(db, config, scenario, limit=4):
    rows = db.scalars(select(PersonalCase).where(PersonalCase.owner_id == config.owner_id,
        PersonalCase.profile_id == config.id, PersonalCase.status == "confirmed").order_by(PersonalCase.updated_at.desc()).limit(200))
    ranked = sorted((row for row in rows if row.scenario in {"all", scenario}),
                    key=lambda row: (row.scenario == scenario, row.features.get("quality", {}).get("passed", False)), reverse=True)
    # Include abstractions only; user labels can contain business identifiers.
    return [{"caseId": row.id, "features": copy.deepcopy(row.features)} for row in ranked[:limit]]


def confirm_case(db, config, row):
    if not row.features.get("quality", {}).get("passed"):
        raise HTTPException(409, "该作品尚未通过质量检查，请修复并重新采集")
    row.status = "confirmed"
    config.revision += 1
    from app.personalization.service import put_memory
    for key, value in row.features.get("rules", {}).items():
        exists = db.scalar(select(PersonalMemory).where(PersonalMemory.profile_id == config.id,
            PersonalMemory.key == key, PersonalMemory.status == "confirmed"))
        if not exists:
            put_memory(db, config, key, value, origin="case", status="candidate", evidence=[row.id])


def additional_edit_proposal(before, after):
    old = before.get("designSystem", {})
    new = after.get("designSystem", {})
    font = new.get("typography", {}).get("fontFamily")
    if font != old.get("typography", {}).get("fontFamily") and font in OPTIONS["font_family"]:
        return {"key": "font_family", "value": font}
    if new.get("palette") and new.get("palette") != old.get("palette"):
        from app.personalization.schemas import validate_preference
        try:
            value = validate_preference("reference_style", json.dumps({"palette": new["palette"]}))
            return {"key": "reference_style", "value": value}
        except ValueError:
            pass
    return None


def drain_outbox(db, owner):
    """Idempotent, lazy consumer; interruption cannot lose a committed observation."""
    for pending in db.scalars(select(PersonalOutbox).where(PersonalOutbox.owner_id == owner.id,
        PersonalOutbox.status == "pending").order_by(PersonalOutbox.created_at).limit(200)):
        event = db.get(PersonalFeedback, pending.feedback_id)
        slide = db.get(SlideSpecRecord, event.slide_id) if event else None
        if pending.epoch != owner.epoch or not event or not slide or slide.current_version != event.revision:
            pending.status = "discarded"
            continue
        # Only aggregate live candidates; never confirm on behalf of the user.
        proposal = event.features.get("proposal")
        similar = 0
        if proposal:
            for prior in db.scalars(select(PersonalFeedback).where(PersonalFeedback.profile_id == event.profile_id,
                PersonalFeedback.status.in_({"confirmed", "pending"}), PersonalFeedback.epoch == owner.epoch)):
                similar += prior.features.get("proposal") == proposal
        event.features = {**event.features, "supportCount": similar, "extractionVersion": "abstract-v2"}
        pending.status = "processed"
    db.flush()


def delete_case(db, config, case_id):
    row = db.get(PersonalCase, case_id)
    if not row or row.owner_id != config.owner_id or row.profile_id != config.id:
        raise HTTPException(404, "案例不存在")
    for rule in db.scalars(select(PersonalMemory).where(PersonalMemory.profile_id == config.id)):
        if case_id in rule.evidence:
            db.delete(rule)
    db.execute(delete(PersonalCase).where(PersonalCase.id == case_id))
    config.revision += 1
