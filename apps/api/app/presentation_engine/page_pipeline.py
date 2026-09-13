import asyncio
import json
import math
import shutil
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from app.presentation_engine.service import PresentationEngine
from app.validation.render_safety import safe_render_candidate

PageEventHandler = Callable[[dict[str, Any]], Awaitable[None]]
CancellationCheck = Callable[[], bool]


def _variant_family(variant: str) -> str:
    return {
        "hero": "cover",
        "editorial-cover": "cover-editorial",
        "minimal-cover": "typography",
        "numbered-list": "list",
        "section-map": "map",
        "agenda-cards": "cards",
        "chapter-divider": "section",
        "section-statement": "typography",
        "minimal-section": "minimal",
        "big-statement": "typography",
        "context-cards": "cards",
        "timeline": "timeline",
        "problem-cards": "cards",
        "contrast": "comparison",
        "before-after": "comparison",
        "workflow": "flow",
        "three-stage": "stages",
        "process": "flow",
        "layered-architecture": "layers",
        "pipeline": "flow",
        "hub-spoke": "map",
        "evidence-chain": "flow",
        "source-map": "map",
        "claim-map": "layers",
        "chart-focus": "chart",
        "metric-wall": "metrics",
        "table-highlight": "table",
        "comparison-bars": "chart",
        "two-column": "comparison",
        "scorecard": "metrics",
        "finding-cards": "cards",
        "ablation": "chart",
        "takeaways": "list",
        "summary-grid": "cards",
        "next-steps": "timeline",
        "minimal-qa": "minimal",
        "closing-statement": "typography",
        "contact": "contact",
        "split": "split",
        "statement": "typography",
        "cards": "cards",
        "figure-wide": "image-wide",
        "figure-analysis": "image-analysis",
        "figure-focus": "image-focus",
        "image-story": "image-split",
        "media-focus": "media",
    }.get(variant, variant or "unspecified")


def _deck_rhythm_score(
    variant: str,
    previous_family: str | None,
    variant_counts: dict[str, int],
    family_counts: dict[str, int],
) -> int:
    family = _variant_family(variant)
    score = (
        100
        - variant_counts.get(variant, 0) * 16
        - family_counts.get(family, 0) * 7
        - (18 if previous_family == family else 0)
    )
    return max(48, score)


def _js_round(value: float) -> int:
    return math.floor(value + 0.5)


def _recompute_overall(score: dict[str, Any]) -> int:
    weighted = (
        float(score.get("geometry", 0)) * 0.16
        + float(score.get("readability", 0)) * 0.14
        + float(score.get("hierarchy", 0)) * 0.12
        + float(score.get("whitespace", 0)) * 0.09
        + float(score.get("alignment", 0)) * 0.08
        + float(score.get("semanticFit", 0)) * 0.12
        + float(score.get("contentFit", 0)) * 0.11
        + float(score.get("visualEvidence", 0)) * 0.07
        + float(score.get("planningFit", 0)) * 0.06
        + float(score.get("styleConsistency", 0)) * 0.03
        + float(score.get("deckRhythm", 0)) * 0.02
    )
    return max(0, min(100, _js_round(weighted)))


def _safe_candidate(score: dict[str, Any]) -> bool:
    return safe_render_candidate(score)


