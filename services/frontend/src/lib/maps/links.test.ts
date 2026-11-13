// How the maps link (links.ts) and the world rules (rules.ts) on the PROJECT (Batt 2026-11-13,
// docs/planning/project-model.md): entries by how the character arrives, exits by where they go
// (any tab of a map node), the save point stated as the START map's first statement and the
// unknown-map rule as a GLOBAL event. The rules' output on the two-map sample is the committed
// fixture fixtures/sample_world_rules.project.json (for the engine's lint: a TODO of the parent's).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { def, globalOf, mapNodes, nodeById, type Project, sampleProject, sessionPath, tab, xmasProject } from "../flow/project.ts";
import { sessionProject } from "../flow/testkit.ts";
import { arrivalText, entryRows, exitHow, exitRows, knownMaps, nodeLinks, savePointNode, worldLinks } from "./links.ts";
import { isOurRule, MAX_PER_RUN, readRules, refreshRule, RULE_NAME, ruleMaps, setSavePoint, setUnknownMap, WING_ID, wingItem } from "./rules.ts";

const fixture = JSON.parse(readFileSync(new URL("./fixtures/sample_world_rules.project.json", import.meta.url), "utf8")) as Project;
const town = { kind: "cell" as const, map: "town_1", x: 42, y: 40 };

test("the session path: login -> character -> the start map's entry", () => {
  const sp = sessionPath(sampleProject());
  assert.deepEqual([sp.login?.id, sp.character?.id, sp.map?.id, sp.entry, sp.problems], ["login", "character", "town", "spawn", []]);
  const broken = sampleProject();
  broken.edges = broken.edges.filter((e) => e.from !== "character");
  assert.match(sessionPath(broken).problems[0], /not connected to a map/);
});

test("an entry says how the character arrives: the session, a wing, an NPC warp, a respawn", () => {
  const p = sampleProject();
  const t = nodeLinks(p, "town");
  const f = nodeLinks(p, "field");
  assert.ok(t && f);
  assert.deepEqual(t.entries[0].arrivals.map((a) => a.kind), ["start", "item_warp", "death_respawn"]);
  assert.deepEqual(f.entries[0].arrivals.map((a) => [a.kind, a.fromMap]), [["npc_warp", "town_1"]]);
  assert.deepEqual(savePointNode(p), { node: "town", why: "the save point is on town_1" });
  assert.equal(nodeLinks(p, "login"), null, "a session node has no map links");
});

test("an exit says where it goes and how, by its engine path; a def's exit counts too", () => {
  const p = sampleProject();
  const t = nodeLinks(p, "town");
  assert.deepEqual(t?.exits.map((x) => [x.path, x.kind, x.toMap, x.toEntry, x.entryKnown, x.how]), [["town/main/main.2", "npc_warp", "field_1", "arrival", true, "talk to n_warper · o_to_field"]]);
  assert.deepEqual(worldLinks(p).map((x) => `${x.fromMap}->${x.toMap}:${x.kind}:${x.how}`), ["town_1->field_1:npc_warp:talk to n_warper · o_to_field", "field_1->town_1:item_warp:call butterfly_wing()"]);
  assert.deepEqual(knownMaps(p), ["field_1", "town_1"]);
  // an exit inside a function of another tab is one of the map's exits as well
  const x = sessionProject();
  const xm = nodeById(x, "xmas_dun02");
  assert.ok(xm && xm.kind === "map");
  const main = xm.tabs[0].main!;
  const wing = main.pop()!;
  xm.tabs.push(tab("home", [def("go_home", [wing])]));
  main.push({ kind: "call", proc: "go_home", args: [], kwargs: {} });
  assert.deepEqual(exitRows(x, xm).map((r) => [r.path, r.tab, r.toNode]), [["xmas_dun02/home/go_home.0", "home", "geffen"]]);
  assert.equal(exitHow({ kind: "walk_exit", warp: { kind: "cell", map: "a", x: 3, y: 4 }, npc: null, options: [], item: null, to_block: "b", to_entry: "e", timeout_s: 1 }), "walk to (3, 4)");
  assert.equal(exitHow({ kind: "item_warp", warp: null, npc: null, options: [], item: { kind: "item", id: 602 }, to_block: "b", to_entry: "e", timeout_s: 1 }), "a Butterfly Wing");
});

