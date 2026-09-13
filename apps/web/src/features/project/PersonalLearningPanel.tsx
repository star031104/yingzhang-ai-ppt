import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { exportUrl, json } from "../../api";

type Comparison = { id: string; status: string; modelComparison: string; revealed?: Record<string, string>; reviews: Record<string, Record<string, number>> };
type Verification = { id: string; status: string; fileHash: string; software: string; report: { message?: string; problems?: string[]; pages?: { page: number }[] } };
const send = <T,>(path: string, body: unknown) => json<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const dimensions: Record<string, string> = { logic: "汇报逻辑", visual: "视觉质量", completeness: "内容完整", accuracy: "事实准确", personalFit: "是否符合我的习惯" };

export function PersonalLearningPanel({ projectId }: { projectId: string }) {
  const qc = useQueryClient(), base = `/projects/${projectId}`;
  const [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const [selectedSoftware, setSoftware] = useState("");
  const office = useQuery({ queryKey: ["desktop-capabilities", projectId], queryFn: () => json<Record<string, boolean | string | null>>(`${base}/desktop-capabilities`) });
  const software = selectedSoftware || ["powerpoint-windows", "libreoffice", "wps"].find(key => office.data?.[key]) || "powerpoint-windows";
  const [scores, setScores] = useState<Record<string, number>>({ logic: 80, visual: 80, completeness: 80, accuracy: 80, personalFit: 80 });
  const [checks, setChecks] = useState<Record<string, Record<string, boolean>>>({});
  const comparisons = useQuery({ queryKey: ["personal-comparisons", projectId], queryFn: () => json<Comparison[]>(`${base}/personal-comparisons`), enabled: !busy });
  const verifications = useQuery({ queryKey: ["desktop-verifications", projectId], queryFn: () => json<Verification[]>(`${base}/desktop-verifications`), enabled: !busy });
  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true); setMessage("正在处理，请稍候…");
    try { const result = await action(); await qc.invalidateQueries({ queryKey: ["personal-comparisons", projectId] }); await qc.invalidateQueries({ queryKey: ["desktop-verifications", projectId] }); await qc.invalidateQueries({ queryKey: ["personal-profiles"] }); setMessage(typeof result === "string" ? result : success); }
    catch (error) { setMessage(error instanceof Error ? error.message : "操作失败"); }
    finally { setBusy(false); }
  }
  return <details className="panel personal-learning"><summary>个人经验回传与交付验收</summary>
    {message && <p role="status">{message}</p>}
    <h3>在 PowerPoint / WPS 中改完，再教给助手</h3>
    <p>上传从本项目导出后修改的 PPTX。系统会匹配页面和对象，只从可靠匹配中提出视觉规则建议；正文和数字变化不会自动成为长期经验。</p>
    <label>上传修改稿<input type="file" accept=".pptx" disabled={busy} onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
      void run(async () => { const form = new FormData(); form.set("file", file); const result = await json<{ alignment: { matchedObjects: number; uncertainObjects: number }; suggestions: unknown[] }>(`${base}/external-feedback`, { method: "POST", body: form }); return `已可靠匹配 ${result.alignment.matchedObjects} 个对象；${result.alignment.uncertainObjects} 个对象无法可靠匹配。产生 ${result.suggestions.length} 条待确认建议，请在“我的助手”查看。`; }, "修改稿已对照。");
    }} /></label>
    <h3>比较普通成稿与个人成稿</h3>
    <p>A/B 顺序随机。请先查看两份作品并分别评分，评分完成后再揭晓来源。</p>
    {comparisons.data?.length ? comparisons.data.map(item => <div className="personal-case" key={item.id}>
      <p>{item.modelComparison === "both-model" ? "两路使用相同模型配置独立完成成稿" : item.modelComparison === "partial-model" ? "模型调用存在失败或缺页，部分内容由内置规划补齐" : "内置规划对照（未使用外部模型）"}</p>
      {item.status === "pending" ? <button disabled={busy} onClick={() => void run(() => send(`${base}/personal-comparisons/${item.id}/render`, {}), "A/B 对照已生成，可分别查看。")}>生成两份对照作品</button> : <>
        <div className="personal-actions">{["A", "B"].map(label => <a key={label} href={`/api/v1${base}/personal-comparisons/${item.id}/${label}/pptx`}>下载候选 {label}</a>)}</div>
        <div className="personal-score-grid">{Object.entries(dimensions).map(([key, label]) => <label key={key}>{label}<input type="number" min={0} max={100} value={scores[key]} onChange={event => setScores({ ...scores, [key]: Number(event.target.value) })} /></label>)}</div>
        {["A", "B"].map(label => <button key={label} disabled={busy} onClick={() => void run(() => send(`${base}/personal-comparisons/${item.id}/review`, { label, scores }), `候选 ${label} 的评分已保存。`)}>保存 {label} 的评分{item.reviews[label] ? "（已评，可修改）" : ""}</button>)}
        {item.revealed && <p>已揭晓：{Object.entries(item.revealed).map(([label, source]) => `${label} 为${source === "personal" ? "个人" : "普通"}成稿`).join("；")}</p>}
      </>}
    </div>) : <p>选择个人档案重新规划后，将记录两路成稿对照。</p>}
    <h3>核对实际 PPTX 显示</h3>
    <p>先<a href={exportUrl(projectId, "pptx", "draft")}>导出检查草稿</a>，再使用本机已安装的办公软件生成验收预览。无法启动的软件会明确显示不可用。</p>
    <label>目标软件<select value={software} onChange={event => { setSoftware(event.target.value); setChecks({}); }}><option value="libreoffice">LibreOffice</option><option value="powerpoint-windows">Windows PowerPoint</option><option value="wps">WPS</option><option value="powerpoint-macos">Mac PowerPoint（需要手工验收）</option></select></label>
    {office.data && !office.data[software] && <p>本机未检测到该软件可用的自动化接口。请选择其他软件，或手动导出 PDF 后上传验收。</p>}
    <button disabled={busy || !office.data?.[software]} onClick={() => void run(() => send(`${base}/desktop-verifications`, { software }), "已记录实际软件验收结果，请查看下方详情。")}>生成实际软件验收预览</button>
    <label>或上传从目标软件导出的验收 PDF<input type="file" accept=".pdf" disabled={busy} onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
      void run(async () => { const current = await json<{ fileHash: string | null }>(`${base}/desktop-file`); if (!current.fileHash) throw new Error("请先导出当前 PPTX 草稿"); const form = new FormData(); form.set("file", file); form.set("software", software); form.set("file_hash", current.fileHash); await json(`${base}/desktop-verifications/manual`, { method: "POST", body: form }); }, "已收到人工导出的验收稿，请逐页核对。这份 PDF 的软件来源以你的声明为准。");
    }} /></label>
    {verifications.data?.map(item => <article className="personal-case" key={item.id}>
      <h4>{item.software} · {({ accepted: "已验收", "rendered-needs-review": "预览已生成，待核对", unavailable: "软件不可用", failed: "渲染未完成", "needs-repair": "需要修复" } as Record<string, string>)[item.status] || item.status}</h4>
      {item.report.message && <p>{item.report.message}</p>}{item.report.problems?.map(problem => <p key={problem}>{problem}</p>)}
      <div className="reference-thumbnails">{item.report.pages?.map(page => <a key={page.page} target="_blank" rel="noreferrer" href={`/api/v1${base}/desktop-verifications/${item.id}/pages/${page.page}`}><img alt={`${item.software} 实际显示第 ${page.page} 页`} src={`/api/v1${base}/desktop-verifications/${item.id}/pages/${page.page}`} loading="lazy" /></a>)}</div>
      {item.status === "rendered-needs-review" && <><div className="personal-switches">{Object.entries({ fonts: "字体正确", layout: "布局无截断", content: "内容完整准确" }).map(([key, label]) => <label key={key}><input type="checkbox" checked={checks[item.id]?.[key] || false} onChange={event => setChecks({ ...checks, [item.id]: { ...checks[item.id], [key]: event.target.checked } })} />{label}</label>)}</div><button disabled={busy || !["fonts", "layout", "content"].every(key => checks[item.id]?.[key])} onClick={() => void run(() => send(`${base}/desktop-verifications/${item.id}/accept`, { file_hash: item.fileHash, checked_fonts: checks[item.id]?.fonts, checked_layout: checks[item.id]?.layout, checked_content: checks[item.id]?.content }), "该文件已验收；文件变化后需重新验收。")}>确认这一版本通过验收</button></>}
    </article>)}
  </details>;
}
