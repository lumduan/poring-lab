// The hunt block in the block editor (blocks-from-hunt-flow.md B2): groups as lists of rule
// versions with badges; IR -> blocks -> IR exact with and without the catalogue's lists; nothing
// but the registry's parameters can be a field (no gate, safety number, reader or constant).
// hunt_rules.json is GET /flows/catalogue's `hunt_rules` (scripts/gen_zones_fixtures.py,
// drift-tested in packages/poring_flow/tests/test_hunt_rules.py).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { COLOURS, namesOf, toolbox } from "./blockdefs.ts";
import { fromWorkspace, type Scope, toWorkspace, type Workspace, type WsBlock } from "./blocks.ts";
import { badgeText, defaultFields, fieldOf, HUNT_TYPE, huntDef, type HuntRules, huntTooltip, omitted, params } from "./hunt.ts";
import { action, canonical, clone, type Flow, lit } from "./ir.ts";
import { fixture } from "./testkit.ts";

const RULES = JSON.parse(readFileSync(new URL("./fixtures/hunt_rules.json", import.meta.url), "utf8")) as HuntRules;
const ADOPTED = { strike: "arm_c@32", engage_on_the_way: "on_the_way@19", dead: "exp_line@48", loot: "gm_fast_scan@54", search: "heading_coverage@22" }; // the adopted base v55 (3.97; v52 until 10-22 04:32)
// engage_source and search_route (Batt 2026-10-22): OPTIONS, not required; absent = detector /
// heading, so the IR above (written before them) is a detector hunt searching by heading and its
// dropdowns show "detector" and "heading"
const DEFAULTS = { ...ADOPTED, engage_source: "detector", search_route: "heading" };
const SHOWN = { strike: "arm_c@32", engage_on_the_way: "on_the_way@19", engage_source: "detector", dead: "exp_line@48", loot: "gm_fast_scan@54", search: "heading_coverage@22", search_route: "heading" };
const OMIT = { engage_source: "detector", search_route: "heading" };
const FARM: Scope = { kind: "block", name: "farm" };

function withHunt(values: Record<string, string>): Flow {
  const flow = clone(fixture("town_warp_farm"));
  const farm = flow.workflow!.blocks.find((b) => b.name === "farm")!;
  const ps = Object.fromEntries(Object.entries(values).map(([k, v]) => [k, lit(v)]));
  farm.main.unshift({ ...action("hunt", "combat.hunt", ps, 600), note: "the field" });
  return flow;
}

const viaJson = (ws: Workspace): Workspace => JSON.parse(JSON.stringify(ws)) as Workspace;

function first(ws: Workspace): WsBlock {
  return ws.blocks.blocks[0].inputs!.DO!.block!;
}

test("the hunt block's groups are Batt's, each a list of the registry's rule versions", () => {
  assert.deepEqual(RULES.groups.map((g) => g.name), ["engage", "dead_loot", "search", "stop"]);
  assert.deepEqual(Object.fromEntries(params(RULES).map((p) => [p.name, p.default])), DEFAULTS);
  const def = huntDef(RULES, COLOURS.action);
  const loot = (def.args2 ?? []).find((a) => "name" in a && a.name === "P_LOOT");
  assert.ok(loot && "options" in loot);
  assert.deepEqual(loot.options?.map(([, v]) => v), ["gm_fast_scan@54", "gm_scan_one_pass@51", "gm_scan@50"]);
  assert.deepEqual(loot.options?.map(([t]) => t), ["gm_fast_scan@54 ★", "gm_scan_one_pass@51 ◆", "gm_scan@50 ◆"]);
  assert.equal(def.message4, "stop: %1"); // the stop group: the enclosing loop, no parameter
});

test("no field but the registry's parameters: no gate can become a field", () => {
  const def = huntDef(RULES, COLOURS.action);
  const n = namesOf(HUNT_TYPE, def);
  assert.deepEqual([...n.saved].sort(), params(RULES).map((p) => fieldOf(p.name)).sort());
  assert.deepEqual([...n.inputs], []);
  // the dropdowns are the only saved fields; the labels (badges, run line, the stop note) are not
  for (const f of n.fields) assert.ok(n.saved.has(f) || ["BADGE", "EVIDENCE", "RUN", "NOTE_STOP"].includes(f), f);
});

test("IR -> blocks -> IR is exact for a hunt, shown as the hunt block", () => {
  const flow = withHunt(ADOPTED);
  const ws = toWorkspace(flow, FARM, { hunt: RULES });
  const b = first(ws);
  assert.equal(b.type, HUNT_TYPE);
  assert.deepEqual(b.fields, Object.fromEntries(Object.entries(SHOWN).map(([k, v]) => [fieldOf(k), v])));
  const back = fromWorkspace(flow, FARM, viaJson(ws));
  assert.ok(back.ok, !back.ok ? back.errors.join("; ") : "");
  assert.equal(canonical(back.flow), canonical(flow));
});

