import re
from pathlib import Path


FACTUAL_ROLES = {"method", "architecture", "evidence", "data", "comparison", "insight", "content"}
TERM_STOPWORDS = {"分析", "研究", "任务", "系统", "方法", "结果", "设计", "实验", "实现", "总体", "处理", "应用"}
PURPOSE_CAPTION_HINTS = [
    (re.compile(r"多源信息采集|应用分类与隐私政策处理"), re.compile(r"多源|采集|数据源|爬虫|应用分类")),
    (re.compile(r"RAG|检索|消融"), re.compile(r"RAG|检索|查询|召回|MRR|Hit@", re.IGNORECASE)),
    (re.compile(r"系统性能|生成质量|成本|效率"), re.compile(r"性能|耗时|时间|成本|效率|质量")),
    (re.compile(r"实验环境|数据集|评价指标|基线"), re.compile(r"实验环境|数据集|数据来源|评价指标|基线")),
]
ROLE_FIGURE_KINDS = {
    "method": {"diagram", "prompt"},
    "architecture": {"diagram"},
    "evidence": {"diagram", "figure"},
    "data": {"chart"},
    "comparison": {"chart"},
    "insight": {"chart", "figure"},
    "content": {"diagram", "figure", "prompt"},
}


def _terms(value: str) -> set[str]:
    text = str(value or "").lower()
    terms = set(re.findall(r"[a-z][a-z0-9@_-]{2,}", text))
    for sequence in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        terms.update(sequence[index:index + 2] for index in range(len(sequence) - 1))
        terms.update(sequence[index:index + 4] for index in range(max(0, len(sequence) - 3)))
    return terms - TERM_STOPWORDS


def _slide_query(slide: dict) -> str:
    content = slide.get("content", {})
    return " ".join([
        str(content.get("title", "")),
        str(slide.get("message", "")),
        str(slide.get("purpose", "")),
        *[str(item) for item in content.get("bullets", [])],
    ])


def _figure_score(slide: dict, figure: dict) -> float:
    refs = slide.get("sourceRefs", [])
    ref_pages = [int(ref["page"]) for ref in refs if ref.get("page") is not None]
    ref_documents = {str(ref.get("document", "")) for ref in refs}
    page = int(figure.get("page") or 0)
    visual_intent = slide.get("visualIntent", {})
    expected_kinds = set(visual_intent.get("expectedFigureKinds", []))
    forbidden_kinds = set(visual_intent.get("forbiddenFigureKinds", []))
    figure_kind = str(figure.get("kind", "figure"))
    # 页面职责先于关键词相似度：实验结果页不能使用 Prompt 截图，
    # 方法页也不能拿一个结果柱状图冒充流程图。
    if figure_kind in forbidden_kinds:
        return -100
    if expected_kinds and figure_kind not in expected_kinds:
        return -100
    score = 0.0
    if figure.get("document") in ref_documents:
        score += 5
    if figure.get("section") and any(
        ref.get("document") == figure.get("document") and ref.get("section") == figure["section"]
        for ref in refs
    ):
        score += 20
    if ref_pages:
        distance = min(abs(page - ref_page) for ref_page in ref_pages)
        if distance > 3:
            return -100
        score += 14 if distance == 0 else 8 if distance == 1 else 4 if distance <= 3 else 0
    caption_terms = _terms(f"{figure.get('caption', '')} {figure.get('kind', '')}")
    overlap = len(_terms(_slide_query(slide)) & caption_terms)
    score += min(35, 5 * overlap)
    expected = ROLE_FIGURE_KINDS.get(str(slide.get("role")), set())
    if figure_kind in expected:
        score += 6
    elif expected:
        return -100
    purpose = str(slide.get("purpose", ""))
    caption = str(figure.get("caption", ""))
    slide_query = _slide_query(slide)
    task_query = f"{slide.get('content', {}).get('title', '')} {purpose}"
    if re.search(r"问题背景|研究现状|研究缺口|技术缺口|现有研究|现有方法|研究目标|任务拆解|主要贡献|创新点", purpose):
        return -100
    hint_matched = False
    for purpose_pattern, caption_pattern in PURPOSE_CAPTION_HINTS:
        if purpose_pattern.search(purpose):
            if caption_pattern.search(caption):
                score += 12
                hint_matched = True
            else:
                score -= 45
    if re.search(r"多任务合规分析结果|结果与案例", purpose):
        if re.search(r"合规性分类|证据支撑率|结构完整性", caption):
            score += 14
        elif re.search(r"标签分布", caption):
            score -= 18
    if re.search(r"实验结果|实验验证|基线对比|系统效率|生成质量", purpose):
        if figure_kind != "chart":
            return -100
    if re.search(r"总体框架|技术路线|系统架构|构建流程|运行链路|模块协作", purpose):
        if figure_kind != "diagram":
            return -100
    # 对论文中常见的同主题多张图执行任务级匹配。宁可回退到可编辑图表，
    # 也不把标签分布、Prompt 或另一个任务的图放到当前结论页。
    if re.search(r"总体框架|整体架构", task_query):
        if not re.search(r"总体研究框架|总体框架|系统架构", caption):
            return -100
    if re.search(r"知识库|向量库|规范映射", task_query):
        if not re.search(r"国标.*(?:向量库|知识库)|向量库.*流程", caption):
            return -100
    if re.search(r"隐私政策.*权限.*一致性.*(?:流程|机制|方法)", task_query):
        if not re.search(r"隐私政策.*权限.*一致性.*(?:流程|分析)", caption):
            return -100
    if re.search(r"国标.*隐私政策.*(?:流程|机制|方法|合规性分析)", task_query):
        if not re.search(r"国标.*隐私政策.*(?:流程|合规)", caption):
            return -100
    if re.search(r"系统.*架构|模块协作|工程实现", task_query):
        if not re.search(r"总体研究框架|系统架构|模块", caption):
            return -100
    if re.search(r"实验结果|效果提升|性能对比|消融", slide_query) and re.search(r"标签分布", caption):
        return -100
    if re.search(r"RAG|检索", task_query, re.I) and not re.search(r"系统.*架构|总体框架|整体架构", task_query):
        if not re.search(r"RAG|检索|意图约束", caption, re.I):
            return -100
    task_rules = [
        (r"隐私政策.*权限.*一致性", r"隐私政策.*权限.*一致性"),
        (r"国标.*权限", r"国标.*权限"),
        (r"国标.*隐私政策", r"国标.*隐私政策"),
        (r"应用分类|应用类别", r"应用分类|应用类别"),
    ]
    for query_pattern, caption_pattern in task_rules:
        if re.search(query_pattern, task_query) and not re.search(caption_pattern, caption):
            return -100
    if caption and overlap == 0 and not hint_matched:
        return -100
    if figure.get("caption"):
        score += 2
    return score


