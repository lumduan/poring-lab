// THE SETTING BLOCKS (lib/flow/settings.ts; docs/planning/live-blocks.md section 12; Batt 2026-11-14
// ~15:2x: "there should be no runner [page] ... make them ALL blocks, no hardcoding like this"):
// the registry the engine generated, the one box's setting tabs, the blocks <-> project round trip
// for every kind, the name rule (the map node's block > Global's > the default; a deleted block falls
// back), the checklist from the blocks, and the runner page that went.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";

import { BLOCK_DEFS, categoryOf, DEF_BY_TYPE, settingDef, toolbox, toolboxBlocks } from "./blockdefs.ts";
import { tabFromWorkspace, tabToWorkspace, type Workspace } from "./blocks.ts";
import { canonical, clone } from "./ir.ts";
import { INDENT, rowsOf } from "./layout.ts";
import { BOX_PLAYS_THEM, GLOBAL_ID, nodeById, type Project, tab, xmasProject } from "./project.ts";
import { matchEntries } from "./search.ts";
import {
  noteLines,
  nodeSettings,
  rowUnits,
  SETTING_GEOMETRY,
  SETTING_NOTE_ROWS,
  SETTING_ROW_BUDGET,
  settingRowUnits,
  settingRows,
  textUnits,
  unitOf,
  varText,
  RUNNER_MAPS,
  SETTING_BLOCKS,
  SETTING_BY_NAME,
  SETTING_BY_VAR,
  SETTING_TABS,
  SETTINGS,
  settingFallback,
  settingFields,
  settingFromFields,
  settingLit,
  settingProblem,
  settingTabNote,
  settingTooltip,
  settingType,
  startChecklist,
  withSettingTabs,
} from "./settings.ts";

const NODE = "xmas_dun02";
const f = (name: string) => {
  const x = SETTING_BY_NAME.get(name);
  assert.ok(x, name);
  return x;
};
const tabNamed = (p: Project, node: string, name: string) => nodeById(p, node)!.tabs.find((t) => t.name === name)!;

test("the registry is the engine's: 121 setting blocks in 11 tabs, the keys none, each default valid", () => {
  assert.equal(SETTINGS.version, 3);
  assert.equal(SETTING_BLOCKS.length, 121);
  // matpilot round 20 #5: in the box's tab order (survival before knife); "loop" is "timing"
  assert.deepEqual([...SETTING_TABS], ["survival", "knife", "exits", "respawn", "start", "fight", "aim", "loot", "walk", "safety", "timing"]);
  assert.deepEqual(SETTINGS.fields.filter((x) => !x.block).map((x) => x.name), ["heal_key", "fly_key", "home_key", "knife_key", "dagger_key"]);
  for (const x of SETTINGS.fields) assert.equal(settingProblem(x, x.default), null, x.name);
  // the variable names stated in ONE place (poring_flow.settings VAR_NAMES)
  assert.deepEqual(SETTINGS.fields.filter((x) => x.var !== x.name).map((x) => [x.name, x.var]), [["vt.D0_PX", "D0_PX"], ["respawn", "respawn_on_death"], ["loot", "loot_step"]]);
  assert.deepEqual([...RUNNER_MAPS], ["xmas_dun02"]);
  // the Python side's text is the generated file (test_settings.py pins the file to the engine)
  const gen = readFileSync(new URL("./settings.gen.ts", import.meta.url), "utf8");
  assert.match(gen, /^\/\* GENERATED from packages\/poring_flow\/src\/poring_flow\/settings\.py/);
});

