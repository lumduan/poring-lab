import assert from "node:assert/strict";
import test from "node:test";

import { FALLBACK_COLOURS } from "../maps/draw.ts";
import { cellPx, drawLive, HER_COLOUR, NEAR_R, sightLine, sightOf, TRAIL_COLOUR, viewWindow } from "./livemap.ts";
import type { LiveSummary } from "./liverun.ts";

/** A recording 2D context: each call with the fill colour at that moment. */
function recorder() {
  const calls: { op: string; args: unknown[]; fill: unknown; stroke: unknown; width: number; alpha: number }[] = [];
  const ctx: Record<string, unknown> = { fillStyle: "", strokeStyle: "", lineWidth: 1, lineJoin: "miter", lineCap: "butt", globalAlpha: 1, font: "" };
  for (const op of ["fillRect", "clearRect", "beginPath", "arc", "fill", "stroke", "moveTo", "lineTo", "closePath", "setLineDash", "fillText", "strokeText", "roundRect"]) {
    ctx[op] = (...args: unknown[]) => calls.push({ op, args, fill: ctx.fillStyle, stroke: ctx.strokeStyle, width: ctx.lineWidth as number, alpha: ctx.globalAlpha as number });
  }
  ctx.measureText = () => ({ width: 10 });
  return { ctx: ctx as never, calls };
}

const SUMMARY = {
  map: "xmas_dun02",
  pos: [5, 2],
  trail: [[3, 2], [4, 2], [5, 2]],
  mobs: [[7, 3, "cruiser"], [1, 1, "mystcase"]],
  mobs_age_s: 0.4,
} as unknown as LiveSummary;

test("the Run's summary becomes what the live map shows (an older helper: nothing to show)", () => {
  const s = sightOf(SUMMARY);
  assert.deepEqual(s.pos, [5, 2]);
  assert.deepEqual(s.mobs, [{ x: 7, y: 3, name: "cruiser" }, { x: 1, y: 1, name: "mystcase" }]);
  assert.equal(s.trail.length, 3);
  assert.deepEqual(sightOf(null), { map: null, pos: null, trail: [], mobs: null, ageS: null });
  assert.equal(sightOf({ pos: null } as unknown as LiveSummary).mobs, null);
  assert.match(sightLine(s, true), /map xmas_dun02 · her cell \(5, 2\) · 2 monsters seen, 0.4 s ago/);
  assert.match(sightLine({ ...s, ageS: 5 }, true), /faded: not read since/);
  assert.match(sightLine({ ...s, mobs: null }, true), /no hunt core playing/);
  assert.equal(sightLine(sightOf(null), false), "No Run is playing.");
});

test("the close-up follows her and stays inside the map; the whole map is the default view", () => {
  assert.deepEqual(viewWindow("whole", [50, 50], 200, 150), { x0: 0, y0: 0, w: 200, h: 150 });
  assert.deepEqual(viewWindow("near", [50, 60], 200, 150), { x0: 50 - NEAR_R, y0: 60 - NEAR_R, w: 2 * NEAR_R + 1, h: 2 * NEAR_R + 1 });
  assert.deepEqual(viewWindow("near", [2, 148], 200, 150), { x0: 0, y0: 150 - (2 * NEAR_R + 1), w: 2 * NEAR_R + 1, h: 2 * NEAR_R + 1 });
  assert.deepEqual(viewWindow("near", null, 200, 150), { x0: 0, y0: 0, w: 200, h: 150 }); // no cell yet
  // y grows north: the top row of the window is its highest y
  assert.deepEqual(cellPx({ x0: 0, y0: 0, w: 10, h: 4 }, 10, 0, 3), { x: 5, y: 5 });
});

test("she is drawn green OVER the red monsters; the walk grid as /maps; stale dots fade", () => {
  const rows = ["........", "...##...", "........", "........"];
  const win = { x0: 0, y0: 0, w: 8, h: 4 };
  const { ctx, calls } = recorder();
  const got = drawLive(ctx, { rows, win, scale: 10, sight: sightOf(SUMMARY), colours: FALLBACK_COLOURS });
  assert.deepEqual(got, { her: true, mobs: 2, trail: 3 });
  const fills = calls.filter((c) => c.op === "fill").map((c) => c.fill);
  assert.deepEqual(fills, [FALLBACK_COLOURS.monster, FALLBACK_COLOURS.monster, HER_COLOUR]); // her last: on top
  assert.ok(calls.some((c) => c.op === "fillRect" && c.fill === FALLBACK_COLOURS.floor));
  assert.ok(calls.some((c) => c.op === "fillText" && c.args[0] === "cruiser")); // names at a close scale
  const old = recorder();
  drawLive(old.ctx, { rows, win, scale: 3, sight: { ...sightOf(SUMMARY), ageS: 9 }, colours: FALLBACK_COLOURS });
  const mobFills = old.calls.filter((c) => c.op === "fill" && c.fill === FALLBACK_COLOURS.monster);
  assert.ok(mobFills.length === 2 && mobFills.every((c) => c.alpha < 1));
  assert.ok(!old.calls.some((c) => c.op === "fillText")); // no names when small
  // outside the window: not drawn
  const out = recorder();
  assert.deepEqual(drawLive(out.ctx, { rows, win: { x0: 6, y0: 0, w: 2, h: 4 }, scale: 10, sight: sightOf(SUMMARY), colours: FALLBACK_COLOURS }), { her: false, mobs: 1, trail: 0 });
});

test("her path is a WHITE line on a dark casing (Batt 2026-11-21: the green line was hard to see)", () => {
  const { ctx, calls } = recorder();
  const sight = { ...sightOf(SUMMARY), mobs: [] }; // no monster: their edges are strokes too
  drawLive(ctx, { rows: ["........", "........", "........", "........"], win: { x0: 0, y0: 0, w: 8, h: 4 }, scale: 10, sight, colours: FALLBACK_COLOURS });
  const strokes = calls.filter((c) => c.op === "stroke");
  assert.equal(strokes.length, 3); // the casing, the white line, then her dot's edge
  assert.equal(strokes[0].stroke, FALLBACK_COLOURS.wall);
  assert.equal(strokes[1].stroke, TRAIL_COLOUR);
  assert.equal(TRAIL_COLOUR, "#ffffff");
  assert.ok(strokes[0].width > strokes[1].width); // the casing shows on both sides
  assert.notEqual(strokes[1].stroke, HER_COLOUR); // her dot stays green, the path is white
});
