"""PPTEval-style Content / Design / Coherence scoring on a 1–5 scale.

Follows PPTAgent's PPTEval rubric (EMNLP 2025): a judge scores every slide on Content,
Design and Coherence with a short rationale, and the deck is scored as a whole. A vision
judge looks at rendered PPTX pages when available; otherwise a text judge reads the slide
copy (design then stays rule-based); without any model a deterministic mapping of existing
quality metrics produces the same schema.
"""

import json
from pathlib import Path

from app.evaluation.common import (
    NAVIGATION_ROLES,
    Judge,
    clamp_score,
    from_percent,
    parse_json_object,
    short,
    slide_text,
)
from app.validation.quality import ISSUE_GUIDANCE
from app.validation.visual_maturity import variant_family

VERSION = "ppteval-v1"
DIMENSIONS = ("content", "design", "coherence")
DIMENSION_LABELS = {"content": "内容", "design": "设计", "coherence": "连贯"}

RENDER_GUIDANCE = {
    "text-clipped": ("文字被裁切", "缩短文案或改用容量更大的版式，确保文字完整显示。"),
    "low-text-contrast": ("文字对比度不足", "加深文字或减淡背景，正文对比度至少达到 4.5:1。"),
    "missing-asset": ("素材缺失", "重新绑定图片或改用不依赖该素材的版式。"),
    "missing-content": ("页面内容缺失", "检查该页正文是否被版式遗漏，必要时更换候选。"),
    "blank-page": ("导出页面空白", "检查 PPTX 中该页对象是否丢失，重新导出后复核。"),
    "near-empty-page": ("页面内容过少", "补充本页关键证据或与相邻页合并。"),
    "large-empty-region": ("大面积留白失衡", "调整主视觉尺寸或改用分栏版式，让内容占据视觉中心。"),
    "edge-touching": ("内容贴边或越界", "为文字和图形保留安全边距，避免投影时被裁切。"),
    "low-contrast": ("整页对比度过低", "提高前景与背景的明度差，避免浅灰字配白底。"),
    "page-count-mismatch": ("导出页数不一致", "重新导出 PPTX，并确认没有隐藏页或缺页。"),
    "missing-title-text": ("标题未出现在导出页面", "核对替代字体和文本框，确保标题在 PPTX 中可读。"),
}

CONTENT_PENALTIES = {
    "empty-content-slide": 4, "placeholder-slide-title": 2, "unsupported-metric": 2,
    "metric-binding-mismatch": 2, "generated-factual-visual": 2, "missing-evidence-binding": 1,
    "weak-source-grounding": 1, "broken-source-ref": 1, "weak-chart-encoding": 1,
    "missing-content": 2, "missing-title-text": 1,
}
DESIGN_PENALTIES = {
    "density": 2, "high-reading-load": 1, "long-audience-bullet": 1, "long-slide-title": 1,
    "visible-source-marker": 1, "render-error": 2, "text-clipped": 2, "low-text-contrast": 2,
    "missing-asset": 1, "blank-page": 4, "near-empty-page": 1, "large-empty-region": 1,
    "edge-touching": 1, "low-contrast": 2,
}
COHERENCE_PENALTIES = {
    "duplicate-slide-title": 2, "duplicate-slide-content": 2, "repeated-message": 1,
    "missing-single-message": 1, "audience-copy-process-leak": 2, "generic-title": 1,
    "position-contract-broken": 1,
}
EVIDENCE_FAMILIES = {"chart", "metrics", "table", "flow", "stages", "timeline", "layers", "map", "media"}


def _guidance(code: str) -> tuple[str, str]:
    return ISSUE_GUIDANCE.get(code) or RENDER_GUIDANCE.get(code) or (code, "按检查结果修改本页。")


def _dimension_for(code: str) -> str | None:
    for dimension, table in (
        ("content", CONTENT_PENALTIES), ("design", DESIGN_PENALTIES), ("coherence", COHERENCE_PENALTIES),
    ):
        if code in table:
            return dimension
    return None


def _slide_issue_codes(position: int, report: dict, render_pages: dict[int, dict]) -> list[str]:
    codes = [str(item.get("code")) for item in report.get("issues", []) if item.get("slide") == position]
    visual = next(
        (item for item in (report.get("visualQA") or {}).get("slides", []) if item.get("position") == position),
        None,
    )
    if visual:
        codes.extend(str(item.get("code")) for item in visual.get("issues", []) if isinstance(item, dict))
    for issue in (render_pages.get(position) or {}).get("issues", []):
        codes.append(str(issue.get("code")))
    return list(dict.fromkeys(code for code in codes if code and code != "None"))


