"""Orchestrates PPTEval, PaperQuiz and render review, and shapes persisted evaluation runs."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.evaluation.ppteval import evaluate_ppteval
from app.evaluation.quiz import evaluate_quiz
from app.evaluation.render_review import render_pptx, review_rendered_pptx

RESEARCH_SUITE = "research-v1"
KINDS = ("ppteval", "quiz", "render")
EVALUATION_TIMEOUT_SECONDS = 600.0
RUNNING_STALE_AFTER = timedelta(minutes=20)


def content_fingerprint(deck_fingerprint: str, sources: list[dict]) -> str:
    """Deck + source fingerprint: any slide, asset or material change makes results stale."""
    payload = json.dumps(
        {"deck": deck_fingerprint, "sources": sorted(str(source.get("sha256", "")) for source in sources
                                                     if not source.get("synthetic"))},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def run_evaluations(
    kinds: list[str],
    *,
    slides: list[dict],
    sources: list[dict],
    quality_report: dict,
    output_root: Path,
    pptx: Path | None = None,
    text_judge=None,
    vision_judge=None,
    renderer=render_pptx,
    max_questions: int = 18,
) -> dict:
    """Run the requested evaluators. Each one degrades to deterministic rules on its own."""
    kinds = [kind for kind in KINDS if kind in kinds]
    results: dict = {"kinds": kinds}
    render_pages: dict[int, dict] = {}
    if "render" in kinds or ("ppteval" in kinds and vision_judge and pptx):
        render = await review_rendered_pptx(
            pptx, slides, output_root / "render", vision_judge=vision_judge, renderer=renderer,
        )
        if "render" in kinds:
            results["render"] = render
        if render.get("status") == "completed" and render.get("pageCount") == len(slides):
            render_pages = {
                int(slide.get("position", index + 1)): page
                for index, (slide, page) in enumerate(zip(slides, render["pages"]))
            }
    if "ppteval" in kinds:
        results["ppteval"] = await evaluate_ppteval(
            slides, quality_report, render_pages=render_pages,
            text_judge=text_judge, vision_judge=vision_judge,
        )
    if "quiz" in kinds:
        detail = max(2, round(max_questions * 0.55))
        results["quiz"] = await evaluate_quiz(
            slides, sources, judge=text_judge, max_detail=detail, max_concept=max(2, max_questions - detail),
        )
    results["summary"] = summarize(results)
    return results


def summarize(results: dict) -> dict:
    summary: dict = {}
    ppteval = results.get("ppteval")
    if ppteval:
        summary.update({
            "content": ppteval["deck"]["content"]["score"],
            "design": ppteval["deck"]["design"]["score"],
            "coherence": ppteval["deck"]["coherence"]["score"],
            "overall": ppteval["overall"],
            "pptevalMode": ppteval["mode"],
        })
    quiz = results.get("quiz")
    if quiz:
        summary.update({
            "retention": quiz.get("retention"),
            "detailRetention": quiz.get("detailRetention"),
            "conceptRetention": quiz.get("conceptRetention"),
            "quizStatus": quiz.get("status"),
        })
    render = results.get("render")
    if render:
        summary.update({
            "renderStatus": render.get("status"),
            "renderErrors": render.get("errorCount"),
            "renderWarnings": render.get("warningCount"),
            "renderScore": render.get("averageScore"),
        })
    return summary


def _public(value):
    """Drop internal keys and absolute file paths from persisted results."""
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items() if not key.startswith("_") and key != "imagePath"}
    if isinstance(value, list):
        return [_public(item) for item in value]
    return value


def run_view(row, current_fingerprint: str | None, detail: bool = True) -> dict:
    metrics = row.metrics or {}
    status = row.status
    created = row.created_at
    if created and created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    if status == "running" and created and datetime.now(UTC) - created > RUNNING_STALE_AFTER:
        status = "interrupted"
    view = {
        "id": row.id,
        "suite": row.suite,
        "status": status,
        "kinds": metrics.get("kinds", []),
        "createdAt": created.isoformat() if created else None,
        "fingerprint": metrics.get("fingerprint"),
        "stale": bool(current_fingerprint and metrics.get("fingerprint") != current_fingerprint),
        "exportMatchesCurrent": metrics.get("exportMatchesCurrent"),
        "summary": metrics.get("summary", {}),
        "error": metrics.get("error"),
        "models": metrics.get("models", {}),
    }
    if detail:
        for kind in KINDS:
            if kind in metrics:
                view[kind] = _public(metrics[kind])
    return view
