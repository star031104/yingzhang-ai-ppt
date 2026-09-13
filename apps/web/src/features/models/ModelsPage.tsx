import { useMemo, useState } from "react";

import {
  createProvider,
  discoverModels,
  mapModelRole,
  registerModel,
  removeProvider,
  testImageModel,
  testProvider,
} from "../../api";
import type { ModelConfig } from "../../api";
import { Empty } from "../../components/Empty";
import { Notice } from "../../components/Notice";

export function ModelsPage({
  providers,
  models,
  refresh,
}: {
  providers: { id: string; name: string; base_url: string }[];
  models: ModelConfig[];
  refresh: () => void;
}) {
  const [modelKind, setModelKind] = useState<"text" | "image">("text"),
    [found, setFound] = useState<string[]>([]),
    [selected, setSelected] = useState(""),
    [status, setStatus] = useState(""),
    [step, setStep] = useState(1),
    [saving, setSaving] = useState(false),
    [vision, setVision] = useState(false),
    [imagePreview, setImagePreview] = useState(""),
    [form, setForm] = useState({ name: "自定义模型服务", url: "", key: "" });
  const isImage = modelKind === "image";
  const providerModels = useMemo(
    () =>
      new Map(
        providers.map((p) => [
          p.id,
          models.filter((m) => m.provider_id === p.id),
        ]),
      ),
    [providers, models],
  );
  async function discover() {
    setSaving(true);
    setStatus("正在连接并读取模型列表…");
    try {
      const result = await discoverModels(form.url, form.key, modelKind);
      if (!result.ok) throw new Error(result.error || "连接失败");
      setFound(result.models);
      setSelected(result.models[0] ?? "");
      setStep(2);
      setStatus(
        isImage && !result.models.length
          ? "连接成功，但服务列表没有返回可识别的文生图模型。可以手动填写服务商提供的文生图模型 ID；图片编辑模型需要原图，不能替代文生图。"
          : `连接成功，找到 ${result.models.length} 个候选模型。列表可见不代表已通过实际调用测试。`,
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "连接失败");
    } finally {
      setSaving(false);
    }
  }
  async function save() {
    if (!selected) return;
    setSaving(true);
    try {
      const provider = await createProvider({
        name: form.name,
        base_url: form.url,
        api_key: form.key,
      });
      const capabilities = isImage
        ? ["image_generation"]
        : ["chat", "structured_output", "long_context", ...(vision ? ["vision"] : [])];
      const model = await registerModel(provider.id, selected, capabilities);
      if (isImage) {
        await mapModelRole("image_generation", model.id);
      } else {
        for (const role of ["planner", "source_analyst", "slide_coder", "repair", "research"])
          await mapModelRole(role, model.id);
        if (vision) await mapModelRole("vision_critic", model.id);
      }
      setStep(3);
      setStatus(
        isImage
          ? `已保存 ${selected}，并设为默认生图模型`
          : `已保存 ${selected}，并设为默认工作模型`,
      );
      refresh();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }
  return (
    <section className="content">
      <div className="section-heading">
        <div>
          <span className="kicker">模型中枢</span>
          <h2>连接文本模型与生图模型</h2>
          <p>分别配置内容推理和图片生成，避免让同一个模型承担不适合的任务。</p>
        </div>
        <div className="steps">
          <span className={step >= 1 ? "on" : ""}>1 连接</span>
          <span className={step >= 2 ? "on" : ""}>2 选模型</span>
          <span className={step >= 3 ? "on" : ""}>3 完成</span>
        </div>
      </div>
      <div className="model-kind-tabs" role="tablist" aria-label="模型类型">
        <button
          className={!isImage ? "active" : ""}
          onClick={() => {
            setModelKind("text"); setFound([]); setSelected(""); setStep(1); setStatus("");
            setForm((current) => ({ ...current, name: "文本模型服务" }));
          }}
        >文字与推理模型</button>
        <button
          className={isImage ? "active" : ""}
          onClick={() => {
            setModelKind("image"); setFound([]); setSelected(""); setStep(1); setStatus(""); setVision(false);
            setForm((current) => ({ ...current, name: "生图模型服务" }));
          }}
        >生图模型</button>
      </div>
      <div className="model-layout">
        <div className="panel model-form">
          <div className="panel-title">
            <span className="number">01</span>
            <div>
              <h3>{isImage ? "图片服务地址" : "文本服务地址"}</h3>
              <p>密钥只保存在系统密钥库，页面不会回显</p>
            </div>
          </div>
          <label>
            配置名称
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </label>
          <label>
            API 地址
            <input
              type="url"
              value={form.url}
              onChange={(e) => {
                setForm({ ...form, url: e.target.value });
                setStep(1); setFound([]); setSelected("");
              }}
              placeholder="例如：https://api.example.com/v1"
            />
          </label>
          <label>
            API 密钥
            <input
              type="password"
              value={form.key}
              onChange={(e) => setForm({ ...form, key: e.target.value })}
              placeholder="请输入 API Key（本地服务可留空）"
            />
          </label>
          <button
            className="primary"
            type="button"
            onClick={discover}
            disabled={!form.url || saving}
          >
            {saving ? "正在测试…" : "测试连接并获取模型 →"}
          </button>
          {status && (
            <Notice
              text={status}
              tone={
                status.includes("失败") ? "error" : step === 3 ? "success" : "info"
              }
            />
          )}
        </div>
        <div className="panel model-select">
          <div className="panel-title">
            <span className="number purple">02</span>
            <div>
              <h3>{isImage ? "选择生图模型" : "选择工作模型"}</h3>
              <p>{isImage ? "筛选文生图候选，也支持手动填写模型 ID" : "测试成功后列出可用文字模型"}</p>
            </div>
          </div>
          {found.length || (isImage && step >= 2) ? (
            <>
              {found.length > 0 && <label>
                可用模型
                <select
                  value={selected}
                  onChange={(e) => setSelected(e.target.value)}
                >
                  {found.map((model) => (
                    <option key={model}>{model}</option>
                  ))}
                </select>
              </label>}
              {isImage && <label>文生图模型 ID（可手动填写）
                <input value={selected} onChange={event => setSelected(event.target.value.trim())} placeholder="例如：Qwen/Qwen-Image" />
                <small>魔搭的模型列表可能不包含文生图模型，请以模型详情页的 API-Inference 示例为准。保存后点击“测试生图”验证权限及可用性。</small>
              </label>}
              {!isImage && <label className="check">
                <input
                  type="checkbox"
                  checked={vision}
                  onChange={(e) => setVision(e.target.checked)}
                />
                <span>
                  <b>该模型支持图片理解</b>
                  <small>启用后可承担视觉检查任务</small>
                </span>
              </label>}
              <div className="role-list">
                {(isImage
                  ? ["封面主视觉", "概念插画", "风格统一"]
                  : ["大纲规划", "材料分析", "页面生成", "内容修复"]
                ).map((label) => <span key={label}>{label}</span>)}
              </div>
              <button className="primary" onClick={save} disabled={saving || !selected}>
                {isImage ? "保存并设为默认生图模型" : "保存并设为默认工作模型"}
              </button>
            </>
          ) : (
            <Empty
              title={isImage ? "等待生图服务测试" : "等待连接测试"}
              text={isImage
                ? "填写服务地址和密钥，连接后筛选文生图候选，或手动填写模型 ID。"
                : "填写左侧 API 地址和密钥，测试成功后即可选择文字模型。"}
            />
          )}
        </div>
      </div>
      <div className="saved-list">
        <div className="section-heading compact">
          <div>
            <h3>已连接的服务</h3>
            <p>可随时重新测试连接状态</p>
          </div>
        </div>
        {providers.length ? (
          providers.map((provider) => (
            <article key={provider.id}>
              <div className="provider-icon">◇</div>
              <div>
                <b>{provider.name}</b>
                <small>{provider.base_url}</small>
                {(providerModels.get(provider.id) ?? []).map(model => <small key={model.id}>{model.model_id}</small>)}
                <div className="service-tags">
                  {(providerModels.get(provider.id) ?? []).some((model) => model.capabilities.includes("chat")) && <span>文本模型</span>}
                  {(providerModels.get(provider.id) ?? []).some((model) => model.capabilities.includes("image_generation")) && <span>生图模型</span>}
                </div>
              </div>
              <span>{providerModels.get(provider.id)?.length ?? 0} 个模型</span>
              <div className="service-actions">
                {(providerModels.get(provider.id) ?? []).some((model) => model.capabilities.includes("image_generation")) && <button
                  disabled={saving}
                  onClick={async () => {
                    setStatus("正在调用生图模型生成测试图片…");
                    const imageModel = (providerModels.get(provider.id) ?? []).find((model) => model.capabilities.includes("image_generation"));
                    if (!imageModel) return;
                    setSaving(true);
                    try {
                      const result = await testImageModel(imageModel.id);
                      if (result.status === "pending") {
                        setStatus(`${result.message}。再次点击“测试生图”将继续查询同一任务。`);
                      } else {
                        if (imagePreview) URL.revokeObjectURL(imagePreview);
                        setImagePreview(result.url);
                        setStatus("生图模型测试成功，已返回图片");
                      }
                    } catch (error) {
                      setStatus(error instanceof Error ? error.message : "生图测试失败");
                    } finally {
                      setSaving(false);
                    }
                  }}
                >测试生图</button>}
                <button
                  onClick={async () => {
                    const r = await testProvider(provider.id);
                    setStatus(r.ok ? `连接正常，共 ${r.models.length} 个模型` : r.error || "连接失败");
                  }}
                >重新测试</button>
                <button
                  className="danger-button"
                  onClick={async () => {
                    if (!window.confirm(`确定删除“${provider.name}”吗？关联的模型分工也会一并移除。`)) return;
                    await removeProvider(provider.id);
                    setStatus(`已删除模型服务“${provider.name}”`);
                    refresh();
                  }}
                >删除</button>
              </div>
            </article>
          ))
        ) : (
          <p className="muted">暂无已保存的模型服务</p>
        )}
        {imagePreview && (
          <div className="image-model-preview">
            <div><b>生图测试结果</b><small>仅用于验证连接，不会加入项目</small></div>
            <img src={imagePreview} alt="生图模型测试结果" />
          </div>
        )}
      </div>
    </section>
  );
}