def _figure_ref(source: dict, figure: dict) -> dict:
    page = int(figure.get("page") or 0)
    sections = source.get("sections", [])
    section = next((item for item in sections if item.get("id") == figure.get("section")), None)
    if section is None and page:
        section = next((item for item in sections if item.get("page") == page), None)
    return {
        "document": source["name"],
        "section": section.get("id") if section else f"S{page:03d}",
        "page": page or None,
    }


def bind_source_figures(plan: dict, sources: list[dict]) -> int:
    """Bind extracted source figures to the most relevant factual slide.

    The binding stays provenance-first: a figure must have a real local asset,
    is used at most once, and keeps its source page and caption in the deck spec.
    """
    candidates: list[tuple[dict, dict]] = []
    for source in sources:
        for figure in source.get("figures", []):
            path = figure.get("path")
            if path and Path(path).is_file():
                candidates.append((source, figure))
    if not candidates:
        return 0

    for slide in plan.get("slides", []):
        # Source references may carry metrics that live on the page next to a bound figure.
        # Keep those evidence references when refreshing visual bindings; dropping them can
        # make a true metric look unsupported during the final numeric safety check.
        slide["assetBindings"] = [
            item for item in slide.get("assetBindings", []) if item.get("type") != "source-image"
        ]
        if slide.get("visualIntent", {}).get("primaryVisual") == "source-image":
            slide["visualIntent"].pop("primaryVisual", None)
    used: set[str] = set()
    bound = 0
    for slide in plan.get("slides", []):
        role = str(slide.get("role", "content"))
        if role not in FACTUAL_ROLES:
            continue
        ranked = sorted(
            (
                (_figure_score(slide, figure), source, figure)
                for source, figure in candidates
                if str(figure.get("path")) not in used
            ),
            key=lambda item: (-item[0], int(item[2].get("page") or 0)),
        )
        if not ranked or ranked[0][0] < 18:
            continue
        _, source, figure = ranked[0]
        path = str(figure["path"])
        used.add(path)
        binding = {
            "type": "source-image",
            "path": path,
            "alt": figure.get("caption") or slide.get("content", {}).get("title", "原文图表"),
            "provenance": figure.get("provenance") or f"{source['name']} · 第 {figure.get('page')} 页",
            "caption": figure.get("caption", ""),
            "sourceFigureId": figure.get("id"),
            "sourcePage": figure.get("page"),
            "kind": figure.get("kind", "figure"),
            "width": figure.get("width"),
            "height": figure.get("height"),
            "fitMode": "contain",
        }
        slide["assetBindings"] = [
            item for item in slide.get("assetBindings", [])
            if item.get("type") != "source-image"
        ] + [binding]
        ref = _figure_ref(source, figure)
        current_refs = list(slide.get("sourceRefs", []))
        if ref not in current_refs:
            current_refs.append(ref)
        slide["sourceRefs"] = current_refs
        visual = dict(slide.get("visualIntent", {}))
        visual.update({
            "primaryVisual": "source-image",
            "figureKind": figure.get("kind", "figure"),
            "figureCaption": figure.get("caption", ""),
            "evidencePriority": "source-first",
        })
        if figure.get("kind") == "chart":
            visual["archetypeCandidates"] = ["figure-focus", "figure-analysis", "image-story"]
        elif figure.get("kind") == "prompt":
            visual["archetypeCandidates"] = ["figure-analysis", "figure-wide", "image-story"]
        else:
            visual["archetypeCandidates"] = ["figure-wide", "figure-analysis", "image-story"]
        slide["visualIntent"] = visual
        bound += 1
    return bound


