import { ExperiencePanel } from "./ExperiencePanel";
import { AccountPanel } from "./AccountPanel";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { json } from "../../api";
import { Notice } from "../../components/Notice";
import "./personalization.css";

export type PersonalMemory = { id: string; key: string; value: string; label: string; description: string; status: string; origin: string; evidenceCount: number };
export type PersonalProfile = { id: string; name: string; scenario: string; revision: number; use_memory: boolean; capture_feedback: boolean; memories: PersonalMemory[] };
type Catalog = { profiles: PersonalProfile[]; epoch: number; options: Record<string, Record<string, string>>; labels: Record<string, string> };
type Feedback = { id: string; kind: string; status: string; features: { proposal?: { key: string; value: string }; changedFields: string[] }; revision: number };
type Reset = { id: string; digest: string; memoryCount: number; profileCount: number; feedbackCount: number; caseCount?: number; referenceCount?: number; retained: string[]; message: string };
export const getPersonalProfiles = () => json<Catalog>("/me/profiles");
const headers = { "Content-Type": "application/json" };
const post = <T,>(url: string, value: unknown) => json<T>(url, { method: "POST", headers, body: JSON.stringify(value) });
const SCENARIOS: Record<string, string> = { all: "所有场景", business: "商业汇报", review: "经营复盘", executive: "高管决策", academic: "学术答辩", teaching: "课程教学", product: "产品发布", pitch: "融资路演", sales: "客户提案", strategy: "战略规划" };

