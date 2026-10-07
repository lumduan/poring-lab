// The agent's planned route over the stream (walk@8, Batt 2026-10-07): display only. Pure, unit
// tested with `node --test` (src/lib/route.test.ts).

import type { RoutePreview } from "./protocol.ts";

export type RoutePixel = { x: number; y: number; kind: "start" | "waypoint" | "goal" | "click" };

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
