"""Bind project roles to private accounts and approvals to deck snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    member_columns = {column["name"] for column in inspector.get_columns("project_members")}
    if "account_id" not in member_columns:
        with op.batch_alter_table("project_members") as batch:
            batch.add_column(sa.Column("account_id", sa.String(length=36), nullable=True))
            batch.create_foreign_key(
                "fk_project_members_account_id",
                "personal_accounts",
                ["account_id"],
                ["id"],
            )
            batch.create_index("ix_project_members_account_id", ["account_id"])

    approval_columns = {column["name"] for column in inspector.get_columns("approval_records")}
    if "snapshot_hash" not in approval_columns:
        op.add_column(
            "approval_records",
            sa.Column("snapshot_hash", sa.String(length=64), nullable=True),
        )


def downgrade():
    # Preserve identity bindings and publication audit history on rollback.
    return None
