import assert from "node:assert/strict";
import { test } from "node:test";

import { BLOCK_DEFS, blockOf, categoryOf, DEF_BY_TYPE, namesOf, toolbox } from "./blockdefs.ts";
import { fromWorkspace, type Scope, toWorkspace, type WsBlock, type Workspace } from "./blocks.ts";
import { canonical, clone, type Expr, type Flow, type Stmt } from "./ir.ts";
import { blockWords } from "./words.ts";
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
    for (const args of [d.args0, d.args1, d.args2, d.args3, d.args4, d.args5, d.args6, d.args7, d.args8]) {
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
            // a value block: any output (null, or the model blocks' "Boolean" / "Number" shapes)
            if (inputKind(b.type, i) === "input_value") assert.ok(child.output !== undefined, `${inp.block!.type} in ${b.type}.${i}`);
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
    ["n:town.1", "pl_set_save_point"], // a sentence block since 2026-11-09 pm (Actions)
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
  const tb = toolbox({ walk_to: { concept: "nav.walk_to", timeout_s: 120 }, respawn: { concept: "char.respawn", timeout_s: 30 } }, { node: "map", main: true });
  const walk = blockOf(categoryOf(tb, "Movement"), "pl_walk_to")!; // MatPilot's categories (2026-11-09)
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

// --- the studio (2026-11-09): the model blocks, live paths, issues and detached stacks ------------
const DETECT_FLOW = (): Flow => {
  const f = clone(fixture("visit_and_choose"));
  const sees = { kind: "sense" as const, sensor: "detector_sees", args: { label: { kind: "lit" as const, value: "monster" }, model: { kind: "lit" as const, value: "v1" } } };
  const count = { kind: "sense" as const, sensor: "detector_count", args: { label: { kind: "lit" as const, value: "cookie_xmas" }, model: { kind: "lit" as const, value: "xmas02" } } };
  f.main = [
    { kind: "wait_until", cond: sees, timeout_s: 30, outcome_to: null },
    { kind: "if", cond: { kind: "cmp", op: ">", left: count, right: { kind: "lit", value: 2 } }, then: [{ kind: "stop", reason: "many" }], orelse: [] },
    ...(f.main ?? []),
  ];
  return f;
};

test("a detector sensor shows as the model block, and converts back exactly", () => {
  const flow = DETECT_FLOW();
  const ws = toWorkspace(flow, { kind: "main" });
  const all = [...allBlocks(ws.blocks.blocks[0])];
  const sees = all.find((b) => b.type === "pl_detect_sees");
  const count = all.find((b) => b.type === "pl_detect_count");
  assert.deepEqual(sees?.fields, { MODEL: "v1", CLASS: "monster" });
  assert.deepEqual(count?.fields, { MODEL: "xmas02", CLASS: "cookie_xmas" });
  assert.equal(DEF_BY_TYPE.pl_detect_sees.output, "Boolean"); // a question: a hexagon
  assert.equal(DEF_BY_TYPE.pl_detect_count.output, "Number"); // a value: round
  roundTrip(flow);
  // not two text literals: kept exactly as a text expression
  const odd = clone(flow);
  const w = odd.main![0];
  if (w.kind === "wait_until" && w.cond.kind === "sense") w.cond.args.model = { kind: "var", name: "M" };
  odd.variables = { ...odd.variables, M: { kind: "lit", value: "v1" } };
  const oddWs = toWorkspace(odd, { kind: "main" });
  assert.equal(allBlocks(oddWs.blocks.blocks[0]).next().value?.inputs?.DO?.block?.inputs?.COND?.block?.type, "pl_expr");
  roundTrip(odd);
});

test("a bad model or class is refused with its block's id", () => {
  const flow = DETECT_FLOW();
  const ws = viaJson(toWorkspace(flow, { kind: "main" }));
  const sees = [...allBlocks(ws.blocks.blocks[0])].find((b) => b.type === "pl_detect_sees")!;
  sees.fields!.MODEL = "Not A Model";
  const r = fromWorkspace(flow, { kind: "main" }, ws);
  assert.equal(r.ok, false);
  if (r.ok) return;
  assert.ok(r.issues.some((i) => i.id === "n:main.0" && /not a model id/.test(i.text)), JSON.stringify(r.issues));
});

test("after an edit, every block knows its NEW node path", () => {
  const flow = fixture("town_warp_farm");
  const scope: Scope = { kind: "block", name: "town" };
  const ws = viaJson(toWorkspace(flow, scope));
  const main = ws.blocks.blocks[0];
  // a new block at the top of the town's main: every old block moves down by one
  const first = main.inputs!.DO!.block!;
  main.inputs!.DO!.block = { type: "pl_wait", id: "fresh", fields: { SECONDS: 2 }, next: { block: first } };
  const r = fromWorkspace(flow, scope, ws);
  assert.ok(r.ok);
  if (!r.ok) return;
  assert.equal(r.paths.fresh, "town.0");
  assert.equal(r.paths["n:town.0"], "town.1");
  assert.equal(r.paths["n:town.9"], "town.10");
  assert.equal(r.paths["h:main"], "town");
  // a map event's body hangs from its label (ir.event_label), as the IR's node paths do
  const farm = viaJson(toWorkspace(flow, { kind: "block", name: "farm" }));
  const fr = fromWorkspace(flow, { kind: "block", name: "farm" }, farm);
  assert.ok(fr.ok);
  if (fr.ok) assert.ok(Object.entries(fr.paths).some(([id, p]) => id.startsWith("n:farm_hp_low.") && p.startsWith("farm_hp_low.")), JSON.stringify(fr.paths));
});

test("detached stacks are listed with their words, top block and size", () => {
  const flow = fixture("visit_and_choose");
  const ws: Workspace = {
    blocks: {
      languageVersion: 0,
      blocks: [
        { type: "pl_main", inputs: {} },
        { type: "pl_walk_to", id: "lost", fields: { MAP: "prontera", X: 150, Y: 180 }, next: { block: { type: "pl_wait", fields: { SECONDS: 1 } } } },
        { type: "pl_detect_sees", id: "q", fields: { MODEL: "v1", CLASS: "monster" } },
      ],
    },
  };
  const r = fromWorkspace(flow, { kind: "main" }, ws, { walk_to: { concept: "nav.walk_to", timeout_s: 120 } });
  assert.ok(r.ok);
  if (!r.ok) return;
  assert.deepEqual(r.loose.map((l) => [l.id, l.count, l.value]), [["lost", 2, false], ["q", 1, true]]);
  assert.match(r.loose[0].words, /^walk\sto\sprontera\sx\s150\sy\s180$/);
  assert.match(r.loose[1].words, /^detector\sv1\ssees\smonster$/);
});

// --- the shop / Kafra / storage sentences (2026-11-09 pm) -------------------------------------
test("shop and Kafra actions show as sentences and convert back exactly; anything else stays generic", () => {
  const act = (block: string, concept: string, params: Record<string, Expr>): Stmt => ({
    kind: "action", block, concept, params, timeout_s: 60, on_fail: "stop", outcome_to: null, note: null,
  });
  const npc = (key: string): Expr => ({ kind: "lit", value: { kind: "npc", key } });
  const ids = (...n: number[]): Expr => ({ kind: "lit", value: n.map((id) => ({ kind: "item" as const, id })) });
  const flow = clone(fixture("visit_and_choose"));
  flow.variables = { ...flow.variables, WING: { kind: "lit", value: { kind: "item", id: 9002 } }, KEEP: { kind: "lit", value: [{ kind: "item", id: 1 }] } };
  flow.main = [
    act("buy", "trade.buy", { npc: npc("n_shop"), items: ids(501, 502) }),
    act("sell", "trade.sell", { npc: npc("n_shop"), keep: { kind: "list", items: [{ kind: "lit", value: { kind: "item", id: 501 } }, { kind: "var", name: "WING" }] } }),
    act("kafra_store", "storage.deposit", { npc: npc("n_k1"), all_except: ids(9002) }),
    act("kafra_store", "storage.deposit", { npc: npc("n_k1") }),
    act("kafra_teleport", "nav.kafra_teleport", { npc: npc("n_k1"), to: { kind: "lit", value: { kind: "map", map: "geffen" } } }),
    act("set_save_point", "nav.set_save_point", { npc: npc("n_k1") }),
    // not a sentence's shape: a list variable, an empty list, an extra parameter -> generic
    act("sell", "trade.sell", { npc: npc("n_shop"), keep: { kind: "var", name: "KEEP" } }),
    act("buy", "trade.buy", { npc: npc("n_shop"), items: ids() }),
    act("set_save_point", "nav.set_save_point", { npc: npc("n_k1"), within: { kind: "lit", value: 3 } }),
    ...(flow.main ?? []),
  ];
  const ws = toWorkspace(flow, { kind: "main" });
  const types = [...allBlocks(ws.blocks.blocks[0])].slice(1, 10).map((b) => b.type);
  assert.deepEqual(types, ["pl_buy", "pl_sell", "pl_kafra_store", "pl_kafra_store", "pl_kafra_teleport", "pl_set_save_point", "pl_action", "pl_action", "pl_action"]);
  const sell = [...allBlocks(ws.blocks.blocks[0])][2];
  assert.deepEqual(sell.fields, { NPC: "n_shop", KEEP: "501, WING" });
  assert.match(blockWords(sell), /^sell\sall\sbut\s501,\sWING\sto\sn_shop$/);
  assert.match(blockWords([...allBlocks(ws.blocks.blocks[0])][1]), /^buy\s501,\s502\sfrom\sn_shop$/);
  roundTrip(flow);
  // a learner's edit: items typed as text
  const edited = viaJson(ws);
  const buy = [...allBlocks(edited.blocks.blocks[0])][1];
  buy.fields!.ITEMS = "607, WING";
  const r = fromWorkspace(flow, { kind: "main" }, edited);
  assert.ok(r.ok);
  if (r.ok) {
    const s0 = r.flow.main![0];
    assert.ok(s0.kind === "action" && s0.params.items.kind === "list" && s0.params.items.items.length === 2);
  }
  buy.fields!.ITEMS = "";
  const bad = fromWorkspace(flow, { kind: "main" }, edited);
  assert.ok(!bad.ok && bad.issues.some((i) => /at least one item/.test(i.text)));
});

test("Actions holds the shop and Kafra sentences, after the four NPC / item / window actions", () => {
  const cat = Object.fromEntries(
    ["talk_npc", "choose_menu", "use_item", "open_window", "buy", "sell", "kafra_store", "set_save_point", "sit"].map((n) => [n, { concept: "x.y", timeout_s: 60 }]),
  );
  const tb = toolbox(cat, { node: "map", main: true });
  const actions = categoryOf(tb, "Actions")!.contents.filter((i) => i.kind === "block").map((i) => (i as { type: string }).type);
  assert.deepEqual(actions, ["pl_talk_npc", "pl_choose_menu", "pl_use_item", "pl_open_window", "pl_set_save_point", "pl_kafra_store", "pl_buy", "pl_sell"]);
  const more = categoryOf(tb, "More skills")!.contents.map((i) => (i as { fields?: { BLOCK?: string } }).fields?.BLOCK);
  assert.deepEqual(more, ["sit"]);
  for (const t of actions) assert.equal(DEF_BY_TYPE[t].style, "mp_output_blocks", t); // matpilot's output blue
});