def normalize_visual_intent(plan: dict) -> None:
    """Match the visual form to evidence while keeping explanatory pages scannable."""
    for slide in plan.get("slides", []):
        role = str(slide.get("role", "content"))
        visual = dict(slide.get("visualIntent", {}))
        page_text = " ".join([
            str(slide.get("purpose", "")),
            str(slide.get("content", {}).get("title", "")),
            str(slide.get("message", "")),
        ])
        metric_lines = sum(
            bool(re.search(r"\d+(?:\.\d+)?\s*(?:%|倍|万|亿|ms|秒|分|分钟|小时|MB|GB)?", str(item)))
            for item in slide.get("content", {}).get("bullets", [])
        )
        if any(item.get("type") == "source-image" for item in slide.get("assetBindings", [])):
            visual["primaryVisual"] = "source-image"
        elif role == "data":
            visual["primaryVisual"] = "chart"
        elif role == "comparison" and metric_lines >= 2:
            visual["primaryVisual"] = "chart"
        elif role == "comparison":
            visual["primaryVisual"] = "cards"
            visual["archetypeCandidates"] = ["two-column", "cards", "contrast"]
        elif metric_lines >= 2 and re.search(r"实验|结果|验证|评估|性能|指标|对比|增长|下降", page_text):
            visual["primaryVisual"] = "chart"
            visual["archetypeCandidates"] = ["chart-focus", "comparison-bars", "table-highlight"]
        elif visual.get("contentRelation") == "explanation" and role in {"background", "method", "architecture", "evidence", "content"}:
            if len(slide.get("content", {}).get("bullets", [])) >= 3:
                visual["primaryVisual"] = "cards"
                visual["archetypeCandidates"] = list(dict.fromkeys([
                    "cards", "evidence-brief", *visual.get("archetypeCandidates", [])
                ]))[:5]
                layout = dict(slide.get("layoutPlan") or {})
                layout["compositionMode"] = "cards"
                layout["recommendedVariant"] = "cards"
                layout["candidateOrder"] = list(dict.fromkeys([
                    "cards", *layout.get("candidateOrder", []), "evidence-brief"
                ]))[:5]
                slide["layoutPlan"] = layout
                if (
                    visual.get("variantSelectionSource") == "critic"
                    and set(visual.get("criticIssues") or []) == {"repetition"}
                    and visual.get("selectedVariant") != "cards"
                ):
                    visual.pop("selectedVariant", None)
                    visual.pop("variantSelectionSource", None)
                    visual.pop("criticIssues", None)
            else:
                visual["primaryVisual"] = "typography"
        elif role in {"method", "architecture", "evidence"}:
            visual["primaryVisual"] = "diagram"
        elif role == "section":
            visual["primaryVisual"] = "typography"
        slide["visualIntent"] = visual
