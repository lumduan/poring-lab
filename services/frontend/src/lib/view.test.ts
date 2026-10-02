import assert from "node:assert/strict";
import { test } from "node:test";

import { drawRect, normalizePoint } from "./view.ts";

const FRAME = { width: 1280, height: 720 };

test("fit in a wider viewport pillarboxes and centres", () => {
  const r = drawRect({ width: 2000, height: 720 }, FRAME, "fit");
  assert.deepEqual(r, { x: 360, y: 0, width: 1280, height: 720 });
});

test("fit in a taller viewport letterboxes and centres", () => {
  const r = drawRect({ width: 640, height: 1000 }, FRAME, "fit");
  assert.deepEqual(r, { x: 0, y: 320, width: 640, height: 360 });
});

test("fit scales up too, keeping the aspect ratio", () => {
  const r = drawRect({ width: 2560, height: 1440 }, FRAME, "fit");
  assert.deepEqual(r, { x: 0, y: 0, width: 2560, height: 1440 });
});

test("native is 1:1 at the origin whatever the viewport", () => {
  assert.deepEqual(drawRect({ width: 300, height: 200 }, FRAME, "native"), {
    x: 0,
    y: 0,
    width: 1280,
    height: 720,
  });
});

test("degenerate sizes fall back to native", () => {
  assert.deepEqual(drawRect({ width: 0, height: 0 }, FRAME, "fit"), {
    x: 0,
    y: 0,
    width: 1280,
    height: 720,
  });
});

test("normalization is relative to the drawn image, not the viewport", () => {
  const r = drawRect({ width: 640, height: 1000 }, FRAME, "fit"); // letterboxed at y=320
  assert.deepEqual(normalizePoint(160, 320 + 180, r), { x: 0.25, y: 0.5, inside: true });
});

test("points in the letterbox are outside and clamped to the edge", () => {
  const r = drawRect({ width: 640, height: 1000 }, FRAME, "fit");
  assert.deepEqual(normalizePoint(320, 100, r), { x: 0.5, y: 0, inside: false });
  assert.deepEqual(normalizePoint(700, 900, r), { x: 1, y: 1, inside: false });
});

test("image edges count as inside", () => {
  const r = { x: 10, y: 10, width: 100, height: 50 };
  assert.equal(normalizePoint(10, 10, r).inside, true);
  assert.equal(normalizePoint(110, 60, r).inside, true);
  assert.equal(normalizePoint(110.5, 60, r).inside, false);
});

test("an empty rect never reports inside", () => {
  assert.equal(normalizePoint(5, 5, { x: 0, y: 0, width: 0, height: 0 }).inside, false);
});

test("the lab's 1440x900 session: a game pixel round-trips in fit and native (2026-10-02)", () => {
  // The RO client area is 1280x720 at (80,77) of the 1440x900 desktop; aim at its centre.
  const DESK = { width: 1440, height: 900 };
  const target = { x: 80 + 640, y: 77 + 360 };
  for (const viewport of [{ width: 1180, height: 760 }, { width: 2560, height: 1300 }]) {
    const r = drawRect(viewport, DESK, "fit");
    const s = r.width / DESK.width;
    const p = normalizePoint(r.x + target.x * s, r.y + target.y * s, r);
    assert.equal(p.inside, true);
    assert.ok(Math.abs(p.x * DESK.width - target.x) < 1e-9 && Math.abs(p.y * DESK.height - target.y) < 1e-9);
  }
  // native: 1:1, the viewport scrolled by (200, 150) -> the image's client rect starts at -200,-150
  const scrolled = { x: -200, y: -150, width: 1440, height: 900 };
  const q = normalizePoint(target.x - 200, target.y - 150, scrolled);
  assert.deepEqual({ x: q.x * 1440, y: q.y * 900, inside: q.inside }, { ...target, inside: true });
});
