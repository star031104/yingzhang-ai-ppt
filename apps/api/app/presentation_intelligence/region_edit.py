"""Map a rectangle drawn on a rendered slide to editable content objects.

The renderer stores a measured scene (``<variant>.scene.json``) for every
candidate. Its nodes carry bounding boxes in 1280x720 slide coordinates and the
visible text, so a selection can be resolved to the slide spec objects
(title, message, bullets, the main visual) that produced those nodes. The
instruction is then turned into deterministic object edits; no model is needed.
"""

import re
from difflib import SequenceMatcher

SLIDE_WIDTH, SLIDE_HEIGHT = 1280, 720
VISUAL_NODE_TYPES = {"chart": "chart", "table": "table", "diagram": "diagram", "image": "image", "svg": "image", "video": "media"}
VISUAL_LABELS = {"chart": "图表", "table": "表格", "diagram": "关系图", "image": "图片", "media": "媒体"}
_SOURCE_MARK = re.compile(r"[（(]\s*(?:S|SRC)\s*\d*\s*[）)]|\[\s*(?:S|SRC)\s*\d+\s*\]", re.IGNORECASE)
_BADGE = re.compile(r"^\d{1,2}$")
_NUMBER = re.compile(r"\d")

# (pattern, primary visual, layout variant) — first match wins.
VISUAL_RULES = (
    (r"三步|三个步骤|三阶段|三个阶段", "diagram", "three-stage"),
    (r"时间线|时间轴|里程碑", "diagram", "timeline"),
    (r"流程|步骤|工作流", "diagram", "workflow"),
    (r"架构|分层", "diagram", "layered-architecture"),
    (r"指标卡|数字卡|大数字", "chart", "metric-wall"),
    (r"柱状|条形|折线|图表|曲线", "chart", "chart-focus"),
    (r"表格", "table", "table-highlight"),
    (r"前后对比|对比|对照", "diagram", "before-after"),
    (r"纯文字|文字叙事|列表", "typography", "content-list"),
)
CHANGE_VERB = r"(?:改成|改为|换成|变成|做成|转成|转换成|写成|替换为)"
VISUAL_VERB = rf"(?:{CHANGE_VERB[3:-1]}|呈现为|展示为|用|以)"
QUOTED = re.compile(r"[“\"「『'‘]([^”\"」』'’]+)[”\"」』'’]")
REPLACE_WITH = re.compile(rf"{CHANGE_VERB}\s*[：:]?\s*(.+)$")
APPEND_WITH = re.compile(r"(?:补充|追加|加上|添加|再加|增加)\s*[：:]?\s*(.+)$")
DELETE_WORDS = re.compile(r"删除|删掉|去掉|移除|不要了|拿掉")
EMPHASIS_WORDS = re.compile(r"加粗|突出|强调|高亮|醒目|放大|重点显示")
SHORTEN_WORDS = re.compile(r"精简|缩短|简洁|简短|压缩|太长")


class RegionEditError(ValueError):
    pass


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", _SOURCE_MARK.sub("", str(text or ""))).lower()


def _match_score(node_text: str, candidate: str) -> float:
    node, target = _norm(node_text), _norm(candidate)
    if not node or not target or _BADGE.match(node):
        return 0.0
    if node == target:
        return 1.0
    if len(node) >= 2 and node in target:
        return 0.6 + 0.4 * len(node) / len(target)
    if len(target) >= 4 and target in node:
        return 0.55 + 0.4 * len(target) / len(node)
    ratio = SequenceMatcher(None, node, target).ratio()
    return ratio * 0.95 if ratio >= 0.6 else 0.0


def _content_candidates(spec: dict) -> list[dict]:
    content = spec.get("content") or {}
    items = [{"kind": "title", "text": str(content.get("title") or "")}]
    items += [{"kind": "bullet", "index": index, "text": str(text)} for index, text in enumerate(content.get("bullets") or [])]
    items.append({"kind": "message", "text": str(spec.get("message") or "")})
    return [item for item in items if item["text"].strip()]


def _overlap(box: dict, region: dict) -> tuple[float, float]:
    width = min(box["x"] + box["width"], region["x"] + region["width"]) - max(box["x"], region["x"])
    height = min(box["y"] + box["height"], region["y"] + region["height"]) - max(box["y"], region["y"])
    if width <= 0 or height <= 0:
        return 0.0, 0.0
    area = width * height
    return area / max(1.0, box["width"] * box["height"]), area / max(1.0, region["width"] * region["height"])


