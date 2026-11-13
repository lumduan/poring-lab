// Test helpers for the flow editor's converters: the committed SYNTHETIC fixtures (canonical JSON
// written by scripts/gen_flow_fixtures.py from MW1's fixtures and the MW2 sample) and a seeded
// generator of random flows within MW2's block set (the round-trip property tests).
import { readFileSync } from "node:fs";

import type { ActionStmt, Exit, Expr, Flow, Handler, MapBlock, MapEvent, Ref, Stmt } from "./ir.ts";
import type { Project } from "./project.ts";

export const FIXTURES = ["visit_and_choose", "farm_loop", "town_warp_farm"] as const;

export function fixture(name: (typeof FIXTURES)[number]): Flow {
  return JSON.parse(readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8")) as Flow;
}

/** The LOGIN-START project the tests build on (fixtures/project_session.json, the engine's test
 * fixture too): login -> character -> xmas_dun02 -> geffen, a Global with tabs keys and safety. It
 * was the ready-made xmas_dun02 before the one box (Batt 2026-11-13 ~21:4x); a fresh copy a call. */
export function sessionProject(): Project {
  return JSON.parse(readFileSync(new URL("./fixtures/project_session.json", import.meta.url), "utf8")) as Project;
}

/** Every expression of a flow (statement fields, handler conditions, nested), for the text tests. */
export function allExprs(flow: Flow): Expr[] {
  const out: Expr[] = [];
  const expr = (e: Expr | null) => {
    if (!e) return;
    out.push(e);
    if (e.kind === "do") Object.values(e.action.params).forEach(expr);
  };
  const stmts = (ss: Stmt[]) => {
    for (const s of ss) {
      if (s.kind === "action") Object.values(s.params).forEach(expr);
      if (s.kind === "if" || s.kind === "while" || s.kind === "wait_until") expr(s.cond);
      if (s.kind === "repeat") expr(s.times);
      if (s.kind === "set") expr(s.value);
      if (s.kind === "if") {
        stmts(s.then);
        stmts(s.orelse);
      }
      if (s.kind === "while" || s.kind === "repeat" || s.kind === "for") stmts(s.body);
    }
  };
  const handler = (h: Handler) => {
    [h.when, h.until, h.rearm].forEach(expr);
    stmts(h.body);
  };
  flow.handlers.forEach(handler);
  if (flow.main) stmts(flow.main);
  for (const b of flow.workflow?.blocks ?? []) {
    stmts(b.main);
    for (const ev of b.events) {
      if (ev.kind === "override" || ev.kind === "add") handler(ev.event);
      if (ev.kind === "extend") stmts(ev.steps);
    }
  }
  flow.assumes.forEach(expr);
  expr(flow.stop_when);
  return out;
}

// --- a seeded random flow generator ----------------------------------------------------------------
export class Rng {
  private s: number;
  constructor(seed: number) {
    this.s = seed >>> 0 || 1;
  }
  next(): number {
    // xorshift32
    let x = this.s;
    x ^= x << 13;
    x ^= x >>> 17;
    x ^= x << 5;
    this.s = x >>> 0;
    return this.s / 0x100000000;
  }
  int(lo: number, hi: number): number {
    return lo + Math.floor(this.next() * (hi - lo + 1));
  }
  pick<T>(xs: readonly T[]): T {
    return xs[this.int(0, xs.length - 1)];
  }
  chance(p: number): boolean {
    return this.next() < p;
  }
}

const SENSORS = ["hp_percent", "sp_percent", "weight_percent", "is_dead", "map_load_seen", "sees", "count_visible"];
const VARS = ["POTION", "WING", "BOSS", "x", "n_runs"];
const GENERIC = [
  ["attack_nearest", "combat.attack_target"],
  ["set_save_point", "nav.set_save_point"],
  ["respawn", "char.respawn"],
  ["close_dialog", "npc.close"],
  ["kafra_store", "storage.deposit"],
] as const;
const TEXTS = ["plain", 'quote " inside', "back\\slash", "ไทย", "tab\there", "emoji 🙂"];

function ref(r: Rng): Ref {
  switch (r.int(0, 7)) {
    case 0:
      return { kind: "map", map: r.pick(["map_1", "town_1", "prt_fild08"]) };
    case 1:
      return { kind: "cell", map: r.pick(["map_1", "field_1"]), x: r.int(0, 400), y: r.int(0, 400) };
    case 2:
      return { kind: "npc", key: r.pick(["n_k1", "n_2b71", "n-x.y"]) };
    case 3:
      return { kind: "option", key: r.pick(["o_5d0e", "o_1"]) };
    case 4:
      return { kind: "item", id: r.int(1, 99999) };
    case 5:
      return { kind: "mob", id: r.int(1, 99999) };
    case 6:
      return { kind: "skill", id: r.int(1, 999), level: r.chance(0.5) ? null : r.int(1, 10) };
    default:
      return { kind: "window", name: r.pick(["basic_info", "inventory"]) };
  }
}

function lit(r: Rng): Expr {
  switch (r.int(0, 5)) {
    case 0:
      return { kind: "lit", value: r.chance(0.5) };
    case 1:
      return { kind: "lit", value: r.int(-50, 500) };
    case 2:
      return { kind: "lit", value: r.pick([0.5, 1.25, -2.75, 1e-7]) };
    case 3:
      return { kind: "lit", value: r.pick(TEXTS) };
    case 4:
      return { kind: "lit", value: ref(r) };
    default:
      return { kind: "lit", value: Array.from({ length: r.int(0, 3) }, () => ref(r)) };
  }
}

export function expr(r: Rng, depth = 0, allowDo = true): Expr {
  const leaf = depth >= 3;
  switch (leaf ? r.int(0, 3) : r.int(0, 10)) {
    case 0:
    case 1:
      return lit(r);
    case 2:
      return { kind: "var", name: r.pick(VARS) };
    case 3: {
      const args: Record<string, Expr> = {};
      if (r.chance(0.4)) args.mob = { kind: "lit", value: { kind: "mob", id: r.int(1, 9999) } };
      if (r.chance(0.3)) args.within = { kind: "lit", value: r.int(1, 20) };
      return { kind: "sense", sensor: r.pick(SENSORS), args };
    }
    case 4:
      return { kind: "outcome", value: r.pick(["ok", "failed", "unsupported", "interrupted", "refused"] as const) };
    case 5:
      return { kind: "cmp", op: r.pick(["==", "!=", "<", "<=", ">", ">=", "in", "not in"] as const), left: expr(r, depth + 1, allowDo), right: expr(r, depth + 1, allowDo) };
    case 6:
      return { kind: r.pick(["and", "or"] as const), terms: Array.from({ length: r.int(2, 4) }, () => expr(r, depth + 1, allowDo)) };
    case 7:
      return { kind: "not", term: expr(r, depth + 1, allowDo) };
    case 8:
      return { kind: "arith", op: r.pick(["+", "-", "*", "//", "%"] as const), left: expr(r, depth + 1, allowDo), right: expr(r, depth + 1, allowDo) };
    case 9:
      return { kind: "list", items: [{ kind: "var", name: r.pick(VARS) }, ...Array.from({ length: r.int(0, 2) }, () => lit(r))] };
    default:
      return allowDo ? { kind: "do", action: action(r, depth + 1) } : lit(r);
  }
}

function action(r: Rng, depth: number): ActionStmt {
  const base = {
    kind: "action" as const,
    timeout_s: r.pick([10, 60, 120, 2.5]),
    on_fail: r.pick(["stop", "continue"] as const),
    outcome_to: r.chance(0.2) ? "res" : null,
    note: r.chance(0.2) ? r.pick(TEXTS) : null,
  };
  switch (r.int(0, 6)) {
    case 0:
      return { ...base, block: "walk_to", concept: "nav.walk_to", params: { cell: { kind: "lit", value: { kind: "cell", map: "map_1", x: r.int(0, 300), y: r.int(0, 300) } } } };
    case 1:
      return { ...base, block: "talk_npc", concept: "npc.talk", params: { npc: { kind: "lit", value: { kind: "npc", key: "n_k1" } } } };
    case 2:
      return { ...base, block: "choose_menu", concept: "npc.choose", params: { option: { kind: "lit", value: { kind: "option", key: "o_1" } } } };
    case 3:
      return { ...base, block: "open_window", concept: "ui.open_window", params: { window: { kind: "lit", value: { kind: "window", name: "basic_info" } } } };
    case 4:
      return { ...base, block: "use_item", concept: "item.use", params: { item: r.chance(0.5) ? { kind: "var", name: "POTION" } : { kind: "lit", value: { kind: "item", id: r.int(1, 999) } } } };
    default: {
      const [block, concept] = r.pick(GENERIC);
      const params: Record<string, Expr> = {};
      for (const k of ["within", "npc", "mob", "all_except"]) if (r.chance(0.3)) params[k] = expr(r, depth + 1, depth < 2);
      return { ...base, block, concept, params };
    }
  }
}

function exit(r: Rng, blocks: string[]): Exit {
  const base: Exit = { kind: "walk_exit", warp: null, npc: null, options: [], item: null, to_block: r.pick(blocks), to_entry: "arrival", timeout_s: r.pick([120, 60]) };
  switch (r.int(0, 2)) {
    case 0:
      return { ...base, warp: { kind: "cell", map: "map_1", x: r.int(0, 300), y: r.int(0, 300) } };
    case 1:
      return { ...base, kind: "npc_warp", npc: { kind: "npc", key: "n_2b71" }, options: [{ kind: "option", key: "o_5d0e" }, ...(r.chance(0.3) ? [{ kind: "option" as const, key: "o_2" }] : [])] };
    default:
      return { ...base, kind: "item_warp", item: r.chance(0.5) ? { kind: "var", name: "WING" } : { kind: "item", id: 9002 } };
  }
}

export function stmts(r: Rng, depth: number, blocks: string[], n = r.int(1, 4)): Stmt[] {
  return Array.from({ length: n }, () => stmt(r, depth, blocks));
}

function stmt(r: Rng, depth: number, blocks: string[]): Stmt {
  const leaf = depth >= 3;
  switch (leaf ? r.int(0, 2) : r.int(0, 13)) {
    case 0:
    case 1:
      return action(r, depth);
    case 2:
      return { kind: "wait_until", cond: { kind: "lit", value: false }, timeout_s: r.pick([1, 2.5, 30]), outcome_to: null };
    case 3:
      return { kind: "wait_until", cond: expr(r, 1), timeout_s: r.pick([5, 10]), outcome_to: r.chance(0.5) ? "w" : null };
    case 4:
      return { kind: "if", cond: expr(r, 0), then: stmts(r, depth + 1, blocks), orelse: r.chance(0.5) ? stmts(r, depth + 1, blocks) : [] };
    case 5:
      return { kind: "while", cond: expr(r, 0), body: stmts(r, depth + 1, blocks), max_iter: r.chance(0.5) ? r.int(1, 99) : null, max_s: r.chance(0.3) ? 30.5 : null };
    case 6:
      return { kind: "repeat", times: expr(r, 1), body: stmts(r, depth + 1, blocks) };
    case 7:
      return { kind: "set", var: r.pick(VARS), value: expr(r, 0) };
    case 8:
      return { kind: "call", proc: "helper", args: [], kwargs: {} };
    case 9:
      return { kind: "stop", reason: r.pick(["done", "menu_mismatch"]) };
    case 10:
      return r.chance(0.5) ? { kind: "break" } : { kind: "continue" };
    case 11:
      return { kind: "for", var: "i", items: { kind: "range", start: { kind: "lit", value: 0 }, stop: { kind: "lit", value: 3 }, step: { kind: "lit", value: 1 } }, body: stmts(r, depth + 1, blocks) };
    default:
      return { kind: "take_exit", exit: exit(r, blocks) };
  }
}

export function handler(r: Rng, name: string, blocks: string[]): Handler {
  const until = r.chance(0.4) ? expr(r, 1) : null;
  return {
    name,
    when: expr(r, 0),
    until,
    rearm: until === null && r.chance(0.5) ? expr(r, 1) : null,
    priority: r.pick(["critical", "survival", "upkeep"] as const),
    rank: r.chance(0.3) ? r.int(1, 99) : null,
    mode: r.pick(["insert", "preempt"] as const),
    escalate: r.chance(0.2) ? "helper" : null,
    max_insert_fails: r.int(1, 10),
    cooldown_s: r.pick([0, 1.5, 30]),
    max_per_min: r.chance(0.5) ? r.int(1, 60) : null,
    max_fires_per_10min: r.int(1, 100),
    max_per_run: r.chance(0.5) ? r.int(1, 100) : null,
    then: r.pick(["resume", "skip_block", "restart_flow", "relocate", "stop"] as const),
    body: stmts(r, 1, blocks),
  };
}

export function randomFlow(seed: number): Flow {
  const r = new Rng(seed);
  const names = Array.from({ length: r.int(1, 4) }, (_, i) => `b${i}`);
  const blocks: MapBlock[] = names.map((name) => {
    const events: MapEvent[] = [];
    if (r.chance(0.5)) events.push({ kind: "override", event: handler(r, "hp_low", names), label: `${name}_hp_low` });
    if (r.chance(0.4)) events.push({ kind: "add", event: handler(r, `${name}_only`, names), label: `${name}_only` });
    if (r.chance(0.4)) events.push({ kind: "extend", key: "dead", steps: stmts(r, 1, names), max_per_run: r.chance(0.5) ? 2 : null, label: `${name}_dead` });
    if (r.chance(0.3)) events.push({ kind: "disable", key: "weight" });
    return {
      name,
      map: { kind: "map", map: `map_${name}` },
      entries: [{ name: "arrival", at: r.chance(0.7) ? { kind: "cell", map: `map_${name}`, x: r.int(0, 99), y: r.int(0, 99) } : null, radius: r.int(0, 15) }],
      targets: r.chance(0.5) ? [{ kind: "mob", id: r.int(1, 999) }] : [],
      ignore: [],
      events,
      main: stmts(r, 0, names, r.int(1, 6)),
      resume_here: r.chance(0.8),
    };
  });
  const plain = r.chance(0.2);
  return {
    ir: 2,
    name: `random_${seed}`,
    description: r.pick(TEXTS),
    target: { client: "kro-20211103-prere", server: "lab-rathena", locale: "en", path: "s2" },
    assumes: r.chance(0.3) ? [expr(r, 1, false)] : [],
    max_runtime_s: 3600,
    where_budget: 12,
    stop_when: r.chance(0.3) ? expr(r, 1, false) : null,
    variables: { POTION: { kind: "lit", value: { kind: "item", id: 9001 } } },
    procedures: { helper: stmts(r, 1, names) },
    handlers: ["dead", "hp_low", "weight"].filter(() => r.chance(0.7)).map((n) => handler(r, n, names)),
    main: plain ? stmts(r, 0, names) : null,
    workflow: plain ? null : { start_block: names[0], start_entry: "arrival", blocks, run_until_stopped: r.chance(0.5) },
  };
}
