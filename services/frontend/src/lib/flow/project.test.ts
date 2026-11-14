// The project model in the browser (2026-11-13, docs/planning/project-model.md): one tab of one
// node <-> its blocks, functions with inputs, events as functions, overrides, the Run keys.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";

import { categoryOf, toolbox, toolboxBlocks } from "./blockdefs.ts";
import { tabFromWorkspace, tabToWorkspace, type Workspace } from "./blocks.ts";
import { parseCallArgs, parseParams } from "./expr.ts";
import { canonical, type Stmt } from "./ir.ts";
import {
  call,
  clickAt,
  def,
  globalOf,
  hotbarCount,
  isMapStart,
  keyOfCall,
  mapNodes,
  modelOn,
  MONSTERS_TAB,
  newTabName,
  nodeById,
  overriddenBy,
  overridesOn,
  pressKey,
  pressKeyOf,
  type Project,
  resolve,
  roleKeyOf,
  recipeDef,
  runnerKeysOn,
  sampleProject,
  sessionPath,
  startMap,
  tab,
  tabNameProblem,
  xmasProject,
} from "./project.ts";
import { exportProject, importProject } from "./projectfile.ts";
import { sessionProject } from "./testkit.ts";

type WsBlock = Workspace["blocks"]["blocks"][number];
/** The first block of a type anywhere in a workspace's blocks (statement inputs, values, next). */
function findBlock(blocks: readonly WsBlock[], type: string): WsBlock | undefined {
  for (const b of blocks) {
    if (b.type === type) return b;
    const kids = [...Object.values(b.inputs ?? {}).map((i) => i.block), b.next?.block].filter((x): x is WsBlock => !!x);
    const hit = findBlock(kids, type);
    if (hit) return hit;
  }
  return undefined;
}

const roundTrip = (p: Project) => {
  for (const n of p.nodes) {
    for (const t of n.tabs) {
      const scope = { node: n.id, tab: t.name };
      const ws = JSON.parse(JSON.stringify(tabToWorkspace(p, scope))) as Workspace;
      const back = tabFromWorkspace(p, scope, ws);
      assert.ok(back.ok, `${n.id}/${t.name}: ${back.ok ? "" : back.errors.join(" | ")}`);
      assert.equal(canonical(back.project), canonical(p), `${n.id}/${t.name}`);
    }
  }
};

test("the ready-made projects: every tab of every node round-trips through its blocks", () => {
  for (const p of [xmasProject(), sampleProject(), sessionProject()]) roundTrip(p);
  const s = sessionProject();
  assert.deepEqual(s.nodes.map((n) => `${n.id}:${n.kind}`), ["login:login", "character:character", "xmas_dun02:map", "geffen:map", "global:global"]);
  assert.deepEqual(globalOf(s)?.tabs.map((t) => t.name), ["keys", "safety"]);
  assert.ok(s.nodes.filter((n) => n.kind !== "global").every((n) => n.tabs[0].name === "main" && n.tabs[0].main !== null));
});

