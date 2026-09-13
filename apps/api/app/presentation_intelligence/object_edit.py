import copy
import re


ALLOWED_TARGETS = {"title", "message", "bullet", "bullets", "visual"}
ALLOWED_OPERATIONS = {"replace", "append", "delete", "move"}


def infer_edit_target(instruction: str) -> dict:
    text = instruction.strip()
    bullet = re.search(r"第\s*([一二三四五六七八九十\d]+)\s*(?:个|条)?要点", text)
    if bullet:
        raw = bullet.group(1)
        chinese = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        return {"kind": "bullet", "index": max(0, chinese.get(raw, int(raw) if raw.isdigit() else 1) - 1)}
    if "标题" in text:
        return {"kind": "title"}
    if any(word in text for word in ("结论", "核心观点", "核心判断")):
        return {"kind": "message"}
    return {"kind": "bullets"}


def apply_object_edit(
    spec: dict,
    instruction: str,
    target: dict | None = None,
    operation: str = "replace",
    value: str | list[str] | None = None,
) -> tuple[dict, dict]:
    target = dict(target or infer_edit_target(instruction))
    kind = str(target.get("kind", "")).strip()
    if kind not in ALLOWED_TARGETS:
        raise ValueError("不支持的页面对象")
    if operation not in ALLOWED_OPERATIONS:
        raise ValueError("不支持的修改操作")
    result = copy.deepcopy(spec)
    content = result.setdefault("content", {})
    bullets = list(content.get("bullets") or [])
    normalized = value.strip() if isinstance(value, str) else value
    before = None
    if kind == "title":
        before = str(content.get("title", ""))
        if operation == "delete":
            raise ValueError("页面标题不能删除")
        content["title"] = f"{before}{normalized}" if operation == "append" else str(normalized or "").strip()
        if not content["title"]:
            raise ValueError("页面标题不能为空")
    elif kind == "message":
        before = str(result.get("message", ""))
        result["message"] = "" if operation == "delete" else (
            f"{before}{normalized}" if operation == "append" else str(normalized or "").strip()
        )
    elif kind == "bullet":
        index = int(target.get("index", -1))
        if index < 0 or index >= len(bullets):
            raise ValueError("要点序号不存在")
        before = bullets[index]
        if operation == "delete":
            bullets.pop(index)
        elif operation == "move":
            destination = int(target.get("to", index))
            destination = max(0, min(len(bullets) - 1, destination))
            bullets.insert(destination, bullets.pop(index))
        else:
            bullets[index] = f"{before}{normalized}" if operation == "append" else str(normalized or "").strip()
    elif kind == "bullets":
        before = bullets
        values = value if isinstance(value, list) else [line.strip() for line in str(value or "").splitlines() if line.strip()]
        bullets = bullets + values if operation == "append" else ([] if operation == "delete" else values)
    else:
        before = dict(result.get("visualIntent") or {})
        if not isinstance(value, str) or value not in {"chart", "table", "diagram", "typography", "source-image", "generated-image"}:
            raise ValueError("视觉对象只能切换到受支持的语义类型")
        visual = dict(result.get("visualIntent") or {})
        visual["primaryVisual"] = value
        visual.pop("selectedVariant", None)
        visual["variantSelectionSource"] = "object-edit"
        result["visualIntent"] = visual
    content["bullets"] = [str(item).strip() for item in bullets if str(item).strip()][:8]
    result["content"] = content
    change_set = {
        "target": target,
        "operation": operation,
        "before": before,
        "after": result.get("visualIntent") if kind == "visual" else (
            result.get("message") if kind == "message" else result["content"].get("title") if kind == "title" else result["content"]["bullets"]
        ),
    }
    return result, change_set
