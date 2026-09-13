import type { SlideSpec } from "../../api";
import { ROLE_LABELS } from "./presentationMeta";

export function SlideRail({
  slides,
  currentId,
  onSelect,
}: {
  slides: SlideSpec[];
  currentId?: string;
  onSelect: (slideId: string) => void;
}) {
  return (
    <aside className="slide-rail">
      <div className="rail-title"><b>页面目录</b><small>点击页面进行微调</small></div>
      {slides.map((slide) => (
        <button
          key={slide.id}
          className={currentId === slide.id ? "active" : ""}
          onClick={() => onSelect(slide.id)}
        >
          <span>{String(slide.position).padStart(2, "0")}</span>
          <div>
            <b>{slide.content.title}</b>
            <small>{ROLE_LABELS[slide.role] || slide.role}</small>
          </div>
        </button>
      ))}
    </aside>
  );
}