test("the one box shows every setting it runs with, in its group's tab, at our defaults", () => {
  const x = xmasProject();
  const n = nodeById(x, NODE)!;
  assert.deepEqual(n.tabs.map((t) => t.name), ["main", "keys", "survival", "knife", "exits", "monsters", "respawn", "start", "fight", "aim", "loot", "walk", "safety", "timing"]);
  const shown = Object.fromEntries(n.tabs.flatMap((t) => Object.entries(t.vars).map(([k, v]) => [k, [t.name, v.value]])));
  // matpilot round 20 #4a: but the five its own events and functions play (drink, fly_away, bag_full,
  // respawn_button, respawn_ok): no block of them (test_settings.py pins the list to the engine's)
  assert.deepEqual([...BOX_PLAYS_THEM], ["potion_below", "fly_below", "weight_home", "respawn_at", "respawn_confirm_at"]);
  assert.deepEqual(shown, Object.fromEntries(SETTING_BLOCKS.filter((s) => !BOX_PLAYS_THEM.includes(s.name)).map((s) => [s.var, [s.group, s.default]])));
  assert.equal(Object.keys(shown).length, 116);
  // the file the engine and the Run read is the same project (byte-identical canonical)
  const file = JSON.parse(readFileSync(new URL("./fixtures/project_xmas_dun02.json", import.meta.url), "utf8")) as Project;
  assert.equal(canonical(file), canonical(x));
  // knife, survival and exits keep their functions beside their settings
  assert.deepEqual(tabNamed(x, NODE, "knife").defs.map((d) => d.name), ["knife_on", "knife_back"]);
  assert.deepEqual(Object.keys(tabNamed(x, NODE, "knife").vars), ["knife_max_s", "knife_hp_min", "knife_swap", "bare_ready", "steal_cue", "swap_gap"]);
  // a map node that sets only what differs (Global holds the rest)
  const only = withSettingTabs([tab("main", [])], { potion_below: 0.3 }, (s) => s.name === "potion_below");
  assert.deepEqual(only.map((t) => [t.name, t.vars]), [["main", {}], ["survival", { potion_below: settingLit(0.3) }]]);
});

test("every setting block round-trips: project -> blocks -> project, exactly", () => {
  const x = xmasProject();
  for (const t of SETTING_TABS) {
    const scope = { node: NODE, tab: t };
    const ws = JSON.parse(JSON.stringify(tabToWorkspace(x, scope))) as Workspace;
    const sets = ws.blocks.blocks.filter((b) => b.type.startsWith("pl_set_"));
    const held = SETTING_BLOCKS.filter((s) => s.group === t && !BOX_PLAYS_THEM.includes(s.name));
    assert.equal(sets.length, held.length, t);
    // in the registry's order (the Python view's), one under the other: never overlapping
    assert.deepEqual(sets.map((b) => b.type), held.map(settingType));
    for (let i = 1; i < sets.length; i++) assert.ok((sets[i].y ?? 0) > (sets[i - 1].y ?? 0), `${t}: ${sets[i].type}`);
    const back = tabFromWorkspace(x, scope, ws);
    assert.ok(back.ok, back.ok ? "" : back.errors.join("; "));
    if (back.ok) assert.equal(canonical(back.project), canonical(x), t);
  }
  // each kind's fields: a share as its percent, a switch on / off, a point's x and y, a none
  assert.deepEqual(settingFields(f("knife_hp_min"), 0.5), { VALUE: 50 });
  assert.deepEqual(settingFields(f("knife_swap"), true), { VALUE: "on" });
  assert.deepEqual(settingFields(f("steal_cue"), "both"), { VALUE: "both" });
  assert.deepEqual(settingFields(f("respawn_at"), "645,481"), { X: 645, Y: 481 });
  assert.deepEqual(settingFields(f("respawn_confirm_at"), "none"), { AT: "none", X: 714, Y: 405 });
  assert.deepEqual(settingFields(f("LOOT_TRIM_HOVERS"), 9), { VALUE: 9 });
  assert.deepEqual(settingFromFields(f("knife_hp_min"), { VALUE: 55 }), { value: 0.55 });
  assert.deepEqual(settingFromFields(f("WEIGHT_MAX"), { VALUE: 7 }), { error: "refuse to start with the bag at: 7 % is not from 10 % to 90 %" });
  assert.deepEqual(settingFromFields(f("respawn_confirm_at"), { AT: "none", X: 1, Y: 2 }), { value: "none" });
  assert.deepEqual(settingFromFields(f("respawn_at"), { X: 10.4, Y: 20 }), { value: "10,20" });
  assert.deepEqual(settingFromFields(f("hud"), { VALUE: "maybe" }), { error: "on or off" });
});

