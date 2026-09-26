"""foundation and model gateway"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # This migration must never read today's ORM metadata. The frozen snapshot
    # keeps fresh installs reproducible while later revisions evolve it.
    from app.db.schema_snapshot import create_missing_schema

    create_missing_schema(op, op.get_bind(), allow_legacy_usage_columns=True)


def downgrade():
    # This revision is adopted by existing workspaces that contain user data.
    # Downgrading the foundation would destroy projects and provider settings.
    return None
