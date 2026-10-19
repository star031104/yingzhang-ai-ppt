import math
import re
import uuid
from collections import Counter

from app.intelligence.content_selection import section_understanding, select_key_points
from app.intelligence.contract_library import (
    ACADEMIC_CONTRACT_LIBRARY,
    ACADEMIC_PRESETS,
    BUSINESS_PLAN_CONTRACT_LIBRARY,
    PHASE_LABELS,
    general_contracts,
    preset_library,
)
from app.intelligence.evidence import extract_evidence_graph
from app.intelligence.role_classifier import ROLE_PATTERNS, classify_section  # noqa: F401
from app.presentation_intelligence.layout_planner import plan_deck_layouts

ROLE_LABELS = {
    "agenda": "内容导览", "section": "章节过渡", "background": "研究背景", "problem": "核心问题",
    "method": "研究方法", "architecture": "系统架构", "evidence": "证据链路",
    "data": "实验结果", "comparison": "对比分析", "insight": "关键洞察",
    "conclusion": "结论与展望", "questions": "问答交流", "content": "核心内容",
}

def is_business_plan(sources: list[dict]) -> bool:
    return any(
        source.get("documentProfile", {}).get("presentationMode") == "business-plan"
        or source.get("documentProfile", {}).get("kind") == "商业计划书"
        for source in sources
    )


def _business_plan_contracts(slide_count: int) -> list[dict]:
    contracts = [
        {"role": "cover", "responsibility": "封面与项目核心主张", "targets": ["background", "problem"], "phase": "opening"}
    ]
    if slide_count >= 8:
        contracts.append({
            "role": "agenda",
            "responsibility": "答辩逻辑：机会与痛点、产品与技术、商业落地、财务风险",
            "targets": [],
            "phase": "opening",
        })
    closing = 2 if slide_count >= 7 else 1
    body_count = max(0, slide_count - len(contracts) - closing)
    library = BUSINESS_PLAN_CONTRACT_LIBRARY
    if body_count <= len(library):
        # Preserve the whole business argument even in shorter decks.
        chosen = [library[round(index * (len(library) - 1) / max(1, body_count - 1))] for index in range(body_count)]
    else:
        chosen = [*library]
        records_needed = body_count - len(chosen)
        chosen.extend(
            {**library[index % len(library)], "responsibility": f"补充证据：{library[index % len(library)]['responsibility']}"}
            for index in range(records_needed)
        )
    contracts.extend(dict(item) for item in chosen)
    contracts.append({
        "role": "conclusion",
        "responsibility": "总结项目价值、可行性与下一阶段行动",
        "targets": ["conclusion", "insight", "background"],
        "phase": "closing",
    })
    if closing == 2:
        contracts.append({"role": "questions", "responsibility": "感谢聆听并邀请交流", "targets": [], "phase": "closing"})
    return contracts[:slide_count]


def extract_evidence(sources: list[dict]) -> dict:
    return extract_evidence_graph(sources)


def classify_role(section: dict, position: int | None = None, total: int | None = None) -> str:
    return classify_section(section, position, total, set(ROLE_LABELS))["role"]


def archetypes(role: str) -> list[str]:
    return {
        "cover": ["hero", "editorial-cover", "minimal-cover"],
        "agenda": ["numbered-list", "section-map", "agenda-cards"],
        "section": ["chapter-divider", "section-statement", "minimal-section"],
        "background": ["big-statement", "context-cards", "timeline"],
        "problem": ["problem-cards", "contrast", "before-after"],
        "method": ["workflow", "three-stage", "process"],
        "architecture": ["layered-architecture", "pipeline", "hub-spoke"],
        "evidence": ["evidence-chain", "source-map", "claim-map"],
        "data": ["chart-focus", "metric-wall", "table-highlight"],
        "comparison": ["comparison-bars", "two-column", "scorecard"],
        "insight": ["finding-cards", "ablation", "big-statement"],
        "conclusion": ["takeaways", "summary-grid", "next-steps"],
        "questions": ["minimal-qa", "closing-statement", "contact"],
    }.get(role, ["split", "statement", "cards"])


def _source_ref(source: dict, section: dict) -> dict:
    return {"document": source["name"], "section": section["id"], "page": section.get("page")}