test("a person edits a setting block: the project's variable follows; an impossible value is refused", () => {
  const x = xmasProject();
  const scope = { node: NODE, tab: "knife" };
  const ws = JSON.parse(JSON.stringify(tabToWorkspace(x, scope))) as Workspace;
  const hp = ws.blocks.blocks.find((b) => b.type === "pl_set_knife_hp_min")!;
  hp.fields = { VALUE: 60 };
  const sw = ws.blocks.blocks.find((b) => b.type === "pl_set_knife_swap")!;
  sw.fields = { VALUE: "off" };
  const r = tabFromWorkspace(x, scope, ws);
  assert.ok(r.ok, r.ok ? "" : r.errors.join("; "));
  if (!r.ok) return;
  assert.equal(tabNamed(r.project, NODE, "knife").vars.knife_hp_min.value, 0.6);
  assert.equal(tabNamed(r.project, NODE, "knife").vars.knife_swap.value, false);
  // the block's id path is its variable: lint findings land on it
  assert.equal(r.paths[hp.id!], "knife_hp_min");
  hp.fields = { VALUE: 95 };
  const bad = tabFromWorkspace(x, scope, ws);
  assert.equal(bad.ok, false);
  if (!bad.ok) assert.match(bad.errors.join("; "), /setting knife_hp_min: or at once under HP: 95 % is not from 20 % to 90 %/);
  // the same setting twice on a tab (dragged in from the toolbox again) is refused
  const twice = JSON.parse(JSON.stringify(tabToWorkspace(x, scope))) as Workspace;
  twice.blocks.blocks.push({ ...clone(twice.blocks.blocks.find((b) => b.type === "pl_set_knife_swap")!), id: "dup", y: 9999 });
  const two = tabFromWorkspace(x, scope, twice);
  assert.equal(two.ok, false);
  if (!two.ok) assert.match(two.errors.join("; "), /setting knife_swap: this setting is on this tab twice/);
});

test("a value a setting block cannot hold stays a plain variable block, exactly as written", () => {
  const x = xmasProject();
  tabNamed(x, NODE, "knife").vars.knife_hp_min = settingLit(5); // out of range: the lint's error
  const ws = tabToWorkspace(x, { node: NODE, tab: "knife" });
  const plain = ws.blocks.blocks.find((b) => b.type === "pl_vardecl" && b.fields?.NAME === "knife_hp_min");
  assert.ok(plain, "a pl_vardecl, never a clamped number");
  const back = tabFromWorkspace(x, { node: NODE, tab: "knife" }, JSON.parse(JSON.stringify(ws)) as Workspace);
  assert.ok(back.ok);
  if (back.ok) assert.equal(tabNamed(back.project, NODE, "knife").vars.knife_hp_min.value, 5);
});

test("the name rule: the map node's block over Global's over the default; a deleted one falls back", () => {
  const x = xmasProject();
  tabNamed(x, NODE, "survival").vars.potion_below = settingLit(0.4); // a person adds them back
  tabNamed(x, NODE, "survival").vars.fly_below = settingLit(0.2);
  x.nodes.push({ id: GLOBAL_ID, kind: "global", pos: { x: 0, y: 200 }, tabs: [tab("survival", [], { potion_below: settingLit(0.3), fly_below: settingLit(0.25) })] });
  let s = nodeSettings(x, NODE);
  assert.deepEqual([s.values.potion_below, s.src.potion_below], [0.4, `${NODE}/survival`]);
  delete tabNamed(x, NODE, "survival").vars.fly_below; // the person deletes the map's block
  s = nodeSettings(x, NODE);
  assert.deepEqual([s.values.fly_below, s.src.fly_below], [0.25, "global/survival"]);
  assert.equal(settingFallback(x, NODE, f("potion_below")), "Global's 30 % (tab survival)");
  delete tabNamed(x, GLOBAL_ID, "survival").vars.fly_below; // and Global's
  s = nodeSettings(x, NODE);
  assert.deepEqual([s.values.fly_below, s.src.fly_below], [0.2, "default"]);
  assert.equal(settingFallback(x, NODE, f("fly_below")), "the default, 20 %");
  assert.equal(settingFallback(x, GLOBAL_ID, f("potion_below")), "the default, 40 %");
  // an impossible value is no value (the lint's error; Run refuses): the default stands in, as the
  // engine's node_values (never the level below: the block is there, it is wrong)
  tabNamed(x, NODE, "survival").vars.potion_below = settingLit("lots");
  assert.deepEqual([nodeSettings(x, NODE).values.potion_below, nodeSettings(x, NODE).src.potion_below], [0.4, "default"]);
  // the tooltip says it, with the range and the default
  assert.match(settingTooltip(f("potion_below"), { fallback: "Global's 30 % (tab survival)", global: true }), /^potion_below = \.\.\. \(tab survival\): heal at HP under\. 10 % to 90 %, in steps of 5 %; our default 40 %; the runner's --potion-below\. A map's block replaces Global's there\. Delete this block: Global's 30 % \(tab survival\) applies\.$/);
  // matpilot round 20 #3: "While it is off: off: ..." said "off" twice
  assert.match(settingTooltip(f("respawn")), /\nWhile it is off: after a death she stays where she fell, and the run ends there\.$/);
  assert.doesNotMatch(settingTooltip(f("npc_guard")), /off: off|While it is off: off/);
});

