"""Optional generated imagery for cover and concept pages."""

import copy
import time
from pathlib import Path

from app.config import settings
from app.db.models import (
    ModelConfig,
    Project,
    Provider,
    RoleAssignment,
    SlideSpecRecord,
)
from app.presentation_intelligence.creative_pages import (
    CREATIVE_ROLES,
    MAX_CREATIVE_PAGES,
    annotate_creative,
    poster_prompt,
)
from app.providers.openai_compatible import OpenAICompatibleClient, ProviderError
from app.security.secrets import secret_store
from fastapi import HTTPException
from sqlalchemy.orm import Session


async def ensure_generated_images(
    project: Project,
    slides: list[dict],
    db: Session,
    allowed_positions: set[int] | None = None,
    creative: bool = False,
) -> int:
    """Generate optional images; with ``creative`` also poster backgrounds for navigation pages."""
    assignment = db.get(RoleAssignment, "image_generation")
    model = db.get(ModelConfig, assignment.model_config_id) if assignment else None
    provider = db.get(Provider, model.provider_id) if model else None
    if not model or not provider or not provider.enabled:
        for slide in slides:
            slide["imageGeneration"] = {"status": "deferred", "message": "未配置可用生图服务，本轮使用原文素材和原生排版"}
        return 0
    candidates = [
        slide for slide in slides
        if slide.get("role") == "cover"
        or slide.get("visualIntent", {}).get("primaryVisual") == "generated-image"
        or slide.get("imageGeneration", {}).get("status") == "deferred"
    ]
    candidates = [
        slide for slide in candidates
        if slide.get("visualIntent", {}).get("allowGeneratedImage", True)
        and (allowed_positions is None or slide.get("position") in allowed_positions)
        and (slide.get("role") in CREATIVE_ROLES or not slide.get("visualIntent", {}).get("creativePoster"))
    ][: MAX_CREATIVE_PAGES if creative else 3]
    if not candidates:
        return 0
    client = OpenAICompatibleClient(
        provider.base_url,
        secret_store.get(provider.api_key_ref),
        provider.extra_headers,
        settings.request_timeout_seconds,
    )
    asset_root = Path(project.artifact_path) / "slides" / "assets" / "generated"
    asset_root.mkdir(parents=True, exist_ok=True)
    generated = 0
    deadline = time.monotonic() + max(1, settings.optional_image_wait_seconds)
    for slide in candidates:
        existing = next(
            (
                item for item in slide.get("assetBindings", [])
                if item.get("type") == "generated-image" and Path(item.get("path", "")).exists()
            ),
            None,
        )
        if existing:
            continue
        visual = slide.get("visualIntent", {})
        concrete_query = visual.get("imageQuery") or slide.get("content", {}).get("title", "")
        prompt = (poster_prompt(slide) if visual.get("creativePoster") else None) or visual.get("imagePrompt") or (
            f"为中文专业演示制作一张16:9纪实或科学可视化画面。画面主题：{concrete_query}。"
            f"本页观点：{slide.get('message', '')}。必须出现与主题直接相关、可辨认的真实对象、工作场景或技术装置，"
            "使用编辑摄影或严谨的信息插画语言，主体明确，右侧或边缘保留标题留白。"
        )
        prompt = (
            f"{prompt} 只生成视觉画面，不得出现任何文字、字母、数字、标志或水印；"
            "不要生成表格、统计图、流程图或虚构数据；禁止抽象科技网络、发光大脑、悬浮粒子、无意义几何球体和泛化蓝紫光效；"
            "优先真实物体、人物行为、设备界面关系或具体空间，适合裁切为16:9演示页面。"
        )
        size = "1664x928" if "qwen" in model.model_id.lower() else "1024x1024"
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderError("本轮可选配图等待已结束，先完成页面；再次生成时可继续查询")
            data = await client.image_generation(model.model_id, prompt, size,
                task_state_path=asset_root / f"slide-{slide['position']:02d}.task.json", wait_seconds=remaining)
        except ProviderError as exc:
            slide["imageGeneration"] = {"status": "deferred", "message": str(exc), "fallback": "source-or-native-layout"}
            visual = dict(slide.get("visualIntent") or {})
            if visual.get("primaryVisual") == "generated-image":
                visual["primaryVisual"] = "typography"
            visual.pop("creativePoster", None)
            slide["visualIntent"] = visual
            row = db.get(SlideSpecRecord, slide["id"])
            if row:
                row.spec = copy.deepcopy(slide)
            continue
        if not data or len(data) > 25 * 1024 * 1024:
            raise HTTPException(502, f"第 {slide['position']} 页生图结果无效")
        suffix = ".jpg" if data.startswith(b"\xff\xd8\xff") else ".png"
        path = asset_root / f"slide-{slide['position']:02d}{suffix}"
        path.write_bytes(data)
        binding = {
            "type": "generated-image",
            "path": str(path.resolve()),
            "alt": slide.get("content", {}).get("title", "主题配图"),
            "provider": provider.name,
            "model": model.model_id,
            "provenance": "AI 生成概念图，不作为事实证据",
        }
        slide["assetBindings"] = [
            item for item in slide.get("assetBindings", [])
            if item.get("type") != "generated-image"
        ] + [binding]
        slide["imageGeneration"] = {"status": "ready"}
        if visual.get("creativePoster"):
            annotate_creative(slide, binding)
        row = db.get(SlideSpecRecord, slide["id"])
        if row:
            row.spec = slide
        generated += 1
    db.commit()
    return generated

