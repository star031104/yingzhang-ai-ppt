"""Deck-level visual reflection: deterministic critic plus optional vision critic."""

import copy
import json
from pathlib import Path

from app.config import settings
from app.db.models import (
    ModelConfig,
    Project,
    Provider,
    RoleAssignment,
    SlideCandidate,
    SlideSpecRecord,
)
from app.presentation_engine.service import presentation_engine
from app.presentation_intelligence.visual_critic import (
    ISSUE_CODES,
    apply_safe_repairs,
    deterministic_review,
    load_candidate_snapshots,
    merge_vision_reviews,
    vision_prompt,
)
from app.providers.openai_compatible import OpenAICompatibleClient, ProviderError, vision_messages
from app.providers.structured import structured_completion
from app.security.secrets import secret_store
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

VISION_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "position": {"type": "integer"},
                    "issues": {"type": "array", "items": {"type": "string"}},
                    "recommendedVariant": {"type": ["string", "null"]},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["position", "issues"],
            },
        }
    },
    "required": ["slides"],
}


async def run_visual_reflection(
    project: Project, slides: list[dict], render_root: Path, db: Session
) -> dict:
    snapshots = load_candidate_snapshots(render_root, slides)
    reviews = deterministic_review(snapshots)
    vision_status = "not-configured"
    vision_error = ""
    assignment = db.get(RoleAssignment, "vision_critic")
    model = db.get(ModelConfig, assignment.model_config_id) if assignment else None
    provider = db.get(Provider, model.provider_id) if model else None
    if model and provider and provider.enabled and "vision" in (model.capabilities or []):
        client = OpenAICompatibleClient(
            provider.base_url,
            secret_store.get(provider.api_key_ref),
            provider.extra_headers,
            settings.request_timeout_seconds,
        )
        vision_reviews = []
        try:
            for start in range(0, len(snapshots), 4):
                batch = [
                    item for item in snapshots[start:start + 4]
                    if Path(item["imagePath"]).is_file()
                ]
                if not batch:
                    continue
                result = await structured_completion(
                    client,
                    model.model_id,
                    vision_messages(
                        vision_prompt(batch),
                        [Path(item["imagePath"]).read_bytes() for item in batch],
                    ),
                    VISION_REVIEW_SCHEMA,
                    purpose="vision-review",
                    temperature=0.1,
                    max_tokens=2400,
                )
                payload = result.value
                if isinstance(payload.get("slides"), list):
                    vision_reviews.extend(payload["slides"])
            reviews = merge_vision_reviews(reviews, vision_reviews)
            vision_status = "completed"
        except (ProviderError, ValueError, TypeError, OSError) as exc:
            vision_status = "fallback"
            vision_error = str(exc)[:600]
    applied = apply_safe_repairs(slides, snapshots, reviews)
    if applied:
        applied_positions = {item["position"] for item in applied}
        for slide in slides:
            if slide["position"] not in applied_positions:
                continue
            row = db.get(SlideSpecRecord, slide["id"])
            if row:
                row.spec = copy.deepcopy(slide)
                flag_modified(row, "spec")
            selected_variant = slide.get("visualIntent", {}).get("selectedVariant")
            for candidate in db.scalars(
                select(SlideCandidate).where(SlideCandidate.slide_id == slide["id"])
            ):
                candidate.selected = candidate.variant == selected_variant
        presentation_engine.run("assemble", slides, render_root)
    report = {
        "version": "visual-reflection-v1",
        "visionStatus": vision_status,
        "visionError": vision_error,
        "checked": len(snapshots),
        "applied": applied,
        "slides": reviews,
    }
    target = Path(project.artifact_path) / "validation" / "visual-critic.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report



PAGE_ISSUE_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["issues"],
}


def build_page_inspector(db: Session):
    """Return an async per-page vision inspector, or None when no vision critic is routed.

    The inspector only reports issue codes for one rendered page; the page repair
    loop decides what to patch. Database reads happen here, before rendering, so
    concurrent page tasks never touch the session.
    """
    if str(settings.page_vision_repair).lower() == "off":
        return None
    assignment = db.get(RoleAssignment, "vision_critic")
    model = db.get(ModelConfig, assignment.model_config_id) if assignment else None
    provider = db.get(Provider, model.provider_id) if model else None
    if not (model and provider and provider.enabled and "vision" in (model.capabilities or [])):
        return None
    client = OpenAICompatibleClient(
        provider.base_url,
        secret_store.get(provider.api_key_ref),
        provider.extra_headers,
        settings.request_timeout_seconds,
    )
    model_id = model.model_id

    async def inspect(slide: dict, snapshot: dict) -> list[str]:
        prompt = (
            "你是演示页面视觉质检员。只检查附图这一页是否存在："
            + "、".join(sorted(ISSUE_CODES))
            + "。不评价文案和事实。没有问题时 issues 返回空数组。"
            + '只返回 JSON：{"issues":["awkward-wrap"],"reason":"简短原因"}'
            + f"\n页面标题：{str((slide.get('content') or {}).get('title', ''))[:80]}"
        )
        result = await structured_completion(
            client,
            model_id,
            vision_messages(prompt, [Path(snapshot["imagePath"]).read_bytes()]),
            PAGE_ISSUE_SCHEMA,
            purpose="page-vision-check",
            temperature=0.1,
            max_tokens=600,
        )
        return [str(item) for item in result.value.get("issues", []) if str(item) in ISSUE_CODES]

    return inspect
