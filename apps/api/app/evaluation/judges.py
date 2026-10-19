"""Model access for evaluators. Every evaluator also works without any judge."""

import asyncio
from dataclasses import dataclass

from app.config import settings
from app.providers.openai_compatible import OpenAICompatibleClient

MODEL_CALL_TIMEOUT_SECONDS = 120.0


@dataclass
class ModelJudge:
    client: OpenAICompatibleClient
    model_id: str
    vision: bool = False
    timeout: float = MODEL_CALL_TIMEOUT_SECONDS

    async def complete(self, prompt: str, max_tokens: int = 2400) -> str:
        return await asyncio.wait_for(
            self.client.chat_completion(
                self.model_id,
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=max_tokens,
                json_mode=True,
            ),
            self.timeout,
        )

    async def see(self, prompt: str, images: list[bytes], max_tokens: int = 2400) -> str:
        return await asyncio.wait_for(
            self.client.vision_completion(self.model_id, prompt, images, max_tokens=max_tokens),
            self.timeout,
        )


def judge_from_settings(base_url: str, api_key: str | None, model_id: str, vision: bool) -> ModelJudge:
    client = OpenAICompatibleClient(base_url, api_key, {}, settings.request_timeout_seconds)
    return ModelJudge(client, model_id, vision)


def resolve_judges(db) -> tuple[ModelJudge | None, ModelJudge | None]:
    """Return (text judge, vision judge) from configured role assignments.

    The vision critic role judges rendered pages; the planner (or source analyst) role is the
    text judge and quiz model. Disabled providers or missing roles yield ``None``.
    """
    from app.db.models import ModelConfig, Provider, RoleAssignment
    from app.security.secrets import secret_store

    def build(role: str, need_vision: bool) -> ModelJudge | None:
        assignment = db.get(RoleAssignment, role)
        model = db.get(ModelConfig, assignment.model_config_id) if assignment else None
        provider = db.get(Provider, model.provider_id) if model else None
        if not model or not provider or not provider.enabled:
            return None
        if need_vision and "vision" not in (model.capabilities or []):
            return None
        client = OpenAICompatibleClient(
            provider.base_url,
            secret_store.get(provider.api_key_ref),
            provider.extra_headers,
            settings.request_timeout_seconds,
        )
        return ModelJudge(client, model.model_id, need_vision)

    text = build("planner", False) or build("source_analyst", False)
    vision = build("vision_critic", True)
    return text, vision
