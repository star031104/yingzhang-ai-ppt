"""Audience-facing claim selection and numeric evidence guards."""

import re

from app.intelligence.content_selection import query_terms
from app.intelligence.numeric_claims import numeric_claim_bindings, strict_numbers


def strip_internal_source_markers(value: object) -> str:
    return re.sub(
        r"\s*[（(\[]\s*(?:S|SRC)\s*\d*(?:\s*[-,，]\s*(?:S|SRC)?\s*\d+)*\s*[）)\]]\s*",
        " ",
        str(value or ""),
        flags=re.IGNORECASE,
    ).strip()


def clean_audience_bullet(value: object) -> str:
    """Return a complete, audience-facing bullet or an empty string for model debris."""
    text = re.sub(r"\s*\[\s*\d+(?:\s*[-,，]\s*\d+)*\s*\]\s*", "", str(value or ""))
    text = strip_internal_source_markers(text)
    text = re.sub(r"\s+", " ", text).strip(" ：:、，,；;。.")
    if re.search(r"统一标题风格|避免标题过长|(?:保留|移[至入]|放).{0,16}(?:message|title|bullets)\b", text, re.IGNORECASE):
        return ""
    if re.match(r"^\d+(?:\.\d+){1,3}\s+", text):
        return ""
    text = re.sub(r"^[（(]\d+[）)]\s*", "", text)
    if not text or re.fullmatch(r"[\d\W_]+", text):
        return ""
    if re.match(r"^(?:果的|的|与|及|和|或|以及|其中|所示|如表|如图)", text):
        return ""
    labeled_metric = bool(re.match(r"(?:[A-Za-z][\w@-]+|[\u4e00-\u9fff]{2,})\s*[:：]\s*\d", text))
    if len(re.findall(r"[\u4e00-\u9fffA-Za-z]", text)) < 5 and not labeled_metric:
        return ""
    if re.search(r"如[表图]\s*\d+(?:[-－.]\d+)?\s*所示$", text):
        return ""
    # Conditions often follow a comma. Keep the claim intact; layout handles capacity.
    return text


def fit_audience_bullet(value: object, limit: int = 84) -> str:
    """Keep slide copy readable while retaining the full source in speaker notes."""
    text = clean_audience_bullet(value)
    if len(text) <= limit:
        return text
    # A short bullet is not worth silently removing a caveat that changes the
    # meaning of a claim. Leave it intact; density checks can flag the slide.
    if re.search(
        r"但|然而|仅限|仅在|不代表|不能|不足|尚未|仍需|局限|边界|前提|风险|限制|however|only|limitation|not yet",
        text,
        flags=re.IGNORECASE,
    ):
        return text
    # A character-based cut can turn 1,200 into 1 or 89.6% into 89. Keep the
    # complete metric claim and let layout validation report excess density.
    if strict_numbers(text):
        return text
    sentence = re.split(r"[。！？；;]", text, maxsplit=1)[0].strip()
    if 18 <= len(sentence) <= limit:
        return sentence
    candidate = text[: limit + 1]
    cut = max(candidate.rfind("，"), candidate.rfind(","), candidate.rfind("、"))
    if cut >= 28:
        return candidate[:cut].rstrip()
    return text[: limit - 1].rstrip() + "…"


def useful_evidence_claim(value: object) -> str:
    raw = str(value or "").strip()
    if re.search(r"[,，]\s*$", raw) or re.search(r"(?:对于|以及|并且|但是|其中)\s*$", raw):
        return ""
    text = clean_audience_bullet(value)
    if (
        not text
        or len(re.findall(r"[\u4e00-\u9fff]", text)) < 4
        or re.match(r"^[表图]\s*\d", text)
        or (
            len(re.findall(r"(?:MRR|Hit@\d+|nDCG@\d+|Accuracy|Precision|Recall|F1)", text, flags=re.IGNORECASE)) >= 3
            and not re.search(r"(?:达到|提升|下降|表明|说明|高于|低于|为)", text)
        )
    ):
        return ""
    return text


def ranked_evidence_claims(evidence: dict, refs: list[dict], query: str) -> list[str]:
    keys = {(ref.get("document"), ref.get("section")) for ref in refs}
    terms = set(re.findall(r"[A-Za-z][\w@-]{2,}|[\u4e00-\u9fff]{2,6}", query.lower()))
    ranked: list[tuple[float, str, tuple[str | None, str | None]]] = []
    seen: set[str] = set()
    for fact in evidence.get("facts", []):
        source_ref = fact.get("sourceRef", {})
        if (source_ref.get("document"), source_ref.get("section")) not in keys:
            continue
        claim = useful_evidence_claim(fact.get("claim"))
        if not claim or claim in seen:
            continue
        seen.add(claim)
        lowered = claim.lower()
        overlap = sum(1 for term in terms if term in lowered)
        metric_bonus = 8 if strict_numbers(claim) else 0
        sentence_bonus = 2 if re.search(r"[。！？；;]$", str(fact.get("claim", "")).strip()) else 0
        source_key = (source_ref.get("document"), source_ref.get("section"))
        ranked.append((metric_bonus + overlap * 1.5 + sentence_bonus + min(len(claim), 60) / 100, claim, source_key))
    ranked.sort(key=lambda item: (-item[0], -len(item[1])))
    diverse: list[str] = []
    used_sources: set[tuple[str | None, str | None]] = set()
    for _, claim, source_key in ranked:
        if source_key not in used_sources:
            diverse.append(claim)
            used_sources.add(source_key)
    diverse.extend(claim for _, claim, source_key in ranked if source_key in used_sources and claim not in diverse)
    return diverse


