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
import { badgeText, defaultFields, fieldOf, HUNT_TYPE, huntDef, type HuntRules, huntTooltip, params } from "./hunt.ts";
import { action, canonical, clone, type Flow, lit } from "./ir.ts";
import { fixture } from "./testkit.ts";

const RULES = JSON.parse(readFileSync(new URL("./fixtures/hunt_rules.json", import.meta.url), "utf8")) as HuntRules;
const ADOPTED = { strike: "arm_c@32", engage_on_the_way: "on_the_way@19", dead: "exp_line@48", loot: "gm_fast_scan@54", search: "heading_coverage@22" }; // the adopted base v55 (3.97; v52 until 10-22 04:32)
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
  assert.deepEqual(Object.fromEntries(params(RULES).map((p) => [p.name, p.default])), ADOPTED);
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
  assert.deepEqual(b.fields, Object.fromEntries(Object.entries(ADOPTED).map(([k, v]) => [fieldOf(k), v])));
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
  const tb = toolbox({ hunt: { concept: "combat.hunt", timeout_s: 600 }, walk_to: { concept: "nav.walk_to", timeout_s: 120 } }, "block", defaultFields(RULES));
  const item = tb.contents.find((c) => c.name === "More skills")!.contents.find((i) => i.type === HUNT_TYPE);
  assert.ok(item);
  assert.deepEqual(item.fields, defaultFields(RULES));
  const flow = clone(fixture("town_warp_farm"));
  const ws = viaJson(toWorkspace(flow, FARM, { hunt: RULES }));
  const dragged: WsBlock = { type: HUNT_TYPE, id: "fresh", fields: defaultFields(RULES) };
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