def _score_with(base: int, codes: list[str], table: dict[str, int]) -> int:
    return max(1, min(5, base - sum(table.get(code, 0) for code in codes)))


def _rationale(dimension: str, score: int, codes: list[str], base_note: str) -> str:
    relevant = [_guidance(code)[0] for code in codes if _dimension_for(code) == dimension]
    if relevant:
        return short(f"{base_note}；发现：{'、'.join(dict.fromkeys(relevant))}", 120)
    praise = {
        "content": "信息明确且有来源支撑",
        "design": "版式与可读性未发现明显问题",
        "coherence": "与前后页衔接自然，未发现重复",
    }[dimension]
    return short(f"{base_note}；{praise}" if base_note else praise, 120)


def rule_slide_scores(slide: dict, report: dict, render_pages: dict[int, dict]) -> dict:
    position = int(slide.get("position", 0))
    codes = _slide_issue_codes(position, report, render_pages)
    navigation = slide.get("role") in NAVIGATION_ROLES
    visual = next(
        (item for item in (report.get("visualQA") or {}).get("slides", []) if item.get("position") == position),
        None,
    )
    has_sources = bool(slide.get("sourceRefs") or slide.get("evidenceBindings"))
    content_base = 4 if navigation else (5 if has_sources else 4)
    content_note = "导航页" if navigation else ("有材料来源" if has_sources else "未绑定材料来源")
    if visual:
        design_base = from_percent(min(visual.get("overall", 0), visual.get("readability", 100) or 100))
        design_note = f"渲染检查 {round(visual.get('overall', 0))} 分"
    else:
        selected = (slide.get("visualIntent") or {}).get("selectedVariant") or (
            slide.get("layoutPlan") or {}
        ).get("recommendedVariant")
        family = variant_family(selected, (slide.get("visualIntent") or {}).get("primaryVisual"))
        design_base = 5 if family in EVIDENCE_FAMILIES or family.startswith("image-") or navigation else 4
        design_note = "尚无渲染结果，按版式规划估计"
    if render_pages.get(position, {}).get("score") is not None:
        design_base = min(design_base, int(render_pages[position]["score"]))
        design_note += "；已核对 PPTX 实际页面"
    coherence_base = 5
    scores = {
        "content": _score_with(content_base, codes, CONTENT_PENALTIES),
        "design": _score_with(design_base, codes, DESIGN_PENALTIES),
        "coherence": _score_with(coherence_base, codes, COHERENCE_PENALTIES),
    }
    notes = {"content": content_note, "design": design_note, "coherence": ""}
    issues = []
    for code in codes:
        dimension = _dimension_for(code)
        if not dimension:
            continue
        title, detail = _guidance(code)
        issues.append({"dimension": dimension, "code": code, "message": title, "suggestion": detail})
    return {
        "position": position,
        "slideId": slide.get("id"),
        "title": short((slide.get("content") or {}).get("title", ""), 60),
        **{
            dimension: {
                "score": scores[dimension],
                "rationale": _rationale(dimension, scores[dimension], codes, notes[dimension]),
                "source": "rule",
            }
            for dimension in DIMENSIONS
        },
        "issues": issues,
    }


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 1) if values else 0.0


def _suggestions(slides: list[dict], dimension: str, limit: int = 3) -> list[str]:
    ranked = sorted(slides, key=lambda item: item[dimension]["score"])
    result: list[str] = []
    for item in ranked:
        for issue in item.get("issues", []):
            if issue["dimension"] != dimension:
                continue
            text = f"第 {item['position']} 页：{issue['suggestion']}"
            if text not in result:
                result.append(text)
            if len(result) >= limit:
                return result
    return result


