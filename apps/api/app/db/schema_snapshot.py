"""Frozen schema contract as of Alembic revision 0005.

This file intentionally does not import ORM models. Changes require a new
reviewed migration so fresh installs and upgrades converge on one schema.
"""

import sqlalchemy as sa
from sqlalchemy import inspect

FROZEN_TABLES = {
    "approval_records", "blind_reviews", "brand_assets", "deck_specs",
    "delivery_verifications", "evaluation_runs", "exports", "imported_decks",
    "imported_object_edits", "jobs", "licensed_assets", "model_configs",
    "model_usage_records", "personal_accounts", "personal_bindings", "personal_cases",
    "personal_comparisons", "personal_feedback", "personal_identities", "personal_memories",
    "personal_outbox", "personal_profiles", "personal_references", "personal_resets",
    "personal_sessions", "project_members", "project_owners", "project_skills", "projects",
    "providers", "published_decks", "role_assignments", "skills", "slide_candidates",
    "slide_edit_messages", "slide_specs", "slide_versions", "source_documents",
}


def create_missing_schema(operations, bind, *, allow_legacy_usage_columns=False):
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    unexpected_tables = existing_tables - FROZEN_TABLES - {"alembic_version"}
    if unexpected_tables:
        raise RuntimeError(
            f"数据库包含未登记的数据表 {sorted(unexpected_tables)}；"
            "请为它们建立显式迁移后再升级。"
        )
    if 'personal_accounts' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('personal_accounts')}
        expected_columns = {'created_at', 'enabled', 'id', 'password_hash', 'role', 'updated_at', 'username'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in personal_accounts: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'personal_bindings' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('personal_bindings')}
        expected_columns = {'created_at', 'owner_id', 'profile_id', 'project_id', 'snapshot', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in personal_bindings: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'personal_cases' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('personal_cases')}
        expected_columns = {'created_at', 'features', 'id', 'label', 'owner_id', 'profile_id', 'project_id', 'scenario', 'source_hash', 'status', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in personal_cases: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'personal_feedback' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('personal_feedback')}
        expected_columns = {'created_at', 'epoch', 'features', 'id', 'kind', 'owner_id', 'profile_id', 'project_id', 'revision', 'slide_id', 'status', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in personal_feedback: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'personal_identities' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('personal_identities')}
        expected_columns = {'created_at', 'epoch', 'id', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in personal_identities: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'personal_memories' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('personal_memories')}
        expected_columns = {'created_at', 'evidence', 'id', 'key', 'origin', 'owner_id', 'profile_id', 'revision', 'status', 'updated_at', 'value'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in personal_memories: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'personal_outbox' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('personal_outbox')}
        expected_columns = {'created_at', 'epoch', 'feedback_id', 'id', 'owner_id', 'status', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in personal_outbox: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'personal_profiles' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('personal_profiles')}
        expected_columns = {'capture_feedback', 'created_at', 'id', 'name', 'owner_id', 'revision', 'scenario', 'updated_at', 'use_memory'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in personal_profiles: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'personal_references' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('personal_references')}
        expected_columns = {'active', 'analysis', 'artifact_path', 'created_at', 'id', 'name', 'owner_id', 'profile_id', 'sha256', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in personal_references: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'personal_resets' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('personal_resets')}
        expected_columns = {'created_at', 'epoch', 'id', 'manifest', 'owner_id', 'receipt', 'scope', 'status', 'target_id', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in personal_resets: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'personal_sessions' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('personal_sessions')}
        expected_columns = {'expires_at', 'owner_id', 'token_hash'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in personal_sessions: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'projects' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('projects')}
        expected_columns = {'artifact_path', 'created_at', 'id', 'name', 'status', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in projects: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'providers' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('providers')}
        expected_columns = {'api_key_ref', 'base_url', 'created_at', 'enabled', 'extra_headers', 'id', 'name', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in providers: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'skills' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('skills')}
        expected_columns = {'created_at', 'id', 'manifest', 'path', 'scripts_enabled', 'sha256', 'updated_at', 'version'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in skills: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'approval_records' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('approval_records')}
        expected_columns = {'actor', 'comment', 'created_at', 'id', 'project_id', 'stage', 'status', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in approval_records: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'brand_assets' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('brand_assets')}
        expected_columns = {'artifact_path', 'created_at', 'id', 'kind', 'metadata_json', 'name', 'project_id', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in brand_assets: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'deck_specs' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('deck_specs')}
        expected_columns = {'created_at', 'design_system', 'narrative', 'project_id', 'reproducibility', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in deck_specs: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'delivery_verifications' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('delivery_verifications')}
        expected_columns = {'created_at', 'file_hash', 'id', 'project_id', 'report', 'software', 'status', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in delivery_verifications: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'evaluation_runs' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('evaluation_runs')}
        expected_columns = {'blind_token', 'created_at', 'id', 'metrics', 'project_id', 'status', 'suite', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in evaluation_runs: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'exports' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('exports')}
        expected_columns = {'artifact_path', 'created_at', 'format', 'id', 'project_id', 'report', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in exports: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'imported_decks' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('imported_decks')}
        expected_columns = {'analysis', 'artifact_path', 'created_at', 'current_version', 'id', 'project_id', 'source_name', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in imported_decks: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'jobs' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('jobs')}
        expected_columns = {'checkpoint', 'created_at', 'error', 'id', 'kind', 'progress', 'project_id', 'status', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in jobs: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'model_configs' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('model_configs')}
        expected_columns = {'capabilities', 'created_at', 'id', 'model_id', 'provider_id', 'quality_profile', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in model_configs: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'model_usage_records' in existing_tables and not allow_legacy_usage_columns:
        actual_columns = {column["name"] for column in inspector.get_columns('model_usage_records')}
        expected_columns = {'created_at', 'id', 'input_tokens', 'model_id', 'output_tokens', 'project_id', 'request_count', 'unreported_requests', 'updated_at', 'usage_requests'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in model_usage_records: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'personal_comparisons' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('personal_comparisons')}
        expected_columns = {'created_at', 'epoch', 'id', 'owner_id', 'payload', 'project_id', 'reviews', 'status', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in personal_comparisons: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'project_members' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('project_members')}
        expected_columns = {'created_at', 'id', 'name', 'project_id', 'role', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in project_members: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'project_owners' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('project_owners')}
        expected_columns = {'owner_id', 'project_id'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in project_owners: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'project_skills' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('project_skills')}
        expected_columns = {'created_at', 'project_id', 'skill_id', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in project_skills: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'published_decks' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('published_decks')}
        expected_columns = {'artifact_path', 'created_at', 'created_by', 'expires_at', 'id', 'project_id', 'status', 'token', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in published_decks: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'slide_specs' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('slide_specs')}
        expected_columns = {'created_at', 'current_version', 'id', 'position', 'project_id', 'spec', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in slide_specs: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'source_documents' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('source_documents')}
        expected_columns = {'artifact_path', 'created_at', 'id', 'media_type', 'model', 'name', 'project_id', 'sha256', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in source_documents: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'blind_reviews' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('blind_reviews')}
        expected_columns = {'candidate_label', 'comment', 'created_at', 'evaluation_run_id', 'id', 'reviewer_alias', 'scores', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in blind_reviews: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'imported_object_edits' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('imported_object_edits')}
        expected_columns = {'actor', 'after_text', 'before_text', 'created_at', 'id', 'imported_deck_id', 'object_id', 'slide_index', 'updated_at', 'version'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in imported_object_edits: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'licensed_assets' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('licensed_assets')}
        expected_columns = {'approved', 'artifact_path', 'attribution', 'created_at', 'id', 'kind', 'license', 'metadata_json', 'name', 'project_id', 'provider', 'slide_id', 'source_url', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in licensed_assets: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'role_assignments' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('role_assignments')}
        expected_columns = {'created_at', 'model_config_id', 'role', 'updated_at'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in role_assignments: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'slide_candidates' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('slide_candidates')}
        expected_columns = {'artifact_path', 'created_at', 'id', 'score', 'selected', 'slide_id', 'updated_at', 'variant'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in slide_candidates: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'slide_edit_messages' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('slide_edit_messages')}
        expected_columns = {'actor', 'change_set', 'created_at', 'id', 'instruction', 'slide_id', 'target', 'updated_at', 'version'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in slide_edit_messages: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'slide_versions' in existing_tables:
        actual_columns = {column["name"] for column in inspector.get_columns('slide_versions')}
        expected_columns = {'created_at', 'id', 'reason', 'slide_id', 'spec', 'updated_at', 'version'}
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(f"Database schema drift in slide_versions: missing={missing}, extra={extra}; add a forward Alembic migration.")
    if 'personal_accounts' not in existing_tables:
        operations.create_table('personal_accounts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username')
        )
        existing_tables.add('personal_accounts')
    if 'personal_bindings' not in existing_tables:
        operations.create_table('personal_bindings',
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('profile_id', sa.String(length=36), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('project_id')
        )
        existing_tables.add('personal_bindings')
    if 'personal_cases' not in existing_tables:
        operations.create_table('personal_cases',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('profile_id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=True),
        sa.Column('label', sa.String(length=120), nullable=False),
        sa.Column('scenario', sa.String(length=40), nullable=False),
        sa.Column('features', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('source_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('personal_cases')
    if 'personal_feedback' not in existing_tables:
        operations.create_table('personal_feedback',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('profile_id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('slide_id', sa.String(length=36), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('epoch', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('features', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slide_id', 'revision', 'kind')
        )
        existing_tables.add('personal_feedback')
    if 'personal_identities' not in existing_tables:
        operations.create_table('personal_identities',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('epoch', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('personal_identities')
    if 'personal_memories' not in existing_tables:
        operations.create_table('personal_memories',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('profile_id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('key', sa.String(length=80), nullable=False),
        sa.Column('value', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('origin', sa.String(length=40), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('evidence', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('personal_memories')
    if 'personal_outbox' not in existing_tables:
        operations.create_table('personal_outbox',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('feedback_id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('epoch', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('feedback_id')
        )
        existing_tables.add('personal_outbox')
    if 'personal_profiles' not in existing_tables:
        operations.create_table('personal_profiles',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('scenario', sa.String(length=40), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('use_memory', sa.Boolean(), nullable=False),
        sa.Column('capture_feedback', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('personal_profiles')
    if 'personal_references' not in existing_tables:
        operations.create_table('personal_references',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('profile_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=180), nullable=False),
        sa.Column('artifact_path', sa.Text(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('analysis', sa.JSON(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('personal_references')
    if 'personal_resets' not in existing_tables:
        operations.create_table('personal_resets',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('scope', sa.String(length=40), nullable=False),
        sa.Column('target_id', sa.String(length=36), nullable=True),
        sa.Column('epoch', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('manifest', sa.JSON(), nullable=False),
        sa.Column('receipt', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('personal_resets')
    if 'personal_sessions' not in existing_tables:
        operations.create_table('personal_sessions',
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('token_hash')
        )
        existing_tables.add('personal_sessions')
    if 'projects' not in existing_tables:
        operations.create_table('projects',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('status', sa.String(length=40), nullable=False),
        sa.Column('artifact_path', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('projects')
    if 'providers' not in existing_tables:
        operations.create_table('providers',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('base_url', sa.Text(), nullable=False),
        sa.Column('api_key_ref', sa.String(length=200), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('extra_headers', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
        )
        existing_tables.add('providers')
    if 'skills' not in existing_tables:
        operations.create_table('skills',
        sa.Column('id', sa.String(length=120), nullable=False),
        sa.Column('version', sa.String(length=40), nullable=False),
        sa.Column('manifest', sa.JSON(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('path', sa.Text(), nullable=False),
        sa.Column('scripts_enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('skills')
    if 'approval_records' not in existing_tables:
        operations.create_table('approval_records',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('stage', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('actor', sa.String(length=80), nullable=False),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('approval_records')
    if 'brand_assets' not in existing_tables:
        operations.create_table('brand_assets',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=240), nullable=False),
        sa.Column('kind', sa.String(length=40), nullable=False),
        sa.Column('artifact_path', sa.Text(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('brand_assets')
    if 'deck_specs' not in existing_tables:
        operations.create_table('deck_specs',
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('narrative', sa.JSON(), nullable=False),
        sa.Column('design_system', sa.JSON(), nullable=False),
        sa.Column('reproducibility', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('project_id')
        )
        existing_tables.add('deck_specs')
    if 'delivery_verifications' not in existing_tables:
        operations.create_table('delivery_verifications',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('file_hash', sa.String(length=64), nullable=False),
        sa.Column('software', sa.String(length=40), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('report', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('delivery_verifications')
    if 'evaluation_runs' not in existing_tables:
        operations.create_table('evaluation_runs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('suite', sa.String(length=80), nullable=False),
        sa.Column('blind_token', sa.String(length=64), nullable=False),
        sa.Column('metrics', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('blind_token')
        )
        existing_tables.add('evaluation_runs')
    if 'exports' not in existing_tables:
        operations.create_table('exports',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('format', sa.String(length=20), nullable=False),
        sa.Column('artifact_path', sa.Text(), nullable=False),
        sa.Column('report', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('exports')
    if 'imported_decks' not in existing_tables:
        operations.create_table('imported_decks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('source_name', sa.String(length=300), nullable=False),
        sa.Column('artifact_path', sa.Text(), nullable=False),
        sa.Column('analysis', sa.JSON(), nullable=False),
        sa.Column('current_version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('imported_decks')
    if 'jobs' not in existing_tables:
        operations.create_table('jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=True),
        sa.Column('kind', sa.String(length=80), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('progress', sa.Float(), nullable=False),
        sa.Column('checkpoint', sa.JSON(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('jobs')
    if 'model_configs' not in existing_tables:
        operations.create_table('model_configs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('provider_id', sa.String(length=36), nullable=False),
        sa.Column('model_id', sa.String(length=240), nullable=False),
        sa.Column('capabilities', sa.JSON(), nullable=False),
        sa.Column('quality_profile', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['provider_id'], ['providers.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider_id', 'model_id')
        )
        existing_tables.add('model_configs')
    if 'model_usage_records' not in existing_tables:
        operations.create_table('model_usage_records',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('model_id', sa.String(length=240), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('request_count', sa.Integer(), nullable=False),
        sa.Column('usage_requests', sa.Integer(), nullable=False),
        sa.Column('unreported_requests', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('model_usage_records')
    if 'personal_comparisons' not in existing_tables:
        operations.create_table('personal_comparisons',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('epoch', sa.Integer(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('reviews', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('personal_comparisons')
    if 'project_members' not in existing_tables:
        operations.create_table('project_members',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('role', sa.String(length=30), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'name')
        )
        existing_tables.add('project_members')
    if 'project_owners' not in existing_tables:
        operations.create_table('project_owners',
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('project_id')
        )
        existing_tables.add('project_owners')
    if 'project_skills' not in existing_tables:
        operations.create_table('project_skills',
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('skill_id', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('project_id', 'skill_id'),
        sa.UniqueConstraint('project_id', 'skill_id')
        )
        existing_tables.add('project_skills')
    if 'published_decks' not in existing_tables:
        operations.create_table('published_decks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('artifact_path', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(length=80), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token')
        )
        existing_tables.add('published_decks')
    if 'slide_specs' not in existing_tables:
        operations.create_table('slide_specs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('spec', sa.JSON(), nullable=False),
        sa.Column('current_version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('slide_specs')
    if 'source_documents' not in existing_tables:
        operations.create_table('source_documents',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=300), nullable=False),
        sa.Column('media_type', sa.String(length=120), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('artifact_path', sa.Text(), nullable=False),
        sa.Column('model', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('source_documents')
    if 'blind_reviews' not in existing_tables:
        operations.create_table('blind_reviews',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('evaluation_run_id', sa.String(length=36), nullable=False),
        sa.Column('reviewer_alias', sa.String(length=80), nullable=False),
        sa.Column('candidate_label', sa.String(length=20), nullable=False),
        sa.Column('scores', sa.JSON(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['evaluation_run_id'], ['evaluation_runs.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('blind_reviews')
    if 'imported_object_edits' not in existing_tables:
        operations.create_table('imported_object_edits',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('imported_deck_id', sa.String(length=36), nullable=False),
        sa.Column('slide_index', sa.Integer(), nullable=False),
        sa.Column('object_id', sa.String(length=80), nullable=False),
        sa.Column('before_text', sa.Text(), nullable=False),
        sa.Column('after_text', sa.Text(), nullable=False),
        sa.Column('actor', sa.String(length=80), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['imported_deck_id'], ['imported_decks.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('imported_object_edits')
    if 'licensed_assets' not in existing_tables:
        operations.create_table('licensed_assets',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('slide_id', sa.String(length=36), nullable=True),
        sa.Column('name', sa.String(length=240), nullable=False),
        sa.Column('kind', sa.String(length=40), nullable=False),
        sa.Column('provider', sa.String(length=120), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=False),
        sa.Column('license', sa.String(length=120), nullable=False),
        sa.Column('attribution', sa.Text(), nullable=False),
        sa.Column('artifact_path', sa.Text(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('approved', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.ForeignKeyConstraint(['slide_id'], ['slide_specs.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('licensed_assets')
    if 'role_assignments' not in existing_tables:
        operations.create_table('role_assignments',
        sa.Column('role', sa.String(length=60), nullable=False),
        sa.Column('model_config_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['model_config_id'], ['model_configs.id'], ),
        sa.PrimaryKeyConstraint('role')
        )
        existing_tables.add('role_assignments')
    if 'slide_candidates' not in existing_tables:
        operations.create_table('slide_candidates',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('slide_id', sa.String(length=36), nullable=False),
        sa.Column('variant', sa.String(length=40), nullable=False),
        sa.Column('artifact_path', sa.Text(), nullable=False),
        sa.Column('score', sa.JSON(), nullable=False),
        sa.Column('selected', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['slide_id'], ['slide_specs.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('slide_candidates')
    if 'slide_edit_messages' not in existing_tables:
        operations.create_table('slide_edit_messages',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('slide_id', sa.String(length=36), nullable=False),
        sa.Column('actor', sa.String(length=80), nullable=False),
        sa.Column('instruction', sa.Text(), nullable=False),
        sa.Column('target', sa.JSON(), nullable=False),
        sa.Column('change_set', sa.JSON(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['slide_id'], ['slide_specs.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('slide_edit_messages')
    if 'slide_versions' not in existing_tables:
        operations.create_table('slide_versions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('slide_id', sa.String(length=36), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('spec', sa.JSON(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['slide_id'], ['slide_specs.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        existing_tables.add('slide_versions')
    existing_indexes = {index["name"] for index in inspector.get_indexes('personal_accounts')}
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('personal_bindings')}
    if 'ix_personal_bindings_owner_id' not in existing_indexes:
        operations.create_index(operations.f('ix_personal_bindings_owner_id'), 'personal_bindings', ['owner_id'], unique=False)
        existing_indexes.add('ix_personal_bindings_owner_id')
    if 'ix_personal_bindings_profile_id' not in existing_indexes:
        operations.create_index(operations.f('ix_personal_bindings_profile_id'), 'personal_bindings', ['profile_id'], unique=False)
        existing_indexes.add('ix_personal_bindings_profile_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('personal_cases')}
    if 'ix_personal_cases_owner_id' not in existing_indexes:
        operations.create_index(operations.f('ix_personal_cases_owner_id'), 'personal_cases', ['owner_id'], unique=False)
        existing_indexes.add('ix_personal_cases_owner_id')
    if 'ix_personal_cases_profile_id' not in existing_indexes:
        operations.create_index(operations.f('ix_personal_cases_profile_id'), 'personal_cases', ['profile_id'], unique=False)
        existing_indexes.add('ix_personal_cases_profile_id')
    if 'ix_personal_cases_project_id' not in existing_indexes:
        operations.create_index(operations.f('ix_personal_cases_project_id'), 'personal_cases', ['project_id'], unique=False)
        existing_indexes.add('ix_personal_cases_project_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('personal_feedback')}
    if 'ix_personal_feedback_owner_id' not in existing_indexes:
        operations.create_index(operations.f('ix_personal_feedback_owner_id'), 'personal_feedback', ['owner_id'], unique=False)
        existing_indexes.add('ix_personal_feedback_owner_id')
    if 'ix_personal_feedback_profile_id' not in existing_indexes:
        operations.create_index(operations.f('ix_personal_feedback_profile_id'), 'personal_feedback', ['profile_id'], unique=False)
        existing_indexes.add('ix_personal_feedback_profile_id')
    if 'ix_personal_feedback_project_id' not in existing_indexes:
        operations.create_index(operations.f('ix_personal_feedback_project_id'), 'personal_feedback', ['project_id'], unique=False)
        existing_indexes.add('ix_personal_feedback_project_id')
    if 'ix_personal_feedback_slide_id' not in existing_indexes:
        operations.create_index(operations.f('ix_personal_feedback_slide_id'), 'personal_feedback', ['slide_id'], unique=False)
        existing_indexes.add('ix_personal_feedback_slide_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('personal_identities')}
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('personal_memories')}
    if 'ix_personal_memories_owner_id' not in existing_indexes:
        operations.create_index(operations.f('ix_personal_memories_owner_id'), 'personal_memories', ['owner_id'], unique=False)
        existing_indexes.add('ix_personal_memories_owner_id')
    if 'ix_personal_memories_profile_id' not in existing_indexes:
        operations.create_index(operations.f('ix_personal_memories_profile_id'), 'personal_memories', ['profile_id'], unique=False)
        existing_indexes.add('ix_personal_memories_profile_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('personal_outbox')}
    if 'ix_personal_outbox_owner_id' not in existing_indexes:
        operations.create_index(operations.f('ix_personal_outbox_owner_id'), 'personal_outbox', ['owner_id'], unique=False)
        existing_indexes.add('ix_personal_outbox_owner_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('personal_profiles')}
    if 'ix_personal_profiles_owner_id' not in existing_indexes:
        operations.create_index(operations.f('ix_personal_profiles_owner_id'), 'personal_profiles', ['owner_id'], unique=False)
        existing_indexes.add('ix_personal_profiles_owner_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('personal_references')}
    if 'ix_personal_references_owner_id' not in existing_indexes:
        operations.create_index(operations.f('ix_personal_references_owner_id'), 'personal_references', ['owner_id'], unique=False)
        existing_indexes.add('ix_personal_references_owner_id')
    if 'ix_personal_references_profile_id' not in existing_indexes:
        operations.create_index(operations.f('ix_personal_references_profile_id'), 'personal_references', ['profile_id'], unique=False)
        existing_indexes.add('ix_personal_references_profile_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('personal_resets')}
    if 'ix_personal_resets_owner_id' not in existing_indexes:
        operations.create_index(operations.f('ix_personal_resets_owner_id'), 'personal_resets', ['owner_id'], unique=False)
        existing_indexes.add('ix_personal_resets_owner_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('personal_sessions')}
    if 'ix_personal_sessions_owner_id' not in existing_indexes:
        operations.create_index(operations.f('ix_personal_sessions_owner_id'), 'personal_sessions', ['owner_id'], unique=False)
        existing_indexes.add('ix_personal_sessions_owner_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('projects')}
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('providers')}
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('skills')}
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('approval_records')}
    if 'ix_approval_records_project_id' not in existing_indexes:
        operations.create_index(operations.f('ix_approval_records_project_id'), 'approval_records', ['project_id'], unique=False)
        existing_indexes.add('ix_approval_records_project_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('brand_assets')}
    if 'ix_brand_assets_project_id' not in existing_indexes:
        operations.create_index(operations.f('ix_brand_assets_project_id'), 'brand_assets', ['project_id'], unique=False)
        existing_indexes.add('ix_brand_assets_project_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('deck_specs')}
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('delivery_verifications')}
    if 'ix_delivery_verifications_file_hash' not in existing_indexes:
        operations.create_index(operations.f('ix_delivery_verifications_file_hash'), 'delivery_verifications', ['file_hash'], unique=False)
        existing_indexes.add('ix_delivery_verifications_file_hash')
    if 'ix_delivery_verifications_project_id' not in existing_indexes:
        operations.create_index(operations.f('ix_delivery_verifications_project_id'), 'delivery_verifications', ['project_id'], unique=False)
        existing_indexes.add('ix_delivery_verifications_project_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('evaluation_runs')}
    if 'ix_evaluation_runs_project_id' not in existing_indexes:
        operations.create_index(operations.f('ix_evaluation_runs_project_id'), 'evaluation_runs', ['project_id'], unique=False)
        existing_indexes.add('ix_evaluation_runs_project_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('exports')}
    if 'ix_exports_project_id' not in existing_indexes:
        operations.create_index(operations.f('ix_exports_project_id'), 'exports', ['project_id'], unique=False)
        existing_indexes.add('ix_exports_project_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('imported_decks')}
    if 'ix_imported_decks_project_id' not in existing_indexes:
        operations.create_index(operations.f('ix_imported_decks_project_id'), 'imported_decks', ['project_id'], unique=True)
        existing_indexes.add('ix_imported_decks_project_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('jobs')}
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('model_configs')}
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('model_usage_records')}
    if 'ix_model_usage_records_project_id' not in existing_indexes:
        operations.create_index(operations.f('ix_model_usage_records_project_id'), 'model_usage_records', ['project_id'], unique=False)
        existing_indexes.add('ix_model_usage_records_project_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('personal_comparisons')}
    if 'ix_personal_comparisons_owner_id' not in existing_indexes:
        operations.create_index(operations.f('ix_personal_comparisons_owner_id'), 'personal_comparisons', ['owner_id'], unique=False)
        existing_indexes.add('ix_personal_comparisons_owner_id')
    if 'ix_personal_comparisons_project_id' not in existing_indexes:
        operations.create_index(operations.f('ix_personal_comparisons_project_id'), 'personal_comparisons', ['project_id'], unique=False)
        existing_indexes.add('ix_personal_comparisons_project_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('project_members')}
    if 'ix_project_members_project_id' not in existing_indexes:
        operations.create_index(operations.f('ix_project_members_project_id'), 'project_members', ['project_id'], unique=False)
        existing_indexes.add('ix_project_members_project_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('project_owners')}
    if 'ix_project_owners_owner_id' not in existing_indexes:
        operations.create_index(operations.f('ix_project_owners_owner_id'), 'project_owners', ['owner_id'], unique=False)
        existing_indexes.add('ix_project_owners_owner_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('project_skills')}
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('published_decks')}
    if 'ix_published_decks_project_id' not in existing_indexes:
        operations.create_index(operations.f('ix_published_decks_project_id'), 'published_decks', ['project_id'], unique=False)
        existing_indexes.add('ix_published_decks_project_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('slide_specs')}
    if 'ix_slide_specs_project_id' not in existing_indexes:
        operations.create_index(operations.f('ix_slide_specs_project_id'), 'slide_specs', ['project_id'], unique=False)
        existing_indexes.add('ix_slide_specs_project_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('source_documents')}
    if 'ix_source_documents_project_id' not in existing_indexes:
        operations.create_index(operations.f('ix_source_documents_project_id'), 'source_documents', ['project_id'], unique=False)
        existing_indexes.add('ix_source_documents_project_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('blind_reviews')}
    if 'ix_blind_reviews_evaluation_run_id' not in existing_indexes:
        operations.create_index(operations.f('ix_blind_reviews_evaluation_run_id'), 'blind_reviews', ['evaluation_run_id'], unique=False)
        existing_indexes.add('ix_blind_reviews_evaluation_run_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('imported_object_edits')}
    if 'ix_imported_object_edits_imported_deck_id' not in existing_indexes:
        operations.create_index(operations.f('ix_imported_object_edits_imported_deck_id'), 'imported_object_edits', ['imported_deck_id'], unique=False)
        existing_indexes.add('ix_imported_object_edits_imported_deck_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('licensed_assets')}
    if 'ix_licensed_assets_project_id' not in existing_indexes:
        operations.create_index(operations.f('ix_licensed_assets_project_id'), 'licensed_assets', ['project_id'], unique=False)
        existing_indexes.add('ix_licensed_assets_project_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('role_assignments')}
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('slide_candidates')}
    if 'ix_slide_candidates_slide_id' not in existing_indexes:
        operations.create_index(operations.f('ix_slide_candidates_slide_id'), 'slide_candidates', ['slide_id'], unique=False)
        existing_indexes.add('ix_slide_candidates_slide_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('slide_edit_messages')}
    if 'ix_slide_edit_messages_slide_id' not in existing_indexes:
        operations.create_index(operations.f('ix_slide_edit_messages_slide_id'), 'slide_edit_messages', ['slide_id'], unique=False)
        existing_indexes.add('ix_slide_edit_messages_slide_id')
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes('slide_versions')}
    if 'ix_slide_versions_slide_id' not in existing_indexes:
        operations.create_index(operations.f('ix_slide_versions_slide_id'), 'slide_versions', ['slide_id'], unique=False)
        existing_indexes.add('ix_slide_versions_slide_id')
    inspector = inspect(bind)
