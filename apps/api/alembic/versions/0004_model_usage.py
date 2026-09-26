"""Record provider-reported token usage per project without storing prompts."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("model_usage_records"):
        op.create_table(
            "model_usage_records",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("model_id", sa.String(length=240), nullable=False),
            sa.Column("input_tokens", sa.Integer(), nullable=True),
            sa.Column("output_tokens", sa.Integer(), nullable=True),
            sa.Column("request_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("usage_requests", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("unreported_requests", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    else:
        # create_all() cannot evolve an existing table. This migration also
        # upgrades installations that created the initial usage table before
        # request reporting was added.
        columns = {column["name"] for column in sa.inspect(bind).get_columns("model_usage_records")}
        if "usage_requests" not in columns:
            op.add_column(
                "model_usage_records",
                sa.Column("usage_requests", sa.Integer(), nullable=False, server_default=sa.text("0")),
            )
        if "unreported_requests" not in columns:
            op.add_column(
                "model_usage_records",
                sa.Column("unreported_requests", sa.Integer(), nullable=False, server_default=sa.text("0")),
            )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("model_usage_records")}
    if "ix_model_usage_records_project_id" not in indexes:
        op.create_index("ix_model_usage_records_project_id", "model_usage_records", ["project_id"])


def downgrade():
    # Usage data is append-only operational history. Keep the table when the
    # application is rolled back so a deploy rollback cannot erase telemetry.
    # Older application versions safely ignore this additive table and columns.
    return None