def _section_records(sources: list[dict]) -> list[dict]:
    records = []
    for source_index, source in enumerate(sources):
        back_matter = False
        by_title = {}
        section_total = len(source.get("sections", []))
        for section_index, section in enumerate(source.get("sections", [])):
            if not section.get("text", "").strip():
                continue
            title = str(section.get("title", "")).strip()
            if re.match(r"^(?:参考文献|references\b|附录|appendix\b|致谢)", title, re.IGNORECASE):
                back_matter = True
            # Continuation pages often have an arbitrary first line as their title.
            # Keep appendices available as evidence, but never use them as the core narrative.
            if back_matter:
                continue
            if re.search(r"参考文献|致谢|独创性声明|学位论文使用授权|目录$", title, re.IGNORECASE):
                continue
            if re.search(r"https?://|www\.|@", title, re.IGNORECASE) or len(title) > 100 or re.match(r"^\[?\d+\]", title):
                continue
            classified = classify_section(section, section_index, section_total, set(ROLE_LABELS))
            role = classified["role"]
            text = section.get("text", "")
            if title in by_title:
                previous = by_title[title]
                previous["section"]["text"] += "\n" + text
                previous["section"].pop("understanding", None)
                for key in ("tableIds", "figureIds"):
                    previous["section"][key] = list(dict.fromkeys([
                        *previous["section"].get(key, []), *section.get(key, []),
                    ]))
                previous["refSections"].append(section)
                previous["importance"] = max(previous["importance"], float(section.get("importance", 0.5)))
                previous["hasMetrics"] |= "metric" in section.get("evidenceTypes", [])
                continue
            record = {
                "source": source,
                "section": {**section},
                "refSections": [section],
                "role": role,
                "roleConfidence": classified["confidence"],
                "roleSignal": classified["signal"],
                "order": (source_index, section_index),
                "hasMetrics": bool(re.search(r"\d+(?:\.\d+)?\s*(?:%|倍|ms|秒|分钟|GB|MB)|Accuracy|F1|Recall|Precision", text, re.IGNORECASE)),
                "importance": float(section.get("importance", 0.5)),
            }
            records.append(record)
            by_title[title] = record
    return records


def analyze_materials(sources: list[dict]) -> dict:
    role_counts: Counter = Counter()
    documents = []
    for source in sources:
        sections = source.get("sections", [])
        classified = [
            (section, classify_section(section, index, len(sections), set(ROLE_LABELS)))
            for index, section in enumerate(sections) if section.get("text", "").strip()
        ]
        counts = Counter(item["role"] for _, item in classified)
        role_counts.update(counts)
        suffix = str(source.get("name", "")).lower().rsplit(".", 1)[-1]
        profile = source.get("documentProfile", {})
        documents.append({
            "name": source.get("name", "材料"),
            "kind": profile.get("kind") or ("论文/报告" if suffix in {"pdf", "docx"} else "数据材料" if suffix in {"xlsx", "xls", "csv"} else "视觉材料" if suffix in {"png", "jpg", "jpeg", "webp", "pptx"} else "文本材料"),
            "sections": len(sections),
            "figures": len(source.get("figures", [])),
            "tables": len(source.get("tables", [])),
            "characters": source.get("stats", {}).get("characters", sum(len(item.get("text", "")) for item in sections)),
            "semanticCoverage": dict(counts),
            "uncertainRoles": [
                {"section": section.get("id"), "title": str(section.get("title", ""))[:60],
                 "role": item["role"], "confidence": item["confidence"]}
                for section, item in classified if item["confidence"] < 0.5
            ][:8],
            "keyPoints": list(dict.fromkeys(
                point for section in sections
                for point in select_key_points(section, maximum=1)
            ))[:8],
            "limitations": list(dict.fromkeys(
                point for section in sections
                for point in section_understanding(section)["limitations"]
            ))[:6],
            "readingWarnings": source.get("readingWarnings", []),
        })
    missing = [role for role in ("background", "problem", "method", "architecture", "data", "conclusion") if not role_counts.get(role)]
    return {
        "documents": documents,
        "semanticCoverage": dict(role_counts),
        "missingEvidence": missing,
        "sourceStrategy": [
            "以论文或主报告建立叙事主线",
            "以表格和数据文件补充可编辑图表",
            "以图片和既有演示补充原始视觉证据",
            "冲突数字保留各自来源，不自动合并",
        ],
    }


