"""Validate and repair model page proposals against the rule-built plan.

The deterministic planner owns structure and facts; a model may only propose
copy, roles and visual hints. ``validate_page_proposals`` checks every proposal
against those rules, repairs what can be repaired from the builtin page, falls
back to the builtin page when too little survives, and records each decision so
the outline review UI can show why a model suggestion was changed.
"""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher

from app.intelligence.contract_library import allowed_roles
from app.intelligence.numeric_claims import strict_numbers

NAVIGATION_ROLES = {"cover", "agenda", "section", "questions"}
INLINE_REF_RE = re.compile(r"[\[（(]\s*((?:F|M)\d{3,5}|S\d{3,5})\s*[\]）)]")
REF_FIELDS = ("evidenceRefs", "evidence", "evidenceIds", "refs")
MAX_TITLE = 44
MAX_MESSAGE = 120
NEAR_DUPLICATE = 0.82
MESSAGES = {
    "missing-page": "模型未返回本页，使用内置规划页面",
    "extra-pages": "模型返回了超出页数预算的页面，已忽略",
    "role-not-allowed": "建议角色不在当前演示类型允许范围内，保留规划角色",
    "cover-not-first": "封面只能出现在第 1 页",
    "first-page-not-cover": "第 1 页必须是封面",
    "conclusion-not-last": "结论页只能出现在结尾",
    "last-page-not-conclusion": "最后一页必须负责收束",
    "unknown-evidence-ref": "引用了不存在的证据编号，已移除",
    "unsupported-number": "出现事实白名单之外的数字，已替换或删除",
    "duplicate-title": "标题与前文重复，已改用规划标题",
    "near-duplicate-title": "标题与前文高度相似，已改用规划标题",
    "title-too-long": "标题超过长度预算，已改用规划标题",
    "message-too-long": "本页结论超过长度预算，已改用规划结论",
    "too-many-bullets": "要点数量超出预算，已截断",
    "text-budget": "本页文字量超出密度预算，已删减末尾要点",
    "fallback": "本页提案问题过多，整页使用内置规划结果",
}


def _key(text: str) -> str:
    return re.sub(r"[^\w一-鿿]", "", str(text or "")).lower()


def near_duplicate(left: str, right: str) -> bool:
    a, b = _key(left), _key(right)
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = sorted((a, b), key=len)
    if len(shorter) >= 6 and shorter in longer and len(shorter) / len(longer) >= 0.75:
        return True
    return SequenceMatcher(None, a, b).ratio() >= NEAR_DUPLICATE


def _bare(value: str) -> str:
    match = re.match(r"[+\-]?\d+(?:\.\d+)?", value)
    return match.group().lstrip("+") if match else value


def _numbers_allowed(text: str, allowed: set[str]) -> list[str]:
    """Return the numbers in ``text`` that are not supported by the whitelist."""
    bare_allowed = {_bare(value) for value in allowed}
    unsupported = []
    for value in strict_numbers(text):
        bare = _bare(value)
        if value in allowed or (bare == value and bare in bare_allowed):
            continue
        # Small bare counts ("三步" written as 3) are structural, not factual claims.
        if bare == value and re.fullmatch(r"\d", value):
            continue
        unsupported.append(value)
    return sorted(unsupported)


def page_fact_claims(evidence: dict, slide: dict) -> list[str]:
    """All evidence claims bound to the page's fixed source sections (the page whitelist)."""
    keys = {(ref.get("document"), ref.get("section")) for ref in slide.get("sourceRefs", [])}
    return [
        str(fact.get("claim", ""))
        for fact in evidence.get("facts", [])
        if (fact.get("sourceRef", {}).get("document"), fact.get("sourceRef", {}).get("section")) in keys
    ]


def _max_items(role: str) -> int:
    if role in {"cover", "section", "questions"}:
        return 2
    return 5 if role in {"method", "architecture", "evidence", "content"} else 4


