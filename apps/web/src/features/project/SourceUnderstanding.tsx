import type { SourceReading } from "../../api";
import "./source-understanding.css";

type DocumentRoles = { name: string; uncertainRoles: { section?: string; title: string; role: string; confidence: number }[] };
const SECTION_ROLES: Record<string, string> = {
  agenda: "内容导览", section: "章节过渡", background: "背景", problem: "核心问题", method: "方法",
  architecture: "架构", evidence: "证据", data: "数据结果", comparison: "对比", insight: "洞察",
  conclusion: "结论", questions: "问答", content: "核心内容", cover: "封面",
};

export function SourceUnderstanding({ sources, documents = [] }: { sources: SourceReading[]; documents?: DocumentRoles[] }) {
  if (!sources.length) return null;
  const attention = sources.filter((source) => source.readingStatus === "needs-attention");
  const uncertainCount = documents.reduce((total, item) => total + item.uncertainRoles.length, 0);
  return (
    <details className={`panel source-understanding${attention.length ? " has-attention" : ""}`}>
      <summary><i>{attention.length ? "!" : "✓"}</i><span><b>材料读取情况</b><small>{attention.length ? `${attention.length} 份材料需要补充核对` : `${sources.length} 份材料 · 查看章节与重点`}{uncertainCount > 0 && ` · ${uncertainCount} 个章节用途待确认`}</small></span><em>查看详情</em></summary>
      <p>以下是从原文提取的重点，方便核对。页面内容仍以原始材料为依据。</p>
      {attention.length > 0 && <p>黄色提醒不阻止确认大纲。请优先核对识别出的文字和数字；若关键页面仍缺少汇报所需内容，再补充可复制文字的材料后重新规划。未可靠读取的表格数值不会自动补猜。</p>}
      {sources.map((source) => (
        <article key={source.id}>
          <h4>{source.name}</h4>
          <small>{source.sections ?? "—"} 个章节 · {source.tables ?? 0} 个表格 · {source.figures ?? 0} 张图片</small>
          {(() => {
            const uncertain = documents.find((item) => item.name === source.name)?.uncertainRoles ?? [];
            return uncertain.length > 0 && (
              <div className="uncertain-roles">
                <b>章节用途待确认</b>
                <small>系统对这些章节在汇报中的作用把握不大，规划时会谨慎使用；如判断有误，可在大纲中调整对应页面。</small>
                <ul>{uncertain.map((item, index) => (
                  <li key={`${item.section}-${index}`}><span>{item.title || item.section}</span><em>推测为{SECTION_ROLES[item.role] || item.role} · 置信度 {Math.round(item.confidence * 100)}%</em></li>
                ))}</ul>
              </div>
            );
          })()}
          {!!source.readingWarnings?.length && <ul className="reading-warnings">{source.readingWarnings.map((warning, index) => <li key={index}>{warning.message}</li>)}</ul>}
          <div className="reading-outline">{source.outline?.map((section) => (
            <details key={section.id}>
              <summary>{section.headingPath?.join(" / ") || section.title}</summary>
              <p>{section.mainPoint || "此章节未提取到正文"}</p>
              {!!section.limitations?.length && <ul>{section.limitations.map((point, index) => <li key={index}>{point}</li>)}</ul>}
            </details>
          ))}</div>
          {(source.outlineTotal ?? 0) > (source.outline?.length ?? 0) && <small>此处预览前 {source.outline?.length} 个章节，生成时可检索全部已读取章节。</small>}
        </article>
      ))}
    </details>
  );
}
