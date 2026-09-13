import copy

from sqlalchemy import delete, select

from app.db.models import DeckSpecRecord, Job, ProjectOwner, PersonalBinding, PersonalIdentity, PersonalMemory, PersonalOutbox, PersonalComparison, Project, SlideSpecRecord, SlideVersion
from app.personalization.data_management import scrub_personal_hints, scrub_project_cache
from app.config import settings


def delete_derived_rules(db, profile, source_ids):
    sources = set(source_ids)
    for rule in db.scalars(select(PersonalMemory).where(PersonalMemory.profile_id == profile.id)):
        if sources.intersection(rule.evidence):
            db.delete(rule)


def invalidate_profile(db, profile):
    owner = db.get(PersonalIdentity, profile.owner_id)
    owner.epoch += 1
    db.execute(delete(PersonalOutbox).where(PersonalOutbox.owner_id == owner.id))
    from app.personalization.private_files import erase_comparison_files
    erase_comparison_files(db, owner.id)
    db.execute(delete(PersonalComparison).where(PersonalComparison.owner_id == owner.id))
    for binding in db.scalars(select(PersonalBinding).where(PersonalBinding.profile_id == profile.id)):
        project = db.get(Project, binding.project_id)
        deck = db.get(DeckSpecRecord, binding.project_id)
        if deck:
            deck.reproducibility = scrub_personal_hints(copy.deepcopy(deck.reproducibility))
            deck.design_system = scrub_personal_hints(copy.deepcopy(deck.design_system))
        if project:
            scrub_project_cache(project.artifact_path, settings.artifact_root)
        for slide in db.scalars(select(SlideSpecRecord).where(SlideSpecRecord.project_id == binding.project_id)):
            slide.spec = scrub_personal_hints(copy.deepcopy(slide.spec))
            for version in db.scalars(select(SlideVersion).where(SlideVersion.slide_id == slide.id)):
                version.spec = scrub_personal_hints(copy.deepcopy(version.spec))
        db.delete(binding)
    for job in db.scalars(select(Job).where(Job.status.in_({"queued", "running"}))):
        job_owner = db.get(ProjectOwner, job.project_id) if job.project_id else None
        if (not settings.private_accounts_mode or (job_owner and job_owner.owner_id == owner.id)) and (job.checkpoint or {}).get("workflow", {}).get("personalizationEpoch"):
            job.status = "cancelled"
            job.checkpoint = {"stage": "cancelled", "label": "经验来源已删除", "cancelRequested": True, "workflow": {"resumable": False}}
    from app.personalization.service import freeze
    from app.db.models import PersonalProfile
    for binding in db.scalars(select(PersonalBinding).where(PersonalBinding.owner_id == owner.id, PersonalBinding.profile_id != profile.id)):
        config = db.get(PersonalProfile, binding.profile_id)
        if config:
            binding.snapshot = freeze(db, config, binding.snapshot.get("scenario", "all"))
