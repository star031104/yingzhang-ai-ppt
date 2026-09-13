import json
import re
from collections import Counter
from pathlib import Path

from app.validation.render_safety import hard_render_failures, safe_render_candidate
from app.validation.visual_maturity import variant_family

ISSUE_CODES = {
    "overflow",
    "small-text",
    "weak-hierarchy",
    "imbalance",
    "repetition",
    "low-contrast",
    "awkward-wrap",
    "weak-semantic-fit",
}


def _has_multi_series_rows(slide: dict) -> bool:
    """Return true when several rows each carry multiple named numeric fields.

    A metric wall only surfaces the first number from every row. For sales or
    cash-flow projections that would hide the year-over-year story, so those
    pages should keep a chart or table unless that rendering is unsafe.
    """
    structured_rows = 0
    for bullet in (slide.get("content") or {}).get("bullets") or []:
        text = str(bullet or "").strip()
        rest = re.sub(r"^[^：:；;]{1,40}[：:]", "", text, count=1)
        fields = re.findall(
            r"(?:^|[；;])\s*[^：:；;]{1,30}[：:]\s*[-+−]?(?:\d+(?:\.\d+)?|\.\d+)",
            rest,
        )
        if len(fields) >= 2:
            structured_rows += 1
    return structured_rows >= 2


def load_candidate_snapshots(render_root: Path, slides: list[dict]) -> list[dict]:
    snapshots = []
    for slide in slides:
        root = render_root / "slides" / str(slide["position"])
        current_path = root / "current.json"
        if not current_path.is_file():
            continue
        current = json.loads(current_path.read_text(encoding="utf-8"))
        candidates = []
        for score_path in sorted(root.glob("*.score.json")):
            variant = score_path.name.removesuffix(".score.json")
            score = json.loads(score_path.read_text(encoding="utf-8"))
            candidates.append({"variant": variant, "score": score})
        snapshots.append({
            "slideId": slide["id"],
            "position": slide["position"],
            "title": slide.get("content", {}).get("title", ""),
            "selectedVariant": current.get("variant"),
            "selectionSource": slide.get("visualIntent", {}).get("variantSelectionSource", "auto"),
            "imagePath": str(root / f"{current.get('variant')}.png"),
            "candidates": candidates,
        })
    return snapshots


def deterministic_review(snapshots: list[dict]) -> list[dict]:
    counts = Counter(variant_family(item["selectedVariant"]) for item in snapshots)
    reviews = []
    for item in snapshots:
        current = next(
            (candidate for candidate in item["candidates"] if candidate["variant"] == item["selectedVariant"]),
            None,
        )
        if not current:
            continue
        score = current["score"]
        issues = []
        if hard_render_failures(score):
            issues.append("overflow")
        if score.get("tooSmall", 0) or score.get("readability", 100) < 78:
            issues.append("small-text")
        if score.get("hierarchy", 100) < 78:
            issues.append("weak-hierarchy")
        if score.get("whitespace", 100) < 72:
            issues.append("imbalance")
        if score.get("semanticFit", 100) < 80 or score.get("contentFit", 100) < 70:
            issues.append("weak-semantic-fit")
        selected_family = variant_family(item["selectedVariant"])
        if counts[selected_family] > 3:
            issues.append("repetition")
        alternatives = sorted(
            (
                candidate for candidate in item["candidates"]
                if candidate["variant"] != item["selectedVariant"]
            ),
            key=lambda candidate: (
                variant_family(candidate["variant"]) != selected_family,
                min(candidate["score"].get("geometry", 0), candidate["score"].get("readability", 0)),
                candidate["score"].get("contentFit", 0),
                candidate["score"].get("overall", 0),
            ),
            reverse=True,
        )
        recommended = None
        layout_issues = [issue for issue in issues if issue != "repetition"]
        for candidate in alternatives:
            candidate_score = candidate["score"]
            minimum_overall = score.get("overall", 0) - 5 if layout_issues else score.get("overall", 0)
            if (
                safe_render_candidate(candidate_score)
                and candidate_score.get("overall", 0) >= minimum_overall
                and (issues or counts[selected_family] > 3)
            ):
                recommended = candidate["variant"]
                break
        reviews.append({
            "position": item["position"],
            "issues": list(dict.fromkeys(issues)),
            "recommendedVariant": recommended,
            "confidence": 0.82 if recommended else 0.6,
            "reason": "基于几何、可读性、语义匹配与全稿节奏的确定性检查",
            "reviewer": "deterministic",
        })
    return reviews


