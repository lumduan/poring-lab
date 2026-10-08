import assert from "node:assert/strict";
import { test } from "node:test";

import { BLOCK_DEFS, DEF_BY_TYPE, namesOf, toolbox } from "./blockdefs.ts";
import { fromWorkspace, type Scope, toWorkspace, type WsBlock, type Workspace } from "./blocks.ts";
import { canonical, clone, type Flow } from "./ir.ts";
import { FIXTURES, fixture, randomFlow } from "./testkit.ts";

function scopes(flow: Flow): Scope[] {
  const out: Scope[] = [{ kind: "global" }];
  if (flow.workflow) for (const b of flow.workflow.blocks) out.push({ kind: "block", name: b.name });
  else out.push({ kind: "main" });
  return out;
}

/** What a Blockly save/load cycle keeps: JSON (fields, inputs, next, extraState, ids). */
function viaJson(ws: Workspace): Workspace {
  return JSON.parse(JSON.stringify(ws)) as Workspace;
}

function roundTrip(flow: Flow): void {
  let cur = flow;
  for (const scope of scopes(flow)) {
    const back = fromWorkspace(cur, scope, viaJson(toWorkspace(cur, scope)));
    assert.ok(back.ok, `${flow.name} ${JSON.stringify(scope)}: ${!back.ok && back.errors.join("; ")}`);
    if (back.ok) {
      assert.deepEqual(back.warnings, []);
      assert.equal(canonical(back.flow), canonical(flow), `${flow.name} ${JSON.stringify(scope)}`);
      cur = back.flow;
    }
  }
}

function* allBlocks(b: WsBlock | undefined): Generator<WsBlock> {
  for (let cur = b; cur; cur = cur.next?.block) {
    yield cur;
    for (const inp of Object.values(cur.inputs ?? {})) yield* allBlocks(inp.block);
  }
}

test("IR -> blocks -> IR is exact for MW1's fixtures and the sample, every scope", () => {
  for (const name of FIXTURES) roundTrip(fixture(name));
});

test("IR -> blocks -> IR is exact for random flows within MW2's block set (seeded)", () => {
  for (let seed = 1; seed <= 300; seed++) roundTrip(randomFlow(seed));
});

test("the workspace uses only the fields, inputs and connections the block types define", () => {
  const types = new Set(BLOCK_DEFS.map((d) => d.type));
  const inputKind = (type: string, name: string): string | undefined => {
    if (type === "pl_logic" && /^T[0-9]+$/.test(name)) return "input_value";
    const d = DEF_BY_TYPE[type];
    for (const args of [d.args0, d.args1, d.args2, d.args3]) {
      for (const a of args ?? []) if ("name" in a && a.name === name) return a.type;
    }
    return undefined;
  };
  const check = (flow: Flow) => {
    for (const scope of scopes(flow)) {
      for (const top of toWorkspace(flow, scope).blocks.blocks) {
        const td = DEF_BY_TYPE[top.type];
        assert.ok(td && td.previousStatement === undefined && td.output === undefined, `hat ${top.type}`);
        for (const b of allBlocks(top)) {
          assert.ok(types.has(b.type), b.type);
          const n = namesOf(b.type);
          for (const f of Object.keys(b.fields ?? {})) assert.ok(n.saved.has(f), `${b.type}.${f}`);
          for (const [i, inp] of Object.entries(b.inputs ?? {})) {
            assert.ok(n.inputs.has(i), `${b.type}.${i}`);
            const child = DEF_BY_TYPE[inp.block!.type];
            if (inputKind(b.type, i) === "input_value") assert.ok(child.output === null, `${inp.block!.type} in ${b.type}.${i}`);
            else assert.ok(child.previousStatement === null, `${inp.block!.type} in ${b.type}.${i}`);
          }
          if (b.next) assert.ok(DEF_BY_TYPE[b.type].nextStatement === null && DEF_BY_TYPE[b.next.block!.type].previousStatement === null);
        }
      }
    }
  };
  for (const name of FIXTURES) check(fixture(name));
  for (let seed = 1; seed <= 50; seed++) check(randomFlow(seed));
});

test("the sample shows MW2's palette blocks with node-path ids", () => {
  const flow = fixture("town_warp_farm");
  const ws = toWorkspace(flow, { kind: "block", name: "town" });
  const types = [...allBlocks(ws.blocks.blocks[0])].map((b) => [b.id, b.type]);
  assert.deepEqual(types.slice(0, 5), [
    ["h:main", "pl_main"],
    ["n:town.0", "pl_walk_to"],
    ["n:town.1", "pl_action"],
    ["n:town.2", "pl_open_window"],
    ["n:town.3", "pl_walk_to"],
  ]);
  const ids = types.map(([id]) => id).filter(Boolean);
  assert.ok(ids.includes("n:town.4") && ids.includes("n:town.5:choose_menu") && ids.includes("n:town.9"));
  assert.ok(types.some(([id, t]) => id === "n:town.7" && t === "pl_wait"));
  assert.ok(types.some(([id, t]) => id === "n:town.9" && t === "pl_exit_npc"));
  const farm = toWorkspace(flow, { kind: "block", name: "farm" }).blocks.blocks;
  assert.deepEqual(
    farm.map((b) => [b.type, b.id]),
    [["pl_main", "h:main"], ["pl_event", "h:farm_hp_low"], ["pl_event", "h:boss_seen"]],
  );
  const town = toWorkspace(flow, { kind: "block", name: "town" }).blocks.blocks;
  assert.deepEqual(town.map((b) => [b.type, b.id]), [["pl_main", "h:main"], ["pl_disable", "h:disable:hp_low"]]);
});

