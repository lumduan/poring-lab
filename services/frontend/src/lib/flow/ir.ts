// The flow IR as the browser holds it (MW2, docs/planning/mw2-block-editor.md section 1). MW1's
// Pydantic models (packages/poring_flow/src/poring_flow/ir.py) are the ONLY source of truth; these
// types describe their CANONICAL JSON (`ir.to_json`: every field present, defaults included), which
// is what the backend returns and what every view converts to and from. flow.gen.ts is the
// json2ts mirror of the schema; check.ts pins these types against it at typecheck time.
//
// Equality is by canonical JSON (sorted keys): the backend's flow_hash is sha256 of the same text,
// with one browser exception: JSON cannot keep 2.0 apart from 2, so an integral FLOAT literal comes
// back as an int (float FIELDS such as timeout_s are floats again after validation).

export type MapRef = { kind: "map"; map: string };
export type CellRef = { kind: "cell"; map: string; x: number; y: number };
export type NpcRef = { kind: "npc"; key: string };
export type OptionRef = { kind: "option"; key: string };
export type ItemRef = { kind: "item"; id: number };
export type MobRef = { kind: "mob"; id: number };
export type SkillRef = { kind: "skill"; id: number; level: number | null };
export type WindowRef = { kind: "window"; name: string };
export type Ref = MapRef | CellRef | NpcRef | OptionRef | ItemRef | MobRef | SkillRef | WindowRef;
export const REF_KINDS = ["map", "cell", "npc", "option", "item", "mob", "skill", "window"] as const;

export type Outcome = "ok" | "failed" | "unsupported" | "interrupted" | "refused";
export const OUTCOMES: Outcome[] = ["ok", "failed", "unsupported", "interrupted", "refused"];

export type Lit = { kind: "lit"; value: boolean | number | string | Ref | Ref[] };
export type Var = { kind: "var"; name: string };
export type OutcomeLit = { kind: "outcome"; value: Outcome };
export type ListE = { kind: "list"; items: Expr[] };
export type Logic = { kind: "and" | "or"; terms: Expr[] };
export type Not = { kind: "not"; term: Expr };
export type Sense = { kind: "sense"; sensor: string; args: Record<string, Expr> };
export type CmpOp = "==" | "!=" | "<" | "<=" | ">" | ">=" | "in" | "not in";
export const CMP_OPS: CmpOp[] = ["==", "!=", "<", "<=", ">", ">=", "in", "not in"];
export type Cmp = { kind: "cmp"; op: CmpOp; left: Expr; right: Expr };
export type ArithOp = "+" | "-" | "*" | "//" | "%";
export type Arith = { kind: "arith"; op: ArithOp; left: Expr; right: Expr };
export type Do = { kind: "do"; action: ActionStmt };
export type Expr = Lit | Var | OutcomeLit | ListE | Sense | Cmp | Logic | Not | Arith | Do;
export type Range = { kind: "range"; start: Expr; stop: Expr; step: Expr };

export type ActionStmt = {
  kind: "action";
  block: string;
  concept: string;
  params: Record<string, Expr>;
  timeout_s: number;
  on_fail: "stop" | "continue";
  outcome_to: string | null;
  note: string | null;
};
export type If = { kind: "if"; cond: Expr; then: Stmt[]; orelse: Stmt[] };
export type While = {
  kind: "while";
  cond: Expr;
  body: Stmt[];
  max_iter: number | null;
  max_s: number | null;
};
export type WaitUntil = { kind: "wait_until"; cond: Expr; timeout_s: number; outcome_to: string | null };
export type Repeat = { kind: "repeat"; times: Expr; body: Stmt[] };
export type ForEach = { kind: "for"; var: string; items: Lit | Var | Range; body: Stmt[] };
export type SetVar = { kind: "set"; var: string; value: Expr };
export type CallProc = { kind: "call"; proc: string };
export type Stop = { kind: "stop"; reason: string };
export type Break = { kind: "break" };
export type Continue = { kind: "continue" };
export type ExitKind = "walk_exit" | "npc_warp" | "item_warp" | "death_respawn";
export const AUTHORED_EXITS = ["walk_exit", "npc_warp", "item_warp"] as const;
export type AuthoredExit = (typeof AUTHORED_EXITS)[number];
export type Exit = {
  kind: ExitKind;
  warp: CellRef | null;
  npc: NpcRef | null;
  options: OptionRef[];
  item: ItemRef | Var | null;
  to_block: string;
  to_entry: string;
  timeout_s: number;
};
export type TakeExit = { kind: "take_exit"; exit: Exit };
export type Stmt =
  | ActionStmt
  | If
  | While
  | WaitUntil
  | Repeat
  | ForEach
  | SetVar
  | CallProc
  | Stop
  | Break
  | Continue
  | TakeExit;

