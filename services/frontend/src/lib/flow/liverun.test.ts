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

// dungeon@9.45 (Batt 2026-11-13 "do it"): the start checklist ticked from the game screen
const CHECK = {
  state: "done",
  at: "2026-11-13T18:30:05+07:00",
  flow: FLOW,
  ok: false,
  refuses: true,
  items: [
    { id: "wings", ok: true, words: "12 Fly Wings on F8: at least 5", value: "12 Fly Wings on F8", refuses: true },
    { id: "chat", ok: false, words: "the chat input is open (now): close it first (a person)", value: "open", refuses: true },
    { id: "home", ok: false, words: "no Butterfly Wing on the hotbar (count 0) (F9)", value: "0 Butterfly Wings on F9", refuses: false },
    { id: "knife", ok: null, words: "the F4 slot is dark (a load screen?): not read", value: null, refuses: true },
  ],
  used: { fly_key: "F8", PLAYER_MIN_WINGS: 5, home_key: "F9", knife_key: "F4", knife_swap: true },
};

test("a line's tick: ✓ with the value read, ✗ with its words, ? when not read, none without a result", async () => {
  const { tickFor } = await import("./liverun.ts");
  const w = tickFor(CHECK, FLOW, "wings", { PLAYER_MIN_WINGS: 5, fly_key: "F8" });
  assert.deepEqual([w.mark, w.sign, w.value, w.stale], ["ok", "✓", "12 Fly Wings on F8", false]);
  const c = tickFor(CHECK, FLOW, "chat", {});
  assert.deepEqual([c.mark, c.sign, c.refuses], ["fail", "✗", true]);
  assert.match(String(c.words), /chat input is open/);
  assert.equal(tickFor(CHECK, FLOW, "home", { home_key: "F9" }).refuses, false); // a warning only
  assert.deepEqual([tickFor(CHECK, FLOW, "knife", {}).mark, tickFor(CHECK, FLOW, "knife", {}).sign], ["unread", "?"]);
  assert.equal(tickFor(CHECK, FLOW, "cell", {}).mark, "none");
  assert.equal(tickFor({ ...CHECK, state: "checking" }, FLOW, "wings", {}).mark, "none");
  assert.equal(tickFor(null, FLOW, "wings", {}).mark, "none");
});

test("a result is greyed once the settings it was made with changed", async () => {
  const { checkStale, tickFor } = await import("./liverun.ts");
  assert.equal(checkStale(CHECK, FLOW, { fly_key: "F8", PLAYER_MIN_WINGS: 5 }), false);
  assert.equal(checkStale(CHECK, FLOW, { fly_key: "F6" }), true); // another key since
  assert.equal(checkStale(CHECK, FLOW, { PLAYER_MIN_WINGS: 3 }), true);
  assert.equal(checkStale(CHECK, "other_flow", {}), true);
  assert.equal(checkStale(CHECK, FLOW, {}), false);
  assert.equal(tickFor(CHECK, FLOW, "wings", { fly_key: "F6" }).stale, true);
});

test("Run stays pressable with a ✗, and its title says the runner will refuse", async () => {
  const { refuseWarning } = await import("./liverun.ts");
  const w = String(refuseWarning(CHECK, FLOW));
  assert.match(w, /chat input is open/);
  assert.match(w, /runner will refuse/);
  assert.ok(!/Butterfly/.test(w)); // the runner does not refuse on the Butterfly Wings
  assert.equal(refuseWarning({ ...CHECK, items: [CHECK.items[0], CHECK.items[2]] }, FLOW), null);
  assert.equal(refuseWarning(CHECK, "other_flow"), null);
  assert.match(String(refuseWarning({ ...CHECK, state: "refused", items: [], detail: "refused before any input: the Knife and the dagger are both on F4" }, FLOW)), /both on F4/);
  assert.equal(liveButtons({ ...ok, check: CHECK }, FLOW).canStart, true); // warnings, not locks
});

test("the game is checked only while no run goes and no check reads", async () => {
  const { canCheck } = await import("./liverun.ts");
  assert.deepEqual(canCheck(ok, FLOW), { can: true, why: null });
  assert.equal(canCheck({ ...ok, mode: "HUMAN" }, FLOW).can, true); // it reads only: no ASSIST needed
  assert.equal(canCheck({ ...ok, state: "running" }, FLOW).can, false);
  assert.equal(canCheck({ ...ok, check: { ...CHECK, state: "checking" } }, FLOW).can, false);
  assert.equal(canCheck({ ...ok, helper_alive: false }, FLOW).can, false);
  assert.equal(canCheck(ok, "other_flow").can, false);
  assert.equal(canCheck(null, FLOW).can, false);
});

test("a start or a check carries the flow and the flow's keys; a stop nothing", async () => {
  const { runBody, checkTime } = await import("./liverun.ts");
  const keys = { heal_key: "F1", fly_key: "F8", home_key: "F9", knife_key: "F4", dagger_key: "F5" };
  assert.deepEqual(runBody("start", FLOW, keys), { action: "start", flow: FLOW, keys });
  assert.deepEqual(runBody("check", FLOW, null), { flow: FLOW }); // its own route (matpilot #16)
  const { runPath } = await import("./liverun.ts");
  assert.equal(runPath("check"), "/flows/run/check");
  assert.equal(runPath("start"), "/flows/run");
  assert.deepEqual(runBody("stop", FLOW, keys), { action: "stop" });
  assert.match(checkTime(CHECK.at), /^\d\d:\d\d:05$/);
  assert.equal(checkTime("not a time"), "not a time");
  assert.ok(REFUSALS.keys_refused && REFUSALS.check_running);
});

// THE PROJECT RUN (Batt 2026-11-13 ~21:4x, live-blocks.md stage 1): the request the other half
// (feat/live-player: the backend and the live block player) is built against
test("the project run: POST /flows/run/project {project, node}; its status is the flow id project", async () => {
  const { PROJECT_FLOW, projectRunBody, projectRunPath, runBody, runPath } = await import("./liverun.ts");
  const { xmasProject } = await import("./project.ts");
  const p = xmasProject();
  assert.equal(projectRunPath(), "/flows/run/project");
  assert.deepEqual(projectRunBody(p, "xmas_dun02"), { project: p, node: "xmas_dun02" });
  assert.deepEqual(Object.keys(JSON.parse(JSON.stringify(projectRunBody(p, "xmas_dun02")))).sort(), ["node", "project"]);
  // Stop and the check are as before
  assert.deepEqual(runBody("stop", PROJECT_FLOW), { action: "stop" });
  assert.equal(runPath("stop"), "/flows/run");
  // the buttons: a project run needs no entry in the helper's flow list; ASSIST and an idle helper still do
  assert.equal(PROJECT_FLOW, "project");
  assert.deepEqual(liveButtons(ok, PROJECT_FLOW), { canStart: true, canStop: false, why: null });
  assert.equal(liveButtons({ ...ok, mode: "HUMAN" }, PROJECT_FLOW).canStart, false);
  assert.equal(liveButtons({ ...ok, helper_alive: false }, PROJECT_FLOW).canStart, false);
  assert.deepEqual(liveButtons({ ...ok, state: "running", flow: PROJECT_FLOW }, PROJECT_FLOW), { canStart: false, canStop: true, why: null });
  // every refusal of the project run has words
  for (const r of ["lint_errors", "not_live", "run_start_refused", "already_running", "mode_not_assist", "helper_not_running"]) assert.ok(REFUSALS[r], r);
});