test("an edit in the blocks lands in the IR", () => {
  const flow = fixture("town_warp_farm");
  const scope: Scope = { kind: "block", name: "town" };
  const ws = viaJson(toWorkspace(flow, scope));
  const walk = [...allBlocks(ws.blocks.blocks[0])].find((b) => b.id === "n:town.0")!;
  walk.fields!.X = 57;
  const r = fromWorkspace(flow, scope, ws);
  assert.ok(r.ok);
  if (!r.ok) return;
  const s = r.flow.workflow!.blocks[0].main[0];
  assert.equal(s.kind === "action" && s.params.cell.kind === "lit" && (s.params.cell.value as { x: number }).x, 57);
  // the original is untouched
  const o = flow.workflow!.blocks[0].main[0];
  assert.equal(o.kind === "action" && (o.params.cell as { value: { x: number } }).value.x, 55);
});

test("bad fields are refused with their node, and nothing is applied", () => {
  const flow = fixture("town_warp_farm");
  const scope: Scope = { kind: "block", name: "farm" };
  const ws = viaJson(toWorkspace(flow, scope));
  const blocks = ws.blocks.blocks.flatMap((t) => [...allBlocks(t)]);
  const hp = blocks.find((b) => b.type === "pl_event")!;
  hp.inputs!.WHEN = { block: { type: "pl_expr", fields: { TEXT: "hp_percent( <" } } };
  const exit = blocks.find((b) => b.type === "pl_exit_item")!;
  exit.fields!.TO_BLOCK = "not a name";
  const r = fromWorkspace(flow, scope, ws);
  assert.equal(r.ok, false);
  if (r.ok) return;
  assert.ok(r.errors.some((e) => e.startsWith("hp_low: when:")), r.errors.join("; "));
  assert.ok(r.errors.some((e) => e.startsWith("farm.1: to_block")), r.errors.join("; "));
});

test("new blocks from the toolbox take the catalogue's defaults", () => {
  const flow = fixture("visit_and_choose");
  const tb = toolbox({ walk_to: { concept: "nav.walk_to", timeout_s: 120 }, respawn: { concept: "char.respawn", timeout_s: 30 } }, "main");
  const skills = tb.contents.find((c) => c.name === "Skills")!.contents;
  const walk = skills.find((i) => i.type === "pl_walk_to")!;
  const ws: Workspace = {
    blocks: {
      languageVersion: 0,
      blocks: [
        {
          type: "pl_main",
          inputs: {
            DO: {
              block: {
                type: "pl_walk_to",
                fields: { MAP: "prt_fild08", X: 1, Y: 2 },
                extraState: walk.extraState,
                next: { block: { type: "pl_wait", fields: { SECONDS: 3 } } },
              },
            },
          },
        },
        { type: "pl_stop", fields: { REASON: "x" } }, // a loose block
      ],
    },
  };
  const r = fromWorkspace(flow, { kind: "main" }, ws);
  assert.ok(r.ok);
  if (!r.ok) return;
  assert.deepEqual(r.warnings, ["1 loose block(s) outside any hat were not applied"]);
  assert.deepEqual(r.flow.main, [
    { kind: "action", block: "walk_to", concept: "nav.walk_to", timeout_s: 120, on_fail: "stop", outcome_to: null, note: null,
      params: { cell: { kind: "lit", value: { kind: "cell", map: "prt_fild08", x: 1, y: 2 } } } },
    { kind: "wait_until", cond: { kind: "lit", value: false }, timeout_s: 3, outcome_to: null },
  ]);
  assert.equal(canonical(r.flow.handlers), canonical(flow.handlers));
});

test("a map event dragged in becomes an override of a global key, else a map-only event", () => {
  const flow = fixture("town_warp_farm");
  const scope: Scope = { kind: "block", name: "town" };
  const ws = viaJson(toWorkspace(flow, scope));
  const hat = (name: string): WsBlock => ({
    type: "pl_event",
    fields: { SCOPE: "map", NAME: name, PRIORITY: "survival", MODE: "preempt", THEN: "resume" },
    inputs: { WHEN: { block: { type: "pl_expr", fields: { TEXT: "hp_percent() < 30" } } }, DO: { block: { type: "pl_stop", fields: { REASON: "low" } } } },
  });
  ws.blocks.blocks.push(hat("hp_low"), hat("town_only"));
  const r = fromWorkspace(clone(flow), scope, ws);
  assert.ok(r.ok);
  if (!r.ok) return;
  const evs = r.flow.workflow!.blocks[0].events;
  assert.deepEqual(evs.map((e) => [e.kind, e.kind === "override" || e.kind === "add" ? e.label : null]), [
    ["disable", null],
    ["override", "town_hp_low"],
    ["add", "town_only"],
  ]);
});