def normalize_region(bbox: dict) -> dict:
    x = max(0.0, min(float(bbox["x"]), SLIDE_WIDTH))
    y = max(0.0, min(float(bbox["y"]), SLIDE_HEIGHT))
    width = max(0.0, min(float(bbox["width"]), SLIDE_WIDTH - x))
    height = max(0.0, min(float(bbox["height"]), SLIDE_HEIGHT - y))
    if width < 4 or height < 4:
        raise RegionEditError("框选区域太小，请拖出一个更大的范围")
    return {"x": x, "y": y, "width": width, "height": height}


def assign_nodes(scene: dict, spec: dict) -> dict[str, dict]:
    """Assign every measured text node of the scene to at most one content object.

    Assignment runs over the whole scene (top to bottom) so that repeated text,
    e.g. a message that restates the first bullet, resolves the same way
    regardless of which part of the slide is selected.
    """
    candidates = _content_candidates(spec)
    used: set[tuple] = set()
    assigned: dict[str, dict] = {}
    nodes = [node for node in scene.get("nodes") or [] if node.get("type") == "text" and node.get("isTextLeaf")]
    nodes.sort(key=lambda node: (node["bbox"]["y"], node["bbox"]["x"]))
    for node in nodes:
        if node.get("region") in {"footer", "header"} and node.get("tag") != "h1":
            continue
        scored = []
        for order, candidate in enumerate(candidates):
            score = _match_score(node.get("text", ""), candidate["text"])
            if node.get("tag") == "h1" and candidate["kind"] == "title":
                score += 0.2
            key = (candidate["kind"], candidate.get("index"))
            if score >= 0.6:
                scored.append((key in used, -score, order, candidate, key))
        if not scored:
            continue
        _, negative, _, candidate, key = min(scored)
        used.add(key)
        target = {key: value for key, value in candidate.items() if key != "text"}
        if candidate["kind"] == "bullet" and _NUMBER.search(node.get("text", "")) and len(_norm(node.get("text", ""))) <= 12:
            target["metric"] = True
        assigned[node["id"]] = {"target": target, "score": round(-negative, 3)}
    return assigned


def target_label(target: dict) -> str:
    kind = target.get("kind")
    if kind == "title":
        return "页面标题"
    if kind == "message":
        return "核心结论"
    if kind == "bullet":
        return f"第 {int(target.get('index', 0)) + 1} 条要点" + ("（数字）" if target.get("metric") else "")
    return VISUAL_LABELS.get(str(target.get("object")), "主视觉")


def targets_in_region(scene: dict, spec: dict, bbox: dict) -> list[dict]:
    """Return the content objects whose rendered nodes fall inside ``bbox``."""
    region = normalize_region(bbox)
    assigned = assign_nodes(scene, spec)
    found: dict[tuple, dict] = {}
    for node in scene.get("nodes") or []:
        node_ratio, region_ratio = _overlap(node["bbox"], region)
        if node_ratio < 0.5 and region_ratio < 0.6:
            continue
        weight = max(node_ratio, region_ratio)
        visual = VISUAL_NODE_TYPES.get(str(node.get("type")))
        if visual:
            target = {"kind": "visual", "object": visual}
        elif node["id"] in assigned:
            target = dict(assigned[node["id"]]["target"])
        else:
            continue
        key = (target["kind"], target.get("index"), target.get("object"))
        entry = found.setdefault(key, {**target, "nodeIds": [], "weight": 0.0})
        entry["nodeIds"].append(node["id"])
        entry["weight"] = max(entry["weight"], weight)
        entry["metric"] = bool(entry.get("metric") or target.get("metric"))
        if not entry["metric"]:
            entry.pop("metric")
    targets = sorted(found.values(), key=lambda item: -item["weight"])
    for target in targets:
        target["weight"] = round(target["weight"], 3)
        target["label"] = target_label(target)
    return targets


VISUAL_FILLER = re.compile(r"图|形式|样式|的|展示|呈现|结构|版式|布局|一个|个|来|方式|这里|这块|这部分|[\s，。：:]")