test("matpilot round 20 #4d: the tooltip names Global only when the project has a Global node; it says the lint's note", () => {
  const x = xmasProject(); // ONE box: no Global node
  const tip = settingTooltip(f("WALK_PICK_TOL"), { fallback: settingFallback(x, NODE, f("WALK_PICK_TOL")), global: x.nodes.some((n) => n.kind === "global") });
  assert.doesNotMatch(tip, /Global/);
  assert.match(tip, /Delete this block: the default, 1 cell applies\.$/);
  // #4c: "1 cells" / "in steps of 1 cells"
  assert.match(tip, /0 cells to 4 cells, in steps of 1 cell;/);
  assert.equal(unitOf(f("WALK_PICK_TOL"), 1), "cell");
  assert.equal(unitOf(f("WALK_PICK_TOL"), 2), "cells");
  assert.equal(unitOf(f("READ_HZ"), 5), "times a second");
  // the flyout's own tooltip (no place known): the default, never Global
  assert.match(settingTooltip(f("potion_below")), /Delete this block: the default, 40 % applies\.$/);
  // the lint's words for THIS block (a box that plays it itself)
  assert.match(settingTooltip(f("potion_below"), { note: { unused: "not used here: the drink event plays it" } }), /\nIn a Run of this project: not used here: the drink event plays it\.$/);
});

test("matpilot round 20 #5: one block per setting on a NODE -- a second one on another tab is refused, naming both tabs", () => {
  const x = xmasProject();
  const scope = { node: NODE, tab: "loot" };
  const ws = JSON.parse(JSON.stringify(tabToWorkspace(x, scope))) as Workspace;
  ws.blocks.blocks.push({ type: settingType(f("vt.D0_PX")), id: "again", x: 20, y: 9999, fields: { VALUE: 300 } });
  const r = tabFromWorkspace(x, scope, ws);
  assert.equal(r.ok, false);
  // round 21 (the re-measure of round 20): the message names BOTH tabs; the copy carries its own rows' words
  if (!r.ok) {
    assert.match(r.errors.join("; "), /setting D0_PX: D0_PX is set on this tab \(loot\) and on the tab aim of xmas_dun02: one block per setting on a node/);
    assert.deepEqual(r.issues.map((i) => [i.id, i.note]), [["again", "already set in tab aim; one block per setting on a node"]]);
  }
  // the same block on its own tab is the ordinary edit
  const aim = JSON.parse(JSON.stringify(tabToWorkspace(x, { node: NODE, tab: "aim" }))) as Workspace;
  aim.blocks.blocks.find((b) => b.type === settingType(f("vt.D0_PX")))!.fields = { VALUE: 300 };
  const ok = tabFromWorkspace(x, { node: NODE, tab: "aim" }, aim);
  assert.ok(ok.ok);
  if (ok.ok) assert.equal(tabNamed(ok.project, NODE, "aim").vars.D0_PX.value, 300);
});

test("the start checklist states the setting blocks' values (the check reads with the same)", () => {
  const x = xmasProject();
  tabNamed(x, NODE, "start").vars.PLAYER_MIN_WINGS = settingLit(7);
  const keys = { heal_key: "F2", fly_key: "F3", home_key: "F6", knife_key: "F7", dagger_key: "F9" };
  const items = startChecklist(nodeSettings(x, NODE).values, NODE, keys);
  assert.equal(items.find((i) => i.id === "wings")?.text, "at least 7 Fly Wings on F3");
  assert.equal(items.find((i) => i.id === "weight")?.text, "the bag under 48 %");
  tabNamed(x, NODE, "knife").vars.knife_swap = settingLit(false); // no Knife swap: no Knife lines
  assert.deepEqual(startChecklist(nodeSettings(x, NODE).values, NODE, keys).map((i) => i.id), ["identity", "cell", "chat", "weight", "wings", "heals", "home"]);
});

