"""Create independent local memory tables without rewriting existing project data."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TABLES = (
    "personal_identities",
    "personal_profiles",
    "personal_memories",
    "personal_bindings",
    "personal_feedback",
    "personal_resets",
)


def upgrade():
    from app.db.models import Base

    for name in TABLES:
        Base.metadata.tables[name].create(op.get_bind(), checkfirst=True)


def downgrade():
    # Personal preferences can contain user-authored data; keep them on rollback.
    return None
