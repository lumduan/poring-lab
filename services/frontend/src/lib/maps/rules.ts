// THE WORLD RULES (Batt 2026-11-13): settings for EVERY map of a project, set once on the Maps page,
// written into the PROJECT as ordinary code (docs/planning/project-model.md), so /flows shows them
// and the engine lints and simulates them:
//
// 1. The SAVE POINT: where a Butterfly Wing (and a death) lands. "This value we can set as a
//    global." Stored as the engine's own `assert_save_point(cell)`, the FIRST statement of the
//    START map's main (the map the session path enters; project.ts sessionPath), so the linter
//    knows it from the run's first step. A `set_save_point` at a Kafra elsewhere still wins from
//    where it runs.
// 2. AN UNKNOWN MAP: "a guard against walking into a teleport by accident: on a map we do not know,
//    press a Butterfly Wing back to the save town." Stored as a GLOBAL EVENT, a def named
//    `unexpected_map` with a trigger (project.ts Def / Trigger): the built-in (read the position,
//    relocate; always_on.py) made STRICTER, as the linter allows -- the same trigger, class and
//    `then`, its body starting with the built-in's step, at most MAX_PER_RUN a run. Its one added
//    step: on a map none of the map nodes is on (and not the save point's map), call the wing's
//    FUNCTION (the one a map's item warp names), else use_item(602). Off: the built-in, which
//    stops the run on an unknown map (relocate_no_block). A map node's own unexpected_map
//    OVERRIDES it there (project-model.md section 3) and is never touched here; a different Global
//    unexpected_map is never overwritten unasked.
//
// Pure functions, tested in links.test.ts.
import { type ActionStmt, type CellRef, clone, type Expr, type ItemRef, type Var } from "../flow/ir.ts";
import {
  call,
  type Def,
  GLOBAL_ID,
  globalOf,
  type GlobalNode,
  MAIN_TAB,
  mapNodes,
  newTabName,
  nodeSites,
  overriddenBy,
  type Project,
  SAVE_NOTE,
  sessionPath,
  type Tab,
  tabNameProblem,
  type Trigger,
} from "../flow/project.ts";
import { knownMaps } from "./links.ts";

export const WING_ID = 602; // Butterfly Wing (the lab's rAthena item db)
export const MAX_PER_RUN = 3;
export const RULE_NOTE = "the world rule: on an unknown map, a Butterfly Wing to the save point";
export const RULE_NAME = "unexpected_map";
export const RULE_TAB = "safety"; // where a new rule goes in Global (its tab, when it has one already)
export { SAVE_NOTE };

export type UnknownMap = "stop" | "wing";
export type SavePoint = { cell: CellRef | null; asserted: boolean };
/** What the rule uses for the wing: the FUNCTION a Butterfly Wing exit calls (Batt 2026-11-13:
 * "every key a function"), else its item (a variable or a literal), else the lab's 602. */
export type Wing = ItemRef | Var | { kind: "proc"; name: string };
export type Rules = {
  savePoint: SavePoint;
  startMap: string | null; // the start map NODE's id (null: the session path is broken)
  unknownMap: UnknownMap;
  custom: boolean; // Global has its own, different unexpected_map
  tab: string | null; // the Global tab that holds the rule (ours or custom)
  overriddenOn: string[]; // map nodes with their own unexpected_map (theirs runs there)
  wingItem: Wing;
};
export type RuleEdit = { ok: true; project: Project } | { ok: false; error: string };

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

/** What a Butterfly Wing exit of the project uses: its function, or its item; else 602. */
export function wingItem(p: Project): Wing {
  for (const n of mapNodes(p)) {
    for (const { stmt: s } of nodeSites(n)) {
      if (s.kind !== "take_exit" || s.exit.kind !== "item_warp") continue;
      if (s.exit.proc) return { kind: "proc", name: s.exit.proc };
      if (s.exit.item) return s.exit.item;
    }
  }
  return { kind: "item", id: WING_ID };
}

