"""Guided intake: five short phases before a deck is built.

Like a consultant's kickoff (Strategy → Substance → Structure → Design → Build), the
intake asks only what changes the deck, and pre-fills every answer with a default
derived from the request and the uploaded materials, so a user can accept it in
one click. Answers compile into the normal planning request; nothing here bypasses
the evidence rules: "must cover" items are preferences for selection, not facts.
"""

from __future__ import annotations

import re
from typing import Any

from app.intelligence.evidence import extract_evidence_graph
from app.workflows.planning_brief import PRESET_LABELS, TONE_LABELS

VERSION = "guided-intake-v1"
AUDIENCE_DEFAULTS = {
    "academic": "答辩委员会", "conference": "同行研究者", "business": "公司管理层", "strategy": "决策层",
    "executive": "高管", "review": "项目团队与管理层", "product": "目标用户与媒体", "pitch": "潜在投资人",
    "marketing": "客户方市场负责人", "sales": "客户决策人", "teaching": "学生", "training": "参训员工",
    "public": "政府部门与公众", "keynote": "大会听众", "portfolio": "招聘方或客户",
}
OBJECTIVE_DEFAULTS = {
    "academic": "认可研究问题、方法与结论成立", "business": "理解现状并支持下一步决策",
    "executive": "在会上做出明确决定", "pitch": "愿意进入下一轮投资沟通", "sales": "同意推进试点或采购",
    "teaching": "掌握核心概念并能应用", "training": "会后能按方法执行", "product": "理解产品价值并愿意尝试",
}
NARRATIVES = {
    "conclusion-first": "结论先行：先给判断，再给证据与行动",
    "problem-solution": "问题 → 方案 → 证据 → 下一步",
    "chronological": "按时间线展开：背景 → 过程 → 结果 → 展望",
    "research": "研究汇报：问题 → 方法 → 实验 → 结论 → 局限",
}
PRESET_NARRATIVE = {
    "academic": "research", "conference": "research", "executive": "conclusion-first", "strategy": "conclusion-first",
    "business": "conclusion-first", "review": "chronological", "pitch": "problem-solution", "sales": "problem-solution",
    "product": "problem-solution",
}
MINUTES_PER_SLIDE = {"executive": 2.2, "strategy": 2.0, "pitch": 1.2, "keynote": 1.5, "teaching": 2.5, "training": 2.5}


def suggested_slide_count(preset: str, minutes: int | None, fallback: int = 12) -> int:
    if not minutes:
        return fallback
    per_slide = MINUTES_PER_SLIDE.get(preset, 1.6)
    return max(6, min(60, round(minutes / per_slide)))


def _candidate_facts(sources: list[dict], limit: int = 8) -> list[dict]:
    real = [source for source in sources if not source.get("synthetic")]
    if not real:
        return []
    facts = extract_evidence_graph(real).get("facts", [])
    metric = [fact for fact in facts if fact.get("kind") == "metric" and 14 <= len(fact["claim"]) <= 140]
    picked, seen = [], set()
    for fact in metric:
        key = re.sub(r"\s+", "", fact["claim"])[:40]
        if key in seen:
            continue
        seen.add(key)
        picked.append({"id": fact["id"], "label": fact["claim"], "sourceRef": fact.get("sourceRef")})
        if len(picked) >= limit:
            break
    return picked


def _constraints(sources: list[dict], limit: int = 4) -> list[str]:
    real = [source for source in sources if not source.get("synthetic")]
    if not real:
        return []
    return [fact["claim"] for fact in extract_evidence_graph(real).get("facts", []) if fact.get("kind") == "constraint"][:limit]