test("the ONE BOX (Batt 2026-11-13: START > map xmas_dun02): one map node, its main and keys, no session", () => {
  const x = xmasProject();
  assert.deepEqual(x.nodes.map((n) => `${n.id}:${n.kind}`), ["xmas_dun02:map"]);
  assert.equal(x.start, "xmas_dun02");
  assert.deepEqual(x.edges, []);
  const n = nodeById(x, "xmas_dun02")!;
  assert.deepEqual(n.tabs.map((t) => t.name), ["main", "keys", "survival", "knife", "exits", "monsters"]);
  // stage 4a (live-blocks.md 3.4): the trained data before the runner
  assert.deepEqual(n.tabs[0].main?.map((s) => (s.kind === "action" ? s.block : s.kind)), ["assert_save_point", "use_model", "dungeon_hunt", "stop"]);
  // stage 2 (live-blocks.md 3.2): the survival tab is two EVENTS, each calling its key's function
  const ev = tabToWorkspace(x, { node: "xmas_dun02", tab: "survival" }).blocks.blocks;
  assert.deepEqual(ev.map((b) => [b.type, b.fields?.NAME, b.fields?.MODE, b.fields?.PRIORITY]), [["pl_event", "drink", "insert", "survival"], ["pl_event", "fly_away", "preempt", "critical"], ["pl_event", "bag_full", "preempt", "upkeep"], ["pl_event", "eat_cane", "insert", "upkeep"], ["pl_event", "eat_candy", "insert", "upkeep"]]);
  assert.deepEqual(n.tabs[2].defs.map((d) => [d.name, d.on?.cooldown_s, d.body]), [["drink", 0.7, [call("heal")]], ["fly_away", 3, [call("fly_wing")]], ["bag_full", 0, [{ kind: "stop", reason: "home" }]], ["eat_cane", 1.5, [call("candy_cane")]], ["eat_candy", 1.5, [call("candy")]]]);
  // Batt 2026-11-14 (live-blocks.md 10): the drink under 50 % (it was 30 %), and each candy eaten the
  // moment its slot shows one (hotbar_count), until the slot reads empty, at any HP
  assert.deepEqual(n.tabs[2].defs[0].on?.when, { kind: "cmp", op: "<", left: { kind: "sense", sensor: "hp_percent", args: {} }, right: { kind: "lit", value: 50 } });
  assert.deepEqual(n.tabs[2].defs[3].on?.when, { kind: "cmp", op: ">", left: hotbarCount("F6"), right: { kind: "lit", value: 0 } });
  assert.deepEqual([n.tabs[2].defs[3].on?.max_fires_per_10min, n.tabs[2].defs[3].on?.rank, n.tabs[2].defs[4].on?.rank], [30, 51, 52]);
  // the keys tab: eat(key) presses its input; the two items' functions give it the lab Rogue's slots
  assert.deepEqual(n.tabs[1].defs.slice(5).map((d) => [d.name, d.params.map((q) => q.name), d.body]), [["eat", ["key"], [pressKeyOf("key")]], ["candy_cane", [], [call("eat", [{ kind: "lit", value: "F6" }])]], ["candy", [], [call("eat", [{ kind: "lit", value: "F7" }])]]]);
  // stage 3 (live-blocks.md 3.3): the weight home fires once a run; the knife swap's two functions
  // call the keys' functions; the way home and the death dialog's two clicks
  assert.equal(n.tabs[2].defs[2].on?.max_per_run, 1);
  assert.deepEqual(n.tabs[3].defs.map((d) => [d.name, d.body]), [["knife_on", [call("wield_knife")]], ["knife_back", [call("wield_damascus")]]]);
  assert.deepEqual(n.tabs[4].defs.map((d) => d.name), ["fly_home", "respawn_button", "respawn_ok"]);
  assert.deepEqual(n.tabs[4].defs[1].body, [clickAt(645, 481, "the death dialog's first button: move to the saved location")]);
  // the runner block shows its five roles, the home one included
  const use = tabToWorkspace(x, { node: "xmas_dun02", tab: "main" }).blocks.blocks[0].inputs?.DO?.block?.next?.block;
  assert.deepEqual([use?.type, use?.fields?.BLOCK, use?.fields?.ARGS], ["pl_action", "use_model", 'model="xmas02"']);
  const hunt = use?.next?.block;
  assert.equal(hunt?.type, "pl_dungeon_hunt");
  assert.deepEqual(hunt?.fields, { HEAL: "heal", FLY: "fly_wing", KNIFE_ON: "knife_on", KNIFE_BACK: "knife_back", HOME: "fly_home", RESPAWN: "respawn_button", RESPAWN_OK: "respawn_ok", EAT: "eat" });
  // the start is the map: no login, no character, its first entry
  const sp = sessionPath(x);
  assert.deepEqual([sp.login, sp.character, sp.map?.id, sp.entry, sp.problems], [null, null, "xmas_dun02", "here", []]);
  assert.equal(startMap(x)?.id, "xmas_dun02");
  assert.ok(isMapStart(x) && !isMapStart(sessionProject()));
  // the Run keys: home from the runner block's home role (no item warp on the one box)
  const r = runnerKeysOn(x, "xmas_dun02");
  assert.ok(r.ok);
  assert.deepEqual(r.keys, { heal_key: "F1", fly_key: "F8", home_key: "F9", knife_key: "F4", dagger_key: "F5" });
  assert.equal(r.from.home_key, "fly_home");
});

