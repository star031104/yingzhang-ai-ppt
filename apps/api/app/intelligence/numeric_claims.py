"""Conservative normalization for source-bound numeric statements."""

import re

STRICT_NUMBER_PATTERN = (
    r"[+\-−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*"
    r"(?:%|个百分点|倍|万|亿|ms|毫秒|秒|分|分钟|小时|KB|MB|GB|TB|条|个|项|份|人|页)?"
)
METRIC_ALIASES = {
    "accuracy": ("accuracy", "准确率", "正确率"),
    "precision": ("precision", "精确率", "查准率"),
    "recall": ("recall", "召回率", "查全率"),
    "f1": ("f1-score", "f1 score", "f1", "调和平均"),
    "revenue": ("revenue", "营收", "收入"),
    "conversion": ("conversion rate", "转化率"),
    "retention": ("retention rate", "留存率"),
}


def strict_numbers(text: str) -> set[str]:
    cleaned = re.sub(r"\b(?:S|F|M|SRC)\s*\d+\b", "", text or "", flags=re.IGNORECASE)
    return {
        re.sub(r"[\s,]", "", value).replace("−", "-").lower()
        for value in re.findall(STRICT_NUMBER_PATTERN, cleaned, flags=re.IGNORECASE)
    }


def numeric_claim_bindings(text: str) -> dict[str, set[str]]:
    """Map a nearby metric/entity label to the complete numeric values it states."""
    found: dict[str, set[str]] = {}
    for match in re.finditer(STRICT_NUMBER_PATTERN, text or "", flags=re.IGNORECASE):
        prefix = text[:match.start()]
        if re.search(r"(?:第|S|SRC|F|M)\s*$", prefix, flags=re.IGNORECASE):
            continue
        label = re.split(r"[。；;\n,，]", prefix)[-1]
        label = re.sub(r"[：:、\s]+", "", label).replace("的", "")
        label = re.sub(
            r"(?:分别|约为|达到|为|是|从|提升至|提升到|下降至|下降到|降至|增长到|减少到|等于|约)$",
            "",
            label,
        )
        label = label[-40:].lower()
        for canonical, aliases in METRIC_ALIASES.items():
            for alias in sorted(aliases, key=len, reverse=True):
                label = re.sub(re.escape(alias), canonical, label, flags=re.IGNORECASE)
        if len(label) >= 2:
            value = re.sub(r"[\s,]", "", match.group()).replace("−", "-").lower()
            found.setdefault(label, set()).add(value)
    return found


def numeric_binding_mismatches(claim: str, evidence: str) -> list[dict]:
    """Find values attached to a different or unsupported source label."""
    source = numeric_claim_bindings(evidence)
    if not source:
        return []
    mismatches = []
    all_source_values = set().union(*source.values())
    for label, values in numeric_claim_bindings(claim).items():
        matches = [key for key in source if key == label or key in label or label in key]
        if not matches:
            reused = sorted(values & all_source_values)
            if reused:
                mismatches.append({"label": label, "values": reused})
            continue
        supported = set().union(*(source[key] for key in matches))
        unsupported = sorted(values - supported)
        if not matches or unsupported:
            mismatches.append({"label": label, "values": unsupported or sorted(values)})
    return mismatches
