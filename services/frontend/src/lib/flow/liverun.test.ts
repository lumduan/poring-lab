import assert from "node:assert/strict";
import { test } from "node:test";

import { busyWhy, canCheck, liveButtons, liveLabel, type LiveStatus, okTail, pauseLine, REFUSALS, RUN_MODES, runCheckLines } from "./liverun.ts";
import { mapsReadyText, statusText } from "./words.ts";

const FLOW = "xmas_dun02_rogue";
const ok: LiveStatus = { state: "idle", helper_alive: true, mode: "ASSIST", flows: { [FLOW]: { title: "t", minutes: 120 } } };

test("Start only when the helper is alive, lists the flow, nothing runs, and the console is in ASSIST or BOT", () => {
  assert.deepEqual(liveButtons(ok, FLOW), { canStart: true, canStop: false, why: null });
  // Batt 2026-11-18: "with BOT it must run too" (ADR-0020 Amendment 2026-11-18); never HUMAN
  assert.deepEqual(liveButtons({ ...ok, mode: "BOT" }, FLOW), { canStart: true, canStop: false, why: null });
  assert.deepEqual(liveButtons({ ...ok, mode: "BOT" }, "project"), { canStart: true, canStop: false, why: null });
  assert.equal(liveButtons({ ...ok, mode: "HUMAN" }, FLOW).canStart, false);
  assert.match(String(liveButtons({ ...ok, mode: "HUMAN" }, FLOW).why), /in HUMAN: set ASSIST or BOT/);
  assert.equal(liveButtons({ ...ok, mode: undefined }, FLOW).canStart, false); // no mode read: off
  assert.deepEqual([...RUN_MODES], ["ASSIST", "BOT"]);
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
  for (const r of ["helper_not_running", "nothing_running", "unknown_flow", "already_running", "mode_human", "csrf_invalid"]) {
    assert.ok(REFUSALS[r], r);
  }
});

