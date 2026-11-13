// Every key a FUNCTION (Batt 2026-11-13): the functions tab, the key-press block, the wing exit by
// a function, the runner's block, and the five keys Run reads from them (functions.ts).
import assert from "node:assert/strict";
import { test } from "node:test";

import { HOTKEYS, toolbox, toolboxBlocks } from "./blockdefs.ts";
import { fromWorkspace, toWorkspace, type Workspace } from "./blocks.ts";
import { homeFunctionOf, keyOf, runnerBlockOf, runnerKeys, runnerMapBlock } from "./functions.ts";
import { canonical, clone, type Flow, type Stmt } from "./ir.ts";
import { pressKey, starterFlow, XMAS_NAME, xmasFlow } from "./starter.ts";

const round = (flow: Flow, scope: Parameters<typeof toWorkspace>[1]) => {
  const ws = JSON.parse(JSON.stringify(toWorkspace(flow, scope))) as Workspace;
  return fromWorkspace(flow, scope, ws);
};

test("the xmas_dun02 flow: an ordinary flow, two map tabs, five functions, every tab round-trips", () => {
  const f = xmasFlow();
  assert.equal(f.name, XMAS_NAME);
  assert.deepEqual(f.workflow?.blocks.map((b) => b.name), ["xmas_dun02", "geffen"]);
  assert.deepEqual(Object.keys(f.procedures).sort(), ["butterfly_wing", "fly_wing", "heal", "knife_back", "knife_on"]);
  for (const scope of [{ kind: "block", name: "xmas_dun02" }, { kind: "block", name: "geffen" }, { kind: "global" }, { kind: "functions" }] as const) {
    const back = round(f, scope);
    assert.ok(back.ok && canonical(back.flow) === canonical(f), JSON.stringify(scope));
  }
  // the blocks a person sees: its own blocks, never the generic one
  const ws = toWorkspace(f, { kind: "block", name: "xmas_dun02" });
  const main = ws.blocks.blocks[0].inputs?.DO?.block;
  const loop = main?.next?.block;
  assert.equal(loop?.type, "pl_while");
  assert.equal(loop?.inputs?.BODY?.block?.type, "pl_dungeon_hunt");
  assert.deepEqual(loop?.inputs?.BODY?.block?.fields, { HEAL: "heal", FLY: "fly_wing", KNIFE_ON: "knife_on", KNIFE_BACK: "knife_back" });
  assert.equal(loop?.next?.block?.type, "pl_exit_item_fn");
  assert.equal(loop?.next?.block?.fields?.FN, "butterfly_wing");
  const defs = toWorkspace(f, { kind: "functions" }).blocks.blocks;
  assert.ok(defs.every((d) => d.type === "pl_def" && d.inputs?.DO?.block?.type === "pl_press_key"));
  assert.deepEqual(Object.fromEntries(defs.map((d) => [d.fields?.NAME, d.inputs?.DO?.block?.fields?.KEY])), { heal: "F1", fly_wing: "F8", butterfly_wing: "F9", knife_on: "F4", knife_back: "F5" });
});

test("Run's keys come from the functions: the runner's roles and the wing exit", () => {
  const f = xmasFlow();
  const b = runnerMapBlock(f);
  assert.equal(b?.name, "xmas_dun02");
  assert.equal(runnerBlockOf(f.workflow?.blocks[1]), null); // geffen holds no runner
  assert.equal(homeFunctionOf(b!), "butterfly_wing");
  const r = runnerKeys(f, b!);
  assert.ok(r.ok);
  assert.deepEqual(r.keys, { heal_key: "F1", fly_key: "F8", home_key: "F9", knife_key: "F4", dagger_key: "F5" });
  assert.equal(r.from.home_key, "butterfly_wing");
  // a person moves the Fly Wing to F6: Run takes F6
  const g = clone(f);
  g.procedures.fly_wing = [pressKey("F6")];
  const r2 = runnerKeys(g, runnerMapBlock(g)!);
  assert.ok(r2.ok && r2.keys.fly_key === "F6");
  // a role function that is not exactly one key press, a missing function, no wing exit: refused, in words
  const h = clone(f);
  h.procedures.heal = [pressKey("F1"), pressKey("F2")];
  delete h.procedures.knife_on;
  const blk = h.workflow!.blocks[0];
  blk.main = blk.main.filter((s: Stmt) => s.kind !== "take_exit");
  const r3 = runnerKeys(h, blk);
  assert.equal(r3.ok, false);
  const words = r3.ok ? "" : r3.problems.join(" | ");
  assert.match(words, /heal\(\) must be exactly one "press key" block/);
  assert.match(words, /there is no function knife_on/);
  assert.match(words, /the way home/);
  assert.deepEqual(keyOf(f, "nope"), { why: "there is no function nope (the functions tab)" });
});

test("the starter's wing is a function too, and the blocks hold only valid keys", () => {
  const s = starterFlow();
  assert.deepEqual(s.procedures.butterfly_wing, [pressKey("F9")]);
  assert.deepEqual(s.variables, {});
  // a press of a key outside F1-F9 is refused under the blocks
  const ws = toWorkspace(s, { kind: "functions" }) as Workspace;
  const press = ws.blocks.blocks[0].inputs!.DO!.block!;
  press.fields = { KEY: "F12" };
  const back = fromWorkspace(s, { kind: "functions" }, ws);
  assert.equal(back.ok, false);
  assert.match(back.ok ? "" : back.errors.join(" "), /press key "F12": one of F1, F2/);
  assert.equal(HOTKEYS.length, 9);
  // two functions with one name: refused
  const two = toWorkspace(s, { kind: "functions" }) as Workspace;
  two.blocks.blocks.push(JSON.parse(JSON.stringify(two.blocks.blocks[0])));
  two.blocks.blocks[1].id = "other";
  assert.equal(fromWorkspace(s, { kind: "functions" }, two).ok, false);
  // a function hat on a map tab is not applied there (it belongs on the functions tab)
  const m = toWorkspace(s, { kind: "block", name: "field" }) as Workspace;
  m.blocks.blocks.push({ type: "pl_def", fields: { NAME: "stray" } });
  const r = fromWorkspace(s, { kind: "block", name: "field" }, m);
  assert.ok(r.ok && !("stray" in r.flow.procedures) && r.warnings.some((w) => /functions tab/.test(w)));
});

test("the toolbox: function definitions on the functions tab only; the runner and the wing exit on a map tab", () => {
  const cat = { press_key: { concept: "ui.press_hotkey", timeout_s: 2 }, dungeon_hunt: { concept: "combat.hunt", timeout_s: 600 } };
  const types = (s: Parameters<typeof toolbox>[1]) => toolboxBlocks(toolbox(cat, s)).map((e) => e.item.type);
  assert.ok(types("functions").includes("pl_def"));
  assert.ok(!types("block").includes("pl_def") && !types("global").includes("pl_def"));
  assert.ok(types("block").includes("pl_dungeon_hunt") && types("block").includes("pl_exit_item_fn"));
  assert.ok(!types("functions").includes("pl_event"));
  for (const s of ["block", "global", "main", "functions"] as const) assert.ok(types(s).includes("pl_press_key") && types(s).includes("pl_call"));
  // press_key and dungeon_hunt are not repeated as generic blocks
  assert.ok(!toolboxBlocks(toolbox(cat, "block")).some((e) => e.item.type === "pl_action" && (e.item.fields?.BLOCK === "press_key" || e.item.fields?.BLOCK === "dungeon_hunt")));
});
