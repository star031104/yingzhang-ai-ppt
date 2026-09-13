import type { ProfessionalPlatform, SlideSpec } from "../api";
import { LayoutCanvasEditor } from "./LayoutCanvasEditor";

type Props = {
  data?: ProfessionalPlatform;
  slide?: SlideSpec;
  loading?: boolean;
  busy?: boolean;
  onVisualRegression: (acceptCurrent: boolean) => Promise<void>;
  onSaveLayout: (
    regions: NonNullable<NonNullable<SlideSpec["layoutPlan"]>["regions"]>,
    focalPoint: "left" | "right" | "full",
  ) => Promise<void>;
};

const PROFILE_LABELS: Record<string, string> = {
  "powerpoint-windows": "Windows PowerPoint",
  "powerpoint-macos": "Mac PowerPoint",
  wps: "WPS",
  libreoffice: "LibreOffice",
};

function scoreTone(score = 0) {
  return score >= 90 ? "good" : score >= 78 ? "watch" : "risk";
}

export function ProfessionalPlatformPanel({ data, slide, loading, busy, onVisualRegression, onSaveLayout }: Props) {
  if (loading) return <div className="panel professional-platform loading">正在整理专业制作状态…</div>;
  if (!data) return null;
  const layout = slide?.layoutPlan;
  const trace = data.p1.stageTrace.slice(-4).reverse();
  return (
    <details className="panel professional-platform">
      <summary>
        <span><b>专业制作控制台</b><small>调研、构图、品牌、评审和交付在同一条链路中工作</small></span>
        <i>完整能力</i>
      </summary>
      <div className="professional-priorities">
        <article>
          <header><span>P0</span><b>内容与构图</b></header>
          <div className="professional-score"><strong>{data.p0.brandKit.score ?? 0}</strong><small>品牌完整度</small></div>
          <p>当前页：{layout?.compositionMode || "等待规划"} · {layout?.silhouette || "自适应构图"}</p>
          <p>全稿已规划 {data.p0.layoutPlanning.uniqueSilhouettes ?? 0} 种页面轮廓，调研缺口 {data.p0.researchManifest.evidenceGaps?.length ?? 0} 项。</p>
        </article>
        <article>
          <header><span>P1</span><b>评审与治理</b></header>
          <div className="professional-tags">
            {data.p1.benchmarkFamilies.map((item) => <span key={item}>{item}</span>)}
          </div>
          <p>版本差异会标记数字新增和来源移除；最终发布需要审批、质量门禁和快照。</p>
          {trace.length > 0 && <ol className="stage-trace">{trace.map((item, index) => <li key={`${item.at}-${index}`}><b>{item.label}</b><small>{Math.round((item.progress || 0) * 100)}%</small></li>)}</ol>}
        </article>
        <article>
          <header><span>P2</span><b>交付兼容性</b></header>
          <div className="delivery-grid">
            {Object.entries(data.p2.deliveryProfiles).map(([id, profile]) => (
              <span className={scoreTone(profile.score)} key={id}><b>{profile.score}</b><small>{PROFILE_LABELS[id] || id}</small></span>
            ))}
          </div>
          <p>支持视频/音频叙事、模板约束学习，以及 PowerPoint、WPS、LibreOffice 交付预检。</p>
        </article>
      </div>
      <div className="professional-actions">
        <button disabled={busy} onClick={() => onVisualRegression(false)}>检查视觉变化</button>
        <button disabled={busy} onClick={() => onVisualRegression(true)}>将当前版本设为视觉基线</button>
        {layout?.communicationJob && <span>本页任务：{layout.communicationJob}</span>}
      </div>
      <LayoutCanvasEditor slide={slide} busy={busy} onSave={onSaveLayout} />
    </details>
  );
}
