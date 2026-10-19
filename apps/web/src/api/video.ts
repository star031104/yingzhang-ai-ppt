import { base, json, jsonHeaders } from "./http";
import type { ProjectJob } from "./types";

export type NarratedVideoOptions = { tts: boolean; subtitles: boolean; locale?: "zh-CN" | "en-US" };
export type NarratedVideoResult = {
  durationSeconds?: number;
  ttsSlides?: number;
  silentSlides?: number;
  subtitles?: string | null;
};

/** Starts (or joins) the background narrated-video export job. 409 means ffmpeg is missing. */
export const startNarratedVideoJob = (projectId: string, options: NarratedVideoOptions) =>
  json<ProjectJob>(`/projects/${encodeURIComponent(projectId)}/jobs/video`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ locale: options.locale ?? "zh-CN", tts: options.tts, subtitles: options.subtitles }),
  });

export const narratedVideoUrl = (projectId: string, subtitles = false) =>
  `${base}/projects/${encodeURIComponent(projectId)}/export/video${subtitles ? "?subtitles=true" : ""}`;
