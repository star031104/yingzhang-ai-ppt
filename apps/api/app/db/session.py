from pathlib import Path

from app.config import settings
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

if settings.database_url.startswith("sqlite:///") and ":memory:" not in settings.database_url:
    Path(settings.database_url.removeprefix("sqlite:///")).resolve().parent.mkdir(
        parents=True, exist_ok=True
    )
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def enable_secure_delete(connection, _record):
        # Ordinary memory rows must not remain in SQLite free pages after DELETE.
        connection.execute("PRAGMA secure_delete=ON")


def get_db():
    with SessionLocal() as session:
        yield session


def create_schema():
    from app.db.models import Base

    Base.metadata.create_all(engine)
