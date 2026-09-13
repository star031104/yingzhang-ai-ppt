def test_api_key_not_returned(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.secret_store.set", lambda ref, value: None)
    response = client.post(
        "/api/v1/providers",
        json={
            "name": "local-test",
            "base_url": "http://127.0.0.1:8000/v1",
            "api_key": "super-secret",
        },
    )
    assert response.status_code == 201
    assert "super-secret" not in response.text
    assert response.json()["has_api_key"] is True


def test_vision_role_requires_vision(client):
    provider = client.post(
        "/api/v1/providers", json={"name": "cap-test", "base_url": "http://localhost:8000/v1"}
    ).json()
    model = client.post(
        f"/api/v1/providers/{provider['id']}/models",
        json={"model_id": "text-only", "capabilities": ["chat"]},
    ).json()
    response = client.put(
        "/api/v1/model-routing", json={"role": "vision_critic", "model_config_id": model["id"]}
    )
    assert response.status_code == 422


def test_discovers_models_before_saving_provider(client, monkeypatch):
    requested = []

    async def fake_models(_self, model_type=None):
        requested.append(model_type)
        return ["model-a", "model-b"], 23

    monkeypatch.setattr("app.api.routes.OpenAICompatibleClient.list_models", fake_models)
    response = client.post(
        "/api/v1/providers/discover",
        json={"base_url": "http://127.0.0.1:9000/v1", "api_key": "secret", "model_type": "image"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "latency_ms": 23,
        "models": ["model-a", "model-b"],
        "error": None,
    }
    assert requested == ["image"]


def test_deleting_provider_removes_models_and_role_assignments(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.secret_store.set", lambda ref, value: None)
    deleted = []
    monkeypatch.setattr("app.api.routes.secret_store.delete", lambda ref: deleted.append(ref))
    provider = client.post(
        "/api/v1/providers",
        json={"name": "image-service", "base_url": "https://api.example.com/v1", "api_key": "secret"},
    ).json()
    model = client.post(
        f"/api/v1/providers/{provider['id']}/models",
        json={"model_id": "image-model", "capabilities": ["image_generation"]},
    ).json()
    assert client.put(
        "/api/v1/model-routing",
        json={"role": "image_generation", "model_config_id": model["id"]},
    ).status_code == 200
    assert client.delete(f"/api/v1/providers/{provider['id']}").status_code == 204
    assert client.get("/api/v1/models").json() == []
    assert client.get("/api/v1/model-routing").json() == []
    assert deleted == [f"provider:{provider['id']}"]
