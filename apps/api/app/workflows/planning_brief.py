"""Planning request schema and professional brief normalization."""

from typing import Literal

from pydantic import BaseModel, Field


class PlanRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    instructions: str = Field(default="", max_length=4000)
    preset: str = "academic"
    slide_count: int = Field(default=12, ge=6, le=60)
    skill_ids: list[str] = Field(default_factory=list, max_length=20)
    approval_mode: bool = False
    image_mode: Literal["off", "auto", "creative"] = "off"
    audience: str = Field(default="", max_length=240)
    objective: str = Field(default="", max_length=500)
    brand_name: str = Field(default="", max_length=120)
    tone: Literal["auto", "formal", "executive", "editorial", "energetic"] = "auto"
    duration_minutes: int | None = Field(default=None, ge=3, le=180)
    profile_id: str | None = Field(default=None, max_length=36)
    profile_revision: int | None = Field(default=None, ge=1)
    personalization_mode: Literal["off", "profile"] = "off"


PRESET_LABELS = {
    "academic": "毕业答辩 / 学术汇报", "conference": "学术会议 / 研究分享",
    "business": "商业汇报", "strategy": "战略规划 / 咨询建议",
    "executive": "高管决策简报", "review": "项目复盘 / 经营复盘",
    "product": "产品发布", "pitch": "融资路演", "marketing": "营销创意提案",
    "sales": "销售解决方案", "teaching": "课程教学", "training": "企业培训 / 工作坊",
    "public": "政务 / 公共事务汇报", "keynote": "主题演讲", "portfolio": "作品集 / 案例展示",
}

TONE_LABELS = {
    "auto": "根据内容自动判断",
    "formal": "严谨克制",
    "executive": "结论先行",
    "editorial": "编辑叙事",
    "energetic": "鲜明有张力",
}


def professional_brief(body: PlanRequest) -> dict:
    """Normalize the few decisions that materially change a professional deck."""
    return {
        "audience": body.audience.strip(),
        "objective": body.objective.strip(),
        "brandName": body.brand_name.strip(),
        "tone": body.tone,
        "toneLabel": TONE_LABELS[body.tone],
        "durationMinutes": body.duration_minutes,
    }


def enriched_instructions(body: PlanRequest) -> str:
    brief = professional_brief(body)
    parts = [body.instructions.strip()]
    if brief["audience"]:
        parts.append(f"目标受众：{brief['audience']}")
    if brief["objective"]:
        parts.append(f"演示结束后希望受众：{brief['objective']}")
    if brief["tone"] != "auto":
        parts.append(f"表达语气：{brief['toneLabel']}")
    if brief["durationMinutes"]:
        parts.append(f"预计演讲时长：{brief['durationMinutes']} 分钟")
    if brief["brandName"]:
        parts.append(f"品牌/组织：{brief['brandName']}")
    return "\n".join(part for part in parts if part)

def page_responsibilities(preset: str, slide_count: int) -> dict[int, str]:
    # 保留兼容入口；真实规划责任由 plan_deck 根据材料语义动态生成。
    return {position: f"第 {position} 页的唯一沟通任务" for position in range(1, slide_count + 1)}

