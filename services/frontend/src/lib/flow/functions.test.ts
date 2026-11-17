// Live blocks 5c (docs/planning/live-blocks.md 15; Batt 2026-11-15 ~13:0x: "dungeon_hunt.py should be
// blocks the user sees and can edit himself"): the hunt core as FUNCTIONS IN TABS in the browser --
// the ready-made box in its new shape (the engine's fixture project_xmas_dun02_functions.json, byte
// for byte), its ROLE BLOCKS and STEP BLOCKS (rows, pickers, the round trip, the refusals), the
// toolbox's Roles and Tick, the runner block it stands for (the keys, Run's readiness, use_skill's
// keys), and the old shapes unchanged.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { categoryOf, DEF_BY_TYPE, HUNT_LOOP_TAB, namesOf, ROLE_OF_TYPE, roleType, RUNNER_ROLES, TICK_CATEGORY, toolbox, toolboxBlocks } from "./blockdefs.ts";
import { shelfItems, tabFromWorkspace, tabToWorkspace, type Workspace } from "./blocks.ts";
import { canonical } from "./ir.ts";
import { layoutKey, overlaps, rowsOf, shelfWidth, STACK_GAP } from "./layout.ts";
import { reachable } from "./liveready.ts";
import { skillKeysOn } from "./pickers.ts";
import { engineKey, FUNCTIONS_MODEL, homeFunctionOn, HUNT_TAB, huntCoreCallOn, mainOf, mapNodes, MONSTERS_TAB, nodeById, rolesOn, runnerBlockOn, runnerKeysOn, tabOf, tickDef, xmasCookieNoSwapProject, xmasFunctionsCookieNoSwapProject, xmasFunctionsProject, xmasHuntProject, xmasProject } from "./project.ts";
import { SETTING_ROW_BUDGET } from "./settings.ts";
import { sessionProject } from "./testkit.ts";
import { HUNT_CALL, HUNT_ROLES, LOWERED_NOTE, OPTIONAL_STEPS, REQUIRED_ROLES, ROLE_PREFIX, STEP_BLOCKS, STEP_OF_TYPE, stepBlock, stepType, TICK_FN, TICK_STEPS, TICK_TAB } from "./tick.ts";

type WsBlock = Workspace["blocks"]["blocks"][number];
const NODE = "xmas_dun02";
const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
const fixture = () => JSON.parse(readFileSync(new URL("./fixtures/project_xmas_dun02_functions.json", import.meta.url), "utf8"));
const tabOfP = (p: ReturnType<typeof xmasFunctionsProject>, name: string) => mapNodes(p)[0].tabs.find((t) => t.name === name)!;
function all(blocks: readonly WsBlock[]): WsBlock[] {
  const out: WsBlock[] = [];
  for (const b of blocks) {
    out.push(b);
    out.push(...all([...Object.values(b.inputs ?? {}).map((i) => i.block), b.next?.block].filter((x): x is WsBlock => !!x)));
  }
  return out;
}

const CAT: Record<string, { concept: string; timeout_s: number; kind?: string }> = {
  dungeon_hunt: { concept: "combat.hunt", timeout_s: 600 },
  find_target: { concept: "combat.hunt", timeout_s: 120 },
  fight_target: { concept: "combat.attack_target", timeout_s: 300 },
  press_key: { concept: "core.press_key", timeout_s: 1 },
  ...Object.fromEntries(STEP_BLOCKS.map((b) => [b, { concept: "core.tick_step", timeout_s: 1, kind: "core" }])),
};

