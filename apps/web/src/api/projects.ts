import { base, json, jsonHeaders } from "./http";
import type { Project, SlideSpec, ProfessionalPlatform, ProfessionalBrief, QualityReport, ProjectWorkspace, PublicSession, ProjectJob, ProjectStorageReport } from "./types";

export const getPublicSession = () => json<PublicSession>("/auth/session");
export const loginPublic = (name: string, password: string) =>
  json<PublicSession>("/auth/login", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ name, password }),
  });
export const logoutPublic = () => json<{ ok: boolean }>("/auth/logout", { method: "POST" });
export const getProjects = () => json<Project[]>("/projects");
export const getProjectWorkspace = (id: string) =>
  json<ProjectWorkspace>(`/projects/${id}/workspace`);
export const getProjectStorage = (id: string) =>
  json<ProjectStorageReport>(`/projects/${id}/storage`);
export const getProfessionalPlatform = (id: string) =>
  json<ProfessionalPlatform>(`/projects/${id}/professional-platform`);
export const runVisualRegression = (id: string, acceptCurrent = false, threshold = 0.035) =>
  json<{ status?: string; passed?: boolean; slides?: number; differences?: unknown[] }>(`/projects/${id}/visual-regression`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ accept_current: acceptCurrent, threshold }),
  });
export const updateSlideLayout = (
  projectId: string,
  slideId: string,
  regions: NonNullable<NonNullable<SlideSpec["layoutPlan"]>["regions"]>,
  focalPoint: "left" | "right" | "full",
  revision?: number,
) => json<{ slide: SlideSpec; version: number }>(`/projects/${projectId}/slides/${slideId}/layout`, {
  method: "PUT",
  headers: jsonHeaders,
  body: JSON.stringify({ regions, focal_point: focalPoint, revision }),
});
export const discoverProjectResearch = (id: string, query: string, kind: "works" | "images") =>
  json<{ query: string; kind: string; results: unknown[] }>(`/projects/${id}/research/discover?q=${encodeURIComponent(query)}&kind=${kind}&limit=8`);
export const renameProject = (id: string, name: string) =>
  json<Project>(`/projects/${id}`, {
    method: "PATCH",
    headers: jsonHeaders,
    body: JSON.stringify({ name }),
  });
