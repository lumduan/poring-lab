// Colours for the read-only Python view, in the style most programmers know from VS Code (Dark+ /
// Light+), with MatPilot's token kinds and CSS variables (--py-*), so the code reads the same on
// /flows as on matpilot.org/blocks (Batt 2026-11-09). MatPilot colours with @lezer/python; no new
// dependency is added here (the image and the supply chain are Batt's call), so this is our own
// small, linear tokenizer for the Python the flow engine prints (a known subset of Python 3.12),
// tested in pycolor.test.ts. It never evaluates anything and builds no HTML: CodeView renders the
// pieces as React text spans.
//
// The rules (MatPilot's):
// - control words (if, elif, else, for, while, return, import, from, break, continue, pass, raise,
//   try, except, finally, with, as, ...) -> control;
// - def, class, lambda, True, False, None, and, or, not, in, is, global, ... -> keyword;
// - a name right before "(" -> function; the name after "def" is a function, after "class" a class;
// - ALL_CAPS names -> constant; CapWords names -> class; other names -> variable;
// - text in quotes (single, double, triple; prefixes) -> string, its escapes -> escape;
// - numbers -> number; "# ..." -> comment; brackets cycle bracket1 / 2 / 3 by nesting depth;
// - everything else (operators, commas, spaces) stays plain text.

export type TokenKind =
  | "control"
  | "keyword"
  | "string"
  | "escape"
  | "number"
  | "comment"
  | "function"
  | "class"
  | "constant"
  | "variable"
  | "bracket1"
  | "bracket2"
  | "bracket3";

export type Piece = { text: string; kind: TokenKind | null };

/** Keywords that change the flow, and imports: purple in VS Code. */
export const CONTROL = new Set([
  "if", "elif", "else", "for", "while", "try", "except", "finally", "return", "raise", "break",
  "continue", "pass", "with", "as", "import", "from", "yield", "await", "assert", "match", "case", "del",
]);

/** The other keywords and the constants True, False, None: blue in VS Code. */
export const KEYWORD = new Set([
  "def", "class", "lambda", "global", "nonlocal", "and", "or", "not", "in", "is", "async", "True", "False", "None",
]);

const BRACKETS: TokenKind[] = ["bracket1", "bracket2", "bracket3"];
const OPEN = "([{";
const CLOSE = ")]}";
const NAME_START = /[\p{L}_]/u;
const NAME_CHAR = /[\p{L}\p{N}_]/u;
const STRING_PREFIX = /^(?:[rRbBuUfF]|[rR][bBfF]|[bBfF][rR])$/;

const isConstant = (name: string) => /^[A-Z][A-Z0-9_]+$/.test(name);
const isClass = (name: string) => /^[A-Z]/.test(name) && /[a-z]/.test(name);

/** The text cut into plain and coloured pieces, in order; joined, they are the text again. */
export function colouredPieces(text: string): Piece[] {
  const out: Piece[] = [];
  const push = (t: string, kind: TokenKind | null) => {
    if (!t) return;
    const last = out[out.length - 1];
    if (kind === null && last && last.kind === null) last.text += t;
    else out.push({ text: t, kind });
  };
  let depth = 0;
  let after: "def" | "class" | null = null; // the name after `def` / `class`
  let i = 0;
  const n = text.length;
  while (i < n) {
    const c = text[i];
    // a comment: to the end of the line
    if (c === "#") {
      let j = text.indexOf("\n", i);
      if (j < 0) j = n;
      push(text.slice(i, j), "comment");
      i = j;
      continue;
    }
    // a string, with an optional prefix (r, b, f, rb, ...)
    if (c === '"' || c === "'") {
      i = readString(text, i, "", push);
      after = null;
      continue;
    }
    if (NAME_START.test(c)) {
      let j = i + 1;
      while (j < n && NAME_CHAR.test(text[j])) j++;
      const name = text.slice(i, j);
      if ((text[j] === '"' || text[j] === "'") && STRING_PREFIX.test(name)) {
        i = readString(text, j, name, push);
        after = null;
        continue;
      }
      push(name, nameKind(text, j, name, after));
      after = name === "def" ? "def" : name === "class" ? "class" : null;
      i = j;
      continue;
    }
    // a number: 12, 1.5, .5, 1e-3, 0x1F, 1_000, 3j
    if (/[0-9]/.test(c) || (c === "." && /[0-9]/.test(text[i + 1] ?? ""))) {
      const m = /^(?:0[xX][0-9a-fA-F_]+|0[oO][0-7_]+|0[bB][01_]+|(?:[0-9][0-9_]*)?\.?[0-9_]*(?:[eE][+-]?[0-9_]+)?[jJ]?)/.exec(text.slice(i));
      const len = Math.max(1, m ? m[0].length : 1);
      push(text.slice(i, i + len), "number");
      i += len;
      after = null;
      continue;
    }
    if (OPEN.includes(c)) {
      push(c, BRACKETS[depth % BRACKETS.length]);
      depth++;
      after = null;
      i++;
      continue;
    }
    if (CLOSE.includes(c)) {
      depth = Math.max(0, depth - 1);
      push(c, BRACKETS[depth % BRACKETS.length]);
      after = null;
      i++;
      continue;
    }
    if (c !== " " && c !== "\t") after = null;
    push(c, null);
    i++;
  }
  return out;
}

/** What colour a name gets, from where it stands: `end` is the index just after it. */
function nameKind(text: string, end: number, name: string, after: "def" | "class" | null): TokenKind {
  if (CONTROL.has(name)) return "control";
  if (KEYWORD.has(name)) return "keyword";
  if (after === "def") return "function";
  if (after === "class") return "class";
  let j = end;
  while (text[j] === " " || text[j] === "\t") j++;
  if (text[j] === "(") return isClass(name) ? "class" : "function";
  if (isConstant(name)) return "constant";
  if (isClass(name)) return "class";
  return "variable";
}

/** A string starting at `at` (its quote), `prefix` already read: pushes it, returns its end. */
function readString(text: string, at: number, prefix: string, push: (t: string, k: TokenKind | null) => void): number {
  const q = text[at];
  const triple = text.startsWith(q.repeat(3), at);
  const close = triple ? q.repeat(3) : q;
  const raw = /[rR]/.test(prefix);
  let i = at + close.length;
  let run = prefix + close; // the string text not yet pushed
  while (i < text.length) {
    if (text.startsWith(close, i)) {
      run += close;
      i += close.length;
      push(run, "string");
      return i;
    }
    const c = text[i];
    if (c === "\n" && !triple) break; // an unterminated one-line string ends at the line
    if (c === "\\" && i + 1 < text.length) {
      const len = escapeLength(text, i);
      if (raw) {
        run += text.slice(i, i + 2);
        i += 2;
        continue;
      }
      push(run, "string");
      run = "";
      push(text.slice(i, i + len), "escape");
      i += len;
      continue;
    }
    run += c;
    i++;
  }
  push(run, "string");
  return i;
}

/** How long the escape at `i` (a backslash) is: \n, \", \x41, ก, \U0001f600, \N{...}, \012. */
function escapeLength(text: string, i: number): number {
  const c = text[i + 1];
  if (c === "x") return 4;
  if (c === "u") return 6;
  if (c === "U") return 10;
  if (c === "N" && text[i + 2] === "{") {
    const end = text.indexOf("}", i + 3);
    return end < 0 ? 2 : end - i + 1;
  }
  if (/[0-7]/.test(c)) {
    let j = i + 1;
    while (j < i + 4 && /[0-7]/.test(text[j] ?? "")) j++;
    return j - i;
  }
  return 2;
}
