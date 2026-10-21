// IR <-> the block editor's workspace (Blockly's JSON serialization), as PURE data: no Blockly
// here, so the round trip IR -> blocks -> IR is unit-tested in node (blocks.test.ts). The block
// types are blockdefs.ts.
//
// A workspace shows ONE scope:
// - a map block: its main flow (a `pl_main` hat) and its map events (override / add / extend /
//   disable hats), in the IR's order;
// - the global events (one `pl_event` hat per handler);
// - a plain flow's main.
// Everything is LOSSLESS: what a block does not show as a field (an action's timeout, on_fail,
// outcome_to, note; an event's limits) travels in its extraState, and a statement MW2 has no block
// for is a read-only `pl_raw` block carrying its JSON. Statement block ids are MW1's node paths
// (`n:town.3`), so lint findings and simulate results land on the right block.
import { DEF_BY_TYPE } from "./blockdefs.ts";
import { argsText, ExprError, exprText, hasDo, parseArgs, parseExpr } from "./expr.ts";
import { fieldOf, HUNT_TYPE, type HuntRules, paramOf, params as huntParams } from "./hunt.ts";
import {
  type ActionStmt,
  type CellRef,
  type Exit,
  type Expr,
  type Flow,
  type Handler,
  type ItemRef,
  type MapBlock,
  type MapEvent,
  type Stmt,
  type Var,
  clone,
  eventLabel,
  KEY,
  MAP_ID,
  MAX_RANK,
  NAME,
} from "./ir.ts";

export type Scope = { kind: "block"; name: string } | { kind: "global" } | { kind: "main" };
export type WsBlock = {
  type: string;
  id?: string;
  x?: number;
  y?: number;
  fields?: Record<string, string | number>;
  inputs?: Record<string, { block?: WsBlock; shadow?: WsBlock }>;
  next?: { block?: WsBlock };
  extraState?: unknown;
};
export type Workspace = { blocks: { languageVersion: 0; blocks: WsBlock[] } };
export type FromResult = { ok: true; flow: Flow; warnings: string[] } | { ok: false; errors: string[] };
/** Catalogue defaults for blocks dragged from the toolbox without their state. */
export type Defaults = Record<string, { concept: string; timeout_s: number }>;
/** `hunt`: the hunt block's rule versions (GET /flows/catalogue `hunt_rules`); with them a hunt
 * whose every parameter is one of its choices shows as the pl_hunt block (hunt.ts), else as a
 * generic block (lossless either way). */
export type ConvertOptions = { hunt?: HuntRules | null };

type ActionRest = Pick<ActionStmt, "concept" | "timeout_s" | "on_fail" | "outcome_to" | "note">;
type HandlerRest = Pick<
  Handler,
  "escalate" | "max_insert_fails" | "cooldown_s" | "max_per_min" | "max_fires_per_10min" | "max_per_run"
>;

const PALETTE: Record<string, { type: string; param: string; kind: string }> = {
  walk_to: { type: "pl_walk_to", param: "cell", kind: "cell" },
  talk_npc: { type: "pl_talk_npc", param: "npc", kind: "npc" },
  choose_menu: { type: "pl_choose_menu", param: "option", kind: "option" },
  open_window: { type: "pl_open_window", param: "window", kind: "window" },
  use_item: { type: "pl_use_item", param: "item", kind: "item" },
};
const BLOCK_OF_TYPE: Record<string, string> = Object.fromEntries(
  Object.entries(PALETTE).map(([b, p]) => [p.type, b]),
);

// --- IR -> workspace ------------------------------------------------------------------------------
class Ids {
  private used = new Set<string>();
  hunt: HuntRules | null;
  constructor(hunt: HuntRules | null = null) {
    this.hunt = hunt;
  }
  take(id: string): string {
    let out = id;
    for (let i = 2; this.used.has(out); i++) out = `${id}#${i}`;
    this.used.add(out);
    return out;
  }
}

