import { base, json, jsonHeaders } from "./http";
import type { ProjectJob } from "./types";

export type IntakeOption = { value: string; label: string };
export type IntakeQuestion = {
  id: string;
  label: string;
  type: "text" | "number" | "choice" | "multi";
  options?: IntakeOption[];
  suggested: string | number | string[];
  why?: string;
};
export type IntakePhase = { id: string; title: string; hint: string; questions: IntakeQuestion[] };
export type GuidedIntake = { version: string; title: string; preset: string; phases: IntakePhase[]; materialFacts: number };
export type PlanRequestPayload = Record<string, unknown> & { title: string; approval_mode?: boolean };

export const getGuidedIntake = (projectId: string, body: Record<string, unknown>) =>
  json<GuidedIntake>(`/projects/${projectId}/intake`, { method: "POST", headers: jsonHeaders, body: JSON.stringify(body) });

export const compileGuidedIntake = (
  projectId: string,
  baseRequest: Record<string, unknown>,
  answers: Record<string, unknown>,
  intake: GuidedIntake,
) =>
  json<PlanRequestPayload>(`/projects/${projectId}/intake/compile`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ base: baseRequest, answers, intake }),
  });

/** Start generation from a compiled request: outline first when samples-first was chosen. */
export const startJobFromRequest = (projectId: string, request: PlanRequestPayload) =>
  json<ProjectJob>(`/projects/${projectId}/jobs/${request.approval_mode ? "outline" : "full"}`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(request),
  });

export type RehearsalPage = {
  position: number;
  slideId?: string;
  title: string;
  startSeconds: number;
  budgetSeconds: number;
  naturalSeconds: number;
  pressure: "ok" | "compress" | "expand";
};
export type RehearsalQuestion = {
  kind: "definition" | "limitation" | "method" | "omitted";
  position: number | null;
  question: string;
  answer: string;
  sourceRef?: { document: string; section: string; page?: number | null } | null;
};
export type Rehearsal = {
  version: string;
  durationMinutes: number | null;
  pacing: { totalSeconds: number; requestedSeconds: number | null; naturalSeconds: number; pages: RehearsalPage[] };
  questions: RehearsalQuestion[];
  advice: string[];
};

export const buildRehearsal = (projectId: string, durationMinutes?: number | null) =>
  json<Rehearsal>(`/projects/${projectId}/rehearsal`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ duration_minutes: durationMinutes || null }),
  });

export const rehearsalCardUrl = (projectId: string) => `${base}/projects/${projectId}/rehearsal/card`;