def _visual_rule(text: str, only_visual_targets: bool):
    """Return (primary visual, variant) when the instruction asks for a layout change.

    "改成三步流程" is a layout request, while "改成 Q3 营收对比" is new text that
    merely contains a layout word; the tail after the verb must consist only of
    layout words unless the selection contains nothing but graphics.
    """
    verb = re.search(VISUAL_VERB, text)
    if not verb:
        return None
    tail = text[verb.end():]
    for pattern, primary, variant in VISUAL_RULES:
        if re.search(pattern, tail):
            leftover = tail
            for rule_pattern, _, _ in VISUAL_RULES:
                leftover = re.sub(rule_pattern, "", leftover)
            if only_visual_targets or len(VISUAL_FILLER.sub("", leftover)) <= 1:
                return primary, variant
            return None
    return None


def _shorten(text: str) -> str:
    clauses = [part for part in re.split(r"[，。；;,.！!？?]", text) if part.strip()]
    first = clauses[0].strip() if clauses else text.strip()
    return first if 4 <= len(first) < len(text.strip()) else text.strip()[: max(8, len(text.strip()) // 2)]


def plan_region_edit(instruction: str, targets: list[dict], spec: dict) -> list[dict]:
    """Translate an instruction for the selected targets into object edits.

    Each edit is ``{"target", "operation", "value"}`` and is applied with
    :func:`apply_object_edit`. Raises :class:`RegionEditError` when the
    instruction cannot be resolved deterministically.
    """
    text = instruction.strip()
    if not targets:
        raise RegionEditError("框选区域内没有可编辑的标题、要点或图表，请重新框选")
    text_targets = [target for target in targets if target["kind"] in {"title", "message", "bullet"}]
    bullets = [target for target in text_targets if target["kind"] == "bullet"]
    clean = lambda target: {key: value for key, value in target.items() if key in {"kind", "index"}}
    quoted = QUOTED.search(text)
    rule = None if quoted else _visual_rule(text, not text_targets)
    if rule:
        primary, variant = rule
        return [{"target": {"kind": "visual", "variant": variant}, "operation": "replace", "value": primary}]
    if DELETE_WORDS.search(text) and not quoted:
        removable = [target for target in text_targets if target["kind"] != "title"]
        if not removable:
            raise RegionEditError("页面标题不能删除，可以改为“改为：新的标题”")
        ordered = sorted(removable, key=lambda target: -int(target.get("index", -1)))
        return [{"target": clean(target), "operation": "delete", "value": None} for target in ordered]
    if EMPHASIS_WORDS.search(text) and not quoted:
        if not bullets:
            raise RegionEditError("标题和核心结论已使用最高层级，框选要点或数字后再要求突出")
        edits = [
            {"target": {"kind": "bullet", "index": int(target["index"]), "to": rank}, "operation": "move", "value": None}
            for rank, target in enumerate(sorted(bullets, key=lambda target: int(target["index"])))
        ]
        # Moving earlier bullets first keeps the requested order stable.
        variant = (spec.get("visualIntent") or {}).get("selectedVariant")
        if any(target.get("metric") for target in bullets) and variant not in {"metric-wall", "scorecard", "chart-focus"}:
            edits.append({"target": {"kind": "visual", "variant": "metric-wall"}, "operation": "replace", "value": "chart"})
        return edits
    if not text_targets:
        raise RegionEditError("框选的是图形区域，可以输入“改成流程图”“改成图表”或“改成表格”")
    primary = text_targets[0]
    if SHORTEN_WORDS.search(text) and not quoted:
        current = _target_text(spec, primary)
        return [{"target": clean(primary), "operation": "replace", "value": _shorten(current)}]
    appended = APPEND_WITH.search(text)
    if appended and not quoted:
        value = appended.group(1).strip().strip("。")
        return [{"target": clean(primary), "operation": "append", "value": f"，{value}"}]
    replacement = quoted.group(1) if quoted else None
    if replacement is None:
        match = REPLACE_WITH.search(text)
        replacement = match.group(1) if match else None
    if replacement and replacement.strip():
        return [{"target": clean(primary), "operation": "replace", "value": replacement.strip().strip("。")}]
    raise RegionEditError("暂时无法理解这条指令。可以写“改为：新内容”“删除”“突出这个数字”或“改成三步流程”")


def _target_text(spec: dict, target: dict) -> str:
    content = spec.get("content") or {}
    if target["kind"] == "title":
        return str(content.get("title") or "")
    if target["kind"] == "message":
        return str(spec.get("message") or "")
    return str((content.get("bullets") or [""])[int(target["index"])])
