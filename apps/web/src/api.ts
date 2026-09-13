export type Provider = {
  id: string;
  name: string;
  base_url: string;
  enabled: boolean;
  has_api_key: boolean;
};
export type ModelConfig = {
  id: string;
  provider_id: string;
  model_id: string;
  capabilities: string[];
  quality_profile: Record<string, number>;
};
export type Project = {
  id: string;
  name: string;
  status: string;
  artifact_path: string;
};
export type Skill = {
  id: string;
  version: string;
  sha256: string;
  scriptsEnabled: boolean;
  name: string;
  description: string;
  kind: string;
};
export type SlideSpec = {
  imageGeneration?: { status: string; message?: string };
  id: string;
  position: number;
  revision: number;
  role: string;
  message?: string;
  content: { title: string; bullets: string[] };
  visualIntent?: { primaryVisual?: string; selectedVariant?: string; [key: string]: unknown };
  generationState?: {
    status?: "pending" | "running" | "ready" | "failed" | "cancelled";
    error?: string;
    candidateCount?: number;
  };
  layoutPlan?: {
    communicationJob?: string;
    compositionMode?: string;
    recommendedVariant?: string;
    silhouette?: string;
    focalPoint?: string;
    candidateOrder?: string[];
    constraints?: Record<string, unknown>;
    manualOverride?: boolean;
    regions?: { id: string; x: number; y: number; w: number; h: number; priority?: number; locked?: boolean }[];
  };
};
export type ProfessionalPlatform = {
  version: string;
  p0: {
    researchManifest: { evidenceGaps?: string[]; workQueries?: unknown[]; imageQueries?: unknown[] };
    layoutPlanning: { uniqueSilhouettes?: number; familySequence?: string[]; warnings?: unknown[] };
    brandKit: { score?: number; name?: string };
    canvasObjectModel: string;
    visualRegression: string;
  };
  p1: {
    stageTrace: { stage: string; label: string; progress: number; at: string }[];
    reviewDiff: string;
    governance: { version?: string; approvalStages?: string[]; publicationSnapshots?: boolean };
    benchmarkFamilies: string[];
  };
  p2: {
    deliveryProfiles: Record<string, { profile: string; score: number; issues: unknown[] }>;
    templateConstraintLearning: string;
    media: boolean;
  };
};
export type SlideCandidate = {
  id: string;
  slideId: string;
  variant: string;
  score: {
    overall?: number;
    geometry?: number;
    readability?: number;
    hierarchy?: number;
    contentFit?: number;
    visualEvidence?: number;
    deckRhythm?: number;
    variantFamily?: string;
  };
  selected: boolean;
  previewAvailable: boolean;
};
export type ProfessionalBrief = {
  profileId?: string;
  profileRevision?: number;
  audience?: string;
  objective?: string;
  brandName?: string;
  tone?: "auto" | "formal" | "executive" | "editorial" | "energetic";
  durationMinutes?: number | null;
};
export type QualityReport = {
  passed: boolean;
  contentCoverage: number;
  blockingErrors: number;
  warningCount?: number;
  visualQA?: {
    checked: number;
    expected?: number;
    blocking: number;
    complete?: boolean;
    missingPositions?: number[];
    stalePositions?: number[];
    slides?: { position: number; issues: { code: string; message?: string }[]; hardFailures?: string[] }[];
  };
  professionalAudit?: {
    overall: number;
    grade: string;
    ready: boolean;
    dimensions: Record<string, number>;
    recommendations: { priority: string; title: string; detail: string }[];
  };
  semanticCompleteness?: {
    score: number;
    requiredSections: number;
    coveredSections: number;
    requiredClaims: number;
    coveredClaims: number;
    missing: { title: string; kind: string; claim?: string }[];
  };
  visualReflection?: {
    checked?: number;
    applied?: number;
    visionStatus?: string;
  };
  visualMaturity?: {
    score: number;
    silhouetteDiversity: number;
    narrativeRhythm: number;
    semanticAdaptation: number;
    evidenceVisualCoverage: number;
    candidateDepth?: number | null;
    uniqueFamilies?: number;
    dominantFamily?: string;
    adjacentRepeatRate?: number;
  };
  accessibility?: {
    score: number;
    errors: number;
    warnings: number;
    passed: boolean;
    issues: { slide: number; code: string; severity: string; message: string }[];
  };
};
export type ProjectWorkspace = {
  personalizationAvailable?: boolean;
  personalization?: { active: boolean; message?: string; rules: { key: string; label: string; description: string }[] };
  project: { id: string; name: string; status: string };
  narrative: { thesis?: string } | null;
  designSystem: Record<string, unknown> | null;
  planOptions: {
    title?: string;
    instructions?: string;
    preset?: string;
    slideCount?: number;
    skillIds?: string[];
    approvalMode?: boolean;
    imageMode?: "off" | "auto";
    professionalBrief?: ProfessionalBrief;
  };
  modelPlanning?: { model?: string; filledByBuiltinPlanner?: number; batchErrors?: string[] };
  orchestration: {
    version?: string;
    principle?: string;
    policy?: { label?: string; batch_size?: number; context_limit?: number };
    ruleOwned?: string[];
    modelOwned?: string[];
    batches?: { index: number; start: number; end: number }[];
  };
  slides: SlideSpec[];
  candidates: SlideCandidate[];
  sources: SourceReading[];
  skillIds: string[];
  gates: { enabled: boolean; outline: "pending" | "approved"; sample: "pending" | "approved" } | null;
  previewAvailable: boolean;
  sampleAvailable: boolean;
  exports: string[];
  licensedAssets: { id: string; name: string; kind: string; slideId?: string; provider: string; sourceUrl: string; license: string; attribution: string; approved: boolean }[];
  brandAssets: { id: string; name: string; kind: string; metadata: Record<string, unknown> }[];
  members: { id: string; name: string; role: string }[];
  approvals: { id: string; stage: string; status: string; actor: string; comment: string }[];
  publications: { id: string; token: string; status: string; expiresAt?: string }[];
  importedPowerPoint: {
    id: string; sourceName: string; version: number;
    analysis: {
      slideCount: number; themeCount: number; masterCount: number; layoutCount: number;
      transitionSlides: number; animationSlides: number;
      slides: { position: number; title: string; hasTransition: boolean; hasAnimation: boolean; objects: { id: string; name: string; type: string; text: string; editable: boolean }[] }[];
    };
  } | null;
  evaluationRuns: {
    id: string; suite: string; status: string; blindToken: string;
    metrics: { professionalScore?: number; fixedCasesPassed?: number; fixedCasesTotal?: number; pageEditCount?: number; editsPerSlide?: number; deliverySuccess?: boolean; userSelectionRate?: number; blindReady?: boolean; blindReviewCount?: number };
  }[];
};
export type SourceReading = {
  id: string; name: string; sha256: string;
  sections?: number; tables?: number; figures?: number; characters?: number;
  readingStatus?: "read" | "needs-attention";
  readingWarnings?: { code: string; page?: number; message: string }[];
  outlineTotal?: number;
  outline?: { id: string; title: string; headingPath: string[]; mainPoint: string; limitations: string[] }[];
};
export type DiscoverResult = {
  ok: boolean;
  latency_ms: number;
  models: string[];
  error?: string;
};
export type PublicSession = {
  authenticated: boolean;
  name: string | null;
  role: "admin" | "tester" | null;
  publicMode: boolean;
  privateMode?: boolean;
  setupRequired?: boolean;
};
export type ProjectJob = {
  type?: "snapshot" | "progress" | "page_progress" | "cancel_requested" | "completed" | "failed" | "cancelled";
  id: string;
  job_id?: string;
  project_id: string | null;
  kind: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress: number;
  checkpoint: {
    stage?: string;
    label?: string;
    result?: Record<string, unknown>;
    cancelRequested?: boolean;
    workflow?: { version?: string; resumable?: boolean; resumeCount?: number };
    pages?: PageGenerationState[];
    pageCounts?: Partial<Record<PageGenerationState["status"], number>>;
    nodes?: Record<string, WorkflowNodeState>;
  };
  error?: string | null;
};

