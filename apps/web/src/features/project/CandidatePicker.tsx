import { candidatePreviewUrl } from "../../api";
import type { SlideCandidate } from "../../api";
import { Empty } from "../../components/Empty";
import { VARIANT_LABELS } from "./presentationMeta";

export function CandidatePicker({
  projectId,
  candidates,
  previewKey,
  busy,
  onSelect,
}: {
  projectId: string;
  candidates: SlideCandidate[];
  previewKey: number;
  busy: boolean;
  onSelect: (candidate: SlideCandidate) => void;
}) {
  if (!candidates.length) {
    return <Empty icon="layout" title="还没有候选版式" text="生成当前页后，这里会列出多个版式供你挑选。" />;
  }
  return (
    <div className="candidate-picker">
      <div className="candidate-heading">
        <div><b>选择本页版式</b><small>选择会同步到 HTML、PDF 与可编辑 PPTX</small></div>
        <span className="count">{candidates.length} 个候选</span>
      </div>
      <div className="candidate-grid">
        {candidates.map((candidate) => {
          const label = VARIANT_LABELS[candidate.variant] || candidate.variant;
          return (
            <button
              type="button"
              key={candidate.id}
              className={candidate.selected ? "selected" : ""}
              aria-pressed={candidate.selected}
              disabled={busy || !candidate.previewAvailable}
              onClick={() => { if (!candidate.selected) onSelect(candidate); }}
            >
              {candidate.previewAvailable ? (
                <img
                  src={`${candidatePreviewUrl(projectId, candidate.slideId, candidate.id)}?v=${previewKey}`}
                  alt={`${label} 候选预览`}
                  loading="lazy"
                />
              ) : <span className="candidate-missing">预览待生成</span>}
              <span className="candidate-meta">
                <b>{label}</b>
                <small>
                  {candidate.score.overall ?? "—"} 分
                  {candidate.score.contentFit != null ? ` · 内容匹配 ${candidate.score.contentFit}` : ""}
                </small>
              </span>
              {candidate.selected && <i>已选</i>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
