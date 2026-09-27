import json

import httpx
import pytest
from app.providers.openai_compatible import OpenAICompatibleClient, ProviderError


def mock_transport(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.providers.openai_compatible.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )


async def test_probe_calls_exact_manual_model_id(monkeypatch):
    def handler(request):
        assert request.url.path == "/api/paas/v4/chat/completions"
        assert request.headers["Authorization"] == "Bearer secret"
        payload = json.loads(request.content)
        assert payload["model"] == "glm-4.7-flash"
        assert payload["max_tokens"] == 32
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    mock_transport(monkeypatch, handler)
    latency = await OpenAICompatibleClient(
        "https://open.bigmodel.cn/api/paas/v4", "secret", {}, 15
    ).probe_chat_model("glm-4.7-flash")
    assert latency >= 0


async def test_probe_preserves_upstream_denial_without_exposing_key(monkeypatch):
    mock_transport(
        monkeypatch,
        lambda request: httpx.Response(
            403, json={"error": {"message": "access denied for secret-token-123"}}
        ),
    )
    with pytest.raises(ProviderError, match="HTTP 403") as error:
        await OpenAICompatibleClient(
            "https://open.bigmodel.cn/api/paas/v4", "secret-token-123", {}, 15
        ).probe_chat_model("glm-4.7-flash")
    assert "secret-token-123" not in str(error.value)
