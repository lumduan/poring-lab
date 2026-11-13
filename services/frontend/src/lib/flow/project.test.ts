// The project model in the browser (2026-11-13, docs/planning/project-model.md): one tab of one
// node <-> its blocks, functions with inputs, events as functions, overrides, the Run keys.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";

import { toolbox, toolboxBlocks } from "./blockdefs.ts";
import { tabFromWorkspace, tabToWorkspace, type Workspace } from "./blocks.ts";
import { parseCallArgs, parseParams } from "./expr.ts";
import { canonical } from "./ir.ts";
import {
  call,
  def,
  globalOf,
  keyOfCall,
  newTabName,
  nodeById,
  overriddenBy,
  overridesOn,
  pressKey,
  type Project,
  resolve,
  runnerKeysOn,
  sampleProject,
  tab,
  tabNameProblem,
  xmasProject,
} from "./project.ts";
import { exportProject, importProject } from "./projectfile.ts";

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
  for (const p of [xmasProject(), sampleProject()]) roundTrip(p);
  const x = xmasProject();
  assert.deepEqual(x.nodes.map((n) => `${n.id}:${n.kind}`), ["login:login", "character:character", "xmas_dun02:map", "geffen:map", "global:global"]);
  assert.deepEqual(globalOf(x)?.tabs.map((t) => t.name), ["keys", "safety"]);
  assert.ok(x.nodes.filter((n) => n.kind !== "global").every((n) => n.tabs[0].name === "main" && n.tabs[0].main !== null));
});

test("the blocks a person sees: the login sentence, a function hat with its inputs, an event, a call with inputs", () => {
  const x = xmasProject();
  const login = tabToWorkspace(x, { node: "login", tab: "main" }).blocks.blocks[0].inputs?.DO?.block;
  assert.equal(login?.type, "pl_login");
  assert.deepEqual(login?.fields, { SERVER: "lab-rathena", CREDENTIAL: "lab_gm" });
  const keys = tabToWorkspace(x, { node: "global", tab: "keys" }).blocks.blocks;
  assert.ok(keys.every((b) => b.type === "pl_def"));
  const safety = tabToWorkspace(x, { node: "global", tab: "safety" }).blocks.blocks;
  assert.equal(safety[0].type, "pl_event");
  assert.equal(safety[0].fields?.SCOPE, "every node");
  // a function with inputs, defaults, *args and **kwargs, called with positional and keyword inputs
  const p = xmasProject();
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
  const p = xmasProject();
  assert.equal(resolve(p, "xmas_dun02", "heal")?.from, "global");
  nodeById(p, "xmas_dun02")!.tabs.push(tab("mine", [def("heal", [pressKey("F2")])]));
  assert.equal(resolve(p, "xmas_dun02", "heal")?.from, "node");
  assert.equal(resolve(p, "geffen", "heal")?.from, "global");
  assert.deepEqual(overridesOn(p, "xmas_dun02"), ["heal"]);
  assert.deepEqual(overriddenBy(p, "heal"), ["xmas_dun02"]);
  roundTrip(p);
});

test("the Run keys: resolved on THAT node (its override first), through calls with plain inputs", () => {
  const p = xmasProject();
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
  // a role function of two presses: refused in words
  g.tabs[0].defs[3] = def("knife_on", [pressKey("F4"), pressKey("F3")]);
  const r3 = runnerKeysOn(p, "xmas_dun02");
  assert.equal(r3.ok, false);
  assert.match(r3.ok ? "" : r3.problems.join(" "), /knife_on\(\) must be exactly one "press key"/);
});

test("tab names are Python module names; a new tab is tab2, tab3 ...", () => {
  const n = globalOf(xmasProject())!;
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
