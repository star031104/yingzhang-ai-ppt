import type { Skill } from "../../api";

type SkillMeta = { name: string; description: string; tags: string[]; palette: [string, string, string, string] };

/** Built-in visual skills. palette = background, ink, primary, accent (from each skill's tokens.json). */
export const SKILL_META: Record<string, SkillMeta> = {
  "swiss-grid-pro": { name: "瑞士网格 · 专业简报", description: "高对比、强网格、低装饰的正式表达。", tags: ["专业", "网格", "高对比"], palette: ["#F5F5F2", "#111111", "#E23D28", "#F3C84B"] },
  "data-consulting": { name: "数据咨询 · 决策表达", description: "结论先行、图表优先，突出关键差异与行动建议。", tags: ["数据", "咨询", "高管汇报"], palette: ["#F5F8FA", "#102A43", "#007A78", "#F0B429"] },
  "editorial-story": { name: "编辑叙事 · 人文报告", description: "以杂志式留白、引文和图片节奏组织观点。", tags: ["编辑设计", "故事", "品牌"], palette: ["#F6F0E7", "#231F20", "#9D2C3A", "#D6A85F"] },
  "nebula-tech": { name: "星云科技 · 产品发布", description: "深色舞台与冷色高光，强调技术结构和产品张力。", tags: ["科技", "发布会", "架构"], palette: ["#F3F6FA", "#121A2F", "#5B5FF0", "#46E6C4"] },
  "oriental-minimal": { name: "东方留白 · 雅致表达", description: "墨色、米白与少量金红构成克制的东方秩序。", tags: ["东方", "留白", "文化"], palette: ["#F7F2E8", "#20211F", "#9A3B2E", "#C69C55"] },
  "playful-bento": { name: "活力便当 · 创意展示", description: "模块化拼贴与明快色块，适合创意提案和作品展示。", tags: ["便当网格", "创意", "作品集"], palette: ["#F6F4FF", "#211D35", "#6E55E8", "#8CE3C7"] },
  "academic-defense": { name: "学术答辩 · 严谨论证", description: "以问题、方法、实验、结论为主线，判断句标题配原生图表，适合答辩与开题。", tags: ["学术", "答辩", "原生图表"], palette: ["#F7F8FA", "#1B2333", "#2B4C7E", "#C8A24B"] },
  "finance-research": { name: "金融研报 · 高密度证据", description: "标题即结论，折线、环形、瀑布与柱线组合图呈现数据，保留原始精度。", tags: ["投研", "高密度", "瀑布图"], palette: ["#FAFAF7", "#1A1F2B", "#C8102E", "#F2C14E"] },
  "gov-briefing": { name: "政务汇报 · 庄重清晰", description: "居中标题、规范措辞，时间线与分阶段流程呈现工作进展和成效。", tags: ["政务", "工作汇报", "时间线"], palette: ["#FBF8F3", "#222222", "#B71C1C", "#C9A227"] },
};

export function skillPalette(skill: Skill) {
  return SKILL_META[skill.id]?.palette;
}

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
