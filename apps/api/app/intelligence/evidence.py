import re
from collections import Counter

DECIMAL_MARK = "\uFFF0"
METRIC_RE = re.compile(
    r"(?<![A-Za-z0-9_.@第表图])[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*"
    r"(?:%|个百分点|倍|万|亿|ms|毫秒|s|秒|分钟|小时|KB|MB|GB|TB|条|个|项|份|人|页)?",
    re.IGNORECASE,
)
STOP = {
    "the", "and", "for", "with", "this", "that", "from", "are", "was",
    "一个", "以及", "可以", "进行", "通过", "研究", "结果", "方法",
}


def split_sentences(text: str) -> list[str]:
    """Split prose without treating decimal points such as 71.2 as sentence boundaries."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in (text or "").splitlines()]

    def structural(line: str) -> bool:
        return bool(
            not line
            or re.fullmatch(r"[•·]", line)
            or re.fullmatch(r"\d+(?:\.\d+)?%?", line)
            or re.match(r"^(?:第\s*\d+\s*页|[表图]\s*\d|\d+(?:\.\d+){1,3}\s|[（(]\d+[）)])", line)
        )

    blocks: list[str] = []
    current = ""
    previous = ""
    for line in lines:
        if not line:
            if current:
                blocks.append(current)
                current = ""
            previous = ""
            continue
        if not current:
            current, previous = line, line
            continue
        if structural(previous) or structural(line) or re.search(r"[。！？!?；;：:]$", previous):
            blocks.append(current)
            current = line
        else:
            separator = " " if re.search(r"[A-Za-z0-9]$", current) and re.match(r"[A-Za-z0-9]", line) else ""
            current += separator + line
        previous = line
    if current:
        blocks.append(current)

    protected = re.sub(r"(?<=\d)\.(?=\d)", DECIMAL_MARK, "\n".join(blocks))
    parts = re.split(r"(?<=[。！？!?])\s*|(?<=\.)\s+|\n+", protected)
    return [part.replace(DECIMAL_MARK, ".").strip() for part in parts if part.strip()]


def _metric(raw: str, metric_id: str, claim_id: str, source_ref: dict) -> dict:
    compact = re.sub(r"\s+", "", raw)
    number = re.search(r"[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", compact)
    unit = compact[number.end():] if number else ""
    return {
        "id": metric_id,
        "claimId": claim_id,
        "raw": compact,
        "value": float(number.group().replace(",", "").replace("−", "-")) if number else None,
        "unit": unit,
        "sourceRef": source_ref,
        "strict": True,
    }


def extract_evidence_graph(sources: list[dict]) -> dict:
    facts: list[dict] = []
    metrics: list[dict] = []
    nodes: list[dict] = []
    edges: list[dict] = []
    terms: Counter = Counter()
    seen_sections: set[tuple[str, str]] = set()
    for source in sources:
        for section in source.get("sections", []):
            source_ref = {
                "document": source["name"],
                "section": section["id"],
                "page": section.get("page"),
            }
            section_key = (source["name"], section["id"])
            section_node_id = f"SRC:{source['name']}:{section['id']}"
            if section_key not in seen_sections:
                nodes.append({"id": section_node_id, "type": "source", "sourceRef": source_ref})
                seen_sections.add(section_key)
            for sentence in split_sentences(section.get("text", "")):
                if re.match(r"^(?:图|表|Figure|Table)\s*\d", sentence, re.IGNORECASE) or sentence == section.get("title"):
                    continue
                matches = [match.group().strip() for match in METRIC_RE.finditer(sentence)]
                if not matches and len(sentence) < 12:
                    continue
                claim_id = f"F{len(facts) + 1:04d}"
                metric_ids = []
                for raw in matches:
                    metric_id = f"M{len(metrics) + 1:04d}"
                    metrics.append(_metric(raw, metric_id, claim_id, source_ref))
                    nodes.append({"id": metric_id, "type": "metric", "value": raw})
                    edges.append({"source": claim_id, "target": metric_id, "type": "ClaimToMetric"})
                    edges.append({"source": metric_id, "target": section_node_id, "type": "MetricToSource"})
                    metric_ids.append(metric_id)
                fact = {
                    "id": claim_id,
                    "claim": sentence,
                    "kind": "metric" if matches else "constraint" if re.search(r"但|仅限|不能|尚未|局限|前提|风险|限制", sentence) else "claim",
                    "sourceRef": source_ref,
                    "metricIds": metric_ids,
                    "strict": True,
                }
                facts.append(fact)
                nodes.append({"id": claim_id, "type": "claim", "claim": fact["claim"]})
                edges.append({"source": claim_id, "target": section_node_id, "type": "ClaimToSource"})
            terms.update(
                word.lower()
                for word in re.findall(r"[A-Za-z][\w-]{2,}|[\u4e00-\u9fff]{2,8}", section.get("text", ""))
                if word.lower() not in STOP
            )
    return {
        "version": "evidence-graph-v1",
        "facts": facts,
        "metrics": metrics,
        "nodes": nodes,
        "edges": edges,
        "keywords": [term for term, _ in terms.most_common(30)],
    }
