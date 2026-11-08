import json

import pytest
from app.providers.openai_compatible import ProviderError
from app.providers.structured import (
    StructuredOutputLedger,
    strict_compatible,
    structured_completion,
    validate_schema,
)

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "items": {"type": "array", "items": {"type": "integer"}, "maxItems": 3},
    },
    "required": ["title", "items"],
}


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def chat_completion(self, model, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def ledger(tmp_path):
    return StructuredOutputLedger(tmp_path / "stats.json")


def test_validate_schema_reports_precise_paths():
    errors = validate_schema({"title": 3, "items": [1, "x", 3, 4]}, SCHEMA)
    assert "$.title 应为 string，实际为 int" in errors
    assert any("$.items[1]" in error for error in errors)
    assert any("最多 3 项" in error for error in errors)
    assert validate_schema({"title": "ok", "items": [1]}, SCHEMA) == []
    assert validate_schema({"title": "x"}, SCHEMA) == ["$ 缺少字段 items"]
    # Booleans are not integers even though Python says so.
    assert validate_schema({"title": "x", "items": [True]}, SCHEMA)


def test_strict_compatible_closes_objects_and_drops_unsupported_bounds():
    strict = strict_compatible(SCHEMA)
    assert strict["additionalProperties"] is False
    assert strict["required"] == ["title", "items"]
    assert "maxItems" not in strict["properties"]["items"]


async def test_strict_schema_first_try(ledger):
    client = FakeClient([json.dumps({"title": "A", "items": [1]})])
    result = await structured_completion(client, "m", [{"role": "user", "content": "x"}], SCHEMA, ledger=ledger)
    assert result.path == "strict" and result.value["title"] == "A"
    assert client.calls[0]["json_schema"]["additionalProperties"] is False
    assert ledger.summary()[0]["firstTryRate"] == 1.0


async def test_invalid_output_gets_one_schema_aware_repair(ledger):
    client = FakeClient(['{"title": 1, "items": []}', json.dumps({"title": "fixed", "items": []})])
    result = await structured_completion(client, "m", [{"role": "user", "content": "x"}], SCHEMA, ledger=ledger)
    assert result.path == "repaired" and result.value["title"] == "fixed"
    repair_turn = client.calls[1]["messages"][-1]["content"]
    assert "$.title 应为 string" in repair_turn and "目标 JSON Schema" in repair_turn
    assert client.calls[1]["messages"][-2]["role"] == "assistant"


async def test_regex_fallback_after_failed_repair(ledger):
    client = FakeClient(['```json\n{"title":"wrapped","items":[2]}\n```', "still not json"])
    result = await structured_completion(client, "m", [{"role": "user", "content": "x"}], SCHEMA, ledger=ledger)
    assert result.path == "regex-fallback" and result.value["items"] == [2]
    assert ledger.summary()[0]["paths"]["regex-fallback"] == 1


async def test_unparseable_output_raises_and_counts_failure(ledger):
    client = FakeClient(['{"title":', '{"title":'])
    with pytest.raises(ValueError):
        await structured_completion(client, "m", [{"role": "user", "content": "x"}], SCHEMA, ledger=ledger)
    assert ledger.summary()[0]["failureRate"] == 1.0


async def test_schema_rejection_is_remembered_per_model(ledger, tmp_path):
    client = FakeClient([
        ProviderError("Client error '400 Bad Request': response_format json_schema unsupported"),
        json.dumps({"title": "A", "items": []}),
        json.dumps({"title": "B", "items": []}),
    ])
    first = await structured_completion(client, "local", [{"role": "user", "content": "x"}], SCHEMA, ledger=ledger)
    assert first.path == "json-mode"
    second = await structured_completion(client, "local", [{"role": "user", "content": "y"}], SCHEMA, ledger=ledger)
    assert second.path == "json-mode"
    assert client.calls[2].get("json_schema") is None and client.calls[2]["json_mode"] is True
    reloaded = StructuredOutputLedger(tmp_path / "stats.json")
    assert reloaded.summary()[0]["schemaUnsupported"] is True


async def test_network_errors_are_not_mistaken_for_schema_rejection(ledger):
    client = FakeClient([ProviderError("connection reset")])
    with pytest.raises(ProviderError):
        await structured_completion(client, "m", [{"role": "user", "content": "x"}], SCHEMA, ledger=ledger)
    assert ledger.schema_supported("m")


def test_structured_output_diagnostics_endpoint(client):
    response = client.get("/api/v1/model-diagnostics/structured-output")
    assert response.status_code == 200 and "models" in response.json()
    assert client.delete("/api/v1/model-diagnostics/structured-output").status_code == 204
