// Can the live block player play this map node? (live-blocks.md stage 1): every block a run from
// there reaches has the catalogue's `live` flag; else Run is greyed with the blocks that are not.
import assert from "node:assert/strict";
import { test } from "node:test";

import { liveReady, reachable } from "./liveready.ts";
import { call, def, nodeById, pressKey, sampleProject, tab, xmasProject } from "./project.ts";
import { sessionProject } from "./testkit.ts";

const LIVE = (names: string[]) => Object.fromEntries(names.map((n) => [n, { spec: { live: true } }]));

const STAGE4 = ["assert_save_point", "click_at", "dungeon_hunt", "loot", "press_key", "strike", "use_model", "wait_kill", "wait_steal"];

test("the one box reaches its save point, the runner, its role functions' presses and clicks", () => {
  const r = reachable(xmasProject(), "xmas_dun02");
  // stage 3 (live-blocks.md 3.3): the respawn roles' functions click (click_at, live there);
  // stage 4a (3.4): use_model, and the monsters' recipes the hunt core asks at its lock
  assert.deepEqual(r, { blocks: STAGE4, exits: [], nodes: ["xmas_dun02"] });
  assert.deepEqual(liveReady(xmasProject(), "xmas_dun02", LIVE(STAGE4)).ready, true);
  const old = liveReady(xmasProject(), "xmas_dun02", LIVE(["assert_save_point", "click_at", "dungeon_hunt", "press_key"]));
  assert.equal(old.ready ? "" : old.why, "loot, strike, use_model, wait_kill, wait_steal: not live yet"); // a backend before 4a
  // a monster's use_skill (4b) greys Run with its name
  const p = xmasProject();
  const mon = p.nodes[0].tabs.find((t) => t.name === "monsters")!;
  mon.defs[0].body.splice(4, 0, { kind: "action", block: "use_skill", concept: "combat.use_skill", params: { key: { kind: "lit", value: "F6" } }, timeout_s: 30, on_fail: "stop", outcome_to: null, note: null });
  const sk = liveReady(p, "xmas_dun02", LIVE(STAGE4));
  assert.equal(sk.ready ? "" : sk.why, "use_skill: not live yet");
});

test("a missing flag is not live; the reason lists the blocks, the exits too", () => {
  const p = xmasProject();
  const no = liveReady(p, "xmas_dun02", { ...LIVE(STAGE4.filter((b) => b !== "dungeon_hunt")), dungeon_hunt: { spec: {} } });
  assert.equal(no.ready, false);
  assert.equal(no.ready ? "" : no.why, "dungeon_hunt: not live yet");
  // the sample's town: walk_to, an NPC warp; following the exit onto the field: attack_nearest
  const s = sampleProject();
  const r = reachable(s, "town");
  assert.deepEqual(r.nodes, ["town", "field"]);
  assert.deepEqual(r.blocks, ["attack_nearest", "press_key", "set_save_point", "walk_to"]);
  assert.deepEqual(r.exits, ["npc_warp"]); // the field's wing home is an item warp by a function: live
  const t = liveReady(s, "town", LIVE(["press_key", "set_save_point"]));
  assert.equal(t.ready ? "" : t.why, "attack_nearest, walk_to, npc_warp: not live yet");
  // before the catalogue: greyed, saying so; a non-map node: never
  assert.match((liveReady(s, "town", null) as { why: string }).why, /reading the block catalogue/);
  assert.match((liveReady(s, "login", LIVE([])) as { why: string }).why, /map node/);
});

test("functions resolve on THAT node (its own first), events count, a call's function too", () => {
  const p = sessionProject();
  // Global's hp_low calls heal (press_key); the map's own heal overrides it with a sit
  const xm = nodeById(p, "xmas_dun02")!;
  xm.tabs.push(tab("mine", [def("heal", [{ kind: "action", block: "sit", concept: "core.sit", timeout_s: 5, on_fail: "stop", outcome_to: null, note: null, params: {} }])]));
  const r = reachable(p, "xmas_dun02");
  assert.ok(r.blocks.includes("sit"), "the node's heal, through Global's event and the runner's heal role");
  assert.deepEqual(r.nodes, ["xmas_dun02", "geffen"]);
  // a function called from main, defined only on Global
  const g = nodeById(p, "global")!;
  g.tabs.push(tab("lib", [def("emote", [pressKey("F6")])]));
  xm.tabs[0].main!.unshift(call("emote"));
  assert.ok(reachable(p, "xmas_dun02").blocks.includes("press_key"));
});
