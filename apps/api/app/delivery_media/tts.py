"""Routed text-to-speech: the ``tts`` model role, resolved like other model roles."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import ModelConfig, Provider, RoleAssignment
from app.providers.openai_compatible import OpenAICompatibleClient
from app.security.secrets import secret_store

Synthesizer = Callable[[str], Awaitable[bytes]]


@dataclass(frozen=True)
class SpeechRoute:
    synthesize: Synthesizer
    model: str
    provider: str
    voice: str
    audio_format: str


def resolve_speech_route(
    db: Session, voice: str | None = None, audio_format: str | None = None
) -> SpeechRoute | None:
    """Return a synthesizer for the model assigned to the ``tts`` role, if any."""
    assignment = db.get(RoleAssignment, "tts")
    model = db.get(ModelConfig, assignment.model_config_id) if assignment else None
    provider = db.get(Provider, model.provider_id) if model else None
    if not model or not provider or not provider.enabled:
        return None
    client = OpenAICompatibleClient(
        provider.base_url,
        secret_store.get(provider.api_key_ref),
        provider.extra_headers,
        settings.request_timeout_seconds,
    )
    chosen_voice = voice or settings.tts_voice
    chosen_format = audio_format or settings.tts_format
    model_id = model.model_id

    async def synthesize(text: str) -> bytes:
        return await client.speech(
            model_id, text, voice=chosen_voice, response_format=chosen_format
        )

    return SpeechRoute(synthesize, model_id, provider.name, chosen_voice, chosen_format)
