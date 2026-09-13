import re

from app.validation.visual_maturity import assess_visual_maturity

NUMBER_RE = re.compile(
    r"[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*"
    r"(?:%|个百分点|倍|万|亿|ms|毫秒|s|秒|分钟|分|小时|KB|MB|GB|TB|条|个|项|份|人|页)?",
    re.IGNORECASE,
)


def _numbers(text: str) -> set[str]:
    cleaned = re.sub(r"\b(?:S|F|M|SRC)\s*\d+\b", "", text or "", flags=re.IGNORECASE)
    cleaned = re.sub(r"(?:Hit|Top|Recall|nDCG)@?\d+", "", cleaned, flags=re.IGNORECASE)
    return {
        re.sub(r"[\s,]", "", match.group()).lower().replace("−", "-").lstrip("+")
        for match in NUMBER_RE.finditer(cleaned)
    }


def _slide_text(slide: dict) -> str:
    content = slide.get("content", {})
    title = re.sub(
        r"^\s*(?:第\s*\d+\s*[章节部分页]|(?:方案|方法)\s*\d+|\d+(?:\.\d+)*[、.\s])\s*",
        "", str(content.get("title", "")),
    )
    return " ".join([
        title,
        str(slide.get("message", "")),
        *[str(item) for item in content.get("bullets", [])],
    ])


ISSUE_GUIDANCE = {
    "render-incomplete": ("完成页面渲染", "生成全部页面后重新检查，尚未渲染的页面不能判定为可交付。"),
    "render-stale": ("更新页面预览", "这些页面的内容、版式或素材已修改。重新生成后再检查，旧预览不能作为当前成稿的质量依据。"),
    "render-error": ("修复页面显示", "检查文字裁切、画布越界、缺失图片和遗漏内容，再选择安全候选或修改页面。"),
    "density": ("降低页面密度", "删减次要信息，或把页面拆成两个连续结论。"),
    "high-reading-load": ("降低阅读负担", "把长段落改成 3—4 个短观点，并扩大关键数字。"),
    "long-audience-bullet": ("压缩观众文案", "每个要点只保留一个判断，细节移入演讲者备注。"),
    "duplicate-slide-title": ("消除重复页面", "为重复标题分配不同沟通任务，或合并重复证据。"),
    "duplicate-slide-content": ("重建重复页面", "按每页的资料章节重新生成标题、结论和要点，不能复制同一份正文。"),
    "placeholder-slide-title": ("替换占位标题", "根据本页唯一沟通任务生成有信息量的标题。"),
    "empty-agenda": ("补全答辩逻辑", "用 3—5 个有顺序的阶段说明整套汇报如何推进。"),
    "empty-content-slide": ("补全页面内容", "从本页绑定章节提取结论和必要证据。"),
    "excessive-source-window": ("收窄页面证据", "每页只绑定直接支撑本页判断的少量章节。"),
    "weak-source-grounding": ("重新绑定材料", "页面文案与当前引用章节缺少语义对应，应按资料重写。"),
    "repeated-message": ("强化叙事推进", "相邻页面需要形成因果、递进或取舍关系。"),
    "low-visual-evidence-ratio": ("增加证据型视觉", "优先使用原文图、可编辑图表或真正解释机制的图解。"),
    "low-visual-diversity": ("打破版式重复", "交替使用图表、图解、主张页和原文证据页。"),
    "visible-source-marker": ("清理正文引用标记", "S003 等内部来源编号应放到页脚和演讲者备注。"),
    "long-slide-title": ("缩短页面标题", "标题只表达本页唯一结论，补充解释放到正文。"),
    "weak-chart-encoding": ("补全图表数据", "图表页至少应有两个可比较的数据点或改用主张型版式。"),
    "unsupported-metric": ("修正无来源数字", "只保留能在当前页面引用材料中逐项核对的数字。"),
    "broken-source-ref": ("修复来源链接", "重新绑定存在的文档、章节与页码。"),
    "missing-semantic-coverage": ("补全核心主张", "重要章节虽已上传，但其核心主张尚未被任何页面承载。"),
    "missing-key-evidence": ("补齐答辩关键证据", "每个核心章节应有实质说明，各任务的主要结果指标应有来源且出现在页面中。"),
    "audience-copy-process-leak": ("移除制作流程文案", "页面应只服务观众，不展示工具能力、生成步骤或内部质量口号。"),
    "repetitive-layout-silhouette": ("更换重复构图", "连续页面应交替使用主张、图解、数据、原文证据与行动型构图。"),
    "flat-deck-rhythm": ("重排全稿节奏", "避免相邻页面连续使用同一视觉骨架，让章节推进在构图上可感知。"),
    "low-evidence-visual-coverage": ("增加有效视觉证据", "优先把指标、流程、原文图表或案例素材转成承担解释任务的主视觉。"),
    "shallow-candidate-diversity": ("提高候选差异", "每页候选应来自不同构图家族，而不是只改变装饰细节。"),
}


