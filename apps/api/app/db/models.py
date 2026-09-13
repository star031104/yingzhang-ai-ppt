import secrets
import uuid
from datetime import datetime

from app.db.base import Base, TimestampMixin
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship


def new_id():
    return str(uuid.uuid4())


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(40), default="ready")
    artifact_path: Mapped[str] = mapped_column(Text)


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0)
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Provider(TimestampMixin, Base):
    __tablename__ = "providers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    base_url: Mapped[str] = mapped_column(Text)
    api_key_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    extra_headers: Mapped[dict] = mapped_column(JSON, default=dict)
    models: Mapped[list["ModelConfig"]] = relationship(cascade="all, delete-orphan")


class ModelConfig(TimestampMixin, Base):
    __tablename__ = "model_configs"
    __table_args__ = (UniqueConstraint("provider_id", "model_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"))
    model_id: Mapped[str] = mapped_column(String(240))
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    quality_profile: Mapped[dict] = mapped_column(JSON, default=dict)


class RoleAssignment(TimestampMixin, Base):
    __tablename__ = "role_assignments"
    role: Mapped[str] = mapped_column(String(60), primary_key=True)
    model_config_id: Mapped[str] = mapped_column(ForeignKey("model_configs.id"))


class SourceDocument(TimestampMixin, Base):
    __tablename__ = "source_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    media_type: Mapped[str] = mapped_column(String(120))
    sha256: Mapped[str] = mapped_column(String(64))
    artifact_path: Mapped[str] = mapped_column(Text)
    model: Mapped[dict] = mapped_column(JSON, default=dict)


class DeckSpecRecord(TimestampMixin, Base):
    __tablename__ = "deck_specs"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    narrative: Mapped[dict] = mapped_column(JSON, default=dict)
    design_system: Mapped[dict] = mapped_column(JSON, default=dict)
    reproducibility: Mapped[dict] = mapped_column(JSON, default=dict)


class SlideSpecRecord(TimestampMixin, Base):
    __tablename__ = "slide_specs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    position: Mapped[int] = mapped_column()
    spec: Mapped[dict] = mapped_column(JSON, default=dict)
    current_version: Mapped[int] = mapped_column(default=1)


class SlideCandidate(TimestampMixin, Base):
    __tablename__ = "slide_candidates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slide_id: Mapped[str] = mapped_column(ForeignKey("slide_specs.id"), index=True)
    variant: Mapped[str] = mapped_column(String(40))
    artifact_path: Mapped[str] = mapped_column(Text)
    score: Mapped[dict] = mapped_column(JSON, default=dict)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)


class SlideVersion(TimestampMixin, Base):
    __tablename__ = "slide_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slide_id: Mapped[str] = mapped_column(ForeignKey("slide_specs.id"), index=True)
    version: Mapped[int] = mapped_column()
    spec: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text, default="generated")


class ExportRecord(TimestampMixin, Base):
    __tablename__ = "exports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    format: Mapped[str] = mapped_column(String(20))
    artifact_path: Mapped[str] = mapped_column(Text)
    report: Mapped[dict] = mapped_column(JSON, default=dict)


class InstalledSkill(TimestampMixin, Base):
    __tablename__ = "skills"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    version: Mapped[str] = mapped_column(String(40))
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    sha256: Mapped[str] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(Text)
    scripts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class ProjectSkill(TimestampMixin, Base):
    __tablename__ = "project_skills"
    __table_args__ = (UniqueConstraint("project_id", "skill_id"),)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )


class SlideEditMessage(TimestampMixin, Base):
    __tablename__ = "slide_edit_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slide_id: Mapped[str] = mapped_column(ForeignKey("slide_specs.id"), index=True)
    actor: Mapped[str] = mapped_column(String(80), default="本机管理员")
    instruction: Mapped[str] = mapped_column(Text)
    target: Mapped[dict] = mapped_column(JSON, default=dict)
    change_set: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(default=1)


class LicensedAsset(TimestampMixin, Base):
    __tablename__ = "licensed_assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    slide_id: Mapped[str | None] = mapped_column(ForeignKey("slide_specs.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(240))
    kind: Mapped[str] = mapped_column(String(40), default="image")
    provider: Mapped[str] = mapped_column(String(120), default="uploaded")
    source_url: Mapped[str] = mapped_column(Text, default="")
    license: Mapped[str] = mapped_column(String(120), default="unknown")
    attribution: Mapped[str] = mapped_column(Text, default="")
    artifact_path: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)


class BrandAsset(TimestampMixin, Base):
    __tablename__ = "brand_assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(240))
    kind: Mapped[str] = mapped_column(String(40), default="logo")
    artifact_path: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ProjectMember(TimestampMixin, Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(30), default="viewer")


class ApprovalRecord(TimestampMixin, Base):
    __tablename__ = "approval_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    stage: Mapped[str] = mapped_column(String(30), default="final")
    status: Mapped[str] = mapped_column(String(30), default="requested")
    actor: Mapped[str] = mapped_column(String(80))
    comment: Mapped[str] = mapped_column(Text, default="")