def _allocate_counts(total: int, weights: list[float]) -> list[int]:
    if total <= 0:
        return [0 for _ in weights]
    raw = [total * weight / sum(weights) for weight in weights]
    counts = [math.floor(value) for value in raw]
    for index in sorted(range(len(raw)), key=lambda item: raw[item] - counts[item], reverse=True)[:total - sum(counts)]:
        counts[index] += 1
    return counts


def _phase_contracts(phase: str, count: int, records: list[dict]) -> list[dict]:
    library = ACADEMIC_CONTRACT_LIBRARY[phase]
    result = []
    phase_roles = {"context": {"background", "problem", "comparison"}, "method": {"method", "architecture", "evidence", "content"}, "evaluation": {"data", "comparison", "insight", "evidence"}}[phase]
    relevant_titles = [record["section"].get("title", "").strip() for record in records if record["role"] in phase_roles and record["section"].get("title", "").strip()]
    for index in range(count):
        contract = dict(library[index % len(library)])
        if index >= len(library) and relevant_titles:
            contract["responsibility"] = f"补充说明：{relevant_titles[index % len(relevant_titles)][:36]}"
        contract["phase"] = phase
        result.append(contract)
    return result


def build_page_contracts(sources: list[dict], title: str, preset: str, slide_count: int, instructions: str = "") -> list[dict]:
    records = _section_records(sources)
    if is_business_plan(sources):
        return _business_plan_contracts(slide_count)
    if preset not in ACADEMIC_PRESETS:
        return general_contracts(preset, slide_count, records)

    contracts = [{"role": "cover", "responsibility": "封面与研究命题", "targets": ["background", "problem"], "phase": "opening"}]
    if slide_count >= 9:
        contracts.append({"role": "agenda", "responsibility": "答辩逻辑：问题、方法、证据与结论", "targets": [], "phase": "opening"})
    section_count = 3 if slide_count >= 16 else 0
    closing_count = 2
    body_count = max(0, slide_count - len(contracts) - section_count - closing_count)
    context_count, method_count, evaluation_count = _allocate_counts(body_count, [0.23, 0.40, 0.37])
    for phase, count in (("context", context_count), ("method", method_count), ("evaluation", evaluation_count)):
        if section_count:
            contracts.append({"role": "section", "responsibility": PHASE_LABELS[phase], "targets": [], "phase": phase})
        contracts.extend(_phase_contracts(phase, count, records))
    if slide_count <= 8:
        contracts.extend([
            {"role": "conclusion", "responsibility": "研究结论、贡献与局限", "targets": ["conclusion", "insight"], "phase": "closing"},
            {"role": "questions", "responsibility": "简洁结束并邀请交流，不展示预设问题", "targets": [], "phase": "closing"},
        ])
    else:
        contracts.extend([
            {"role": "conclusion", "responsibility": "归纳研究结论、贡献与适用边界", "targets": ["conclusion", "insight"], "phase": "closing"},
            {"role": "questions", "responsibility": "简洁结束并邀请交流，不展示预设问题", "targets": [], "phase": "closing"},
        ])
    return contracts[:slide_count]