export function PersonalizationPage() {
  const qc = useQueryClient();
  const catalog = useQuery({ queryKey: ["personal-profiles"], queryFn: getPersonalProfiles });
  const [selected, setSelected] = useState("");
  const [name, setName] = useState("");
  const [scenario, setScenario] = useState("all");
  const [key, setKey] = useState("narrative_order");
  const [choice, setChoice] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [reset, setReset] = useState<Reset | null>(null);
  const profile = catalog.data?.profiles.find(item => item.id === selected) ?? catalog.data?.profiles[0];
  const feedback = useQuery({ queryKey: ["personal-feedback", profile?.id], queryFn: () => json<Feedback[]>(`/me/profiles/${profile!.id}/feedback`), enabled: !!profile && !busy });
  async function run(action: () => Promise<unknown>, message: string) {
    setBusy(true); setStatus("");
    try { const result = await action(); await qc.invalidateQueries({ queryKey: ["personal-profiles"] }); await qc.invalidateQueries({ queryKey: ["personal-feedback"] }); setStatus(typeof result === "string" ? result : message); }
    catch (error) { setStatus(error instanceof Error ? error.message : "操作失败，请重试"); }
    finally { setBusy(false); }
  }
  function update(patch: Partial<PersonalProfile>) {
    if (!profile) return;
    return run(() => json(`/me/profiles/${profile.id}`, { method: "PATCH", headers, body: JSON.stringify({ name: profile.name, scenario: profile.scenario, revision: profile.revision, use_memory: profile.use_memory, capture_feedback: profile.capture_feedback, ...patch }) }), "档案已保存；新的设置用于后续任务。");
  }
  function preview(scope: string, target_id?: string) {
    return run(async () => setReset(await post<Reset>("/me/memory-reset/preview", { scope, target_id })), "请核对下面的清理范围。");
  }
  const choices = catalog.data?.options[key] ?? {};
  const actualChoice = choice in choices ? choice : Object.keys(choices)[0];
  return <section className="content personal-page">
    <div className="section-heading"><div><span className="kicker">我的助手</span><h2>把经验教给映章</h2><p>按场景记住汇报逻辑、视觉偏好与修改习惯。事实和质量检查始终生效。</p></div></div>
    <div className="personal-policy"><b>本机个人工作区</b><span>记忆保存在本机；使用外部模型时，本次适用的偏好会随创作要求发送。自动观察只形成待确认建议。</span></div>
    {catalog.isLoading && <p role="status">正在读取个人档案…</p>}
    {catalog.error && <Notice text={catalog.error.message} tone="error" />}
    {status && <div role="status"><Notice text={status} tone="info" /></div>}
    <div className="personal-grid">
      <div className="panel">
        <h3>场景档案</h3><p>不同汇报场景可以保留不同习惯。</p>
        <div className="personal-profiles">{catalog.data?.profiles.map(item => <button type="button" aria-pressed={profile?.id === item.id} className={profile?.id === item.id ? "selected" : ""} key={item.id} onClick={() => { setSelected(item.id); setReset(null); }}><b>{item.name}</b><small>{SCENARIOS[item.scenario] || item.scenario} · {item.use_memory ? "使用中" : "已暂停"}</small></button>)}</div>
        <form onSubmit={event => { event.preventDefault(); void run(async () => { const created = await post<PersonalProfile>("/me/profiles", { name, scenario }); setSelected(created.id); setName(""); }, "档案已创建，现在可以添加经验。"); }}>
          <label>档案名称<input value={name} onChange={event => setName(event.target.value)} required maxLength={120} placeholder="例如：我的经营汇报" /></label>
          <label>适用场景<select value={scenario} onChange={event => setScenario(event.target.value)}>{Object.entries(SCENARIOS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
          <button className="primary" disabled={busy}>创建场景档案</button>
        </form>
        <label className="personal-import">导入经验包<input type="file" accept=".json" disabled={busy} onChange={event => { const file = event.target.files?.[0]; if (!file) return; void run(async () => { if (file.size > 128 * 1024) throw new Error("经验包不能超过 128 KB"); const imported = await post<PersonalProfile>("/me/profile-import", JSON.parse(await file.text())); setSelected(imported.id); }, "已创建暂停使用的独立档案，请逐条确认规则后启用。"); event.target.value = ""; }} /></label>
      </div>
      <div className="panel">
        {profile ? <>
          <h3>{profile.name}</h3>
          <div className="personal-switches">
            <label><input type="checkbox" checked={profile.use_memory} disabled={busy} onChange={event => void update({ use_memory: event.target.checked })} />使用已有经验</label>
            <label><input type="checkbox" checked={profile.capture_feedback} disabled={busy} onChange={event => void update({ capture_feedback: event.target.checked })} />从新的修改中提出学习建议</label>
          </div>
          <p className="field-help">不开启学习也可以手动教授。暂停使用时停止新建议采集；已启动任务保持其快照，清除操作会使旧任务失效。</p>
          <form className="personal-teach" onSubmit={event => { event.preventDefault(); void run(() => post(`/me/profiles/${profile.id}/memories`, { key, value: actualChoice, revision: profile.revision }), "经验已保存。相同类型的旧规则已替换。"); }}>
            <label>教它记住什么<select value={key} onChange={event => { setKey(event.target.value); setChoice(""); }}>{Object.entries(catalog.data?.labels ?? {}).filter(([id]) => Object.keys(catalog.data?.options[id] ?? {}).length > 0).map(([id, label]) => <option value={id} key={id}>{label}</option>)}</select></label>
            <label>你的偏好<select value={actualChoice ?? ""} onChange={event => setChoice(event.target.value)}>{Object.entries(choices).map(([id, label]) => <option value={id} key={id}>{label}</option>)}</select></label>
            <button className="primary" disabled={busy || !actualChoice}>以后这个场景都这样</button>
          </form>
          <div className="personal-memories">{profile.memories.length ? profile.memories.map(item => <article key={item.id}>
            <div><b>{item.label}</b><p>{item.description}</p><small>{item.status === "candidate" ? "待确认" : "已确认"} · {item.origin === "explicit" ? "你明确教授" : item.origin === "accepted-edit" ? "来自确认的修改" : item.origin === "reference" ? "参考稿提取" : "导入经验包"}</small></div>
            <div className="personal-actions">{item.status === "candidate" && <button disabled={busy} onClick={() => void run(() => post(`/me/memories/${item.id}/confirm`, { revision: profile.revision }), "已确认这条经验。")}>确认</button>}<button disabled={busy} onClick={() => void preview("memory", item.id)}>忘记</button></div>
          </article>) : <p>还没有记忆。先添加一条你最常重复的要求。</p>}</div>
          <label className="personal-import">从参考 PPT 提取建议<input type="file" accept=".pptx" disabled={busy} onChange={event => { const file = event.target.files?.[0]; if (!file) return; void run(async () => { const form = new FormData(); form.set("file", file); form.set("revision", String(profile.revision)); const result = await json<{ message: string }>(`/me/profiles/${profile.id}/reference`, { method: "POST", body: form }); return result.message; }, "已分析参考稿。提取的字体、配色及页型为待确认建议；原文件和正文不保存。"); event.target.value = ""; }} /></label>
          <p className="field-help">参考导入支持字体、主题色及有限的页型构图；复杂母版、动画及逐对象位置不会自动复制。不会把业务数字学成个人经验。</p>
          <button disabled={busy} onClick={() => void run(async () => { const pack = await json(`/me/profiles/${profile.id}/export`); const url = URL.createObjectURL(new Blob([JSON.stringify(pack, null, 2)], { type: "application/json" })); const link = document.createElement("a"); link.href = url; link.download = "yingzhang-personal-profile.json"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }, "已导出确认过的规则；不包含材料、修改正文或 API Key。")}>导出经验包</button>
        </> : <div><h3>从一条明确要求开始</h3><p>创建档案后，可以教授叙事、字体、配色、标题方式和审阅习惯。你随时可以查看它记住了什么。</p></div>}
      </div>
    </div>
    {profile && <div className="panel"><h3>本轮修改的学习建议</h3><p>只从已绑定该档案、开启学习后的新修改产生建议。业务纠错不会被自动保存。</p>
      {feedback.data?.length ? feedback.data.map(item => { const p = item.features.proposal; return <article className="personal-feedback" key={item.id}><div><b>{p ? catalog.data?.labels[p.key] : "修改观察"}</b><p>{p ? catalog.data?.options[p.key]?.[p.value] : "没有可提取的长期规则"}</p><small>页面版本 {item.revision}；后续修改或回滚后建议失效。</small></div><button disabled={busy} onClick={() => void run(() => post(`/me/feedback/${item.id}/confirm`, {}), "已保存为场景经验。")}>以后也这样</button><button disabled={busy} onClick={() => void run(() => json(`/me/feedback/${item.id}`, { method: "DELETE" }), "本次修改不作为长期经验。")}>只改这次</button></article>; }) : <p className="field-help">目前没有待确认建议。</p>}
    </div>}
    {profile && <ExperiencePanel key={profile.id} profile={profile} paused={busy} />}
    <AccountPanel />
    <div className="panel personal-reset"><h3>记忆与清理</h3><p>清空后，新任务恢复默认流程，旧任务停止沿用被清除的记忆。现有作品、材料、模型设置和已下载备份保留。原生参考稿、案例和对照学习记录纳入清理。</p>
      <div className="personal-actions">{profile && <button disabled={busy} onClick={() => void preview("profile", profile.id)}>清空当前场景记忆</button>}<button className="danger-link" disabled={busy} onClick={() => void preview("all")}>清空全部个人记忆</button></div>
      <details><summary>需要连作品和模型设置一起清空？</summary><p>停止映章服务后，在项目根目录运行 <code>python scripts/reset-personal-workspace.py</code> 预览范围。确认后按提示执行恢复出厂；此操作会删除应用管理的作品、材料、生成技能和凭据。下载的备份与外部模型文件保留。</p></details>
      {reset && <div className="personal-reset-preview" role="region" aria-label="清理范围预览"><h4>请核对清理范围</h4><p>{reset.profileCount} 个相关档案 · {reset.memoryCount} 条经验 · {reset.feedbackCount} 条学习记录 · {reset.caseCount ?? 0} 个案例 · {reset.referenceCount ?? 0} 份原始参考稿</p><p>{reset.message}</p><p>保留：{reset.retained.join("；")}</p><button className="primary" disabled={busy} onClick={() => void run(async () => { const receipt = await post<{ cacheCleanup?: { failed: number }; unpublishedFiles: string }>("/me/memory-reset", { preview_id: reset.id, digest: reset.digest }); setReset(null); qc.removeQueries({ queryKey: ["personal-feedback"] }); qc.removeQueries({ queryKey: ["personal-experience"] }); qc.removeQueries({ queryKey: ["personal-comparisons"] }); await qc.invalidateQueries({ queryKey: ["workspace"] }); return `目标记忆已失效；已有作品保留。${receipt.cacheCleanup?.failed ? "部分缓存未能清理，请停止服务后按部署说明核对。" : "缓存中的偏好标记已移除。"}${receipt.unpublishedFiles}`; }, "目标记忆已清除，旧学习记录和任务快照已失效。已有作品保留。")}>确认清除这些记忆</button><button disabled={busy} onClick={() => setReset(null)}>取消</button></div>}
    </div>
  </section>;
}