def referenced_metric_claims(
    responsibility: str, refs: list[dict], sources: list[dict]
) -> list[str]:
    """Select metric-bearing claims from cited material without topic-specific copy."""
    if not re.search(
        r"result|experiment|evaluation|metric|comparison|financial|revenue|cost|benchmark|"
        r"实验|结果|评估|指标|对比|性能|财务|收入|成本|收益|统计|耗时|利润",
        responsibility,
        flags=re.IGNORECASE,
    ):
        return []
    keys = {(ref.get("document"), ref.get("section")) for ref in refs}
    terms = set(re.findall(r"[A-Za-z][\w@-]{2,}|[\u4e00-\u9fff]{2,6}", responsibility.lower()))
    ranked: list[tuple[float, str]] = []
    seen: set[str] = set()
    for source in sources:
        for section in source.get("sections", []):
            if (source.get("name"), section.get("id")) not in keys:
                continue
            # Preserve the source sentence or table row. Do not infer why a
            # value changed, or label a result as good/bad without evidence.
            fragments = re.split(r"[\n\r。！？]+", str(section.get("text", "")))
            for index, fragment in enumerate(fragments):
                claim = useful_evidence_claim(fragment)
                # Carry an adjacent qualification with its numeric result so
                # shortening the source sentence cannot erase its boundary.
                if claim and strict_numbers(claim) and index + 1 < len(fragments):
                    qualifier = useful_evidence_claim(fragments[index + 1])
                    if qualifier and re.search(
                        r"但|然而|仅限|仅在|不代表|不能|不足|尚未|仍需|局限|边界|前提|风险|限制|however|only|limitation|not yet",
                        qualifier,
                        flags=re.IGNORECASE,
                    ):
                        claim = f"{claim}；{qualifier}"
                if not claim or not strict_numbers(claim) or claim in seen or len(claim) > 220:
                    continue
                seen.add(claim)
                lowered = claim.lower()
                overlap = sum(1 for term in terms if term in lowered)
                metric_label = bool(re.search(
                    r"accuracy|precision|recall|f1|mrr|ndcg|hit@|准确率|召回率|精确率|完整率|支撑率|耗时|成本|收入|利润|增长率",
                    lowered,
                ))
                ranked.append((overlap * 2 + (5 if metric_label else 0) + min(len(claim), 80) / 100, claim))
    ranked.sort(key=lambda item: (-item[0], len(item[1])))
    return [claim for _, claim in ranked[:4]]


def sanitize_numeric_claims(slide: dict, evidence: dict, sources: list[dict]) -> None:
    refs = slide.get("sourceRefs", [])
    keys = {(ref.get("document"), ref.get("section")) for ref in refs}
    referenced_text = " ".join(
        section.get("text", "")
        for source in sources for section in source.get("sections", [])
        if (source["name"], section["id"]) in keys
    )
    allowed = strict_numbers(referenced_text)
    source_bindings = numeric_claim_bindings(referenced_text)
    facts = [
        cleaned for fact in evidence.get("facts", [])
        if (fact["sourceRef"].get("document"), fact["sourceRef"].get("section")) in keys
        if (cleaned := useful_evidence_claim(fact.get("claim")))
    ]
    clean = []
    for bullet in slide.get("content", {}).get("bullets", []):
        bullet_text = clean_audience_bullet(bullet)
        if not bullet_text:
            continue
        unsupported = strict_numbers(bullet_text) - allowed
        relation_mismatch = "下降" in bullet_text and "下降到" not in bullet_text and any("下降到" in fact for fact in facts)
        claim_bindings = numeric_claim_bindings(bullet_text)
        binding_mismatch = False
        for label, numbers in claim_bindings.items():
            matching_labels = [
                source_label for source_label in source_bindings
                if source_label == label or source_label in label or label in source_label
            ]
            if matching_labels:
                binding_mismatch |= any(
                    number not in set().union(*(source_bindings[key] for key in matching_labels))
                    for number in numbers
                )
            elif source_bindings:
                # If the source has labels and a numeric claim introduces an
                # unmatched label, it cannot inherit another entity's value.
                binding_mismatch = True
        if unsupported or relation_mismatch or binding_mismatch:
            if facts:
                matching = max(facts, key=lambda fact: len(query_terms(fact) & query_terms(bullet_text)))
                clean.append(matching)
            else:
                # Deleting only a number can turn a fabricated measurement into a false claim.
                continue
        else:
            clean.append(bullet_text)
    slide["content"]["bullets"] = list(dict.fromkeys(clean))
    for field, fallback in (("title", "关键结果"),):
        value = str(slide.get("content", {}).get(field, ""))
        mismatch = bool(strict_numbers(value) - allowed)
        if value and not mismatch:
            for label, numbers in numeric_claim_bindings(value).items():
                labels = [key for key in source_bindings if key == label or key in label or label in key]
                if (labels and any(number not in set().union(*(source_bindings[key] for key in labels)) for number in numbers)) or (source_bindings and not labels):
                    mismatch = True
                    break
        if mismatch:
            slide["content"][field] = fallback
    message = str(slide.get("message", ""))
    message_mismatch = bool(strict_numbers(message) - allowed)
    if message and not message_mismatch:
        for label, numbers in numeric_claim_bindings(message).items():
            labels = [key for key in source_bindings if key == label or key in label or label in key]
            if (labels and any(number not in set().union(*(source_bindings[key] for key in labels)) for number in numbers)) or (source_bindings and not labels):
                message_mismatch = True
                break
    if message_mismatch:
        slide["message"] = facts[0] if facts else slide["content"].get("title", "")