const isAssert = (s: unknown): s is ActionStmt => !!s && (s as ActionStmt).kind === "action" && (s as ActionStmt).block === "assert_save_point";

function cellOf(e: Expr | undefined): CellRef | null {
  if (e?.kind !== "lit") return null;
  const v = e.value;
  return v && typeof v === "object" && !Array.isArray(v) && v.kind === "cell" ? v : null;
}

/** The unknown-map rule's trigger: the built-in's (map_load_seen, CRITICAL, preempt, relocate). */
export function ruleTrigger(): Trigger {
  return {
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
  };
}

/** The unknown-map rule as this module writes it, for `maps` and the save map. */
export function unknownMapDef(maps: string[], saveMap: string | null, item: Wing): Def {
  const avoid = [...new Set([...maps, ...(saveMap ? [saveMap] : [])])].sort();
  return {
    name: RULE_NAME,
    params: [],
    varargs: null,
    kwargs: null,
    on: ruleTrigger(),
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
        then: [item.kind === "proc" ? call(item.name) : act("use_item", "item.use", { item: item.kind === "var" ? item : { kind: "lit", value: item } }, RULE_NOTE)],
        orelse: [],
      },
    ],
  };
}

/** Whether a def is this module's rule (any known maps, any wing). */
export function isOurRule(d: Def): boolean {
  const s = d.body[1];
  return (
    d.name === RULE_NAME &&
    d.on !== null &&
    d.params.length === 0 &&
    d.body.length === 2 &&
    d.body[0].kind === "action" &&
    d.body[0].block === "read_position" &&
    s?.kind === "if" &&
    s.then.length === 1 &&
    ((s.then[0].kind === "action" && s.then[0].block === "use_item") || s.then[0].kind === "call") &&
    s.orelse.length === 0
  );
}

/** Global's unexpected_map and its tab, when it has one. */
function globalRule(p: Project): { tab: Tab; def: Def } | null {
  for (const t of globalOf(p)?.tabs ?? []) for (const d of t.defs) if (d.name === RULE_NAME) return { tab: t, def: d };
  return null;
}

/** What the project says today. */
export function readRules(p: Project): Rules {
  const start = sessionPath(p).map;
  const first = start?.tabs.find((t) => t.name === MAIN_TAB)?.main?.[0];
  const savePoint: SavePoint = isAssert(first) ? { cell: cellOf(first.params.cell), asserted: true } : { cell: null, asserted: false };
  const g = globalRule(p);
  return {
    savePoint,
    startMap: start?.id ?? null,
    unknownMap: g && isOurRule(g.def) ? "wing" : "stop",
    custom: !!g && !isOurRule(g.def),
    tab: g?.tab.name ?? null,
    overriddenOn: overriddenBy(p, RULE_NAME),
    wingItem: wingItem(p),
  };
}

const CELL_MAP = /^[a-z0-9_@-]{1,40}$/i;

/** Set (a cell) or clear (null) the save point stated at the start map's first statement. */
export function setSavePoint(p: Project, cell: CellRef | null): RuleEdit {
  const out = clone(p);
  const sp = sessionPath(out);
  if (!sp.map) return { ok: false, error: `the save point is the START map's first step, and the session path does not reach a map yet (${sp.problems[0] ?? "connect login → character → a map"})` };
  const main = sp.map.tabs.find((t) => t.name === MAIN_TAB);
  if (!main?.main) return { ok: false, error: `${sp.map.id} has no main tab` };
  const has = isAssert(main.main[0]);
  if (cell === null) {
    if (has) main.main.shift();
    if (main.main.length === 0) main.main.push({ kind: "stop", reason: "done" });
  } else {
    if (!CELL_MAP.test(cell.map) || !Number.isInteger(cell.x) || !Number.isInteger(cell.y) || cell.x < 0 || cell.y < 0 || cell.x > 1000 || cell.y > 1000) {
      return { ok: false, error: "the save point needs a map id and a cell (x, y) between 0 and 1000" };
    }
    const stmt = act("assert_save_point", "core.assert_save_point", { cell: { kind: "lit", value: { kind: "cell", map: cell.map, x: cell.x, y: cell.y } } }, SAVE_NOTE, 1);
    if (has) main.main[0] = stmt;
    else main.main.unshift(stmt);
  }
  return { ok: true, project: refreshRule(out) };
}

