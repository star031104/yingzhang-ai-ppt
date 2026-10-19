import { json, jsonHeaders } from "./http";
import type { SlideSpec } from "./types";

/** A rectangle in slide coordinates (the rendered canvas is 1280 × 720). */
export type RegionBox = { x: number; y: number; width: number; height: number };
export type RegionTarget = {
  kind: "title" | "message" | "bullet" | "visual";
  index?: number;
  object?: string;
  metric?: boolean;
  label: string;
  nodeIds: string[];
  weight: number;
};
export type RegionEditResult = {
  slide: SlideSpec;
  version: number;
  region: { bbox: RegionBox; targets: RegionTarget[] };
  edited: { kind: string; index?: number; variant?: string; operation: string; label: string }[];
  render: { variant?: string } | null;
};

export const SLIDE_WIDTH = 1280;
export const SLIDE_HEIGHT = 720;

export const regionEditSlide = (
  projectId: string,
  slideId: string,
  bbox: RegionBox,
  instruction: string,
  revision?: number,
) =>
  json<RegionEditResult>(
    `/projects/${encodeURIComponent(projectId)}/slides/${encodeURIComponent(slideId)}/region-edit`,
    { method: "POST", headers: jsonHeaders, body: JSON.stringify({ bbox, instruction, revision }) },
  );
