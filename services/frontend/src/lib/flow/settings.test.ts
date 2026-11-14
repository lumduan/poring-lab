// THE SETTING BLOCKS (lib/flow/settings.ts; docs/planning/live-blocks.md section 12; Batt 2026-11-14
// ~15:2x: "there should be no runner [page] ... make them ALL blocks, no hardcoding like this"):
// the registry the engine generated, the one box's setting tabs, the blocks <-> project round trip
// for every kind, the name rule (the map node's block > Global's > the default; a deleted block falls
// back), the checklist from the blocks, and the runner page that went.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";

import { BLOCK_DEFS, categoryOf, DEF_BY_TYPE, settingDef, toolbox } from "./blockdefs.ts";
import { tabFromWorkspace, tabToWorkspace, type Workspace } from "./blocks.ts";
import { canonical, clone } from "./ir.ts";
import { GLOBAL_ID, nodeById, type Project, tab, xmasProject } from "./project.ts";
import {
  nodeSettings,
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
  assert.deepEqual([...SETTING_TABS], ["knife", "survival", "exits", "respawn", "start", "fight", "aim", "loot", "walk", "safety", "loop"]);
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
  assert.deepEqual(n.tabs.map((t) => t.name), ["main", "keys", "survival", "knife", "exits", "monsters", "respawn", "start", "fight", "aim", "loot", "walk", "safety", "loop"]);
  const shown = Object.fromEntries(n.tabs.flatMap((t) => Object.entries(t.vars).map(([k, v]) => [k, [t.name, v.value]])));
  assert.deepEqual(shown, Object.fromEntries(SETTING_BLOCKS.map((s) => [s.var, [s.group, s.default]])));
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
    assert.equal(sets.length, SETTING_BLOCKS.filter((s) => s.group === t).length, t);
    // in the registry's order (the Python view's), one row apart
    assert.deepEqual(sets.map((b) => b.type), SETTING_BLOCKS.filter((s) => s.group === t).map(settingType));
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
  assert.match(settingTooltip(f("potion_below"), "Global's 30 % (tab survival)"), /^potion_below = \.\.\. \(tab survival\): heal at HP under\. 10 % to 90 %, in steps of 5 %; our default 40 %; the runner's --potion-below\. .*Delete this block: Global's 30 % \(tab survival\) applies\.$/);
  assert.match(settingTooltip(f("respawn")), /While it is off: off: after a death she stays where she fell/);
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

test("each setting is a block type of its own; the toolbox offers every one by group", () => {
  for (const s of SETTING_BLOCKS) {
    const d = DEF_BY_TYPE[settingType(s)];
    assert.ok(d && BLOCK_DEFS.includes(d), s.name);
    assert.deepEqual(d, settingDef(s));
    const names = [d.args0, d.args1].flat().filter((a) => a && "name" in a).map((a) => (a as { name: string }).name);
    for (const k of Object.keys(settingFields(s, s.default))) assert.ok(names.includes(k), `${s.name}: ${k}`);
    assert.ok(d.previousStatement === undefined && d.output === undefined, s.name); // a top-level block
    assert.equal(names.includes("WARN"), s.warn !== "", s.name);
  }
  const tb = toolbox({}, { node: "map", main: false, tab: "loot" });
  const set = categoryOf(tb, "Settings");
  assert.ok(set);
  const offered = set.contents.filter((i) => i.kind === "block").map((i) => (i as { type: string }).type);
  assert.equal(offered.length, 121);
  assert.equal(offered[0], settingType(SETTING_BLOCKS.find((s) => s.group === "loot")!)); // the tab's group first
  assert.equal(categoryOf(toolbox({}, { node: "login", main: true }), "Settings"), undefined);
});

test("a settings tab's strip line names its group and the name rule", () => {
  const x = xmasProject();
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