test("an exit to a node that is not a map of the project is named, not hidden", () => {
  const p = sampleProject();
  const s = (nodeById(p, "town") as { tabs: { main: unknown[] | null }[] }).tabs[0].main![2] as { exit: { to_block: string } };
  s.exit.to_block = "nowhere";
  assert.deepEqual(nodeLinks(p, "town")?.exits.map((e) => [e.toMap, e.entryKnown]), [[null, false]]);
});

test("the world rules on the sample make exactly the fixture", () => {
  const a = setSavePoint(sampleProject(), town);
  assert.ok(a.ok);
  const b = setUnknownMap(a.project, "wing");
  assert.ok(b.ok);
  assert.deepEqual(b.project, fixture);
  const r = readRules(b.project);
  assert.deepEqual(r.savePoint, { cell: town, asserted: true });
  assert.deepEqual([r.startMap, r.unknownMap, r.custom, r.tab, r.overriddenOn], ["town", "wing", false, "safety", []]);
  const g = globalOf(b.project)!;
  const d = g.tabs.find((t) => t.name === "safety")!.defs[0];
  assert.equal(d.name, RULE_NAME);
  assert.ok(isOurRule(d));
  assert.equal(d.on?.max_per_run, MAX_PER_RUN);
  assert.equal(d.on?.then, "relocate");
  assert.deepEqual(d.params, []);
  assert.deepEqual(ruleMaps(b.project), ["field_1", "town_1"]);
  assert.deepEqual(wingItem(b.project), { kind: "proc", name: "butterfly_wing" }); // the map's item warp's FUNCTION
  assert.deepEqual(d.body[1].kind === "if" ? d.body[1].then : null, [{ kind: "call", proc: "butterfly_wing", args: [], kwargs: {} }]);
});

test("the save point is the START map's first statement: set, moved, cleared", () => {
  const a = setSavePoint(sampleProject(), town);
  assert.ok(a.ok);
  const moved = setSavePoint(a.project, { ...town, x: 50 });
  assert.ok(moved.ok);
  const first = (nodeById(moved.project, "town") as { tabs: { main: { kind: string; block?: string }[] | null }[] }).tabs[0].main!;
  assert.equal(first.filter((s) => s.kind === "action" && s.block === "assert_save_point").length, 1);
  const cleared = setSavePoint(moved.project, null);
  assert.ok(cleared.ok);
  assert.deepEqual(cleared.project, sampleProject());
  assert.equal(setSavePoint(sampleProject(), { ...town, x: -1 }).ok, false);
  assert.equal(setSavePoint(sampleProject(), { ...town, map: "bad map" }).ok, false);
  // xmas_dun02 states Geffen already: its start map is xmas_dun02 (the one box: the START itself;
  // the login-start project: the session path's map)
  for (const p of [xmasProject(), sessionProject()]) {
    const x = readRules(p);
    assert.deepEqual([x.startMap, x.savePoint.cell?.map, x.unknownMap], ["xmas_dun02", "geffen", "stop"]);
  }
  // no path to a map: no start map, refused with words
  const broken = sampleProject();
  broken.edges = [];
  const r = setSavePoint(broken, town);
  assert.ok(!r.ok && /session path/.test(r.error));
});

test("turning the rule off gives back the project; another map refreshes its known maps", () => {
  const on = setUnknownMap(sampleProject(), "wing");
  assert.ok(on.ok);
  const off = setUnknownMap(on.project, "stop");
  assert.ok(off.ok);
  assert.deepEqual(off.project, sampleProject(), "the tab the rule alone filled goes with it");
  assert.equal(refreshRule(on.project), on.project, "nothing to change: the same object");
  const p = structuredClone(on.project);
  const field = structuredClone(mapNodes(p)[1]);
  p.nodes.push({ ...field, id: "field2", map: { kind: "map", map: "field_2" } });
  assert.deepEqual(ruleMaps(refreshRule(p)), ["field_1", "field_2", "town_1"]);
});