def merge_vision_reviews(base: list[dict], vision: list[dict]) -> list[dict]:
    merged = {item["position"]: dict(item) for item in base}
    for item in vision:
        try:
            position = int(item.get("position"))
        except (TypeError, ValueError):
            continue
        if position not in merged:
            continue
        issues = [str(value) for value in item.get("issues", []) if str(value) in ISSUE_CODES]
        recommended = str(item.get("recommendedVariant") or "").strip() or None
        confidence = max(0.0, min(1.0, float(item.get("confidence", 0))))
        merged[position].update({
            "issues": issues or merged[position]["issues"],
            "recommendedVariant": recommended or merged[position]["recommendedVariant"],
            "confidence": confidence,
            "reason": str(item.get("reason") or "视觉模型基于渲染截图建议替代版式")[:300],
            "reviewer": "vision-model",
        })
    return [merged[position] for position in sorted(merged)]


def apply_safe_repairs(slides: list[dict], snapshots: list[dict], reviews: list[dict]) -> list[dict]:
    data_variants = {"chart-focus", "table-highlight", "comparison-matrix", "metric-wall"}
    snapshot_map = {item["position"]: item for item in snapshots}
    review_map = {item["position"]: item for item in reviews}
    applied = []
    for slide in slides:
        position = slide["position"]
        snapshot, review = snapshot_map.get(position), review_map.get(position)
        if not snapshot or not review or snapshot.get("selectionSource") in {"user", "critic"}:
            continue
        recommended = review.get("recommendedVariant")
        if not recommended or review.get("confidence", 0) < 0.72 or not review.get("issues"):
            continue
        current = next(
            (item for item in snapshot["candidates"] if item["variant"] == snapshot["selectedVariant"]),
            None,
        )
        target = next(
            (item for item in snapshot["candidates"] if item["variant"] == recommended),
            None,
        )
        if not current or not target:
            continue
        if (
            set(review.get("issues") or []) == {"repetition"}
            and snapshot["selectedVariant"] == (slide.get("layoutPlan") or {}).get("recommendedVariant")
        ):
            # The deck planner already balances the full sequence. Do not undo
            # an intentional card rhythm solely because that family appears
            # several times across a long deck.
            continue
        if (
            snapshot["selectedVariant"] == "chart-focus"
            and recommended == "metric-wall"
            and _has_multi_series_rows(slide)
        ):
            # Multi-year tables need the comparison axis. Metric cards would
            # retain only one value per row and conceal the trend.
            continue
        if recommended == "content-list" and safe_render_candidate(current["score"]):
            continue
        target_score = target["score"]
        primary_visual = str((slide.get("visualIntent") or {}).get("primaryVisual", ""))
        if (
            snapshot["selectedVariant"] in data_variants
            or primary_visual in {"chart", "table", "data"}
        ) and recommended not in data_variants:
            continue
        if (
            not safe_render_candidate(target_score)
            or target_score.get("overall", 0) < current["score"].get("overall", 0) - 8
        ):
            continue
        visual = dict(slide.get("visualIntent") or {})
        visual["selectedVariant"] = recommended
        visual["variantSelectionSource"] = "critic"
        visual["criticIssues"] = review["issues"]
        slide["visualIntent"] = visual
        review["applied"] = True
        applied.append({"position": position, "from": snapshot["selectedVariant"], "to": recommended})
    return applied


def vision_prompt(batch: list[dict]) -> str:
    compact = [
        {
            "position": item["position"],
            "title": item["title"],
            "selectedVariant": item["selectedVariant"],
            "allowedVariants": [candidate["variant"] for candidate in item["candidates"]],
        }
        for item in batch
    ]
    return f"""你是专业演示稿视觉评审。按顺序检查附带的页面截图，只评估：溢出、字号过小、层级弱、画面失衡、连续版式重复、对比度低、断行别扭、视觉语义不匹配。
不得改写文案、数字或事实；只能从每页 allowedVariants 中选择替代版式。若当前版式合格，recommendedVariant 返回 null。
只返回 JSON：{{"slides":[{{"position":1,"issues":["awkward-wrap"],"recommendedVariant":"minimal-cover","confidence":0.86,"reason":"简短原因"}}]}}
页面信息：{json.dumps(compact, ensure_ascii=False)}
""".strip()
