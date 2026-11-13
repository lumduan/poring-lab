// THE WORLD RULES (Batt 2026-11-13): settings for EVERY map of a flow, set once on the Maps page.
//
// 1. The SAVE POINT: where a Butterfly Wing (and a death) lands. "This value we can set as a
//    global." Stored as the engine's own `assert_save_point(cell)` as the FIRST step of the start
//    block, so the linter knows it from the run's first step (lint/simulate.py, 2026-11-13). A
//    `set_save_point` at a Kafra elsewhere in the flow still wins from where it runs.
// 2. AN UNKNOWN MAP: "a guard against walking into a teleport by accident: on a map we do not know,
//    press a Butterfly Wing back to the save town." Stored as the flow's own `unexpected_map` event:
//    the built-in (read the position, relocate; always_on.py) made STRICTER, as the linter allows:
//    the same trigger, class and `then`, its body starts with the built-in's step, plus a limit of
//    MAX_PER_RUN. Its body adds ONE step: on a map none of the flow's blocks is on (and not the
//    save point's map: a wing there would land on the same map again), use the Butterfly Wing.
//    Then `relocate` picks the save town's block; a town without a block stops the run there.
//    Off: the built-in, which stops the run on an unknown map (relocate_no_block).
//
// Both are visible on /flows as ordinary blocks (the start block's first step; the events tab), and
// round-trip through the Python view. Pure functions, tested in rules.test.ts.
import { type ActionStmt, type CellRef, clone, type Expr, type Flow, type Handler, type ItemRef, type Stmt, type Var } from "../flow/ir.ts";
import { knownMaps } from "./links.ts";

export const WING_ID = 602; // Butterfly Wing (the lab's rAthena item db)
export const MAX_PER_RUN = 3;
export const RULE_NOTE = "the world rule: on an unknown map, a Butterfly Wing to the save point";
export const SAVE_NOTE = "the world rule: the save point (where a Butterfly Wing and a death land)";

export type UnknownMap = "stop" | "wing";
export type SavePoint = { cell: CellRef | null; asserted: boolean };
/** What the rule uses for the wing: an item (a variable or a literal), or the FUNCTION a Butterfly
 * Wing exit of the flow calls (Batt 2026-11-13: "every key a function"). */
export type Wing = ItemRef | Var | { kind: "proc"; name: string };
export type Rules = { savePoint: SavePoint; unknownMap: UnknownMap; custom: boolean; wingItem: Wing };

const act = (block: string, concept: string, params: ActionStmt["params"], note: string | null = null, timeout_s = 10): ActionStmt => ({
  kind: "action",
  block,
  concept,
  timeout_s,
  on_fail: "stop",
  outcome_to: null,
  note,
  params,
});

/** What a Butterfly Wing exit of the flow uses: its function, or its item (a variable or a
 * literal); else the lab's 602. */
export function wingItem(flow: Flow): Wing {
  for (const b of flow.workflow?.blocks ?? []) {
    const stack: Stmt[] = [...b.main];
    while (stack.length) {
      const s = stack.shift() as Stmt;
      if (s.kind === "take_exit" && s.exit.kind === "item_warp" && s.exit.proc) return { kind: "proc", name: s.exit.proc };
      if (s.kind === "take_exit" && s.exit.kind === "item_warp" && s.exit.item) return s.exit.item;
      if (s.kind === "if") stack.push(...s.then, ...s.orelse);
      if (s.kind === "while" || s.kind === "repeat" || s.kind === "for") stack.push(...s.body);
    }
  }
  return { kind: "item", id: WING_ID };
}

function isAssert(s: Stmt | undefined): s is ActionStmt {
  return !!s && s.kind === "action" && s.block === "assert_save_point";
}

function cellOf(e: Expr | undefined): CellRef | null {
  if (e?.kind !== "lit") return null;
  const v = e.value;
  return v && typeof v === "object" && !Array.isArray(v) && v.kind === "cell" ? v : null;
}

/** The unknown-map rule as this module writes it, for `maps` and the save map. */
export function unknownMapRule(maps: string[], saveMap: string | null, item: Wing): Handler {
  const avoid = [...new Set([...maps, ...(saveMap ? [saveMap] : [])])].sort();
  return {
    name: "unexpected_map",
    when: { kind: "sense", sensor: "map_load_seen", args: {} },
    until: null,
    rearm: null,
    priority: "critical",
    rank: null,
    mode: "preempt",
    escalate: null,
    max_insert_fails: 3,
    cooldown_s: 0,
    max_per_min: null,
    max_fires_per_10min: 10,
    max_per_run: MAX_PER_RUN,
    then: "relocate",
    body: [
      act("read_position", "nav.read_position", {}),
      {
        kind: "if",
        cond: {
          kind: "cmp",
          op: "not in",
          left: { kind: "sense", sensor: "current_map", args: {} },
          right: { kind: "lit", value: avoid.map((m) => ({ kind: "map" as const, map: m })) },
        },
        then: [
          item.kind === "proc"
            ? { kind: "call", proc: item.name }
            : act("use_item", "item.use", { item: item.kind === "var" ? item : { kind: "lit", value: item } }, RULE_NOTE),
        ],
        orelse: [],
      },
    ],
  };
}