function actionRest(a: ActionStmt): { rest: ActionRest } {
  return {
    rest: { concept: a.concept, timeout_s: a.timeout_s, on_fail: a.on_fail, outcome_to: a.outcome_to, note: a.note },
  };
}

function itemText(e: Expr): string | null {
  if (e.kind === "var") return e.name;
  if (e.kind === "lit" && typeof e.value === "object" && !Array.isArray(e.value) && e.value.kind === "item") {
    return String(e.value.id);
  }
  return null;
}

function exprBlock(e: Expr, path: string, ids: Ids): WsBlock {
  if (e.kind === "do" && paramsPlain(e.action)) {
    return {
      type: "pl_do",
      id: ids.take(`n:${path}:${e.action.block}`),
      fields: { BLOCK: e.action.block, ARGS: argsText(e.action.params) },
      extraState: actionRest(e.action),
    };
  }
  if (!hasDo(e)) return { type: "pl_expr", fields: { TEXT: exprText(e) } };
  if (e.kind === "do") return { type: "pl_raw_expr", fields: { TEXT: exprText(e) }, extraState: { expr: e } };
  if (e.kind === "cmp") {
    return {
      type: "pl_compare",
      fields: { OP: e.op },
      inputs: { A: { block: exprBlock(e.left, path, ids) }, B: { block: exprBlock(e.right, path, ids) } },
    };
  }
  if (e.kind === "and" || e.kind === "or") {
    const inputs: WsBlock["inputs"] = {};
    e.terms.forEach((t, i) => (inputs[`T${i}`] = { block: exprBlock(t, path, ids) }));
    return { type: "pl_logic", fields: { OP: e.kind }, inputs, extraState: { n: e.terms.length } };
  }
  if (e.kind === "not") return { type: "pl_not", inputs: { X: { block: exprBlock(e.term, path, ids) } } };
  // an action inside a sensor argument, a list or arithmetic: kept exactly, read-only
  return { type: "pl_raw_expr", fields: { TEXT: exprText(e) }, extraState: { expr: e } };
}

function rawText(s: Stmt): string {
  switch (s.kind) {
    case "for":
      return `for ${s.var} in ...: (${s.body.length} statements)`;
    case "action":
      return `${s.block}(${argsText(s.params)})`;
    default:
      return s.kind;
  }
}

function paramsPlain(a: ActionStmt): boolean {
  return Object.values(a.params).every((e) => !hasDo(e));
}

/** The pl_hunt fields of a hunt action: only when it has exactly the block's parameters, each a
 * literal rule version among its choices (anything else stays a generic block, exactly). */
function huntFields(a: ActionStmt, rules: HuntRules): Record<string, string> | null {
  const ps = huntParams(rules);
  const keys = Object.keys(a.params);
  if (keys.length !== ps.length) return null;
  const out: Record<string, string> = {};
  for (const p of ps) {
    const e = a.params[p.name];
    if (!e || e.kind !== "lit" || typeof e.value !== "string") return null;
    const v = e.value;
    if (!p.choices.some((c) => c.id === v)) return null;
    out[fieldOf(p.name)] = v;
  }
  return out;
}