test("the ready-made box as functions is the engine's fixture, byte for byte: the hunt box with its runner block dissolved", () => {
  const p = xmasFunctionsProject();
  assert.equal(canonical(p), canonical(fixture()));
  const [n] = mapNodes(p);
  const names = n.tabs.map((t) => t.name);
  assert.deepEqual(names.slice(names.indexOf(MONSTERS_TAB), names.indexOf(MONSTERS_TAB) + 3), [MONSTERS_TAB, HUNT_TAB, TICK_TAB]);
  // main: hunt_loop() where the runner block stood
  const hunt = xmasHuntProject();
  const old = mainOf(mapNodes(hunt)[0])!.main!;
  const now = mainOf(n)!.main!;
  const at = old.findIndex((s) => s.kind === "action" && s.block === "dungeon_hunt");
  assert.deepEqual(now[at], { kind: "call", proc: HUNT_CALL, args: [], kwargs: {} });
  // the rest of main is the hunt box's, but its use_model names FUNCTIONS_MODEL (live-blocks 18.15)
  const named = old.map((s) => (s.kind === "action" && s.block === "use_model" ? { ...s, params: { ...s.params, model: { kind: "lit" as const, value: FUNCTIONS_MODEL } } } : s));
  assert.equal(canonical(now.filter((_, i) => i !== at)), canonical(named.filter((_, i) => i !== at)));
  // the role blocks name exactly the runner block's functions; the loop takes t=False
  const runner = old[at];
  assert.ok(runner.kind === "action");
  assert.deepEqual(rolesOn(n), Object.fromEntries(Object.entries(runner.params).map(([k, v]) => [k, v.kind === "lit" ? v.value : null])));
  assert.deepEqual(tabOfP(p, HUNT_TAB).defs[0].params, [{ name: "t", default: { kind: "lit", value: false } }]);
  assert.deepEqual(tabOfP(p, TICK_TAB).defs.map((d) => d.name), [TICK_FN]);
  assert.deepEqual(tabOfP(p, TICK_TAB).defs[0].body.map((s) => (s.kind === "action" ? s.block : s.kind)), [...STEP_BLOCKS]);
  // the old shapes are unchanged: the one box keeps its runner block, no tick tab
  for (const q of [xmasProject(), xmasHuntProject()]) {
    assert.ok(!mapNodes(q)[0].tabs.some((t) => t.name === TICK_TAB));
    assert.equal(runnerBlockOn(mapNodes(q)[0])?.note ?? null, null);
  }
});

test("the tick's table: run()'s 20 steps, three optional, the roles the runner block's", () => {
  assert.equal(TICK_STEPS.length, 20);
  assert.equal(new Set(STEP_BLOCKS).size, 20);
  assert.deepEqual(OPTIONAL_STEPS, ["loot", "ready", "plant"]);
  assert.ok(TICK_STEPS.slice(0, 9).every((t) => t.klass === "safety" && t.owner === ""));
  assert.deepEqual(HUNT_ROLES, RUNNER_ROLES.map((r) => r.param));
  assert.deepEqual(REQUIRED_ROLES, RUNNER_ROLES.filter((r) => !r.optional).map((r) => r.param));
  assert.equal(LOWERED_NOTE, "the hunt core of hunt_loop() (live blocks 5c)");
  assert.equal(HUNT_LOOP_TAB, HUNT_TAB);
});

test("the hunt core stands where main calls hunt_loop(): the runner block it stands for, its keys, its home", () => {
  const p = xmasFunctionsProject();
  const h = xmasHuntProject();
  const [n] = mapNodes(p);
  assert.ok(huntCoreCallOn(n));
  const built = runnerBlockOn(n)!;
  const real = runnerBlockOn(mapNodes(h)[0])!;
  assert.equal(built.note, LOWERED_NOTE);
  assert.equal(canonical(built.params), canonical(real.params));
  assert.equal(canonical(runnerKeysOn(p, NODE)), canonical(runnerKeysOn(h, NODE)));
  assert.equal(homeFunctionOn(n), homeFunctionOn(mapNodes(h)[0]));
  assert.deepEqual(skillKeysOn({ project: p, node: NODE, tab: HUNT_TAB, catalogue: null, maps: null }), ["F1"]);
  // not a hunt core: twice, with an input, nested, or beside the runner block
  const twice = clone(p);
  mainOf(mapNodes(twice)[0])!.main!.splice(2, 0, { kind: "call", proc: HUNT_CALL, args: [], kwargs: {} });
  assert.ok(!huntCoreCallOn(mapNodes(twice)[0]) && runnerBlockOn(mapNodes(twice)[0]) === null);
  const withArg = clone(p);
  const m = mainOf(mapNodes(withArg)[0])!.main!;
  m[2] = { kind: "call", proc: HUNT_CALL, args: [{ kind: "lit", value: false }], kwargs: {} };
  assert.ok(!huntCoreCallOn(mapNodes(withArg)[0]));
  const both = clone(h);
  mainOf(mapNodes(both)[0])!.main!.splice(3, 0, { kind: "call", proc: HUNT_CALL, args: [], kwargs: {} });
  assert.ok(!huntCoreCallOn(mapNodes(both)[0]) && runnerBlockOn(mapNodes(both)[0])?.note === null);
  assert.ok(!huntCoreCallOn(sessionProject().nodes[0]));
});

