import { useEffect, useRef } from "react";
import type { KeyboardEvent } from "react";
import { candidatePreviewUrl } from "../../api";
import type { SlideCandidate, SlideSpec } from "../../api";
import { Icon } from "../../components/Icon";
import { ROLE_LABELS } from "./presentationMeta";

export function SlideRail({
  slides,
  currentId,
  onSelect,
  projectId,
  candidates = [],
  previewKey = 0,
}: {
  slides: SlideSpec[];
  currentId?: string;
  onSelect: (slideId: string) => void;
  projectId?: string;
  candidates?: SlideCandidate[];
  previewKey?: number;
}) {
  const list = useRef<HTMLDivElement>(null);
  useEffect(() => {
    list.current?.querySelector<HTMLElement>("[aria-current='true']")?.scrollIntoView?.({ block: "nearest" });
  }, [currentId]);
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (!["ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
    const index = slides.findIndex((slide) => slide.id === currentId);
    const next = slides[index + (event.key === "ArrowDown" || event.key === "ArrowRight" ? 1 : -1)];
    if (!next) return;
    event.preventDefault();
    onSelect(next.id);
    window.requestAnimationFrame(() => list.current?.querySelector<HTMLElement>("[aria-current='true']")?.focus());
  }
  return (
    <aside className="slide-rail" aria-label="页面目录">
      <div className="rail-title"><b>页面</b><small>{slides.length} 页</small></div>
      <div className="rail-list" ref={list} onKeyDown={onKeyDown}>
        {slides.map((slide) => {
          const selected = candidates.find((candidate) => candidate.slideId === slide.id && candidate.selected && candidate.previewAvailable);
          const state = slide.generationState?.status;
          return (
            <button
              key={slide.id}
              type="button"
              className={currentId === slide.id ? "active" : ""}
              aria-current={currentId === slide.id ? "true" : undefined}
              onClick={() => onSelect(slide.id)}
              title={slide.content.title}
            >
              <span className="rail-number">{String(slide.position).padStart(2, "0")}</span>
              <span className="rail-thumb">
                {projectId && selected
                  ? <img src={`${candidatePreviewUrl(projectId, slide.id, selected.id)}?v=${previewKey}`} alt="" loading="lazy" />
                  : <span className="rail-thumb-placeholder"><i /><i /><i /></span>}
                {state === "failed" && <em className="rail-flag" title={slide.generationState?.error || "本页生成失败"}><Icon name="alert" size={12} /></em>}
                {state === "running" && <em className="rail-flag running"><span className="spinner" /></em>}
                {state !== "failed" && state !== "running" && !!slide.proposalIssues?.length && (
                  <em className="rail-flag repaired" title={`已自动修正 ${slide.proposalIssues.length} 处模型提议`}>{slide.proposalIssues.length}</em>
                )}
              </span>
              <span className="rail-meta">
                <b>{slide.content.title}</b>
                <small>{ROLE_LABELS[slide.role] || slide.role}</small>
              </span>
            </button>
          );
        })}
      </div>
    </aside>
  );
}