function isOurRule(h: Handler): boolean {
  const s = h.body[1];
  return (
    h.name === "unexpected_map" &&
    h.body.length === 2 &&
    h.body[0].kind === "action" &&
    h.body[0].block === "read_position" &&
    s?.kind === "if" &&
    s.then.length === 1 &&
    ((s.then[0].kind === "action" && s.then[0].block === "use_item") || s.then[0].kind === "call") &&
    s.orelse.length === 0
  );
}

/** What the flow says today. `custom`: it writes its own unexpected_map that is not this module's
 * rule (shown, never overwritten without asking). */
export function readRules(flow: Flow): Rules {
  const wf = flow.workflow;
  const start = wf?.blocks.find((b) => b.name === wf.start_block);
  const first = start?.main[0];
  const savePoint: SavePoint = isAssert(first) ? { cell: cellOf(first.params.cell), asserted: true } : { cell: null, asserted: false };
  const h = flow.handlers.find((x) => x.name === "unexpected_map");
  return { savePoint, unknownMap: h && isOurRule(h) ? "wing" : "stop", custom: !!h && !isOurRule(h), wingItem: wingItem(flow) };
}

export type RuleEdit = { ok: true; flow: Flow } | { ok: false; error: string };

/** Set (a cell) or clear (null) the save point stated at the run's first step. */
export function setSavePoint(flow: Flow, cell: CellRef | null): RuleEdit {
  const out = clone(flow);
  const wf = out.workflow;
  if (!wf) return { ok: false, error: "a plain flow has no maps: Load a workflow first" };
  const start = wf.blocks.find((b) => b.name === wf.start_block);
  if (!start) return { ok: false, error: `the start block ${wf.start_block} is missing` };
  const has = isAssert(start.main[0]);
  if (cell === null) {
    if (has) start.main.shift();
  } else {
    if (!/^[a-z0-9_@-]{1,40}$/i.test(cell.map) || !Number.isInteger(cell.x) || !Number.isInteger(cell.y) || cell.x < 0 || cell.y < 0 || cell.x > 1000 || cell.y > 1000) {
      return { ok: false, error: "the save point needs a map id and a cell (x, y) between 0 and 1000" };
    }
    const stmt = act("assert_save_point", "core.assert_save_point", { cell: { kind: "lit", value: { ...cell, kind: "cell" } } }, SAVE_NOTE, 1);
    if (has) start.main[0] = stmt;
    else start.main.unshift(stmt);
  }
  return { ok: true, flow: refreshRule(out) };
}

/** Turn the unknown-map rule on (a wing home) or off (the built-in: stop). A flow's own different
 * unexpected_map is replaced only with `replaceCustom`. */
export function setUnknownMap(flow: Flow, to: UnknownMap, replaceCustom = false): RuleEdit {
  const r = readRules(flow);
  if (r.custom && !replaceCustom) return { ok: false, error: "this flow writes its own unexpected_map event: change it on /flows (the events tab), or replace it" };
  const out = clone(flow);
  if (!out.workflow) return { ok: false, error: "a plain flow has no maps: Load a workflow first" };
  out.handlers = out.handlers.filter((h) => h.name !== "unexpected_map");
  if (to === "wing") out.handlers.push(unknownMapRule(knownMaps(out), saveMapOf(out), wingItem(out)));
  return { ok: true, flow: out };
}

/** The save point's map as the rules know it: the stated one, else none (a Kafra's is the flow's). */
function saveMapOf(flow: Flow): string | null {
  return readRules(flow).savePoint.cell?.map ?? null;
}

/** Keep the rule's list of known maps current after the flow's maps changed (a map added,
 * removed, renamed): a no-op when the rule is off or custom. */
export function refreshRule(flow: Flow): Flow {
  const i = flow.handlers.findIndex((h) => h.name === "unexpected_map" && isOurRule(h));
  if (i < 0 || !flow.workflow) return flow;
  const want = unknownMapRule(knownMaps(flow), saveMapOf(flow), wingItem(flow));
  if (JSON.stringify(want) === JSON.stringify(flow.handlers[i])) return flow;
  const out = clone(flow);
  out.handlers[i] = want;
  return out;
}

/** The maps the rule treats as known (no wing there), for the panel's words. */
export function ruleMaps(flow: Flow): string[] {
  const h = flow.handlers.find((x) => x.name === "unexpected_map" && isOurRule(x));
  const s = h?.body[1];
  if (!s || s.kind !== "if" || s.cond.kind !== "cmp" || s.cond.right.kind !== "lit" || !Array.isArray(s.cond.right.value)) return [];
  return s.cond.right.value.flatMap((r) => (r.kind === "map" ? [r.map] : []));
}