test("a person's other choice is a new rule version in the IR, nothing else changes", () => {
  const flow = withHunt(ADOPTED);
  const ws = viaJson(toWorkspace(flow, FARM, { hunt: RULES }));
  first(ws).fields![fieldOf("loot")] = "gm_scan@50";
  const back = fromWorkspace(flow, FARM, ws);
  assert.ok(back.ok);
  assert.equal(canonical(back.flow), canonical(withHunt({ ...ADOPTED, loot: "gm_scan@50" })));
});

test("without the lists, or with a value not among them, the hunt stays a generic block, exactly", () => {
  for (const [flow, rules] of [
    [withHunt(ADOPTED), null],
    [withHunt({ ...ADOPTED, loot: "gm_union@53" }), RULES], // not a choice: the linter names it
    [withHunt({ strike: "arm_c@32" }), RULES], // parameters missing: required (layer 1)
  ] as [Flow, HuntRules | null][]) {
    const ws = toWorkspace(flow, FARM, { hunt: rules });
    assert.equal(first(ws).type, "pl_action");
    const back = fromWorkspace(flow, FARM, viaJson(ws));
    assert.ok(back.ok);
    assert.equal(canonical(back.flow), canonical(flow));
  }
});

test("dragged from the toolbox: the adopted base's rules, the catalogue's concept and timeout", () => {
  const tb = toolbox({ hunt: { concept: "combat.hunt", timeout_s: 600 }, walk_to: { concept: "nav.walk_to", timeout_s: 120 } }, "block", defaultFields(RULES), omitted(RULES));
  const item = tb.contents.find((c) => c.name === "More skills")!.contents.find((i) => i.type === HUNT_TYPE);
  assert.ok(item);
  assert.deepEqual(item.fields, defaultFields(RULES));
  assert.deepEqual((item.extraState as { omit?: unknown }).omit, OMIT);
  const flow = clone(fixture("town_warp_farm"));
  const ws = viaJson(toWorkspace(flow, FARM, { hunt: RULES }));
  const dragged: WsBlock = { type: HUNT_TYPE, id: "fresh", fields: defaultFields(RULES), extraState: item.extraState };
  dragged.next = { block: first(ws) };
  ws.blocks.blocks[0].inputs!.DO!.block = dragged;
  const back = fromWorkspace(flow, FARM, ws, { hunt: { concept: "combat.hunt", timeout_s: 600 } });
  assert.ok(back.ok);
  const h = back.flow.workflow!.blocks.find((b) => b.name === "farm")!.main[0];
  assert.ok(h.kind === "action" && h.block === "hunt" && h.concept === "combat.hunt" && h.timeout_s === 600);
  assert.deepEqual(Object.fromEntries(Object.entries(h.params).map(([k, e]) => [k, e.kind === "lit" ? e.value : null])), ADOPTED);
  // without the catalogue's toolbox lists the hunt is offered as a generic block
  const plain = toolbox({ hunt: { concept: "combat.hunt", timeout_s: 600 } }, "block");
  assert.ok(plain.contents.find((c) => c.name === "More skills")!.contents.some((i) => i.type === "pl_action"));
});

test("badges: the adopted base, the D8 hunting evidence, the versions that hold the rule", () => {
  const loot = params(RULES).find((p) => p.name === "loot")!;
  const [fast, one, v50] = loot.choices;
  // no D8 row for 3.97 yet (evidence.yaml rows are a person's): the adopted rule shows no ◆
  assert.equal(badgeText(fast, RULES.adopted), "★ adopted base v55 · in v54..v55 (2)");
  assert.equal(badgeText(one, RULES.adopted), "◆ RDP prt_fild08 (3.92) · in v51..v52 (2)");
  assert.equal(badgeText(v50, RULES.adopted), "◆ RDP prt_fild08 (3.91) · in v50");
  assert.deepEqual(RULES.evidence.badges, ["one path (RDP), prt_fild08"]);
  const tip = huntTooltip(RULES, "unverified");
  assert.match(tip.split("\n")[0], /^hunt · L1: unverified · hunting evidence \(D8\): one path \(RDP\), prt_fild08$/);
  assert.match(tip, /loot gm_scan@50: .* loot_gm_stand_s=0\.5/);
});