def _semantic_tokens(value: str) -> set[str]:
    text = re.sub(r"\s+", "", str(value or "").lower())
    tokens = set(re.findall(r"[a-z][a-z0-9@_-]{2,}|\d+(?:\.\d+)?%?", text))
    for block in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        tokens.update(block[index:index + 2] for index in range(len(block) - 1))
    return tokens


def _section_claims(section: dict) -> list[str]:
    title = str(section.get("title", "")).strip()
    sentences = [
        re.sub(r"\s+", " ", value).strip()
        for value in re.split(r"[\n。！？；;]+", str(section.get("text", "")))
        if 12 <= len(re.sub(r"\s+", "", value)) <= 240
    ]
    ranked = sorted(
        sentences,
        key=lambda value: (
            bool(re.search(r"\d|Accuracy|F1|结果|表明|因此|建议|提升|降低|实现", value, re.IGNORECASE)),
            len(value),
        ),
        reverse=True,
    )
    return list(dict.fromkeys([title, *ranked[:2]]))[:3]


def summary_evidence_coverage(slides: list[dict], sources: list[dict]) -> dict | None:
    """Long numbered reports: require chapter coverage and primary result tables.

    Full subsection coverage remains separately visible. A short presentation
    must still contain sourced material from every chapter and every task's
    headline metric; merely attaching a citation cannot satisfy this check.
    """
    body = [s for s in slides if s.get("role") not in {"cover", "agenda", "section", "questions"}]
    if not body:
        return None
    chapters = {}
    eligible_sources = []
    for source in sources:
        groups = {}
        for section in source.get("sections", []):
            match = re.match(r"^([1-9]\d?)\.\d+(?:\.\d+)*\s", section.get("title", ""))
            if match:
                groups.setdefault(match.group(1), []).append(section)
        if len(groups) < 3 or len(source.get("sections", [])) <= len(body) * 3:
            return None
        eligible_sources.append(source)
        for number, sections in groups.items():
            chapters[(source["name"], number)] = sections
    if not chapters:
        return None
    audience = []
    for slide in body:
        text = " ".join([slide.get("content", {}).get("title", ""), slide.get("message", ""), *slide.get("content", {}).get("bullets", [])])
        audience.append((text, {(r.get("document"), r.get("section")) for r in slide.get("sourceRefs", [])}))
    missing_chapters = []
    for (document, number), sections in chapters.items():
        covered = any((document, section["id"]) in refs and any(
            len(_semantic_tokens(claim) & _semantic_tokens(text)) / max(1, len(_semantic_tokens(claim))) >= 0.18
            for claim in _section_claims(section)[1:])
            for section in sections for text, refs in audience)
        if not covered:
            missing_chapters.append({"document": document, "chapter": number})
    missing_tables = []
    primary_tables = 0
    for source in eligible_sources:
        for table in source.get("tables", []):
            rows = table.get("rows", [])
            # Two-column metric/value tables represent separate task outcomes.
            # Wider breakdowns remain part of the detailed coverage report.
            if len(rows) < 2 or len(rows[0]) != 2:
                continue
            row = next((r for r in rows[1:] if len(r)==2 and re.fullmatch(r"\d+(?:\.\d+)?%?", str(r[1]).strip())), None)
            if not row:
                continue
            primary_tables += 1
            value = str(row[1]).strip()
            variants = {value, value.rstrip('0').rstrip('.') if '.' in value else value}
            if re.fullmatch(r"0\.\d+", value):
                variants.add(f"{float(value)*100:.6f}".rstrip('0').rstrip('.') + '%')
            label = str(row[0])
            labels = {label.lower()}
            if label.lower() == "accuracy":
                labels.update({"准确率", "准确度"})
            covered = any((source["name"], table.get("section")) in refs
                          and any(v in _numbers(text) for v in variants)
                          and any(label in text.lower() for label in labels)
                          for text, refs in audience)
            if not covered:
                missing_tables.append({"document": source["name"], "section": table.get("section"), "caption": table.get("caption", ""), "metric": label, "value": value})
    return {"mode": "long-report-summary", "requiredChapters": len(chapters), "requiredResultTables": primary_tables,
            "missingChapters": missing_chapters, "missingResultTables": missing_tables,
            "passed": not missing_chapters and not missing_tables}