test("stage 3: a knife function of presses and waits gives Run its FIRST press (both answers to the open question)", () => {
  const x = xmasProject();
  const n = nodeById(x, "xmas_dun02")!;
  const knife = n.tabs.find((t) => t.name === "knife")!;
  const wait: Stmt = { kind: "wait_until", cond: { kind: "lit", value: false }, timeout_s: 0.1, outcome_to: null };
  knife.defs[0].body = [call("wield_knife"), wait, call("wield_damascus")]; // "F4, wait 100 ms, F5"
  const r = runnerKeysOn(x, "xmas_dun02");
  assert.ok(r.ok);
  assert.deepEqual([r.keys.knife_key, r.keys.dagger_key], ["F4", "F5"]);
  assert.deepEqual(roleKeyOf(x, "xmas_dun02", "knife_on", "knife_on"), { key: "F4" });
  // the heal role stays ONE key: a body there is not a key
  assert.ok("why" in roleKeyOf(x, "xmas_dun02", "knife_on", "heal"));
  roundTrip(x);
});

test("a runner block of four roles: an empty home field; with neither a home role nor an item warp Run says so", () => {
  const s = sessionProject();
  const hunt = findBlock(tabToWorkspace(s, { node: "xmas_dun02", tab: "main" }).blocks.blocks, "pl_dungeon_hunt"); // in the while loop
  assert.equal(hunt?.type, "pl_dungeon_hunt");
  assert.equal(hunt?.fields?.HOME, "");
  const x = xmasProject();
  const m = nodeById(x, "xmas_dun02")!.tabs[0].main!;
  const h = m.find((st) => st.kind === "action" && st.block === "dungeon_hunt")!;
  assert.ok(h.kind === "action");
  delete h.params.home;
  roundTrip(x); // four roles: the empty field round-trips as no home role
  const r = runnerKeysOn(x, "xmas_dun02");
  assert.equal(r.ok, false);
  assert.match(r.ok ? "" : r.problems.join(" "), /the way home: the runner block's "home \(Butterfly Wing\): call \.\.\." is empty/);
});

test("the blocks a person sees: the login sentence, a function hat with its inputs, an event, a call with inputs", () => {
  const x = sessionProject();
  const login = tabToWorkspace(x, { node: "login", tab: "main" }).blocks.blocks[0].inputs?.DO?.block;
  assert.equal(login?.type, "pl_login");
  assert.deepEqual(login?.fields, { SERVER: "lab-rathena", CREDENTIAL: "lab_gm" });
  const keys = tabToWorkspace(x, { node: "global", tab: "keys" }).blocks.blocks;
  assert.ok(keys.every((b) => b.type === "pl_def"));
  const safety = tabToWorkspace(x, { node: "global", tab: "safety" }).blocks.blocks;
  assert.equal(safety[0].type, "pl_event");
  assert.equal(safety[0].fields?.SCOPE, "every node");
  // a function with inputs, defaults, *args and **kwargs, called with positional and keyword inputs
  const p = sessionProject();
  const g = globalOf(p)!;
  g.tabs.push(tab("helpers", [def("use_hotkey", [pressKey("F1")], { params: [{ name: "key", default: null }, { name: "times", default: { kind: "lit", value: 1 } }], varargs: "rest", kwargs: "opts" })]));
  g.tabs[0].defs[1] = def("fly_wing", [call("use_hotkey", [{ kind: "lit", value: "F8" }], { times: { kind: "lit", value: 2 } })]);
  roundTrip(p);
  const h = tabToWorkspace(p, { node: "global", tab: "helpers" }).blocks.blocks[0];
  assert.equal(h.fields?.PARAMS, "key, times=1, *rest, **opts");
  const fly = tabToWorkspace(p, { node: "global", tab: "keys" }).blocks.blocks[1].inputs?.DO?.block;
  assert.deepEqual(fly?.fields, { PROC: "use_hotkey", ARGS: '"F8", times=2' });
});

test("names: a node's own definition first, then Global's, and the marks both ways", () => {
  const p = sessionProject();
  assert.equal(resolve(p, "xmas_dun02", "heal")?.from, "global");
  nodeById(p, "xmas_dun02")!.tabs.push(tab("mine", [def("heal", [pressKey("F2")])]));
  assert.equal(resolve(p, "xmas_dun02", "heal")?.from, "node");
  assert.equal(resolve(p, "geffen", "heal")?.from, "global");
  assert.deepEqual(overridesOn(p, "xmas_dun02"), ["heal"]);
  assert.deepEqual(overriddenBy(p, "heal"), ["xmas_dun02"]);
  roundTrip(p);
});

test("the Run keys: resolved on THAT node (its override first), through calls with plain inputs", () => {
  const p = sessionProject();
  const r = runnerKeysOn(p, "xmas_dun02");
  assert.ok(r.ok);
  assert.deepEqual(r.keys, { heal_key: "F1", fly_key: "F8", home_key: "F9", knife_key: "F4", dagger_key: "F5" });
  // the map's own fly_wing on F6 wins there
  nodeById(p, "xmas_dun02")!.tabs.push(tab("mine", [def("fly_wing", [pressKey("F6")])]));
  const r2 = runnerKeysOn(p, "xmas_dun02");
  assert.ok(r2.ok && r2.keys.fly_key === "F6");
  // through a helper with an input: use_hotkey("F7") -> press_key(key)
  const g = globalOf(p)!;
  g.tabs.push(tab("helpers", [def("use_hotkey", [{ kind: "action", block: "press_key", concept: "ui.press_hotkey", timeout_s: 2, on_fail: "stop", outcome_to: null, note: null, params: { key: { kind: "var", name: "key" } } }], { params: [{ name: "key", default: null }] })]));
  g.tabs[0].defs[0] = def("heal", [call("use_hotkey", [{ kind: "lit", value: "F7" }])]);
  assert.deepEqual(keyOfCall(p, "xmas_dun02", "heal"), { key: "F7" });
  roundTrip(p); // the key as a value (press key <input>) round-trips through its block (matpilot round 15 #2)
  const helper = tabToWorkspace(p, { node: "global", tab: "helpers" }).blocks.blocks[0].inputs?.DO?.block;
  assert.equal(helper?.type, "pl_press_key_v");
  // stage 3 (live-blocks.md 3.3): a knife role function of two presses is a BODY the hunt core
  // calls; Run takes its first press (its other keys are checked by the lint and the run check)
  g.tabs[0].defs[3] = def("knife_on", [pressKey("F4"), pressKey("F3")]);
  const r3 = runnerKeysOn(p, "xmas_dun02");
  assert.ok(r3.ok && r3.keys.knife_key === "F4");
  // the heal role stays ONE key: two presses there are refused in words
  g.tabs[0].defs[0] = def("heal", [pressKey("F1"), pressKey("F3")]);
  const r4 = runnerKeysOn(p, "xmas_dun02");
  assert.equal(r4.ok, false);
  assert.match(r4.ok ? "" : r4.problems.join(" "), /heal\(\) must be exactly one "press key"/);
});

test("tab names are Python module names; a new tab is tab2, tab3 ...", () => {
  const n = globalOf(sessionProject())!;
  assert.equal(tabNameProblem(n, "npc"), null);
  assert.match(tabNameProblem(n, "keys") ?? "", /has a tab/);
  assert.match(tabNameProblem(n, "Main") ?? "", /lower-case/);
  assert.match(tabNameProblem(n, "import") ?? "", /Python/);
  assert.match(tabNameProblem(n, "heal") ?? "", /function or variable/);
  assert.equal(newTabName(n), "tab2");
});

test("inputs as Python writes them: parsed, and refused in words", () => {
  assert.deepEqual(parseParams("key, times=1, *rest, **opts"), { params: [{ name: "key", default: null }, { name: "times", default: { kind: "lit", value: 1 } }], varargs: "rest", kwargs: "opts" });
  assert.throws(() => parseParams("a=1, b"), /needs a default/);
  assert.throws(() => parseParams("**k, a"), /comes last/);
  assert.throws(() => parseParams("a, a"), /twice/);
  assert.deepEqual(parseCallArgs('"F8", times=2'), { args: [{ kind: "lit", value: "F8" }], kwargs: { times: { kind: "lit", value: 2 } } });
  assert.deepEqual(parseCallArgs(""), { args: [], kwargs: {} });
});

test("a project file: written and read back; an old flow is refused in words", () => {
  const p = xmasProject();
  const r = importProject(exportProject(p));
  assert.ok(r.ok && canonical(r.project) === canonical(p));
  const old = importProject(JSON.stringify({ ir: 2, name: "x" }));
  assert.equal(old.ok, false);
  assert.match(old.ok ? "" : old.errors[0], /OLD format/);
});

test("the toolbox: exits and the runner on map tabs, the login sentence on a login node only", () => {
  const cat = { press_key: { concept: "ui.press_hotkey", timeout_s: 2 }, dungeon_hunt: { concept: "combat.hunt", timeout_s: 600 }, login: { concept: "session.login", timeout_s: 60 }, choose_character: { concept: "session.select_char", timeout_s: 30 } };
  const types = (node: "login" | "character" | "map" | "global") => toolboxBlocks(toolbox(cat, { node, main: node !== "global" })).map((e) => e.item.type);
  assert.ok(types("login").includes("pl_login") && !types("map").includes("pl_login"));
  assert.ok(types("character").includes("pl_choose_character"));
  assert.ok(types("map").includes("pl_dungeon_hunt") && !types("global").includes("pl_dungeon_hunt"));
  for (const n of ["login", "character", "map", "global"] as const) assert.ok(types(n).includes("pl_def") && types(n).includes("pl_event") && types(n).includes("pl_vardecl"));
});

// stage 4a (live-blocks.md 3.4): the trained data in a map's main, the monsters tab's recipes
test("the toolbox offers use_model in a map's main and a monster's recipe in its monsters tab", () => {
  const core = { concept: "core.x", timeout_s: 1 };
  const cat = { press_key: { concept: "ui.press_hotkey", timeout_s: 2 }, dungeon_hunt: { concept: "combat.hunt", timeout_s: 600 }, use_model: core, strike: { concept: "combat.attack_target", timeout_s: 60 }, wait_steal: core, wait_kill: core, loot: { concept: "loot.pick_up", timeout_s: 30 }, use_skill: { concept: "combat.use_skill", timeout_s: 30 }, sit: { concept: "char.sit", timeout_s: 5 } };
  const monsters = { model: "xmas02", strikes: ["mystcase", "cookie"], mobs: { mystcase: [1249], cookie: [1265] } };
  const items = (scope: { node: "map" | "global"; main: boolean; tab?: string }) => toolboxBlocks(toolbox(cat, scope, null, {}, undefined, monsters));
  const main = items({ node: "map", main: true, tab: "main" });
  const use = main.find((e) => e.item.type === "pl_action" && e.item.fields?.BLOCK === "use_model");
  assert.ok(use && use.category === "Movement" && use.item.fields?.ARGS === 'model="xmas02"');
  // the primitives play only inside a recipe: never under "More skills", nowhere but the monsters tab
  const more = main.filter((e) => e.category === "More skills").map((e) => e.item.fields?.BLOCK);
  for (const b of ["strike", "wait_steal", "wait_kill", "loot", "use_skill", "use_model"]) assert.ok(!more.includes(b), b);
  assert.ok(more.includes("sit"));
  assert.equal(categoryOf(toolbox(cat, { node: "map", main: true, tab: "main" }, null, {}, undefined, monsters), "Monsters"), undefined);
  const mon = toolbox(cat, { node: "map", main: false, tab: MONSTERS_TAB }, null, {}, undefined, monsters);
  const blocksOf = (tb: ReturnType<typeof toolbox>) => (categoryOf(tb, "Monsters")?.contents ?? []).flatMap((i) => (i.kind === "block" ? [i] : []));
  const got = blocksOf(mon).map((i) => [i.type, i.fields?.NAME ?? i.fields?.BLOCK ?? i.fields?.PROC ?? i.fields?.TEXT, i.fields?.ARGS ?? i.fields?.PARAMS ?? null]);
  assert.deepEqual(got, [
    ["pl_def", "attack_mystcase", "t, priority=1"],
    ["pl_def", "attack_cookie", "t, priority=1"],
    ["pl_expr", "mob(1249)", null],
    ["pl_expr", "mob(1265)", null],
    ["pl_call", "knife_on", ""],
    ["pl_action", "strike", "target=t"],
    ["pl_action", "wait_steal", "target=t"],
    ["pl_call", "knife_back", ""],
    ["pl_action", "wait_kill", "target=t"],
    ["pl_action", "loot", "target=t"],
    ["pl_action", "use_skill", 'key="F6"'],
  ]);
  // no model named yet: the steps, and a word about use_model
  const none = toolbox(cat, { node: "map", main: false, tab: MONSTERS_TAB });
  assert.ok(blocksOf(none).length > 0 && blocksOf(none).every((i) => i.type !== "pl_def"));
});

test("the one box names xmas02 and writes today's technique for each monster", () => {
  const p = xmasProject();
  const [n] = mapNodes(p);
  assert.equal(modelOn(n), "xmas02");
  assert.equal(modelOn(sampleProject().nodes[0]), null);
  const mon = n.tabs.find((t) => t.name === MONSTERS_TAB)!;
  assert.deepEqual(mon.defs.map((d) => d.name), ["attack_mystcase", "attack_cruiser", "attack_cookie", "attack_cookie_xmas"]);
  assert.deepEqual(mon.defs[0], recipeDef("mystcase"));
  assert.deepEqual(mon.defs[0].body.map((s) => (s.kind === "call" ? `${s.proc}()` : s.kind === "action" ? s.block : s.kind)), ["knife_on()", "strike", "wait_steal", "knife_back()", "wait_kill", "loot"]);
  assert.deepEqual(recipeDef("cookie", false, null).body.map((s) => (s.kind === "action" ? s.block : s.kind)), ["strike", "wait_kill", "loot"]);
  assert.deepEqual(recipeDef("cookie", false, null).params, [{ name: "t", default: null }]);
});

// the flow engine's fixtures (its branch writes them): the browser's ready-made projects ARE them
for (const [name, make] of [["project_xmas_dun02", xmasProject], ["project_sample", sampleProject]] as const) {
  const url = new URL(`./fixtures/${name}.json`, import.meta.url);
  test(`the ready-made project is the engine's fixture ${name}.json`, { skip: !existsSync(url) }, () => {
    assert.equal(canonical(make()), canonical(JSON.parse(readFileSync(url, "utf8"))));
  });
}

// matpilot round 17 N4: the survival events' Python says cooldown_s=0.7 (drink), cooldown_s=3
// (fly_away), max_per_run=1 (bag_full), and no field on their blocks showed them; the blocks were
// 1022-1102 px wide on a 1008 px canvas (every row on one line)
test("an event block shows every trigger field the Python writes, and edits round-trip", () => {
  const x = xmasProject();
  const scope = { node: "xmas_dun02", tab: "survival" };
  const ws = JSON.parse(JSON.stringify(tabToWorkspace(x, scope))) as Workspace;
  const ev = ws.blocks.blocks;
  const lim = (b: (typeof ev)[number]) => [b.fields?.NAME, b.fields?.COOLDOWN, b.fields?.MAX_RUN, b.fields?.MAX_MIN, b.fields?.MAX_10, b.fields?.FAILS, b.fields?.ESCALATE];
  assert.deepEqual(ev.map(lim), [
    ["drink", 0.7, "", "", "", "", ""],
    ["fly_away", 3, "", "", "", "", ""],
    ["bag_full", 0, "1", "", "", "", ""],
    ["eat_cane", 1.5, "", "", "30", "", ""],
    ["eat_candy", 1.5, "", "", "30", "", ""],
  ]);
  // matpilot round 18 #3: 10 and 3 are the engine's defaults (the Python view omits them): the
  // block leaves their fields empty and its rows name the defaults, so the block and the Python agree
  // nothing rides hidden any more: the fields are the whole trigger
  for (const b of ev) assert.equal(JSON.stringify(b.extraState).includes("cooldown"), false);
  // the round trip is exact: the fixture's canonical bytes do not change
  const back = tabFromWorkspace(x, scope, ws);
  assert.ok(back.ok);
  if (!back.ok) return;
  const url = new URL("./fixtures/project_xmas_dun02.json", import.meta.url);
  assert.equal(canonical(back.project), canonical(JSON.parse(readFileSync(url, "utf8"))));
  // a person edits them on the block
  ev[0].fields = { ...ev[0].fields, COOLDOWN: 1.5, MAX_RUN: "4", MAX_MIN: "6", MAX_10: "20", FAILS: "2", ESCALATE: "heal" };
  const ed = tabFromWorkspace(x, scope, ws);
  assert.ok(ed.ok, ed.ok ? "" : ed.errors.join("; "));
  if (!ed.ok) return;
  const on = nodeById(ed.project, "xmas_dun02")!.tabs[2].defs[0].on!;
  assert.deepEqual([on.cooldown_s, on.max_per_run, on.max_per_min, on.max_fires_per_10min, on.max_insert_fails, on.escalate], [1.5, 4, 6, 20, 2, "heal"]);
  // a value off its range is refused in words, with nothing applied
  for (const [f, v, words] of [["MAX_RUN", "0", /at most … a run "0": a whole number 1\.\.100, or empty for no limit/], ["MAX_MIN", "x", /at most … a minute "x"/], ["FAILS", "11", /an insert's failures "11": a whole number 1\.\.10, or empty for the default 3/], ["MAX_10", "0", /… per 10 minutes "0": a whole number 1\.\.100, or empty for the default 10/], ["COOLDOWN", -1, /the pause after each run "-1": a number 0\.\.3600/], ["ESCALATE", "no way", /escalate "no way" is not a valid name/]] as const) {
    const bad = JSON.parse(JSON.stringify(tabToWorkspace(x, scope))) as Workspace;
    bad.blocks.blocks[0].fields = { ...bad.blocks.blocks[0].fields, [f]: v };
    const r = tabFromWorkspace(x, scope, bad);
    assert.equal(r.ok, false, f);
    if (!r.ok) assert.match(r.errors.join("; "), words, f);
  }
  // a block from the toolbox (no limit fields yet): the IR's defaults
  const fresh = JSON.parse(JSON.stringify(tabToWorkspace(x, scope))) as Workspace;
  for (const k of ["COOLDOWN", "MAX_RUN", "MAX_MIN", "MAX_10", "FAILS", "ESCALATE"]) delete fresh.blocks.blocks[2].fields![k];
  const fr = tabFromWorkspace(x, scope, fresh);
  assert.ok(fr.ok);
  if (fr.ok) assert.equal(nodeById(fr.project, "xmas_dun02")!.tabs[2].defs[2].on!.max_per_run, null);
});

test("the event block puts its inputs on rows of their own (narrow enough for a 1008 px canvas)", async () => {
  const { DEF_BY_TYPE } = await import("./blockdefs.ts");
  const d = DEF_BY_TYPE.pl_event;
  // zelos starts a row at every input only when the block is not inline (isMultiRow)
  assert.equal(d.inputsInline, false);
  const rows = [d.message0, d.message1, d.message2, d.message3, d.message4, d.message5, d.message6, d.message7, d.message8];
  assert.deepEqual(rows, ["%1 when %2", "event %1 class %2 rank %3", "mode %1 then %2", "until %1", "rearm %1", "pause %1 s after each run · at most %2 a run", "at most %1 a minute · %2 per 10 min (default 10)", "%1 failed inserts (default 3): escalate to %2", "do %1"]);
  // no row holds two value inputs (an expression each): a row is never two conditions wide
  for (const args of [d.args0, d.args1, d.args2, d.args3, d.args4, d.args5, d.args6, d.args7, d.args8]) {
    assert.ok((args ?? []).filter((a) => a.type === "input_value").length <= 1);
  }
  // the longest row's own words (without its fields) stay short
  assert.ok(Math.max(...rows.map((r) => (r ?? "").replace(/%\d/g, "").length)) <= 45);
});

// matpilot round 18 #3: the defaults the event block names are the engine's own (poring_flow's
// Trigger and Handler), and a default written by hand comes back as the default (empty field)
const ENGINE = new URL("../../../../../packages/poring_flow/src/poring_flow/", import.meta.url);
test("the event block's defaults are the engine's (its Trigger, its Handler, and what the Python view omits)", { skip: !existsSync(new URL("pyview.py", ENGINE)) }, async () => {
  const { DEFAULT_FAILS, DEFAULT_MAX_10 } = await import("./blockdefs.ts");
  for (const f of ["project.py", "ir.py"]) {
    const py = readFileSync(new URL(f, ENGINE), "utf8");
    assert.equal(Number(/max_fires_per_10min: int = Field\(default=(\d+)/.exec(py)?.[1]), DEFAULT_MAX_10, f);
    assert.equal(Number(/max_insert_fails: int = Field\(default=(\d+)/.exec(py)?.[1]), DEFAULT_FAILS, f);
  }
  // the Python view omits them at their defaults: the block's empty field says the same
  const pyview = readFileSync(new URL("pyview.py", ENGINE), "utf8");
  assert.match(pyview, new RegExp(`if h\\.max_insert_fails != ${DEFAULT_FAILS}:`));
  assert.match(pyview, new RegExp(`if h\\.max_fires_per_10min != ${DEFAULT_MAX_10}:`));
});

test("the event block's runaway guard and insert failure limit show the engine's defaults, empty when unset", () => {
  const x = xmasProject();
  const scope = { node: "xmas_dun02", tab: "survival" };
  const ws = JSON.parse(JSON.stringify(tabToWorkspace(x, scope))) as Workspace;
  // a person types the default itself, or a workspace saved with the old number fields: the same IR
  ws.blocks.blocks[0].fields = { ...ws.blocks.blocks[0].fields, MAX_10: "10", FAILS: 3 };
  const r = tabFromWorkspace(x, scope, ws);
  assert.ok(r.ok);
  if (!r.ok) return;
  const url = new URL("./fixtures/project_xmas_dun02.json", import.meta.url);
  assert.equal(canonical(r.project), canonical(JSON.parse(readFileSync(url, "utf8"))));
  // and back on the block it is a default again (an empty field), never a value a person wrote
  const again = tabToWorkspace(r.project, scope).blocks.blocks[0];
  assert.deepEqual([again.fields?.MAX_10, again.fields?.FAILS], ["", ""]);
});

// matpilot round 18 #4: at 390 x 844 the strip (366 x 204) left the blocks 208 px of 416, and
// Blockly's zoom controls and trashcan (a column 209 px tall from the bottom) sat over drink's
// class and "resume ▾" fields. Folded to one line the strip leaves ~380 px: the first rows clear
test("on a phone the folded strip leaves the tab's first rows clear of Blockly's bottom-right controls", async () => {
  const { FIRST_ROWS_Y, TAB_TOP_Y } = await import("./blocks.ts");
  const { BLOCKLY_CONTROLS, controlsTop, PHONE_START_SCALE } = await import("./theme.ts");
  assert.equal(controlsTop(208), -1); // the measured column: 20 + 60 + 20 + 109 = 209 px
  assert.equal(BLOCKLY_CONTROLS.zoomH, 109);
  const rowsEnd = (TAB_TOP_Y + FIRST_ROWS_Y) * PHONE_START_SCALE; // px from the area's top
  const css = readFileSync(new URL("../../components/flows/studio.css", import.meta.url), "utf8");
  const rem = (prop: string) => Number(new RegExp(`\\.map-binding \\{[^}]*${prop}: ([0-9.]+)rem`).exec(css)?.[1]);
  const pad = /\.map-binding \{[^}]*padding: ([0-9.]+)rem/.exec(css);
  assert.ok(pad, "the strip's padding");
  const line = rem("font-size") * 16 * Number(/\.map-binding \{[^}]*line-height: ([0-9.]+)/.exec(css)?.[1]);
  const folded = 2 * Number(pad[1]) * 16 + line + 2 * 0.15 * 16 + 1; // padding, one line, the toggle's padding, the border
  const area = 416 - folded;
  assert.ok(area > 370 && area < 390, String(area));
  assert.ok(rowsEnd <= controlsTop(area), `rows end ${rowsEnd} px > controls at ${controlsTop(area)} px`);
  // the positive case: the strip unfolded (204 px) still fails the same arithmetic
  assert.ok(rowsEnd > controlsTop(416 - 204));
  // and the fold exists on a phone only: the toggle hidden on a wide screen, the parts hidden while folded
  const code = css.replace(/\/\*[\s\S]*?\*\//g, "");
  assert.match(code, /\.map-binding-toggle \{\s*display: none;\s*\}/);
  assert.match(code, /@media \(max-width: 48rem\) \{\s*\.map-binding-toggle \{[^}]*display: block;[\s\S]*?\.map-binding\[data-open="false"\] \.map-binding-part \{\s*display: none;/);
});

test("a tab's first block starts below the Undo / Redo buttons at the studio's start scale", async () => {
  const { TAB_TOP_Y } = await import("./blocks.ts");
  const { INJECT } = await import("./theme.ts");
  const css = readFileSync(new URL("../../components/flows/studio.css", import.meta.url), "utf8");
  const rem = (sel: string, prop: string) => Number(new RegExp(`\\${sel} \\{[^}]*${prop}: ([0-9.]+)rem`).exec(css)?.[1]);
  const band = (rem(".history-buttons", "top") + rem(".history-button", "height")) * 16; // px from the canvas's top
  assert.ok(band > 50 && band < 60, String(band));
  assert.ok(TAB_TOP_Y * INJECT.zoom.startScale >= band, `${TAB_TOP_Y * INJECT.zoom.startScale} px < ${band} px`);
  // matpilot round 18 #4: and at the phone's start scale
  const { PHONE_START_SCALE, injectFor } = await import("./theme.ts");
  assert.ok(TAB_TOP_Y * PHONE_START_SCALE >= band, `${TAB_TOP_Y * PHONE_START_SCALE} px < ${band} px`);
  assert.equal(injectFor(true).zoom.startScale, PHONE_START_SCALE);
  assert.equal(injectFor(false).zoom.startScale, INJECT.zoom.startScale);
  assert.deepEqual({ ...injectFor(true), zoom: null }, { ...INJECT, zoom: null }); // only the scale differs
  for (const tabName of ["main", "survival", "monsters"]) {
    const ws = tabToWorkspace(xmasProject(), { node: "xmas_dun02", tab: tabName });
    assert.equal(Math.min(...ws.blocks.blocks.map((b) => b.y ?? 0)), TAB_TOP_Y, tabName);
  }
});