function stmtBlock(s: Stmt, path: string, ids: Ids): WsBlock {
  const id = ids.take(`n:${path}`);
  const b = ((): WsBlock => {
    switch (s.kind) {
      case "action": {
        if (s.block === "hunt" && ids.hunt) {
          const f = huntFields(s, ids.hunt);
          if (f) return { type: HUNT_TYPE, fields: f, extraState: actionRest(s) };
        }
        const p = PALETTE[s.block];
        const keys = Object.keys(s.params);
        if (p && keys.length === 1 && keys[0] === p.param) {
          const v = s.params[p.param];
          if (p.kind === "item") {
            const t = itemText(v);
            if (t !== null) return { type: p.type, fields: { ITEM: t }, extraState: actionRest(s) };
          } else if (v.kind === "lit" && typeof v.value === "object" && !Array.isArray(v.value) && v.value.kind === p.kind) {
            const r = v.value;
            if (r.kind === "cell") return { type: p.type, fields: { MAP: r.map, X: r.x, Y: r.y }, extraState: actionRest(s) };
            if (r.kind === "npc") return { type: p.type, fields: { NPC: r.key }, extraState: actionRest(s) };
            if (r.kind === "option") return { type: p.type, fields: { OPTION: r.key }, extraState: actionRest(s) };
            if (r.kind === "window") return { type: p.type, fields: { WINDOW: r.name }, extraState: actionRest(s) };
          }
        }
        if (paramsPlain(s)) {
          return { type: "pl_action", fields: { BLOCK: s.block, ARGS: argsText(s.params) }, extraState: actionRest(s) };
        }
        break;
      }
      case "wait_until":
        if (s.cond.kind === "lit" && s.cond.value === false && s.outcome_to === null) {
          return { type: "pl_wait", fields: { SECONDS: s.timeout_s } };
        }
        return {
          type: "pl_wait_until",
          fields: { TIMEOUT: s.timeout_s },
          inputs: { COND: { block: exprBlock(s.cond, path, ids) } },
          extraState: { outcome_to: s.outcome_to },
        };
      case "if":
        return {
          type: "pl_if",
          inputs: {
            COND: { block: exprBlock(s.cond, path, ids) },
            ...chainInput("THEN", s.then, `${path}.then`, ids),
            ...chainInput("ELSE", s.orelse, `${path}.orelse`, ids),
          },
        };
      case "while":
        return {
          type: "pl_while",
          inputs: { COND: { block: exprBlock(s.cond, path, ids) }, ...chainInput("BODY", s.body, `${path}.body`, ids) },
          extraState: { max_iter: s.max_iter, max_s: s.max_s },
        };
      case "repeat":
        return {
          type: "pl_repeat",
          inputs: { TIMES: { block: exprBlock(s.times, path, ids) }, ...chainInput("BODY", s.body, `${path}.body`, ids) },
        };
      case "set":
        return { type: "pl_set", fields: { VAR: s.var }, inputs: { VALUE: { block: exprBlock(s.value, path, ids) } } };
      case "call":
        return { type: "pl_call", fields: { PROC: s.proc } };
      case "stop":
        return { type: "pl_stop", fields: { REASON: s.reason } };
      case "break":
        return { type: "pl_break" };
      case "continue":
        return { type: "pl_continue" };
      case "take_exit":
        return exitBlock(s.exit) ?? { type: "pl_raw", fields: { TEXT: `take_exit ${s.exit.kind}` }, extraState: { stmt: s } };
    }
    return { type: "pl_raw", fields: { TEXT: rawText(s) }, extraState: { stmt: s } };
  })();
  return { ...b, id };
}

function exitBlock(x: Exit): WsBlock | null {
  const st = { timeout_s: x.timeout_s };
  const to = { TO_BLOCK: x.to_block, TO_ENTRY: x.to_entry };
  if (x.kind === "walk_exit" && x.warp && !x.npc && !x.item && !x.options.length) {
    return { type: "pl_exit_walk", fields: { MAP: x.warp.map, X: x.warp.x, Y: x.warp.y, ...to }, extraState: st };
  }
  if (x.kind === "npc_warp" && x.npc && !x.warp && !x.item) {
    return {
      type: "pl_exit_npc",
      fields: { NPC: x.npc.key, OPTIONS: x.options.map((o) => o.key).join(", "), ...to },
      extraState: st,
    };
  }
  if (x.kind === "item_warp" && x.item && !x.warp && !x.npc && !x.options.length) {
    const item = x.item.kind === "var" ? x.item.name : String(x.item.id);
    return { type: "pl_exit_item", fields: { ITEM: item, ...to }, extraState: st };
  }
  return null;
}

function chainInput(name: string, stmts: Stmt[], prefix: string, ids: Ids): WsBlock["inputs"] {
  const first = chain(stmts, prefix, ids);
  return first ? { [name]: { block: first } } : {};
}

