// The project model in the browser (2026-11-13, docs/planning/project-model.md): one tab of one
// node <-> its blocks, functions with inputs, events as functions, overrides, the Run keys.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";

import { toolbox, toolboxBlocks } from "./blockdefs.ts";
import { tabFromWorkspace, tabToWorkspace, type Workspace } from "./blocks.ts";
import { parseCallArgs, parseParams } from "./expr.ts";
import { canonical, type Stmt } from "./ir.ts";
import {
  call,
  clickAt,
  def,
  globalOf,
  isMapStart,
  keyOfCall,
  newTabName,
  nodeById,
  overriddenBy,
  overridesOn,
  pressKey,
  type Project,
  resolve,
  roleKeyOf,
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
  assert.deepEqual(n.tabs.map((t) => t.name), ["main", "keys", "survival", "knife", "exits"]);
  assert.deepEqual(n.tabs[0].main?.map((s) => (s.kind === "action" ? s.block : s.kind)), ["assert_save_point", "dungeon_hunt", "stop"]);
  // stage 2 (live-blocks.md 3.2): the survival tab is two EVENTS, each calling its key's function
  const ev = tabToWorkspace(x, { node: "xmas_dun02", tab: "survival" }).blocks.blocks;
  assert.deepEqual(ev.map((b) => [b.type, b.fields?.NAME, b.fields?.MODE, b.fields?.PRIORITY]), [["pl_event", "drink", "insert", "survival"], ["pl_event", "fly_away", "preempt", "critical"], ["pl_event", "bag_full", "preempt", "upkeep"]]);
  assert.deepEqual(n.tabs[2].defs.map((d) => [d.name, d.on?.cooldown_s, d.body]), [["drink", 0.7, [call("heal")]], ["fly_away", 3, [call("fly_wing")]], ["bag_full", 0, [{ kind: "stop", reason: "home" }]]]);
  // stage 3 (live-blocks.md 3.3): the weight home fires once a run; the knife swap's two functions
  // call the keys' functions; the way home and the death dialog's two clicks
  assert.equal(n.tabs[2].defs[2].on?.max_per_run, 1);
  assert.deepEqual(n.tabs[3].defs.map((d) => [d.name, d.body]), [["knife_on", [call("wield_knife")]], ["knife_back", [call("wield_damascus")]]]);
  assert.deepEqual(n.tabs[4].defs.map((d) => d.name), ["fly_home", "respawn_button", "respawn_ok"]);
  assert.deepEqual(n.tabs[4].defs[1].body, [clickAt(645, 481, "the death dialog's first button: move to the saved location")]);
  // the runner block shows its five roles, the home one included
  const hunt = tabToWorkspace(x, { node: "xmas_dun02", tab: "main" }).blocks.blocks[0].inputs?.DO?.block?.next?.block;
  assert.equal(hunt?.type, "pl_dungeon_hunt");
  assert.deepEqual(hunt?.fields, { HEAL: "heal", FLY: "fly_wing", KNIFE_ON: "knife_on", KNIFE_BACK: "knife_back", HOME: "fly_home", RESPAWN: "respawn_button", RESPAWN_OK: "respawn_ok" });
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
  const h = m[1];
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

// the flow engine's fixtures (its branch writes them): the browser's ready-made projects ARE them
for (const [name, make] of [["project_xmas_dun02", xmasProject], ["project_sample", sampleProject]] as const) {
  const url = new URL(`./fixtures/${name}.json`, import.meta.url);
  test(`the ready-made project is the engine's fixture ${name}.json`, { skip: !existsSync(url) }, () => {
    assert.equal(canonical(make()), canonical(JSON.parse(readFileSync(url, "utf8"))));
  });
}