def semantic_completeness(slides: list[dict], sources: list[dict]) -> dict:
    if any(source.get("documentProfile", {}).get("presentationMode") == "business-plan" for source in sources):
        topics = [
            ("项目机会", r"项目介绍|项目背景|应用前景"),
            ("市场分析", r"市场分析|商机分析|行业分析"),
            ("产品与技术", r"产品概况|产品服务|关键技术|架构设计"),
            ("营销与竞争", r"市场营销|竞争环境|竞品分析"),
            ("团队执行", r"创业团队|团队简介|团队成员|公司管理|组织架构"),
            ("财务预测", r"财务预测|现金流量|资产负债|销售预测"),
            ("资本与资金", r"资本结构|资金分配|投资者需求"),
            ("风险应对", r"风险分析|风险对冲|风险概述|应对措施"),
        ]
        referenced = {
            (str(ref.get("document", "")), str(ref.get("section", "")))
            for slide in slides if slide.get("role") not in {"cover", "agenda", "section", "questions"}
            for ref in slide.get("sourceRefs", [])
        }
        required_topics = []
        missing = []
        for label, pattern in topics:
            matches = [
                (source.get("name", ""), section.get("id", ""))
                for source in sources for section in source.get("sections", [])
                if re.search(pattern, f"{section.get('title', '')}\n{section.get('text', '')[:300]}")
            ]
            if not matches:
                continue
            required_topics.append(label)
            if not any(match in referenced for match in matches):
                missing.append({"title": label, "role": "business-plan-topic", "importance": 1.0})
        covered = len(required_topics) - len(missing)
        coverage = 1 if not required_topics else covered / len(required_topics)
        return {
            "mode": "business-plan-summary",
            "requiredSections": len(required_topics),
            "coveredSections": covered,
            "sectionCoverage": round(coverage, 3),
            "requiredClaims": len(required_topics),
            "coveredClaims": covered,
            "claimCoverage": round(coverage, 3),
            "overall": round(coverage, 3),
            "score": round(coverage * 100),
            "missing": missing,
        }
    critical_roles = {"problem", "method", "architecture", "data", "insight", "conclusion"}
    required = []
    for source in sources:
        back_matter = False
        for section in source.get("sections", []):
            text = str(section.get("text", ""))
            role = str(section.get("semanticRole", "content"))
            importance = float(section.get("importance", 0.55 if len(text) >= 120 else 0.35))
            title = str(section.get("title", ""))
            if re.match(r"^(?:参考文献|references\b|附录|appendix\b|致谢)", title.strip(), re.IGNORECASE):
                back_matter = True
            if back_matter or re.search(r"https?://|www\.", title):
                continue
            if len(text.strip()) < 20 or re.fullmatch(r"目录|封面|附录|contents?", title.strip(), re.IGNORECASE):
                continue
            if re.search(r"指导老?师|指导教师", text[:600]) and re.search(r"摘\s*要", text[:800]):
                continue
            if role not in critical_roles and importance < 0.52:
                continue
            required.append({
                "document": source.get("name", ""),
                "section": section.get("id", ""),
                "title": title,
                "role": role,
                "importance": importance,
                "claims": _section_claims(section),
                "_text": text,
            })
    # A PDF section may continue across several pages. Audit the logical section
    # once while retaining every page-specific source reference for claim checks.
    grouped = {}
    for item in required:
        key = (item["document"], item["title"])
        if key not in grouped:
            grouped[key] = {**item, "sectionIds": [item["section"]]}
        else:
            group = grouped[key]
            group["sectionIds"].append(item["section"])
            group["_text"] += "\n" + item["_text"]
            group["importance"] = max(group["importance"], item["importance"])
    required = list(grouped.values())
    for item in required:
        item["claims"] = _section_claims({"title": item["title"], "text": item.pop("_text")})
    slide_text_by_ref: dict[tuple[str, str], list[str]] = {}
    for slide in slides:
        if slide.get("role") in {"cover", "agenda", "section", "questions"}:
            continue
        audience_text = " ".join([
            str(slide.get("content", {}).get("title", "")),
            str(slide.get("message", "")),
            *[str(value) for value in slide.get("content", {}).get("bullets", [])],
        ])
        for ref in slide.get("sourceRefs", []):
            slide_text_by_ref.setdefault(
                (str(ref.get("document", "")), str(ref.get("section", ""))), []
            ).append(audience_text)
    covered_sections = 0
    required_claims = 0
    covered_claims = 0
    missing = []
    for item in required:
        slide_texts = [text for section_id in item["sectionIds"] for text in slide_text_by_ref.get((item["document"], section_id), [])]
        if slide_texts:
            covered_sections += 1
        claim_results = []
        for claim in item["claims"]:
            claim_tokens = _semantic_tokens(claim)
            if not claim_tokens:
                continue
            required_claims += 1
            matched = any(
                len(claim_tokens & _semantic_tokens(slide_text)) / max(1, len(claim_tokens)) >= 0.18
                or bool(_numbers(claim) and _numbers(claim) <= _numbers(slide_text))
                for slide_text in slide_texts
            )
            covered_claims += int(matched)
            claim_results.append(matched)
        if not slide_texts or (claim_results and not any(claim_results)):
            missing.append({
                "document": item["document"],
                "section": item["section"],
                "title": item["title"],
                "role": item["role"],
                "importance": item["importance"],
            })
    section_coverage = 1 if not required else covered_sections / len(required)
    claim_coverage = 1 if not required_claims else covered_claims / required_claims
    overall = section_coverage * 0.45 + claim_coverage * 0.55
    return {
        "requiredSections": len(required),
        "coveredSections": covered_sections,
        "sectionCoverage": round(section_coverage, 3),
        "requiredClaims": required_claims,
        "coveredClaims": covered_claims,
        "claimCoverage": round(claim_coverage, 3),
        "overall": round(overall, 3),
        "score": round(overall * 100),
        "missing": sorted(missing, key=lambda item: item["importance"], reverse=True)[:12],
    }