def _promote_page_artifacts(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for stale in target.iterdir():
        if stale.is_file():
            stale.unlink()
    for artifact in source.iterdir():
        if artifact.is_file():
            shutil.copy2(artifact, target / artifact.name)


def select_deck_variants(slides: list[dict], output: Path) -> list[dict[str, Any]]:
    """Apply the engine's cross-page rhythm scoring after parallel page rendering."""
    variant_counts: dict[str, int] = {}
    family_counts: dict[str, int] = {}
    previous_family: str | None = None
    selections: list[dict[str, Any]] = []

    for slide in sorted(slides, key=lambda item: int(item["position"])):
        root = output / "slides" / str(slide["position"])
        prior_current = json.loads((root / "current.json").read_text(encoding="utf-8")) if (root / "current.json").exists() else {}
        if prior_current.get("designSystem"):
            slide["designSystem"] = prior_current["designSystem"]
        candidates: list[dict[str, Any]] = []
        for score_path in sorted(root.glob("*.score.json")):
            variant = score_path.name.removesuffix(".score.json")
            score = json.loads(score_path.read_text(encoding="utf-8"))
            effective = str(score.get("effectiveVariant") or variant)
            score["deckRhythm"] = _deck_rhythm_score(
                effective, previous_family, variant_counts, family_counts
            )
            score["variantFamily"] = _variant_family(effective)
            score["overall"] = _recompute_overall(score)
            score_path.write_text(
                json.dumps(score, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            candidates.append({"variant": variant, "score": score})
        if not candidates:
            continue

        intent = slide.setdefault("visualIntent", {})
        preferred = str(intent.get("selectedVariant") or "")
        planned = str((slide.get("layoutPlan") or {}).get("recommendedVariant") or "")
        chosen = next((item for item in candidates if item["variant"] == preferred), None)
        protected = intent.get("variantSelectionSource") in {"user", "critic"}
        if chosen and not protected and not _safe_candidate(chosen["score"]):
            chosen = None
        if chosen is None:
            chosen = next(
                (
                    item
                    for item in candidates
                    if item["variant"] == planned and _safe_candidate(item["score"])
                ),
                None,
            )
        if chosen is None:
            safe = [item for item in candidates if _safe_candidate(item["score"])]
            designed = [item for item in safe if item["variant"] != "content-list"]
            chosen = max(designed or safe or candidates, key=lambda item: int(item["score"].get("overall", 0)))

        preferences = (slide.get("designSystem") or {}).get("personalization", {})
        preferred_variant = preferences.get("preferredVariant") or preferences.get("preferredByRole", {}).get(slide.get("role"))
        personal_choice = next((item for item in candidates if item["variant"] == preferred_variant), None)
        dimensions = ("overall", "geometry", "readability", "contentFit", "semanticFit", "hierarchy", "visualEvidence")
        if not protected and personal_choice and _safe_candidate(personal_choice["score"]) and all(
            personal_choice["score"].get(key, 0) >= chosen["score"].get(key, 0) for key in dimensions
        ):
            chosen = personal_choice

        if not protected and preferences.get("density") == "airy":
            spacious = [item for item in candidates if _safe_candidate(item["score"]) and all(
                item["score"].get(key, 0) >= chosen["score"].get(key, 0) for key in dimensions)]
            if spacious:
                chosen = max([chosen, *spacious], key=lambda item: item["score"].get("whitespace", 0))

        intent["selectedVariant"] = chosen["variant"]
        if intent.get("variantSelectionSource") not in {"user", "critic"}:
            intent["variantSelectionSource"] = "auto"
        (root / "current.json").write_text(
            json.dumps({
                "variant": chosen["variant"], "score": chosen["score"]["overall"],
                "scoreDetail": chosen["score"],
                "designSystem": slide.get("designSystem", {}),
                "personalizationQA": prior_current.get("personalizationQA"),
                "needsReview": not _safe_candidate(chosen["score"]),
            }, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        effective = str(chosen["score"].get("effectiveVariant") or chosen["variant"])
        family = _variant_family(effective)
        variant_counts[effective] = variant_counts.get(effective, 0) + 1
        family_counts[family] = family_counts.get(family, 0) + 1
        previous_family = family
        selections.append({"slideId": slide["id"], **chosen})
    return selections


async def render_deck_pages(
    slides: list[dict],
    output: Path,
    engine: PresentationEngine,
    *,
    concurrency: int = 2,
    on_event: PageEventHandler | None = None,
    is_cancelled: CancellationCheck | None = None,
) -> dict[str, Any]:
    """Render pages independently, promote successful artifacts, then assemble once."""
    execution_id = uuid.uuid4().hex
    work_root = output.parent / "page-jobs" / execution_id
    work_root.mkdir(parents=True, exist_ok=True)
    limit = asyncio.Semaphore(max(1, min(concurrency, 4)))
    states: dict[str, dict[str, Any]] = {}
    state_lock = asyncio.Lock()

    async def emit(slide: dict, status: str, **extra: Any) -> None:
        async with state_lock:
            state = {
                "slideId": slide["id"],
                "position": int(slide["position"]),
                "status": status,
                **extra,
            }
            states[slide["id"]] = state
            snapshot = [
                states[key]
                for key in sorted(states, key=lambda item: states[item]["position"])
            ]
            counts = {
                name: sum(1 for item in states.values() if item["status"] == name)
                for name in ("pending", "running", "ready", "failed", "cancelled")
            }
        if on_event:
            await on_event({**state, "pages": snapshot, "counts": counts, "total": len(slides)})

    for slide in slides:
        await emit(slide, "pending")

    async def render_one(slide: dict) -> None:
        async with limit:
            if is_cancelled and is_cancelled():
                await emit(slide, "cancelled")
                return
            await emit(slide, "running")
            page_output = work_root / f"{int(slide['position']):03d}-{slide['id']}" / "rendered"
            try:
                await asyncio.to_thread(engine.run, "build", [slide], page_output)
                source = page_output / "slides" / str(slide["position"])
                if not (source / "current.json").is_file():
                    raise RuntimeError("页面渲染未产生可用候选")
                target = output / "slides" / str(slide["position"])
                from app.personalization.runtime import assert_current, lock
                with lock:
                    assert_current()
                    _promote_page_artifacts(source, target)
                await emit(
                    slide,
                    "ready",
                    artifactRoot=str(target),
                    candidateCount=len(list(target.glob("*.score.json"))),
                )
            except Exception as exc:  # noqa: BLE001 - one page must not abort sibling pages
                await emit(slide, "failed", error=str(exc)[:500])

    await asyncio.gather(*(render_one(slide) for slide in slides))

    ready_slides = [slide for slide in slides if states[slide["id"]]["status"] == "ready"]
    failed_pages = [state for state in states.values() if state["status"] == "failed"]
    cancelled_pages = [state for state in states.values() if state["status"] == "cancelled"]
    assembled = not failed_pages and not cancelled_pages and len(ready_slides) == len(slides)
    selections: list[dict[str, Any]] = []
    if assembled:
        from app.personalization.runtime import assert_current
        assert_current()
        selections = select_deck_variants(slides, output)
        await asyncio.to_thread(engine.run, "assemble", slides, output)

    return {
        "executionId": execution_id,
        "workRoot": str(work_root),
        "pages": sorted(states.values(), key=lambda item: item["position"]),
        "readySlides": len(ready_slides),
        "failedPages": failed_pages,
        "cancelledPages": cancelled_pages,
        "assembled": assembled,
        "selections": selections,
    }