test("each setting is a block type of its own; the toolbox offers every one in its group's sub-category", () => {
  for (const s of SETTING_BLOCKS) {
    const d = DEF_BY_TYPE[settingType(s)];
    assert.ok(d && BLOCK_DEFS.includes(d), s.name);
    assert.deepEqual(d, settingDef(s));
    const names = [d.args0, d.args1].flat().filter((a) => a && "name" in a).map((a) => (a as { name: string }).name);
    for (const k of Object.keys(settingFields(s, s.default))) assert.ok(names.includes(k), `${s.name}: ${k}`);
    assert.ok(d.previousStatement === undefined && d.output === undefined, s.name); // a top-level block
    // round 20 #3: a safety switch's warning on rows of its own (the extension shows them while off)
    assert.equal(names.includes("WARN0"), s.warn !== "", s.name);
    assert.equal(names.includes(`NOTE${SETTING_NOTE_ROWS - 1}`) && names.includes(`ROW_NOTE${SETTING_NOTE_ROWS - 1}`), true, s.name);
    assert.deepEqual(d.extensions, ["pl_setting"], s.name);
  }
  // matpilot round 20 #5: ONE sub-category per group, in the tabs' order, each with a short header
  const tb = toolbox({}, { node: "map", main: false, tab: "loot" });
  const set = categoryOf(tb, "Settings");
  assert.ok(set);
  assert.equal(set.contents.filter((i) => i.kind === "block").length, 0);
  const subs = set.contents.filter((i) => i.kind === "category") as { name: string; contents: { kind: string; type?: string; text?: string }[] }[];
  assert.deepEqual(subs.map((c) => c.name), [...SETTING_TABS]);
  for (const c of subs) {
    const blocks = c.contents.filter((i) => i.kind === "block").map((i) => i.type);
    assert.deepEqual(blocks, SETTING_BLOCKS.filter((s) => s.group === c.name).map(settingType), c.name);
    const labels = c.contents.filter((i) => i.kind === "label").map((i) => i.text ?? "");
    assert.ok(labels.length >= 2 && labels.length <= 4, c.name);
    // the header is as narrow as the blocks (the old one was 1,062 px, cut at 1440)
    for (const l of labels) assert.ok(rowUnits([textUnits(l)]) <= SETTING_ROW_BUDGET, `${c.name}: ${l}`);
  }
  assert.equal(toolboxBlocks(set).length, 121);
  assert.equal(categoryOf(toolbox({}, { node: "login", main: true }), "Settings"), undefined);
});

// matpilot round 20 #2: at 390 px (scale 0.6) the blocks start at x 135 and Blockly's trashcan / zoom
// column at x 323; 108 of 121 setting blocks were cut at the screen's edge. No browser here: the rows
// are MEASURED by settings.ts' model of Blockly's text widths, fitted to the reviewer's numbers; the
// reviewer re-measures with getBoundingClientRect.
test("the width model reproduces the reviewer's round-20 measurements (the positive case)", () => {
  const G = SETTING_GEOMETRY;
  const on = textUnits("on") + G.field + G.arrow;
  // the OLD one-row layout, measured at 1440 (scale 0.75) and 390 (0.6): workspace units
  const npc = rowUnits([textUnits("no fight click near an NPC"), on, textUnits("· npc_guard", G.varPx)]);
  const npcWarn = npc + G.gap + textUnits("⚠ off: a strike near an NPC may open its dialog and stop the run", 16, true);
  const alarm = rowUnits([textUnits("... also read on the HUD's boxes and inside a strike or a wait"), on, textUnits("· alarm_fast", G.varPx)]);
  for (const [got, measured] of [
    [npc, 258 / 0.6],
    [npcWarn, 611 / 0.6],
    [alarm, 559 / 0.75],
  ] as const) {
    assert.ok(got >= measured * 0.97 && got <= measured * 1.1, `${got} vs ${measured}`); // errs wide, never narrow
  }
  // and under the model those old rows were far past the budget (the failure it now prevents)
  assert.ok(alarm > SETTING_ROW_BUDGET * 2.4 && npcWarn > SETTING_ROW_BUDGET * 3);
});

