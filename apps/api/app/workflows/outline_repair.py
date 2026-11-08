"""Deterministic outline repair and source-anchor helpers used by planning and generation."""

import copy
import re

from app.intelligence.numeric_claims import strict_numbers

OUTLINE_AUTO_REPAIR_CODES = {
    "placeholder-slide-title",
    "duplicate-slide-title",
    "duplicate-slide-content",
    "repeated-message",
    "empty-agenda",
    "empty-content-slide",
    "excessive-source-window",
    "weak-source-grounding",
    "broken-source-ref",
    "unsupported-metric",
}


def repair_outline_from_builtin(
    plan: dict, builtin: dict, sources: list[dict], *, force_all: bool = False
) -> dict:
    """Replace unsafe model pages with their deterministic, source-bound contracts."""
    from app.validation.quality import validate_deck

    before = validate_deck(plan.get("slides", []), sources)
    repair_positions = {
        int(issue.get("slide") or 0)
        for issue in before.get("issues", [])
        if issue.get("code") in OUTLINE_AUTO_REPAIR_CODES and int(issue.get("slide") or 0) > 0
    }
    if force_all:
        repair_positions = {
            int(slide.get("position") or index + 1)
            for index, slide in enumerate(plan.get("slides", []))
        }
    # Agenda structure is owned by the deterministic page contract.  A model
    # may improve wording, but it cannot silently drop one of the planned
    # phases and leave a shortened or incomplete defense route.
    for index, slide in enumerate(plan.get("slides", [])):
        position = int(slide.get("position") or index + 1)
        baseline = next((item for item in builtin.get("slides", []) if int(item.get("position") or 0) == position), None)
        if not baseline:
            continue
        current_items = [item for item in slide.get("content", {}).get("bullets", []) if str(item).strip()]
        baseline_items = [item for item in baseline.get("content", {}).get("bullets", []) if str(item).strip()]
        if slide.get("role") == "agenda" and len(current_items) < len(baseline_items):
            repair_positions.add(position)
        baseline_structured = [
            str(item) for item in baseline_items
            if str(item).count("：") >= 2 and strict_numbers(str(item))
        ]
        current_structured = [
            str(item) for item in current_items
            if str(item).count("：") >= 2 and strict_numbers(str(item))
        ]
        if baseline.get("role") in {"data", "comparison"} and len(baseline_structured) >= 2 and current_structured != baseline_structured:
            repair_positions.add(position)
    builtin_by_position = {
        int(slide.get("position") or 0): slide for slide in builtin.get("slides", [])
    }
    repaired = []
    for index, slide in enumerate(list(plan.get("slides", []))):
        position = int(slide.get("position") or index + 1)
        replacement = builtin_by_position.get(position)
        if position not in repair_positions or not replacement:
            continue
        recovered = copy.deepcopy(replacement)
        recovered["id"] = slide.get("id") or recovered["id"]
        for key in ("designSystem", "personalizationBaseline"):
            if slide.get(key):
                recovered[key] = copy.deepcopy(slide[key])
        recovered["generationState"] = {"status": "pending", "reason": "automatic-content-repair"}
        plan["slides"][index] = recovered
        repaired.append(position)
    after = validate_deck(plan.get("slides", []), sources)
    return {
        "repairedPositions": repaired,
        "beforeBlockingErrors": before.get("blockingErrors", 0),
        "afterBlockingErrors": after.get("blockingErrors", 0),
        "remainingBlockingCodes": list(dict.fromkeys(
            issue.get("code") for issue in after.get("issues", []) if issue.get("severity") == "error"
        )),
        "sourceChanged": force_all,
    }


