import assert from "node:assert/strict";
import { test } from "node:test";

import type { RoutePreview } from "./protocol.ts";
import { routePath, routePixels, routeTtlMs } from "./route.ts";

const route: RoutePreview = {
  type: "route_preview",
  t_mono_ns: 1,
  frame_id: -1,
  label: "walk@8 route 3",
  ttl_ms: 4000,
  points: [
    { x: 0.5, y: 0.5, kind: "start" },
    { x: 0.6, y: 0.4, kind: "waypoint" },
    { x: 0.7, y: 0.45, kind: "goal" },
    { x: 0.6, y: 0.4, kind: "click" },
  ],
};

test("points scale to the canvas like detection boxes", () => {
  const px = routePixels(route, 1000, 500);
  assert.deepEqual(px[1], { x: 600, y: 200, kind: "waypoint" });
  assert.equal(px.length, 4);
});

test("the drawn path is the polyline without the next click", () => {
  const path = routePath(routePixels(route, 100, 100));
  assert.deepEqual(path.map((p) => p.kind), ["start", "waypoint", "goal"]);
});

test("an empty or missing route clears at once; otherwise it lives its ttl", () => {
  assert.equal(routeTtlMs(null), 0);
  assert.equal(routeTtlMs({ ...route, points: [] }), 0);
  assert.equal(routeTtlMs(route), 4000);
});
