from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def test_public_tester_and_admin_permissions(monkeypatch):
    monkeypatch.setattr(settings, "public_test_mode", True)
    monkeypatch.setattr(settings, "public_test_password", "tester-password-2026")
    monkeypatch.setattr(settings, "public_admin_password", "admin-password-2026")
    monkeypatch.setattr(settings, "public_session_secret", "s" * 48)

    with TestClient(app) as tester:
        session = tester.get("/api/v1/auth/session")
        assert session.status_code == 200
        assert session.json()["authenticated"] is False
        assert tester.get("/api/v1/projects").status_code == 401

        login = tester.post(
            "/api/v1/auth/login",
            json={"name": "测试同学", "password": "tester-password-2026"},
        )
        assert login.status_code == 200
        assert login.json()["role"] == "tester"
        assert tester.get("/api/v1/projects").status_code == 200
        assert tester.get("/api/v1/providers").status_code == 403
        assert tester.delete("/api/v1/projects/not-allowed").status_code == 403
        assert tester.post("/api/v1/skills/install-url", json={}).status_code == 403

    with TestClient(app) as admin:
        login = admin.post(
            "/api/v1/auth/login",
            json={"name": "项目管理员", "password": "admin-password-2026"},
        )
        assert login.status_code == 200
        assert login.json()["role"] == "admin"
        assert admin.get("/api/v1/providers").status_code == 200


def test_public_rejects_cross_origin_changes(monkeypatch):
    monkeypatch.setattr(settings, "public_test_mode", True)
    monkeypatch.setattr(settings, "public_test_password", "tester-password-2026")
    monkeypatch.setattr(settings, "public_admin_password", "admin-password-2026")
    monkeypatch.setattr(settings, "public_session_secret", "s" * 48)

    with TestClient(app, base_url="https://share.example") as tester:
        tester.post(
            "/api/v1/auth/login",
            json={"name": "测试同学", "password": "tester-password-2026"},
        )
        response = tester.post(
            "/api/v1/projects",
            json={"name": "不应创建"},
            headers={"Origin": "https://evil.example"},
        )
        assert response.status_code == 403
def test_local_workspace_needs_no_cookie_or_login(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "public_test_mode", False)
    monkeypatch.setattr(settings, "private_accounts_mode", False)
    client.cookies.clear()
    session = client.get("/api/v1/auth/session").json()
    assert session["authenticated"] and session["role"] == "admin"
    assert not session["publicMode"] and not session["privateMode"]
    assert not session["setupRequired"]
    assert client.get("/api/v1/projects").status_code == 200