function chain(stmts: Stmt[], prefix: string, ids: Ids): WsBlock | undefined {
  let head: WsBlock | undefined;
  for (let i = stmts.length - 1; i >= 0; i--) {
    const b = stmtBlock(stmts[i], `${prefix}.${i}`, ids);
    if (head) b.next = { block: head };
    head = b;
  }
  return head;
}

function eventHat(
  h: Handler,
  kind: "global" | "override" | "add",
  label: string | null,
  order: number,
  ids: Ids,
): WsBlock {
  const inputs: WsBlock["inputs"] = { WHEN: { block: exprBlock(h.when, h.name, ids) } };
  if (h.until) inputs.UNTIL = { block: exprBlock(h.until, h.name, ids) };
  if (h.rearm) inputs.REARM = { block: exprBlock(h.rearm, h.name, ids) };
  const root = kind === "global" ? h.name : (label ?? h.name);
  Object.assign(inputs, chainInput("DO", h.body, root, ids));
  return {
    type: "pl_event",
    id: ids.take(`h:${root}`),
    fields: {
      SCOPE: kind === "global" ? "global" : kind,
      NAME: h.name,
      PRIORITY: h.priority,
      RANK: h.rank === null ? "" : String(h.rank),
      MODE: h.mode,
      THEN: h.then,
    },
    inputs,
    extraState: { kind, label, order, rest: restOf(h) },
  };
}

function restOf(h: Handler): HandlerRest {
  return {
    escalate: h.escalate,
    max_insert_fails: h.max_insert_fails,
    cooldown_s: h.cooldown_s,
    max_per_min: h.max_per_min,
    max_fires_per_10min: h.max_fires_per_10min,
    max_per_run: h.max_per_run,
  };
}

function mapEventHat(ev: MapEvent, block: MapBlock, order: number, ids: Ids): WsBlock {
  if (ev.kind === "override" || ev.kind === "add") return eventHat(ev.event, ev.kind, ev.label, order, ids);
  const lab = eventLabel(ev, block);
  if (ev.kind === "extend") {
    return {
      type: "pl_extend",
      id: ids.take(`h:${lab}`),
      fields: { KEY: ev.key },
      inputs: chainInput("DO", ev.steps, lab, ids),
      extraState: { label: ev.label, max_per_run: ev.max_per_run, order },
    };
  }
  return { type: "pl_disable", id: ids.take(`h:disable:${ev.key}`), fields: { KEY: ev.key }, extraState: { order } };
}

function height(b: WsBlock | undefined): number {
  let n = 0;
  for (let cur = b; cur; cur = cur.next?.block) {
    n += cur.type === HUNT_TYPE ? 4 : 1; // the hunt block is five lines tall
    for (const inp of Object.values(cur.inputs ?? {})) if (inp.block && !DEF_BY_TYPE[inp.block.type]?.output) n += height(inp.block);
  }
  return n;
}

/** The workspace JSON of one scope. */
export function toWorkspace(flow: Flow, scope: Scope, opts: ConvertOptions = {}): Workspace {
  const ids = new Ids(opts.hunt ?? null);
  const top: WsBlock[] = [];
  let y = 20;
  const place = (b: WsBlock, x: number) => {
    b.x = x;
    b.y = y;
    y += 90 + 46 * height(b.inputs?.DO?.block);
    top.push(b);
  };
  if (scope.kind === "block") {
    const block = flow.workflow?.blocks.find((b) => b.name === scope.name);
    if (!block) throw new Error(`no map block ${scope.name}`);
    place({ type: "pl_main", id: ids.take("h:main"), inputs: chainInput("DO", block.main, block.name, ids), extraState: {} }, 20);
    block.events.forEach((ev, i) => place(mapEventHat(ev, block, i, ids), 20));
  } else if (scope.kind === "global") {
    flow.handlers.forEach((h, i) => place(eventHat(h, "global", null, i, ids), 20));
  } else {
    place({ type: "pl_main", id: ids.take("h:main"), inputs: chainInput("DO", flow.main ?? [], "main", ids), extraState: {} }, 20);
  }
  return { blocks: { languageVersion: 0, blocks: top } };
}