class PublishedDeck(TimestampMixin, Base):
    __tablename__ = "published_decks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, default=lambda: secrets.token_urlsafe(24))
    status: Mapped[str] = mapped_column(String(30), default="active")
    artifact_path: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String(80), default="本机管理员")


class ImportedDeck(TimestampMixin, Base):
    __tablename__ = "imported_decks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, unique=True)
    source_name: Mapped[str] = mapped_column(String(300))
    artifact_path: Mapped[str] = mapped_column(Text)
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    current_version: Mapped[int] = mapped_column(default=1)


class ImportedObjectEdit(TimestampMixin, Base):
    __tablename__ = "imported_object_edits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    imported_deck_id: Mapped[str] = mapped_column(ForeignKey("imported_decks.id"), index=True)
    slide_index: Mapped[int] = mapped_column()
    object_id: Mapped[str] = mapped_column(String(80))
    before_text: Mapped[str] = mapped_column(Text, default="")
    after_text: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(80), default="本机管理员")
    version: Mapped[int] = mapped_column(default=1)


class EvaluationRun(TimestampMixin, Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    suite: Mapped[str] = mapped_column(String(80), default="professional-fixed-v2")
    blind_token: Mapped[str] = mapped_column(String(64), unique=True, default=lambda: secrets.token_urlsafe(18))
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="completed")


class BlindReview(TimestampMixin, Base):
    __tablename__ = "blind_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evaluation_run_id: Mapped[str] = mapped_column(ForeignKey("evaluation_runs.id"), index=True)
    reviewer_alias: Mapped[str] = mapped_column(String(80), default="匿名评审")
    candidate_label: Mapped[str] = mapped_column(String(20), default="A")
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    comment: Mapped[str] = mapped_column(Text, default="")


class PersonalIdentity(TimestampMixin, Base):
    __tablename__ = "personal_identities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    epoch: Mapped[int] = mapped_column(default=1)


class PersonalProfile(TimestampMixin, Base):
    __tablename__ = "personal_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(120))
    scenario: Mapped[str] = mapped_column(String(40), default="all")
    revision: Mapped[int] = mapped_column(default=1)
    use_memory: Mapped[bool] = mapped_column(Boolean, default=True)
    capture_feedback: Mapped[bool] = mapped_column(Boolean, default=False)


class PersonalMemory(TimestampMixin, Base):
    __tablename__ = "personal_memories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(String(36), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    key: Mapped[str] = mapped_column(String(80))
    value: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="confirmed")
    origin: Mapped[str] = mapped_column(String(40), default="explicit")
    revision: Mapped[int] = mapped_column(default=1)
    evidence: Mapped[list] = mapped_column(JSON, default=list)


class PersonalBinding(TimestampMixin, Base):
    __tablename__ = "personal_bindings"
    project_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    profile_id: Mapped[str] = mapped_column(String(36), index=True)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)


class PersonalFeedback(TimestampMixin, Base):
    __tablename__ = "personal_feedback"
    __table_args__ = (UniqueConstraint("slide_id", "revision", "kind"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    profile_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    slide_id: Mapped[str] = mapped_column(String(36), index=True)
    revision: Mapped[int] = mapped_column()
    epoch: Mapped[int] = mapped_column()
    kind: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    features: Mapped[dict] = mapped_column(JSON, default=dict)


class PersonalReset(TimestampMixin, Base):
    __tablename__ = "personal_resets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    scope: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    epoch: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(30), default="preview")
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    receipt: Mapped[dict] = mapped_column(JSON, default=dict)


class PersonalAccount(TimestampMixin, Base):
    __tablename__ = "personal_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="tester")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class PersonalSession(Base):
    __tablename__ = "personal_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class ProjectOwner(Base):
    __tablename__ = "project_owners"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)


class PersonalCase(TimestampMixin, Base):
    __tablename__ = "personal_cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    profile_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    label: Mapped[str] = mapped_column(String(120))
    scenario: Mapped[str] = mapped_column(String(40))
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="candidate")
    source_hash: Mapped[str] = mapped_column(String(64))


class PersonalReference(TimestampMixin, Base):
    __tablename__ = "personal_references"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    profile_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(180))
    artifact_path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=False)


class PersonalOutbox(TimestampMixin, Base):
    __tablename__ = "personal_outbox"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    feedback_id: Mapped[str] = mapped_column(String(36), unique=True)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    epoch: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(24), default="pending")


class PersonalComparison(TimestampMixin, Base):
    __tablename__ = "personal_comparisons"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    epoch: Mapped[int] = mapped_column()
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    reviews: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="pending")


class DeliveryVerification(TimestampMixin, Base):
    __tablename__ = "delivery_verifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    software: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default="needs-review")
    report: Mapped[dict] = mapped_column(JSON, default=dict)