export type PageGenerationState = {
  slideId: string;
  position: number;
  status: "pending" | "running" | "ready" | "failed" | "cancelled";
  error?: string;
  candidateCount?: number;
};

export type WorkflowNodeState = {
  name: string;
  status: "running" | "retrying" | "completed" | "failed";
  idempotencyKey: string;
  inputSchema: string;
  outputSchema: string;
  attempts: number;
  maxAttempts: number;
  retryFor: string[];
  artifactPaths: string[];
  output?: Record<string, unknown>;
  error?: string;
};

const base = import.meta.env.VITE_API_URL ?? "/api/v1";

export async function json<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${base}${url}`, init);
  } catch {
    throw new Error("无法连接本地服务。请双击项目中的“启动项目.cmd”，等待启动成功后刷新页面再试；已保存的内容不会丢失。");
  }
  if (!response.ok) {
    const message = await response.text();
    const contentType = response.headers.get("content-type") || "";
    const htmlError = contentType.includes("text/html") || /^\s*<!doctype html/i.test(message);
    if (response.status === 524 || /error code\s*524|a timeout occurred/i.test(message)) {
      throw new Error("公网连接等待超时。任务可能仍在后台执行，请稍后打开项目查看；若未完成可重新生成。");
    }
    if (htmlError) {
      throw new Error(`公网服务暂时不可用（${response.status}），请稍后重试。`);
    }
    try {
      const parsed = JSON.parse(message) as { detail?: string };
      throw new Error(parsed.detail || `请求失败（${response.status}）`);
    } catch (error) {
      if (error instanceof Error && error.message !== "Unexpected end of JSON input") {
        if (!error.message.startsWith("Unexpected token")) throw error;
      }
      throw new Error(message || `请求失败（${response.status}）`);
    }
  }
  return response.json();
}

const jsonHeaders = { "Content-Type": "application/json" };
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
export const rollbackSlide = (projectId: string, slideId: string, version: number) =>
  json<{ slide: SlideSpec; version: number }>(
    `/projects/${projectId}/slides/${slideId}/rollback/${version}`,
    { method: "POST" },
  );
export const exportUrl = (projectId: string, format: "html" | "pptx" | "pdf", stage: "draft" | "final" = "final") =>
  `${base}/projects/${projectId}/export/${format}?stage=${stage}`;
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
