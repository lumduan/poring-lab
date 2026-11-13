// Expressions as TEXT for the block editor's condition / argument fields: a small subset of MW1's
// Python view (packages/poring_flow/src/poring_flow/pyview.py), parsed here by our own linear
// recursive-descent parser and NEVER evaluated (no eval, no Function). `parseExpr(exprText(e))`
// equals `e` for every expression without an action call (`do`), which the block editor shows as
// its own block. Differences from the Python view, all lossless:
// - sensor arguments are written by name (`sees(mob=mob(9109), within=15)`): no catalogue needed;
// - nested and / or / arithmetic are parenthesised so the IR's nesting is kept exactly.
import type { ArithOp, CmpOp, Expr, Lit, Outcome, Ref } from "./ir.ts";
import { NAME } from "./ir.ts";

const OUTCOME_CONST: Record<string, Outcome> = {
  OK: "ok",
  FAILED: "failed",
  UNSUPPORTED: "unsupported",
  INTERRUPTED: "interrupted",
  REFUSED: "refused",
};
const CONST_OF: Record<Outcome, string> = Object.fromEntries(
  Object.entries(OUTCOME_CONST).map(([k, v]) => [v, k]),
) as Record<Outcome, string>;
const REF_CALLS = ["cell", "npc", "option", "item", "mob", "skill", "map_id", "window"];
export const MAX_EXPR_CHARS = 2000;
const MAX_DEPTH = 64;

// --- printing -------------------------------------------------------------------------------------
export function refText(r: Ref): string {
  switch (r.kind) {
    case "map":
      return `map_id(${JSON.stringify(r.map)})`;
    case "cell":
      return `cell(${JSON.stringify(r.map)}, ${r.x}, ${r.y})`;
    case "npc":
      return `npc(${JSON.stringify(r.key)})`;
    case "option":
      return `option(${JSON.stringify(r.key)})`;
    case "item":
      return `item(${r.id})`;
    case "mob":
      return `mob(${r.id})`;
    case "skill":
      return r.level === null ? `skill(${r.id})` : `skill(${r.id}, level=${r.level})`;
    case "window":
      return `window(${JSON.stringify(r.name)})`;
  }
}

function litText(v: Lit["value"]): string {
  if (typeof v === "boolean") return v ? "True" : "False";
  if (typeof v === "number") return String(v);
  if (typeof v === "string") return JSON.stringify(v);
  if (Array.isArray(v)) return `[${v.map(refText).join(", ")}]`;
  return refText(v);
}

const isBinary = (e: Expr) => e.kind === "and" || e.kind === "or" || e.kind === "cmp" || e.kind === "not";

/** An expression as text (for a `do` action: its call, for display only). */
export function exprText(e: Expr): string {
  switch (e.kind) {
    case "lit":
      return litText(e.value);
    case "var":
      return e.name;
    case "outcome":
      return CONST_OF[e.value];
    case "list":
      return `[${e.items.map(exprText).join(", ")}]`;
    case "sense":
      return `${e.sensor}(${Object.keys(e.args)
        .sort()
        .map((k) => `${k}=${exprText(e.args[k])}`)
        .join(", ")})`;
    case "cmp": {
      const side = (x: Expr) => (isBinary(x) ? `(${exprText(x)})` : exprText(x));
      return `${side(e.left)} ${e.op} ${side(e.right)}`;
    }
    case "and":
    case "or":
      return e.terms
        .map((t) => (t.kind === "and" || t.kind === "or" ? `(${exprText(t)})` : exprText(t)))
        .join(` ${e.kind} `);
    case "not":
      return `not ${e.term.kind === "and" || e.term.kind === "or" ? `(${exprText(e.term)})` : exprText(e.term)}`;
    case "arith": {
      const side = (x: Expr) => (isBinary(x) || x.kind === "arith" ? `(${exprText(x)})` : exprText(x));
      return `${side(e.left)} ${e.op} ${side(e.right)}`;
    }
    case "do":
      return `${e.action.block}(${Object.keys(e.action.params)
        .sort()
        .map((k) => `${k}=${exprText(e.action.params[k])}`)
        .join(", ")})`;
    case "callv":
      return `${e.proc}(${callArgsText(e.args, e.kwargs)})`;
  }
}