test("Run's readiness reaches the role functions, the hunt loop and the tick's steps from hunt_loop()", () => {
  const got = reachable(xmasFunctionsProject(), NODE);
  const hunt = reachable(xmasHuntProject(), NODE);
  assert.deepEqual(got.blocks.filter((b) => !STEP_BLOCKS.includes(b)), hunt.blocks);
  for (const b of STEP_BLOCKS) assert.ok(got.blocks.includes(b), b);
  assert.deepEqual(got.exits, hunt.exits);
});

test("the hunt tab shows a role block per role, the tick tab a step block per step; both round-trip exactly", () => {
  const p = xmasFunctionsProject();
  const hunt = clone(tabToWorkspace(p, { node: NODE, tab: HUNT_TAB }));
  const roles = hunt.blocks.blocks.filter((b) => ROLE_OF_TYPE.has(b.type));
  // in the old runner block's order of its rows, also from the fixture (whose keys are sorted)
  const want = RUNNER_ROLES.map((r) => [roleType(r.param), rolesOn(mapNodes(p)[0])[r.param]]);
  assert.deepEqual(roles.map((b) => [b.type, b.fields?.FN]), want);
  const fromFile = tabToWorkspace(fixture(), { node: NODE, tab: HUNT_TAB }).blocks.blocks.filter((b) => ROLE_OF_TYPE.has(b.type));
  assert.deepEqual(fromFile.map((b) => [b.type, b.fields?.FN]), want);
  const tick = clone(tabToWorkspace(p, { node: NODE, tab: TICK_TAB }));
  const def = tick.blocks.blocks[0];
  assert.deepEqual([def.type, def.fields?.NAME, def.fields?.PARAMS], ["pl_def", TICK_FN, ""]);
  assert.deepEqual(all([def]).slice(1).map((b) => b.type), TICK_STEPS.map(stepType));
  // the lint's words land on the step blocks: their ids are the engine's statement paths
  assert.equal(all([def]).find((b) => b.type === "pl_step_ui")?.id, "n:hunt_tick.7");
  for (const [scope, ws] of [[HUNT_TAB, hunt], [TICK_TAB, tick]] as const) {
    for (const b of all(ws.blocks.blocks)) for (const f of Object.keys(b.fields ?? {})) assert.ok(namesOf(b.type).saved.has(f), `${b.type}.${f}`);
    const back = tabFromWorkspace(p, { node: NODE, tab: scope }, ws);
    assert.ok(back.ok, scope);
    if (back.ok) assert.equal(canonical(back.project), canonical(p), scope);
  }
});