def build_professional_audit(report: dict, visual_qa: dict | None = None) -> dict:
    """Map internal checks to a stable five-dimension professional delivery rubric."""
    scorecard = report.get("scorecard", {})
    visual_average = (visual_qa or {}).get("average")
    fundamentals = round(sum([
        scorecard.get("structure", 0),
        scorecard.get("readability", 0),
        scorecard.get("coherence", 0),
    ]) / 3)
    accessibility_score = report.get("accessibility", {}).get("score")
    if accessibility_score is not None:
        fundamentals = round(fundamentals * 0.75 + accessibility_score * 0.25)
    rendered_visual = (
        visual_average if visual_average is not None else scorecard.get("visualSemantics", 0)
    )
    maturity_score = report.get("visualMaturity", {}).get("score")
    visual_design = round(
        rendered_visual * 0.58 + maturity_score * 0.42
        if maturity_score is not None
        else rendered_visual
    )
    semantic_score = report.get("semanticCompleteness", {}).get("score")
    completeness = round(
        scorecard.get("structure", 0) * 0.25 + semantic_score * 0.75
        if semantic_score is not None
        else scorecard.get("structure", 0) * 0.35 + scorecard.get("evidence", 0) * 0.65
    )
    correctness = round(scorecard.get("factuality", 0))
    fidelity = round(
        scorecard.get("evidence", 0) * 0.55 + scorecard.get("factuality", 0) * 0.45
    )
    dimensions = {
        "fundamentals": fundamentals,
        "visualDesign": visual_design,
        "completeness": completeness,
        "correctness": correctness,
        "fidelity": fidelity,
    }
    overall = round(sum(dimensions.values()) / len(dimensions))
    if report.get("blockingErrors", 0):
        overall = min(overall, 69)
    grade = "A+" if overall >= 92 else "A" if overall >= 86 else "B" if overall >= 78 else "C" if overall >= 68 else "D"
    recommendations = []
    seen: set[str] = set()
    for issue in sorted(
        report.get("issues", []), key=lambda item: item.get("severity") != "error"
    ):
        code = str(issue.get("code", ""))
        if code in seen or code not in ISSUE_GUIDANCE:
            continue
        seen.add(code)
        title, detail = ISSUE_GUIDANCE[code]
        recommendations.append({
            "priority": "高" if issue.get("severity") == "error" else "中",
            "title": title,
            "detail": detail,
            "slide": issue.get("slide", 0),
        })
        if len(recommendations) >= 5:
            break
    return {
        "rubric": "professional-slide-quality-v1",
        "benchmarkAlignment": [
            "Presentation Fundamentals", "Visual Design and Layout",
            "Content Completeness", "Content Correctness", "Content Fidelity",
        ],
        "dimensions": dimensions,
        "overall": overall,
        "grade": grade,
        "ready": overall >= 78 and report.get("blockingErrors", 0) == 0,
        "recommendations": recommendations,
    }


