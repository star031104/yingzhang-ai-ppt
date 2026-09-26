import { base, json, jsonHeaders } from "./http";
import type { Provider, ModelConfig, Skill, DiscoverResult } from "./types";

export const getProviders = () => json<Provider[]>("/providers");
export const getModels = () => json<ModelConfig[]>("/models");
export const discoverModels = (
  base_url: string,
  api_key: string,
  model_type?: "text" | "image",
) =>
  json<DiscoverResult>("/providers/discover", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ base_url, api_key: api_key || null, model_type }),
  });
export const createProvider = (body: {
  name: string;
  base_url: string;
  api_key?: string;
}) =>
  json<Provider>("/providers", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(body),
  });
export const registerModel = (
  providerId: string,
  model_id: string,
  capabilities: string[],
) =>
  json<ModelConfig>(`/providers/${providerId}/models`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ model_id, capabilities, quality_profile: {} }),
  });
export const mapModelRole = (role: string, model_config_id: string) =>
  json("/model-routing", {
    method: "PUT",
    headers: jsonHeaders,
    body: JSON.stringify({ role, model_config_id }),
  });
export const testProvider = (id: string) =>
  json<DiscoverResult>(`/providers/${id}/test`, { method: "POST" });
export async function removeProvider(id: string) {
  const response = await fetch(`${base}/providers/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error(await response.text());
}
export async function removeModel(id: string) {
  const response = await fetch(`${base}/models/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error(await response.text());
}
export async function testImageModel(id: string) {
  const response = await fetch(`${base}/models/${encodeURIComponent(id)}/test-image`, {
    method: "POST",
  });
  if (!response.ok) {
    const text = await response.text();
    let detail = text;
    try { const body = JSON.parse(text); if (typeof body.detail === "string") detail = body.detail; } catch { /* Plain-text gateway error. */ }
    throw new Error(detail);
  }
  if (response.status === 202) {
    const pending = await response.json();
    return { status: "pending" as const, message: String(pending.message || "服务仍在生成，请继续查询") };
  }
  return { status: "ready" as const, url: URL.createObjectURL(await response.blob()) };
}

export const getSkills = () => json<Skill[]>("/skills");
export const installSkillUrl = (url: string, allow_scripts: boolean) =>
  json<Skill>("/skills/install-url", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ url, allow_scripts }),
  });
export async function compileReferenceSkill(file: File, name: string) {
  const form = new FormData();
  form.append("file", file);
  form.append("name", name || file.name.replace(/\.pptx$/i, ""));
  const response = await fetch(`${base}/reference/compile-skill`, { method: "POST", body: form });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<{ id: string; version: string; analysis: Record<string, unknown> }>;
}
export async function removeSkill(id: string) {
  const response = await fetch(`${base}/skills/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error(await response.text());
}
