"""Extractive editorial selection: preserve claims and conditions before shortening copy."""
import re

from app.intelligence.evidence import split_sentences

LIMITATION = re.compile(r"但|然而|仅限|仅在|不代表|不能|不足|尚未|仍需|局限|边界|前提|风险|限制|however|only|limitation|not yet", re.IGNORECASE)
FINDING = re.compile(r"表明|说明|发现|结果|结论|建议|因此|优先|验证|实现|降低|提高|提升|支持|必须|应当|conclu|found|result|recommend", re.IGNORECASE)
PROCESS = re.compile(r"首先|其次|然后|最后|步骤|依次|输入|输出|阶段|first|then|finally|step", re.IGNORECASE)


def query_terms(value: str) -> set[str]:
    english = re.findall(r"[A-Za-z][\w@-]{2,}", value.lower())
    chinese = re.findall(r"[\u4e00-\u9fff]+", value)
    return {*english, *(part[i:i + 2] for part in chinese for i in range(len(part) - 1))}


def source_sentences(section: dict) -> list[str]:
    result = []
    source_text = section.get("text", "")
    abstract = re.search(r"摘\s*要\s*[:：]", source_text)
    if abstract and abstract.start() < 600:
        source_text = source_text[abstract.end():]
    source_text = "\n".join(line for line in source_text.splitlines()
                            if sum(map(len, re.findall(r"https?://\S+", line))) <= len(line) * 0.35)
    for sentence in split_sentences(source_text):
        text = re.sub(r"^\s*(?:[-*•]\s+|[（(]\d+[）)]\s*|\d+[、]\s*)", "", sentence).strip()
        urls = re.findall(r"https?://\S+", text)
        if sum(map(len, urls)) > len(text) * 0.35:
            continue
        text = re.sub(r"[,，]\s*(?:包括|分别为|如下)\s*[:：]?$", "", text)
        if len(text) < 6 or re.fullmatch(r"[\d\W_]+", text) or re.match(r"^(?:图|表|Figure|Table)\s*\d", text, re.IGNORECASE):
            continue
        if text == section.get("title") or re.match(r"^\[\d+]", text):
            continue
        if text not in result:
            result.append(text)
    return result


def select_key_points(section: dict, query: str = "", maximum: int = 4) -> list[str]:
    if maximum <= 0:
        return []
    sentences = source_sentences(section)
    # Flattened PDF tables are not audience prose. Keep their raw text in the
    # source model; use intact prose sentences instead of overflowing a slide.
    prose = [point for point in sentences if len(point) <= 240]
    if prose:
        sentences = prose
    if len(sentences) <= maximum:
        return sentences
    terms = query_terms(query or section.get("title", ""))
    def score(item):
        index, text = item
        overlap = len(terms & query_terms(text)) / max(1, len(terms))
        return (overlap * 8 + bool(FINDING.search(text)) * 4 + bool(LIMITATION.search(text)) * 3
                + bool(re.search(r"\d+(?:\.\d+)?\s*(?:%|秒|ms|万元)", text)) * 2
                - (2 if len(text) > 180 else 0) - index / max(1, len(sentences)))
    ranked = sorted(enumerate(sentences), key=score, reverse=True)
    selected = []
    # Important boundaries must not disappear simply because they occur at the end.
    boundary = next((item for item in ranked if LIMITATION.search(item[1])), None)
    if boundary and maximum >= 2:
        selected.append(boundary)
    for item in ranked:
        if item not in selected:
            selected.append(item)
        if len(selected) >= maximum:
            break
    return [text for _, text in sorted(selected)]


def section_understanding(section: dict) -> dict:
    points = select_key_points(section)
    findings = [point for point in points if FINDING.search(point) and not LIMITATION.search(point)]
    relation = "sequence" if sum(bool(PROCESS.search(point)) for point in points) >= 2 else "comparison" if len(section.get("tableIds", [])) else "explanation"
    return {"mainPoint": (findings or points or [section.get("title", "")])[0], "keyPoints": points,
            "limitations": [point for point in source_sentences(section) if LIMITATION.search(point)][:3],
            "relation": relation}


def concise_source_context(section: dict, budget: int, query: str = "") -> str:
    text = str(section.get("text", "")).strip()
    if len(text) <= budget:
        return text
    points = select_key_points(section, query, maximum=12)
    selected, used = [], 0
    # Budget by complete sentences, keeping tail findings and conditions discoverable.
    priority = sorted(enumerate(points), key=lambda pair: (not bool(LIMITATION.search(pair[1])), not bool(FINDING.search(pair[1])), pair[0]))
    for index, point in priority:
        if used + len(point) + 2 <= budget:
            selected.append((index, point))
            used += len(point) + 2
    return "\n\n".join(point for _, point in sorted(selected))


def retain_source_boundaries(original: list[str], proposed: list[str], maximum: int = 4) -> list[str]:
    """Keep source qualifications on the audience page when a model omits them."""
    boundaries = [point for point in original if LIMITATION.search(point)]
    missing = [point for point in boundaries if not any(point.rstrip("。.") in value for value in proposed)]
    if not missing:
        return proposed[:maximum]
    reserved = missing[:maximum]
    return list(dict.fromkeys([*proposed[:max(0, maximum - len(reserved))], *reserved]))
