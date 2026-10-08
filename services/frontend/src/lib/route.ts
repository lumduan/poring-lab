// The agent's planned route over the stream (walk@8, Batt 2026-10-07): display only. Pure, unit
// tested with `node --test` (src/lib/route.test.ts).

import type { RoutePreview } from "./protocol.ts";

export type RoutePixel = { x: number; y: number; kind: "start" | "waypoint" | "goal" | "click" | "feet" };

/** The route's points in canvas pixels (points are normalized like detection boxes). */
export function routePixels(route: RoutePreview | null, width: number, height: number): RoutePixel[] {
  if (!route) return [];
  return route.points.map((p) => ({ x: p.x * width, y: p.y * height, kind: p.kind ?? "waypoint" }));
}

/** The polyline the agent will walk: every point but the next click, in order. */
export function routePath(pixels: RoutePixel[]): RoutePixel[] {
  return pixels.filter((p) => p.kind !== "click");
}

/** How long to keep it on screen; an empty route clears at once. */
export function routeTtlMs(route: RoutePreview | null): number {
  if (!route || route.points.length === 0) return 0;
  return route.ttl_ms ?? 5000;
}

// --- LIVE previews (Batt 2026-10-08): the route anchored to the WORLD -------------------------------
// The agent re-projects its map cells ~20 times a second from the character's CURRENT position and
// stamps each message with the host clock -- the clock of the stream frames' t_capture_ns too. The
// console draws the live message nearest the frame it is showing, and NOTHING when none is close:
// a stale route is never drawn (it would float over a scene the camera has moved).

export const LIVE_MAX_SKEW_NS = 200e6; // a live route farther than this from the frame: not drawn
export const LIVE_BUFFER = 40; // ~2 s at 20 Hz
export const FADE_MS = 400; // a walked-over stretch fades out over this, then it is dropped

export function isLive(route: RoutePreview | null): boolean {
  return route?.live === true;
}

/** Keep the newest live messages (time order); an empty one (the route ended) clears the buffer. */
export function pushLive(buffer: RoutePreview[], msg: RoutePreview, cap = LIVE_BUFFER): RoutePreview[] {
  if (msg.points.length === 0) return [];
  const out = [...buffer, msg].sort((a, b) => a.t_mono_ns - b.t_mono_ns);
  return out.slice(Math.max(0, out.length - cap));
}

/** The live message nearest the displayed frame's capture time, or null when none is close. */
export function pickForFrame(
  buffer: RoutePreview[],
  frameNs: number | null,
  maxSkewNs = LIVE_MAX_SKEW_NS,
): RoutePreview | null {
  if (frameNs == null || buffer.length === 0) return null;
  let best: RoutePreview | null = null;
  let bestSkew = Number.POSITIVE_INFINITY;
  for (const m of buffer) {
    const skew = Math.abs(m.t_mono_ns - frameNs);
    if (skew < bestSkew) {
      best = m;
      bestSkew = skew;
    }
  }
  return bestSkew <= maxSkewNs ? best : null;
}

/** A walked-over stretch's opacity: 1 when just passed, 0 at FADE_MS. */
export function passedAlpha(ageMs: number, fadeMs = FADE_MS): number {
  return Math.max(0, Math.min(1, 1 - ageMs / fadeMs));
}

export type PixelRect = { x: number; y: number; w: number; h: number };

/** The client's UI windows (normalized) in canvas pixels: the route is drawn UNDER them. */
export function clipRects(route: RoutePreview | null, width: number, height: number): PixelRect[] {
  return (route?.clip ?? []).map((r) => ({ x: r.x * width, y: r.y * height, w: r.w * width, h: r.h * height }));
}

/** The walked-over stretches still visible, in canvas pixels with their opacity. */
export function passedPixels(
  route: RoutePreview | null,
  width: number,
  height: number,
): { a: { x: number; y: number }; b: { x: number; y: number }; alpha: number }[] {
  return (route?.passed ?? [])
    .map((s) => ({
      a: { x: s.points[0].x * width, y: s.points[0].y * height },
      b: { x: s.points[s.points.length - 1].x * width, y: s.points[s.points.length - 1].y * height },
      alpha: passedAlpha(s.age_ms),
    }))
    .filter((s) => s.alpha > 0);
}