export type Entry = { name: string; at: CellRef | null; radius: number };

export type Priority = "critical" | "survival" | "upkeep";
export const PRIORITIES: Priority[] = ["critical", "survival", "upkeep"];
export type Then = "resume" | "skip_block" | "restart_flow" | "relocate" | "stop";
export const THENS: Then[] = ["resume", "skip_block", "restart_flow", "relocate", "stop"];
export type Handler = {
  name: string;
  when: Expr;
  until: Expr | null;
  rearm: Expr | null;
  priority: Priority;
  mode: "insert" | "preempt";
  escalate: string | null;
  max_insert_fails: number;
  cooldown_s: number;
  max_per_min: number | null;
  max_fires_per_10min: number;
  max_per_run: number | null;
  then: Then;
  body: Stmt[];
};
export type Override = { kind: "override"; event: Handler; label: string | null };
export type Extend = {
  kind: "extend";
  key: string;
  steps: Stmt[];
  max_per_run: number | null;
  label: string | null;
};
export type Disable = { kind: "disable"; key: string };
export type Add = { kind: "add"; event: Handler; label: string | null };
export type MapEvent = Override | Extend | Disable | Add;

export type MapBlock = {
  name: string;
  map: MapRef;
  entries: Entry[];
  targets: MobRef[];
  ignore: MobRef[];
  events: MapEvent[];
  main: Stmt[];
  resume_here: boolean;
};
export type Workflow = {
  start_block: string;
  start_entry: string;
  blocks: MapBlock[];
  run_until_stopped: boolean;
};
export type Target = { client: string; server: string; locale: string; path: "s2" | "rdp" };
export type Flow = {
  ir: 1;
  name: string;
  description: string;
  target: Target;
  assumes: Expr[];
  max_runtime_s: number;
  stop_when: Expr | null;
  variables: Record<string, Lit>;
  procedures: Record<string, Stmt[]>;
  handlers: Handler[];
  main: Stmt[] | null;
  workflow: Workflow | null;
};

// MW1's constants (ir.py): names, limits and the safety-critical set, fixed in code.
export const NAME = /^[A-Za-z][A-Za-z0-9_]{0,47}$/;
export const FLOW_NAME = /^[a-z][a-z0-9_]{0,47}$/;
export const MAP_ID = /^[A-Za-z0-9_@.\-]{1,40}$/;
export const KEY = /^[A-Za-z0-9_.\-]{1,64}$/;
export const SAFETY_CRITICAL = ["dead", "hp_critical", "unexpected_map"];
export const MAX_JSON_BYTES = 1 << 20;
export const MAX_JSON_DEPTH = 256;

// --- canonical JSON and equality ----------------------------------------------------------------
function sortKeys(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(sortKeys);
  if (v && typeof v === "object") {
    const out: Record<string, unknown> = {};
    for (const k of Object.keys(v as Record<string, unknown>).sort()) {
      out[k] = sortKeys((v as Record<string, unknown>)[k]);
    }
    return out;
  }
  if (typeof v === "string") return v.normalize("NFC");
  return v;
}

/** Sorted keys, no whitespace, NFC strings: the browser's view of MW1's canonical JSON. */
export function canonical(v: unknown): string {
  return JSON.stringify(sortKeys(v));
}

