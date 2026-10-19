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
export type ProposalIssue = {
  position: number | null;
  code: string;
  severity: string;
  field?: string;
  message: string;
  detail?: Record<string, unknown>;
};
export type SlideSpec = {
  proposalIssues?: ProposalIssue[];
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
  proposalValidation?: {
    summary: { pages?: number; accepted?: number; repaired?: number; fallback?: number; byCode?: Record<string, number> };
    issues: ProposalIssue[];
    fallbackPositions: number[];
  } | null;
  materialAnalysis?: {
    documents: { name: string; kind?: string; uncertainRoles: { section?: string; title: string; role: string; confidence: number }[] }[];
  };
  projectRole?: "owner" | "editor" | "reviewer" | "viewer";
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
  retryFullGeneration?: boolean;
  modelPlanning?: { model?: string; filledByBuiltinPlanner?: number; batchErrors?: string[] };
  modelUsage?: { inputTokens: number | null; outputTokens: number | null; requests: number; reportedRequests: number; unreportedRequests: number; source: "provider-reported"; costAvailable: false; models: { model: string; inputTokens: number | null; outputTokens: number | null; requests: number; reportedRequests: number; unreportedRequests: number }[] };
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
    metrics: { professionalScore?: number; fixedCasesPassed?: number; fixedCasesTotal?: number; fixedCasesNotApplicable?: number; fixedCasesNotVerified?: number; pageEditCount?: number; editsPerSlide?: number; deliverySuccess?: boolean; userSelectionRate?: number; blindReady?: boolean; blindReadinessReason?: string; blindReviewCount?: number };
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

export type ProjectStorageReport = {
  totalBytes: number;
  totalFiles: number;
  freeBytes: number;
  backupIncludesAllArtifacts: boolean;
  groups: Record<string, { bytes: number; files: number }>;
};

export type EvaluationKind = "ppteval" | "quiz" | "render";

export type PptevalDimensionScore = { score: number; rationale: string; source: string; suggestions?: string[] };

export type PptevalSlide = {
  position: number;
  slideId?: string;
  title: string;
  content: PptevalDimensionScore;
  design: PptevalDimensionScore;
  coherence: PptevalDimensionScore;
  issues: { dimension: "content" | "design" | "coherence"; code: string; message: string; suggestion: string }[];
};

export type QuizTrace = {
  id: string;
  type: "detail" | "concept";
  question: string;
  expected: string;
  answer: string;
  supportedBySlide: number | null;
  citedSlide?: number | null;
  correct: boolean;
};

export type RenderReviewPage = {
  page: number;
  image: string;
  slideId?: string;
  title?: string;
  score: number;
  issues: { code: string; severity: "error" | "warning"; message: string; suggestion?: string }[];
};

export type ResearchEvaluationRun = {
  id: string;
  suite: string;
  status: "running" | "completed" | "failed" | "interrupted";
  kinds: EvaluationKind[];
  createdAt: string | null;
  fingerprint?: string;
  stale: boolean;
  exportMatchesCurrent?: boolean | null;
  error?: string | null;
  models?: { text?: string | null; vision?: string | null };
  summary: {
    content?: number; design?: number; coherence?: number; overall?: number; pptevalMode?: string;
    retention?: number | null; detailRetention?: number | null; conceptRetention?: number | null; quizStatus?: string;
    renderStatus?: string; renderErrors?: number; renderWarnings?: number; renderScore?: number | null;
  };
  ppteval?: {
    mode: string;
    overall: number;
    deck: Record<"content" | "design" | "coherence", PptevalDimensionScore>;
    slides: PptevalSlide[];
    errors: string[];
  };
  quiz?: {
    status: string;
    message?: string;
    generator?: string;
    answerer?: string;
    retention: number | null;
    detailRetention?: number | null;
    conceptRetention?: number | null;
    questions: QuizTrace[];
    missingFacts: { claim: string; missingValues: string[]; sourceRef?: { document: string; section: string } }[];
    errors: string[];
  };
  render?: {
    status: string;
    mode?: string;
    message?: string;
    pageCount?: number;
    slideCount?: number;
    pages: RenderReviewPage[];
    issues: ({ page: number } & RenderReviewPage["issues"][number])[];
    errors?: string[];
  };
};