def _record_score(record: dict, contract: dict, used: Counter, relevance: dict | None = None) -> float:
    targets = contract.get("targets", [])
    if record["role"] in targets:
        score = 26 - targets.index(record["role"]) * 9
    else:
        score = -8 if targets else 0
    responsibility = contract.get("responsibility", "")
    title = str(record["section"].get("title", ""))
    text = f"{title} {record['section'].get('text', '')[:800]}"
    body = str(record["section"].get("text", "")).replace(title, " ")
    source_length = len(str(record["section"].get("text", "")).strip())
    if source_length < 40:
        score -= 90
    for keyword in contract.get("keywords", []):
        if keyword.lower() in title.lower():
            score += 72
        elif keyword.lower() in text.lower():
            score += 20
    if contract.get('role') not in {'cover', 'background'} and re.search(r"摘\s*要\s*[:：]|指导老?师|指导教师", text):
        return -1000
    query_terms = set(re.findall(r"[A-Za-z][\w-]{2,}|[\u4e00-\u9fff]{2,6}", responsibility.lower()))
    score += min(12, sum(1.5 for term in query_terms if term in text.lower()))
    title_expectations = {
        "background": r"背景|意义|引言|绪论|摘要",
        "problem": r"问题|挑战|目标|任务|贡献|研究内容|主要工作|缺口|提出",
        "comparison": r"现状|相关工作|国内外|对比|基线|性能分析",
        "method": r"方法|模型|算法|流程|构建|知识库|检索|Prompt|分析任务|产品服务|功能|营销|推广|运营",
        "architecture": r"总体|架构|框架|技术路线|系统设计|模块|流程|结构化|向量化|信息组织|产品概况|协同",
        "data": r"实验|结果|性能|评估|评价|指标|数据集|财务|现金流|销售|收入|资本|资金",
        "insight": r"消融|误差|分析|讨论|质量|效率|局限|风险|应对",
        "conclusion": r"结论|总结|展望|创新|局限|未来",
    }
    title_pattern = title_expectations.get(str(contract.get("role")))
    if title_pattern:
        score += 18 if re.search(title_pattern, title, re.IGNORECASE) else -14
    if len(title) > 32 and re.search(r"[，。；]", title):
        score -= 40
    if contract.get("phase") == "context" and re.search(r"实验|耗时|效率|性能|结果|消融", title):
        score -= 55
    if re.search(r"Prompt|提示词", title, re.IGNORECASE) and not re.search(r"Prompt|提示|推理约束", responsibility, re.IGNORECASE):
        score -= 28
    if contract.get("phase") == "method" and re.search(r"实验|结果|性能|效果|评估|评价|消融|去除|对比分析", title, re.IGNORECASE):
        score -= 100
    if contract.get("role") == "problem" and re.search(r"主要工作|研究目标|研究内容|主要贡献", title):
        score += 45
    if contract.get("role") == "data" and re.search(r"财务|现金流|资产负债|收入|资本|资金", responsibility):
        finance_signals = set(re.findall(
            r"财务|现金流|资产|负债|收入|成本|利润|资本|资金|金额|万元|融资|投资|销售",
            body,
        ))
        if len(finance_signals) < 2:
            score -= 85
    for keyword in ("总体", "知识", "数据", "输入", "算法", "系统", "实验", "消融", "效率", "未来"):
        if keyword in responsibility and keyword in title:
            score += 7
    if "总体框架" in responsibility and re.search(r"框架|技术路线|总体", title):
        score += 24
    if "系统架构" in responsibility and re.search(r"系统|架构|模块|工程", title):
        score += 20
    if record["hasMetrics"] and contract.get("role") in {"data", "comparison", "insight"}:
        score += 8
    if record["section"].get("page") is not None:
        score += 1
    score += record["importance"] * 3
    score -= used[(record["source"]["name"], record["section"]["id"])] * 32
    if relevance:
        # Hybrid (BM25 + dense) relevance of the section to the deck query; a tie-breaker, not an override.
        score += 6 * max(relevance.get((record["source"]["name"], part["id"]), 0.0) for part in record["refSections"])
    return score


def PathLikeTitle(name: str) -> str:
    value = re.sub(r"\.(?:pdf|docx|pptx|xlsx|csv|md|txt)$", "", str(name), flags=re.IGNORECASE)
    return re.sub(r"^[^_]{1,12}_", "", value).strip()


PLACEHOLDER_TITLE_RE = re.compile(
    r"^(?:第\s*\d+\s*页(?:幻灯片)?|未命名(?:页面|幻灯片)?|页面\s*\d+|slide\s*\d+)$",
    re.IGNORECASE,
)


def is_placeholder_title(value: object) -> bool:
    return bool(PLACEHOLDER_TITLE_RE.fullmatch(str(value or "").strip()))


def _contract_title(contract: dict) -> str:
    title = str(contract.get("responsibility") or ROLE_LABELS.get(contract.get("role"), "核心内容"))
    title = re.sub(r"^(?:答辩逻辑|补充证据)\s*[：:]\s*", "", title).strip()
    return title[:36]


