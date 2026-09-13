import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getProjects, json } from "../../api";
import type { PersonalProfile } from "./PersonalizationPage";

type Example = { id: string; label: string; status: string; features: { roleSequence: string[]; slideCount: number; averageTitleLength: number; quality?: { imported?: boolean; passed?: boolean } } };
type Reference = { id: string; name: string; active: boolean; analysis: { slideCount?: number; preview?: { status: string; pages?: { page: number }[] } } };
const send = <T,>(url: string, body: unknown) => json<T>(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const roles: Record<string, string> = { cover: "封面", content: "正文", agenda: "目录", background: "背景", problem: "问题", method: "方法", data: "数据", insight: "判断", conclusion: "结论", comparison: "对照", evidence: "证据", architecture: "架构", section: "章节", questions: "问答" };

export function ExperiencePanel({ profile, paused = false }: { profile: PersonalProfile; paused?: boolean }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const [projectId, setProjectId] = useState(""), [label, setLabel] = useState("");
  const [previewSoftware, setPreviewSoftware] = useState("libreoffice");
  const [retain, setRetain] = useState(false), [includeFiles, setIncludeFiles] = useState(false);
  const projects = useQuery({ queryKey: ["projects"], queryFn: getProjects });
  const data = useQuery({ queryKey: ["personal-experience", profile.id], queryFn: () => json<{ cases: Example[]; references: Reference[] }>(`/me/profiles/${profile.id}/experience`), enabled: !busy && !paused });
  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true); setMessage("");
    try { const result = await action(); await qc.invalidateQueries({ queryKey: ["personal-profiles"] }); await qc.invalidateQueries({ queryKey: ["personal-experience"] }); setMessage(typeof result === "string" ? result : success); }
    catch (error) { setMessage(error instanceof Error ? error.message : "操作失败"); }
    finally { setBusy(false); }
  }
  const base = `/me/profiles/${profile.id}`;
  return <div className="panel personal-experience">
    <h3>从作品和参考稿中积累经验</h3>
    <p>案例只保留页面结构和表达规律；原生参考模板需要你明确选择保留原文件。</p>
    {message && <p role="status">{message}</p>}
    {data.error && <p role="alert">{data.error.message}</p>}
    <form onSubmit={event => { event.preventDefault(); void run(() => send(`${base}/cases`, { project_id: projectId, label, revision: profile.revision }), "作品已提取为待确认案例。"); }}>
      <label>选择历史作品<select value={projectId} required onChange={event => setProjectId(event.target.value)}><option value="">请选择作品</option>{projects.data?.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
      <label>案例名称<input value={label} maxLength={120} required onChange={event => setLabel(event.target.value)} placeholder="例如：我满意的一次经营汇报" /></label>
      <button disabled={busy}>提取表达案例</button>
    </form>
    {data.data?.cases.map(example => <article className="personal-case" key={example.id}>
      <h4>{example.label} · {example.status === "confirmed" ? "已确认" : "待确认"}</h4>
      <p>{example.features.slideCount} 页；标题平均 {example.features.averageTitleLength} 字</p>
      <p>{example.features.roleSequence.map(role => roles[role] || role).join(" → ")}</p>
      <p>{example.features.quality?.imported ? "这是导入案例，确认表示你已核对其适用性。" : example.features.quality?.passed ? "来源作品已通过质量检查。" : "来源作品需要先修复质量问题，再重新采集。"}</p>
      {example.status !== "confirmed" && <button disabled={busy} onClick={() => void run(() => send(`${base}/cases/${example.id}/confirm`, { revision: profile.revision, reviewed_imported_example: !!example.features.quality?.imported }), "案例已确认；提炼出的新规则仍需逐条确认。")}>已核对，作为表达案例</button>}
      <button disabled={busy} onClick={() => void run(() => json(`${base}/cases/${example.id}`, { method: "DELETE" }), "案例及依赖它的规则已忘记，旧任务上下文已失效。")}>忘记案例</button>
    </article>)}
    <h4>原生参考模板</h4>
    <label>参考预览软件<select value={previewSoftware} onChange={event => setPreviewSoftware(event.target.value)}><option value="libreoffice">LibreOffice</option><option value="powerpoint-windows">Windows PowerPoint</option><option value="wps">WPS</option></select></label>
    <label className="personal-consent"><input type="checkbox" checked={retain} onChange={event => setRetain(event.target.checked)} />允许在本机保存原始 PPTX，用于母版复用和实际预览</label>
    <label>保存参考模板<input type="file" accept=".pptx" disabled={busy || !retain} onChange={event => {
      const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
      void run(async () => { const form = new FormData(); form.set("file", file); form.set("revision", String(profile.revision)); form.set("retain_original", "true"); await json(`${base}/reference-template`, { method: "POST", body: form }); }, "原稿已保存在本机；可查看预览后启用模板，提取的视觉规则仍需确认。");
    }} /></label>
    {data.data?.references.map(reference => <article className="personal-case" key={reference.id}>
      <h4>{reference.name} · {reference.active ? "后续作品使用此母版" : "尚未启用"}</h4>
      <div className="personal-actions">
        <button disabled={busy} onClick={() => void run(async () => { const result = await send<{ message?: string; status: string }>(`${base}/references/${reference.id}/preview`, { software: previewSoftware }); return result.message || (result.status === "rendered-needs-review" ? "参考稿实际预览已生成。" : "预览未完成，请检查本机办公软件配置。"); }, "预览已更新。")}>用本机办公软件预览</button>
        <button disabled={busy || reference.active} onClick={() => void run(() => send(`${base}/references/${reference.id}/activate`, { revision: profile.revision }), "后续作品将使用此母版；正式交付前需核对实际导出文件。")}>启用原生母版</button>
        <button disabled={busy} onClick={() => void run(() => json(`${base}/references/${reference.id}`, { method: "DELETE" }), "原稿、预览及依赖规则已删除。")}>删除原稿与相关经验</button>
      </div>
      <div className="reference-thumbnails">{reference.analysis.preview?.pages?.map(page => <a key={page.page} target="_blank" rel="noreferrer" href={`/api/v1${base}/references/${reference.id}/pages/${page.page}`}><img alt={`参考稿第 ${page.page} 页`} src={`/api/v1${base}/references/${reference.id}/pages/${page.page}`} loading="lazy" /></a>)}</div>
    </article>)}
    <h4>迁移完整经验</h4>
    <p>包含确认过的规则与抽象案例。勾选下面的选项后，也会携带原始参考稿，其中可能含有业务内容。</p>
    <label className="personal-consent"><input type="checkbox" checked={includeFiles} onChange={event => setIncludeFiles(event.target.checked)} />导出或导入时允许包含原始参考文件</label>
    <button disabled={busy} onClick={() => void run(async () => {
      const pack = await send(`${base}/experience-pack`, { include_original_references: includeFiles });
      const url = URL.createObjectURL(new Blob([JSON.stringify(pack)], { type: "application/json" }));
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = "yingzhang-experience-v2.json"; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }, "完整经验包已导出。")}>导出完整经验包</button>
    <label>导入完整经验包<input type="file" accept=".json" disabled={busy} onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
      void run(async () => { const form = new FormData(); form.set("file", file); form.set("retain_originals", String(includeFiles)); await json("/me/experience-pack-import", { method: "POST", body: form }); }, "已导入为暂停使用的独立档案，案例和规则需要重新确认。");
    }} /></label>
  </div>;
}
