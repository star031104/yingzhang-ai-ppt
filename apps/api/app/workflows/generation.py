"""Sample and full-deck generation cores shared by sync routes and durable jobs."""

import asyncio
import copy
import hashlib
import json
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.api.dependencies import project_or_404
from app.config import settings
from app.db.models import (
    DeckSpecRecord,
    SlideCandidate,
    SlideSpecRecord,
    SlideVersion,
)
from app.intelligence import extract_evidence_graph
from app.personalization.runtime import assert_current, guarded_generation
from app.presentation_engine.page_pipeline import render_deck_pages
from app.presentation_engine.service import EngineError, presentation_engine
from app.presentation_intelligence.assets import bind_source_figures, normalize_visual_intent
from app.presentation_intelligence.content_claims import (
    fit_audience_bullet,
    sanitize_numeric_claims,
    strip_internal_source_markers,
)
from app.presentation_intelligence.creative_pages import mark_creative_pages
from app.presentation_intelligence.planner import evidence_bindings, plan_deck
from app.slides import load_slides
from app.sources import load_sources
from app.workflows.images import ensure_generated_images
from app.workflows.outline_repair import best_source_refs, repair_outline_from_builtin
from app.workflows.visual_reflection import build_page_inspector, run_visual_reflection
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.orm import Session


def _set_gate(deck: DeckSpecRecord, name: str, status: str) -> dict:
    reproducibility = dict(deck.reproducibility or {})
    gates = dict(reproducibility.get("gates") or {})
    gates[name] = status
    reproducibility["gates"] = gates
    deck.reproducibility = reproducibility
    return gates