def rule_deck_scores(slides: list[dict], scored: list[dict], report: dict) -> dict:
    audit = (report.get("professionalAudit") or {}).get("dimensions", {})
    scorecard = report.get("scorecard", {})
    maturity = report.get("visualMaturity", {})
    content_metric = _mean([
        audit.get("completeness", 0), audit.get("correctness", 0), audit.get("fidelity", 0),
    ]) if audit else round(report.get("contentCoverage", 0) * 100)
    coherence_metric = _mean([
        scorecard.get("coherence", 100), scorecard.get("structure", 100), maturity.get("narrativeRhythm", 100),
    ])
    missing_conclusion = any(item.get("code") == "missing-conclusion" for item in report.get("issues", []))
    deck = {
        "content": round(
            0.5 * _mean([item["content"]["score"] for item in scored]) + 0.5 * from_percent(content_metric), 1
        ),
        "design": round(
            0.5 * _mean([item["design"]["score"] for item in scored])
            + 0.5 * from_percent(maturity.get("score", 70)), 1
        ),
        "coherence": round(
            max(1.0, 0.4 * _mean([item["coherence"]["score"] for item in scored])
                + 0.6 * from_percent(coherence_metric) - (1 if missing_conclusion else 0)), 1
        ),
    }
    coverage = round(report.get("contentCoverage", 0) * 100)
    rationales = {
        "content": f"证据覆盖 {coverage}%，数值主张可溯源率 {round(report.get('claimCoverage', 1) * 100)}%",
        "design": (
            f"视觉成熟度 {maturity.get('score', '—')} 分，{maturity.get('uniqueFamilies', 0)} 种构图骨架"
        ),
        "coherence": (
            f"叙事节奏 {maturity.get('narrativeRhythm', '—')} 分，结构 {scorecard.get('structure', '—')} 分"
            + ("，缺少结论页" if missing_conclusion else "")
        ),
    }
    result = {}
    for dimension in DIMENSIONS:
        suggestions = _suggestions(scored, dimension)
        if dimension == "coherence" and missing_conclusion:
            suggestions.insert(0, "在末尾增加结论与行动页，回应开篇提出的问题。")
        result[dimension] = {
            "score": max(1.0, min(5.0, deck[dimension])),
            "rationale": short(rationales[dimension], 120),
            "suggestions": suggestions[:3],
            "source": "rule",
        }
    return result


def _slide_prompt(batch: list[dict], outline: list[str], with_images: bool) -> str:
    pages = [
        {"position": slide["position"], "role": slide.get("role"), "text": short(slide_text(slide), 900)}
        for slide in batch
    ]
    dimensions = DIMENSIONS if with_images else ("content", "coherence")
    image_note = (
        "随附图片依次对应下列页面的 PPTX 实际渲染结果，请依据图片评价设计。"
        if with_images else "你只能看到文字，因此不评价设计。"
    )
    schema = {"slides": [{
        "position": "页码（整数）",
        "scores": {
            name: {"score": "1-5 的整数", "rationale": "不超过40字的中文理由", "suggestion": "具体修改建议"}
            for name in dimensions
        },
    }]}
    return (
        "你是演示文稿评审专家，按 PPTEval 标准为每页评分（1–5 的整数，5 为最好）。\n"
        "content：信息是否准确、充分、有证据且表达简洁；design：版式、层级、对比度、留白与可读性；"
        "coherence：与全稿逻辑的衔接、页面主张是否推进叙事。\n"
        f"{image_note}\n全稿目录：{json.dumps(outline, ensure_ascii=False)}\n"
        f"待评页面：{json.dumps(pages, ensure_ascii=False)}\n"
        f"只输出符合此结构的 JSON 对象，不要其他文字：{json.dumps(schema, ensure_ascii=False)}"
    )


def _merge_model_slides(scored: list[dict], payload: dict, dimensions: tuple[str, ...], source: str) -> int:
    by_position = {item["position"]: item for item in scored}
    merged = 0
    for entry in payload.get("slides", []) if isinstance(payload.get("slides"), list) else []:
        if not isinstance(entry, dict):
            continue
        try:
            position = int(entry.get("position"))
        except (TypeError, ValueError):
            continue
        target = by_position.get(position)
        scores = entry.get("scores") if isinstance(entry.get("scores"), dict) else entry
        if not target or not isinstance(scores, dict):
            continue
        for dimension in dimensions:
            value = scores.get(dimension)
            value = value if isinstance(value, dict) else {"score": value}
            score = clamp_score(value.get("score"))
            if score is None:
                continue
            target[dimension] = {
                "score": score,
                "rationale": short(value.get("rationale") or target[dimension]["rationale"], 120),
                "source": source,
            }
            suggestion = short(value.get("suggestion"), 160)
            if suggestion and score <= 3:
                target["issues"].append({
                    "dimension": dimension, "code": f"{source}-judge", "message": "评审模型建议",
                    "suggestion": suggestion,
                })
            merged += 1
    return merged


