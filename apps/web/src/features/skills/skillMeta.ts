import type { Skill } from "../../api";

export const SKILL_META: Record<string, { name: string; description: string; tags: string[] }> = {
  "swiss-grid-pro": { name: "瑞士网格 · 专业简报", description: "高对比、强网格、低装饰的正式表达。", tags: ["专业", "网格", "高对比"] },
  "data-consulting": { name: "数据咨询 · 决策表达", description: "结论先行、图表优先，突出关键差异与行动建议。", tags: ["数据", "咨询", "高管汇报"] },
  "editorial-story": { name: "编辑叙事 · 人文报告", description: "以杂志式留白、引文和图片节奏组织观点。", tags: ["编辑设计", "故事", "品牌"] },
  "nebula-tech": { name: "星云科技 · 产品发布", description: "深色舞台与冷色高光，强调技术结构和产品张力。", tags: ["科技", "发布会", "架构"] },
  "oriental-minimal": { name: "东方留白 · 雅致表达", description: "墨色、米白与少量金红构成克制的东方秩序。", tags: ["东方", "留白", "文化"] },
  "playful-bento": { name: "活力便当 · 创意展示", description: "模块化拼贴与明快色块，适合创意提案和作品展示。", tags: ["便当网格", "创意", "作品集"] },
};

export function skillName(skill: Skill) {
  return SKILL_META[skill.id]?.name || skill.name || skill.id;
}

export function skillDescription(skill: Skill) {
  if (SKILL_META[skill.id]) return SKILL_META[skill.id].description;
  const description = skill.description || "";
  const chineseChars = (description.match(/[\u4e00-\u9fff]/g) || []).length;
  return chineseChars >= 6
    ? description
    : "社区视觉技能，用于扩展版式、色彩、字体层级与图表表达。";
}

export function skillTags(skill: Skill) {
  return SKILL_META[skill.id]?.tags || ["视觉排版", "社区精选"];
}