export async function removeProject(id: string) {
  const response = await fetch(`${base}/projects/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error(await response.text());
}
export const createProject = (name: string) =>
  json<Project>("/projects", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ name }),
  });
export async function uploadSource(projectId: string, file: File) {
  const body = new FormData();
  body.append("file", file);
  return json(`/projects/${projectId}/sources`, { method: "POST", body });
}
export const planProject = (
  projectId: string,
  title: string,
  instructions: string,
  preset: string,
  count: number,
  skill_ids: string[] = [],
  approval_mode = false,
  image_mode: "off" | "auto" = "off",
  brief: ProfessionalBrief = {},
) =>
  json(`/projects/${projectId}/outline`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      title, instructions, preset, slide_count: count, skill_ids, approval_mode, image_mode,
      profile_id: brief.profileId || null,
      profile_revision: brief.profileRevision || null,
      personalization_mode: brief.profileId ? "profile" : "off",
      audience: brief.audience || "",
      objective: brief.objective || "",
      brand_name: brief.brandName || "",
      tone: brief.tone || "auto",
      duration_minutes: brief.durationMinutes || null,
    }),
  });
export const startOutlineJob = (
  projectId: string,
  title: string,
  instructions: string,
  preset: string,
  count: number,
  skill_ids: string[] = [],
  approval_mode = false,
  image_mode: "off" | "auto" = "off",
  brief: ProfessionalBrief = {},
) =>
  json<ProjectJob>(`/projects/${projectId}/jobs/outline`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      title, instructions, preset, slide_count: count, skill_ids, approval_mode, image_mode,
      profile_id: brief.profileId || null,
      profile_revision: brief.profileRevision || null,
      personalization_mode: brief.profileId ? "profile" : "off",
      audience: brief.audience || "",
      objective: brief.objective || "",
      brand_name: brief.brandName || "",
      tone: brief.tone || "auto",
      duration_minutes: brief.durationMinutes || null,
    }),
  });
export const startFullGenerationJob = (
  projectId: string,
  title: string,
  instructions: string,
  preset: string,
  count: number,
  skill_ids: string[] = [],
  image_mode: "off" | "auto" = "off",
  brief: ProfessionalBrief = {},
) =>
  json<ProjectJob>(`/projects/${projectId}/jobs/full`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      title, instructions, preset, slide_count: count, skill_ids, approval_mode: false, image_mode,
      profile_id: brief.profileId || null,
      profile_revision: brief.profileRevision || null,
      personalization_mode: brief.profileId ? "profile" : "off",
      audience: brief.audience || "",
      objective: brief.objective || "",
      brand_name: brief.brandName || "",
      tone: brief.tone || "auto",
      duration_minutes: brief.durationMinutes || null,
    }),
  });
export const approveOutline = (projectId: string) =>
  json(`/projects/${projectId}/gates/outline/approve`, { method: "POST" });
export const generateSample = (projectId: string) =>
  json<{ slides: number[]; html: string }>(`/projects/${projectId}/sample`, { method: "POST" });
export const startSampleJob = (projectId: string) =>
  json<ProjectJob>(`/projects/${projectId}/jobs/sample`, { method: "POST" });
export const approveSample = (projectId: string) =>
  json(`/projects/${projectId}/gates/sample/approve`, { method: "POST" });
export const sampleUrl = (projectId: string) => `${base}/projects/${projectId}/sample/html`;
export const generateProject = (projectId: string) =>
  json<{ slides: number; candidateCount: number; html: string }>(
    `/projects/${projectId}/generate`,
    { method: "POST" },
  );
export const startGenerateJob = (projectId: string) =>
  json<ProjectJob>(`/projects/${projectId}/jobs/generate`, { method: "POST" });
export const getProjectJob = (jobId: string) => json<ProjectJob>(`/jobs/${jobId}`);
export const cancelProjectJob = (jobId: string) =>
  json<ProjectJob>(`/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
export const jobPagePreviewUrl = (jobId: string, slideId: string) =>
  `${base}/jobs/${encodeURIComponent(jobId)}/pages/${encodeURIComponent(slideId)}/preview`;

function finishProjectJob(job: ProjectJob) {
  if (job.status === "failed") {
    throw new Error(job.error || job.checkpoint.label || "后台任务执行失败");
  }
  if (job.status === "cancelled") {
    throw new Error(job.checkpoint.label || "任务已取消");
  }
  return job;
}

async function pollProjectJob(
  initial: ProjectJob,
  onUpdate: ((job: ProjectJob) => void) | undefined,
  deadline: number,
) {
  let job = initial;
  while (job.status === "queued" || job.status === "running") {
    if (Date.now() > deadline) {
      throw new Error("后台任务执行时间过长，请稍后从项目库重新打开查看结果。");
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1200));
    job = await getProjectJob(job.id);
    onUpdate?.(job);
  }
  return finishProjectJob(job);
}

export async function waitForProjectJob(
  initial: ProjectJob,
  onUpdate?: (job: ProjectJob) => void,
  timeoutMs = 30 * 60 * 1000,
) {
  const deadline = Date.now() + timeoutMs;
  onUpdate?.(initial);
  if (!(["queued", "running"] as const).includes(initial.status as "queued" | "running")) {
    return finishProjectJob(initial);
  }
  if (typeof EventSource === "undefined") {
    return pollProjectJob(initial, onUpdate, deadline);
  }

  return new Promise<ProjectJob>((resolve, reject) => {
    const source = new EventSource(
      `${base}/jobs/${encodeURIComponent(initial.id)}/events`,
      { withCredentials: true },
    );
    let settled = false;
    const timeout = window.setTimeout(() => {
      if (settled) return;
      settled = true;
      source.close();
      reject(new Error("后台任务执行时间过长，请稍后从项目库重新打开查看结果。"));
    }, timeoutMs);
    const close = () => {
      source.close();
      window.clearTimeout(timeout);
    };

    source.onmessage = (event) => {
      try {
        const job = JSON.parse(event.data) as ProjectJob;
        onUpdate?.(job);
        if (job.status === "queued" || job.status === "running") return;
        settled = true;
        close();
        try { resolve(finishProjectJob(job)); } catch (error) { reject(error); }
      } catch (error) {
        settled = true;
        close();
        reject(error);
      }
    };
    source.onerror = () => {
      if (settled) return;
      settled = true;
      close();
      void pollProjectJob(initial, onUpdate, deadline).then(resolve, reject);
    };
  });
}
export const validateProject = (projectId: string) =>
  json<QualityReport>(
    `/projects/${projectId}/validate`,
    { method: "POST" },
  );
export const updateProjectSkills = (projectId: string, skill_ids: string[]) =>
  json<{ skillIds: string[] }>(`/projects/${projectId}/skills`, {
    method: "PUT",
    headers: jsonHeaders,
    body: JSON.stringify({ skill_ids }),
  });
export const repairSlide = (
  projectId: string,
  slideId: string,
  instruction: string,
  patch: Record<string, unknown>,
  revision?: number,
) =>
  json<{ slide: SlideSpec; version: number }>(
    `/projects/${projectId}/slides/${slideId}/repair`,
    {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ instruction, patch, revision }),
    },
  );