async def _model_deck_coherence(judge: Judge, slides: list[dict]) -> dict | None:
    outline = [
        {"position": slide.get("position"), "role": slide.get("role"),
         "title": short((slide.get("content") or {}).get("title", ""), 60),
         "message": short(slide.get("message", ""), 100)}
        for slide in slides
    ]
    prompt = (
        "你是演示文稿评审专家。按 PPTEval 的 coherence 维度评价整套演示的逻辑结构："
        "开场是否提出问题、正文是否递进、结尾是否给出结论与行动。\n"
        f"全稿结构：{json.dumps(outline, ensure_ascii=False)}\n"
        "只输出 JSON：{\"score\":1-5 的整数,\"rationale\":\"不超过60字的中文理由\","
        "\"suggestions\":[\"具体修改建议，注明页码\"]}"
    )
    payload = parse_json_object(await judge.complete(prompt, max_tokens=800))
    score = clamp_score(payload.get("score"))
    if score is None:
        return None
    suggestions = payload.get("suggestions") if isinstance(payload.get("suggestions"), list) else []
    return {
        "score": float(score),
        "rationale": short(payload.get("rationale"), 120),
        "suggestions": [short(item, 160) for item in suggestions if isinstance(item, str)][:3],
        "source": "text",
    }


async def evaluate_ppteval(
    slides: list[dict],
    report: dict,
    *,
    render_pages: dict[int, dict] | None = None,
    text_judge: Judge | None = None,
    vision_judge: Judge | None = None,
) -> dict:
    """Score a deck. ``render_pages`` maps slide position to {imagePath, issues, score}."""
    render_pages = render_pages or {}
    scored = [rule_slide_scores(slide, report, render_pages) for slide in slides]
    deck = rule_deck_scores(slides, scored, report)
    outline = [short((slide.get("content") or {}).get("title", ""), 40) for slide in slides]
    mode = "rule"
    errors: list[str] = []
    imaged = [
        slide for slide in slides
        if vision_judge and Path(str((render_pages.get(int(slide.get("position", 0))) or {}).get("imagePath", ""))).is_file()
    ]
    imaged_positions = {int(slide["position"]) for slide in imaged}
    if imaged:
        for start in range(0, len(imaged), 4):
            batch = imaged[start:start + 4]
            try:
                images = [Path(render_pages[int(slide["position"])]["imagePath"]).read_bytes() for slide in batch]
                raw = await vision_judge.see(_slide_prompt(batch, outline, True), images)
                if _merge_model_slides(scored, parse_json_object(raw), DIMENSIONS, "vision"):
                    mode = "vision"
            except Exception as exc:  # noqa: BLE001 - any provider failure falls back to rules
                errors.append(short(f"视觉评审失败：{exc}", 200))
                break
    remaining = [slide for slide in slides if int(slide.get("position", 0)) not in imaged_positions]
    if text_judge and remaining:
        for start in range(0, len(remaining), 6):
            batch = remaining[start:start + 6]
            try:
                raw = await text_judge.complete(_slide_prompt(batch, outline, False))
                if _merge_model_slides(scored, parse_json_object(raw), ("content", "coherence"), "text"):
                    mode = "vision+text" if mode == "vision" else ("text" if mode == "rule" else mode)
            except Exception as exc:  # noqa: BLE001
                errors.append(short(f"文本评审失败：{exc}", 200))
                break
    if mode != "rule":
        for dimension in ("content", "design"):
            sources = {item[dimension]["source"] for item in scored}
            if sources - {"rule"}:
                deck[dimension] = {
                    "score": _mean([item[dimension]["score"] for item in scored]),
                    "rationale": short(
                        "；".join(
                            f"第 {item['position']} 页 {item[dimension]['score']} 分：{item[dimension]['rationale']}"
                            for item in sorted(scored, key=lambda value: value[dimension]["score"])[:2]
                        ), 120,
                    ),
                    "suggestions": _suggestions(scored, dimension),
                    "source": "vision" if "vision" in sources else "text",
                }
        judge = text_judge or vision_judge
        if judge:
            try:
                coherence = await _model_deck_coherence(judge, slides)
                if coherence:
                    blended = round(0.5 * coherence["score"] + 0.5 * _mean(
                        [item["coherence"]["score"] for item in scored]), 1)
                    deck["coherence"] = {**coherence, "score": blended,
                                         "suggestions": coherence["suggestions"] or _suggestions(scored, "coherence")}
            except Exception as exc:  # noqa: BLE001
                errors.append(short(f"全稿连贯性评审失败：{exc}", 200))
    overall = _mean([deck[dimension]["score"] for dimension in DIMENSIONS])
    return {
        "version": VERSION,
        "mode": mode,
        "model": (vision_judge.model_id if mode.startswith("vision") and vision_judge else
                  text_judge.model_id if mode == "text" and text_judge else None),
        "scale": [1, 5],
        "overall": overall,
        "deck": deck,
        "slides": scored,
        "lowestSlides": [
            item["position"] for item in sorted(
                scored, key=lambda value: sum(value[dimension]["score"] for dimension in DIMENSIONS)
            )[:3]
        ],
        "errors": errors,
    }