test("a different own unexpected_map is never overwritten unasked; a map's own is never touched", () => {
  const p = sampleProject();
  const g = globalOf(p)!;
  g.tabs[0].defs.push({ ...def(RULE_NAME, [{ kind: "stop", reason: "lost" }]), on: fixtureTrigger() });
  assert.equal(readRules(p).custom, true);
  const refused = setUnknownMap(p, "wing");
  assert.ok(!refused.ok && /its own unexpected_map/.test(refused.error));
  const replaced = setUnknownMap(p, "wing", true);
  assert.ok(replaced.ok);
  assert.equal(globalOf(replaced.project)!.tabs[0].defs.filter((d) => d.name === RULE_NAME).length, 1, "it goes back into the tab it was in");
  // a map node's own unexpected_map overrides it there: listed, kept
  const q = setUnknownMap(sampleProject(), "wing");
  assert.ok(q.ok);
  const field = nodeById(q.project, "field")!;
  field.tabs.push(tab("lost", [def(RULE_NAME, [{ kind: "stop", reason: "lost" }])]));
  assert.deepEqual(readRules(q.project).overriddenOn, ["field"]);
  const off = setUnknownMap(q.project, "stop");
  assert.ok(off.ok);
  assert.equal(nodeById(off.project, "field")!.tabs.at(-1)!.defs[0].name, RULE_NAME);
});

test("with no item warp the rule uses the lab's Butterfly Wing", () => {
  const p = sampleProject();
  const field = nodeById(p, "field")!;
  field.tabs[0].main!.pop(); // the wing back
  assert.deepEqual(wingItem(p), { kind: "item", id: WING_ID });
  const on = setUnknownMap(p, "wing");
  assert.ok(on.ok);
  const d = globalOf(on.project)!.tabs.find((t) => t.name === "safety")!.defs[0];
  const s = d.body[1];
  assert.ok(s.kind === "if" && s.then[0].kind === "action");
  assert.deepEqual(s.then[0].params.item, { kind: "lit", value: { kind: "item", id: WING_ID } });
});

function fixtureTrigger() {
  const d = globalOf(fixture)!.tabs.find((t) => t.name === "safety")!.defs[0];
  return structuredClone(d.on!);
}

test("a project lint (by_node, no by_owner) never breaks the node words (matpilot round 15: /maps crashed)", async () => {
  const { nodeLint } = await import("./nodewords.ts");
  const { lintOf } = await import("../flow/status.ts");
  const lint = { findings: [], counts: { error: 0, readiness: 0, warning: 1, info: 0 }, by_node: { login: { error: 0, readiness: 0, warning: 1, info: 0 } }, run: { allowed: true, summary: "", reasons: [] }, effective: {}, world: { server: null, maps: [] } };
  assert.equal(nodeLint(lint as never, "login").counts.warning, 1);
  assert.equal(nodeLint(lint as never, "nobody").counts.warning, 0);
  assert.equal(lintOf(lint as never, "login").warning, 1);
});

test("a map START: its first entry says the run starts there (no session)", () => {
  const x = xmasProject();
  const n = mapNodes(x)[0];
  const rows = entryRows(x, n);
  assert.deepEqual(rows.map((r) => [r.name, r.arrivals.map((a) => [a.kind, a.from])]), [["here", [["start", null]]]]);
  assert.equal(arrivalText(rows[0].arrivals[0]), "START: the run starts here, where she stands");
  // the login start's entry: the session enters there
  const s = sessionProject();
  const sx = nodeById(s, "xmas_dun02");
  assert.ok(sx && sx.kind === "map");
  assert.equal(arrivalText(entryRows(s, sx)[0].arrivals[0]), "the session enters here");
});