/** A call's arguments as Python writes them: positional first, then keywords in their order. */
export function callArgsText(args: Expr[], kwargs: Record<string, Expr>): string {
  return [...args.map(exprText), ...Object.entries(kwargs).map(([k, v]) => `${k}=${exprText(v)}`)].join(", ");
}

/** A call's arguments from their Python text ("F8, times=2"): positional and keyword ones. */
export function parseCallArgs(src: string): { args: Expr[]; kwargs: Record<string, Expr> } {
  if (!src.trim()) return { args: [], kwargs: {} };
  if (src.length > MAX_EXPR_CHARS) throw new ExprError(`longer than ${MAX_EXPR_CHARS} characters`);
  const e = parseExpr(`f_(${src})`);
  if (e.kind === "callv") return { args: e.args, kwargs: e.kwargs };
  if (e.kind === "sense") return { args: [], kwargs: e.args };
  throw new ExprError("write the inputs as in Python: value, ..., name=value, ...");
}

/** A function's inputs from their Python text ("key, times=1, *args, **kwargs"). Defaults are
 * plain values (a number, a text in quotes, True / False, a reference such as item(602)). */
export function parseParams(src: string): { params: { name: string; default: Lit | null }[]; varargs: string | null; kwargs: string | null } {
  const out: { name: string; default: Lit | null }[] = [];
  let varargs: string | null = null;
  let kwargs: string | null = null;
  const parts = splitTop(src);
  for (const raw of parts) {
    const t = raw.trim();
    if (!t) throw new ExprError("an empty input between two commas");
    const m = /^(\*\*|\*)?([A-Za-z][A-Za-z0-9_]{0,47})\s*(?:=\s*(.+))?$/.exec(t);
    if (!m) throw new ExprError(`${JSON.stringify(t)} is not an input (name, name=value, *name or **name)`);
    const [, star, name, dflt] = m;
    if ([...out.map((x) => x.name), varargs, kwargs].includes(name)) throw new ExprError(`the input ${name} is there twice`);
    if (kwargs) throw new ExprError("**" + kwargs + " comes last");
    if (star === "**") {
      if (dflt !== undefined) throw new ExprError(`**${name} takes no default`);
      kwargs = name;
    } else if (star === "*") {
      if (dflt !== undefined) throw new ExprError(`*${name} takes no default`);
      if (varargs) throw new ExprError("one *name only");
      varargs = name;
    } else {
      if (varargs) throw new ExprError(`${name} after *${varargs}: put the inputs before it`);
      let d: Lit | null = null;
      if (dflt !== undefined) {
        const e = parseExpr(dflt);
        if (e.kind !== "lit") throw new ExprError(`the default of ${name} must be a plain value`);
        d = e;
      } else if (out.some((x) => x.default !== null)) throw new ExprError(`${name} needs a default: it comes after one that has one`);
      out.push({ name, default: d });
    }
  }
  return { params: out, varargs, kwargs };
}

