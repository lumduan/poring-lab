import assert from "node:assert/strict";
import { test } from "node:test";

import type { RoutePreview } from "./protocol.ts";
import { routePixels } from "./route.ts";

const route: RoutePreview = {
  type: "route_preview",
  t_mono_ns: 1,
  frame_id: -1,
  label: "walk@8 route 3",
  live: true,
  passed: [],
  clip: [],
  points: [
    { x: 0.5, y: 0.5, kind: "start" },
    { x: 0.6, y: 0.4, kind: "waypoint" },
    { x: 0.7, y: 0.45, kind: "goal" },
    { x: 0.6, y: 0.4, kind: "click" },
  ],
};

// An older sender's one-shot (screen-pixel) message: the protocol refuses it since 2026-10-08
// (live must be true), and the console ignores it anyway.
const oneShot = { ...route, live: false, ttl_ms: 4000 } as unknown as RoutePreview;

test("points scale to the canvas like detection boxes", () => {
  const px = routePixels(route, 1000, 500);
  assert.deepEqual(px[1], { x: 600, y: 200, kind: "waypoint" });
  assert.equal(px.length, 4);
});


// --- LIVE previews (Batt 2026-10-08): world-anchored, matched to the displayed frame ---------------
import { FADE_MS, clipRects, isLive, passedAlpha, passedPixels, pickForFrame, pushLive } from "./route.ts";

const live = (t: number, extra: Partial<RoutePreview> = {}): RoutePreview =>
  ({ ...route, t_mono_ns: t, points: [{ x: 0.5, y: 0.5, kind: "feet" }], ...extra }) as RoutePreview;

test("the live message drawn is the one nearest the displayed frame; none when all are stale", () => {
  let buf: RoutePreview[] = [];
  for (const t of [1_000e6, 1_050e6, 1_100e6]) buf = pushLive(buf, live(t));
  assert.equal(pickForFrame(buf, 1_060e6)?.t_mono_ns, 1_050e6);
  assert.equal(pickForFrame(buf, 1_090e6)?.t_mono_ns, 1_100e6);
  assert.equal(pickForFrame(buf, 1_600e6), null); // 500 ms from any route: the camera has moved on
  assert.equal(pickForFrame(buf, null), null); // no frame yet: nothing to anchor it to
});

test("an empty live message ends the route; the buffer keeps only the newest", () => {
  let buf: RoutePreview[] = [];
  for (let k = 0; k < 60; k++) buf = pushLive(buf, live(k * 50e6));
  assert.equal(buf.length, 40);
  assert.equal(buf[0].t_mono_ns, 20 * 50e6);
  assert.deepEqual(pushLive(buf, live(9e9, { points: [] })), []);
  assert.ok(isLive(buf[0]) && !isLive(oneShot));
});

test("a one-shot preview is never drawn and never clears a live route (Batt 2026-10-08)", () => {
  assert.deepEqual(pushLive([], oneShot), []); // walk@8-12's screen-pixel plan: dropped on arrival
  const buf = pushLive([], live(1_000e6));
  assert.equal(pushLive(buf, { ...oneShot, points: [] }), buf); // its empty "clear" changes nothing
  assert.equal(pushLive(buf, oneShot), buf);
  assert.equal(pickForFrame(pushLive([], oneShot), 1), null); // nothing to draw
});

test("the walked-over stretch fades by its age and disappears at FADE_MS", () => {
  assert.equal(passedAlpha(0), 1);
  assert.equal(passedAlpha(FADE_MS / 2), 0.5);
  assert.equal(passedAlpha(FADE_MS), 0);
  const m = live(1, {
    passed: [
      { points: [{ x: 0.4, y: 0.5, kind: "waypoint" }, { x: 0.45, y: 0.5, kind: "waypoint" }], age_ms: 100 },
      { points: [{ x: 0.3, y: 0.5, kind: "waypoint" }, { x: 0.35, y: 0.5, kind: "waypoint" }], age_ms: 450 },
    ],
  } as Partial<RoutePreview>);
  const px = passedPixels(m, 1000, 500);
  assert.equal(px.length, 1);
  assert.deepEqual(px[0].a, { x: 400, y: 250 });
  assert.equal(px[0].alpha, 0.75);
});

test("the client's UI windows travel as clip rectangles in canvas pixels", () => {
  const m = live(1, { clip: [{ x: 0.1, y: 0.2, w: 0.3, h: 0.1 }] } as Partial<RoutePreview>);
  assert.deepEqual(clipRects(m, 1000, 500), [{ x: 100, y: 100, w: 300, h: 50 }]);
  assert.deepEqual(clipRects(null, 1000, 500), []);
});
