"""Per-slide narration scripts derived from speaker notes, with a deterministic fallback."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Locale = Literal["zh-CN", "en-US"]
NarrationSource = Literal["speaker-notes", "talking-points", "generated"]

# Typical professional delivery speed.
CJK_CHARS_PER_SECOND = 4.2
LATIN_WORDS_PER_SECOND = 2.5
MIN_SLIDE_SECONDS = 3.0
MAX_NARRATION_CHARS = 1200
_CJK = re.compile(r"[㐀-鿿豈-﫿]")
_LATIN_WORD = re.compile(r"[A-Za-z0-9]+(?:['’.-][A-Za-z0-9]+)*")


@dataclass(frozen=True)
class SlideNarration:
    slide_id: str
    position: int
    title: str
    text: str
    source: NarrationSource
    estimated_seconds: float


def _clean(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text.strip("。；; ")


def estimate_speech_seconds(text: str) -> float:
    """Spoken duration estimated from text length (used for silent narration)."""
    cjk = len(_CJK.findall(text))
    words = len(_LATIN_WORD.findall(_CJK.sub(" ", text)))
    seconds = cjk / CJK_CHARS_PER_SECOND + words / LATIN_WORDS_PER_SECOND
    return round(max(MIN_SLIDE_SECONDS, seconds + 0.6), 2)


def fallback_narration(spec: dict, locale: Locale = "zh-CN") -> str:
    """Build a deterministic narration from the slide title, message and bullets."""
    content = spec.get("content") or {}
    title = _clean(content.get("title") or spec.get("title"))
    message = _clean(spec.get("message"))
    bullets = [_clean(item) for item in (content.get("bullets") or [])[:4] if _clean(item)]
    if locale == "en-US":
        parts = [f"This slide covers {title}." if title else ""]
        if message:
            parts.append(f"{message}.")
        if bullets:
            parts.append("Key points: " + "; ".join(bullets) + ".")
        return " ".join(part for part in parts if part).strip()
    parts = [f"这一页介绍{title}。" if title else ""]
    if message and message != title:
        parts.append(f"{message}。")
    if bullets:
        parts.append("重点包括：" + "；".join(bullets) + "。")
    return "".join(parts).strip()


def slide_narration(spec: dict, locale: Locale = "zh-CN") -> SlideNarration:
    intent = spec.get("speakerIntent") or {}
    notes = _clean(intent.get("narration") or spec.get("speakerNotes"))
    points = [_clean(item) for item in intent.get("talkingPoints") or [] if _clean(item)]
    if notes:
        text, source = notes, "speaker-notes"
    elif points:
        separator = "; " if locale == "en-US" else "；"
        text, source = separator.join(points[:5]), "talking-points"
    else:
        text, source = fallback_narration(spec, locale), "generated"
    if text and text[-1] not in "。.!！?？":
        text += "." if locale == "en-US" else "。"
    text = text[:MAX_NARRATION_CHARS]
    title = _clean((spec.get("content") or {}).get("title") or spec.get("title"))
    return SlideNarration(
        slide_id=str(spec.get("id") or ""),
        position=int(spec.get("position") or 0),
        title=title,
        text=text,
        source=source,
        estimated_seconds=estimate_speech_seconds(text),
    )


def deck_narration(slides: list[dict], locale: Locale = "zh-CN") -> list[SlideNarration]:
    return [slide_narration(slide, locale) for slide in sorted(slides, key=lambda s: s.get("position", 0))]
