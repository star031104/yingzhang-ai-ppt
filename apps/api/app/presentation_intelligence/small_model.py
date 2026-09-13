"""面向小参数模型的分阶段演示编排策略。

系统守住事实、安全与交付底线；小模型先形成一份短策略记忆，再按三页一组完成
页面提案，最后只看大纲做一致性复核。这样不会把长文档一次塞给 8B 模型，也不会
因为规则过度僵硬而把每页都做成相同卡片。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from app.intelligence.content_selection import concise_source_context, select_key_points
from app.intelligence.retrieval import retrieve_source_context

NAVIGATION_ROLES = {"cover", "agenda", "section", "questions"}


@dataclass(frozen=True)
class ModelPolicy:
    code: str
    label: str
    detected_billions: float | None
    batch_size: int
    context_limit: int
    max_tokens: int
    temperature: float
    thinking_budget: int | None
    model_may_suggest_visual: bool


def _detected_billions(model_id: str, quality_profile: dict | None = None) -> float | None:
    profile_value = (quality_profile or {}).get("parameter_billions")
    if isinstance(profile_value, (int, float)) and profile_value > 0:
        return float(profile_value)
    # MoE 名称中的 A3B 表示每次推理激活规模；对上下文服从性采用更保守的激活规模。
    active = re.search(r"(?:^|[-_/])A(\d+(?:\.\d+)?)B(?:$|[-_/])", model_id, re.IGNORECASE)
    if active:
        return float(active.group(1))
    values = re.findall(r"(?:^|[-_/])(\d+(?:\.\d+)?)B(?:$|[-_/])", model_id, re.IGNORECASE)
    return float(values[-1]) if values else None


def infer_model_policy(model_id: str | None, quality_profile: dict | None = None) -> ModelPolicy:
    if not model_id:
        return ModelPolicy(
            code="rules-only", label="纯规则规划", detected_billions=None,
            batch_size=0, context_limit=0, max_tokens=0, temperature=0,
            thinking_budget=None, model_may_suggest_visual=False,
        )
    billions = _detected_billions(model_id, quality_profile)
    is_qwen3 = "qwen3" in model_id.lower()
    if billions is not None and billions <= 10:
        return ModelPolicy(
            code="tiny", label="10B 以内·分段协作模式", detected_billions=billions,
            batch_size=3, context_limit=7600, max_tokens=2600, temperature=0.14,
            thinking_budget=256 if is_qwen3 else None, model_may_suggest_visual=False,
        )
    if billions is None or billions <= 30:
        return ModelPolicy(
            code="compact", label="30B 以内·分段协作模式", detected_billions=billions,
            batch_size=4, context_limit=13000, max_tokens=3600, temperature=0.17,
            thinking_budget=384 if is_qwen3 else None, model_may_suggest_visual=False,
        )
    return ModelPolicy(
        code="capable", label="大模型·结构受控模式", detected_billions=billions,
        batch_size=7, context_limit=22000, max_tokens=5200, temperature=0.2,
        thinking_budget=512 if is_qwen3 else None, model_may_suggest_visual=True,
    )


def _page_batches(slides: list[dict], size: int) -> list[dict]:
    batches = []
    for offset in range(0, len(slides), max(1, size)):
        group = slides[offset: offset + max(1, size)]
        refs = []
        for slide in group:
            for ref in slide.get("sourceRefs", []):
                key = (ref.get("document"), ref.get("section"))
                if key not in refs:
                    refs.append(key)
        batches.append({
            "index": len(batches) + 1,
            "start": group[0]["position"],
            "end": group[-1]["position"],
            "positions": [slide["position"] for slide in group],
            "roles": [slide.get("role", "content") for slide in group],
            "sourceSections": [
                {"document": document, "section": section}
                for document, section in refs if document and section
            ],
        })
    return batches


def build_execution_contract(plan: dict, model_id: str | None, quality_profile: dict | None = None) -> dict:
    policy = infer_model_policy(model_id, quality_profile)
    batches = _page_batches(plan.get("slides", []), policy.batch_size) if policy.batch_size else []
    return {
        "version": "small-model-orchestration-v2",
        "model": model_id,
        "policy": asdict(policy),
        "principle": "规则守住事实与交付底线，小模型分段参与策略、页面责任和视觉提案",
        "ruleOwned": [
            "输入材料角色与优先级", "总页数、页面顺序与开场收束位置",
            "来源引用、证据绑定与数字白名单", "事实页必须使用原文图、数据图或可编辑图解",
            "版式安全区、密度上限与候选评分", "事实检查、失败回退与多格式导出",
        ],
        "modelOwned": [
            "受众、中心命题、重点与章节目标提案", "在安全的章节范围内调整页面责任和角色",
            "在给定证据窗口内撰写结论式标题与观众文案", "提出适配页面任务的视觉表达建议",
        ],
        "hybrid": [
            "模型提出叙事策略，程序用材料证据校准", "模型提出页面角色，程序只做相邻语义区兼容检查",
            "模型提出视觉方式，程序按事实类型裁决", "页面文案由模型生成，程序执行数字和引用复核",
        ],
        "hardConstraints": [
            "模型不得增删页面、改变顺序、选择来源或发明数字",
            "事实页不得使用生图替代数据图和原文图", "任一批次失败时使用内置规划结果补位",
            "任一页未通过密度、重复、证据或视觉门禁时不得视为完成",
        ],
        "stages": [
            {"id": "intake", "owner": "规则", "name": "材料分工与冲突登记"},
            {"id": "evidence", "owner": "规则", "name": "章节、事实、指标和图表索引"},
            {"id": "strategy", "owner": "小模型+规则", "name": "生成并校准全局策略记忆"},
            {"id": "contracts", "owner": "规则", "name": "建立逐页证据底稿"},
            {"id": "copy", "owner": "小模型", "name": "每三页生成责任、文案与视觉提案"},
            {"id": "reconcile", "owner": "规则", "name": "兼容校验、数字清洗与缺页回退"},
            {"id": "review", "owner": "小模型+规则", "name": "只读大纲的一致性复核"},
            {"id": "render", "owner": "规则", "name": "安全编译、候选渲染与评分"},
            {"id": "qa", "owner": "规则", "name": "事实、叙事、视觉与可编辑性验收"},
        ],
        "batches": batches,
    }


def _section_map(sources: list[dict]) -> dict[tuple[str, str], dict]:
    return {
        (source.get("name", ""), section.get("id", "")): {
            "document": source.get("name", ""), **section,
        }
        for source in sources for section in source.get("sections", [])
    }


def bounded_batch_context(
    sources: list[dict], slides: list[dict], title: str, preset: str,
    instructions: str, limit: int,
) -> str:
    """Build a small, page-specific evidence window instead of sending the whole document."""
    records = _section_map(sources)
    requested = {}
    for slide in slides:
        query = " ".join(str(slide.get(key, "")) for key in ("purpose", "message"))
        for ref in slide.get("sourceRefs", []):
            key = (str(ref.get("document", "")), str(ref.get("section", "")))
            if key in records:
                requested[key] = (requested.get(key, "") + " " + query).strip()
    if not requested:
        return retrieve_source_context(sources, title, preset, instructions, limit=limit)
    blocks, used = [], 0
    for index, (key, query) in enumerate(requested.items()):
        section = records[key]
        ancestry = " > ".join(section.get("headingPath") or [section.get("title", "正文")])
        page = f"｜第{section['page']}页" if section.get("page") else ""
        header = f"\n【资料：{key[0]}｜{key[1]}｜{ancestry}{page}】\n"
        budget = max(0, (limit - used) // (len(requested) - index) - len(header))
        text = concise_source_context(section, budget, query)
        if text and used + len(header) + len(text) <= limit:
            blocks.append(header + text)
            used += len(header) + len(text)
    return "".join(blocks)


def permitted_facts(evidence: dict, slides: list[dict], limit: int = 28) -> list[str]:
    groups = dict.fromkeys(
        (ref.get("document"), ref.get("section")) for slide in slides for ref in slide.get("sourceRefs", [])
    )
    groups = {key: [] for key in groups}
    for fact in evidence.get("facts", []):
        ref = fact.get("sourceRef", {})
        claim = re.sub(r"\s+", " ", str(fact.get("claim", ""))).strip()
        key = (ref.get("document"), ref.get("section"))
        if key not in groups:
            continue
        if len(claim) < 8 or len(claim) > 220 or re.fullmatch(r"[\d.]+%?", claim):
            continue
        if claim not in groups[key]:
            groups[key].append(claim)
    quota, remainder = divmod(limit, max(1, len(groups)))
    queues = [select_key_points({"text": "\n\n".join(values)}, maximum=quota + (index < remainder)) for index, values in enumerate(groups.values())]
    claims = []
    while len(claims) < limit and any(queues):
        for queue in queues:
            if queue and len(claims) < limit:
                claim = queue.pop(0)
                if claim not in claims:
                    claims.append(claim)
    return claims


def stable_primary_visual(slide: dict) -> str:
    role = str(slide.get("role", "content"))
    if any(item.get("type") == "source-image" for item in slide.get("assetBindings", [])):
        return "source-image"
    if role in {"data", "comparison"}:
        return "chart"
    if role in {"method", "architecture", "evidence"}:
        return "diagram"
    if role == "section":
        return "typography"
    if role == "cover":
        return "typography"
    if role in {"background", "problem", "insight", "conclusion"}:
        return "typography"
    return "diagram" if role == "content" else "typography"


PHASE_ROLE_OPTIONS = {
    "opening": {"cover", "agenda", "section"},
    "context": {"background", "problem", "comparison", "insight", "content"},
    "method": {"method", "architecture", "evidence", "content"},
    "evaluation": {"data", "comparison", "insight", "evidence", "content"},
    "closing": {"conclusion", "questions", "insight"},
}


def safe_role_proposal(slide: dict, proposed_role: str, preset: str, slide_count: int) -> str:
    """Allow local narrative judgment without letting a small model break deck structure."""
    current = str(slide.get("role", "content"))
    position = int(slide.get("position", 0) or 0)
    proposed = str(proposed_role or current).strip().lower()
    if position == 1:
        return "cover"
    if current in NAVIGATION_ROLES:
        return current
    if position == slide_count:
        return "conclusion" if preset in {"academic", "conference"} else (
            proposed if proposed in {"conclusion", "questions"} else "conclusion"
        )
    phase = str(slide.get("phase", "")).strip().lower()
    if not phase:
        phase = (
            "context" if current in PHASE_ROLE_OPTIONS["context"] else
            "method" if current in PHASE_ROLE_OPTIONS["method"] else
            "evaluation" if current in PHASE_ROLE_OPTIONS["evaluation"] else "context"
        )
    return proposed if proposed in PHASE_ROLE_OPTIONS.get(phase, {current}) else current


def compatible_primary_visual(slide: dict, proposed_visual: str | None = None) -> str:
    """Accept expressive proposals only when they match the page's factual job."""
    if any(item.get("type") == "source-image" for item in slide.get("assetBindings", [])):
        return "source-image"
    role = str(slide.get("role", "content"))
    proposed = str(proposed_visual or "").strip().lower()
    if role in {"data", "comparison"}:
        return "chart"
    if role in {"method", "architecture", "evidence"}:
        return proposed if proposed in {"diagram", "source-image"} else "diagram"
    if role in {"cover", "section"}:
        return proposed if proposed in {"typography", "generated-image"} else "typography"
    if proposed in {"typography", "diagram", "cards"}:
        return proposed
    return stable_primary_visual(slide)