export const chatEditSlide = (
  projectId: string,
  slideId: string,
  instruction: string,
  target: Record<string, unknown>,
  operation: "replace" | "append" | "delete" | "move",
  value: string | string[] | null,
  revision?: number,
) => json<{ slide: SlideSpec; version: number; changeSet: Record<string, unknown> }>(
  `/projects/${projectId}/slides/${slideId}/chat`,
  { method: "POST", headers: jsonHeaders, body: JSON.stringify({ instruction, target, operation, value, rerender: true, revision }) },
);
export const getSlideChat = (projectId: string, slideId: string) =>
  json<{ id: string; actor: string; instruction: string; version: number; createdAt: string }[]>(`/projects/${projectId}/slides/${slideId}/chat`);
export const startSlideRegenerateJob = (projectId: string, slideId: string) =>
  json<ProjectJob>(`/projects/${projectId}/slides/${slideId}/jobs/regenerate`, { method: "POST" });
export const singleSlideExportUrl = (projectId: string, slideId: string) =>
  `${base}/projects/${encodeURIComponent(projectId)}/slides/${encodeURIComponent(slideId)}/export/pptx`;
export async function registerLicensedAsset(projectId: string, data: { name: string; kind: string; provider: string; sourceUrl: string; license: string; attribution: string; file?: File | null }) {
  const form = new FormData();
  form.append("name", data.name); form.append("kind", data.kind); form.append("provider", data.provider);
  form.append("source_url", data.sourceUrl); form.append("license", data.license); form.append("attribution", data.attribution);
  if (data.file) form.append("file", data.file);
  return json<{ id: string; approved: boolean; bindable: boolean }>(`/projects/${projectId}/assets`, { method: "POST", body: form });
}
export const bindLicensedAsset = (projectId: string, slideId: string, assetId: string) =>
  json(`/projects/${projectId}/slides/${slideId}/assets/${assetId}/bind`, { method: "POST" });
export async function uploadBrandAsset(projectId: string, name: string, kind: string, file: File) {
  const form = new FormData(); form.append("name", name); form.append("kind", kind); form.append("file", file);
  return json<{ id: string; name: string; kind: string }>(`/projects/${projectId}/brand-assets`, { method: "POST", body: form });
}
export const addProjectMember = (projectId: string, name: string, role: string) =>
  json(`/projects/${projectId}/members`, { method: "POST", headers: jsonHeaders, body: JSON.stringify({ name, role }) });
export const recordProjectApproval = (projectId: string, stage: string, status: string, comment = "") =>
  json(`/projects/${projectId}/approvals`, { method: "POST", headers: jsonHeaders, body: JSON.stringify({ stage, status, comment }) });
