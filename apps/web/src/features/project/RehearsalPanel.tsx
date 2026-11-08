import { useEffect, useRef, useState } from "react";

import { buildRehearsal, rehearsalCardUrl } from "../../api";
import type { Rehearsal } from "../../api";

const format = (seconds: number) => `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(Math.max(0, Math.round(seconds % 60))).padStart(2, "0")}`;
const KIND_LABELS = { definition: "数字口径", limitation: "前提与局限", method: "方法选择", omitted: "未讲到的材料" } as const;

/** Rehearsal: per-slide time budget, a practice timer and source-grounded audience questions. */
export function RehearsalPanel({ projectId, onJumpToSlide }: { projectId: string; onJumpToSlide?: (slideId: string, position: number) => void }) {
  const [rehearsal, setRehearsal] = useState<Rehearsal | null>(null);
  const [minutes, setMinutes] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [page, setPage] = useState(0);
  const [pageStart, setPageStart] = useState(0);
  const [actual, setActual] = useState<number[]>([]);
  const timer = useRef<number | null>(null);

  useEffect(() => () => { if (timer.current) window.clearInterval(timer.current); }, []);

  async function prepare() {
    setBusy(true);
    setError("");
    try {
      const result = await buildRehearsal(projectId, minutes === "" ? null : minutes);
      setRehearsal(result);
      if (minutes === "" && result.durationMinutes) setMinutes(result.durationMinutes);
      reset();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "排练卡生成失败");
    } finally {
      setBusy(false);
    }
  }
  function reset() {
    if (timer.current) window.clearInterval(timer.current);
    timer.current = null;
    setRunning(false);
    setElapsed(0);
    setPage(0);
    setPageStart(0);
    setActual([]);
  }
  function toggle() {
    if (running) {
      if (timer.current) window.clearInterval(timer.current);
      timer.current = null;
      setRunning(false);
      return;
    }
    const startedAt = Date.now() - elapsed * 1000;
    timer.current = window.setInterval(() => setElapsed((Date.now() - startedAt) / 1000), 250);
    setRunning(true);
  }
  function next() {
    if (!rehearsal) return;
    setActual((current) => [...current, elapsed - pageStart]);
    setPageStart(elapsed);
    setPage((current) => Math.min(current + 1, rehearsal.pacing.pages.length - 1));
  }

  const pages = rehearsal?.pacing.pages ?? [];
  const current = pages[page];
  const pageElapsed = elapsed - pageStart;
  const over = current ? pageElapsed > current.budgetSeconds : false;
  const longest = Math.max(1, ...pages.map((item) => item.budgetSeconds));

  return (
    <section className="rehearsal-panel panel" aria-label="演讲排练">
      <header className="rehearsal-head">
        <b>演讲排练</b>
        <label>时长<input type="number" min={1} max={240} value={minutes} placeholder="分钟" onChange={(event) => setMinutes(event.target.value ? Number(event.target.value) : "")} />分钟</label>
        <button type="button" className="primary btn-sm" onClick={prepare} disabled={busy}>{busy ? "计算中…" : rehearsal ? "重新计算" : "生成排练卡"}</button>
        {rehearsal && <a className="ghost btn-sm" href={rehearsalCardUrl(projectId)}>下载排练卡</a>}
      </header>
      {error && <p className="eval-error" role="alert">{error}</p>}
      {rehearsal && (
        <>
          <div className={`rehearsal-timer${over ? " over" : ""}`}>
            <strong>{format(pageElapsed)}</strong>
            <span>第 {current?.position} 页 · 预算 {current?.budgetSeconds} 秒 · 总计 {format(elapsed)} / {format(rehearsal.pacing.totalSeconds)}</span>
            <button type="button" className="ghost btn-sm" onClick={toggle}>{running ? "暂停" : elapsed ? "继续" : "开始计时"}</button>
            <button type="button" className="ghost btn-sm" onClick={next} disabled={!running}>下一页</button>
            <button type="button" className="ghost btn-sm" onClick={reset}>重置</button>
          </div>
          {!!rehearsal.advice.length && <ul className="eval-suggestions">{rehearsal.advice.map((item) => <li key={item}>{item}</li>)}</ul>}
          <div className="rehearsal-timeline" aria-label="每页时间预算">
            {pages.map((item, index) => (
              <div key={item.position} className={`rehearsal-row ${item.pressure}${index === page && rehearsal ? " current" : ""}`}>
                <span>第 {item.position} 页</span>
                <small>{format(item.startSeconds)}</small>
                <span>
                  <button type="button" className="link-button" onClick={() => item.slideId && onJumpToSlide?.(item.slideId, item.position)}>{item.title}</button>
                  <div className="bar" style={{ width: `${Math.round((item.budgetSeconds / longest) * 100)}%` }} />
                </span>
                <small>{actual[index] !== undefined ? `${Math.round(actual[index])}/${item.budgetSeconds}s` : `${item.budgetSeconds}s`}{item.pressure === "compress" ? " · 需压缩" : ""}</small>
              </div>
            ))}
          </div>
          {!!rehearsal.questions.length && (
            <details open>
              <summary>可能被问到的 {rehearsal.questions.length} 个问题（答案只来自材料）</summary>
              <ol className="rehearsal-qa">
                {rehearsal.questions.map((item) => (
                  <li key={item.question}>
                    <p><span className="eval-issue-tag">{KIND_LABELS[item.kind]}</span> <b>{item.question}</b></p>
                    <p>{item.answer}</p>
                    {item.sourceRef && <small>出处：{item.sourceRef.document} · {item.sourceRef.section}{item.sourceRef.page ? ` · 第 ${item.sourceRef.page} 页` : ""}</small>}
                  </li>
                ))}
              </ol>
            </details>
          )}
        </>
      )}
    </section>
  );
}
