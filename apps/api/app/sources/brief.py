import hashlib


def build_brief_source(title: str, instructions: str = "") -> dict:
    """Create an ephemeral evidence source for topic-only creation without faking an upload."""
    brief = (
        instructions.strip()
        or "请围绕主题建立清晰的观点、结构和行动建议；不使用未经提供的外部数字或具体事实。"
    )
    text = f"创作主题：{title.strip()}。\n用户要求：{brief}"
    return {
        "name": "创作简报（未上传材料）",
        "mimeType": "application/x-yingzhang-brief",
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "synthetic": True,
        "sections": [
            {"id": "BRIEF-001", "title": "用户创作说明", "text": text, "page": None}
        ],
        "stats": {"characters": len(text), "sections": 1},
    }