@guarded_generation
async def _generate_sample_core(
    project_id: str, db: Session, *, propagate_engine_error: bool = False
):
    project = project_or_404(project_id, db)
    deck = db.get(DeckSpecRecord, project_id)
    slides = load_slides(project_id, db)
    if not deck or not slides:
        raise HTTPException(409, "请先生成大纲")
    gates = (deck.reproducibility or {}).get("gates", {})
    if gates.get("enabled") and gates.get("outline") != "approved":
        raise HTTPException(409, "请先确认大纲，再生成代表样张")
    indices = sorted({0, len(slides) // 2, len(slides) - 1})
    picks = [slides[index] for index in indices]
    image_mode = (deck.reproducibility or {}).get("request", {}).get("imageMode", "off")
    if image_mode == "creative":
        mark_creative_pages(slides)
    if image_mode in {"auto", "creative"}:
        await ensure_generated_images(
            project, slides, db, {slide["position"] for slide in picks}, creative=image_mode == "creative"
        )
        picks = [slides[index] for index in indices]
    output = Path(project.artifact_path) / "slides" / "sample"
    try:
        await asyncio.to_thread(presentation_engine.run, "build", picks, output)
    except EngineError as exc:
        if propagate_engine_error:
            raise
        raise HTTPException(500, str(exc)) from exc
    return {"slides": [slide["position"] for slide in picks], "html": str(output / "index.html")}


@guarded_generation
async def _generate_core(
    project_id: str,
    db: Session,
    *,
    on_page_event: Callable[[dict], Awaitable[None]] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
):
    project = project_or_404(project_id, db)
    deck = db.get(DeckSpecRecord, project_id)
    slides = load_slides(project_id, db)
    if not slides:
        raise HTTPException(409, "Generate an outline first")
    gates = (deck.reproducibility or {}).get("gates", {}) if deck else {}
    if gates.get("enabled") and (
        gates.get("outline") != "approved" or gates.get("sample") != "approved"
    ):
        raise HTTPException(409, "请先确认大纲与代表样张，再批量生成")
    sources = load_sources(project_id, db)
    request_snapshot = (deck.reproducibility or {}).get("request", {}) if deck else {}
    if sources and slides:
        current_source_hash = hashlib.sha256("".join(source.get("sha256", "") for source in sources).encode()).hexdigest()
        source_changed = bool(
            deck
            and (deck.reproducibility or {}).get("sourceHash")
            and (deck.reproducibility or {}).get("sourceHash") != current_source_hash
        )
        recovery_baseline = plan_deck(
            sources,
            str(request_snapshot.get("title") or (deck.narrative or {}).get("title") or project.name),
            str(request_snapshot.get("preset") or (deck.narrative or {}).get("preset") or "academic"),
            len(slides),
            str(request_snapshot.get("instructions") or ""),
            brief=request_snapshot.get("professionalBrief") or {},
        )
        recovery_plan = {"slides": slides}
        automatic_recovery = repair_outline_from_builtin(
            recovery_plan, recovery_baseline, sources, force_all=source_changed
        )
        slides = recovery_plan["slides"]
        if automatic_recovery["repairedPositions"]:
            for slide in slides:
                if slide["position"] not in automatic_recovery["repairedPositions"]:
                    continue
                row = db.get(SlideSpecRecord, slide["id"])
                if not row:
                    continue
                row.current_version += 1
                row.spec = slide
                db.add(SlideVersion(
                    slide_id=slide["id"], version=row.current_version,
                    spec=slide, reason="automatic outline recovery",
                ))
            reproducibility = dict(deck.reproducibility or {}) if deck else {}
            reproducibility["latestAutomaticContentRepair"] = automatic_recovery
            reproducibility["sourceHash"] = current_source_hash
            if deck:
                deck.reproducibility = reproducibility
    evidence = extract_evidence_graph(sources)
    plan_snapshot = {"slides": slides}
    bind_source_figures(plan_snapshot, sources)
    normalize_visual_intent(plan_snapshot)
    for slide in slides:
        content = slide.setdefault("content", {})
        content["title"] = strip_internal_source_markers(content.get("title"))
        content["bullets"] = [
            fit_audience_bullet(strip_internal_source_markers(value))
            for value in content.get("bullets", [])
            if fit_audience_bullet(strip_internal_source_markers(value))
        ]
        slide["message"] = strip_internal_source_markers(slide.get("message"))
    image_mode = (deck.reproducibility or {}).get("request", {}).get("imageMode", "off") if deck else "off"
    if image_mode == "creative":
        mark_creative_pages(slides)
    if image_mode in {"auto", "creative"}:
        await ensure_generated_images(project, slides, db, creative=image_mode == "creative")
    for slide in slides:
        if slide.get("role") not in {"cover", "agenda", "questions"}:
            page_text = " ".join([
                str(slide.get("content", {}).get("title", "")),
                str(slide.get("message", "")),
                *[str(item) for item in slide.get("content", {}).get("bullets", [])],
            ])
            # 大纲阶段已经用页面责任和材料章节完成证据路由。生成阶段只为旧项目
            # 或手工创建且没有来源的页面补引用，避免渲染时被短文案误导而换错章节。
            if not slide.get("sourceRefs"):
                matched_refs = best_source_refs(page_text, sources)
                if matched_refs:
                    slide["sourceRefs"] = matched_refs
            sanitize_numeric_claims(slide, evidence, sources)
            slide["content"]["bullets"] = [
                fit_audience_bullet(value)
                for value in slide.get("content", {}).get("bullets", [])
                if fit_audience_bullet(value)
            ]
            slide["evidenceBindings"] = evidence_bindings(evidence, slide.get("sourceRefs", []))
        row = db.get(SlideSpecRecord, slide["id"])
        if row:
            row.spec = slide
    output = Path(project.artifact_path) / "slides" / "rendered"
    if on_page_event:
        # Page progress is persisted through short-lived sessions while rendering.
        # Flush preparation changes first so SQLite does not hold a writer lock
        # across the long-running Chromium work.
        db.commit()
        page_result = await render_deck_pages(
            slides,
            output,
            presentation_engine,
            concurrency=settings.render_concurrency,
            on_event=on_page_event,
            is_cancelled=is_cancelled,
            repair_rounds=settings.page_repair_rounds,
            inspector=build_page_inspector(db) if settings.page_repair_rounds else None,
        )
    else:
        try:
            # Keep the synchronous compatibility endpoint as one engine call. The
            # public background workflow uses the page-level pipeline above.
            await asyncio.to_thread(presentation_engine.run, "build", slides, output)
        except EngineError as exc:
            raise HTTPException(500, str(exc)) from exc
        page_result = {
            "pages": [
                {"slideId": slide["id"], "position": slide["position"], "status": "ready"}
                for slide in slides
            ],
            "readySlides": len(slides),
            "failedPages": [],
            "cancelledPages": [],
            "assembled": True,
        }
    page_states = {item["slideId"]: item for item in page_result["pages"]}
    assert_current()
    ready_ids = [
        slide["id"] for slide in slides if page_states.get(slide["id"], {}).get("status") == "ready"
    ]
    if ready_ids:
        db.execute(delete(SlideCandidate).where(SlideCandidate.slide_id.in_(ready_ids)))
    candidate_count = 0
    for slide_index, slide in enumerate(slides):
        generation_state = page_states.get(slide["id"], {"status": "pending"})
        slide["generationState"] = {
            key: value
            for key, value in generation_state.items()
            if key in {"status", "error", "candidateCount"}
        }
        candidate_root = output / "slides" / str(slide["position"])
        if generation_state.get("status") != "ready" or not (candidate_root / "current.json").is_file():
            slide_row = db.get(SlideSpecRecord, slide["id"])
            if slide_row:
                slide_row.spec = slide
            continue
        current = json.loads(
            (candidate_root / "current.json").read_text(encoding="utf-8")
        )
        updated_slide = copy.deepcopy(slide)
        if current.get("designSystem"):
            updated_slide["designSystem"] = current["designSystem"]
        visual_intent = dict(updated_slide.get("visualIntent") or {})
        visual_intent["selectedVariant"] = current["variant"]
        if visual_intent.get("variantSelectionSource") not in {"user", "critic"}:
            visual_intent["variantSelectionSource"] = "auto"
        updated_slide["visualIntent"] = visual_intent
        slides[slide_index] = updated_slide
        slide_row = db.get(SlideSpecRecord, slide["id"])
        if slide_row:
            repaired_content = any(
                action.get("action") in {"move-bullets-to-notes", "shorten-bullets", "drop-missing-assets"}
                for round_record in (updated_slide.get("renderRepair") or {}).get("history", [])
                for action in round_record.get("actions", [])
            )
            slide_row.spec = updated_slide
            if repaired_content:
                slide_row.current_version += 1
                db.add(SlideVersion(
                    slide_id=slide["id"], version=slide_row.current_version,
                    spec=copy.deepcopy(updated_slide), reason="automatic render repair",
                ))
        for score_path in candidate_root.glob("*.score.json"):
            variant = score_path.name.removesuffix(".score.json")
            score = json.loads(score_path.read_text(encoding="utf-8"))
            db.add(
                SlideCandidate(
                    slide_id=slide["id"], variant=variant,
                    artifact_path=str(candidate_root / f"{variant}.html"),
                    score=score, selected=variant == current["variant"],
                )
            )
            candidate_count += 1
    if page_result["assembled"]:
        visual_reflection = await run_visual_reflection(project, slides, output, db)
    else:
        visual_reflection = {"checked": 0, "applied": [], "visionStatus": "skipped-partial"}
    project.status = "partial" if page_result["failedPages"] else "ready"
    assert_current()
    db.commit()
    return {
        "slides": len(slides),
        "readySlides": page_result["readySlides"],
        "failedPages": page_result["failedPages"],
        "cancelledPages": page_result["cancelledPages"],
        "assembled": page_result["assembled"],
        "html": str(output / "index.html"),
        "candidateCount": candidate_count,
        "visualReflection": {
            "checked": visual_reflection["checked"],
            "applied": len(visual_reflection["applied"]),
            "visionStatus": visual_reflection["visionStatus"],
        },
    }