export function sameFlow(a: unknown, b: unknown): boolean {
  return canonical(a) === canonical(b);
}

export function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}

// --- constructors (every field present, MW1's defaults) ------------------------------------------
export function lit(value: Lit["value"]): Lit {
  return { kind: "lit", value };
}

export function action(
  block: string,
  concept: string,
  params: Record<string, Expr>,
  timeout_s: number,
): ActionStmt {
  return { kind: "action", block, concept, params, timeout_s, on_fail: "stop", outcome_to: null, note: null };
}

export function exitOf(kind: AuthoredExit, to_block: string, to_entry: string): Exit {
  return { kind, warp: null, npc: null, options: [], item: null, to_block, to_entry, timeout_s: 120 };
}

export function emptyFlow(name = "new_flow"): Flow {
  return {
    ir: 1,
    name,
    description: "",
    target: { client: "kro-20211103-prere", server: "lab-rathena", locale: "en", path: "s2" },
    assumes: [],
    max_runtime_s: 3600,
    stop_when: null,
    variables: {},
    procedures: {},
    handlers: [],
    main: null,
    workflow: {
      start_block: "start",
      start_entry: "arrival",
      blocks: [newBlock("start", "map_1")],
      run_until_stopped: false,
    },
  };
}

export function newBlock(name: string, map: string): MapBlock {
  return {
    name,
    map: { kind: "map", map },
    entries: [{ name: "arrival", at: null, radius: 2 }],
    targets: [],
    ignore: [],
    events: [],
    main: [{ kind: "stop", reason: "todo" }],
    resume_here: true,
  };
}

// --- node paths (MW1's ir.sites: main.<i>, <proc>.<i>, <handler label>.<i>, <block>.<i>) ----------
export function childBodies(s: Stmt): [string, Stmt[]][] {
  if (s.kind === "if") return [["then", s.then], ["orelse", s.orelse]];
  if (s.kind === "while" || s.kind === "repeat" || s.kind === "for") return [["body", s.body]];
  return [];
}

export function* walk(stmts: Stmt[], prefix: string): Generator<[string, Stmt]> {
  for (let i = 0; i < stmts.length; i++) {
    const path = `${prefix}.${i}`;
    yield [path, stmts[i]];
    for (const [field, body] of childBodies(stmts[i])) yield* walk(body, `${path}.${field}`);
  }
}

/** A map event's label (its node path root and Python function name), as MW1's event_label. */
export function eventLabel(ev: MapEvent, block: MapBlock): string {
  if (ev.kind === "disable") return block.name;
  if (ev.kind === "extend") return ev.label ?? `${block.name}_${ev.key}`;
  if (ev.kind === "override") return ev.label ?? `${block.name}_${ev.event.name}`;
  return ev.label ?? ev.event.name;
}

export function eventKey(ev: MapEvent): string {
  return ev.kind === "extend" || ev.kind === "disable" ? ev.key : ev.event.name;
}

/** Every exit statement of a map block's main, with its node path. */
export function exitsOf(block: MapBlock): { path: string; exit: Exit }[] {
  const out: { path: string; exit: Exit }[] = [];
  for (const [path, s] of walk(block.main, block.name)) if (s.kind === "take_exit") out.push({ path, exit: s.exit });
  return out;
}

/** The statement at a node path inside a list (`<root>.<i>[.then|.orelse|.body.<j>]...`). */
export function stmtAt(stmts: Stmt[], rest: string[]): { list: Stmt[]; index: number } | null {
  let list = stmts;
  let i = 0;
  while (i < rest.length) {
    const index = Number(rest[i]);
    if (!Number.isInteger(index) || index < 0 || index >= list.length) return null;
    if (i === rest.length - 1) return { list, index };
    const field = rest[i + 1];
    const body = childBodies(list[index]).find(([f]) => f === field);
    if (!body) return null;
    list = body[1];
    i += 2;
  }
  return null;
}
