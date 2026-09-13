import os

os.environ["SLIDEFORGE_DATABASE_URL"] = "sqlite:///./runtime/data/test.db"
os.environ["SLIDEFORGE_ARTIFACT_ROOT"] = "./runtime/artifacts-test"
os.environ["SLIDEFORGE_PUBLIC_TEST_MODE"] = "false"
import pytest
from app.db.models import Base
from app.db.session import engine
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(engine)
