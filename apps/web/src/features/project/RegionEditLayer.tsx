import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent, PointerEvent } from "react";
import { SLIDE_HEIGHT, SLIDE_WIDTH, regionEditSlide } from "../../api";
import type { RegionBox, RegionEditResult } from "../../api";
import { Icon } from "../../components/Icon";

type Rect = { x: number; y: number; w: number; h: number }; // fractions of the slide (0–1)
type Phase = "idle" | "drawing" | "editing" | "saving" | "done";

const QUICK_INSTRUCTIONS = ["改为：", "突出显示这里", "精简这段文字", "改成三步流程", "删除这里"];
const clamp01 = (value: number) => Math.min(1, Math.max(0, value));

export function toSlideBox(rect: Rect): RegionBox {
  return {
    x: Math.round(rect.x * SLIDE_WIDTH),
    y: Math.round(rect.y * SLIDE_HEIGHT),
    width: Math.round(rect.w * SLIDE_WIDTH),
    height: Math.round(rect.h * SLIDE_HEIGHT),
  };
}

/**
 * Drag a rectangle over the rendered slide and describe the change.
 * Coordinates are sent in slide space (1280 × 720) so they match the measured scene.
 */
export function RegionEditLayer({
  projectId,
  slideId,
  revision,
  disabled,
  onExit,
  onEdited,
}: {
  projectId: string;
  slideId: string;
  revision?: number;
  disabled?: boolean;
  onExit: () => void;
  onEdited: (result: RegionEditResult) => Promise<void> | void;
}) {
  const layer = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const start = useRef<{ x: number; y: number } | null>(null);
  const [rect, setRect] = useState<Rect | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [instruction, setInstruction] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<RegionEditResult | null>(null);

  useEffect(() => {
    setRect(null);
    setPhase("idle");
    setResult(null);
    setError("");
  }, [slideId]);
  useEffect(() => {
    if (phase === "editing") input.current?.focus();
  }, [phase]);
  useEffect(() => {
    if (phase !== "done") return;
    const timer = window.setTimeout(() => { setPhase("idle"); setRect(null); }, 5000);
    return () => window.clearTimeout(timer);
  }, [phase]);

  function point(event: PointerEvent<HTMLDivElement>) {
    const box = layer.current!.getBoundingClientRect();
    return { x: clamp01((event.clientX - box.left) / box.width), y: clamp01((event.clientY - box.top) / box.height) };
  }
  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if (phase === "saving" || disabled || event.button !== 0) return;
    if ((event.target as HTMLElement).closest(".region-popover")) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    const origin = point(event);
    start.current = origin;
    setRect({ x: origin.x, y: origin.y, w: 0, h: 0 });
    setResult(null);
    setError("");
    setPhase("drawing");
  }
  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    if (phase !== "drawing" || !start.current) return;
    const current = point(event), origin = start.current;
    setRect({ x: Math.min(origin.x, current.x), y: Math.min(origin.y, current.y), w: Math.abs(current.x - origin.x), h: Math.abs(current.y - origin.y) });
  }
  function onPointerUp() {
    if (phase !== "drawing") return;
    start.current = null;
    if (!rect || rect.w < 0.015 || rect.h < 0.02) {
      setRect(null);
      setPhase("idle");
      return;
    }
    setPhase("editing");
  }
  function cancel() {
    setRect(null);
    setPhase("idle");
    setError("");
  }
  async function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!rect || !instruction.trim() || phase === "saving") return;
    setPhase("saving");
    setError("");
    try {
      const edited = await regionEditSlide(projectId, slideId, toSlideBox(rect), instruction.trim(), revision);
      setResult(edited);
      setInstruction("");
      setPhase("done");
      await onEdited(edited);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "区域修改失败");
      setPhase("editing");
    }
  }
  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.stopPropagation();
      if (phase === "editing") cancel();
      else onExit();
    }
  }
  const popoverBelow = rect ? rect.y + rect.h < 0.62 : true;
  const popoverRight = rect ? rect.x > 0.55 : false;
  return (
    <div
      ref={layer}
      className={`region-layer is-${phase}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onKeyDown={onKeyDown}
      role="application"
      aria-label="框选区域修改：在页面上拖出一个矩形"
      tabIndex={-1}
    >
      {phase === "idle" && !rect && (
        <div className="region-hint"><Icon name="select" size={14} />拖动鼠标框选要修改的区域 · Esc 退出</div>
      )}
      {rect && (
        <div
          className="region-rect"
          style={{ left: `${rect.x * 100}%`, top: `${rect.y * 100}%`, width: `${rect.w * 100}%`, height: `${rect.h * 100}%` }}
        >
          {phase === "saving" && <span className="region-badge"><span className="spinner" />正在修改并重新渲染…</span>}
          {phase === "done" && result && (
            <span className="region-badge success"><Icon name="check" size={12} />已修改：{result.edited.map((item) => item.label).join("、")}</span>
          )}
        </div>
      )}
      {rect && (phase === "editing" || phase === "saving") && (
        <form
          className={`region-popover${popoverBelow ? " below" : " above"}${popoverRight ? " align-right" : ""}`}
          style={{
            left: popoverRight ? undefined : `${rect.x * 100}%`,
            right: popoverRight ? `${(1 - rect.x - rect.w) * 100}%` : undefined,
            top: popoverBelow ? `calc(${(rect.y + rect.h) * 100}% + 8px)` : undefined,
            bottom: popoverBelow ? undefined : `calc(${(1 - rect.y) * 100}% + 8px)`,
          }}
          onSubmit={submit}
          onPointerDown={(event) => event.stopPropagation()}
        >
          <label htmlFor="region-instruction">想怎样修改这块区域？</label>
          <textarea
            id="region-instruction"
            ref={input}
            rows={2}
            value={instruction}
            disabled={phase === "saving"}
            onChange={(event) => setInstruction(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void submit();
              }
            }}
            placeholder="例如：把这里改成三步流程 / 这个数字加粗突出 / 改为：新的标题"
          />
          <div className="region-chips">
            {QUICK_INSTRUCTIONS.map((item) => (
              <button type="button" key={item} className="btn-sm" disabled={phase === "saving"} onClick={() => { setInstruction(item); input.current?.focus(); }}>{item}</button>
            ))}
          </div>
          {error && <p className="region-error" role="alert"><Icon name="alert" size={14} />{error}</p>}
          <div className="region-actions">
            <small>Enter 提交 · Shift+Enter 换行</small>
            <button type="button" className="ghost btn-sm" onClick={cancel} disabled={phase === "saving"}>取消</button>
            <button className="primary btn-sm" disabled={phase === "saving" || disabled || !instruction.trim()}>
              {phase === "saving" ? <><span className="spinner" />修改中</> : <><Icon name="wand" size={14} />应用修改</>}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
