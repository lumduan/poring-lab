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
import { CREDENTIALS, DEF_BY_TYPE, HOTKEYS, RUNNER_ROLES, SENTENCE, SENTENCE_BY_TYPE } from "./blockdefs.ts";
import { argsText, callArgsText, ExprError, exprText, hasDo, parseArgs, parseCallArgs, parseExpr, parseParams } from "./expr.ts";
import { fieldOf, HUNT_TYPE, type HuntRules, omitted, paramOf, params as huntParams } from "./hunt.ts";
import { CLASS_KEY, DETECT_SENSOR, MODEL_KEY, SENSOR_BLOCK } from "./models.ts";
import { blockWords, type Issue, type Loose, stackSize } from "./words.ts";
import {
  type ActionStmt,
  type CellRef,
  type Exit,
  type Expr,
  type Flow,
  type Handler,
  type ItemRef,
  type Lit,
  type MapBlock,
  type MapEvent,
  type Ref,
  type Stmt,
  type Var,
  clone,
  eventLabel,
  KEY,
  MAP_ID,
  MAX_RANK,
  NAME,
} from "./ir.ts";
import { type Def, globalOf, MAIN_TAB, namesOf, nodeById, paramsText, type PNode, type Project, tabOf } from "./project.ts";

export type Scope = { kind: "block"; name: string } | { kind: "global" } | { kind: "main" } | { kind: "functions" };
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
/** `paths`: each statement / hat block id -> its node path in the NEW flow (lint findings and run
 * results land on the right block after edits); `issues`: the errors with their block; `loose`: the
 * detached stacks (they are not applied: "Not running"). */
export type FromResult =
  | { ok: true; flow: Flow; warnings: string[]; paths: Record<string, string>; loose: Loose[] }
  | { ok: false; errors: string[]; issues: Issue[]; loose: Loose[] };
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

/** The model block's fields of a detector sensor, when it is one exactly (both text literals). */
function detectFields(e: Expr): Record<string, string> | null {
  if (e.kind !== "sense" || !(e.sensor in SENSOR_BLOCK)) return null;
  const keys = Object.keys(e.args).sort();
  if (keys.length !== 2 || keys[0] !== "label" || keys[1] !== "model") return null;
  const m = e.args.model;
  const c = e.args.label;
  if (m.kind !== "lit" || typeof m.value !== "string" || !MODEL_KEY.test(m.value)) return null;
  if (c.kind !== "lit" || typeof c.value !== "string" || !CLASS_KEY.test(c.value)) return null;
  return { MODEL: m.value, CLASS: c.value };
}

/** A model block, or a compare / and / or / not holding one directly: shown as blocks, so a learner
 * sees "if detector … count of … > 2" as blocks rather than a line of text. */
function blockish(e: Expr): boolean {
  if (detectFields(e)) return true;
  if (e.kind === "cmp") return blockish(e.left) || blockish(e.right);
  if (e.kind === "and" || e.kind === "or") return e.terms.some(blockish);
  if (e.kind === "not") return blockish(e.term);
  return false;
}

