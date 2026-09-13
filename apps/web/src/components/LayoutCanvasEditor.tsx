import { useEffect, useRef, useState } from "react";
import type { PointerEvent } from "react";
import type { SlideSpec } from "../api";

type Region = NonNullable<NonNullable<SlideSpec["layoutPlan"]>["regions"]>[number];
type DragState = { id: string; mode: "move" | "resize"; startX: number; startY: number; region: Region } | null;

const LABELS: Record<string, string> = { title: "标题", primary: "主要内容", support: "辅助内容", claim: "核心结论", source: "来源" };
const clamp = (value: number, minimum: number, maximum: number) => Math.min(maximum, Math.max(minimum, value));
const snap = (value: number) => Math.round(value * 4) / 4;

export function LayoutCanvasEditor({ slide, busy, onSave }: {
  slide?: SlideSpec;
  busy?: boolean;
  onSave: (regions: Region[], focalPoint: "left" | "right" | "full") => Promise<void>;
}) {
  const plan = slide?.layoutPlan;
  const [regions, setRegions] = useState<Region[]>(plan?.regions || []);
  const [focalPoint, setFocalPoint] = useState<"left" | "right" | "full">((plan?.focalPoint as "left" | "right" | "full") || "right");
  const [drag, setDrag] = useState<DragState>(null);
  const canvas = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setRegions(plan?.regions || []);
    setFocalPoint((plan?.focalPoint as "left" | "right" | "full") || "right");
  }, [slide?.id, plan?.manualOverride]);
  if (!slide || !plan || !regions.length) return null;

  function start(event: PointerEvent<HTMLElement>, region: Region, mode: "move" | "resize") {
    if (region.locked) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrag({ id: region.id, mode, startX: event.clientX, startY: event.clientY, region: { ...region } });
  }
  function move(event: PointerEvent<HTMLElement>) {
    if (!drag || !canvas.current) return;
    const rect = canvas.current.getBoundingClientRect();
    const dx = (event.clientX - drag.startX) / rect.width * 12;
    const dy = (event.clientY - drag.startY) / rect.height * 12;
    setRegions((items) => items.map((item) => {
      if (item.id !== drag.id) return item;
      if (drag.mode === "resize") return { ...item, w: snap(clamp(drag.region.w + dx, 1, 12 - drag.region.x)), h: snap(clamp(drag.region.h + dy, .5, 12 - drag.region.y)) };
      return { ...item, x: snap(clamp(drag.region.x + dx, 0, 12 - drag.region.w)), y: snap(clamp(drag.region.y + dy, 0, 12 - drag.region.h)) };
    }));
  }
  function toggleLock(id: string) {
    setRegions((items) => items.map((item) => item.id === id ? { ...item, locked: !item.locked } : item));
  }
  return (
    <details className="layout-canvas-editor">
      <summary><b>页面画布</b><small>拖动区域调整位置，右下角调整大小</small></summary>
      <div className="layout-canvas" ref={canvas}>
        {Array.from({ length: 11 }, (_, index) => <i className="grid-v" key={`v-${index}`} style={{ left: `${(index + 1) / 12 * 100}%` }} />)}
        {Array.from({ length: 11 }, (_, index) => <i className="grid-h" key={`h-${index}`} style={{ top: `${(index + 1) / 12 * 100}%` }} />)}
        {regions.map((region) => (
          <div
            className={`canvas-region region-${region.id} ${region.locked ? "locked" : ""}`}
            key={region.id}
            style={{ left: `${region.x / 12 * 100}%`, top: `${region.y / 12 * 100}%`, width: `${region.w / 12 * 100}%`, height: `${region.h / 12 * 100}%` }}
            onPointerDown={(event) => start(event, region, "move")}
            onPointerMove={move}
            onPointerUp={() => setDrag(null)}
          >
            <span>{LABELS[region.id] || region.id}</span>
            <button type="button" onPointerDown={(event) => event.stopPropagation()} onClick={() => toggleLock(region.id)}>{region.locked ? "解锁" : "锁定"}</button>
            {!region.locked && <i className="resize-handle" onPointerDown={(event) => { event.stopPropagation(); start(event, region, "resize"); }} onPointerMove={move} onPointerUp={() => setDrag(null)} />}
          </div>
        ))}
      </div>
      <div className="canvas-actions">
        <label>视觉重心<select value={focalPoint} onChange={(event) => setFocalPoint(event.target.value as "left" | "right" | "full")}><option value="left">偏左</option><option value="right">偏右</option><option value="full">通栏</option></select></label>
        <button className="primary" disabled={busy} onClick={() => onSave(regions, focalPoint)}>保存画布布局</button>
        {plan.manualOverride && <span>已使用手工布局</span>}
      </div>
    </details>
  );
}
