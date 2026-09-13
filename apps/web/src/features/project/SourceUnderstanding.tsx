import type { SourceReading } from "../../api";
import "./source-understanding.css";

export function SourceUnderstanding({ sources }: { sources: SourceReading[] }) {
  if (!sources.length) return null;
  const attention = sources.filter((source) => source.readingStatus === "needs-attention");
  return (
    <details className={`panel source-understanding${attention.length ? " has-attention" : ""}`}>
      <summary><i>{attention.length ? "!" : "✓"}</i><span><b>材料读取情况</b><small>{attention.length ? `${attention.length} 份材料需要补充核对` : `${sources.length} 份材料 · 查看章节与重点`}</small></span><em>查看详情</em></summary>
      <p>以下是从原文提取的重点，方便核对。页面内容仍以原始材料为依据。</p>
      {attention.length > 0 && <p>黄色提醒不阻止确认大纲。若下列页面包含汇报需要的数据，请补充可复制文字的材料后重新规划；未可靠读取的表格数值不会自动补猜。</p>}
      {sources.map((source) => (
        <article key={source.id}>
          <h4>{source.name}</h4>
          <small>{source.sections ?? "—"} 个章节 · {source.tables ?? 0} 个表格 · {source.figures ?? 0} 张图片</small>
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