def build_intake(
    *, title: str, instructions: str = "", preset: str = "academic", slide_count: int = 12,
    duration_minutes: int | None = None, audience: str = "", objective: str = "", tone: str = "auto",
    brand_name: str = "", sources: list[dict] | None = None,
) -> dict[str, Any]:
    sources = sources or []
    facts = _candidate_facts(sources)
    constraints = _constraints(sources)
    narrative = PRESET_NARRATIVE.get(preset, "conclusion-first")
    minutes = duration_minutes or None
    phases = [
        {"id": "strategy", "title": "策略", "hint": "先确定讲给谁、要他们做什么", "questions": [
            {"id": "audience", "label": "主要受众是谁？", "type": "text",
             "suggested": audience or AUDIENCE_DEFAULTS.get(preset, "目标受众"), "why": "决定术语深度和证据密度"},
            {"id": "objective", "label": "讲完后希望受众理解或决定什么？", "type": "text",
             "suggested": objective or OBJECTIVE_DEFAULTS.get(preset, f"理解《{title}》的核心判断"), "why": "决定结尾页和全篇主线"},
        ]},
        {"id": "substance", "title": "内容", "hint": "材料里哪些事实必须讲到", "questions": [
            {"id": "mustCover", "label": "必须讲到的关键事实", "type": "multi",
             "options": [{"value": fact["id"], "label": fact["label"]} for fact in facts],
             "suggested": [fact["id"] for fact in facts[:3]],
             "why": "优先进入页面；仍需在材料中有出处" if facts else "未上传材料时可跳过"},
            {"id": "avoid", "label": "需要回避或不展开的内容", "type": "text", "suggested": "", "why": "例如未公开数据、敏感客户名称"},
            {"id": "keepBoundaries", "label": "保留材料中的限定条件", "type": "choice",
             "options": [{"value": "yes", "label": "保留在页面上"}, {"value": "notes", "label": "放进讲稿"}],
             "suggested": "yes" if constraints else "notes",
             "why": "；".join(constraints[:2]) or "材料中未发现明显的限定条件"},
        ]},
        {"id": "structure", "title": "结构", "hint": "时长决定页数，叙事决定顺序", "questions": [
            {"id": "durationMinutes", "label": "演讲时长（分钟）", "type": "number",
             "suggested": minutes or 15, "why": "用于计算页数和每页时间预算"},
            {"id": "slideCount", "label": "页数", "type": "number",
             "suggested": suggested_slide_count(preset, minutes, slide_count), "why": f"按约 {MINUTES_PER_SLIDE.get(preset, 1.6)} 分钟一页估算"},
            {"id": "narrative", "label": "叙事方式", "type": "choice",
             "options": [{"value": key, "label": label} for key, label in NARRATIVES.items()],
             "suggested": narrative, "why": f"{PRESET_LABELS.get(preset, preset)}的常用结构"},
        ]},
        {"id": "design", "title": "设计", "hint": "语气和品牌", "questions": [
            {"id": "tone", "label": "表达语气", "type": "choice",
             "options": [{"value": key, "label": label} for key, label in TONE_LABELS.items()],
             "suggested": tone, "why": "影响标题写法和版式家族"},
            {"id": "brandName", "label": "品牌 / 组织名称", "type": "text", "suggested": brand_name, "why": "用于封面与页眉，可留空"},
        ]},
        {"id": "build", "title": "生成", "hint": "怎样交付给你检查", "questions": [
            {"id": "reviewMode", "label": "生成方式", "type": "choice",
             "options": [{"value": "full", "label": "直接生成完整演示"}, {"value": "samples-first", "label": "先确认大纲和样张"}],
             "suggested": "full", "why": "先看样张适合重要场合"},
        ]},
    ]
    return {"version": VERSION, "title": title, "preset": preset, "instructions": instructions,
            "phases": phases, "materialFacts": len(facts)}


def compile_intake(base: dict[str, Any], answers: dict[str, Any], intake: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge answers into a PlanRequest payload (instructions stay ≤ 4,000 characters)."""
    labels = {}
    for phase in (intake or {}).get("phases", []):
        for question in phase.get("questions", []):
            for option in question.get("options", []) or []:
                labels[(question["id"], option["value"])] = option["label"]
    payload = dict(base)
    for key, field in (("audience", "audience"), ("objective", "objective"), ("brandName", "brand_name")):
        value = str(answers.get(key) or "").strip()
        if value:
            payload[field] = value[:500 if field == "objective" else 240]
    if answers.get("tone") in TONE_LABELS:
        payload["tone"] = answers["tone"]
    try:
        minutes = int(answers.get("durationMinutes") or 0)
        if 3 <= minutes <= 180:
            payload["duration_minutes"] = minutes
    except (TypeError, ValueError):
        pass
    try:
        count = int(answers.get("slideCount") or 0)
        if 6 <= count <= 60:
            payload["slide_count"] = count
    except (TypeError, ValueError):
        pass
    payload["approval_mode"] = answers.get("reviewMode") == "samples-first"
    lines = [str(base.get("instructions") or "").strip()]
    narrative = NARRATIVES.get(str(answers.get("narrative") or ""))
    if narrative:
        lines.append(f"叙事方式：{narrative}")
    must = [labels.get(("mustCover", value), "") for value in answers.get("mustCover") or []]
    must = [item for item in must if item]
    if must:
        lines.append("优先覆盖以下材料事实（保留原文数字与限定条件）：" + "；".join(item[:120] for item in must[:6]))
    avoid = str(answers.get("avoid") or "").strip()
    if avoid:
        lines.append(f"回避或不展开：{avoid[:300]}")
    if answers.get("keepBoundaries") == "yes":
        lines.append("材料中的限定条件（口径、样本、前提）保留在页面上，不只放进讲稿")
    instructions = "\n".join(line for line in lines if line)
    payload["instructions"] = instructions[:4000]
    return payload