/** The Global node, made when the project has none (id "global", under the maps). */
function ensureGlobal(p: Project): GlobalNode {
  const g = globalOf(p);
  if (g) return g;
  const xs = p.nodes.map((n) => n.pos.x).filter(Number.isFinite);
  const ys = p.nodes.map((n) => n.pos.y).filter(Number.isFinite);
  const made: GlobalNode = { id: GLOBAL_ID, kind: "global", pos: { x: xs.length ? Math.min(...xs) : 0, y: (ys.length ? Math.max(...ys) : 0) + 220 }, tabs: [] };
  p.nodes.push(made);
  return made;
}

/** Turn the unknown-map rule on (a wing home) or off (the built-in: stop). Global's own different
 * unexpected_map is replaced only with `replaceCustom`; a map node's own is never touched. */
export function setUnknownMap(p: Project, to: UnknownMap, replaceCustom = false): RuleEdit {
  const r = readRules(p);
  if (r.custom && !replaceCustom) return { ok: false, error: `Global has its own ${RULE_NAME} event (its tab ${r.tab}): change it on /flows, or replace it` };
  const out = clone(p);
  const g = globalOf(out);
  let at: string | null = null; // the tab the old rule was in: the new one goes back there
  for (const t of g?.tabs ?? []) {
    if (t.defs.some((d) => d.name === RULE_NAME)) at = t.name;
    t.defs = t.defs.filter((d) => d.name !== RULE_NAME);
  }
  if (g) g.tabs = g.tabs.filter((t) => t.name !== at || t.defs.length || Object.keys(t.vars).length || to === "wing"); // a tab the rule alone filled goes with it
  if (to === "stop") return { ok: true, project: out };
  const glob = ensureGlobal(out);
  const def = unknownMapDef(knownMaps(out), r.savePoint.cell?.map ?? null, wingItem(out));
  let tab = glob.tabs.find((t) => t.name === (at ?? RULE_TAB));
  if (!tab) {
    const name = !tabNameProblem(glob, RULE_TAB) ? RULE_TAB : newTabName(glob);
    tab = { name, main: null, defs: [], vars: {} };
    glob.tabs.push(tab);
  }
  tab.defs.push(def);
  return { ok: true, project: out };
}

/** Keep the rule's list of known maps (and its wing) current after the maps changed (a map node
 * added, removed, its map changed): the same object when nothing changes (off, custom, current). */
export function refreshRule(p: Project): Project {
  const g = globalRule(p);
  if (!g || !isOurRule(g.def)) return p;
  const want = unknownMapDef(knownMaps(p), readRules(p).savePoint.cell?.map ?? null, wingItem(p));
  if (JSON.stringify(want) === JSON.stringify(g.def)) return p;
  const out = clone(p);
  for (const t of globalOf(out)?.tabs ?? []) t.defs = t.defs.map((d) => (d.name === RULE_NAME ? want : d));
  return out;
}

/** The maps the rule treats as known (no wing there), for the panel's words. */
export function ruleMaps(p: Project): string[] {
  const g = globalRule(p);
  const s = g && isOurRule(g.def) ? g.def.body[1] : undefined;
  if (!s || s.kind !== "if" || s.cond.kind !== "cmp" || s.cond.right.kind !== "lit" || !Array.isArray(s.cond.right.value)) return [];
  return s.cond.right.value.flatMap((r) => (r.kind === "map" ? [r.map] : []));
}

/** The rule's wing in words ("call butterfly_wing()", "use item 602"). */
export function wingText(w: Wing): string {
  if (w.kind === "proc") return `call ${w.name}()`;
  if (w.kind === "var") return `use the item ${w.name}`;
  return w.id === WING_ID ? "use a Butterfly Wing (item 602)" : `use item ${w.id}`;
}