test("a role block's edits play, and what cannot stand is refused in words", () => {
  const p = xmasFunctionsProject();
  const scope = { node: NODE, tab: HUNT_TAB };
  const ws = () => clone(tabToWorkspace(p, scope));
  const set = (w: Workspace, param: string, fn: string) => ((w.blocks.blocks.find((b) => b.type === roleType(param))!.fields as Record<string, unknown>).FN = fn);
  // another function: the variable is its name
  const w1 = ws();
  set(w1, "heal", "fly_wing");
  const r1 = tabFromWorkspace(p, scope, w1);
  assert.ok(r1.ok && tabOfP(r1.project, HUNT_TAB).vars[`${ROLE_PREFIX}heal`].value === "fly_wing");
  // an optional role left empty, or its block deleted: no role (as the runner block's empty field)
  const w2 = ws();
  set(w2, "eat", "");
  const r2 = tabFromWorkspace(p, scope, w2);
  assert.ok(r2.ok && !(`${ROLE_PREFIX}eat` in tabOfP(r2.project, HUNT_TAB).vars));
  const w3 = ws();
  w3.blocks.blocks = w3.blocks.blocks.filter((b) => b.type !== roleType("home"));
  const r3 = tabFromWorkspace(p, scope, w3);
  assert.ok(r3.ok && !("home" in rolesOn(mapNodes(r3.project)[0])));
  // a required role left empty, twice, or on two tabs of the node: refused, the role named
  const w4 = ws();
  set(w4, "heal", "");
  const r4 = tabFromWorkspace(p, scope, w4);
  assert.ok(!r4.ok && r4.errors.some((e) => e.includes("the role block heal names the function")));
  const w5 = ws();
  w5.blocks.blocks.push({ ...clone(w5.blocks.blocks.find((b) => b.type === roleType("fly"))!), id: "dup", y: 99999 });
  const r5 = tabFromWorkspace(p, scope, w5);
  assert.ok(!r5.ok && r5.errors.some((e) => e.includes("the role block Fly Wing is on this tab twice")));
  const two = clone(p);
  tabOfP(two, "keys").vars[`${ROLE_PREFIX}fly`] = { kind: "lit", value: "fly_wing" };
  const r6 = tabFromWorkspace(two, scope, clone(tabToWorkspace(two, scope)));
  assert.ok(!r6.ok && r6.errors.some((e) => e.includes("and on the tab keys of xmas_dun02")));
  // a role variable that is not a function's name stays a plain variable block (lossless)
  const odd = clone(p);
  tabOfP(odd, HUNT_TAB).vars[`${ROLE_PREFIX}heal`] = { kind: "lit", value: 5 };
  const ow = tabToWorkspace(odd, scope);
  assert.ok(ow.blocks.blocks.some((b) => b.type === "pl_vardecl" && b.fields?.NAME === `${ROLE_PREFIX}heal`));
  const back = tabFromWorkspace(odd, scope, clone(ow));
  assert.ok(back.ok && canonical(back.project) === canonical(odd));
});

test("a step left out of hunt_tick() leaves the project's tick without it; the steps stay in order", () => {
  const p = xmasFunctionsProject();
  const scope = { node: NODE, tab: TICK_TAB };
  const ws = clone(tabToWorkspace(p, scope));
  // unlink step_loot from the chain (the editor's drag out): the rest stays chained
  const chain = all([ws.blocks.blocks[0]]).slice(1);
  const before = chain.find((b) => b.next?.block?.type === "pl_step_loot")!;
  before.next = chain.find((b) => b.type === "pl_step_loot")!.next;
  const r = tabFromWorkspace(p, scope, ws);
  assert.ok(r.ok);
  if (!r.ok) return;
  assert.deepEqual(tabOfP(r.project, TICK_TAB).defs[0].body.map((s) => (s.kind === "action" ? s.block : "")), STEP_BLOCKS.filter((b) => b !== "step_loot"));
  assert.equal(canonical(tabOfP(r.project, TICK_TAB).defs[0]), canonical(tickDef(STEP_BLOCKS.filter((b) => b !== "step_loot"))));
});