class _PageIssues:
    """Issue collector for one page, with the reference-stripping repair."""

    def __init__(self, position: int, known_refs: set[str]):
        self.position = position
        self.known_refs = known_refs
        self.items: list[dict] = []

    def flag(self, code: str, field: str, severity: str = "repaired", **detail) -> None:
        self.items.append({"position": self.position, "code": code, "severity": severity, "field": field,
                           "message": MESSAGES[code], **({"detail": detail} if detail else {})})

    def strip_refs(self, text: str, field: str) -> str:
        unknown = [match.group(1) for match in INLINE_REF_RE.finditer(text) if match.group(1) not in self.known_refs]
        if unknown:
            self.flag("unknown-evidence-ref", field, refs=unknown[:6])
            for ref in unknown:
                text = re.sub(r"[\[（(]\s*" + re.escape(ref) + r"\s*[\]）)]", "", text)
        return text.strip()


def _conclusion_positions(slides: list[dict]) -> set[int]:
    total = len(slides)
    positions = {total}
    if total >= 2 and slides[-1].get("role") == "questions":
        positions.add(total - 1)
    return positions


def validate_page_proposals(
    plan: dict,
    proposals: dict[int, dict],
    *,
    preset: str,
    deck_title: str = "",
    extra_pages: int = 0,
    facts_by_position: dict[int, list[str]] | None = None,
) -> dict:
    """Check, repair or reject each model proposal; annotate ``plan['slides']`` with issues."""
    slides = plan.get("slides", [])
    evidence = plan.get("evidence", {})
    total = len(slides)
    roles = allowed_roles(preset)
    conclusion_positions = _conclusion_positions(slides)
    evidence_ids = {fact.get("id") for fact in evidence.get("facts", [])} | {
        metric.get("id") for metric in evidence.get("metrics", [])
    }
    issues: list[dict] = []
    repaired: dict[int, dict] = {}
    fallback_positions: list[int] = []
    accepted_titles: list[str] = []

    if extra_pages:
        issues.append({"position": None, "code": "extra-pages", "severity": "warning", "field": "slides",
                       "message": MESSAGES["extra-pages"], "detail": {"count": extra_pages}})

    for slide in slides:
        position = int(slide["position"])
        base_title = str(slide.get("content", {}).get("title", ""))
        base_role = str(slide.get("role", "content"))
        page_sections = {str(ref.get("section")) for ref in slide.get("sourceRefs", [])}
        page = _PageIssues(position, {str(ref) for ref in evidence_ids} | page_sections)
        flag, strip_refs, page_issues = page.flag, page.strip_refs, page.items

        proposal = proposals.get(position)
        if not isinstance(proposal, dict):
            flag("missing-page", "slide", "fallback")
            fallback_positions.append(position)
            accepted_titles.append(base_title)
            slide["proposalIssues"] = page_issues
            issues.extend(page_issues)
            continue
        item = dict(proposal)

        # --- structure: allowed roles, cover first, conclusion last -------------------------
        role = str(item.get("role") or base_role).strip().lower()
        if role not in roles:
            flag("role-not-allowed", "role", proposed=role)
            role = base_role
        if role == "cover" and position != 1:
            flag("cover-not-first", "role")
            role = base_role if base_role != "cover" else "content"
        if position == 1 and role != "cover":
            flag("first-page-not-cover", "role", proposed=role)
            role = "cover"
        if role == "conclusion" and position not in conclusion_positions and base_role != "conclusion":
            flag("conclusion-not-last", "role")
            role = base_role
        if position == total and total > 1 and role not in {"conclusion", "questions"}:
            flag("last-page-not-conclusion", "role", proposed=role)
            role = base_role if base_role in {"conclusion", "questions"} else "conclusion"
        item["role"] = role

        # --- evidence references must exist ------------------------------------------------
        for field in REF_FIELDS:
            if field in item and isinstance(item[field], list):
                kept = [ref for ref in item[field] if str(ref) in evidence_ids or str(ref) in page_sections]
                unknown = [str(ref) for ref in item[field] if ref not in kept]
                if unknown:
                    flag("unknown-evidence-ref", field, refs=unknown[:6])
                item[field] = kept

        # --- numbers must come from the page's permitted facts -----------------------------
        facts = (facts_by_position or {}).get(position)
        if facts is None:
            facts = page_fact_claims(evidence, slide)
        base_text = " ".join([
            base_title, str(slide.get("message", "")), str(slide.get("purpose", "")),
            *map(str, slide.get("content", {}).get("bullets", [])),
        ])
        allowed_numbers = strict_numbers(" ".join([*facts, base_text, deck_title]))

        title = strip_refs(str(item.get("title") or base_title).strip(), "title")
        if _numbers_allowed(title, allowed_numbers):
            flag("unsupported-number", "title", values=_numbers_allowed(title, allowed_numbers))
            title = base_title
        if len(title) > MAX_TITLE:
            flag("title-too-long", "title", length=len(title))
            title = base_title
        message = strip_refs(str(item.get("message") or "").strip(), "message")
        if message and _numbers_allowed(message, allowed_numbers):
            flag("unsupported-number", "message", values=_numbers_allowed(message, allowed_numbers))
            message = str(slide.get("message", ""))
        if len(message) > MAX_MESSAGE:
            flag("message-too-long", "message", length=len(message))
            message = str(slide.get("message", ""))
        purpose = str(item.get("purpose") or "").strip()
        if purpose and _numbers_allowed(purpose, allowed_numbers):
            flag("unsupported-number", "purpose", values=_numbers_allowed(purpose, allowed_numbers))
            purpose = str(slide.get("purpose", ""))

        raw_bullets = item.get("bullets") if isinstance(item.get("bullets"), list) else []
        bullets = []
        rejected_bullets = 0
        for value in raw_bullets:
            text = strip_refs(str(value or ""), "bullets")
            unsupported = _numbers_allowed(text, allowed_numbers)
            if unsupported:
                flag("unsupported-number", "bullets", values=unsupported)
                rejected_bullets += 1
                continue
            if text:
                bullets.append(text)

        # --- titles must not repeat earlier pages -------------------------------------------
        if role not in NAVIGATION_ROLES and position != 1:
            duplicate = next((earlier for earlier in accepted_titles if _key(earlier) == _key(title)), None)
            near = duplicate or next((earlier for earlier in accepted_titles if near_duplicate(earlier, title)), None)
            if near:
                flag("duplicate-title" if duplicate else "near-duplicate-title", "title", previous=near)
                replacement = next(
                    (candidate for candidate in (base_title, str(slide.get("purpose", ""))[:36])
                     if candidate and not any(near_duplicate(earlier, candidate) for earlier in accepted_titles)),
                    None,
                )
                title = replacement or base_title

        # --- page and text budgets ---------------------------------------------------------
        limit = _max_items(role)
        if len(bullets) > limit:
            flag("too-many-bullets", "bullets", count=len(bullets), limit=limit)
            bullets = bullets[:limit]
        density = int((slide.get("constraints") or {}).get("maxTextDensity") or 520)
        while len(bullets) > 1 and len(title) + len(message) + sum(map(len, bullets)) > density:
            bullets.pop()
            if not any(issue["code"] == "text-budget" for issue in page_issues):
                flag("text-budget", "bullets", limit=density)

        severe = sum(issue["severity"] == "repaired" for issue in page_issues)
        lost_all_copy = bool(raw_bullets) and not bullets and rejected_bullets == len(raw_bullets)
        if lost_all_copy or severe >= 4:
            flag("fallback", "slide", "fallback", repairs=severe)
            fallback_positions.append(position)
            accepted_titles.append(base_title)
        else:
            item.update({"title": title, "message": message or item.get("message"), "bullets": bullets})
            if purpose:
                item["purpose"] = purpose
            repaired[position] = item
            accepted_titles.append(title)
        slide["proposalIssues"] = page_issues
        issues.extend(page_issues)

    by_code = Counter(issue["code"] for issue in issues)
    repaired_pages = {issue["position"] for issue in issues if issue["severity"] == "repaired"} - set(fallback_positions)
    return {
        "version": "page-proposal-validation-v1",
        "proposals": repaired,
        "issues": issues,
        "fallbackPositions": fallback_positions,
        "summary": {
            "pages": total,
            "accepted": len(repaired) - len(repaired_pages & set(repaired)),
            "repaired": len(repaired_pages & set(repaired)),
            "fallback": len(fallback_positions),
            "byCode": dict(by_code),
        },
    }