// --- workspace -> IR ------------------------------------------------------------------------------
class Reader {
  errors: string[] = [];
  warnings: string[] = [];
  private defaults: Defaults;
  constructor(defaults: Defaults) {
    this.defaults = defaults;
  }

  err(where: string, msg: string): void {
    if (this.errors.length < 50) this.errors.push(`${where}: ${msg}`);
  }

  field(b: WsBlock, name: string): string {
    const v = b.fields?.[name];
    return v === undefined || v === null ? "" : String(v);
  }

  num(b: WsBlock, name: string, where: string): number {
    const v = Number(b.fields?.[name]);
    if (!Number.isFinite(v)) this.err(where, `${name.toLowerCase()} is not a number`);
    return v;
  }

  int(b: WsBlock, name: string, where: string): number {
    const v = this.num(b, name, where);
    if (!Number.isInteger(v)) this.err(where, `${name.toLowerCase()} must be a whole number`);
    return v;
  }

  name(b: WsBlock, field: string, where: string, re: RegExp = NAME): string {
    const v = this.field(b, field).trim();
    if (!re.test(v)) this.err(where, `${field.toLowerCase()} ${JSON.stringify(v)} is not a valid name`);
    return v;
  }

  expr(b: WsBlock | undefined, where: string, what: string): Expr {
    if (!b) {
      this.err(where, `${what} is missing`);
      return { kind: "lit", value: false };
    }
    switch (b.type) {
      case "pl_expr":
        try {
          const e = parseExpr(this.field(b, "TEXT"));
          return e;
        } catch (e) {
          this.err(where, `${what}: ${e instanceof ExprError ? e.message : "cannot be read"}`);
          return { kind: "lit", value: false };
        }
      case "pl_compare": {
        const op = this.field(b, "OP") as Extract<Expr, { kind: "cmp" }>["op"];
        return {
          kind: "cmp",
          op,
          left: this.expr(b.inputs?.A?.block, where, `${what} (left)`),
          right: this.expr(b.inputs?.B?.block, where, `${what} (right)`),
        };
      }
      case "pl_logic": {
        const st = (b.extraState ?? {}) as { n?: number };
        const n = Math.max(2, Number(st.n ?? 2));
        const terms: Expr[] = [];
        for (let i = 0; i < n; i++) {
          const t = b.inputs?.[`T${i}`]?.block;
          if (t) terms.push(this.expr(t, where, `${what} (term ${i + 1})`));
        }
        if (terms.length < 2) this.err(where, `${what}: and / or needs two terms`);
        return { kind: this.field(b, "OP") === "or" ? "or" : "and", terms };
      }
      case "pl_not":
        return { kind: "not", term: this.expr(b.inputs?.X?.block, where, `${what} (not)`) };
      case "pl_do":
        return { kind: "do", action: this.generic(b, where) };
      case "pl_raw_expr": {
        const st = (b.extraState ?? {}) as { expr?: Expr };
        if (st.expr) return clone(st.expr);
        this.err(where, `${what}: an unreadable block`);
        return { kind: "lit", value: false };
      }
      default:
        this.err(where, `${what}: a ${b.type} block is not a value`);
        return { kind: "lit", value: false };
    }
  }

  rest(b: WsBlock, block: string, where: string): ActionRest {
    const st = (b.extraState ?? {}) as { rest?: ActionRest };
    if (st.rest) return st.rest;
    const d = this.defaults[block];
    if (!d) {
      this.err(where, `${block}: not in the catalogue`);
      return { concept: "core.unknown", timeout_s: 10, on_fail: "stop", outcome_to: null, note: null };
    }
    return { concept: d.concept, timeout_s: d.timeout_s, on_fail: "stop", outcome_to: null, note: null };
  }