def academic_result_topics(sources: list[dict], limit: int = 4) -> list[str]:
    """Discover major experiment/result subsections from a long academic document."""
    discovered: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for source in sources:
        for section in source.get("sections", []):
            text = f"{section.get('title', '')}\n{section.get('text', '')}"
            for match in re.finditer(
                r"(?m)^\s*(\d+)\.(\d+)(?!\.)\s+([^\n]{3,54})", text
            ):
                chapter, subsection, heading = int(match.group(1)), int(match.group(2)), match.group(3)
                heading = re.sub(r"\s+", " ", heading).strip(" ：:。.")
                if not re.search(r"实验|结果|评估|性能|质量|效率|消融", heading):
                    continue
                if re.search(r"设置|环境|数据集|评价指标", heading) and not re.search(r"结果|性能|质量|效率", heading):
                    continue
                key = re.sub(r"\s+", "", heading)
                if key in seen:
                    continue
                seen.add(key)
                discovered.append((chapter, subsection, heading))
    if not discovered:
        return []
    latest_chapter = max(item[0] for item in discovered)
    topics = [heading for chapter, _, heading in discovered if chapter == latest_chapter]
    non_ablation = [heading for heading in topics if "消融" not in heading]
    ablation = next((heading for heading in topics if "消融" in heading), "")
    selected = non_ablation[:limit]
    if ablation and len(selected) >= 2 and not any("消融" in heading for heading in selected):
        selected[1] = f"{selected[1]}与消融分析"
    return selected[:limit]


def best_source_refs(text: str, sources: list[dict], limit: int = 2) -> list[dict]:
    terms = {
        token.lower()
        for token in re.findall(r"[A-Za-z][\w-]{2,}|[\u4e00-\u9fff]{2,8}", text)
    }
    numbers = {value.replace(",", "") for value in re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", text)}
    cited_sections = {value.upper() for value in re.findall(r"\bS\d+\b", text, flags=re.IGNORECASE)}
    query_cjk = "".join(re.findall(r"[\u4e00-\u9fff]", text))
    cjk_bigrams = {query_cjk[index:index + 2] for index in range(max(0, len(query_cjk) - 1))}
    ranked = []
    for source in sources:
        for section in source.get("sections", []):
            haystack = f"{section.get('title', '')} {section.get('text', '')}".lower()
            score = sum(1 + min(haystack.count(term), 3) for term in terms if term in haystack)
            haystack_numbers = {value.replace(",", "") for value in re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", haystack)}
            score += 8 * len(numbers & haystack_numbers)
            score += sum(0.75 for token in cjk_bigrams if token in haystack)
            if str(section.get("id", "")).upper() in cited_sections:
                score += 20
            if score:
                ranked.append((score, {
                    "document": source["name"], "section": section["id"],
                    "page": section.get("page"),
                }))
    ranked.sort(key=lambda item: -item[0])
    return [item[1] for item in ranked[:limit]]


def academic_result_source_refs(responsibility: str, sources: list[dict]) -> list[dict]:
    normalized_responsibility = re.sub(r"\s+", "", responsibility)
    anchor_patterns = [
        (r"应用分类", r"5\.2应用分类实验结果分析"),
        (r"RAG.*检索", r"5\.3\.1整体检索性能对比分析"),
        (r"多任务合规|合规分析结果", r"5\.4多任务合规分析实验结果分析"),
        (r"系统性能|生成质量|系统效率", r"5\.5合规分析报告质量与系统效率分析"),
    ]
    marker_pattern = next(
        (marker for responsibility_pattern, marker in anchor_patterns
         if re.search(responsibility_pattern, normalized_responsibility, flags=re.IGNORECASE)),
        None,
    )
    if not marker_pattern:
        return []
    anchors: list[tuple[int, dict, int]] = []
    for source in sources:
        sections = source.get("sections", [])
        for index, section in enumerate(sections):
            haystack = re.sub(r"\s+", "", f"{section.get('title', '')}{section.get('text', '')}")
            if re.search(marker_pattern, haystack, flags=re.IGNORECASE):
                anchors.append((section.get("page") or index, source, index))
    if not anchors:
        return []
    _, source, start = max(anchors, key=lambda item: item[0])
    return [
        {"document": source["name"], "section": section["id"], "page": section.get("page")}
        for section in source.get("sections", [])[start:start + 4]
    ]

