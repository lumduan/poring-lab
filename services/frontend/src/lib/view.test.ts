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
