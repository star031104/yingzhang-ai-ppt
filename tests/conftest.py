import os

# YINGZHANG_* wins over SLIDEFORGE_*; set both so a developer shell can never
# point the destructive test fixtures at a real workspace.
for _prefix in ("YINGZHANG_", "SLIDEFORGE_"):
    os.environ[f"{_prefix}DATABASE_URL"] = "sqlite:///./runtime/data/test.db"
    os.environ[f"{_prefix}ARTIFACT_ROOT"] = "./runtime/artifacts-test"
    os.environ[f"{_prefix}PUBLIC_TEST_MODE"] = "false"
import pytest
from app.db.models import Base
from app.db.session import engine
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import text


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
