import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCENARIOS = {
    "all",
    "academic",
    "conference",
    "business",
    "strategy",
    "executive",
    "review",
    "product",
    "pitch",
    "marketing",
    "sales",
    "teaching",
    "training",
    "public",
    "keynote",
    "portfolio",
}
OPTIONS = {
    "reference_style": {},
    "narrative_order": {"default": "遵循材料组织结构", "conclusion-first": "结论先行，再展开证据"},
    "title_style": {"takeaway": "有证据支持的结论式标题", "topic": "清楚的主题式标题"},
    "tone": {
        "formal": "严谨克制",
        "executive": "结论先行",
        "editorial": "编辑叙事",
        "energetic": "鲜明有张力",
    },
    "font_family": {
        "Microsoft YaHei": "微软雅黑",
        "SimSun": "宋体",
        "Arial": "Arial",
        "Noto Sans SC": "思源黑体",
        "Noto Serif SC": "思源宋体",
    },
    "palette": {
        "academic": "靛青证据",
        "business": "深海决策",
        "review": "经营复盘",
        "product": "紫曜发布",
        "teaching": "暖橙课堂",
    },
    "density": {"balanced": "适中", "airy": "舒展留白（不删减内容）"},
    "preferred_variant": {
        "split": "左右分区",
        "statement": "主张式",
        "evidence-brief": "判断与证据",
        "chart-focus": "图表聚焦",
        "table-highlight": "数据表格",
        "minimal-cover": "极简封面",
        "two-column": "双栏对照",
    },
    "review_mode": {"samples-first": "先看大纲和代表样张", "standard": "标准流程"},
    "delivery_profile": {
        "powerpoint-windows": "Windows PowerPoint",
        "powerpoint-macos": "Mac PowerPoint",
        "wps": "WPS",
        "libreoffice": "LibreOffice",
    },
}
LABELS = {
    "reference_style": "参考稿视觉规范",
    "narrative_order": "汇报逻辑",
    "title_style": "标题表达",
    "tone": "表达语气",
    "font_family": "字体",
    "palette": "配色",
    "density": "页面密度",
    "preferred_variant": "候选版式",
    "review_mode": "审阅习惯",
    "delivery_profile": "交付软件",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    scenario: str = "all"
    use_memory: bool = True
    capture_feedback: bool = False

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("请填写档案名称")
        return value.strip()

    @field_validator("scenario")
    @classmethod
    def valid_scenario(cls, value):
        if value not in SCENARIOS:
            raise ValueError("不支持的汇报场景")
        return value


class ProfileUpdate(ProfileCreate):
    revision: int = Field(ge=1)


class MemoryCreate(StrictModel):
    key: str
    value: str
    revision: int = Field(ge=1, description="当前档案版本")

    @field_validator("key")
    @classmethod
    def valid_key(cls, value):
        if value not in OPTIONS:
            raise ValueError("不支持的经验类型")
        return value


def validate_preference(key: str, value: Any) -> str:
    if key == "reference_style":
        if not isinstance(value, str) or len(value) > 8000:
            raise ValueError("视觉规范内容过大或格式不正确")
        data = json.loads(value)
        if not isinstance(data, dict) or set(data) - {
            "fontFamily",
            "palette",
            "preferredByRole",
            "cardRadius",
            "layouts",
        }:
            raise ValueError("视觉规范包含不支持的参数")
        if "fontFamily" in data and (
            not isinstance(data["fontFamily"], str)
            or data["fontFamily"] not in OPTIONS["font_family"]
        ):
            raise ValueError("参考字体不在支持列表")
        if "palette" in data:
            palette = data["palette"]
            if (
                not isinstance(palette, dict)
                or set(palette) != {"bg", "ink", "primary", "accent", "deep", "line"}
                or any(
                    not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color)
                    for color in palette.values()
                )
            ):
                raise ValueError("视觉规范需要完整的六色 RGB 色板")
        if "cardRadius" in data and (
            not isinstance(data["cardRadius"], (int, float)) or not 0 <= data["cardRadius"] <= 28
        ):
            raise ValueError("圆角超出支持范围")
        mapping = data.get("preferredByRole", {})
        if not isinstance(mapping, dict) or len(mapping) > 16:
            raise ValueError("页型偏好格式错误")
        roles = {
            "cover",
            "agenda",
            "section",
            "background",
            "problem",
            "method",
            "architecture",
            "evidence",
            "data",
            "comparison",
            "insight",
            "conclusion",
            "content",
            "questions",
        }
        if any(
            role not in roles
            or not isinstance(variant, str)
            or variant not in OPTIONS["preferred_variant"]
            for role, variant in mapping.items()
        ):
            raise ValueError("参考版式不在支持列表")
        if "layouts" in data:
            layouts = data["layouts"]
            if not isinstance(layouts, dict) or set(layouts) - {"cover", "content", "background", "problem", "insight", "conclusion"}:
                raise ValueError("不支持的参考布局页型")
            for boxes in layouts.values():
                if not isinstance(boxes, list) or not 2 <= len(boxes) <= 8:
                    raise ValueError("参考布局需要 2—8 个区域")
                for box in boxes:
                    if not isinstance(box, dict) or set(box) - {"x", "y", "w", "h", "fontSize", "fontFamily"} or not {"x", "y", "w", "h", "fontSize"} <= set(box):
                        raise ValueError("参考布局区域格式错误")
                    if any(not isinstance(box[key], (int, float)) or isinstance(box[key], bool) for key in ("x", "y", "w", "h", "fontSize")):
                        raise ValueError("参考区域需要数值")
                    if not (0 <= box["x"] < 1 and 0 <= box["y"] < 1 and 0 < box["w"] <= 1-box["x"]+0.001 and 0 < box["h"] <= 1-box["y"]+0.001 and 14 <= box["fontSize"] <= 64):
                        raise ValueError("参考布局区域越界")
                    if "fontFamily" in box and (not isinstance(box["fontFamily"], str) or box["fontFamily"] not in OPTIONS["font_family"]):
                        raise ValueError("参考字体不支持")
        return json.dumps(data, ensure_ascii=False, sort_keys=True)
    if key not in OPTIONS or not isinstance(value, str) or value not in OPTIONS[key]:
        raise ValueError("经验必须使用受支持的类型和值")
    return value


def preference_description(key, value):
    if key == "reference_style":
        data = json.loads(value)
        return "；".join(
            filter(
                None,
                [
                    data.get("fontFamily"),
                    "六色参考色板" if data.get("palette") else "",
                    f"{len(data.get('preferredByRole', {}))} 类页面构图",
                    "规则不包含业务正文；原稿是否保留见参考模板区",
                ],
            )
        )
    return OPTIONS.get(key, {}).get(value, value)


class RevisionRequest(StrictModel):
    revision: int = Field(ge=1)


class ResetPreview(StrictModel):
    scope: Literal["all", "profile", "memory"] = "all"
    target_id: str | None = Field(default=None, max_length=36)


class ResetExecute(StrictModel):
    preview_id: str
    digest: str


class ProfileImport(StrictModel):
    version: Literal[1]
    name: str = Field(min_length=1, max_length=120)
    scenario: str = "all"
    memories: list[dict] = Field(default_factory=list, max_length=100)
