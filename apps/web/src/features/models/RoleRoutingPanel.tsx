import { useEffect, useState } from "react";
import { getModelRouting, mapModelRole, registerModel } from "../../api";
import type { ModelConfig } from "../../api";
import { Icon } from "../../components/Icon";
import type { IconName } from "../../components/Icon";
import { toast } from "../../store/toasts";

const OPTIONAL_ROLES: { role: "tts" | "embedding"; title: string; description: string; placeholder: string; icon: IconName }[] = [
  { role: "tts", title: "语音合成", description: "用于讲解视频的旁白配音；未配置时视频按字幕无声导出。", placeholder: "例如：tts-1 或 CosyVoice2-0.5B", icon: "message" },
  { role: "embedding", title: "向量检索", description: "启用语义 + 关键词混合检索，长材料定位证据更准；可选。", placeholder: "例如：text-embedding-3-small", icon: "layers" },
];

/** Optional model roles (tts, embedding) that need a model with the matching capability. */
export function RoleRoutingPanel({
  providers,
  models,
  refresh,
}: {
  providers: { id: string; name: string }[];
  models: ModelConfig[];
  refresh: () => void;
}) {
  const [routes, setRoutes] = useState<{ role: string; model_config_id: string }[]>([]);
  const loadRoutes = () => getModelRouting().then(setRoutes).catch(() => setRoutes([]));
  useEffect(() => { void loadRoutes(); }, [models.length]);
  const [drafts, setDrafts] = useState<Record<string, { provider: string; model: string }>>({});
  const [saving, setSaving] = useState("");
  async function assign(role: string, modelConfigId: string) {
    await mapModelRole(role, modelConfigId);
    await loadRoutes();
    refresh();
  }
  return (
    <div className="role-routing">
      <div className="section-heading compact">
        <div><h3>可选能力</h3><p>为讲解视频和语义检索指定专用模型，不配置也不影响基础生成。</p></div>
      </div>
      <div className="role-routing-grid">
        {OPTIONAL_ROLES.map((item) => {
          const capable = models.filter((model) => model.capabilities.includes(item.role));
          const current = routes.find((row) => row.role === item.role)?.model_config_id;
          const currentModel = models.find((model) => model.id === current);
          const draft = drafts[item.role] ?? { provider: providers[0]?.id ?? "", model: "" };
          return (
            <article className="panel role-card" key={item.role}>
              <header>
                <span className="role-card-icon"><Icon name={item.icon} size={16} /></span>
                <div><b>{item.title}</b><small>{item.description}</small></div>
                <span className={`badge ${currentModel ? "success" : ""}`}>{currentModel ? "已启用" : "未配置"}</span>
              </header>
              {capable.length > 0 && (
                <label>当前模型
                  <select
                    value={current ?? ""}
                    aria-label={`${item.title}模型`}
                    onChange={async (event) => {
                      if (!event.target.value) return;
                      try { await assign(item.role, event.target.value); toast(`${item.title}已切换模型`, "success"); }
                      catch (error) { toast(error instanceof Error ? error.message : "保存失败", "error"); }
                    }}
                  >
                    <option value="" disabled>选择已登记的模型</option>
                    {capable.map((model) => <option key={model.id} value={model.id}>{model.model_id}</option>)}
                  </select>
                </label>
              )}
              {providers.length ? (
                <div className="role-card-add">
                  <select aria-label={`${item.title}服务`} value={draft.provider} onChange={(event) => setDrafts({ ...drafts, [item.role]: { ...draft, provider: event.target.value } })}>
                    {providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.name}</option>)}
                  </select>
                  <input aria-label={`${item.title}模型 ID`} value={draft.model} placeholder={item.placeholder} onChange={(event) => setDrafts({ ...drafts, [item.role]: { ...draft, model: event.target.value } })} />
                  <button
                    type="button"
                    disabled={!draft.provider || !draft.model.trim() || saving === item.role}
                    onClick={async () => {
                      setSaving(item.role);
                      try {
                        const model = await registerModel(draft.provider, draft.model.trim(), [item.role]);
                        await assign(item.role, model.id);
                        setDrafts({ ...drafts, [item.role]: { ...draft, model: "" } });
                        toast(`已登记 ${draft.model.trim()}，并用于${item.title}`, "success");
                      } catch (error) {
                        toast(error instanceof Error ? error.message : "登记失败", "error");
                      } finally { setSaving(""); }
                    }}
                  >{saving === item.role ? "保存中…" : "登记并启用"}</button>
                </div>
              ) : <p className="field-help">先在上方连接一个模型服务，再为它登记{item.title}模型。</p>}
            </article>
          );
        })}
      </div>
    </div>
  );
}