def validate_deck(slides: list[dict], sources: list[dict]) -> dict:
    source_names = {source["name"] for source in sources}
    source_sections = {
        (source["name"], section["id"]): section.get("text", "")
        for source in sources for section in source.get("sections", [])
    }
    issues = []
    referenced = 0
    checked_claims = 0
    supported_claims = 0
    messages: list[str] = []
    seen_titles: dict[str, int] = {}
    seen_content: dict[str, int] = {}
    seen_messages: dict[str, int] = {}
    visual_types: list[str] = []
    for expected_position, slide in enumerate(slides, 1):
        position = slide["position"]
        if position != expected_position:
            issues.append({
                "slide": position, "code": "position-contract-broken", "severity": "error",
                "message": f"页面位置应为 {expected_position}，实际为 {position}",
            })
        text = _slide_text(slide)
        messages.append(str(slide.get("message", "")).strip().lower())
        bullets = slide.get("content", {}).get("bullets", [])
        if slide.get("role") not in {"cover", "agenda", "section", "questions"} and not str(slide.get("message", "")).strip():
            issues.append({"slide": position, "code": "missing-single-message", "severity": "warning"})
        for bullet in bullets:
            if len(str(bullet)) > 86:
                issues.append({
                    "slide": position, "code": "long-audience-bullet", "severity": "warning",
                    "length": len(str(bullet)),
                })
        density = len("".join(bullets))
        if density > slide.get("constraints", {}).get("maxTextDensity", 420):
            issues.append({"slide": position, "code": "density", "severity": "error"})
        elif density > 360 or len(bullets) > 5:
            issues.append({"slide": position, "code": "high-reading-load", "severity": "warning"})
        title = str(slide.get("content", {}).get("title", "")).strip()
        if re.fullmatch(
            r"(?:第\s*\d+\s*页(?:幻灯片)?|未命名(?:页面|幻灯片)?|页面\s*\d+|slide\s*\d+)",
            title,
            re.IGNORECASE,
        ):
            issues.append({"slide": position, "code": "placeholder-slide-title", "severity": "error"})
        if slide.get("role") == "agenda" and len([item for item in bullets if str(item).strip()]) < 3:
            issues.append({"slide": position, "code": "empty-agenda", "severity": "error"})
        if (
            slide.get("role") not in {"cover", "agenda", "section", "questions"}
            and not str(slide.get("message", "")).strip()
            and not any(str(item).strip() for item in bullets)
        ):
            issues.append({"slide": position, "code": "empty-content-slide", "severity": "error"})
        if len(title) > 34:
            issues.append({
                "slide": position, "code": "long-slide-title", "severity": "warning",
                "length": len(title),
            })
        if re.search(
            r"[（(\[]\s*(?:S|SRC)\s*\d*\s*[）)\]]",
            f"{title} {text}",
            re.IGNORECASE,
        ):
            issues.append({
                "slide": position, "code": "visible-source-marker", "severity": "warning",
            })
        title_key = re.sub(r"[^\w\u4e00-\u9fff]", "", title).lower()
        if (
            len(slides) >= 12
            and title_key
            and title_key in seen_titles
            and slide.get("role") not in {"agenda", "section", "questions"}
        ):
            issues.append({
                "slide": position,
                "code": "duplicate-slide-title",
                "severity": "error",
                "firstSlide": seen_titles[title_key],
                "message": f"与第 {seen_titles[title_key]} 页标题重复",
            })
        elif title_key:
            seen_titles[title_key] = position
        content_key = re.sub(r"[^\w\u4e00-\u9fff]", "", " ".join([str(slide.get("message", "")), *map(str, bullets)])).lower()
        if (
            slide.get("role") not in {"cover", "agenda", "section", "questions"}
            and len(content_key) >= 24
            and content_key in seen_content
        ):
            issues.append({
                "slide": position,
                "code": "duplicate-slide-content",
                "severity": "error",
                "firstSlide": seen_content[content_key],
                "message": f"与第 {seen_content[content_key]} 页正文重复",
            })
        elif content_key:
            seen_content[content_key] = position
        message_key = re.sub(r"[^\w\u4e00-\u9fff]", "", str(slide.get("message", ""))).lower()
        if (
            slide.get("role") not in {"cover", "agenda", "section", "questions"}
            and len(message_key) >= 12
            and message_key in seen_messages
        ):
            issues.append({
                "slide": position,
                "code": "repeated-message",
                "severity": "error",
                "firstSlide": seen_messages[message_key],
            })
        elif message_key:
            seen_messages[message_key] = position
        if re.fullmatch(r"(?:背景|背景介绍|核心内容|方法概述|项目介绍|研究内容|主要内容|总结|结论)", title):
            issues.append({"slide": position, "code": "generic-title", "severity": "warning"})
        if re.search(
            r"证据可追溯\s*[·・|｜]\s*叙事可验证|从证据提取、叙事规划到可编辑交付|统一标题风格|避免标题过长|(?:保留|移[至入]|放).{0,16}(?:message|title|bullets)\b",
            f"{title} {text}",
        ):
            issues.append({
                "slide": position,
                "code": "audience-copy-process-leak",
                "severity": "error",
            })
        visual_type = str(slide.get("visualIntent", {}).get("primaryVisual", "cards"))
        visual_types.append(visual_type)
        if visual_type == "chart" and sum(bool(_numbers(str(item))) for item in bullets) < 2:
            issues.append({
                "slide": position, "code": "weak-chart-encoding", "severity": "warning",
            })
        if visual_type == "generated-image" and slide.get("role") in {"data", "evidence", "comparison"}:
            issues.append({"slide": position, "code": "generated-factual-visual", "severity": "error"})
        if any(item.get("type") == "generated-image" and not item.get("provenance") for item in slide.get("assetBindings", [])):
            issues.append({"slide": position, "code": "missing-image-provenance", "severity": "warning"})
        refs = slide.get("sourceRefs", [])
        if slide.get("role") not in {"cover", "agenda", "section", "questions"} and len(refs) > 8:
            issues.append({
                "slide": position,
                "code": "excessive-source-window",
                "severity": "error",
                "count": len(refs),
            })
        for ref in refs:
            referenced += 1
            if ref.get("document") not in source_names or (
                ref.get("document"), ref.get("section")
            ) not in source_sections:
                issues.append({
                    "slide": position, "code": "broken-source-ref", "severity": "error",
                    "document": ref.get("document"), "section": ref.get("section"),
                    "message": "引用的文档或章节不存在",
                })
        if slide.get("role") in {"cover", "agenda", "section", "questions"}:
            continue
        referenced_text = " ".join(
            source_sections.get((ref.get("document"), ref.get("section")), "") for ref in refs
        )
        audience_tokens = _semantic_tokens(text)
        source_tokens = _semantic_tokens(referenced_text)
        lexical_tokens = {token for token in audience_tokens if not re.fullmatch(r"\d+(?:\.\d+)?%?", token)}
        if refs and len(lexical_tokens) >= 6 and source_tokens:
            overlap = len(lexical_tokens & source_tokens) / len(lexical_tokens)
            if overlap < 0.08:
                issues.append({
                    "slide": position,
                    "code": "weak-source-grounding",
                    "severity": "error",
                    "overlap": round(overlap, 3),
                })
        # A number found elsewhere in the corpus does not support this page's citation.
        allowed_numbers = _numbers(referenced_text)
        for value in sorted(_numbers(text)):
            checked_claims += 1
            accounting_value = value[1:] if value.startswith("-") else ""
            accounting_source = bool(
                accounting_value
                and accounting_value in allowed_numbers
                and re.search(
                    rf"[（(]\s*{re.escape(accounting_value)}\s*[）)]",
                    referenced_text,
                )
            )
            if value in allowed_numbers or accounting_source:
                supported_claims += 1
            else:
                issues.append({
                    "slide": position, "code": "unsupported-metric", "severity": "error",
                    "value": value, "message": f"数字 {value} 无法在引用资料中找到",
                })
        if _numbers(text) and not slide.get("evidenceBindings"):
            issues.append({
                "slide": position, "code": "missing-evidence-binding", "severity": "error",
            })
    body = [slide for slide in slides if slide.get("role") not in {"cover", "agenda", "section", "questions"}]
    coverage = 1 if not body else sum(bool(slide.get("sourceRefs")) for slide in body) / len(body)
    for index in range(1, len(messages)):
        if messages[index] and messages[index] == messages[index - 1] and not any(
            issue.get("slide") == index + 1 and issue.get("code") == "repeated-message" for issue in issues
        ):
            issues.append({"slide": index + 1, "code": "repeated-message", "severity": "warning"})
    if len(slides) >= 6 and not any(slide.get("role") == "conclusion" for slide in slides[-2:]):
        issues.append({"slide": len(slides), "code": "missing-conclusion", "severity": "error"})
    role_runs = []
    for slide in slides:
        role = slide.get("role", "content")
        if role_runs and role_runs[-1][0] == role:
            role_runs[-1][1] += 1
        else:
            role_runs.append([role, 1])
    for role, count in role_runs:
        if role not in {"content"} and count > 3:
            issues.append({"slide": 0, "code": "repetitive-role-run", "severity": "warning", "role": role, "count": count})
    meaningful_visuals = sum(value in {"chart", "diagram", "source-image", "generated-image"} for value in visual_types)
    if slides and meaningful_visuals / len(slides) < 0.45:
        issues.append({"slide": 0, "code": "low-visual-evidence-ratio", "severity": "warning"})
    if len(slides) >= 10 and len(set(visual_types)) < 3:
        issues.append({"slide": 0, "code": "low-visual-diversity", "severity": "warning"})
    visual_maturity = assess_visual_maturity(slides)
    for issue in visual_maturity["issues"]:
        issues.append({"slide": 0, **issue})
    semantic_report = semantic_completeness(slides, sources)
    summary_report = summary_evidence_coverage(slides, sources)
    if summary_report and not summary_report["passed"]:
        issues.append({"slide": 0, "code": "missing-key-evidence", "severity": "error",
                       "message": "长篇材料的核心章节或主要任务指标尚未在演示中呈现", "details": summary_report})
    if semantic_report["requiredSections"] >= 2 and semantic_report["overall"] < 0.82:
        issues.append({
            "slide": 0,
            "code": "missing-semantic-coverage",
            "severity": "error" if semantic_report["overall"] < 0.55 and summary_report is None else "warning",
            "missing": semantic_report["missing"][:5],
        })
    blocking = sum(issue["severity"] == "error" for issue in issues)
    claim_coverage = 1 if not checked_claims else supported_claims / checked_claims
    warning_count = sum(issue["severity"] == "warning" for issue in issues)
    duplicate_count = sum(issue["code"] in {"duplicate-slide-title", "duplicate-slide-content", "repeated-message"} for issue in issues)
    scorecard = {
        "structure": max(0, 100 - 20 * sum(issue["code"] in {"position-contract-broken", "missing-conclusion", "repetitive-role-run"} for issue in issues)),
        "evidence": round(coverage * 100),
        "factuality": round(claim_coverage * 100),
        "readability": max(0, 100 - 7 * sum(issue["code"] in {"density", "high-reading-load", "long-audience-bullet"} for issue in issues)),
        "coherence": max(0, 100 - 14 * duplicate_count),
        "visualSemantics": round(
            min(100, (meaningful_visuals / max(1, len(slides))) * 160) * 0.5
            + visual_maturity["score"] * 0.5
        ),
    }
    result = {
        "contentCoverage": round(coverage, 3),
        "claimCoverage": round(claim_coverage, 3),
        "checkedNumericClaims": checked_claims,
        "supportedNumericClaims": supported_claims,
        "sourceRefs": referenced,
        "blockingErrors": blocking,
        "issues": issues,
        "warningCount": warning_count,
        "scorecard": scorecard,
        "semanticCompleteness": semantic_report,
        "summaryEvidenceCoverage": summary_report,
        "visualMaturity": visual_maturity,
        "narrative": {"roles": [slide.get("role") for slide in slides], "hasConclusion": any(slide.get("role") == "conclusion" for slide in slides[-2:])},
        "passed": blocking == 0 and coverage >= 0.9 and claim_coverage == 1,
    }
    result["professionalAudit"] = build_professional_audit(result)
    return result