test("no row of any setting block is wider than what shows at 390 px before Blockly's controls", async () => {
  const { BLOCKLY_CONTROLS, PHONE_START_SCALE } = await import("./theme.ts");
  const left = 123 + 20 * PHONE_START_SCALE; // the toolbox, then the block's x 20 (blocks.ts)
  const controls = 390 - BLOCKLY_CONTROLS.margin - 47; // the trashcan's left edge (47 px wide)
  assert.ok(left + SETTING_ROW_BUDGET * PHONE_START_SCALE <= controls, `${left + SETTING_ROW_BUDGET * PHONE_START_SCALE} px > ${controls} px`);
  const widest: [string, number][] = [];
  for (const s of SETTING_BLOCKS) {
    const rows = settingRowUnits(s);
    for (const w of rows) assert.ok(w <= SETTING_ROW_BUDGET, `${s.name}: a row of ${Math.round(w)} units`);
    widest.push([s.name, Math.max(...rows)]);
    // the words name their subject (round 20 #4b): no fragment
    assert.doesNotMatch(s.words, /^(\.\.\.|…)|(\.\.\.|…)$/, s.name);
  }
  // the note rows a block may show (the lint's longest kinds of words)
  for (const text of ["not used here: the respawn_button function plays it", "not used while loot_items is off", "not used on xmas_dun02 while loot_step is v1, not trim", "not used: no hunt with the runner on this map reads it"]) {
    const lines = noteLines(text);
    assert.ok(lines.length >= 1 && lines.length <= SETTING_NOTE_ROWS, text);
    for (const l of lines) assert.ok(rowUnits([textUnits(l)]) <= SETTING_ROW_BUDGET, l);
  }
  // the worst of round 20: alarm_fast (447 px at 390) and near_single_still, now a few rows each
  assert.ok(settingRows(f("alarm_fast")).words.length >= 3 && settingRows(f("alarm_fast")).warn.length >= 3);
  assert.ok(settingRows(f("near_single_still")).words.length >= 2);
  // a long variable name goes on a row of its own; a short one stays beside the value
  assert.equal(settingRows(f("RESPAWN_CONFIRM_WAIT_S")).varOwnRow, true);
  assert.equal(settingRows(f("knife_swap")).varOwnRow, false);
  assert.equal(varText(f("knife_swap")), "· knife_swap");
});

test("matpilot round 20 #2: the main tab's program shows whole at 390 too: its title on two rows, the runner a role a row", async () => {
  const { titleLines } = await import("./blockdefs.ts");
  assert.deepEqual(titleLines("when the run starts: she stands on xmas_dun02"), ["when the run starts:", "she stands on xmas_dun02"]);
  assert.deepEqual(titleLines("when she arrives on xmas_dun02"), ["when she arrives on", "xmas_dun02"]);
  assert.deepEqual(titleLines("when the program starts"), ["when the program starts", ""]);
  for (const t of ["when the run starts: she stands on xmas_dun02", "after the login: choose the character", "when she arrives on xmas_dun02"]) {
    for (const l of titleLines(t)) assert.ok(rowUnits([textUnits(l)]) <= SETTING_ROW_BUDGET, l);
  }
  // each row of the runner's block and the save point, with the ready-made box's values, nested in
  // main: no row past the budget. ➡️ Round 21: measured by layout.ts, the model of zelos' own rows
  // (this test's own model took each message for a row; Blockly joined them: round 20's re-measure)
  const values: Record<string, string> = { HEAL: "heal", FLY: "fly_wing", KNIFE_ON: "knife_on", KNIFE_BACK: "knife_back", HOME: "fly_home", RESPAWN: "respawn_button", RESPAWN_OK: "respawn_ok", EAT: "eat", MAP: "geffen", X: "119", Y: "40" };
  const labels = { BADGE: "● plays live", RUN: "ran 1 · 600 s · ok" };
  const hunt = rowsOf({ type: "pl_dungeon_hunt", fields: values }, labels, INDENT);
  const save = rowsOf({ type: "pl_save_point", fields: values }, labels, INDENT);
  assert.ok(hunt.length >= 12, String(hunt.length));
  for (const r of [...hunt, ...save]) assert.ok(r.w <= SETTING_ROW_BUDGET, `${Math.round(r.w)} units: ${r.what}`);
});