  generic(b: WsBlock, where: string): ActionStmt {
    const block = this.field(b, "BLOCK");
    let params: Record<string, Expr> = {};
    try {
      params = parseArgs(this.field(b, "ARGS"));
    } catch (e) {
      this.err(where, `${block}: ${e instanceof ExprError ? e.message : "parameters cannot be read"}`);
    }
    return { kind: "action", block, params, ...this.rest(b, block, where) };
  }

  item(b: WsBlock, field: string, where: string): ItemRef | Var {
    const t = this.field(b, field).trim();
    if (/^[0-9]+$/.test(t)) return { kind: "item", id: Number(t) };
    if (NAME.test(t)) return { kind: "var", name: t };
    this.err(where, `item ${JSON.stringify(t)}: an item id or a variable name`);
    return { kind: "item", id: 1 };
  }

  stmts(head: WsBlock | undefined, where: string): Stmt[] {
    const out: Stmt[] = [];
    for (let cur = head; cur; cur = cur.next?.block) out.push(this.stmt(cur, `${where}.${out.length}`));
    return out;
  }

  stmt(b: WsBlock, where: string): Stmt {
    const pal = BLOCK_OF_TYPE[b.type];
    if (pal) {
      const r = this.rest(b, pal, where);
      let v: Expr;
      if (b.type === "pl_walk_to") {
        const cell: CellRef = {
          kind: "cell",
          map: this.name(b, "MAP", where, MAP_ID),
          x: this.int(b, "X", where),
          y: this.int(b, "Y", where),
        };
        v = { kind: "lit", value: cell };
      } else if (b.type === "pl_talk_npc") v = { kind: "lit", value: { kind: "npc", key: this.name(b, "NPC", where, KEY) } };
      else if (b.type === "pl_choose_menu") {
        v = { kind: "lit", value: { kind: "option", key: this.name(b, "OPTION", where, KEY) } };
      } else if (b.type === "pl_open_window") {
        v = { kind: "lit", value: { kind: "window", name: this.name(b, "WINDOW", where, /^[a-z][a-z0-9_]{0,47}$/) } };
      } else {
        const it = this.item(b, "ITEM", where);
        v = it.kind === "var" ? it : { kind: "lit", value: it };
      }
      return { kind: "action", block: pal, params: { [PALETTE[pal].param]: v }, ...r };
    }
    switch (b.type) {
      case "pl_action":
        return this.generic(b, where);
      case HUNT_TYPE: {
        // the dropdowns ARE the parameters: P_<NAME> -> <name>, each a rule version literal
        const ps: Record<string, Expr> = {};
        for (const [k, v] of Object.entries(b.fields ?? {})) {
          const name = paramOf(k);
          if (name === null) continue;
          if (typeof v !== "string" || !v) this.err(where, `hunt: ${name} has no rule version`);
          ps[name] = { kind: "lit", value: String(v) };
        }
        return { kind: "action", block: "hunt", params: ps, ...this.rest(b, "hunt", where) };
      }
      case "pl_wait":
        return { kind: "wait_until", cond: { kind: "lit", value: false }, timeout_s: this.num(b, "SECONDS", where), outcome_to: null };
      case "pl_wait_until": {
        const st = (b.extraState ?? {}) as { outcome_to?: string | null };
        return {
          kind: "wait_until",
          cond: this.expr(b.inputs?.COND?.block, where, "the condition"),
          timeout_s: this.num(b, "TIMEOUT", where),
          outcome_to: st.outcome_to ?? null,
        };
      }
      case "pl_if":
        return {
          kind: "if",
          cond: this.expr(b.inputs?.COND?.block, where, "the condition"),
          then: this.stmts(b.inputs?.THEN?.block, `${where}.then`),
          orelse: this.stmts(b.inputs?.ELSE?.block, `${where}.orelse`),
        };
      case "pl_while": {
        const st = (b.extraState ?? {}) as { max_iter?: number | null; max_s?: number | null };
        return {
          kind: "while",
          cond: this.expr(b.inputs?.COND?.block, where, "the condition"),
          body: this.stmts(b.inputs?.BODY?.block, `${where}.body`),
          max_iter: st.max_iter ?? null,
          max_s: st.max_s ?? null,
        };
      }
      case "pl_repeat":
        return {
          kind: "repeat",
          times: this.expr(b.inputs?.TIMES?.block, where, "the count"),
          body: this.stmts(b.inputs?.BODY?.block, `${where}.body`),
        };
      case "pl_set":
        return { kind: "set", var: this.name(b, "VAR", where), value: this.expr(b.inputs?.VALUE?.block, where, "the value") };
      case "pl_call":
        return { kind: "call", proc: this.name(b, "PROC", where) };
      case "pl_stop":
        return { kind: "stop", reason: this.name(b, "REASON", where, /^[a-z_]{1,40}$/) };
      case "pl_break":
        return { kind: "break" };
      case "pl_continue":
        return { kind: "continue" };
      case "pl_exit_walk":
      case "pl_exit_npc":
      case "pl_exit_item":
        return { kind: "take_exit", exit: this.exit(b, where) };
      case "pl_raw": {
        const st = (b.extraState ?? {}) as { stmt?: Stmt };
        if (st.stmt) return clone(st.stmt);
        break;
      }
    }
    this.err(where, `a ${b.type} block cannot stand here`);
    return { kind: "stop", reason: "invalid" };
  }

