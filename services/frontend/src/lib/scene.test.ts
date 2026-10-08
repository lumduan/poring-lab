import assert from "node:assert/strict";
import { test } from "node:test";

import type { HudDelta, HudMotion, HudScene, SceneObject } from "./protocol.ts";
import { SceneStore } from "./scene.ts";

const win: SceneObject = { id: 1, kind: "window", anchor: "screen", box: { x: 0.1, y: 0.1, w: 0.2, h: 0.2 }, cls: "", conf: null };
const npc: SceneObject = { id: 2, kind: "unit", anchor: "world", box: { x: 0.5, y: 0.4, w: 0.02, h: 0.05 }, cls: "npc", conf: 0.6 };
const key = (seq: number, objects: SceneObject[], x = 0, y = 0, fid = 10, t = 1000): HudScene =>
  ({ type: "hud_scene", t_mono_ns: t, frame_id: fid, seq, offset: { x, y }, objects, period_ms: 5000 }) as HudScene;
const motion = (fid: number, t: number, x: number, y: number): HudMotion =>
  ({ type: "hud_motion", t_mono_ns: t, frame_id: fid, offset: { x, y } }) as HudMotion;
const delta = (seq: number, d: Partial<HudDelta>): HudDelta =>
  ({ type: "hud_delta", t_mono_ns: 1, frame_id: 1, seq, add: [], move: [], remove: [], ...d }) as HudDelta;

test("nothing is drawn before a keyframe; a keyframe gives the whole scene", () => {
  const s = new SceneStore();
  assert.deepEqual(s.boxes(null, null, 1000, 500), []);
  s.keyframe(key(3, [win, npc]));
  const b = s.boxes(10, 1000, 1000, 500);
  assert.equal(b.length, 2);
  assert.deepEqual([b[1].x, b[1].y, b[1].label], [500, 200, "npc 60%"]);
});

test("world objects ride the frame's motion; screen objects never shift", () => {
  const s = new SceneStore();
  s.keyframe(key(0, [win, npc]));
  s.motion(motion(11, 1100, -0.01, 0.02));
  s.motion(motion(12, 1200, -0.02, 0.04));
  const [w12, n12] = s.boxes(12, 1200, 1000, 500); // exact by frame_id
  const r = (v: number) => Math.round(v * 1000) / 1000;
  assert.deepEqual([r(w12.x), r(w12.y)], [100, 50]);
  assert.deepEqual([r(n12.x), r(n12.y)], [480, 220]);
  const [, nT] = s.boxes(99, 1150, 1000, 500); // unknown id: the latest motion at or before t
  assert.deepEqual([r(nT.x), r(nT.y)], [490, 210]);
});

test("deltas apply in order; a gap marks the scene stale until the next keyframe", () => {
  const s = new SceneStore();
  s.keyframe(key(5, [win]));
  s.delta(delta(6, { add: [npc] }));
  assert.equal(s.objects.size, 2);
  s.delta(delta(7, { move: [{ id: 2, box: { x: 0.6, y: 0.4, w: 0.02, h: 0.05 }, conf: 0.7 }] }));
  assert.equal(s.objects.get(2)?.box.x, 0.6);
  s.delta(delta(9, { remove: [2] })); // 8 was missed
  assert.ok(s.stale && s.boxes(null, null, 10, 10).length === 0);
  s.keyframe(key(9, [win]));
  const size: number = s.objects.size; // after the earlier assert, TS narrows .size to 2
  assert.ok(!s.stale && size === 1);
});