/** Split at the commas that are not inside brackets or quotes. */
function splitTop(src: string): string[] {
  if (!src.trim()) return [];
  const out: string[] = [];
  let depth = 0;
  let quote: string | null = null;
  let cur = "";
  for (const ch of src) {
    if (quote) {
      cur += ch;
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'") quote = ch;
    else if (ch === "(" || ch === "[") depth++;
    else if (ch === ")" || ch === "]") depth--;
    if (ch === "," && depth === 0) {
      out.push(cur);
      cur = "";
    } else cur += ch;
  }
  out.push(cur);
  return out;
}

export function hasDo(e: Expr): boolean {
  switch (e.kind) {
    case "do":
      return true;
    case "list":
      return e.items.some(hasDo);
    case "sense":
      return Object.values(e.args).some(hasDo);
    case "cmp":
    case "arith":
      return hasDo(e.left) || hasDo(e.right);
    case "and":
    case "or":
      return e.terms.some(hasDo);
    case "not":
      return hasDo(e.term);
    default:
      return false;
  }
}

// --- parsing --------------------------------------------------------------------------------------
type Tok = { t: "num" | "str" | "name" | "op" | "end"; v: string; at: number };

export class ExprError extends Error {}

function tokenize(src: string): Tok[] {
  if (src.length > MAX_EXPR_CHARS) throw new ExprError(`longer than ${MAX_EXPR_CHARS} characters`);
  const out: Tok[] = [];
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    if (c === " " || c === "\t" || c === "\n") {
      i++;
    } else if (/[0-9]/.test(c) || (c === "." && /[0-9]/.test(src[i + 1] ?? ""))) {
      const m = /^(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?/.exec(src.slice(i));
      out.push({ t: "num", v: m![0], at: i });
      i += m![0].length;
    } else if (c === '"') {
      let j = i + 1;
      while (j < src.length && src[j] !== '"') j += src[j] === "\\" ? 2 : 1;
      if (j >= src.length) throw new ExprError(`col ${i + 1}: unterminated text`);
      out.push({ t: "str", v: src.slice(i, j + 1), at: i });
      i = j + 1;
    } else if (/[A-Za-z_]/.test(c)) {
      const m = /^[A-Za-z_][A-Za-z0-9_]*/.exec(src.slice(i));
      out.push({ t: "name", v: m![0], at: i });
      i += m![0].length;
    } else {
      const two = src.slice(i, i + 2);
      if (["==", "!=", "<=", ">=", "//"].includes(two)) {
        out.push({ t: "op", v: two, at: i });
        i += 2;
      } else if ("<>+-*%()[],=".includes(c)) {
        out.push({ t: "op", v: c, at: i });
        i++;
      } else {
        throw new ExprError(`col ${i + 1}: unexpected ${JSON.stringify(c)}`);
      }
    }
  }
  out.push({ t: "end", v: "", at: src.length });
  return out;
}

class Parser {
  private i = 0;
  private depth = 0;
  private toks: Tok[];
  constructor(toks: Tok[]) {
    this.toks = toks;
  }

  private peek(): Tok {
    return this.toks[this.i];
  }
  private next(): Tok {
    return this.toks[this.i++];
  }
  private is(v: string): boolean {
    const t = this.peek();
    return (t.t === "op" || t.t === "name") && t.v === v;
  }
  private expect(v: string): void {
    const t = this.next();
    if (t.v !== v) throw new ExprError(`col ${t.at + 1}: expected ${JSON.stringify(v)}`);
  }
  private deeper<T>(f: () => T): T {
    if (++this.depth > MAX_DEPTH) throw new ExprError(`nested deeper than ${MAX_DEPTH}`);
    try {
      return f();
    } finally {
      this.depth--;
    }
  }

  parseAll(): Expr {
    const e = this.or();
    const t = this.peek();
    if (t.t !== "end") throw new ExprError(`col ${t.at + 1}: unexpected ${JSON.stringify(t.v)}`);
    return e;
  }

  private logic(kind: "and" | "or", sub: () => Expr): Expr {
    const terms = [sub()];
    while (this.is(kind)) {
      this.next();
      terms.push(sub());
    }
    return terms.length === 1 ? terms[0] : { kind, terms };
  }
  private or(): Expr {
    return this.deeper(() => this.logic("or", () => this.and()));
  }
  private and(): Expr {
    return this.logic("and", () => this.not());
  }
  private not(): Expr {
    if (this.is("not")) {
      this.next();
      return this.deeper(() => ({ kind: "not", term: this.not() }));
    }
    return this.cmp();
  }
  private cmp(): Expr {
    const left = this.arith();
    let op: CmpOp | null = null;
    const t = this.peek();
    if (["==", "!=", "<", "<=", ">", ">="].includes(t.v) && t.t === "op") op = t.v as CmpOp;
    else if (t.t === "name" && t.v === "in") op = "in";
    else if (t.t === "name" && t.v === "not" && this.toks[this.i + 1]?.v === "in") op = "not in";
    if (op === null) return left;
    this.next();
    if (op === "not in") this.next();
    const right = this.arith();
    const after = this.peek();
    if (after.t === "op" && ["==", "!=", "<", "<=", ">", ">="].includes(after.v)) {
      throw new ExprError(`col ${after.at + 1}: chained comparisons are not allowed`);
    }
    return { kind: "cmp", op, left, right };
  }
  private arith(): Expr {
    let left = this.term();
    while (this.peek().t === "op" && (this.peek().v === "+" || this.peek().v === "-")) {
      const op = this.next().v as ArithOp;
      left = { kind: "arith", op, left, right: this.term() };
    }
    return left;
  }
  private term(): Expr {
    let left = this.unary();
    while (this.peek().t === "op" && ["*", "//", "%"].includes(this.peek().v)) {
      const op = this.next().v as ArithOp;
      left = { kind: "arith", op, left, right: this.unary() };
    }
    return left;
  }
  private unary(): Expr {
    if (this.peek().t === "op" && this.peek().v === "-" && this.toks[this.i + 1]?.t === "num") {
      this.next();
      return { kind: "lit", value: -Number(this.next().v) };
    }
    return this.atom();
  }
  private atom(): Expr {
    const t = this.next();
    if (t.t === "num") {
      const n = Number(t.v);
      if (!Number.isFinite(n)) throw new ExprError(`col ${t.at + 1}: not a finite number`);
      return { kind: "lit", value: n };
    }
    if (t.t === "str") return { kind: "lit", value: parseString(t) };
    if (t.t === "op" && t.v === "(") {
      const e = this.deeper(() => this.or());
      this.expect(")");
      return e;
    }
    if (t.t === "op" && t.v === "[") return this.deeper(() => this.list());
    if (t.t !== "name") throw new ExprError(`col ${t.at + 1}: unexpected ${JSON.stringify(t.v || "end")}`);
    if (t.v === "True" || t.v === "False") return { kind: "lit", value: t.v === "True" };
    if (t.v in OUTCOME_CONST) return { kind: "outcome", value: OUTCOME_CONST[t.v] };
    if (["and", "or", "not", "in"].includes(t.v)) throw new ExprError(`col ${t.at + 1}: unexpected ${t.v}`);
    if (this.is("(")) return this.deeper(() => this.call(t));
    if (!NAME.test(t.v)) throw new ExprError(`col ${t.at + 1}: ${t.v} is not a valid name`);
    return { kind: "var", name: t.v };
  }
  private list(): Expr {
    const items: Expr[] = [];
    while (!this.is("]")) {
      items.push(this.or());
      if (!this.is("]")) this.expect(",");
    }
    this.expect("]");
    if (items.every((x) => x.kind === "lit")) {
      const refs = items.map((x) => (x as Lit).value);
      if (!refs.every((v) => typeof v === "object" && v !== null && !Array.isArray(v))) {
        throw new ExprError("a list holds references (item(..), mob(..), ...) or variables");
      }
      return { kind: "lit", value: refs as Ref[] };
    }
    return { kind: "list", items };
  }
  private call(name: Tok): Expr {
    this.expect("(");
    const pos: Expr[] = [];
    const kw: Record<string, Expr> = {};
    while (!this.is(")")) {
      const t = this.peek();
      if (t.t === "name" && this.toks[this.i + 1]?.v === "=" && this.toks[this.i + 1]?.t === "op") {
        this.next();
        this.next();
        if (t.v in kw) throw new ExprError(`col ${t.at + 1}: ${t.v} given twice`);
        kw[t.v] = this.or();
      } else {
        if (Object.keys(kw).length) throw new ExprError(`col ${t.at + 1}: positional after keyword`);
        pos.push(this.or());
      }
      if (!this.is(")")) this.expect(",");
    }
    this.expect(")");
    if (REF_CALLS.includes(name.v)) return { kind: "lit", value: refCall(name, pos, kw) };
    if (!NAME.test(name.v)) throw new ExprError(`col ${name.at + 1}: ${name.v} is not a valid name`);
    // positional inputs: a FUNCTION's call (the project model, 2026-11-13); sensors and actions
    // take theirs by name. A call with keywords only reads as a sensor here, and the block reader
    // turns it into a function's call when the node has a function of that name.
    if (pos.length) return { kind: "callv", proc: name.v, args: pos, kwargs: kw };
    return { kind: "sense", sensor: name.v, args: kw };
  }
}

function parseString(t: Tok): string {
  try {
    const s = JSON.parse(t.v) as unknown;
    if (typeof s === "string") return s;
  } catch {
    /* fall through */
  }
  throw new ExprError(`col ${t.at + 1}: bad text literal`);
}

function constant(e: Expr | undefined, type: "string" | "int", what: string): string | number {
  if (!e || e.kind !== "lit") throw new ExprError(`${what}: a constant is needed`);
  if (type === "string" && typeof e.value === "string") return e.value;
  if (type === "int" && typeof e.value === "number" && Number.isInteger(e.value)) return e.value;
  throw new ExprError(`${what}: ${type === "int" ? "a whole number" : "text"} is needed`);
}

function refCall(name: Tok, pos: Expr[], kw: Record<string, Expr>): Ref {
  const n = name.v;
  const arity: Record<string, number> = { cell: 3, skill: 1 };
  const want = arity[n] ?? 1;
  const extra = Object.keys(kw).filter((k) => !(n === "skill" && k === "level"));
  if (pos.length !== want || extra.length) throw new ExprError(`col ${name.at + 1}: ${n}(...) takes ${want} value(s)`);
  switch (n) {
    case "cell":
      return {
        kind: "cell",
        map: constant(pos[0], "string", "cell map") as string,
        x: constant(pos[1], "int", "cell x") as number,
        y: constant(pos[2], "int", "cell y") as number,
      };
    case "npc":
      return { kind: "npc", key: constant(pos[0], "string", "npc key") as string };
    case "option":
      return { kind: "option", key: constant(pos[0], "string", "option key") as string };
    case "item":
      return { kind: "item", id: constant(pos[0], "int", "item id") as number };
    case "mob":
      return { kind: "mob", id: constant(pos[0], "int", "mob id") as number };
    case "skill":
      return {
        kind: "skill",
        id: constant(pos[0], "int", "skill id") as number,
        level: kw.level ? (constant(kw.level, "int", "skill level") as number) : null,
      };
    case "map_id":
      return { kind: "map", map: constant(pos[0], "string", "map id") as string };
    default:
      return { kind: "window", name: constant(pos[0], "string", "window name") as string };
  }
}

/** Parse an expression written in the editor's text form; throws ExprError with a column. */
export function parseExpr(src: string): Expr {
  return new Parser(tokenize(src)).parseAll();
}

/** `name=value, ...` (an action's parameters, by name). */
export function argsText(params: Record<string, Expr>): string {
  return Object.keys(params)
    .sort()
    .map((k) => `${k}=${exprText(params[k])}`)
    .join(", ");
}

export function parseArgs(src: string): Record<string, Expr> {
  if (!src.trim()) return {};
  if (src.length > MAX_EXPR_CHARS) throw new ExprError(`longer than ${MAX_EXPR_CHARS} characters`);
  const e = parseExpr(`params(${src})`);
  if (e.kind !== "sense") throw new ExprError("write the parameters by name: name=value, ...");
  return e.args;
}