// matpilot's player test 2026-11-13: "while she really plays, the page tells me nothing"
test("the live line says what she does, the counts and the time of the time box", async () => {
  const { liveLine } = await import("./liverun.ts");
  const l = { hp: 95, hp_low: 94, pos: [8, 22], doing: "looting", block: "loot", elapsed_s: 581, kills: 23, loot_steps: 27, pickups: 5, knife: 26, steals: 14, potions: 0, flies: 0, end: {} };
  // Batt 2026-11-20: no Knife words (a Rogue's technique); a steal is an item gained, beside the loot
  assert.equal(liveLine(l, 120), "HP 95 % · looting · 23 kills · 27 loot steps · 14 stolen · 9:41 of 120 min");
  assert.equal(liveLine({ ...l, kills: 1, steals: 0, hp: null, elapsed_s: 5 }, null), "looting · 1 kill · 27 loot steps · 0:05");
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
  for (const r of ["lint_errors", "not_live", "run_start_refused", "already_running", "mode_human", "helper_not_running"]) assert.ok(REFUSALS[r], r);
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

test("a Run's pause says since when, why and that it goes on by itself (Batt 2026-11-18)", () => {
  assert.equal(pauseLine(null), null);
  assert.equal(pauseLine({ paused: false, since: null, why: null, count: 0, paused_s: 0 }), null);
  const now = pauseLine({ paused: true, since: "19:25:30", why: "the Windows taskbar shows: the game is not in front", count: 1, paused_s: 0 });
  assert.match(String(now), /^PAUSED since 19:25:30: the Windows taskbar shows/);
  assert.match(String(now), /presses nothing; it plays on by itself/);
  assert.equal(pauseLine({ paused: false, since: null, why: null, count: 2, paused_s: 31.6 }), "Paused 2 times (32 s in all): the game was off the screen; it played on by itself each time.");
});

test("the Run's own start check: one line per item, the failing ones first", () => {
  assert.deepEqual(runCheckLines(null), []);
  const lines = runCheckLines({ state: "done", items: [
    { id: "chat", ok: true, words: "the chat input is closed", value: "closed" },
    { id: "cell", ok: null, words: "cannot tell", value: null },
    { id: "weight", ok: false, words: "the weight did not read", value: null },
  ] } as never);
  assert.deepEqual(lines.map((l) => `${l.sign} ${l.id}`), ["✗ weight", "? cell", "✓ chat"]);
});


// Batt 2026-11-20: "a small dashboard of the bot, with small emoji so a look tells"
test("the monitor bar: a tile per fact with its emoji; no Knife tile; steals beside the pickups", async () => {
  const { doingIcon, monitorTiles } = await import("./liverun.ts");
  for (const [d, icon] of [["walking", "🚶"], ["scanning around her", "👀"], ["striking", "⚔️"], ["picking up", "🫳"], ["a Fly Wing", "🪽"], ["the Butterfly Wing home", "🪽"], ["a potion", "🧪"], ["the idle weapon on", "🔁"], ["waiting", "⏳"], ["RETRY 1 of 3: waiting, then checking her", "🛠️"], ["something new", "•"]] as const) {
    assert.equal(doingIcon(d), icon, d);
  }
  assert.deepEqual(monitorTiles(null).map((t) => t.key), ["state"]);
  const st = { ...ok, state: "running", live: { hp: 42, hp_low: 30, pos: [128, 89], doing: "walking", block: null, elapsed_s: 2790, kills: 89, loot_steps: 123, pickups: 14, knife: 0, steals: 3, potions: 0, flies: 15, end: {}, retries: 0 } };
  const tiles = monitorTiles(st);
  assert.deepEqual(tiles.map((t) => t.key), ["state", "doing", "hp", "cell", "kills", "items", "potions", "wings", "time"]);
  const by = Object.fromEntries(tiles.map((t) => [t.key, t]));
  assert.equal(by.state.icon, "▶️");
  assert.equal(by.doing.icon, "🚶");
  assert.equal(by.hp.text, "42 % (low 30)");
  assert.equal(by.hp.bar, 42);
  assert.equal(by.cell.text, "128, 89");
  assert.equal(by.items.text, "14 + 3 stolen");
  assert.equal(by.time.text, "46:30");
  assert.ok(!tiles.some((t) => /knife/i.test(`${t.text} ${t.title}`)));
  assert.equal(monitorTiles({ ...st, live: { ...st.live, retries: 2 } }).at(-1)?.key, "retries");
});

// Batt 2026-11-21: "add SP, the weight as a %, and the zeny: other jobs need them, a mage, a
// merchant whose skill strikes with money"
test("the live line and the monitor bar carry SP, the weight % and the zeny", async () => {
  const { liveLine, monitorTiles, zenyChange, zenyText } = await import("./liverun.ts");
  assert.equal(zenyText(0), "0");
  assert.equal(zenyText(33287), "33,287");
  assert.equal(zenyText(1234567), "1,234,567");
  assert.equal(zenyChange(33287, 30000), "+3,287");
  assert.equal(zenyChange(29000, 30000), "-1,000");
  assert.equal(zenyChange(30000, 30000), "");
  assert.equal(zenyChange(null, 30000), "");
  const base = { hp: 99, hp_low: 82, pos: [238, 125], doing: "walking", block: null, elapsed_s: 9297, kills: 346, loot_steps: 399, pickups: 91, knife: 0, steals: 0, potions: 0, flies: 76, end: {}, retries: 0 };
  const l = { ...base, sp: 74, sp_low: 12, weight: 37.7, weight_red: false, zeny: 33287, zeny_start: 30000 };
  assert.equal(liveLine(l, null), "HP 99 % · SP 74 % · weight 38 % · 33,287 z · walking · 346 kills · 399 loot steps · 76 Fly Wings · 154:57");
  assert.equal(liveLine(base, null), "HP 99 % · walking · 346 kills · 399 loot steps · 76 Fly Wings · 154:57"); // an older helper
  const tiles = monitorTiles({ ...ok, state: "running", live: l });
  assert.deepEqual(tiles.map((t) => t.key), ["state", "doing", "hp", "sp", "weight", "zeny", "cell", "kills", "items", "potions", "wings", "time"]);
  const by = Object.fromEntries(tiles.map((t) => [t.key, t]));
  assert.equal(by.sp.text, "74 % (low 12)");
  assert.equal(by.sp.bar, 74);
  assert.equal(by.sp.warn, false);
  assert.equal(by.weight.text, "38 %");
  // Batt 2026-11-21: "show the real weight in brackets"
  const nm = { ...l, weight_nm: [1680, 4200] as [number, number] };
  assert.equal(Object.fromEntries(monitorTiles({ ...ok, state: "running", live: nm }).map((t) => [t.key, t])).weight.text, "38 % (1680/4200)");
  assert.match(liveLine(nm, null) ?? "", /weight 38 % \(1680\/4200\)/);
  assert.equal(by.weight.warn, false);
  assert.equal(by.zeny.text, "33,287 (+3,287)");
  assert.equal(by.zeny.icon, "💰"); // Batt 2026-11-21: 💰 is the zeny, a hand the pickups
  assert.equal(by.items.icon, "🫳");
  assert.match(by.zeny.title, /30,000 at the Run's first read/);
  const heavy = Object.fromEntries(monitorTiles({ ...ok, state: "running", live: { ...l, sp: 10, weight: 51, weight_red: true, zeny: null } }).map((t) => [t.key, t]));
  assert.equal(heavy.sp.warn, true); // SP below 20 %
  assert.equal(heavy.weight.warn, true); // at 50 %: no natural regen
  assert.equal(heavy.zeny.text, "zeny not read");
  const unread = Object.fromEntries(monitorTiles({ ...ok, state: "running", live: { ...l, sp: null, weight: null } }).map((t) => [t.key, t]));
  assert.equal(unread.sp.text, "SP not read");
  assert.equal(unread.sp.bar, undefined);
  assert.equal(unread.weight.text, "weight not read");
});

// Batt 2026-11-21: what the flow uses (the heal item on its key, the swap's keys) is a NOTE (ℹ), not ✗
test("a note line shows ℹ, sorts after the failures and is never a refusal", async () => {
  const { markOf, runCheckLines, tickFor } = await import("./liverun.ts");
  assert.equal(markOf({ ok: true, info: true }), "info");
  assert.equal(markOf({ ok: false, info: true }), "info");
  assert.equal(markOf({ ok: false }), "fail");
  const check = { state: "done", at: "", flow: "project", ok: true, items: [
    { id: "knife", ok: false, info: true, words: "this flow swaps weapons on F4 and F5", value: null, refuses: false },
    { id: "weight", ok: false, words: "too heavy", value: "48 %" },
    { id: "heals", ok: true, info: true, words: "F2 holds 570 of the item she drinks or eats to heal", value: "570 on F2", refuses: false },
  ] };
  const lines = runCheckLines(check);
  assert.deepEqual(lines.map((l) => [l.id, l.mark, l.sign]), [["weight", "fail", "✗"], ["knife", "info", "ℹ"], ["heals", "info", "ℹ"]]);
  const t = tickFor(check, "project", "knife", {});
  assert.equal(t.mark, "info");
  assert.equal(t.refuses, false);
});
