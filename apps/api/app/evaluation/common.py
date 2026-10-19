"""Shared helpers for research-standard deck evaluation (PPTEval, quiz, render review)."""

import json
import math
import re
from collections.abc import Awaitable, Iterable
from typing import Protocol

NAVIGATION_ROLES = {"cover", "agenda", "section", "questions"}
_SKIP_CONTENT_KEYS = {
    "id", "ids", "path", "src", "url", "href", "assetId", "imagePath", "sourceRef", "sourceRefs",
    "color", "colors", "style", "variant", "icon", "kind", "type", "format",
}


class Judge(Protocol):
    """Minimal model surface used by evaluators; tests pass an in-memory fake."""

    model_id: str
    vision: bool

    def complete(self, prompt: str, max_tokens: int = 2400) -> Awaitable[str]: ...

    def see(self, prompt: str, images: list[bytes], max_tokens: int = 2400) -> Awaitable[str]: ...


def _strings(value, depth: int = 0) -> Iterable[str]:
    if depth > 5:
        return
    if isinstance(value, str):
        if value.strip():
            yield value.strip()
    elif isinstance(value, bool):
        return
    elif isinstance(value, (int, float)):
        yield str(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in _SKIP_CONTENT_KEYS:
                continue
            yield from _strings(item, depth + 1)
    elif isinstance(value, list):
        for item in value[:60]:
            yield from _strings(item, depth + 1)


def slide_segments(slide: dict) -> list[str]:
    """Audience-visible text of one slide: title, message, bullets and structured content.

    Speaker notes and planning metadata are excluded so that evaluators only see what the
    audience sees on the page.
    """
    content = slide.get("content") or {}
    segments: list[str] = []
    title = str(content.get("title", "")).strip()
    if title:
        segments.append(title)
    message = str(slide.get("message", "")).strip()
    if message:
        segments.append(message)
    for bullet in content.get("bullets", []) or []:
        if str(bullet).strip():
            segments.append(str(bullet).strip())
    for key, value in content.items():
        if key in {"title", "bullets"} or key in _SKIP_CONTENT_KEYS:
            continue
        segments.extend(_strings(value))
    seen: set[str] = set()
    unique = []
    for segment in segments:
        if segment not in seen:
            seen.add(segment)
            unique.append(segment[:600])
    return unique


def slide_text(slide: dict) -> str:
    return "\n".join(slide_segments(slide))


def clamp_score(value, default: int | None = None) -> int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number):
        return default
    return int(max(1, min(5, round(number))))


def from_percent(value: float | None) -> int:
    """Map a 0–100 internal metric onto the PPTEval 1–5 scale."""
    if value is None:
        return 3
    value = max(0.0, min(100.0, float(value)))
    return int(max(1, min(5, round(1 + value / 25))))


def short(text, limit: int = 140) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _balance(text: str) -> str:
    """Close brackets and strings left open by a truncated model reply."""
    stack: list[str] = []
    in_string = escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append("}" if char == "{" else "]")
        elif char in "}]" and stack and stack[-1] == char:
            stack.pop()
    suffix = '"' if in_string else ""
    trimmed = (text + suffix).rstrip()
    trimmed = re.sub(r",\s*$", "", trimmed)
    trimmed = re.sub(r":\s*$", ": null", trimmed)
    return trimmed + "".join(reversed(stack))


def parse_json_object(content: str) -> dict:
    """Strictly parse a model reply as one JSON object, repairing common formatting damage.

    Handles reasoning tags, Markdown fences, prose around the object, trailing commas,
    full-width quotes used as delimiters and truncated output. Raises ``ValueError`` when no
    object can be recovered; callers then fall back to deterministic evaluation.
    """
    if not isinstance(content, str):
        raise TypeError("模型未返回文本")
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", content, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
    start = cleaned.find("{")
    if start < 0:
        raise ValueError("模型未返回 JSON 对象")
    end = cleaned.rfind("}")
    candidates = []
    if end > start:
        candidates.append(cleaned[start : end + 1])
    candidates.append(cleaned[start:])
    for candidate in candidates:
        attempts = [
            candidate,
            re.sub(r",\s*([}\]])", r"\1", candidate),
        ]
        normalized = re.sub(r"[“”]", '"', attempts[-1])
        attempts.append(normalized)
        attempts.append(_balance(re.sub(r",\s*([}\]])", r"\1", normalized)))
        for attempt in attempts:
            try:
                value = json.loads(attempt, strict=False)
            except ValueError:
                continue
            if isinstance(value, dict):
                return value
    raise ValueError("模型返回的 JSON 无法解析")


def tokens(text: str) -> set[str]:
    """Language-neutral lexical units: lower-case words plus CJK character bigrams."""
    lowered = (text or "").lower()
    words = {word for word in re.findall(r"[a-z][a-z0-9\-]{1,}", lowered) if len(word) > 2}
    words -= {"the", "and", "for", "with", "this", "that", "from", "are", "was", "were", "has"}
    cjk_runs = re.findall(r"[一-鿿]+", lowered)
    bigrams = {run[index : index + 2] for run in cjk_runs for index in range(len(run) - 1)}
    bigrams -= {"以及", "可以", "进行", "通过", "一个", "我们", "这个", "其中"}
    return words | bigrams