def _select_record(
    records: list[dict], contract: dict, used: Counter, relevance: dict | None = None
) -> dict | None:
    if not records or contract["role"] in {"agenda", "section", "questions"}:
        return None
    return max(records, key=lambda record: (
        _record_score(record, contract, used, relevance), -record["order"][0], -record["order"][1]
    ))


def _bullets(section: dict, limit: int = 4, query: str = "") -> list[str]:
    return select_key_points(section, query, maximum=limit)


def _fit_bullets(points: list[str], budget: int = 430) -> list[str]:
    result: list[str] = []
    used = 0
    for point in points:
        text = str(point).strip()
        if not text:
            continue
        if re.search(
            r"[+\-−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*(?:%|个百分点|倍|万|亿|ms|毫秒|秒|分|分钟|小时|KB|MB|GB|TB|条|个|项|份|人|页)?",
            text,
            flags=re.IGNORECASE,
        ):
            # Punctuation trimming must not split thousands separators or
            # detach a result from its evidence; density validation can flag it.
            result.append(text)
            used += len(text)
            continue
        if len(text) > 84:
            sentence = re.split(r"[。！？；;]", text, maxsplit=1)[0].strip()
            if 18 <= len(sentence) <= 84:
                text = sentence
            else:
                candidate = text[:85]
                cut = max(candidate.rfind("，"), candidate.rfind(","), candidate.rfind("、"))
                text = candidate[:cut].rstrip() if cut >= 28 else text[:83].rstrip() + "…"
        if result and used + len(text) > budget:
            continue
        result.append(text)
        used += len(text)
        if used >= budget:
            break
    return result[:4]


def _accounting_number(value: object) -> str:
    text = re.sub(r"\s+", "", str(value or "")).strip()
    match = re.fullmatch(r"[（(]([-+−]?\d[\d,]*(?:\.\d+)?)[）)]", text)
    return f"-{match.group(1).lstrip('+').replace('−', '-')}" if match else text


