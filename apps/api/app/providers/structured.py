"""Structured JSON output for OpenAI-compatible chat models.

The order of preference is deliberate:

1. ``response_format=json_schema`` with ``strict: true`` when the provider accepts it;
2. one repair turn that shows the model its own output and the exact validation
   errors (schema-aware, not a blind retry);
3. the legacy tolerant extractor (``parse_model_json``) as the last resort.

Every call records which path produced the result so per-model failure rates are
visible in the model configuration page instead of being hidden by fallbacks.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import settings
from app.providers.openai_compatible import OpenAICompatibleClient, ProviderError

STRUCTURED_PATHS = ("strict", "json-mode", "repaired", "regex-fallback", "failed")


def parse_model_json(content: str) -> dict:
    """Tolerant extractor kept for models that ignore response_format."""
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", content, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型未返回 JSON 对象")
    return json.loads(cleaned[start : end + 1])


def strict_json(content: str) -> Any:
    """Parse exactly one JSON document; reasoning tags are the only tolerated wrapper."""
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", content, flags=re.IGNORECASE).strip()
    return json.loads(cleaned)


_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


def validate_schema(value: Any, schema: dict, path: str = "$", limit: int = 12) -> list[str]:
    """Validate the JSON-schema subset used by YingZhang prompts.

    Supported keywords: type (string or list), properties, required,
    additionalProperties (bool), items, enum, minItems, maxItems, minimum, maximum,
    maxLength. Unknown keywords are ignored rather than rejected.
    """
    errors: list[str] = []

    def visit(node: Any, rule: dict, where: str) -> None:
        if len(errors) >= limit:
            return
        expected = rule.get("type")
        if expected:
            names = expected if isinstance(expected, list) else [expected]
            matched = False
            for name in names:
                python_type = _TYPES.get(name)
                if python_type is None:
                    matched = True
                    break
                if isinstance(node, bool) and name in {"integer", "number"}:
                    continue
                if isinstance(node, python_type):
                    matched = True
                    break
            if not matched:
                errors.append(f"{where} 应为 {'/'.join(names)}，实际为 {type(node).__name__}")
                return
        if "enum" in rule and node not in rule["enum"]:
            errors.append(f"{where} 取值 {json.dumps(node, ensure_ascii=False)[:40]} 不在允许范围 {rule['enum']}")
        if isinstance(node, str) and isinstance(rule.get("maxLength"), int) and len(node) > rule["maxLength"]:
            errors.append(f"{where} 超过 {rule['maxLength']} 字符")
        if isinstance(node, (int, float)) and not isinstance(node, bool):
            if isinstance(rule.get("minimum"), (int, float)) and node < rule["minimum"]:
                errors.append(f"{where} 小于最小值 {rule['minimum']}")
            if isinstance(rule.get("maximum"), (int, float)) and node > rule["maximum"]:
                errors.append(f"{where} 大于最大值 {rule['maximum']}")
        if isinstance(node, dict):
            properties = rule.get("properties") or {}
            for key in rule.get("required") or []:
                if key not in node:
                    errors.append(f"{where} 缺少字段 {key}")
            if rule.get("additionalProperties") is False:
                for key in node:
                    if key not in properties:
                        errors.append(f"{where} 出现未定义字段 {key}")
            for key, child in properties.items():
                if key in node and isinstance(child, dict):
                    visit(node[key], child, f"{where}.{key}")
        if isinstance(node, list):
            if isinstance(rule.get("minItems"), int) and len(node) < rule["minItems"]:
                errors.append(f"{where} 至少需要 {rule['minItems']} 项")
            if isinstance(rule.get("maxItems"), int) and len(node) > rule["maxItems"]:
                errors.append(f"{where} 最多 {rule['maxItems']} 项")
            child = rule.get("items")
            if isinstance(child, dict):
                for index, item in enumerate(node):
                    visit(item, child, f"{where}[{index}]")

    visit(value, schema, path)
    return errors[:limit]


def strict_compatible(schema: dict) -> dict:
    """Return a copy that satisfies OpenAI strict mode: every object closed and fully required."""
    if not isinstance(schema, dict):
        return schema
    result = {key: value for key, value in schema.items() if key not in {"minItems", "maxItems", "maxLength", "minimum", "maximum"}}
    if result.get("type") == "object" or "properties" in result:
        properties = {key: strict_compatible(value) for key, value in (result.get("properties") or {}).items()}
        result["properties"] = properties
        result["required"] = list(properties)
        result["additionalProperties"] = False
    if isinstance(result.get("items"), dict):
        result["items"] = strict_compatible(result["items"])
    return result


# ---------------------------------------------------------------------------
# Per-model ledger


class StructuredOutputLedger:
    """Counts which structured-output path each model needed, persisted as small JSON."""

    def __init__(self, path: Path | None = None):
        self._path = path
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] | None = None
        self._loaded_path: Path | None = None
        self._schema_unsupported: set[str] = set()

    @property
    def path(self) -> Path:
        return self._path or Path(settings.artifact_root) / ".observability" / "structured-output.json"

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._data is not None and self._loaded_path != self.path:
            self._data = None
            self._schema_unsupported = set()
        if self._data is None:
            self._loaded_path = self.path
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._data = {}
            for model, entry in self._data.items():
                if entry.get("schemaUnsupported"):
                    self._schema_unsupported.add(model)
        return self._data

    def schema_supported(self, model: str) -> bool:
        with self._lock:
            self._load()
            return model not in self._schema_unsupported

    def mark_schema_unsupported(self, model: str) -> None:
        with self._lock:
            data = self._load()
            self._schema_unsupported.add(model)
            data.setdefault(model, {})["schemaUnsupported"] = True
            self._flush()

    def record(self, model: str, purpose: str, path: str, errors: list[str] | None = None) -> None:
        with self._lock:
            data = self._load()
            entry = data.setdefault(model, {})
            counts = entry.setdefault("paths", {})
            counts[path] = int(counts.get(path, 0)) + 1
            by_purpose = entry.setdefault("purposes", {}).setdefault(purpose, {})
            by_purpose[path] = int(by_purpose.get(path, 0)) + 1
            entry["calls"] = int(entry.get("calls", 0)) + 1
            entry["updatedAt"] = int(time.time())
            if errors:
                entry["lastErrors"] = [str(item)[:160] for item in errors[:4]]
            self._flush()

    def _flush(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            # Observability never fails a generation.
            return

    def summary(self) -> list[dict[str, Any]]:
        with self._lock:
            data = self._load()
            rows = []
            for model, entry in sorted(data.items()):
                counts = entry.get("paths", {})
                calls = max(1, int(entry.get("calls", 0)))
                first_try = int(counts.get("strict", 0)) + int(counts.get("json-mode", 0))
                rows.append({
                    "model": model,
                    "calls": int(entry.get("calls", 0)),
                    "paths": {name: int(counts.get(name, 0)) for name in STRUCTURED_PATHS},
                    "firstTryRate": round(first_try / calls, 3),
                    "failureRate": round(int(counts.get("failed", 0)) / calls, 3),
                    "schemaUnsupported": bool(entry.get("schemaUnsupported")),
                    "purposes": entry.get("purposes", {}),
                    "lastErrors": entry.get("lastErrors", []),
                })
            return rows

    def reset(self) -> None:
        with self._lock:
            self._data = {}
            self._schema_unsupported.clear()
            self._flush()


structured_ledger = StructuredOutputLedger()


@dataclass
class StructuredResult:
    value: dict
    path: str
    errors: list[str] = field(default_factory=list)
    raw: str = ""

    def report(self) -> dict:
        return {"path": self.path, "errors": self.errors[:6]}


def _schema_rejected(exc: ProviderError) -> bool:
    message = str(exc).lower()
    return any(token in message for token in ("400", "422", "response_format", "json_schema", "not supported", "unsupported"))


def repair_prompt(raw: str, errors: list[str], schema: dict) -> str:
    excerpt = raw.strip()
    if len(excerpt) > 6000:
        excerpt = excerpt[:3000] + "\n…（中间省略）…\n" + excerpt[-2400:]
    return (
        "上一次输出未通过结构校验，请只修正结构问题后重新输出完整 JSON。\n"
        "不得新增材料之外的事实或数字，不要解释，不要输出 Markdown。\n"
        "校验错误：\n- " + "\n- ".join(errors[:10])
        + "\n目标 JSON Schema：" + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))[:3000]
        + "\n上一次输出：\n" + excerpt
    )


async def structured_completion(
    client: OpenAICompatibleClient,
    model: str,
    messages: list[dict],
    schema: dict,
    *,
    purpose: str = "general",
    temperature: float = 0.2,
    max_tokens: int = 4000,
    thinking_budget: int | None = None,
    repair_attempts: int = 1,
    ledger: StructuredOutputLedger | None = None,
) -> StructuredResult:
    """Return a JSON object that validates against ``schema`` whenever possible.

    Raises ``ValueError`` only when no path produced a JSON object; a result that
    still has schema errors after repair is returned with ``path='regex-fallback'``
    and its errors so callers keep their own rule-based validation.
    """
    ledger = ledger or structured_ledger
    use_schema = ledger.schema_supported(model)
    first_path = "strict" if use_schema else "json-mode"
    raw = ""
    try:
        raw = await client.chat_completion(
            model, messages, temperature=temperature, max_tokens=max_tokens,
            json_mode=not use_schema, thinking_budget=thinking_budget,
            json_schema=strict_compatible(schema) if use_schema else None,
        )
    except ProviderError as exc:
        if not use_schema or not _schema_rejected(exc):
            ledger.record(model, purpose, "failed", [str(exc)])
            raise
        ledger.mark_schema_unsupported(model)
        first_path = "json-mode"
        raw = await client.chat_completion(
            model, messages, temperature=temperature, max_tokens=max_tokens,
            json_mode=True, thinking_budget=thinking_budget,
        )
    errors: list[str]
    try:
        value = strict_json(raw)
        errors = validate_schema(value, schema) if isinstance(value, dict) else ["$ 应为 JSON 对象"]
    except ValueError as exc:
        value, errors = None, [f"JSON 解析失败：{str(exc)[:120]}"]
    if isinstance(value, dict) and not errors:
        ledger.record(model, purpose, first_path)
        return StructuredResult(value, first_path, [], raw)

    last_raw, last_errors = raw, errors
    for _ in range(max(0, repair_attempts)):
        try:
            repaired_raw = await client.chat_completion(
                model,
                [*messages, {"role": "assistant", "content": last_raw[:8000]},
                 {"role": "user", "content": repair_prompt(last_raw, last_errors, schema)}],
                temperature=min(temperature, 0.1), max_tokens=max_tokens, json_mode=True,
                thinking_budget=thinking_budget,
            )
        except ProviderError as exc:
            last_errors = [*last_errors, f"修复请求失败：{str(exc)[:120]}"]
            break
        try:
            repaired = strict_json(repaired_raw)
            repaired_errors = validate_schema(repaired, schema) if isinstance(repaired, dict) else ["$ 应为 JSON 对象"]
        except ValueError as exc:
            repaired, repaired_errors = None, [f"JSON 解析失败：{str(exc)[:120]}"]
        if isinstance(repaired, dict) and not repaired_errors:
            ledger.record(model, purpose, "repaired", last_errors)
            return StructuredResult(repaired, "repaired", last_errors, repaired_raw)
        last_raw, last_errors = repaired_raw, repaired_errors

    for candidate in (last_raw, raw):
        try:
            fallback = parse_model_json(candidate)
        except ValueError:
            continue
        if isinstance(fallback, dict):
            remaining = validate_schema(fallback, schema)
            ledger.record(model, purpose, "regex-fallback", remaining or last_errors)
            return StructuredResult(fallback, "regex-fallback", remaining, candidate)
    ledger.record(model, purpose, "failed", last_errors)
    raise ValueError("模型输出无法解析为 JSON：" + "；".join(last_errors[:3]))
