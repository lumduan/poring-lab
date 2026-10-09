import assert from "node:assert/strict";
import { test } from "node:test";

import { addBlock, connectExit, fromGraph, removeBlock, removeExit, retargetExit, savePointBlock, setStart, toGraph, updateBlock } from "./canvas.ts";
import { canonical, type Flow } from "./ir.ts";
import { FIXTURES, fixture, randomFlow } from "./testkit.ts";

const ok = <T extends { ok: boolean }>(r: T): Extract<T, { ok: true }> => {
  assert.ok(r.ok, JSON.stringify(r));
  return r as Extract<T, { ok: true }>;
};

test("IR -> canvas -> IR is exact (fixtures, sample, random flows)", () => {
  const flows: Flow[] = [...FIXTURES.map(fixture), ...Array.from({ length: 200 }, (_, i) => randomFlow(i + 1))];
  for (const f of flows) assert.equal(canonical(fromGraph(JSON.parse(JSON.stringify(toGraph(f))))), canonical(f), f.name);
});

test("the sample's canvas: map nodes, typed exits, events, the derived death_respawn", () => {
  const g = toGraph(fixture("town_warp_farm"));
  assert.deepEqual(g.nodes.map((n) => n.id).sort(), ["block:farm", "block:town", "events:farm", "events:global", "events:town"]);
  const edges = g.edges.map((e) => [e.data.kind, e.source, e.target, e.data.derived]);
  assert.deepEqual(edges.sort(), [
    ["attach", "events:farm", "block:farm", true],
    ["attach", "events:town", "block:town", true],
    ["death_respawn", "block:farm", "block:town", true],
    ["item_warp", "block:farm", "block:town", false],
    ["npc_warp", "block:town", "block:farm", false],
  ].sort());
  const npc = g.edges.find((e) => e.data.kind === "npc_warp")!;
  assert.equal(npc.data.path, "town.9");
  assert.equal(npc.sourceHandle, "npc_warp");
  assert.deepEqual(savePointBlock(fixture("town_warp_farm")), { block: "town", why: "the save point is on town_1" });
  const start = g.nodes.find((n) => n.id === "block:town")!;
  assert.ok(start.data.kind === "map" && start.data.start && start.data.startEntry === "spawn");
});

test("MW1's farm fixture: a loop of three exit kinds; the plain flow has a main node", () => {
  const g = toGraph(fixture("farm_loop"));
  const kinds = g.edges.filter((e) => !e.data.derived).map((e) => `${e.source}>${e.data.kind}>${e.target}`);
  assert.deepEqual(kinds, ["block:town>walk_exit>block:relay", "block:relay>npc_warp>block:farm", "block:farm>item_warp>block:town"]);
  const plain = toGraph(fixture("visit_and_choose"));
  assert.deepEqual(plain.nodes.map((n) => n.id), ["events:global", "main"]);
  assert.deepEqual(plain.edges, []);
});

test("drawing and deleting an exit edits the IR", () => {
  const flow = fixture("farm_loop");
  const a = ok(connectExit(flow, "farm", "walk_exit", "relay")).flow;
  const g = toGraph(a);
  const added = g.edges.filter((e) => e.data.kind === "walk_exit" && e.source === "block:farm");
  assert.equal(added.length, 1);
  assert.equal(added[0].data.path, "farm.2");
  const x = a.workflow!.blocks[2].main[2];
  assert.ok(x.kind === "take_exit" && x.exit.to_entry === "south" && x.exit.warp?.map === "map_3");
  const b = ok(removeExit(a, "farm.2")).flow;
  assert.equal(canonical(b), canonical(flow));
  assert.equal(removeExit(flow, "farm.0").ok, false); // a while loop, not an exit
  const c = ok(retargetExit(flow, "farm.1", "relay")).flow;
  const y = c.workflow!.blocks[2].main[1];
  assert.ok(y.kind === "take_exit" && y.exit.to_block === "relay" && y.exit.to_entry === "south");
});

test("blocks: add, rename (exits and start follow), remove, start", () => {
  const flow = fixture("town_warp_farm");
  const a = ok(addBlock(flow, "field_2")).flow;
  assert.equal(a.workflow!.blocks[2].name, "block_3");
  const town = a.workflow!.blocks[0];
  const r = ok(updateBlock(a, "town", { ...town, name: "home" })).flow;
  assert.equal(r.workflow!.start_block, "home");
  const back = r.workflow!.blocks[1].main[1];
  assert.ok(back.kind === "take_exit" && back.exit.to_block === "home");
  assert.equal(updateBlock(a, "town", { ...town, name: "farm" }).ok, false);
  assert.equal(updateBlock(a, "town", { ...town, name: "9bad" }).ok, false);
  assert.equal(removeBlock(a, "town").ok, false); // the start block
  const s = ok(setStart(a, "farm", "arrival")).flow;
  assert.equal(ok(removeBlock(s, "town")).flow.workflow!.blocks.length, 2);
  // the new block's empty main is a placeholder stop the first exit replaces
  const e = ok(connectExit(a, "block_3", "item_warp", "town")).flow;
  assert.deepEqual(e.workflow!.blocks[2].main.map((m) => m.kind), ["take_exit"]);
});

test("the always-on safety events show on the global node, never in the IR (ADR-0020 #15)", () => {
  const plain = toGraph(fixture("visit_and_choose"));
  const g = plain.nodes.find((n) => n.id === "events:global")!;
  assert.ok(g.data.kind === "events" && g.data.scope === "global");
  assert.deepEqual(g.data.builtIn, ["dead", "hp_critical", "unexpected_map"]); // none written
  const farm = fixture("farm_loop");
  const fg = toGraph(farm).nodes.find((n) => n.id === "events:global")!;
  assert.ok(fg.data.kind === "events" && fg.data.scope === "global" && fg.data.builtIn.length === 0); // all three written
  // a workflow that writes no dead still respawns (the built-in): the derived edges remain
  const noDead = { ...farm, handlers: farm.handlers.filter((h) => h.name !== "dead") };
  const g2 = toGraph(noDead);
  const gn = g2.nodes.find((n) => n.id === "events:global")!;
  assert.ok(gn.data.kind === "events" && gn.data.scope === "global");
  assert.deepEqual(gn.data.builtIn, ["dead"]);
  assert.ok(g2.edges.some((e) => e.data.kind === "death_respawn"));
  assert.equal(canonical(fromGraph(JSON.parse(JSON.stringify(g2)))), canonical(noDead)); // not IR
});
