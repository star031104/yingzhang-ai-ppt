from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SlideSpecRecord


def load_slides(project_id: str, db: Session) -> list[dict]:
    rows = db.scalars(
        select(SlideSpecRecord)
        .where(SlideSpecRecord.project_id == project_id)
        .order_by(SlideSpecRecord.position)
    ).all()
    return [row.spec for row in rows]
