import type { CSSProperties } from "react";
import type { QualityReport } from "../../api";
import { EvaluationPanel } from "./EvaluationPanel";

const VISION_STATUS: Record<string, string> = { "not-configured": "未配置视觉模型", unavailable: "视觉模型不可用", checked: "视觉模型已复核" };

const DIMENSION_LABELS: Record<string, string> = {
  fundamentals: "演示基础",
  visualDesign: "视觉设计",
  completeness: "内容完整",
  correctness: "事实正确",
  fidelity: "材料忠实",
};

export function QualityCenter({ report, projectId, slides, onJumpToSlide }: {
  report: QualityReport;
  projectId?: string;
  slides?: { id: string; position: number }[];
  onJumpToSlide?: (slideId: string, position: number) => void;
}) {
  if (!report.professionalAudit) return null;
  const audit = report.professionalAudit;
  const ready = audit.ready && report.passed && report.visualQA?.complete !== false;
  return (
    <div className="quality-center">
      <div className="quality-heading">
        <strong className={`score-ring ${ready ? "is-ready" : "is-pending"}`} style={{ "--score": Math.max(0, Math.min(100, audit.overall)) } as CSSProperties}>
          <span>{audit.overall}<i>{audit.grade}</i></span>
        </strong>
        <div><b>专业质量门禁</b><small>内容、设计、完整性、正确性与材料忠实度</small></div>
      </div>
      {report.visualQA && (
        <div className="quality-evidence">
          <span><b>页面显示检查 {report.visualQA.checked}/{report.visualQA.expected ?? report.visualQA.checked} 页</b>
            {report.visualQA.blocking > 0 ? `${report.visualQA.blocking} 页需要修复` : "已检查页面未发现阻断问题"}
            {!!report.visualQA.missingPositions?.length && ` · 待生成第 ${report.visualQA.missingPositions.join("、")} 页`}
            {!!report.visualQA.stalePositions?.length && ` · 第 ${report.visualQA.stalePositions.join("、")} 页已修改，需重新生成`}
          </span>
          {report.visualQA.slides?.filter(slide => slide.issues.length > 0).slice(0, 4).map(slide => (
            <span key={slide.position}><b>第 {slide.position} 页</b>{[...new Set(slide.issues.map(issue => issue.message || "页面显示异常"))].join("；")}</span>
          ))}
        </div>
      )}
      <div className="quality-bars">
        {Object.entries(audit.dimensions).map(([key, value]) => (
          <div key={key}>
            <span>{DIMENSION_LABELS[key] || key}</span>
            <i className={value >= 85 ? "good" : value >= 70 ? "watch" : "risk"}><b style={{ width: `${Math.max(0, Math.min(100, value))}%` }}></b></i>
            <em>{value}</em>
          </div>
        ))}
      </div>
      {(report.semanticCompleteness || report.visualReflection || report.accessibility) && (
        <div className="quality-evidence">
          {report.semanticCompleteness && (
            <span>
              <b>语义覆盖 {report.semanticCompleteness.score}</b>
              章节 {report.semanticCompleteness.coveredSections}/{report.semanticCompleteness.requiredSections} · 关键结论 {report.semanticCompleteness.coveredClaims}/{report.semanticCompleteness.requiredClaims}
            </span>
          )}
          {report.visualReflection && (
            <span>
              <b>视觉反思已检查 {report.visualReflection.checked || 0} 页</b>
              安全修复 {report.visualReflection.applied || 0} 页{report.visualReflection.visionStatus ? ` · ${VISION_STATUS[report.visualReflection.visionStatus] || report.visualReflection.visionStatus}` : ""}
            </span>
          )}
          {report.visualMaturity && (
            <span>
              <b>视觉成熟度 {report.visualMaturity.score} 分</b>
              {report.visualMaturity.uniqueFamilies || 0} 种构图骨架 · 节奏 {report.visualMaturity.narrativeRhythm} · 语义适配 {report.visualMaturity.semanticAdaptation}
            </span>
          )}
          {report.accessibility && (
            <span>
              <b>无障碍 {report.accessibility.score} 分</b>
              错误 {report.accessibility.errors} · 提醒 {report.accessibility.warnings} · {report.accessibility.passed ? "通过" : "需要修复"}
            </span>
          )}
        </div>
      )}
      {audit.recommendations[0] ? (
        <p className="quality-next"><b>优先优化：</b>{audit.recommendations[0].title} · {audit.recommendations[0].detail}</p>
      ) : <p className={`quality-next${ready ? " pass" : ""}`}>{ready ? "已通过当前自动检查，交付前请预览完整演示" : "检查尚未全部通过，请完成页面生成并处理待修复问题"}</p>}
      {projectId && <EvaluationPanel projectId={projectId} slides={slides} onJumpToSlide={onJumpToSlide} />}
    </div>
  );
}
