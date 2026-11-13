// How the maps link (links.ts) and the world rules (rules.ts), Batt 2026-11-13: entries by how the
// character arrives, exits by where they go, the save point stated at the run's first step and the
// unknown-map rule. The rules' output on the starter is the committed fixture the flow engine
// lints (packages/poring_flow/tests/test_world_rules.py: no error).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import type { Flow } from "../flow/ir.ts";
import { oneMapStarter, starterFlow } from "../flow/starter.ts";
import { blockLinks, entryCaption, exitHow, knownMaps, worldLinks } from "./links.ts";
import { MAX_PER_RUN, readRules, refreshRule, ruleMaps, setSavePoint, setUnknownMap, WING_ID, wingItem } from "./rules.ts";

const fixture = JSON.parse(readFileSync(new URL("../flow/fixtures/starter_world_rules.json", import.meta.url), "utf8")) as Flow;
const town = { kind: "cell" as const, map: "town_1", x: 42, y: 40 };

test("an entry says how the character arrives: the start, a wing, an NPC warp", () => {
  const f = starterFlow();
  const t = blockLinks(f, "town");
  const fl = blockLinks(f, "field");
  assert.ok(t && fl);
  assert.deepEqual(
    t.entries[0].arrivals.map((a) => a.kind),
    ["start", "item_warp", "death_respawn"],
  );
  assert.equal(entryCaption(t.entries[0]), "start · wing arrival from field_1 · respawn");
  assert.deepEqual(fl.entries[0].arrivals.map((a) => [a.kind, a.fromMap]), [["npc_warp", "town_1"]]);
});

test("an exit says where it goes and how", () => {
  const f = starterFlow();
  const t = blockLinks(f, "town");
  assert.ok(t);
  assert.deepEqual(
    t.exits.map((x) => [x.kind, x.toMap, x.toEntry, x.entryKnown, x.how]),
    [["npc_warp", "field_1", "arrival", true, "talk to n_warper · o_to_field"]],
  );
  assert.deepEqual(
    worldLinks(f).map((x) => `${x.fromMap}->${x.toMap}:${x.kind}`),
    ["town_1->field_1:npc_warp", "field_1->town_1:item_warp"],
  );
  assert.equal(exitHow({ kind: "walk_exit", warp: { kind: "cell", map: "a", x: 3, y: 4 }, npc: null, options: [], item: null, to_block: "b", to_entry: "e", timeout_s: 1 }), "walk to (3, 4)");
  assert.equal(exitHow({ kind: "item_warp", warp: null, npc: null, options: [], item: { kind: "item", id: 602 }, to_block: "b", to_entry: "e", timeout_s: 1 }), "a Butterfly Wing");
  assert.deepEqual(knownMaps(f), ["field_1", "town_1"]);
});

test("an exit to a block that is not in the flow is named, not hidden", () => {
  const f = starterFlow();
  const x = f.workflow?.blocks[0].main[2];
  assert.ok(x && x.kind === "take_exit");
  x.exit.to_block = "nowhere";
  const t = blockLinks(f, "town");
  assert.deepEqual(t?.exits.map((e) => [e.toMap, e.entryKnown]), [[null, false]]);
});

test("a plain flow has no blocks and no links", () => {
  const f = oneMapStarter();
  assert.equal(blockLinks(f, "main"), null);
  assert.deepEqual(worldLinks(f), []);
  assert.equal(setSavePoint(f, town).ok, false);
  assert.equal(setUnknownMap(f, "wing").ok, false);
});

test("the world rules on the starter make exactly the fixture the engine lints clean", () => {
  const a = setSavePoint(starterFlow(), town);
  assert.ok(a.ok);
  const b = setUnknownMap(a.flow, "wing");
  assert.ok(b.ok);
  assert.deepEqual(b.flow, fixture);
  const r = readRules(b.flow);
  assert.deepEqual(r.savePoint, { cell: town, asserted: true });
  assert.equal(r.unknownMap, "wing");
  assert.equal(r.custom, false);
  const h = b.flow.handlers[0];
  assert.equal(h.max_per_run, MAX_PER_RUN);
  assert.equal(h.then, "relocate");
  assert.deepEqual(ruleMaps(b.flow), ["field_1", "town_1"]);
  assert.deepEqual(wingItem(b.flow), { kind: "var", name: "WING" }); // the flow's own wing exit's item
});

test("the save point is the start block's first step: set, moved, cleared", () => {
  const a = setSavePoint(starterFlow(), town);
  assert.ok(a.ok);
  const moved = setSavePoint(a.flow, { ...town, x: 50 });
  assert.ok(moved.ok);
  const first = moved.flow.workflow?.blocks[0].main;
  assert.equal(first?.filter((s) => s.kind === "action" && s.block === "assert_save_point").length, 1);
  const cleared = setSavePoint(moved.flow, null);
  assert.ok(cleared.ok);
  assert.deepEqual(cleared.flow, starterFlow());
  assert.equal(setSavePoint(starterFlow(), { ...town, x: -1 }).ok, false);
  assert.equal(setSavePoint(starterFlow(), { ...town, map: "bad map" }).ok, false);
});

test("turning the rule off gives back the built-in; another map refreshes its known maps", () => {
  const on = setUnknownMap(starterFlow(), "wing");
  assert.ok(on.ok);
  const off = setUnknownMap(on.flow, "stop");
  assert.ok(off.ok);
  assert.deepEqual(off.flow.handlers, []);
  const f = on.flow;
  f.workflow?.blocks.push({ ...structuredClone(f.workflow.blocks[1]), name: "field2", map: { kind: "map", map: "field_2" } });
  assert.deepEqual(ruleMaps(refreshRule(f)), ["field_1", "field_2", "town_1"]);
});

test("a flow's own different unexpected_map is never overwritten unasked", () => {
  const f = starterFlow();
  f.handlers.push({ ...structuredClone(fixture.handlers[0]), body: [fixture.handlers[0].body[0]] });
  assert.equal(readRules(f).custom, true);
  assert.equal(setUnknownMap(f, "wing").ok, false);
  assert.equal(setUnknownMap(f, "wing", true).ok, true);
});

test("with no wing exit the rule uses the lab's Butterfly Wing", () => {
  const f = starterFlow();
  const field = f.workflow?.blocks[1];
  assert.ok(field);
  field.main.pop(); // the wing back
  assert.deepEqual(wingItem(f), { kind: "item", id: WING_ID });
  const on = setUnknownMap(f, "wing");
  assert.ok(on.ok);
  const s = on.flow.handlers[0].body[1];
  assert.ok(s.kind === "if" && s.then[0].kind === "action");
  assert.deepEqual(s.then[0].params.item, { kind: "lit", value: { kind: "item", id: WING_ID } });
});
