import { exportUrl, exportWithTemplate, sampleUrl } from "../../api";
import type { ProjectWorkspace, QualityReport } from "../../api";
import { Empty } from "../../components/Empty";
import { SKILL_META } from "../skills/skillMeta";
import { QualityCenter } from "./QualityCenter";

export function ProjectPreview({
  projectId,
  data,
  previewKey,
  busy,
  qualityReport,
  setBusy,
  setStatus,
}: {
  projectId: string;
  data: ProjectWorkspace;
  previewKey: number;
  busy: boolean;
  qualityReport: QualityReport | null;
  setBusy: (busy: boolean) => void;
  setStatus: (status: string) => void;
}) {
  const sampleMode =
    data.gates?.enabled &&
    data.gates.outline === "approved" &&
    data.gates.sample !== "approved" &&
    data.sampleAvailable;

  return (
    <div className="preview-column">
      <div className="preview-heading">
        <div><b>演示预览</b><small>生成完成后自动刷新</small></div>
        <span className={data.previewAvailable ? "ready" : "pending"}><i />{data.previewAvailable ? "已就绪" : "待生成"}</span>
      </div>
      <div className="preview-stage">
        {sampleMode ? (
          <iframe key={previewKey} title="代表样张预览" src={`${sampleUrl(projectId)}?preview=${previewKey}`} />
        ) : data.previewAvailable ? (
          <iframe key={previewKey} title="演示预览" src={`${exportUrl(projectId, "html", "draft")}&preview=${previewKey}`} />
        ) : (
          <Empty title="还没有预览" text="保存内容后点击“重新生成全稿”。" />
        )}
      </div>
      <div className="download-row">
        <a aria-label="下载 HTML" href={exportUrl(projectId, "html")}><span>HTML</span><small>网页演示</small></a>
        <a aria-label="下载 PPTX" href={exportUrl(projectId, "pptx")}><span>PPTX</span><small>继续编辑</small></a>
        <a aria-label="下载 PDF" href={exportUrl(projectId, "pdf")}><span>PDF</span><small>固定版式</small></a>
      </div>
      <p className="field-help">正式交付须通过质量检查。需要先核对内容时，可 <a href={exportUrl(projectId, "pptx", "draft")}>下载检查草稿 PPTX</a>。</p>
      <label className="template-export">
        <input
          type="file"
          accept=".pptx"
          disabled={busy}
          onChange={async (event) => {
            const file = event.currentTarget.files?.[0];
            if (!file) return;
            setBusy(true);
            setStatus("正在识别母版版式并生成品牌 PPTX…");
            try {
              await exportWithTemplate(projectId, file);
              setStatus("已按模板的母版和页面版式完成导出");
            } catch (error) {
              setStatus(error instanceof Error ? error.message : "模板导出失败");
            } finally {
              setBusy(false);
              event.currentTarget.value = "";
            }
          }}
        />
        <i>⌁</i><span><b>使用公司模板导出</b><small>点击选择 PPTX，自动匹配封面、章节与正文母版</small></span><strong>选择模板</strong>
      </label>
      <div className="source-summary">
        <div><span>来源</span><p>{data.sources.map((source) => source.name).join("、") || "基于主题与创作要求生成"}</p></div>
        <div><span>视觉</span><p>{data.skillIds.map((id) => SKILL_META[id]?.name || id).join("、") || "映章默认视觉系统"}</p></div>
      </div>
      {qualityReport && <QualityCenter report={qualityReport} />}
    </div>
  );
}