  exit(b: WsBlock, where: string): Exit {
    const st = (b.extraState ?? {}) as { timeout_s?: number };
    const base: Exit = {
      kind: "walk_exit",
      warp: null,
      npc: null,
      options: [],
      item: null,
      to_block: this.name(b, "TO_BLOCK", where),
      to_entry: this.name(b, "TO_ENTRY", where),
      timeout_s: st.timeout_s ?? 120,
    };
    if (b.type === "pl_exit_walk") {
      return {
        ...base,
        warp: { kind: "cell", map: this.name(b, "MAP", where, MAP_ID), x: this.int(b, "X", where), y: this.int(b, "Y", where) },
      };
    }
    if (b.type === "pl_exit_npc") {
      const keys = this.field(b, "OPTIONS")
        .split(",")
        .map((k) => k.trim())
        .filter(Boolean);
      for (const k of keys) if (!KEY.test(k)) this.err(where, `option ${JSON.stringify(k)} is not a key`);
      if (!keys.length) this.err(where, "an npc warp needs at least one option key");
      return {
        ...base,
        kind: "npc_warp",
        npc: { kind: "npc", key: this.name(b, "NPC", where, KEY) },
        options: keys.map((key) => ({ kind: "option", key })),
      };
    }
    return { ...base, kind: "item_warp", item: this.item(b, "ITEM", where) };
  }

  /** IR 2 (ADR-0020 #13): empty = 13.6.3's table order (null); else a whole number 1..99. */
  rank(b: WsBlock, where: string): number | null {
    const t = this.field(b, "RANK").trim();
    if (t === "") return null;
    if (/^[0-9]{1,2}$/.test(t) && Number(t) >= 1 && Number(t) <= MAX_RANK) return Number(t);
    this.err(where, `rank ${JSON.stringify(t)}: a whole number 1..${MAX_RANK}, or empty for the 13.6.3 table order`);
    return null;
  }

  handler(b: WsBlock, where: string): Handler {
    const st = (b.extraState ?? {}) as { rest?: HandlerRest };
    const r: HandlerRest = st.rest ?? {
      escalate: null,
      max_insert_fails: 3,
      cooldown_s: 0,
      max_per_min: null,
      max_fires_per_10min: 10,
      max_per_run: null,
    };
    const name = this.name(b, "NAME", where);
    return {
      name,
      when: this.expr(b.inputs?.WHEN?.block, where, "when"),
      until: b.inputs?.UNTIL?.block ? this.expr(b.inputs.UNTIL.block, where, "until") : null,
      rearm: b.inputs?.REARM?.block ? this.expr(b.inputs.REARM.block, where, "rearm") : null,
      priority: this.field(b, "PRIORITY") as Handler["priority"],
      rank: this.rank(b, where),
      mode: this.field(b, "MODE") as Handler["mode"],
      then: this.field(b, "THEN") as Handler["then"],
      body: this.stmts(b.inputs?.DO?.block, name),
      ...r,
    };
  }
}

