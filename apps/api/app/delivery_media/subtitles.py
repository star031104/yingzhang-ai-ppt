"""SRT subtitle cues aligned to per-slide narration segments."""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_CJK_CUE_CHARS = 24
MAX_LATIN_CUE_CHARS = 64
_SENTENCE = re.compile(r"[^。！？；!?;]+?(?:[。！？；!?;]|\.(?=\s|$)|$)")


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def _is_cjk_heavy(text: str) -> bool:
    return len(re.findall(r"[㐀-鿿]", text)) * 2 >= len(text.replace(" ", ""))


def split_cue_text(text: str) -> list[str]:
    """Split narration into readable subtitle lines at sentence boundaries."""
    limit = MAX_CJK_CUE_CHARS if _is_cjk_heavy(text) else MAX_LATIN_CUE_CHARS
    chunks: list[str] = []
    for sentence in (part.strip() for part in _SENTENCE.findall(text)):
        if not sentence:
            continue
        while len(sentence) > limit:
            cut = max(sentence.rfind(mark, 0, limit) for mark in ("，", ",", "、", " "))
            cut = cut + 1 if cut >= limit // 3 else limit
            chunks.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            chunks.append(sentence)
    return chunks


def segment_cues(text: str, start: float, duration: float) -> list[Cue]:
    """Distribute cues across a slide segment in proportion to their length."""
    chunks = split_cue_text(text)
    if not chunks or duration <= 0:
        return []
    total = sum(len(chunk) for chunk in chunks)
    cues, cursor = [], start
    for index, chunk in enumerate(chunks):
        end = start + duration if index == len(chunks) - 1 else cursor + duration * len(chunk) / total
        cues.append(Cue(round(cursor, 3), round(end, 3), chunk))
        cursor = end
    return cues


def _timestamp(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def render_srt(cues: list[Cue]) -> str:
    blocks = [
        f"{index}\n{_timestamp(cue.start)} --> {_timestamp(cue.end)}\n{cue.text}\n"
        for index, cue in enumerate(cues, start=1)
    ]
    return "\n".join(blocks)
