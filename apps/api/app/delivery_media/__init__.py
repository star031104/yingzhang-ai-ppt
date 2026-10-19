"""Narrated video delivery: speaker notes → TTS → ffmpeg MP4 (+ SRT)."""

from app.delivery_media.narration import deck_narration, slide_narration

__all__ = ["deck_narration", "slide_narration"]