test("engage_source: an option in the engage group, default detector, written only when changed", () => {
  const es = params(RULES).find((p) => p.name === "engage_source")!;
  assert.equal(es.kind, "option");
  assert.equal(es.required, false);
  assert.equal(es.default, "detector");
  assert.deepEqual(omitted(RULES), OMIT);
  const def = huntDef(RULES, COLOURS.action);
  assert.equal(def.message1, "engage: strike %1  engage on the way %2  engage source %3");
  const dd = (def.args1 ?? []).find((a) => "name" in a && a.name === "P_ENGAGE_SOURCE");
  assert.ok(dd && "options" in dd);
  assert.deepEqual(dd.options, [["detector (default)", "detector"], ["melee_ring", "melee_ring"]]);
  const [det, ring] = es.choices;
  assert.equal(badgeText(det, RULES.adopted), "option · the default (absent = this)");
  assert.equal(badgeText(ring, RULES.adopted), "option");
  assert.match(huntTooltip(RULES, "unverified"), /engage_source: detector: .*melee_ring: .*IGNORE/);
  // a person picks melee_ring: the IR gains engage_source="melee_ring", nothing else changes
  const flow = withHunt(ADOPTED);
  const ws = viaJson(toWorkspace(flow, FARM, { hunt: RULES }));
  first(ws).fields![fieldOf("engage_source")] = "melee_ring";
  const picked = fromWorkspace(flow, FARM, ws);
  assert.ok(picked.ok);
  assert.equal(canonical(picked.flow), canonical(withHunt({ ...ADOPTED, engage_source: "melee_ring" })));
  // ... it shows as the hunt block, and back to detector leaves the parameter out again (absent)
  const ws2 = viaJson(toWorkspace(picked.flow, FARM, { hunt: RULES }));
  assert.equal(first(ws2).type, HUNT_TYPE);
  assert.equal(first(ws2).fields![fieldOf("engage_source")], "melee_ring");
  first(ws2).fields![fieldOf("engage_source")] = "detector";
  const back = fromWorkspace(picked.flow, FARM, ws2);
  assert.ok(back.ok);
  assert.equal(canonical(back.flow), canonical(flow));
});

test("engage_source written AT its default, or not an option, stays a generic block, exactly", () => {
  for (const flow of [withHunt({ ...ADOPTED, engage_source: "detector" }), withHunt({ ...ADOPTED, engage_source: "cursor" })]) {
    const ws = toWorkspace(flow, FARM, { hunt: RULES });
    assert.equal(first(ws).type, "pl_action");
    const back = fromWorkspace(flow, FARM, viaJson(ws));
    assert.ok(back.ok);
    assert.equal(canonical(back.flow), canonical(flow));
  }
});

test("search_route: an option in the search group, default heading, written only when changed", () => {
  const sr = params(RULES).find((p) => p.name === "search_route")!;
  assert.equal(sr.kind, "option");
  assert.equal(sr.required, false);
  assert.equal(sr.default, "heading");
  const def = huntDef(RULES, COLOURS.action);
  assert.equal(def.message3, "search: search %1  search route %2");
  const dd = (def.args3 ?? []).find((a) => "name" in a && a.name === "P_SEARCH_ROUTE");
  assert.ok(dd && "options" in dd);
  assert.deepEqual(dd.options, [["heading (default)", "heading"], ["patrol_route", "patrol_route"]]);
  const [heading, patrol] = sr.choices;
  assert.equal(badgeText(heading, RULES.adopted), "option · the default (absent = this)");
  assert.equal(badgeText(patrol, RULES.adopted), "option");
  assert.match(huntTooltip(RULES, "unverified"), /search_route: heading: .*patrol_route: .*AHEAD/);
  // a person picks patrol_route: the IR gains search_route="patrol_route", nothing else changes
  const flow = withHunt(ADOPTED);
  const ws = viaJson(toWorkspace(flow, FARM, { hunt: RULES }));
  first(ws).fields![fieldOf("search_route")] = "patrol_route";
  const picked = fromWorkspace(flow, FARM, ws);
  assert.ok(picked.ok);
  assert.equal(canonical(picked.flow), canonical(withHunt({ ...ADOPTED, search_route: "patrol_route" })));
  // ... it shows as the hunt block, and back to heading leaves the parameter out again (absent)
  const ws2 = viaJson(toWorkspace(picked.flow, FARM, { hunt: RULES }));
  assert.equal(first(ws2).type, HUNT_TYPE);
  assert.equal(first(ws2).fields![fieldOf("search_route")], "patrol_route");
  first(ws2).fields![fieldOf("search_route")] = "heading";
  const back = fromWorkspace(picked.flow, FARM, ws2);
  assert.ok(back.ok);
  assert.equal(canonical(back.flow), canonical(flow));
  // both options at once: each written, each round-trips
  const both = withHunt({ ...ADOPTED, engage_source: "melee_ring", search_route: "patrol_route" });
  const ws3 = toWorkspace(both, FARM, { hunt: RULES });
  assert.equal(first(ws3).type, HUNT_TYPE);
  const again = fromWorkspace(both, FARM, viaJson(ws3));
  assert.ok(again.ok);
  assert.equal(canonical(again.flow), canonical(both));
});

test("search_route written AT its default, or not an option, stays a generic block, exactly", () => {
  for (const flow of [withHunt({ ...ADOPTED, search_route: "heading" }), withHunt({ ...ADOPTED, search_route: "spiral" })]) {
    const ws = toWorkspace(flow, FARM, { hunt: RULES });
    assert.equal(first(ws).type, "pl_action");
    const back = fromWorkspace(flow, FARM, viaJson(ws));
    assert.ok(back.ok);
    assert.equal(canonical(back.flow), canonical(flow));
  }
});
