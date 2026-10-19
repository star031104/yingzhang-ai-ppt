import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { candidatePreviewUrl, exportDownloadUrl, exportUrl, exportWithTemplate, sampleUrl } from "../../api";
import type { ProjectWorkspace, QualityReport, RegionEditResult } from "../../api";
import { Empty } from "../../components/Empty";
import { Icon } from "../../components/Icon";
import { RegionEditLayer } from "./RegionEditLayer";
import { VideoExport } from "./VideoExport";

const ZOOM_STEPS = [0.5, 0.75, 1, 1.25, 1.5, 2];

export function ProjectPreview({
  projectId,
  data,
  previewKey,
  busy,
  setBusy,
  setStatus,
  currentSlideId,
  onRegionEdited,
  regionToolRequest = 0,
}: {
  projectId: string;
  data: ProjectWorkspace;
  previewKey: number;
  busy: boolean;
  /** Kept for API compatibility; the quality report is shown in the inspector. */
  qualityReport?: QualityReport | null;
  setBusy: (busy: boolean) => void;
  setStatus: (status: string) => void;
  currentSlideId?: string;
  onRegionEdited?: (result: RegionEditResult) => Promise<void> | void;
  /** Incremented by the parent to switch the region tool on. */
  regionToolRequest?: number;
}) {
  const sampleMode =
    data.gates?.enabled &&
    data.gates.outline === "approved" &&
    data.gates.sample !== "approved" &&
    data.sampleAvailable;
  const readOnlyRole = data.projectRole === "viewer" || data.projectRole === "reviewer";
  const fileUrl = (format: "html" | "pptx" | "pdf", stage: "draft" | "final" = "final") =>
    readOnlyRole
      ? exportDownloadUrl(projectId, format, stage)
      : exportUrl(projectId, format, stage);
  const slide = (data.slides ?? []).find((item) => item.id === currentSlideId) ?? data.slides?.[0];
  const selectedCandidate = (data.candidates ?? []).find(
    (candidate) => candidate.slideId === slide?.id && candidate.selected && candidate.previewAvailable,
  );
  const [mode, setMode] = useState<"slide" | "deck">("slide");
  const [zoom, setZoom] = useState(1);
  const [regionTool, setRegionTool] = useState(false);
  const singleAvailable = Boolean(slide && selectedCandidate) && !sampleMode;
  const effectiveMode = mode === "slide" && singleAvailable ? "slide" : "deck";
  const canRegionEdit = effectiveMode === "slide" && !readOnlyRole && Boolean(onRegionEdited);
  useEffect(() => {
    if (regionToolRequest > 0 && singleAvailable && !readOnlyRole) {
      setMode("slide");
      setRegionTool(true);
    }
  }, [regionToolRequest]);
  useEffect(() => {
    if (!canRegionEdit) setRegionTool(false);
  }, [canRegionEdit]);

  return (
    <div className="preview-column">
      <div className="preview-heading">
        <div className="segmented" role="tablist" aria-label="预览方式">
          <button type="button" role="tab" aria-selected={effectiveMode === "slide"} disabled={!singleAvailable} onClick={() => setMode("slide")}>当前页</button>
          <button type="button" role="tab" aria-selected={effectiveMode === "deck"} onClick={() => { setMode("deck"); setRegionTool(false); }}>{sampleMode ? "代表样张" : "全稿预览"}</button>
        </div>
        <span className={`preview-state ${data.previewAvailable ? "ready" : "pending"}`}><i />{data.previewAvailable ? "已就绪" : "待生成"}</span>
        <div className="stage-tools">
          {effectiveMode === "slide" && (
            <div className="zoom-control" role="group" aria-label="缩放">
              <button type="button" className="ghost icon-button btn-sm" aria-label="缩小" disabled={zoom <= ZOOM_STEPS[0]} onClick={() => setZoom(ZOOM_STEPS[Math.max(0, ZOOM_STEPS.indexOf(zoom) - 1)])}><Icon name="zoomOut" size={15} /></button>
              <button type="button" className="ghost btn-sm zoom-value" aria-label="适应窗口" title="适应窗口" onClick={() => setZoom(1)}>{zoom === 1 ? "适应" : `${Math.round(zoom * 100)}%`}</button>
              <button type="button" className="ghost icon-button btn-sm" aria-label="放大" disabled={zoom >= ZOOM_STEPS.at(-1)!} onClick={() => setZoom(ZOOM_STEPS[Math.min(ZOOM_STEPS.length - 1, ZOOM_STEPS.indexOf(zoom) + 1)])}><Icon name="zoomIn" size={15} /></button>
            </div>
          )}
          {canRegionEdit && (
            <button
              type="button"
              className={`btn-sm region-toggle${regionTool ? " active" : ""}`}
              aria-pressed={regionTool}
              onClick={() => setRegionTool((value) => !value)}
              title="在页面上框选区域，用一句话描述修改"
            >
              <Icon name="select" size={15} />{regionTool ? "退出框选" : "框选修改"}
            </button>
          )}
        </div>
      </div>
      <div className={`preview-stage mode-${effectiveMode}${regionTool ? " is-selecting" : ""}`}>
        {sampleMode ? (
          <iframe key={previewKey} title="代表样张预览" src={`${sampleUrl(projectId)}?preview=${previewKey}`} />
        ) : effectiveMode === "slide" && slide && selectedCandidate ? (
          <div className="stage-scroll">
            <div className="slide-frame" style={{ "--zoom": zoom } as CSSProperties}>
              <img
                key={`${selectedCandidate.id}-${previewKey}`}
                src={`${candidatePreviewUrl(projectId, slide.id, selectedCandidate.id)}?v=${previewKey}`}
                alt={`第 ${slide.position} 页：${slide.content.title}`}
                draggable={false}
              />
              {regionTool && (
                <RegionEditLayer
                  projectId={projectId}
                  slideId={slide.id}
                  revision={slide.revision}
                  disabled={busy}
                  onExit={() => setRegionTool(false)}
                  onEdited={async (result) => { await onRegionEdited?.(result); }}
                />
              )}
            </div>
          </div>
        ) : data.previewAvailable ? (
          <iframe key={previewKey} title="演示预览" src={`${exportUrl(projectId, "html", "draft")}&preview=${previewKey}`} />
        ) : (
          <Empty icon="slides" title="还没有预览" text="生成完成后会在这里显示页面。可以先检查左侧大纲，再点击“重新生成全稿”。" />
        )}
      </div>
      <div className="export-dock" id="project-export">
        <div className="download-row">
          <a aria-label="下载 HTML 或网页媒体包" href={fileUrl("html")}><Icon name="download" size={15} /><span>HTML</span><small>网页演示与媒体</small></a>
          <a aria-label="下载 PPTX" href={fileUrl("pptx")}><Icon name="download" size={15} /><span>PPTX</span><small>原生可编辑</small></a>
          <a aria-label="下载 PDF" href={fileUrl("pdf")}><Icon name="download" size={15} /><span>PDF</span><small>固定版式</small></a>
        </div>
        <label className="template-export">
          <input
            type="file"
            accept=".pptx"
            disabled={busy}
            onChange={async (event) => {
              const input = event.currentTarget;
              const file = input.files?.[0];
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
                input.value = "";
              }
            }}
          />
          <Icon name="layout" size={15} /><span><b>套用公司模板</b><small>选择 PPTX，自动匹配封面、章节与正文母版</small></span>
        </label>
        {!readOnlyRole && <VideoExport projectId={projectId} disabled={busy || !data.previewAvailable} />}
      </div>
      <p className="field-help export-help">正式交付需通过质量检查。需要先核对内容时，可 <a href={fileUrl("pptx", "draft")}>下载检查草稿 PPTX</a>。</p>
    </div>
  );
}