export const publishProject = (projectId: string, expiresDays = 14) =>
  json<{ id: string; token: string; url: string }>(`/projects/${projectId}/publish`, { method: "POST", headers: jsonHeaders, body: JSON.stringify({ expires_days: expiresDays }) });
export const setPowerPointEffects = (projectId: string, slideId: string, transition: string, animation: string) =>
  json(`/projects/${projectId}/slides/${slideId}/powerpoint-effects`, { method: "POST", headers: jsonHeaders, body: JSON.stringify({ transition, transition_speed: "med", animation }) });
export const generateNarration = (projectId: string, slideId?: string) =>
  json<{ totalSeconds: number; slides: { slideId: string; narration: string; estimatedSeconds: number }[] }>(`/projects/${projectId}/narration`, { method: "POST", headers: jsonHeaders, body: JSON.stringify({ slide_id: slideId || null, locale: "zh-CN", words_per_minute: 220 }) });
export async function importPowerPoint(projectId: string, file: File) {
  const form = new FormData(); form.append("file", file);
  return json(`/projects/${projectId}/powerpoint/import`, { method: "POST", body: form });
}
export const editImportedPowerPointObject = (projectId: string, slideIndex: number, objectId: string, value: string) =>
  json(`/projects/${projectId}/powerpoint/slides/${slideIndex}/objects/${objectId}`, { method: "POST", headers: jsonHeaders, body: JSON.stringify({ value }) });
export const importedPowerPointExportUrl = (projectId: string) => `${base}/projects/${encodeURIComponent(projectId)}/powerpoint/export`;
export const runProfessionalEvaluation = (projectId: string) =>
  json<{ id: string; blindToken: string; metrics: ProjectWorkspace["evaluationRuns"][number]["metrics"] }>(`/projects/${projectId}/evaluations`, { method: "POST" });
export const blindEvaluationUrl = (token: string) => `${base}/evaluations/blind/${encodeURIComponent(token)}`;
export const candidatePreviewUrl = (projectId: string, slideId: string, candidateId: string) =>
  `${base}/projects/${encodeURIComponent(projectId)}/slides/${encodeURIComponent(slideId)}/candidates/${encodeURIComponent(candidateId)}/preview`;
export const selectSlideCandidate = (projectId: string, slideId: string, candidateId: string, revision?: number) => {
  const body = new FormData();
  body.append("candidate_id", candidateId);
  if (revision !== undefined) body.append("revision", String(revision));
  return json<{ selected: string; variant: string }>(
    `/projects/${projectId}/slides/${slideId}/select`,
    { method: "POST", body },
  );
};
export const getSlideVersions = (projectId: string, slideId: string) =>
  json<{ version: number; reason: string; spec: SlideSpec }[]>(
    `/projects/${projectId}/slides/${slideId}/versions`,
  );
export const rollbackSlide = (projectId: string, slideId: string, version: number, revision?: number) =>
  json<{ slide: SlideSpec; version: number }>(
    `/projects/${projectId}/slides/${slideId}/rollback/${version}${revision === undefined ? "" : `?revision=${revision}`}`,
    { method: "POST" },
  );
export const exportUrl = (projectId: string, format: "html" | "pptx" | "pdf", stage: "draft" | "final" = "final") =>
  `${base}/projects/${projectId}/export/${format}?stage=${stage}`;
export const exportDownloadUrl = (projectId: string, format: "html" | "pptx" | "pdf", stage: "draft" | "final" = "final") =>
  `${base}/projects/${encodeURIComponent(projectId)}/downloads/${format}?stage=${stage}`;
export async function exportWithTemplate(projectId: string, file: File) {
  const body = new FormData();
  body.append("template", file);
  const response = await fetch(`${base}/projects/${encodeURIComponent(projectId)}/export/template-pptx`, {
    method: "POST",
    body,
  });
  if (!response.ok) throw new Error(await response.text());
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = "template-filled.pptx";
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
