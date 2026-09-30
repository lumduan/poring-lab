import assert from "node:assert/strict";
import { test } from "node:test";

import { eventTimeMs, LatestSlot, median, moveDelayMs, OffsetEstimator } from "./timing.ts";

const MS = 1_000_000;

test("Cristian: the min-RTT sample sets the offset, half its RTT the uncertainty", () => {
  const est = new OffsetEstimator();
  assert.equal(est.offsetNs, null);
  // True offset 1000 ms. A slow sample (40 ms RTT, asymmetric) and a fast one (4 ms RTT).
  est.sample(100 * MS, 1_130 * MS, 140 * MS, 0);
  est.sample(200 * MS, 1_202 * MS, 204 * MS, 1);
  assert.equal(est.offsetNs, 1_000 * MS);
  assert.equal(est.uncertaintyNs, 2 * MS);
});

test("old samples leave the window", () => {
  const est = new OffsetEstimator(1_000);
  est.sample(0, 1_001 * MS, 2 * MS, 0); // fast, but expires
  est.sample(0, 1_010 * MS, 20 * MS, 5_000);
  assert.equal(est.uncertaintyNs, 10 * MS);
});

test("a negative round trip is ignored", () => {
  const est = new OffsetEstimator();
  est.sample(10 * MS, 0, 5 * MS, 0);
  assert.equal(est.offsetNs, null);
});

test("move throttle: send at once when the interval has passed, else wait the rest", () => {
  assert.equal(moveDelayMs(10, 8), 0);
  assert.equal(moveDelayMs(8, 8), 0);
  assert.equal(moveDelayMs(3, 8), 5);
  assert.equal(moveDelayMs(0, 4), 4);
  assert.equal(moveDelayMs(Number.POSITIVE_INFINITY, 4), 0);
});

test("event timestamps: use the event's own time unless it is on another clock", () => {
  assert.equal(eventTimeMs(1234.5, 1240), 1234.5);
  assert.equal(eventTimeMs(1_727_000_000_000, 1240), 1240); // epoch ms: fall back
  assert.equal(eventTimeMs(0, 1240), 1240);
});

test("latest slot keeps the newest and hands back what it replaced", () => {
  const slot = new LatestSlot<string>();
  assert.equal(slot.put("a"), null);
  assert.equal(slot.put("b"), "a");
  assert.equal(slot.dropped, 1);
  assert.equal(slot.take(), "b");
  assert.equal(slot.take(), null);
});

test("median", () => {
  assert.equal(median([]), 0);
  assert.equal(median([3, 1, 2]), 2);
  assert.equal(median([4, 1, 3, 2]), 2.5);
});
