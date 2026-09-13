"""Private accounts, reference provenance, examples and delivery evaluations."""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TABLES = ("personal_accounts", "personal_sessions", "project_owners", "personal_cases",
          "personal_references", "personal_outbox", "personal_comparisons", "delivery_verifications")


def upgrade():
    from app.db.models import Base
    for name in TABLES:
        Base.metadata.tables[name].create(op.get_bind(), checkfirst=True)


def downgrade():
    from app.db.models import Base
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(op.get_bind(), checkfirst=True)
