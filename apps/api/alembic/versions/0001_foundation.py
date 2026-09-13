"""foundation and model gateway"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    from app.db.models import Base

    Base.metadata.create_all(op.get_bind())


def downgrade():
    for table in ("role_assignments", "model_configs", "providers", "jobs", "projects"):
        op.drop_table(table)