test("matpilot round 20 #5: the block search finds every knife setting by 'knife', a Garm setting by 'garm'", () => {
  const tb = toolbox({}, { node: "map", main: false, tab: "aim" });
  const entries = toolboxBlocks(tb).map(({ category, item }) => ({ category, item, text: String(item.type) }));
  const found = (q: string) => matchEntries(q, entries).map((e) => String(e.item.type));
  const knife = SETTING_BLOCKS.filter((s) => s.group === "knife").map(settingType);
  assert.equal(knife.length, 6);
  for (const t of knife) assert.ok(found("knife").includes(t), t);
  for (const n of ["garm_fly", "garm_confirm", "alarm_fast", "alarm_solo", "GARM_FRESH_S"]) assert.ok(found("garm").includes(settingType(f(n))), n);
  // "loop" finds Control's loop blocks, never a setting (the group is "timing" now)
  assert.ok(!found("loop").some((t) => t.startsWith("pl_set_")));
  assert.ok(found("timing").includes(settingType(f("READ_HZ"))));
});

test("a settings tab's strip line names its group and the name rule", () => {
  const x = xmasProject();
  assert.match(settingTabNote(tabNamed(x, NODE, "timing"), "map") ?? "", /^timing -- how often the bot looks at the screen: 6 settings/);
  assert.equal(settingTabNote(tabNamed(x, NODE, "aim"), "map"), `choosing and striking -- which monster, how to aim, how fast to click: ${SETTING_BLOCKS.filter((s) => s.group === "aim").length} settings of the runner's hunt core (these replace Global's here; a deleted one falls back to Global's, else the default)`);
  assert.equal(settingTabNote(tabNamed(x, NODE, "keys"), "map"), null);
  assert.equal(settingTabNote(tabNamed(x, NODE, "main"), "map"), null);
  assert.match(settingTabNote(tabNamed(x, NODE, "knife"), "global") ?? "", /every map node takes these unless it sets its own/);
  assert.equal(SETTING_BY_VAR.get("D0_PX")?.name, "vt.D0_PX");
});

test("the runner page is gone: no runner view, no settings panel, no generated description", () => {
  for (const gone of ["./runner.ts", "./runner_sim.ts", "./config.ts", "./runners/index.ts", "./runners/xmas_dun02_rogue.gen.ts", "../../components/flows/RunnerView.tsx", "../../components/flows/ConfigPanel.tsx", "../../components/flows/blockly-runner.ts"]) {
    assert.equal(existsSync(new URL(gone, import.meta.url)), false, gone);
  }
  const client = readFileSync(new URL("../../components/flows/FlowsClient.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(client, /import .*RunnerView|findRunner\(/);
  const page = readFileSync(new URL("../../app/flows/page.tsx", import.meta.url), "utf8");
  // an old link lands on the map's node: ?runner=xmas_dun02 (or its flow id) opens xmas_dun02
  assert.match(page, /RUNNER_IDS: Record<string, string> = \{ xmas_dun02_rogue: "xmas_dun02" \}/);
  assert.match(page, /typeof block === "string" \? block : old/);
  const studio = readFileSync(new URL("../../components/flows/ProjectStudio.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(studio, /Inside the runner|onRunner|ConfigPanel/);
  assert.match(studio, /the old runner page's link \(\/flows\?runner=xmas_dun02/);
});

test("round 21 (the re-measure of round 20): Global is named only where the project has one; a flagless switch says what it turns on", () => {
  const x = xmasProject(); // the one box has no Global node
  assert.match(settingTabNote(tabNamed(x, NODE, "aim"), "map", false) ?? "", /\(a deleted one falls back to the default\)$/);
  assert.doesNotMatch(settingTabNote(tabNamed(x, NODE, "aim"), "map", false) ?? "", /Global/);
  assert.match(settingTabNote(tabNamed(x, NODE, "aim"), "map", true) ?? "", /these replace Global's here/);
  const exit = f("weight_exit");
  assert.match(settingTooltip(exit), /a switch with no flag of its own: weight_home \(go home when the bag is over\) is used only while it is on/);
  assert.doesNotMatch(settingTooltip(exit), /a switch for the settings it needs/);
  // the two that read as fragments once fly_below left the box name their subject
  assert.equal(f("fly_rate").words, "Fly Wing when HP falls faster than");
  assert.equal(f("fly_rate_below").words, "the Fly Wing's fall rule: only while HP is under");
});
