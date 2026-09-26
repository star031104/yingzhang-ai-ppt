"""Freeze the schema contract and repair missing tables/indexes safely."""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    from app.db.schema_snapshot import create_missing_schema

    create_missing_schema(op, op.get_bind())


def downgrade():
    # The contract may have created tables used by an older application.
    # Keep user data and require forward-only schema evolution.
    return None
