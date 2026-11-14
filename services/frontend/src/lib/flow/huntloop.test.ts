// Live blocks 5b-2 (docs/planning/live-blocks.md 14): the HUNT TAB in the browser -- hunt_loop(t),
// the hunt core's loop as its own steps (poring_flow.huntloop): its blocks (the value's variable and
// the time box shown), the toolbox's Hunt category, the ready-made box with it (the engine's fixture
// project_xmas_dun02_hunt.json, byte for byte), the round trip, and Run's readiness reaching it.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";

import { categoryOf, DEF_BY_TYPE, HUNT_LOOP_BLOCKS, HUNT_LOOP_TAB, namesOf, toolbox, toolboxBlocks } from "./blockdefs.ts";
import { tabFromWorkspace, tabToWorkspace, type Workspace } from "./blocks.ts";
import { canonical } from "./ir.ts";
import { reachable } from "./liveready.ts";
import { HUNT_TAB, huntLoopDef, mapNodes, MONSTERS_TAB, xmasHuntProject, xmasProject } from "./project.ts";

type WsBlock = Workspace["blocks"]["blocks"][number];
function all(blocks: readonly WsBlock[]): WsBlock[] {
  const out: WsBlock[] = [];
  for (const b of blocks) {
    out.push(b);
    const kids = [...Object.values(b.inputs ?? {}).map((i) => i.block), b.next?.block].filter((x): x is WsBlock => !!x);
    out.push(...all(kids));
  }
  return out;
}

const CAT = {
  find_target: { concept: "combat.hunt", timeout_s: 120 },
  fight: { concept: "combat.attack_target", timeout_s: 300 },
  walk_to_target: { concept: "combat.attack_target", timeout_s: 30 },
  choose_target: { concept: "core.choose_target", timeout_s: 1, kind: "core" },
  look: { concept: "core.look", timeout_s: 1, kind: "core" },
  strike: { concept: "combat.attack_target", timeout_s: 60 },
  wait_steal: { concept: "core.wait_steal", timeout_s: 10, kind: "core" },
  wait_kill: { concept: "core.wait_kill", timeout_s: 120, kind: "core" },
  loot: { concept: "loot.pick_up", timeout_s: 30 },
  use_skill: { concept: "combat.use_skill", timeout_s: 30 },
  press_key: { concept: "core.press_key", timeout_s: 1 },
};

test("the one box with its hunt tab is the engine's fixture, byte for byte, and the one box is unchanged", () => {
  const url = new URL("./fixtures/project_xmas_dun02_hunt.json", import.meta.url);
  assert.ok(existsSync(url));
  assert.equal(canonical(xmasHuntProject()), canonical(JSON.parse(readFileSync(url, "utf8"))));
  const [n] = mapNodes(xmasHuntProject());
  const names = n.tabs.map((t) => t.name);
  assert.equal(names[names.indexOf(MONSTERS_TAB) + 1], HUNT_TAB);
  assert.ok(!mapNodes(xmasProject())[0].tabs.some((t) => t.name === HUNT_TAB)); // 5b-1's A/B plays it
  assert.equal(HUNT_TAB, HUNT_LOOP_TAB);
});

test("the hunt tab's blocks show the value's variable and the time box, and round-trip exactly", () => {
  const p = xmasHuntProject();
  const scope = { node: "xmas_dun02", tab: HUNT_TAB };
  const ws = JSON.parse(JSON.stringify(tabToWorkspace(p, scope))) as Workspace;
  const blocks = all(ws.blocks.blocks);
  const take = blocks.find((b) => b.type === "pl_hunt_take");
  const step = blocks.find((b) => b.type === "pl_hunt_step");
  assert.deepEqual(take?.fields, { VAR: "t", BLOCK: "find_target", ARGS: "", TIMEOUT: 120 });
  assert.deepEqual(step?.fields, { BLOCK: "fight", ARGS: "target=t", TIMEOUT: 300 });
  // every field the converter writes is the type's (the contract)
  for (const b of [take, step]) for (const f of Object.keys(b?.fields ?? {})) assert.ok(namesOf(b!.type).saved.has(f), `${b?.type}.${f}`);
  const back = tabFromWorkspace(p, scope, ws);
  assert.ok(back.ok);
  if (!back.ok) return;
  assert.equal(canonical(back.project), canonical(p));
  // an edit plays: the time box and the variable are the IR's
  (take!.fields as Record<string, unknown>).TIMEOUT = 60;
  (take!.fields as Record<string, unknown>).VAR = "x";
  const edited = tabFromWorkspace(p, scope, ws);
  assert.ok(edited.ok);
  if (!edited.ok) return;
  const loop = mapNodes(edited.project)[0].tabs.find((t) => t.name === HUNT_TAB)!.defs[0].body[0];
  assert.ok(loop.kind === "while");
  const first = loop.kind === "while" ? loop.body[0] : null;
  assert.ok(first?.kind === "action" && first.timeout_s === 60 && first.outcome_to === "x");
  // an empty variable is refused in words
  (take!.fields as Record<string, unknown>).VAR = "";
  const bad = tabFromWorkspace(p, scope, ws);
  assert.ok(!bad.ok && bad.errors.some((e) => e.includes("its value goes into a variable")));
});

test("the toolbox's Hunt category is offered on the hunt tab only, the canonical loop first", () => {
  const tb = toolbox(CAT, { node: "map", main: false, tab: HUNT_TAB });
  const hunt = categoryOf(tb, "Hunt");
  assert.ok(hunt);
  const items = toolboxBlocks(tb).filter((x) => x.category === "Hunt").map((x) => x.item);
  assert.deepEqual(items.slice(0, 4).map((i) => [i.type, (i.fields as Record<string, unknown>)?.BLOCK ?? (i.fields as Record<string, unknown>)?.NAME ?? ""]), [
    ["pl_def", "hunt_loop"],
    ["pl_while", ""],
    ["pl_hunt_take", "find_target"],
    ["pl_hunt_step", "fight"],
  ]);
  const offered = new Set(items.map((i) => (i.fields as Record<string, unknown>)?.BLOCK).filter(Boolean));
  for (const b of [...HUNT_LOOP_BLOCKS, "strike", "wait_steal", "wait_kill", "loot", "use_skill"]) assert.ok(offered.has(b), b);
  assert.equal(categoryOf(toolbox(CAT, { node: "map", main: false, tab: "keys" }), "Hunt"), undefined);
  assert.equal(categoryOf(toolbox(CAT, { node: "global", main: false, tab: HUNT_TAB }), "Hunt"), undefined);
  // never under "More skills" (they play only in the hunt loop)
  const more = toolboxBlocks(tb).filter((x) => x.category === "More skills").map((x) => (x.item.fields as Record<string, unknown>)?.BLOCK);
  for (const b of HUNT_LOOP_BLOCKS) assert.ok(!more.includes(b), b);
  for (const t of ["pl_hunt_take", "pl_hunt_step"]) assert.ok(DEF_BY_TYPE[t], t);
});

test("Run's readiness reaches the hunt loop from the hunt core", () => {
  const p = xmasHuntProject();
  const got = reachable(p, "xmas_dun02");
  for (const b of ["find_target", "fight"]) assert.ok(got.blocks.includes(b), b);
  assert.ok(!reachable(xmasProject(), "xmas_dun02").blocks.includes("find_target"));
  assert.equal(huntLoopDef().params[0].name, "t");
});