def _table_bullets(record: dict | None, contract: dict, limit: int = 4) -> list[str]:
    """Turn parser tables into compact, named data rows for charts/tables.

    The full source table remains in speaker notes and provenance.  Audience
    slides keep the columns needed for the current communication job, avoiding
    anonymous fields and wide operational-detail tables.
    """
    if not record:
        return []
    table_ids = set(record["section"].get("tableIds", []))
    tables = [table for table in record["source"].get("tables", []) if table.get("id") in table_ids]
    if not tables:
        return []
    responsibility = str(contract.get("responsibility", ""))
    table = max(tables, key=lambda item: (len(item.get("rowStatements", [])), item.get("rowCount", 0)))
    rows = table.get("rows", [])
    header_index = int(table.get("headerRowIndex", 0) or 0)
    if not rows or header_index >= len(rows):
        return []
    headers = [re.sub(r"\s+", "", str(value or "")).strip() for value in rows[header_index]]
    data_rows = rows[header_index + 1:]
    if len(headers) < 2 or not data_rows:
        return []

    if re.search(r"资本结构|资金需求|资金用途", responsibility):
        selected_columns = [index for index, header in enumerate(headers) if re.search(r"占比|比例", header)]
    elif re.search(r"商业模式|收入来源|销售", responsibility):
        selected_columns = [index for index, header in enumerate(headers) if re.search(r"第?[一二三123]\s*年|年度", header)]
    elif re.search(r"财务预测|现金流|增长路径", responsibility):
        selected_columns = [index for index, header in enumerate(headers) if re.search(r"第?\s*[一二三123]\s*年|合计", header)]
    else:
        selected_columns = []
    if not selected_columns:
        for column in range(1, len(headers)):
            values = [_accounting_number(row[column] if column < len(row) else "") for row in data_rows]
            numeric = sum(bool(re.fullmatch(r"[-+−]?\d[\d,]*(?:\.\d+)?%?", value)) for value in values if value and value != "/")
            if numeric >= max(2, sum(bool(value and value != "/") for value in values) // 2):
                selected_columns.append(column)
    selected_columns = selected_columns[:3]
    if not selected_columns:
        return []

    candidates = []
    for order, row in enumerate(data_rows):
        subject = re.sub(r"\s+", "", str(row[0] if row else "")).strip(" ：:")
        if not subject or re.fullmatch(r"项目|收入来源|资金来源|资产类|负债与权益类|[一二三四五六七八九十]+[.．、]?", subject):
            continue
        if re.search(r"资本结构|资金需求|资金用途", responsibility) and re.search(r"合计|总计", subject):
            continue
        fields = []
        numeric_count = 0
        for column in selected_columns:
            if column >= len(row) or column >= len(headers):
                continue
            value = _accounting_number(row[column])
            if not value or value == "/":
                continue
            numeric_count += bool(re.fullmatch(r"[-+−]?\d[\d,]*(?:\.\d+)?%?", value))
            fields.append(f"{headers[column] or f'列{column + 1}'}：{value}")
        if not fields or not numeric_count:
            continue
        priority = (
            4 if re.search(r"总收入|合计|净流量|现金余额|利润", subject) else
            3 if re.search(r"政府|企业|团队|学校|补贴|赞助|SaaS", subject, re.IGNORECASE) else 1
        )
        candidates.append((priority, order, f"{subject}：{'；'.join(fields)}"))
    chosen = sorted(candidates, key=lambda item: (-item[0], item[1]))[:limit]
    return [item[2] for item in sorted(chosen, key=lambda item: item[1])]


def evidence_bindings(evidence: dict, refs: list[dict]) -> list[str]:
    keys = {(ref.get("document"), ref.get("section")) for ref in refs}
    return [fact["id"] for fact in evidence.get("facts", []) if (fact["sourceRef"].get("document"), fact["sourceRef"].get("section")) in keys]


def _expected_figure_kinds(contract: dict) -> list[str]:
    responsibility = contract.get("responsibility", "")
    role = contract.get("role")
    if role in {"data", "comparison"}:
        return ["chart", "table"]
    if "提示" in responsibility or "Prompt" in responsibility:
        return ["prompt", "diagram"]
    if role in {"method", "architecture"}:
        return ["diagram"]
    if role == "evidence":
        return ["diagram", "figure", "chart"]
    if role == "insight" and re.search(r"实验|结果|消融|效率|质量", responsibility):
        return ["chart", "diagram"] if "消融" in responsibility else ["chart"]
    return ["figure", "diagram"]


def plan_deck(
    sources: list[dict], title: str, preset: str = "academic", slide_count: int = 12,
    instructions: str = "", brief: dict | None = None,
    relevance: dict[tuple[str, str], float] | None = None,
) -> dict:
    """Plan a deck deterministically.

    ``relevance`` optionally maps ``(document, section)`` to a 0–1 hybrid retrieval
    score (see :func:`app.intelligence.retrieval.section_relevance_async`).
    """
    brief = brief or {}
    business_plan = is_business_plan(sources)
    evidence = extract_evidence_graph(sources)
    records = _section_records(sources)
    contracts = build_page_contracts(sources, title, preset, slide_count, instructions)
    if brief.get("narrativeOrder") == "conclusion-first" and preset not in {"academic", "conference"} and len(contracts) > 2:
        # Keep the final action/conclusion contract; use the opening route as a decision brief.
        opening = contracts[1]
        contracts[1] = {**opening, "role": "insight", "responsibility": "先陈述材料支持的核心判断，并交代问题背景",
                        "targets": list(dict.fromkeys(["conclusion", "insight", *opening.get("targets", [])])), "phase": "opening"}
    conclusion_record = next((record for record in reversed(records) if record["role"] == "conclusion"), None)
    opening_thesis = section_understanding(conclusion_record["section"])["mainPoint"] if conclusion_record and preset not in {"academic", "conference"} else title
    used: Counter = Counter()
    material_analysis = analyze_materials(sources)
    section_titles = [contract["responsibility"] for contract in contracts if contract["role"] == "section"]
    slides = []
    used_page_titles: set[str] = set()
    used_messages: set[str] = set()
    for position, contract in enumerate(contracts, 1):
        role = contract["role"]
        record = _select_record(records, contract, used, relevance)
        if record and role != "cover":
            used[(record["source"]["name"], record["section"]["id"])] += 1
        section = record["section"] if record else {"id": "S000", "title": title, "text": ""}
        refs = [_source_ref(record["source"], part) for part in record["refSections"]] if record else []
        # A result slide compares the complete task family, rather than picking
        # one child subsection and losing sibling baselines or task outcomes.
        if record and contract.get("phase") == "evaluation":
            match = re.match(r"^(\d+\.\d+)(?:\.\d+)*\s", section.get("title", ""))
            if match:
                prefix = match.group(1)
                siblings = [part for part in record["source"].get("sections", [])
                            if re.match(r"^" + re.escape(prefix) + r"(?:\.\d+)*\s", part.get("title", ""))]
                if siblings:
                    refs = [_source_ref(record["source"], part) for part in siblings]
                    section = {**section, "text": "\n".join(part.get("text", "") for part in siblings)}
                    section.pop("understanding", None)
        understanding = section.get("understanding") or section_understanding(section)
        if role == "cover":
            page_title, bullets = title, []
            message = str(brief.get("objective") or opening_thesis).strip()
        elif role == "agenda":
            academic = preset in {"academic", "conference"}
            page_title = "答辩逻辑" if academic else preset_library(preset)["agenda"]["title"]
            bullets = (
                ["机会与真实痛点", "产品、技术与服务闭环", "市场进入与组织执行", "商业可行性、风险与行动"]
                if business_plan
                else section_titles or (["研究问题与目标", "技术方案与系统实现", "实验验证与结论"] if academic else list(preset_library(preset)["agenda"]["bullets"]))
            )
            message, refs = (
                "从真实需求出发，验证解决方案能否持续落地"
                if business_plan else "从问题出发，用方法与证据回答核心命题"
            ), []
        elif role == "section":
            page_title = contract["responsibility"]
            bullets, message, refs = [], page_title.split("｜", 1)[-1], []
        elif role == "questions":
            page_title, bullets, message, refs = "感谢聆听", [], "欢迎交流", []
        elif role == "conclusion":
            page_title = (
                "项目价值与下一阶段行动"
                if business_plan
                else ("研究结论与未来工作" if position == slide_count else "研究结论、贡献与边界") if preset in ACADEMIC_PRESETS else preset_library(preset)["conclusion"]["title"]
            )
            bullets = _bullets(section, 4, contract["responsibility"])
            message = understanding.get("mainPoint") or contract["responsibility"]
        else:
            page_title = section.get("title") or _contract_title(contract)
            if (
                page_title == title
                or is_placeholder_title(page_title)
                or len(page_title) > 32 and re.search(r"[，。；]", page_title)
            ):
                page_title = _contract_title(contract)
            bullets = _bullets(section, 4, contract["responsibility"])
            message = understanding.get("mainPoint") or contract["responsibility"]
        table_points = _table_bullets(record, contract) if role in {"data", "comparison"} else []
        if table_points:
            bullets = table_points
            message = f"{page_title}按原始表格口径呈现"
        if role in {"data", "comparison"} and message in bullets and len(bullets) > 1 and not re.search(r"\d", message):
            # A standalone finding belongs in the takeaway; keep the chart rows tabular.
            bullets = [point for point in bullets if point != message]
        elif role in {"data", "comparison"} and section.get("tableIds") and message in bullets:
            message = f"{section.get('title', '数据')}按原始口径对照"
        title_key = re.sub(r"[^\w\u4e00-\u9fff]", "", str(page_title)).lower()
        if role not in {"cover", "agenda", "section", "questions"} and title_key in used_page_titles:
            page_title = _contract_title(contract)
            title_key = re.sub(r"[^\w\u4e00-\u9fff]", "", page_title).lower()
        if title_key:
            used_page_titles.add(title_key)
        message_key = re.sub(r"[^\w\u4e00-\u9fff]", "", str(message)).lower()
        if role not in {"cover", "agenda", "section", "questions"} and message_key in used_messages:
            message = contract["responsibility"]
            message_key = re.sub(r"[^\w\u4e00-\u9fff]", "", str(message)).lower()
        if message_key:
            used_messages.add(message_key)
        if role not in {"cover", "agenda", "section", "questions"}:
            bullets = _fit_bullets(bullets)
        bindings = evidence_bindings(evidence, refs)
        if brief.get("titleStyle") == "takeaway" and role not in {"cover", "agenda", "section", "questions"}:
            takeaway = str(understanding.get("mainPoint") or "").strip()
            if takeaway and len(takeaway) <= 44:
                page_title = takeaway
        expected_kinds = _expected_figure_kinds(contract)
        speaker_points = _bullets(section, 10)
        if table_points and record:
            table_ids = set(record["section"].get("tableIds", []))
            speaker_points = list(dict.fromkeys([
                *speaker_points,
                *[
                    point
                    for table in record["source"].get("tables", []) if table.get("id") in table_ids
                    for point in table.get("rowStatements", [])
                ],
            ]))[:10]
        slides.append({
            "id": str(uuid.uuid4()), "position": position, "role": role,
            "phase": contract.get("phase"), "purpose": contract["responsibility"], "message": message,
            "content": {"title": page_title, "bullets": bullets},
            "sourceRefs": refs, "evidenceBindings": bindings, "assetBindings": [],
            "visualIntent": {
                "archetypeCandidates": archetypes(role), "emphasis": "evidence" if bindings else "narrative",
                "density": "low" if role in {"cover", "section", "questions"} else ("high" if len(bullets) >= 4 else "medium"),
                "complexity": "high" if role == "architecture" else "medium",
                "contentRelation": understanding.get("relation", "explanation"),
                "expectedFigureKinds": expected_kinds,
                "forbiddenFigureKinds": ["prompt"] if "prompt" not in expected_kinds else [],
            },
            "layoutConstraints": {"preserveEvidenceValues": True, "oneCommunicationJob": True},
            "speakerIntent": {"talkingPoints": speaker_points, "sourceBoundaries": understanding.get("limitations", []), "transition": "承接下一页" if position < slide_count else "结束汇报"},
            "constraints": {"maxTextDensity": 520 if len(bullets) >= 4 else 440, "strictSource": True},
        })
    thesis_record = next((record for record in reversed(records) if record["role"] == "conclusion"), None)
    thesis_sentences = _bullets(thesis_record["section"], 1) if thesis_record else []
    body_roles = [slide["role"] for slide in slides if slide["role"] not in {"cover", "agenda", "section", "questions"}]
    default_job = (
        f"答辩委员会应理解《{title}》解决的真实需求，并判断产品、技术、商业模式与执行计划是否可行。"
        if business_plan
        else
        f"答辩委员会应理解研究问题、判断技术方案是否成立，并依据可追溯实验结果评价《{title}》的贡献。"
        if preset in {"academic", "conference"}
        else f"目标受众应理解《{title}》的核心判断，并知道下一步如何行动。"
    )
    audience = brief.get("audience") or (
        "答辩委员会" if preset in {"academic", "conference"} else "目标受众"
    )
    audience_outcome = brief.get("objective") or "理解问题、方法、证据与结论之间的因果链"
    layout_planning = plan_deck_layouts(slides, preset, brief)
    narrative = {
        "title": title, "preset": preset,
        "audience": audience,
        "communicationJob": brief.get("objective") or default_job,
        "audienceOutcome": audience_outcome,
        "delivery": {
            "durationMinutes": brief.get("durationMinutes"),
            "tone": brief.get("tone", "auto"),
            "brandName": brief.get("brandName", ""),
        },
        "thesis": thesis_sentences[0] if thesis_sentences else title,
        "arc": (
            ["机会与痛点", "产品与技术", "商业落地", "财务风险与行动"]
            if business_plan
            else ["研究问题", "技术方案", "实验验证", "结论与边界"] if preset in {"academic", "conference"} else body_roles
        ),
        "slideBudget": {"total": slide_count, "roles": body_roles},
        "visualRhythm": layout_planning["familySequence"],
    }
    return {
        "narrative": narrative, "materialAnalysis": material_analysis,
        "pageContracts": [{"position": index + 1, **contract} for index, contract in enumerate(contracts)],
        "presenterPreparation": {"audienceVisible": False, "anticipatedQuestionAreas": ["研究边界与数据代表性", "方法有效性的证据", "系统实现与实际应用限制"]},
        "layoutPlanning": layout_planning, "evidence": evidence, "slides": slides,
    }