test("the toolbox: hunt_loop() in a map's main, the Roles on the tab hunt, the Tick on the tab tick, the steps nowhere else", () => {
  const main = toolboxBlocks(toolbox(CAT, { node: "map", main: true, tab: "main" }));
  assert.ok(main.some((x) => x.item.type === "pl_call" && (x.item.fields as Record<string, unknown>).PROC === HUNT_CALL));
  assert.ok(main.some((x) => x.item.type === "pl_dungeon_hunt")); // the old shape's block stays offered
  const hunt = toolbox(CAT, { node: "map", main: false, tab: HUNT_TAB });
  const roles = toolboxBlocks(hunt).filter((x) => x.category === "Roles").map((x) => [x.item.type, (x.item.fields as Record<string, unknown>).FN]);
  assert.deepEqual(roles, RUNNER_ROLES.map((r) => [roleType(r.param), r.fn]));
  const loopDef = toolboxBlocks(hunt).find((x) => x.category === "Hunt" && x.item.type === "pl_def");
  assert.equal((loopDef?.item.fields as Record<string, unknown>).PARAMS, "t=False"); // main may call it
  const tb = toolbox(CAT, { node: "map", main: false, tab: TICK_TAB });
  const tick = toolboxBlocks(tb).filter((x) => x.category === TICK_CATEGORY).map((x) => x.item);
  assert.deepEqual([tick[0].type, (tick[0].fields as Record<string, unknown>).NAME], ["pl_def", TICK_FN]);
  assert.deepEqual(tick.slice(1).map((i) => i.type), TICK_STEPS.map(stepType));
  for (const i of tick.slice(1)) assert.deepEqual((i.extraState as { rest: unknown }).rest, { concept: "core.tick_step", timeout_s: 1, on_fail: "stop", outcome_to: null, note: null });
  for (const scope of [{ tab: "keys" }, { tab: HUNT_TAB }, { tab: "main", main: true }]) assert.equal(categoryOf(toolbox(CAT, { node: "map", main: false, ...scope }), TICK_CATEGORY), undefined);
  assert.equal(categoryOf(toolbox(CAT, { node: "global", main: false, tab: TICK_TAB }), TICK_CATEGORY), undefined);
  assert.equal(categoryOf(toolbox(CAT, { node: "map", main: false, tab: "keys" }), "Roles"), undefined);
  const more = toolboxBlocks(tb).filter((x) => x.category === "More skills").map((x) => (x.item.fields as Record<string, unknown>)?.BLOCK);
  for (const b of STEP_BLOCKS) assert.ok(!more.includes(b), b);
});

test("the role and step blocks: their types are defined, each row inside the 300-unit budget, the class shown", () => {
  for (const t of TICK_STEPS) {
    const type = stepType(t);
    assert.ok(DEF_BY_TYPE[type], type);
    assert.equal(STEP_OF_TYPE.get(type), t);
    const rows = rowsOf({ type, id: "x" }, {}, 20); // inside hunt_tick() (layout.ts INDENT)
    assert.ok(rows[0].what.endsWith(`${stepBlock(t)}()`) && rows[1].what.includes(`${t.klass === "optional" ? "optional" : t.klass.toUpperCase()} ·`), `${type}: ${rows[1].what}`);
    for (const r of rows) assert.ok(r.w <= SETTING_ROW_BUDGET, `${type}: ${Math.round(r.w)}: ${r.what}`);
    assert.equal(DEF_BY_TYPE[type].previousStatement, null); // a statement in hunt_tick()'s chain
  }
  for (const r of RUNNER_ROLES) {
    const type = roleType(r.param);
    assert.ok(DEF_BY_TYPE[type] && DEF_BY_TYPE[type].previousStatement === undefined, type); // a top block, as a variable
    assert.deepEqual([...namesOf(type).saved].filter((n) => !n.startsWith("ROW_")), ["FN"]); // (its end rows are inputs)
    // its usual function (the ready-made box's own: layout.test.ts), as the runner block's rows
    for (const row of rowsOf({ type, id: "x", fields: { FN: r.fn } })) assert.ok(row.w <= SETTING_ROW_BUDGET, `${type}: ${Math.round(row.w)}: ${row.what}`);
  }
});