function exprBlock(e: Expr, path: string, ids: Ids): WsBlock {
  if (e.kind === "callv") return { type: "pl_callv", fields: { PROC: e.proc, ARGS: callArgsText(e.args, e.kwargs) } };
  const det = e.kind === "sense" ? detectFields(e) : null;
  if (det && e.kind === "sense") return { type: SENSOR_BLOCK[e.sensor], fields: det };
  if (e.kind === "do" && paramsPlain(e.action)) {
    return {
      type: "pl_do",
      id: ids.take(`n:${path}:${e.action.block}`),
      fields: { BLOCK: e.action.block, ARGS: argsText(e.action.params) },
      extraState: actionRest(e.action),
    };
  }
  if (!hasDo(e) && !blockish(e)) return { type: "pl_expr", fields: { TEXT: exprText(e) } };
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

/** An item list as a sentence field's text: "501, 502" (ids) or "501, WING" (ids and variables);
 * null when the value is anything else (a list variable, an empty list): the generic block. */
function itemsText(e: Expr): string | null {
  const id = (x: unknown) => (typeof x === "object" && x !== null && !Array.isArray(x) && (x as Ref).kind === "item" ? (x as ItemRef).id : null);
  if (e.kind === "lit" && Array.isArray(e.value) && e.value.length && e.value.every((r) => id(r) !== null)) {
    return e.value.map((r) => String(id(r))).join(", ");
  }
  if (e.kind === "list" && e.items.length && e.items.some((i) => i.kind === "var")) {
    const parts = e.items.map((i) => (i.kind === "var" ? i.name : i.kind === "lit" && id(i.value) !== null ? String(id(i.value)) : null));
    return parts.every((x) => x !== null) ? parts.join(", ") : null;
  }
  return null;
}

/** The fields of a shop / Kafra / storage action shown as its sentence block, when every
 * parameter fits a field exactly; else null (the generic block keeps it, exactly). */
function sentenceFields(a: ActionStmt): Record<string, string> | null {
  const spec = SENTENCE[a.block];
  if (!spec || Object.keys(a.params).some((k) => !spec.fields.some((f) => f.param === k))) return null;
  const out: Record<string, string> = {};
  for (const f of spec.fields) {
    const v = a.params[f.param];
    if (!v) {
      if (!f.optional) return null;
      out[f.field] = "";
      continue;
    }
    const r = v.kind === "lit" && typeof v.value === "object" && !Array.isArray(v.value) ? v.value : null;
    if (f.kind === "npc" && r?.kind === "npc") out[f.field] = r.key;
    else if (f.kind === "map" && r?.kind === "map") out[f.field] = r.map;
    else if (f.kind === "items" && itemsText(v) !== null) out[f.field] = itemsText(v)!;
    else return null;
  }
  return out;
}

function paramsPlain(a: ActionStmt): boolean {
  return Object.values(a.params).every((e) => !hasDo(e));
}

/** The pl_hunt fields of a hunt action: only when it has the block's parameters and no other,
 * each a literal rule version (or option) among its choices; an OPTIONAL parameter that is absent
 * shows its default, and one written AT its default stays a generic block (the editor would leave
 * it out: not exact). Anything else stays a generic block, exactly. */
function huntFields(a: ActionStmt, rules: HuntRules): Record<string, string> | null {
  const ps = huntParams(rules);
  const omit = omitted(rules);
  if (Object.keys(a.params).some((k) => !ps.some((p) => p.name === k))) return null;
  const out: Record<string, string> = {};
  for (const p of ps) {
    const e = a.params[p.name];
    if (!e && p.name in omit) {
      out[fieldOf(p.name)] = omit[p.name];
      continue;
    }
    if (!e || e.kind !== "lit" || typeof e.value !== "string") return null;
    const v = e.value;
    if (!p.choices.some((c) => c.id === v) || omit[p.name] === v) return null;
    out[fieldOf(p.name)] = v;
  }
  return out;
}

/** The hunt block's extra state: what it does not show, plus the optional parameters' defaults
 * (`omit`: written back only when the dropdown differs from them). */
function huntState(rest: object, rules: HuntRules | null): object {
  const omit = rules ? omitted(rules) : {};
  return Object.keys(omit).length ? { ...rest, omit } : rest;
}

function stmtBlock(s: Stmt, path: string, ids: Ids): WsBlock {
  const id = ids.take(`n:${path}`);
  const b = ((): WsBlock => {
    switch (s.kind) {
      case "action": {
        if (s.block === "hunt" && ids.hunt) {
          const f = huntFields(s, ids.hunt);
          if (f) return { type: HUNT_TYPE, fields: f, extraState: huntState(actionRest(s), ids.hunt) };
        }
        const own = ownBlock(s);
        if (own) return own;
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
        const sentence = sentenceFields(s);
        if (sentence) return { type: SENTENCE[s.block].type, fields: sentence, extraState: actionRest(s) };
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
        return { type: "pl_call", fields: { PROC: s.proc, ARGS: callArgsText(s.args ?? [], s.kwargs ?? {}) } };
      case "return":
        return { type: "pl_return", inputs: s.value ? { VALUE: { block: exprBlock(s.value, path, ids) } } : {} };
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

/** A string literal's text, else null. */
function litText(e: Expr | undefined): string | null {
  return e && e.kind === "lit" && typeof e.value === "string" ? e.value : null;
}

/** press_key and the runner's block, when their parameters are exactly what their block holds
 * (else the generic block keeps them, lossless). */
function ownBlock(s: ActionStmt): WsBlock | null {
  const keys = Object.keys(s.params).sort();
  if (s.block === "press_key" && keys.length === 1 && keys[0] === "key") {
    const k = litText(s.params.key);
    if (k !== null && (HOTKEYS as readonly string[]).includes(k)) return { type: "pl_press_key", fields: { KEY: k }, extraState: actionRest(s) };
    // the key as a value: a function's input (matpilot round 15 #2)
    return { type: "pl_press_key_v", inputs: { KEY: { block: exprBlock(s.params.key, "key", new Ids()) } }, extraState: actionRest(s) };
  }
  if (s.block === "assert_save_point" && keys.length === 1 && keys[0] === "cell") {
    const v = s.params.cell;
    if (v.kind === "lit" && typeof v.value === "object" && !Array.isArray(v.value) && v.value.kind === "cell") {
      return { type: "pl_save_point", fields: { MAP: v.value.map, X: v.value.x, Y: v.value.y }, extraState: actionRest(s) };
    }
  }
  if (s.block === "login" && keys.join(",") === "credential,server") {
    const sv = litText(s.params.server);
    const cr = litText(s.params.credential);
    if (sv !== null && cr !== null && (CREDENTIALS as readonly string[]).includes(cr)) return { type: "pl_login", fields: { SERVER: sv, CREDENTIAL: cr }, extraState: actionRest(s) };
  }
  if (s.block === "choose_character" && (keys.length === 0 || (keys.length === 1 && keys[0] === "name"))) {
    const nm = keys.length ? litText(s.params.name) : "";
    if (nm !== null) return { type: "pl_choose_character", fields: { CHAR: nm }, extraState: actionRest(s) };
  }
  if (s.block === "dungeon_hunt" && keys.join(",") === RUNNER_ROLES.map((r) => r.param).sort().join(",")) {
    const fields: Record<string, string> = {};
    for (const r of RUNNER_ROLES) {
      const v = litText(s.params[r.param]);
      if (v === null || !NAME.test(v)) return null;
      fields[r.field] = v;
    }
    return { type: "pl_dungeon_hunt", fields, extraState: actionRest(s) };
  }
  return null;
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
  if (x.kind === "item_warp" && x.proc && !x.item && !x.warp && !x.npc && !x.options.length) {
    return { type: "pl_exit_item_fn", fields: { FN: x.proc, ...to }, extraState: st };
  }
  if (x.kind === "item_warp" && x.item && x.proc === undefined && !x.warp && !x.npc && !x.options.length) {
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
  } else if (scope.kind === "functions") {
    // each function a hat; its statements' node paths are <name>.<i> (MW1's ir.sites)
    for (const [name, body] of Object.entries(flow.procedures)) {
      place({ type: "pl_def", id: ids.take(`h:def:${name}`), fields: { NAME: name }, inputs: chainInput("DO", body, name, ids), extraState: {} }, 20);
    }
  } else {
    place({ type: "pl_main", id: ids.take("h:main"), inputs: chainInput("DO", flow.main ?? [], "main", ids), extraState: {} }, 20);
  }
  return { blocks: { languageVersion: 0, blocks: top } };
}

// --- workspace -> IR ------------------------------------------------------------------------------
class Reader {
  errors: string[] = [];
  issues: Issue[] = [];
  warnings: string[] = [];
  paths: Record<string, string> = {};
  private at: string | null = null; // the statement block being read (an issue names it)
  private defaults: Defaults;
  constructor(defaults: Defaults) {
    this.defaults = defaults;
  }

  err(where: string, msg: string): void {
    if (this.errors.length < 50) {
      this.errors.push(`${where}: ${msg}`);
      this.issues.push({ where, text: msg, id: this.at });
    }
  }

  /** Read under a block: its id names any issue, and records its node path. */
  under<T>(b: WsBlock, path: string | null, read: () => T): T {
    const prev = this.at;
    if (b.id) {
      this.at = b.id;
      if (path !== null) this.paths[b.id] = path;
    }
    try {
      return read();
    } finally {
      this.at = prev;
    }
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
          const e = this.asCalls(parseExpr(this.field(b, "TEXT")));
          this.unknownCalls(e, where, what);
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
      case "pl_detect_sees":
      case "pl_detect_count": {
        const model = this.field(b, "MODEL").trim();
        const label = this.field(b, "CLASS").trim();
        if (!MODEL_KEY.test(model)) this.err(where, `${what}: the model ${JSON.stringify(model)} is not a model id`);
        if (!CLASS_KEY.test(label)) this.err(where, `${what}: the class ${JSON.stringify(label)} is not a class name`);
        return {
          kind: "sense",
          sensor: DETECT_SENSOR[b.type],
          args: { label: { kind: "lit", value: label }, model: { kind: "lit", value: model } },
        };
      }
      case "pl_do":
        return { kind: "do", action: this.generic(b, where) };
      case "pl_callv": {
        const proc = this.name(b, "PROC", where);
        const a = this.callArgs(b, where, proc);
        return { kind: "callv", proc, args: a.args, kwargs: a.kwargs };
      }
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

  /** A call block's inputs from their Python text. */
  callArgs(b: WsBlock, where: string, proc: string): { args: Expr[]; kwargs: Record<string, Expr> } {
    try {
      const a = parseCallArgs(this.field(b, "ARGS"));
      return { args: a.args.map((e) => this.asCalls(e)), kwargs: Object.fromEntries(Object.entries(a.kwargs).map(([k, v]) => [k, this.asCalls(v)])) };
    } catch (e) {
      this.err(where, `${proc}: ${e instanceof ExprError ? e.message : "its inputs cannot be read"}`);
      return { args: [], kwargs: {} };
    }
  }

  /** The project model: a name the node calls a FUNCTION reads as its call, not a sensor
   * (`heal()` in a condition is the function's value). */
  fns: ReadonlySet<string> = new Set();
  asCalls(e: Expr): Expr {
    const walk = (x: Expr): Expr => {
      switch (x.kind) {
        case "sense":
          if (this.fns.has(x.sensor)) return { kind: "callv", proc: x.sensor, args: [], kwargs: Object.fromEntries(Object.entries(x.args).map(([k, v]) => [k, walk(v)])) };
          return { ...x, args: Object.fromEntries(Object.entries(x.args).map(([k, v]) => [k, walk(v)])) };
        case "cmp":
          return { ...x, left: walk(x.left), right: walk(x.right) };
        case "arith":
          return { ...x, left: walk(x.left), right: walk(x.right) };
        case "and":
        case "or":
          return { ...x, terms: x.terms.map(walk) };
        case "not":
          return { ...x, term: walk(x.term) };
        case "list":
          return { ...x, items: x.items.map(walk) };
        case "callv":
          return { ...x, args: x.args.map(walk), kwargs: Object.fromEntries(Object.entries(x.kwargs).map(([k, v]) => [k, walk(v)])) };
        default:
          return x;
      }
    };
    return walk(e);
  }

  /** A call with positional inputs of a name that is no function here: a sensor or an action
   * takes its inputs by name (the parser cannot tell them apart; the node's names can). */
  unknownCalls(e: Expr, where: string, what: string): void {
    const seen: string[] = [];
    const walk = (x: Expr): void => {
      if (x.kind === "callv") {
        if (!this.fns.has(x.proc)) seen.push(x.proc);
        x.args.forEach(walk);
        Object.values(x.kwargs).forEach(walk);
      } else if (x.kind === "cmp" || x.kind === "arith") {
        walk(x.left);
        walk(x.right);
      } else if (x.kind === "and" || x.kind === "or") x.terms.forEach(walk);
      else if (x.kind === "not") walk(x.term);
      else if (x.kind === "list") x.items.forEach(walk);
      else if (x.kind === "sense") Object.values(x.args).forEach(walk);
    };
    walk(e);
    for (const n of seen) this.err(where, `${what}: ${n}(...) is not a function of this node: a sensor or an action takes its inputs by name, e.g. sees(mob=mob(1))`);
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
    return this.under(b, where, () => this.stmtOf(b, where));
  }

  /** A sentence field's item list: ids and variable names, comma separated (one at least). */
  items(b: WsBlock, field: string, where: string): Expr {
    const tokens = this.field(b, field)
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    if (!tokens.length) this.err(where, `${field.toLowerCase()}: at least one item id or variable`);
    const parts: Expr[] = [];
    for (const t of tokens) {
      if (/^[0-9]{1,8}$/.test(t) && Number(t) >= 1) parts.push({ kind: "lit", value: { kind: "item", id: Number(t) } });
      else if (NAME.test(t)) parts.push({ kind: "var", name: t });
      else this.err(where, `${field.toLowerCase()}: ${JSON.stringify(t)} is not an item id or a variable`);
    }
    if (parts.every((x) => x.kind === "lit")) return { kind: "lit", value: parts.map((x) => (x as { value: ItemRef }).value) };
    return { kind: "list", items: parts };
  }

  private stmtOf(b: WsBlock, where: string): Stmt {
    const sentence = SENTENCE_BY_TYPE[b.type];
    if (sentence) {
      const params: Record<string, Expr> = {};
      for (const f of SENTENCE[sentence].fields) {
        if (f.optional && !this.field(b, f.field).trim()) continue;
        if (f.kind === "npc") params[f.param] = { kind: "lit", value: { kind: "npc", key: this.name(b, f.field, where, KEY) } };
        else if (f.kind === "map") params[f.param] = { kind: "lit", value: { kind: "map", map: this.name(b, f.field, where, MAP_ID) } };
        else params[f.param] = this.items(b, f.field, where);
      }
      return { kind: "action", block: sentence, params, ...this.rest(b, sentence, where) };
    }
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
        // the dropdowns ARE the parameters: P_<NAME> -> <name>, each a rule version (or option)
        // literal; an optional one at its default (extraState `omit`) is left out (absent = it)
        const omit = ((b.extraState ?? {}) as { omit?: Record<string, string> }).omit ?? {};
        const ps: Record<string, Expr> = {};
        for (const [k, v] of Object.entries(b.fields ?? {})) {
          const name = paramOf(k);
          if (name === null) continue;
          if (typeof v !== "string" || !v) this.err(where, `hunt: ${name} has no rule version`);
          if (name in omit && omit[name] === v) continue;
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
      case "pl_call": {
        const proc = this.name(b, "PROC", where);
        const a = this.callArgs(b, where, proc);
        return { kind: "call", proc, args: a.args, kwargs: a.kwargs };
      }
      case "pl_return":
        return { kind: "return", value: b.inputs?.VALUE?.block ? this.expr(b.inputs.VALUE.block, where, "the value") : null };
      case "pl_save_point":
        return {
          kind: "action",
          block: "assert_save_point",
          params: { cell: { kind: "lit", value: { kind: "cell", map: this.name(b, "MAP", where, MAP_ID), x: this.int(b, "X", where), y: this.int(b, "Y", where) } } },
          ...this.rest(b, "assert_save_point", where),
        };
      case "pl_login":
        return {
          kind: "action",
          block: "login",
          params: { server: { kind: "lit", value: this.name(b, "SERVER", where, KEY) }, credential: { kind: "lit", value: this.name(b, "CREDENTIAL", where, /^[a-z][a-z0-9_]{0,31}$/) } },
          ...this.rest(b, "login", where),
        };
      case "pl_choose_character": {
        const nm = this.field(b, "CHAR").trim();
        return { kind: "action", block: "choose_character", params: nm ? { name: { kind: "lit", value: nm } } : {}, ...this.rest(b, "choose_character", where) };
      }
      case "pl_press_key": {
        const k = this.field(b, "KEY");
        if (!(HOTKEYS as readonly string[]).includes(k)) this.err(where, `press key ${JSON.stringify(k)}: one of ${HOTKEYS.join(", ")}`);
        return { kind: "action", block: "press_key", params: { key: { kind: "lit", value: k } }, ...this.rest(b, "press_key", where) };
      }
      case "pl_press_key_v":
        return { kind: "action", block: "press_key", params: { key: this.expr(b.inputs?.KEY?.block, where, "the key") }, ...this.rest(b, "press_key", where) };
      case "pl_dungeon_hunt": {
        const params: Record<string, Expr> = {};
        for (const r of RUNNER_ROLES) params[r.param] = { kind: "lit", value: this.name(b, r.field, where) };
        return { kind: "action", block: "dungeon_hunt", params, ...this.rest(b, "dungeon_hunt", where) };
      }
      case "pl_stop":
        return { kind: "stop", reason: this.name(b, "REASON", where, /^[a-z_]{1,40}$/) };
      case "pl_break":
        return { kind: "break" };
      case "pl_continue":
        return { kind: "continue" };
      case "pl_exit_walk":
      case "pl_exit_npc":
      case "pl_exit_item":
      case "pl_exit_item_fn":
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
    if (b.type === "pl_exit_item_fn") return { ...base, kind: "item_warp", proc: this.name(b, "FN", where) };
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

  /** `root`: the node path its body's statements hang from (a map event's label). */
  handler(b: WsBlock, where: string, root?: string): Handler {
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
      body: this.stmts(b.inputs?.DO?.block, root ?? name),
      ...r,
    };
  }
}

type Hat = { b: WsBlock; order: number; y: number };

const HATS = new Set(["pl_main", "pl_event", "pl_extend", "pl_disable"]);

function hats(ws: Workspace, r: Reader): { main: WsBlock[]; events: Hat[]; defs: WsBlock[]; vars: WsBlock[]; loose: Loose[] } {
  const main: WsBlock[] = [];
  const events: Hat[] = [];
  const defs: WsBlock[] = [];
  const vars: WsBlock[] = [];
  const loose: Loose[] = [];
  for (const b of ws.blocks?.blocks ?? []) {
    if (b.type === "pl_main") main.push(b);
    else if (b.type === "pl_def") defs.push(b);
    else if (b.type === "pl_vardecl") vars.push(b);
    else if (HATS.has(b.type)) {
      const order = Number((b.extraState as { order?: number } | undefined)?.order);
      events.push({ b, order: Number.isFinite(order) ? order : Infinity, y: b.y ?? 0 });
    } else {
      const value = DEF_BY_TYPE[b.type] !== undefined && DEF_BY_TYPE[b.type].output !== undefined;
      loose.push({ id: b.id ?? null, type: b.type, words: blockWords(b), count: value ? 1 : stackSize(b), value });
    }
  }
  if (loose.length) r.warnings.push(`${loose.length} loose block(s) outside any hat were not applied`);
  events.sort((a, c) => a.order - c.order || a.y - c.y);
  defs.sort((a, c) => (a.y ?? 0) - (c.y ?? 0));
  vars.sort((a, c) => (a.y ?? 0) - (c.y ?? 0));
  return { main, events, defs, vars, loose };
}

/** The flow with one scope replaced by the workspace's content (or the errors, nothing applied). */
export function fromWorkspace(flow: Flow, scope: Scope, ws: Workspace, defaults: Defaults = {}): FromResult {
  const r = new Reader(defaults);
  const out = clone(flow);
  const { main, events, defs, loose } = hats(ws, r);
  if (scope.kind !== "functions" && defs.length) r.warnings.push("a function belongs on the functions tab: not applied here");
  if (scope.kind === "functions") {
    if (main.length || events.length) r.warnings.push("only functions belong on the functions tab: the other hats were not applied");
    const procs: Record<string, Stmt[]> = {};
    for (const b of defs) {
      const name = String(b.fields?.NAME ?? "").trim();
      r.under(b, name || null, () => {
        const n = r.name(b, "NAME", `function ${name || "?"}`);
        if (n in procs) r.err(`function ${n}`, "two functions have this name");
        procs[n] = r.stmts(b.inputs?.DO?.block, n);
      });
    }
    out.procedures = procs;
  } else if (scope.kind === "global") {
    if (main.length) r.warnings.push("a main hat has no place among the global events: not applied");
    out.handlers = events.map(({ b }, i) => {
      if (b.type !== "pl_event") {
        r.under(b, null, () => r.err(`event ${i + 1}`, "extend / disable belong to a map block"));
        return null;
      }
      const name = (b.fields?.NAME as string) || `event ${i + 1}`;
      return r.under(b, String(b.fields?.NAME ?? ""), () => r.handler(b, name));
    }).filter((h): h is Handler => h !== null);
  } else {
    const root = scope.kind === "block" ? scope.name : "main";
    if (main.length !== 1) r.err("main", main.length ? "only one main hat" : "the main hat is missing");
    const body = main[0] ? r.under(main[0], root, () => r.stmts(main[0].inputs?.DO?.block, root)) : [];
    if (scope.kind === "main") {
      if (events.length) r.warnings.push("events in a plain flow's main view were not applied (use the global events)");
      out.main = body;
    } else {
      const block = out.workflow?.blocks.find((b) => b.name === scope.name);
      if (!block) return { ok: false, errors: [`no map block ${scope.name}`], issues: [], loose };
      const globalNames = new Set(flow.handlers.map((h) => h.name));
      block.main = body;
      block.events = events.map(({ b }) => {
        const st = (b.extraState ?? {}) as { kind?: string; label?: string | null; max_per_run?: number | null };
        const where = b.fields?.NAME ? String(b.fields.NAME) : String(b.fields?.KEY ?? scope.name);
        if (b.type === "pl_disable") return r.under(b, null, () => ({ kind: "disable", key: r.name(b, "KEY", where) }) as MapEvent);
        if (b.type === "pl_extend") {
          const key = String(b.fields?.KEY ?? "").trim();
          const label = st.label ?? `${scope.name}_${key}`;
          return r.under(b, label, () => ({
            kind: "extend",
            key: r.name(b, "KEY", where),
            steps: r.stmts(b.inputs?.DO?.block, label),
            max_per_run: st.max_per_run ?? null,
            label,
          }) as MapEvent);
        }
        // the event's node path is its LABEL (ir.event_label), so its body's blocks get it
        const named = String(b.fields?.NAME ?? "").trim();
        const kind0 = st.kind === "override" || st.kind === "add" ? st.kind : globalNames.has(named) ? "override" : "add";
        const root0 = st.label ?? (kind0 === "add" ? named : `${scope.name}_${named}`);
        const h = r.under(b, root0, () => r.handler(b, where, root0));
        const kind =
          st.kind === "override" || st.kind === "add" ? st.kind : globalNames.has(h.name) ? "override" : "add";
        const label = st.label ?? (kind === "add" ? h.name : `${scope.name}_${h.name}`);
        return { kind, event: h, label } as MapEvent;
      });
    }
  }
  if (r.errors.length) return { ok: false, errors: r.errors, issues: r.issues, loose };
  return { ok: true, flow: out, warnings: r.warnings, paths: r.paths, loose };
}

// --- THE PROJECT MODEL (2026-11-13, docs/planning/project-model.md): one tab of one node <-> blocks --
export type TabScope = { node: string; tab: string };
export type TabResult =
  | { ok: true; project: Project; warnings: string[]; paths: Record<string, string>; loose: Loose[] }
  | { ok: false; errors: string[]; issues: Issue[]; loose: Loose[] };

/** The functions a node can call: its own and Global's (a node's replaces Global's of that name). */
export function callableOn(p: Project, nodeId: string): Set<string> {
  const out = new Set<string>();
  for (const n of [nodeById(p, nodeId), globalOf(p)]) if (n) for (const [k, v] of namesOf(n)) if (v.kind !== "var") out.add(k);
  return out;
}

function defHat(p: Project, node: PNode, d: Def, order: number, ids: Ids): WsBlock {
  if (d.on) {
    const h: Handler = { ...d.on, name: d.name, body: d.body };
    const b = eventHat(h, "global", null, order, ids);
    const replaces = node.kind !== "global" && globalOf(p) !== undefined && namesOf(globalOf(p)!).has(d.name);
    b.fields = { ...b.fields, SCOPE: node.kind === "global" ? "every node" : replaces ? "replaces Global's" : "this node" };
    b.extraState = { order, rest: restOf(h) };
    return b;
  }
  return {
    type: "pl_def",
    id: ids.take(`h:def:${d.name}`),
    fields: { NAME: d.name, PARAMS: paramsText(d, (l) => exprText(l)) },
    inputs: chainInput("DO", d.body, d.name, ids),
    extraState: { order },
  };
}

/** One tab's blocks: the main hat (the main tab only), then its functions and events, then its
 * variables. A statement's node path is the engine's site inside the tab ("main.2", "heal.0"). */
export function tabToWorkspace(p: Project, scope: TabScope, opts: ConvertOptions = {}): Workspace {
  const node = nodeById(p, scope.node);
  const t = node ? tabOf(node, scope.tab) : undefined;
  if (!node || !t) throw new Error(`no tab ${scope.node}/${scope.tab}`);
  const ids = new Ids(opts.hunt ?? null);
  const top: WsBlock[] = [];
  let y = 20;
  const place = (b: WsBlock) => {
    b.x = 20;
    b.y = y;
    y += 90 + 46 * height(b.inputs?.DO?.block);
    top.push(b);
  };
  if (t.main) place({ type: "pl_main", id: ids.take("h:main"), inputs: chainInput("DO", t.main, "main", ids), extraState: {} });
  t.defs.forEach((d, i) => place(defHat(p, node, d, i, ids)));
  for (const [name, v] of Object.entries(t.vars)) place({ type: "pl_vardecl", id: ids.take(`h:var:${name}`), fields: { NAME: name }, inputs: { VALUE: { block: exprBlock(v, name, ids) } }, extraState: {} });
  return { blocks: { languageVersion: 0, blocks: top } };
}

/** The project with one tab replaced by its blocks (or the errors, nothing applied). */
export function tabFromWorkspace(p: Project, scope: TabScope, ws: Workspace, defaults: Defaults = {}): TabResult {
  const r = new Reader(defaults);
  r.fns = callableOn(p, scope.node);
  const out = clone(p);
  const node = nodeById(out, scope.node);
  const t = node ? tabOf(node, scope.tab) : undefined;
  if (!node || !t) return { ok: false, errors: [`no tab ${scope.node}/${scope.tab}`], issues: [], loose: [] };
  const { main, events, defs, vars, loose } = hats(ws, r);
  for (const d of defs) {
    const nm = String(d.fields?.NAME ?? "").trim();
    if (nm) r.fns = new Set([...r.fns, nm]); // a function written on this tab is callable at once
  }
  const isMain = t.name === MAIN_TAB && node.kind !== "global";
  if (isMain) {
    if (main.length !== 1) r.err("main", main.length ? "only one start block" : "the start block is missing (a main tab begins with it)");
    t.main = main[0] ? r.under(main[0], "main", () => r.stmts(main[0].inputs?.DO?.block, "main")) : [];
  } else {
    if (main.length) r.warnings.push("the start block belongs on the main tab: not applied here");
    t.main = null;
  }
  const out_defs: Def[] = [];
  const seen = new Set<string>();
  const order = [...defs.map((b) => ({ b, ev: false })), ...events.map((h) => ({ b: h.b, ev: true }))].sort((a, c) => (a.b.y ?? 0) - (c.b.y ?? 0));
  for (const { b, ev } of order) {
    if (b.type === "pl_extend" || b.type === "pl_disable") {
      r.under(b, null, () => r.err(String(b.fields?.KEY ?? "event"), "a map replaces Global's event by writing its own event of the same name (extend / disable are gone)"));
      continue;
    }
    const nm = String(b.fields?.NAME ?? "").trim();
    const where = `${ev ? "event" : "function"} ${nm || "?"}`;
    const d = r.under(b, nm || null, (): Def | null => {
      const name = r.name(b, "NAME", where);
      if (seen.has(name)) r.err(where, "two definitions on this tab have this name");
      seen.add(name);
      if (ev) {
        const h = r.handler(b, where, name);
        const { name: _n, body, ...on } = h;
        void _n;
        return { name, params: [], varargs: null, kwargs: null, body, on };
      }
      let ps: ReturnType<typeof parseParams> = { params: [], varargs: null, kwargs: null };
      try {
        ps = parseParams(r.field(b, "PARAMS"));
      } catch (e) {
        r.err(where, `its inputs: ${e instanceof ExprError ? e.message : "cannot be read"}`);
      }
      const body = r.stmts(b.inputs?.DO?.block, name);
      if (!body.length) r.err(where, "a function needs at least one block inside");
      return { name, ...ps, body, on: null };
    });
    if (d) out_defs.push(d);
  }
  t.defs = out_defs;
  const vs: Record<string, Lit> = {};
  for (const b of vars) {
    const nm = String(b.fields?.NAME ?? "").trim();
    r.under(b, null, () => {
      const name = r.name(b, "NAME", `variable ${nm || "?"}`);
      const v = r.expr(b.inputs?.VALUE?.block, `variable ${name}`, "its value");
      if (v.kind !== "lit") r.err(`variable ${name}`, "its first value must be a plain value (a number, a text, True / False)");
      else if (name in vs || seen.has(name)) r.err(`variable ${name}`, "this name is used twice on this tab");
      else vs[name] = v;
    });
  }
  t.vars = vs;
  if (r.errors.length) return { ok: false, errors: r.errors, issues: r.issues, loose };
  return { ok: true, project: out, warnings: r.warnings, paths: r.paths, loose };
}