type Hat = { b: WsBlock; order: number; y: number };

function hats(ws: Workspace, r: Reader): { main: WsBlock[]; events: Hat[] } {
  const main: WsBlock[] = [];
  const events: Hat[] = [];
  let loose = 0;
  for (const b of ws.blocks?.blocks ?? []) {
    if (b.type === "pl_main") main.push(b);
    else if (b.type === "pl_event" || b.type === "pl_extend" || b.type === "pl_disable") {
      const order = Number((b.extraState as { order?: number } | undefined)?.order);
      events.push({ b, order: Number.isFinite(order) ? order : Infinity, y: b.y ?? 0 });
    } else loose++;
  }
  if (loose) r.warnings.push(`${loose} loose block(s) outside any hat were not applied`);
  events.sort((a, c) => a.order - c.order || a.y - c.y);
  return { main, events };
}

/** The flow with one scope replaced by the workspace's content (or the errors, nothing applied). */
export function fromWorkspace(flow: Flow, scope: Scope, ws: Workspace, defaults: Defaults = {}): FromResult {
  const r = new Reader(defaults);
  const out = clone(flow);
  const { main, events } = hats(ws, r);
  if (scope.kind === "global") {
    if (main.length) r.warnings.push("a main hat has no place among the global events: not applied");
    out.handlers = events.map(({ b }, i) => {
      if (b.type !== "pl_event") {
        r.err(`event ${i + 1}`, "extend / disable belong to a map block");
        return null;
      }
      return r.handler(b, (b.fields?.NAME as string) || `event ${i + 1}`);
    }).filter((h): h is Handler => h !== null);
  } else {
    if (main.length !== 1) r.err("main", main.length ? "only one main hat" : "the main hat is missing");
    const body = r.stmts(main[0]?.inputs?.DO?.block, scope.kind === "block" ? scope.name : "main");
    if (scope.kind === "main") {
      if (events.length) r.warnings.push("events in a plain flow's main view were not applied (use the global events)");
      out.main = body;
    } else {
      const block = out.workflow?.blocks.find((b) => b.name === scope.name);
      if (!block) return { ok: false, errors: [`no map block ${scope.name}`] };
      const globalNames = new Set(flow.handlers.map((h) => h.name));
      block.main = body;
      block.events = events.map(({ b }) => {
        const st = (b.extraState ?? {}) as { kind?: string; label?: string | null; max_per_run?: number | null };
        const where = b.fields?.NAME ? String(b.fields.NAME) : String(b.fields?.KEY ?? scope.name);
        if (b.type === "pl_disable") return { kind: "disable", key: r.name(b, "KEY", where) } as MapEvent;
        if (b.type === "pl_extend") {
          const key = r.name(b, "KEY", where);
          return {
            kind: "extend",
            key,
            steps: r.stmts(b.inputs?.DO?.block, st.label ?? `${scope.name}_${key}`),
            max_per_run: st.max_per_run ?? null,
            label: st.label ?? `${scope.name}_${key}`,
          } as MapEvent;
        }
        const h = r.handler(b, where);
        const kind =
          st.kind === "override" || st.kind === "add" ? st.kind : globalNames.has(h.name) ? "override" : "add";
        const label = st.label ?? (kind === "add" ? h.name : `${scope.name}_${h.name}`);
        return { kind, event: h, label } as MapEvent;
      });
    }
  }
  if (r.errors.length) return { ok: false, errors: r.errors };
  return { ok: true, flow: out, warnings: r.warnings };
}