// round 25 (merged 2026-11-15): the shelf lays the new blocks out too, a person's places are kept
// by their names (var:role_<param>, def:hunt_tick), and the engine never sees them
test("round 25's layout: the role blocks and hunt_tick have their keys; the functions box's tabs never overlap; a place never changes the engine's project", () => {
  const p = xmasFunctionsProject();
  const hunt = tabToWorkspace(p, { node: NODE, tab: HUNT_TAB }).blocks.blocks;
  assert.deepEqual(hunt.map((b) => layoutKey(b.type, b.fields)), ["def:hunt_loop", ...RUNNER_ROLES.map((r) => `var:${ROLE_PREFIX}${r.param}`)]);
  assert.deepEqual(tabToWorkspace(p, { node: NODE, tab: TICK_TAB }).blocks.blocks.map((b) => layoutKey(b.type, b.fields)), [`def:${TICK_FN}`]);
  for (const width of [313, 600, shelfWidth(1440 - 432 - 150, 0.75), 2400]) {
    for (const t of mapNodes(p)[0].tabs) {
      const ws = tabToWorkspace(p, { node: NODE, tab: t.name }, { width });
      const items = shelfItems(ws.blocks.blocks, t);
      const boxes = ws.blocks.blocks.map((b, i) => ({ id: b.id ?? `#${i}`, x: b.x ?? 0, y: b.y ?? 0, w: items[i].w, h: items[i].h }));
      for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
        const c = boxes[j];
        assert.ok(!overlaps(boxes[i], { ...c, x: c.x - STACK_GAP + 1, y: c.y - STACK_GAP + 1, w: c.w + 2 * STACK_GAP - 2, h: c.h + 2 * STACK_GAP - 2 }), `${width} ${t.name}: ${boxes[i].id} and ${c.id}`);
      }
    }
  }
  // a person moves every role block and hunt_tick: the layout keeps them by name, the engine's
  // project (and so the lowering, the keys, the hash) is unchanged
  for (const tab of [HUNT_TAB, TICK_TAB]) {
    const ws = clone(tabToWorkspace(p, { node: NODE, tab }));
    ws.blocks.blocks.forEach((b, i) => ([b.x, b.y] = [900 - 37 * i, 40 + 211 * i]));
    const back = tabFromWorkspace(p, { node: NODE, tab }, ws, {}, new Set(ws.blocks.blocks.map((b) => b.id ?? "")));
    assert.ok(back.ok, tab);
    if (!back.ok) continue;
    const lay = tabOf(nodeById(back.project, NODE)!, tab)!.layout ?? {};
    assert.deepEqual(Object.keys(lay).sort(), ws.blocks.blocks.map((b) => layoutKey(b.type, b.fields)!).sort());
    assert.equal(engineKey(back.project), engineKey(p), tab);
    assert.equal(canonical(runnerBlockOn(mapNodes(back.project)[0])), canonical(runnerBlockOn(mapNodes(p)[0])));
  }
});

// live-blocks 18.10 #1 (Batt 2026-11-16: "On"): the ready-made functions box and its cookie twin
// hold fly_first ON; the one box, the hunt box (the reference arms) keep it off; fly_first_hp
// (18.11) is ON in the two functions boxes since s8ab passed (18.13), off in the reference boxes
test("the ready-made functions boxes hold fly_first and fly_first_hp ON, the reference boxes off", () => {
  const safety = (p: ReturnType<typeof xmasFunctionsProject>) => mapNodes(p)[0].tabs.find((t) => t.name === "safety")!.vars;
  for (const p of [xmasFunctionsProject(), xmasFunctionsCookieNoSwapProject()]) {
    assert.equal(safety(p).fly_first?.value, true, p.name);
    assert.equal(safety(p).fly_first_hp?.value, true, p.name);
  }
  for (const p of [xmasProject(), xmasHuntProject()]) {
    assert.equal(safety(p).fly_first?.value, false, p.name);
    assert.equal(safety(p).fly_first_hp?.value, false, p.name);
  }
});

// live-blocks 18.15 (Batt 18.14, 2026-11-17: "use it for real"): the ready-made functions boxes
// name the deployed xmas02sk in use_model; the reference boxes keep xmas02 (xmas02-gb)
test("the ready-made functions boxes name xmas02sk, the reference boxes xmas02", () => {
  const model = (p: ReturnType<typeof xmasFunctionsProject>) => {
    const s = mainOf(mapNodes(p)[0])!.main!.find((x) => x.kind === "action" && x.block === "use_model");
    return s?.kind === "action" ? s.params.model : null;
  };
  assert.equal(FUNCTIONS_MODEL, "xmas02sk");
  for (const p of [xmasFunctionsProject(), xmasFunctionsCookieNoSwapProject()]) assert.deepEqual(model(p), { kind: "lit", value: FUNCTIONS_MODEL }, p.name);
  for (const p of [xmasProject(), xmasHuntProject(), xmasCookieNoSwapProject()]) assert.deepEqual(model(p), { kind: "lit", value: "xmas02" }, p.name);
  assert.equal(fixture().nodes[0].tabs[0].main[1].params.model.value, FUNCTIONS_MODEL);
});
