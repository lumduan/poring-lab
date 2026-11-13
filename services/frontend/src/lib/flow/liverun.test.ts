import assert from "node:assert/strict";
import { test } from "node:test";

import { liveButtons, liveLabel, type LiveStatus, REFUSALS } from "./liverun.ts";

const FLOW = "xmas_dun02_rogue";
const ok: LiveStatus = { state: "idle", helper_alive: true, mode: "ASSIST", flows: { [FLOW]: { title: "t", minutes: 120 } } };

test("Start only when the helper is alive, lists the flow, nothing runs, and the console is in ASSIST", () => {
  assert.deepEqual(liveButtons(ok, FLOW), { canStart: true, canStop: false, why: null });
  assert.equal(liveButtons({ ...ok, mode: "HUMAN" }, FLOW).canStart, false);
  assert.match(String(liveButtons({ ...ok, mode: "HUMAN" }, FLOW).why), /ASSIST/);
  assert.equal(liveButtons({ ...ok, helper_alive: false }, FLOW).canStart, false);
  assert.equal(liveButtons(ok, "other_flow").canStart, false);
  assert.equal(liveButtons(null, FLOW).canStart, false);
});

test("Stop while a run is going, not while it already stops", () => {
  assert.deepEqual(liveButtons({ ...ok, state: "running" }, FLOW), { canStart: false, canStop: true, why: null });
  assert.equal(liveButtons({ ...ok, state: "starting" }, FLOW).canStop, true);
  assert.equal(liveButtons({ ...ok, state: "stopping" }, FLOW).canStop, false);
  assert.equal(liveButtons({ ...ok, state: "ended" }, FLOW).canStart, true); // a new run after an end
});

test("the labels and every refusal the backend gives have words", () => {
  assert.equal(liveLabel({ ...ok, state: "running" }), "playing in the game");
  assert.equal(liveLabel({ ...ok, helper_alive: false }), "the Run helper is not running");
  for (const r of ["helper_not_running", "nothing_running", "unknown_flow", "already_running", "mode_not_assist", "csrf_invalid"]) {
    assert.ok(REFUSALS[r], r);
  }
});

// matpilot's player test 2026-11-13: "while she really plays, the page tells me nothing"
test("the live line says what she does, the counts and the time of the time box", async () => {
  const { liveLine } = await import("./liverun.ts");
  const l = { hp: 95, hp_low: 94, pos: [8, 22], doing: "looting", block: "loot", elapsed_s: 581, kills: 23, loot_steps: 27, pickups: 5, knife: 26, steals: 14, potions: 0, flies: 0, end: {} };
  assert.equal(liveLine(l, 120), "HP 95 % · looting · 23 kills · 27 loot steps · 26 Knife swaps (14 steals) · 9:41 of 120 min");
  assert.equal(liveLine({ ...l, kills: 1, knife: 0, hp: null, elapsed_s: 5 }, null), "looting · 1 kill · 27 loot steps · 0:05");
  assert.equal(liveLine(null, 120), null);
});
