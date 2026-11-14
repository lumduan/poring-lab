import assert from "node:assert/strict";
import { test } from "node:test";

import { busyWhy, canCheck, liveButtons, liveLabel, type LiveStatus, okTail, REFUSALS } from "./liverun.ts";
import { mapsReadyText, statusText } from "./words.ts";

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

// matpilot round 17 N5: at 04:24 and 04:26 GET /flows/run said "idle", "waiting for the Run
// button" while the live block player played an A/B run, and Run stayed enabled at both sizes
test("another input writer of ours playing disables Run and the check, in the helper's words", () => {
  const why = "an A/B series is running (one input writer at a time)";
  const busy: LiveStatus = { ...ok, state: "busy", detail: why, busy: why };
  const b = liveButtons(busy, FLOW);
  assert.equal(b.canStart, false);
  assert.equal(b.why, `${why}: Run waits until it ends (the Run helper refuses to start meanwhile)`);
  assert.equal(liveButtons(busy, "project").canStart, false); // a PROJECT run (the live block player) too
  // matpilot round 18 (c): "Check the game"'s title names the CHECK as what waits, not Run
  assert.deepEqual(canCheck(busy, FLOW), { can: false, why: `${why}: the check waits until it ends (the Run helper refuses a check meanwhile)` });
  assert.equal(canCheck(busy, FLOW).why, busyWhy(busy, "check"));
  assert.doesNotMatch(String(canCheck(busy, FLOW).why), /Run waits/);
  assert.equal(liveLabel(busy), `busy: ${why}`);
  // a last run's end keeps its words; `busy` still disables Run
  const ended: LiveStatus = { ...ok, state: "ended", detail: "Stopped by you after 3 min.", busy: why };
  assert.equal(liveButtons(ended, FLOW).canStart, false);
  assert.equal(liveLabel(ended), `busy: ${why}`);
  // gone: Run again
  assert.equal(liveButtons({ ...ok, busy: null }, FLOW).canStart, true);
  assert.equal(busyWhy({ ...ok }), null);
  assert.ok(REFUSALS.input_writer_busy);
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

test("a check carries the project and its node; a stop nothing (live-blocks.md 12)", async () => {
  const { runBody, checkBody, checkTime } = await import("./liverun.ts");
  const { xmasProject } = await import("./project.ts");
  const p = xmasProject();
  // 2026-11-14: the backend reads the node's keys (its functions) and its setting blocks from the
  // project, as the Run does: the body names no flow, no keys, no values
  assert.deepEqual(checkBody(p, "xmas_dun02"), { project: p, node: "xmas_dun02" });
  assert.deepEqual(Object.keys(JSON.parse(JSON.stringify(checkBody(p, "xmas_dun02")))).sort(), ["node", "project"]);
  const { runPath } = await import("./liverun.ts");
  assert.equal(runPath("check"), "/flows/run/check"); // its own route (matpilot #16)
  assert.equal(runPath("stop"), "/flows/run");
  assert.deepEqual(runBody("stop"), { action: "stop" });
  assert.match(checkTime(CHECK.at), /^\d\d:\d\d:05$/);
  assert.equal(checkTime("not a time"), "not a time");
  assert.ok(REFUSALS.keys_refused && REFUSALS.check_running && REFUSALS.settings_refused && REFUSALS.no_hunt_core);
  // the settings file's refusals went with it (GET / PUT /flows/config)
  assert.equal(REFUSALS.config_file_broken, undefined);
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
  // Stop is as before
  assert.deepEqual(runBody("stop"), { action: "stop" });
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

// matpilot round 18 (b): while the helper says busy Run is disabled, so neither page's status line
// may say "Run (amber) plays it in the game": it says why Run is off, in the helper's words
test("both pages' status lines say why Run is off while another input writer plays", () => {
  const why = "an A/B series is running (one input writer at a time)";
  const busy: LiveStatus = { ...ok, state: "busy", detail: why, busy: why };
  const base = { loading: false, engine: null, issues: 0, lintErrors: 0, simulating: false, mapTab: false, run: true };
  const flows = statusText({ ...base, busy: busyWhy(busy) });
  assert.equal(flows, `Ready to simulate: Simulate plays this map without the game. Run is off now: ${why}: Run waits until it ends (the Run helper refuses to start meanwhile).`);
  assert.doesNotMatch(flows, /Run \(amber\) plays/);
  assert.match(statusText({ ...base, busy: busyWhy(ok) }), /Run \(amber\) plays it in the game/);
  const maps = mapsReadyText("xmas_dun02", busyWhy(busy));
  assert.match(maps, /^Ready to simulate: Simulate plays the project from START \(xmas_dun02\) without the game\. Run is off now: an A\/B series/);
  assert.doesNotMatch(maps, /Run \(amber\) plays/);
  assert.match(mapsReadyText("xmas_dun02", busyWhy(ok)), /Run \(amber\) plays it in the game from there, box by box\.$/);
  assert.match(mapsReadyText(null, null), /^Ready\. Press Simulate to watch the bot log in/);
});

// matpilot round 18 #1: the identity line's "(her references; no DB, as the player start)" showed
// as "no DB, as the player start)": the cut at the last ";" fell inside the parenthesis
test("a ✓ line's tail is cut at the last ';' outside parentheses, never inside one", () => {
  const identity = "the name plate reads Rogue and the job rogue (her references; no DB, as the player start)";
  assert.equal(okTail(identity), null); // no ";" outside the parenthesis: the value says it all
  assert.equal(okTail("on xmas_dun02; at 120,85 (the cell read; 2 reads)"), "at 120,85 (the cell read; 2 reads)");
  assert.equal(okTail("4 Fly Wings on F8: at least 2; the icon reads Fly Wing"), "the icon reads Fly Wing");
  assert.equal(okTail("a; b; c"), "c");
  assert.equal(okTail("no semicolon"), null);
  assert.equal(okTail("ends with;"), null);
  assert.equal(okTail(null), null);
  // whatever it shows, its parentheses balance
  for (const w of [identity, "x (a; b) y; z (c; d)", "(a; b); c", "a; (b; c"]) {
    const t = okTail(w) ?? "";
    assert.equal((t.match(/\(/g) ?? []).length >= (t.match(/\)/g) ?? []).length, true, w);
  }
});
