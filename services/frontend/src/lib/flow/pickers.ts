// THE PICKERS (round 21; Batt 2026-11-14 ~19:4x ICT, docs/planning/live-blocks.md 12.5): "fields
// that choose a value, like use_model or 'this node when', should be DROPDOWNS with the values to
// choose from, so you know what there is. Typing should work like a search, guessing the word, and
// help with AUTO-COMPLETION ... where a value must be entered, a visual UI (matpilot's turn angle,
// more/less speed), for values that are not naming, such as functions or variables."
//
// The rule (ADR-0020 Amendment K): free text ONLY where a name is DEFINED (a function's, a
// variable's, an event's, a tab's); a REFERENCE to something that exists is a searchable list of
// what exists AT EDIT TIME; a NUMBER is a visual control; a CONDITION is a structured picker with a
// typed fallback that autocompletes. A picker EDITS THE SAME FIELD VALUE as before -- the same text,
// the same number -- so the workspace JSON, the IR and the Python view never change, and a value
// that is not in the list (an unknown function, a model not in models.yaml) is KEPT, shown marked;
// the lint names it, as before.
//
// Pure data and functions (no Blockly, no DOM; pickers.test.ts): what each picker offers, how a
// typed word ranks, how a number steps, how a condition's parts become its text. The Blockly fields
// that open them are components/flows/blockly-pickers.ts.
//
// `sliderKey` is ported, and `rankChoices` follows the word-prefix match of `matchEntries`, from
// MatPilot (https://github.com/lumduan/matpilot at commit 4022c870083c38c7ed4c62ff8361ef65a57d41f8,
// src/lib/blocks/fields/common.ts and src/lib/blocks/search.ts; THIRD_PARTY.md), MIT License,
// Copyright (c) 2026 Sarat Sonsuk:
//
//   Permission is hereby granted, free of charge, to any person obtaining a copy of this software
//   and associated documentation files (the "Software"), to deal in the Software without
//   restriction, including without limitation the rights to use, copy, modify, merge, publish,
//   distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the
//   Software is furnished to do so, subject to the following conditions: The above copyright
//   notice and this permission notice shall be included in all copies or substantial portions of
//   the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
//   IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
//   PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
//   LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
//   OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
//   DEALINGS IN THE SOFTWARE.
//
// Our own: the substring and fuzzy steps of the ranking, every option source, the conditions.
import type { CatalogueDoc } from "./api.ts";
import { HOTKEYS, RECIPE_TAB, RUNNER_ROLES } from "./blockdefs.ts";
import { argsText, callArgsText, ExprError, exprText, parseArgs, parseCallArgs, parseExpr, parseParams } from "./expr.ts";
import { type CmpOp, type Expr, type Lit, KEY, MAP_ID, NAME, type Stmt } from "./ir.ts";
import { type Models, monstersOf } from "./models.ts";
import { type Def, globalOf, mapNodes, nodeById, type PNode, type Project } from "./project.ts";
import { normalise } from "./search.ts";
import { SETTINGS, textUnits, tidy } from "./settings.ts";

// --- what a picker field is (blockdefs.ts puts one on each field it converts) ---------------------
/** What a reference picker lists. */
export type RefKind =
  | "function" // a function to call: the node's and Global's
  | "role" // a dungeon_hunt role's function (`role`: the role's param)
  | "escalate" // the function an insert event escalates to (empty: none)
  | "model" // a trained model (models.yaml via the catalogue)
  | "map" // a map name (GET /flows/maps; the project's maps)
  | "save_map" // a map for the save point: the maps with a Kafra first
  | "stop" // a stop reason (the project's, then the usual ones)
  | "node" // a map node of the project (an exit's arrival)
  | "entry" // an entry of the node the block's TO_BLOCK names
  | "window" // an L2 window (the catalogue's `windows`)
  | "server" // a login server (the catalogue's `servers`)
  | "variable"; // a variable of the tab, the node, Global, or the function's inputs

/** A picker on a field (JSON, in the block definition): what opens when the field is pressed.
 * `lo` / `hi` / `step` are the CONTROL's range (a slider's ends, the steppers' step); the field's
 * own min / max (when the definition gives them) are Blockly's, unchanged, so a loaded value is
 * never clamped by a picker. */
export type PickSpec =
  | { kind: "stepper"; lo: number; hi: number; step: number; unit?: string; one?: string; presets?: number[]; title: string }
  | { kind: "percent"; lo: number; hi: number; step: number; presets?: number[]; title: string; bar?: "hp" | "weight" | "level" }
  | { kind: "point"; axis: "x" | "y"; pair: string; title: string }
  | { kind: "cell"; axis: "x" | "y"; pair: string; title: string }
  | { kind: "optnum"; lo: number; hi: number; step: number; empty: string; none: string; title: string; unit?: string }
  | { kind: "ref"; ref: RefKind; role?: string; optional?: string; title: string }
  | { kind: "expr"; mode: "expr" | "args" | "callargs"; title: string }
  | { kind: "name"; title: string };

/** The game picture a point is in (the registry's game_px: 1280 x 720). */
export const GAME_PX: readonly [number, number] = [SETTINGS.game_px[0], SETTINGS.game_px[1]];

// --- the search: typing ranks the list ------------------------------------------------------------
/** One entry of a list: the value the field takes, what it shows, a hint beside it. */
export type Choice = { value: string; label: string; note?: string; group?: string };

const compact = (s: string) => normalise(s).replace(/ /g, "");

/** Is every character of `q` in `s`, in order (a fuzzy match: "flw" finds "fly_wing")? */
function subsequence(q: string, s: string): boolean {
  let i = 0;
  for (const c of s) if (c === q[i]) i++;
  return i === q.length;
}

/** How well `choice` matches the query (lower is better; null: no match): 0 the value or label
 * itself, 1 it starts with the query, 2 every query word starts a word of it (matpilot's block
 * search), 3 the query inside it, 4 its letters in order (fuzzy), 5 only its hint matches. */
export function matchScore(query: string, choice: Choice): number | null {
  const q = normalise(query);
  if (!q) return 5;
  const qc = q.replace(/ /g, "");
  const texts = [choice.value, choice.label];
  if (texts.some((t) => normalise(t) === q || compact(t) === qc)) return 0;
  if (texts.some((t) => compact(t).startsWith(qc))) return 1;
  const words = q.split(" ");
  if (texts.some((t) => words.every((w) => normalise(t).split(" ").some((x) => x.startsWith(w))))) return 2;
  if (texts.some((t) => compact(t).includes(qc))) return 3;
  if (qc.length >= 2 && texts.some((t) => subsequence(qc, compact(t)))) return 4;
  if (choice.note && normalise(choice.note).includes(q)) return 5;
  return null;
}

/** The choices that match `query`, best first; equally good ones keep the list's order. An empty
 * query keeps the whole list in its order. */
export function rankChoices(query: string, choices: readonly Choice[], max = 80): Choice[] {
  if (!normalise(query)) return choices.slice(0, max);
  const hits: { c: Choice; s: number; i: number }[] = [];
  choices.forEach((c, i) => {
    const s = matchScore(query, c);
    if (s !== null) hits.push({ c, s, i });
  });
  hits.sort((a, b) => a.s - b.s || a.i - b.i);
  return hits.slice(0, max).map((h) => h.c);
}

/** The list a picker shows for `query`: the ranked matches, then -- when the field may take a word
 * the list does not have (`typed`) -- the typed word itself as the last entry ("use it as typed"),
 * unless it is already there. A loaded value that is not in the list leads, marked (`current`). */
export function pickerList(query: string, choices: readonly Choice[], opts: { current?: string; typed?: (s: string) => string | null; empty?: string } = {}): Choice[] {
  const all: Choice[] = [...choices];
  if (opts.empty !== undefined && !all.some((c) => c.value === "")) all.unshift({ value: "", label: opts.empty, group: "none" });
  const cur = opts.current ?? "";
  if (cur && !all.some((c) => c.value === cur)) all.unshift({ value: cur, label: cur, note: "not in the list (kept as it is; the lint says why)", group: "unknown" });
  const out = rankChoices(query, all);
  const t = query.trim();
  if (t && opts.typed && !out.some((c) => c.value === t)) {
    const why = opts.typed(t);
    out.push(why === null ? { value: t, label: t, note: "use it as typed", group: "typed" } : { value: "", label: t, note: why, group: "refused" });
  }
  return out;
}

// --- numbers: the steppers, the sliders, the lever ------------------------------------------------
export type NumRange = { lo: number; hi: number; step: number };

/** A value on the control's grid (multiples of `step`) and inside its range. */
export function snap(v: number, r: NumRange): number {
  if (!Number.isFinite(v)) return r.lo;
  const onGrid = r.step > 0 ? tidy(Math.round(v / r.step) * r.step) : v;
  return tidy(Math.min(r.hi, Math.max(r.lo, onGrid)));
}

/** One step up (`dir` 1) or down (-1); `big` steps ten at a time. A value off the grid (loaded so)
 * moves to the grid line in that direction first. */
export function stepBy(v: number, dir: 1 | -1, r: NumRange, big = false): number {
  const n = big ? 10 : 1;
  if (!Number.isFinite(v)) return r.lo;
  const k = r.step > 0 ? v / r.step : v;
  const onGrid = Math.abs(k - Math.round(k)) < 1e-6;
  const base = r.step > 0 && !onGrid ? (dir > 0 ? Math.floor(k) : Math.ceil(k)) * r.step : v;
  return snap(base + dir * n * r.step, r);
}

/** The new value of a slider after a key, or null for a key it does not take (matpilot's
 * sliderKey, common.ts: arrows step, Page Up / Down take ten steps, Home / End go to the ends). */
export function sliderKey(key: string, v: number, r: NumRange): number | null {
  switch (key) {
    case "ArrowUp":
    case "ArrowRight":
      return stepBy(v, 1, r);
    case "ArrowDown":
    case "ArrowLeft":
      return stepBy(v, -1, r);
    case "PageUp":
      return stepBy(v, 1, r, true);
    case "PageDown":
      return stepBy(v, -1, r, true);
    case "Home":
      return r.lo;
    case "End":
      return r.hi;
    default:
      return null;
  }
}

/** A number as a person reads it, with its unit ("1.5 s", "40 %", "1 cell": `one` is the unit
 * said of one, round 20 #4c). */
export function numText(v: number, unit = "", one?: string): string {
  const t = Number.isFinite(v) ? String(tidy(v)) : "?";
  const u = v === 1 && one ? one : unit;
  return u ? `${t} ${u}` : t;
}

/** Where a value sits on the control, 0..1 (a slider's knob, the lever's fill). */
export function fraction(v: number, r: NumRange): number {
  if (!(r.hi > r.lo) || !Number.isFinite(v)) return 0;
  return Math.min(1, Math.max(0, (v - r.lo) / (r.hi - r.lo)));
}

/** The value at a place on the control, 0..1, on its grid. */
export function atFraction(f: number, r: NumRange): number {
  return snap(r.lo + Math.min(1, Math.max(0, f)) * (r.hi - r.lo), r);
}

/** A few round values inside the range for the preset buttons (the given ones that fit, else the
 * range's quarters on the grid), at most five, distinct. */
export function presetsOf(r: NumRange, given?: readonly number[]): number[] {
  const pick = given?.filter((v) => v >= r.lo && v <= r.hi) ?? [];
  const out = pick.length ? pick : [0, 0.25, 0.5, 0.75, 1].map((f) => atFraction(f, r));
  return [...new Set(out.map((v) => tidy(v)))].slice(0, 5);
}

/** An optional whole number in a TEXT field ("" = none / the default): the number, null for
 * empty, NaN for a text that is no whole number (kept as typed; the converter says why). */
export function optNumOf(text: string): number | null {
  const t = text.trim();
  if (t === "") return null;
  return /^[0-9]{1,6}$/.test(t) ? Number(t) : NaN;
}

/** Round 21 (the re-measure of round 20): on a PHONE an expression wider than this (workspace
 * units: the 300-unit row budget less an event's sides, the field's box and a reporter's rounded
 * ends, layout.ts) shows shortened in the middle, its head and tail kept ("hotbar_count(…) > 0");
 * its whole text is the field's tooltip, the picker's and the Python view's. On a wider screen it
 * shows whole. */
export const EXPR_SHOW_UNITS = 232;

/** An expression's text as a phone shows it closed: whole when it fits `max` units, else its head
 * up to the first "(" and as much of its tail as fits, joined by "…". */
export function shortExpr(text: string, max = EXPR_SHOW_UNITS): string {
  if (textUnits(text) <= max) return text;
  const open = text.indexOf("(");
  for (let head = open > 0 && open < 24 ? open + 1 : Math.min(12, text.length); head > 0; head--) {
    for (let tail = text.length - head - 1; tail >= 1; tail--) {
      const cand = `${text.slice(0, head)}…${text.slice(text.length - tail)}`;
      if (textUnits(cand) <= max) return cand;
    }
  }
  return "…";
}

/** What a picker field SHOWS on its block, closed (blockly-pickers.ts; settings.test.ts measures the
 * runner's block with it): a reference its value and ▾ (⚠ before it when it is not one of what
 * exists: `known` false), an empty optional one its word ("none"); an optional number its empty
 * word, or ⚠ after a text that is no whole number; any other picker its value as the plain field
 * showed it. `text`: the value as Blockly displays it (truncated, spaces kept). */
export function closedText(spec: PickSpec | undefined, text: string, value: string, known: boolean | null = null, compact = false): string {
  if (spec?.kind === "expr") return compact ? shortExpr(text) : text;
  if (spec?.kind === "optnum") return value === "" ? spec.empty : Number.isNaN(optNumOf(value)) ? `${text} ⚠` : text;
  if (spec?.kind !== "ref") return text;
  return `${value === "" ? (spec.optional ?? "…") : text}${known === false ? " ⚠" : ""} ▾`;
}

/** A point "X,Y" of the game picture as two numbers on the picture (clamped to it). */
export function pointIn(x: number, y: number): [number, number] {
  const c = (v: number, n: number) => Math.min(n - 1, Math.max(0, Math.round(Number.isFinite(v) ? v : 0)));
  return [c(x, GAME_PX[0]), c(y, GAME_PX[1])];
}

// --- what exists at edit time ---------------------------------------------------------------------
/** GET /flows/maps: the map names the backend's world knows (the local KB at run time, never
 * committed), each with whether a Kafra is there (a save point can be set there). */
export type MapsDoc = { server: string; source: string; maps: { id: string; kafra: boolean }[]; notes: string[] };

/** What a picker reads when it opens: the project as converted last, the tab shown, the catalogue,
 * the map list, and the functions written on the tab but not converted yet. */
export type PickerData = {
  project: Project | null;
  node: string | null;
  tab: string | null;
  catalogue: CatalogueDoc | null;
  maps: MapsDoc | null;
  extraDefs?: readonly string[];
};

/** Where the field is: its block's type, its own name, its siblings' values, the input its block
 * is plugged into (a value block's), and the inputs of the function around it. */
export type FieldAt = {
  blockType: string;
  field: string;
  sibling: (name: string) => string;
  parentInput?: string | null;
  params?: readonly string[];
};

type FnInfo = { name: string; tab: string; global: boolean; event: boolean; params: string; keys: string[]; calls: string[]; clicks: boolean };

/** The functions a body calls and whether it clicks (click_at), at its top level. */
function bodyWords(body: readonly Stmt[]): { calls: string[]; clicks: boolean } {
  const calls: string[] = [];
  let clicks = false;
  for (const s of body) {
    if (s.kind === "call" && !calls.includes(s.proc)) calls.push(s.proc);
    if (s.kind === "action" && s.block === "click_at") clicks = true;
  }
  return { calls, clicks };
}

/** The literal hotbar keys a function's body presses (press_key("F1")), in order. */
export function pressedKeys(body: readonly Stmt[]): string[] {
  const out: string[] = [];
  const walk = (ss: readonly Stmt[]) => {
    for (const s of ss) {
      if (s.kind === "action" && s.block === "press_key") {
        const k = s.params.key;
        if (k && k.kind === "lit" && typeof k.value === "string" && !out.includes(k.value)) out.push(k.value);
      } else if (s.kind === "if") {
        walk(s.then);
        walk(s.orelse);
      } else if (s.kind === "while" || s.kind === "repeat" || s.kind === "for") walk(s.body);
    }
  };
  walk(body);
  return out;
}

const paramNames = (d: Def): string => [...d.params.map((p) => p.name), ...(d.varargs ? [`*${d.varargs}`] : []), ...(d.kwargs ? [`**${d.kwargs}`] : [])].join(", ");

/** The functions (and events) the node can call: its own, then Global's it does not replace, then
 * the ones written on the tab and not converted yet. */
export function functionsOn(data: PickerData): FnInfo[] {
  const p = data.project;
  const node = p && data.node ? nodeById(p, data.node) : undefined;
  const out: FnInfo[] = [];
  const seen = new Set<string>();
  const add = (n: PNode | undefined, global: boolean) => {
    for (const t of n?.tabs ?? []) {
      for (const d of t.defs) {
        if (seen.has(d.name)) continue;
        seen.add(d.name);
        out.push({ name: d.name, tab: t.name, global, event: d.on !== null, params: paramNames(d), keys: pressedKeys(d.body), ...bodyWords(d.body) });
      }
    }
  };
  add(node, node?.kind === "global");
  const g = p ? globalOf(p) : undefined;
  if (g && g !== node) add(g, true);
  for (const n of data.extraDefs ?? []) {
    if (!seen.has(n) && NAME.test(n)) {
      seen.add(n);
      out.push({ name: n, tab: data.tab ?? "", global: false, event: false, params: "", keys: [], calls: [], clicks: false });
    }
  }
  return out;
}

/** The definition a name means on the node (its own first, then Global's). */
export function defOn(data: PickerData, name: string): Def | null {
  const p = data.project;
  if (!p) return null;
  for (const n of [data.node ? nodeById(p, data.node) : undefined, globalOf(p)]) {
    for (const t of n?.tabs ?? []) for (const d of t.defs) if (d.name === name) return d;
  }
  return null;
}

function fnNote(f: FnInfo): string {
  const what = f.event
    ? "an event"
    : f.keys.length
      ? `presses ${f.keys.join(", ")}`
      : f.params
        ? `(${f.params})`
        : f.calls.length
          ? `calls ${f.calls.join(", ")}`
          : f.clicks
            ? "clicks a point"
            : "a function";
  return `${what} · tab ${f.tab || "?"}${f.global ? " (Global)" : ""}`;
}
const fnChoice = (f: FnInfo): Choice => ({ value: f.name, label: f.name, note: fnNote(f), group: f.event ? "events" : "functions" });

/** Every stop reason a project's statements use, with how many times (the list's first part). */
export function stopReasons(p: Project | null): Map<string, number> {
  const out = new Map<string, number>();
  const walk = (ss: readonly Stmt[] | null) => {
    for (const s of ss ?? []) {
      if (s.kind === "stop") out.set(s.reason, (out.get(s.reason) ?? 0) + 1);
      else if (s.kind === "if") {
        walk(s.then);
        walk(s.orelse);
      } else if (s.kind === "while" || s.kind === "repeat" || s.kind === "for") walk(s.body);
    }
  };
  for (const n of p?.nodes ?? []) for (const t of n.tabs) {
    walk(t.main);
    for (const d of t.defs) walk(d.body);
  }
  return out;
}
/** The stop reasons a new project knows: the end of a run, and the way home (the bag full). */
export const USUAL_STOPS: readonly [string, string][] = [
  ["done", "the run is over"],
  ["home", "go home (the bag is full)"],
];

function modelChoices(models: Models | null | undefined): Choice[] {
  const out: Choice[] = [];
  for (const [id, m] of Object.entries(models ?? {})) {
    const where = m.maps.length ? m.maps.join(", ") : "any map";
    out.push({ value: id, label: id, note: `${m.kind === "boss_recognizer" ? "a boss recognizer" : "a detector"} · ${where} · ${m.available ? "live" : "not adopted"}`, group: m.available ? "live" : "not adopted" });
  }
  return out.sort((a, b) => Number(a.group !== "live") - Number(b.group !== "live"));
}

function mapChoices(data: PickerData, saving: boolean): Choice[] {
  const kafra = new Map<string, boolean>();
  for (const m of data.maps?.maps ?? []) kafra.set(m.id, m.kafra);
  const own = new Set(data.project ? mapNodes(data.project).map((n) => n.map.map) : []);
  for (const m of own) if (!kafra.has(m)) kafra.set(m, false);
  const out = [...kafra.entries()].map(([id, k]): Choice => ({
    value: id,
    label: id,
    note: [own.has(id) ? "a map of this project" : "", k ? "a Kafra is here (a save point)" : ""].filter(Boolean).join(" · ") || undefined,
    group: saving ? (k ? "save" : "other") : own.has(id) ? "project" : "other",
  }));
  const first = saving ? "save" : "project";
  return out.sort((a, b) => Number(a.group !== first) - Number(b.group !== first) || a.value.localeCompare(b.value));
}

function variablesOn(data: PickerData, at: FieldAt | null): Choice[] {
  const out: Choice[] = [];
  const seen = new Set<string>();
  for (const p of at?.params ?? []) if (!seen.has(p) && NAME.test(p)) {
    seen.add(p);
    out.push({ value: p, label: p, note: "an input of this function", group: "inputs" });
  }
  const p = data.project;
  for (const [n, global] of [[p && data.node ? nodeById(p, data.node) : undefined, false], [p ? globalOf(p) : undefined, true]] as const) {
    for (const t of n?.tabs ?? []) for (const [v, lit] of Object.entries(t.vars)) if (!seen.has(v)) {
      seen.add(v);
      out.push({ value: v, label: v, note: `= ${exprText(lit)} · tab ${t.name}${global ? " (Global)" : ""}`, group: "variables" });
    }
  }
  return out;
}

/** The list a reference picker shows (before any typing), in its order. */
export function refChoices(spec: Extract<PickSpec, { kind: "ref" }>, data: PickerData, at: FieldAt | null = null): Choice[] {
  const fns = functionsOn(data);
  switch (spec.ref) {
    case "function":
      return [...fns.filter((f) => !f.event), ...fns.filter((f) => f.event)].map(fnChoice);
    case "role": {
      const role = RUNNER_ROLES.find((r) => r.param === spec.role);
      const plain = fns.filter((f) => !f.event);
      const usual = plain.filter((f) => f.name === role?.fn);
      const keyed = plain.filter((f) => f.name !== role?.fn && f.keys.length);
      const rest = plain.filter((f) => f.name !== role?.fn && !f.keys.length);
      return [...usual, ...keyed, ...rest].map((f) => ({ ...fnChoice(f), note: `${f.name === role?.fn ? "the usual one · " : ""}${fnNote(f)}` }));
    }
    case "escalate":
      return fns.filter((f) => !f.event).map(fnChoice);
    case "model":
      return modelChoices(data.catalogue?.models);
    case "map":
      return mapChoices(data, false);
    case "save_map":
      return mapChoices(data, true);
    case "stop": {
      const used = stopReasons(data.project);
      const out: Choice[] = [...used.entries()].map(([r, n]) => ({ value: r, label: r, note: `used ${n} time${n === 1 ? "" : "s"} in this project`, group: "project" }));
      for (const [r, note] of USUAL_STOPS) if (!used.has(r)) out.push({ value: r, label: r, note, group: "usual" });
      return out;
    }
    case "node":
      return data.project ? mapNodes(data.project).map((n) => ({ value: n.id, label: n.id, note: `the map ${n.map.map}`, group: "nodes" })) : [];
    case "entry": {
      const to = at?.sibling("TO_BLOCK") ?? "";
      const n = data.project ? nodeById(data.project, to) : undefined;
      return n?.kind === "map" ? n.entries.map((e) => ({ value: e.name, label: e.name, note: e.at ? `at x ${e.at.x} y ${e.at.y}` : "where she arrives", group: "entries" })) : [];
    }
    case "window":
      return (data.catalogue?.windows ?? []).map((w) => ({ value: w, label: w.replaceAll("_", " "), group: "windows" }));
    case "server":
      return (data.catalogue?.servers ?? []).map((s) => ({ value: s.id, label: s.id, note: `${s.status}${s.lab ? " · the lab's" : ""}`, group: "servers" }));
    case "variable":
      return variablesOn(data, at);
  }
}

/** The pattern a typed word must fit to be kept as typed (the converter's rule for the field). */
const TYPED: Record<RefKind, { re: RegExp; why: string } | null> = {
  function: { re: NAME, why: "a function's name: letters, digits and _, a letter first" },
  role: { re: NAME, why: "a function's name: letters, digits and _, a letter first" },
  escalate: { re: NAME, why: "a function's name: letters, digits and _, a letter first" },
  model: null,
  map: { re: MAP_ID, why: "a map name: letters, digits, _ @ . -" },
  save_map: { re: MAP_ID, why: "a map name: letters, digits, _ @ . -" },
  stop: { re: /^[a-z_]{1,40}$/, why: "a stop reason: small letters and _" },
  node: { re: NAME, why: "a node's name" },
  entry: { re: NAME, why: "an entry's name" },
  window: { re: /^[a-z][a-z0-9_]{0,47}$/, why: "a window name: small letters, digits and _" },
  server: { re: KEY, why: "a server's id" },
  variable: { re: NAME, why: "a variable's name: letters, digits and _, a letter first" },
};

/** Why a typed word cannot be this field's value (null: it can be kept as typed). A model must be
 * one of the catalogue's -- typing filters the list -- but a loaded unknown one is still kept. */
export function typedProblem(ref: RefKind, word: string): string | null {
  const t = TYPED[ref];
  if (!t) return "choose one of the list";
  return t.re.test(word) ? null : t.why;
}

/** Whether the field's value is one of what exists: true, false (shown marked), or null when the
 * picker cannot tell yet (the map list not loaded, no catalogue). An empty optional field is fine. */
export function refKnown(spec: Extract<PickSpec, { kind: "ref" }>, value: string, data: PickerData, at: FieldAt | null = null): boolean | null {
  if (value === "") return spec.optional !== undefined;
  switch (spec.ref) {
    case "stop":
      return /^[a-z_]{1,40}$/.test(value);
    case "map":
    case "save_map":
      if (!data.maps) return data.project ? mapNodes(data.project).some((n) => n.map.map === value) || null : null;
      break;
    case "model":
    case "window":
    case "server":
      if (!data.catalogue) return null;
      if (spec.ref === "window" && !(data.catalogue.windows ?? []).length) return null;
      if (spec.ref === "server" && !(data.catalogue.servers ?? []).length) return null;
      break;
    case "function":
    case "role":
    case "escalate":
    case "variable":
    case "node":
    case "entry":
      if (!data.project) return null;
      break;
  }
  return refChoices(spec, data, at).some((c) => c.value === value);
}

/** The recipe tab's names (stage 4a): a function attack_<class> for each monster of the node's
 * model, the ones not written yet first. Suggestions only: a function's name stays free text. */
export function recipeNames(data: PickerData, model: string | null): Choice[] {
  if (data.tab !== RECIPE_TAB) return [];
  const m = monstersOf(data.catalogue?.models ?? null, model);
  if (!m) return [];
  const have = new Set(functionsOn(data).map((f) => f.name));
  const out = m.strikes.map((c): Choice => ({ value: `attack_${c}`, label: `attack_${c}`, note: `the recipe for ${c.replaceAll("_", " ")} (${m.model})${have.has(`attack_${c}`) ? " · written already" : ""}`, group: have.has(`attack_${c}`) ? "written" : "new" }));
  return out.sort((a, b) => Number(a.group !== "new") - Number(b.group !== "new"));
}

/** The model a node's main names (its use_model's), else null. */
export function nodeModel(data: PickerData): string | null {
  const n = data.project && data.node ? nodeById(data.project, data.node) : undefined;
  for (const t of n?.tabs ?? []) for (const s of t.main ?? []) {
    if (s.kind === "action" && s.block === "use_model") {
      const m = s.params.model;
      if (m?.kind === "lit" && typeof m.value === "string") return m.value;
    }
  }
  return null;
}

// --- conditions: sensor ▾ comparison ▾ value -------------------------------------------------------
/** A sensor (or one of the node's functions) as the condition picker offers it. */
export type SensorInfo = {
  name: string;
  type: string; // percent, int, bool, map, cell, mob, ... (blocks.yaml); "value" for a function
  range: [number, number] | null;
  params: { name: string; type: string; options?: string[]; required?: boolean }[];
  live: boolean;
  note: string;
  fn: boolean;
};
type CatSensor = { name?: string; spec?: { type?: string; range?: [number, number]; params?: { name: string; type: string; options?: string[]; required?: boolean }[]; live?: boolean; note?: string } };

/** The sensors a condition may read: the catalogue's (the trained models have blocks of their own,
 * the cell is no value to compare), then the node's functions (their value). */
export function sensorsOf(data: PickerData): SensorInfo[] {
  const out: SensorInfo[] = [];
  for (const [name, s] of Object.entries((data.catalogue?.sensors ?? {}) as Record<string, CatSensor>)) {
    const type = s.spec?.type ?? "value";
    if (name.startsWith("detector_") || type === "cell") continue;
    out.push({ name, type, range: s.spec?.range ?? null, params: s.spec?.params ?? [], live: s.spec?.live === true, note: s.spec?.note ?? "", fn: false });
  }
  out.sort((a, b) => Number(b.live) - Number(a.live));
  for (const f of functionsOn(data)) if (!f.event) out.push({ name: f.name, type: "value", range: null, params: [], live: false, note: `${fnNote(f)}: its return value`, fn: true });
  return out;
}

export const COMPARE_OPS: readonly CmpOp[] = ["<", "<=", ">", ">=", "==", "!="];
export const OP_WORDS: Record<string, string> = { "<": "under", "<=": "at most", ">": "over", ">=": "at least", "==": "is", "!=": "is not" };

/** A condition as its parts: what is read (a sensor call, a function's value or a variable), the
 * comparison, and the value. `op` "true": the left side alone (a yes / no sensor), "false": not it. */
export type Cond = { left: Expr; name: string; op: CmpOp | "true" | "false"; right: Expr | null };

const isPlainLit = (e: Expr) => e.kind === "lit" && (typeof e.value !== "object" || (!Array.isArray(e.value) && e.value !== null));
const leftName = (e: Expr): string | null => (e.kind === "sense" ? e.sensor : e.kind === "callv" ? e.proc : e.kind === "var" ? e.name : null);

/** The parts of a condition's text, or null when it is not one the picker can show (and/or, a
 * sum, an action): those stay text, edited by the typed fallback. */
export function condOf(text: string): Cond | null {
  let e: Expr;
  try {
    e = parseExpr(text);
  } catch {
    return null;
  }
  if (e.kind === "cmp" && (COMPARE_OPS as readonly string[]).includes(e.op)) {
    const name = leftName(e.left);
    if (name !== null && isPlainLit(e.right)) return { left: e.left, name, op: e.op, right: e.right };
    return null;
  }
  if (e.kind === "not") {
    const name = leftName(e.term);
    return name !== null && e.term.kind !== "var" ? { left: e.term, name, op: "false", right: null } : null;
  }
  const name = leftName(e);
  return name !== null && e.kind !== "var" ? { left: e, name, op: "true", right: null } : null;
}

/** A condition's text from its parts: the expression printed by the same printer as the block's
 * text (expr.ts exprText), so `hp_percent() < 50` stays exactly that. */
export function condText(c: Cond): string {
  if (c.op === "true") return exprText(c.left);
  if (c.op === "false") return exprText({ kind: "not", term: c.left });
  return exprText({ kind: "cmp", op: c.op, left: c.left, right: c.right ?? { kind: "lit", value: 0 } });
}

/** The left side for a sensor (its required inputs at their first choices) or a function. */
export function leftFor(s: SensorInfo): Expr {
  if (s.fn) return { kind: "callv", proc: s.name, args: [], kwargs: {} };
  const args: Record<string, Expr> = {};
  for (const p of s.params) if (p.required && p.options?.length) args[p.name] = { kind: "lit", value: p.options[0] };
  return { kind: "sense", sensor: s.name, args };
}

/** The value a newly chosen sensor is compared with, and the comparison (a percent: under 50). */
export function condFor(s: SensorInfo, prev: Cond | null, map = ""): Cond {
  const left = leftFor(s);
  if (s.type === "bool") return { left, name: s.name, op: "true", right: null };
  const op = prev && prev.op !== "true" && prev.op !== "false" ? prev.op : s.type === "percent" ? "<" : ">=";
  const keep = prev?.right && prev.right.kind === "lit" && typeof prev.right.value === "number" && s.type !== "map" ? prev.right : null;
  const right: Expr = keep ?? (s.type === "percent" ? { kind: "lit", value: 50 } : s.type === "map" ? { kind: "lit", value: { kind: "map", map: MAP_ID.test(map) ? map : "map" } } : { kind: "lit", value: s.range ? s.range[0] : 1 });
  return { left, name: s.name, op, right };
}

/** The range a value compared with this sensor takes (a percent 0..100). */
export function valueRange(s: SensorInfo | undefined): NumRange {
  if (s?.type === "percent") return { lo: 0, hi: 100, step: 1 };
  if (s?.range) return { lo: s.range[0], hi: Math.min(s.range[1], s.range[0] + 999), step: 1 };
  return { lo: 0, hi: 100, step: 1 };
}

/** A number literal's value (the stepper of a count, e.g. repeat 3 times), else null. */
export function numberOf(text: string): number | null {
  try {
    const e = parseExpr(text);
    return e.kind === "lit" && typeof e.value === "number" ? e.value : null;
  } catch {
    return null;
  }
}

// --- the typed fallback: autocomplete -------------------------------------------------------------
const CONSTANTS: readonly [string, string][] = [
  ["True", "yes"],
  ["False", "no"],
  ["OK", "an action's outcome: it worked"],
  ["FAILED", "an action's outcome: it did not"],
];
const KEYWORDS: readonly [string, string][] = [
  ["and", "both must hold"],
  ["or", "one of them is enough"],
  ["not", "the opposite"],
];
const REFS: readonly [string, string][] = [
  ["mob(", "a monster by its id"],
  ["item(", "an item by its id"],
  ["map_id(", "a map by its name"],
  ["cell(", "a cell: a map, x, y"],
];

/** What typing at `caret` may complete: the word being typed, replaced by a choice's value from
 * `from` to `to`; after a whole operand, the comparisons and and / or; after `key=`, the hotbar keys
 * in quotes. */
export function completions(text: string, caret: number, data: PickerData, at: FieldAt | null = null): { from: number; to: number; choices: Choice[] } {
  const before = text.slice(0, caret);
  const keyArg = /\bkey\s*=\s*"?([A-Za-z0-9]*)$/.exec(before);
  if (keyArg) {
    const from = caret - keyArg[1].length - (before.endsWith(`"${keyArg[1]}`) ? 1 : 0);
    return { from, to: caret, choices: rankChoices(keyArg[1], HOTKEYS.map((k) => ({ value: `"${k}"`, label: k, note: "a hotbar key (row 1)" }))) };
  }
  const word = /([A-Za-z_][A-Za-z0-9_]*)$/.exec(before);
  if (word) {
    const prefix = word[1];
    const all: Choice[] = [];
    for (const s of sensorsOf(data)) {
      const p = s.params.find((x) => x.required);
      const call = s.fn ? `${s.name}()` : p ? `${s.name}(${p.name}=${p.options?.length ? JSON.stringify(p.options[0]) : ""})` : `${s.name}()`;
      all.push({ value: call, label: s.name, note: s.fn ? s.note : `a sensor (${s.type})${s.live ? " · plays live" : ""}`, group: s.fn ? "functions" : "sensors" });
    }
    for (const v of variablesOn(data, at)) all.push(v);
    for (const [c, note] of [...CONSTANTS, ...KEYWORDS]) all.push({ value: c, label: c, note, group: "words" });
    for (const [c, note] of REFS) all.push({ value: c, label: c, note, group: "values" });
    const choices = rankChoices(prefix, all, 12).filter((c) => c.value !== prefix);
    return { from: caret - prefix.length, to: caret, choices };
  }
  if (/[)\]0-9A-Za-z"]\s+$/.test(before) && !/\b(and|or|not)\s+$/.test(before)) {
    const ops = [...COMPARE_OPS.map((o): [string, string] => [o, OP_WORDS[o]]), ["and", "both must hold"], ["or", "one is enough"]] as [string, string][];
    return { from: caret, to: caret, choices: ops.map(([o, note]) => ({ value: `${o} `, label: o, note, group: "operators" })) };
  }
  return { from: caret, to: caret, choices: [] };
}

/** The text with a completion put in. */
export function complete(text: string, c: { from: number; to: number }, value: string): { text: string; caret: number } {
  const out = text.slice(0, c.from) + value + text.slice(c.to);
  return { text: out, caret: c.from + value.length };
}

// --- a block's inputs as rows: the catalogue's parameters; a function's inputs --------------------
type CatParam = { name: string; type: string; required: boolean; options?: string[]; choices?: string[]; note?: string | null };

/** One input of a call as the picker shows it: its name, how it is chosen, its value's text. */
export type ArgRow = { name: string; kind: "model" | "key" | "options" | "int" | "text"; text: string; required: boolean; options: string[]; note: string; positional: boolean };

const KEY_LIKE = (name: string, opts: readonly string[] | undefined) => name === "key" || (!!opts?.length && opts.every((o) => (HOTKEYS as readonly string[]).includes(o)));
function rowKind(block: string, p: CatParam): ArgRow["kind"] {
  if (block === "use_model" && p.name === "model") return "model";
  if (KEY_LIKE(p.name, p.options)) return "key";
  if (p.options?.length) return "options";
  if (p.type === "int") return "int";
  return "text";
}

/** A catalogue block's parameters as rows, with the values its text names (by name), or null when
 * the text does not read (the typed fallback shows why). Parameters the catalogue does not list are
 * rows too (kept; the lint names them). */
export function argRows(block: string, text: string, cat: CatalogueDoc | null): ArgRow[] | null {
  let got: Record<string, Expr>;
  try {
    got = parseArgs(text);
  } catch {
    return null;
  }
  const params = (cat?.blocks[block]?.spec.params ?? []) as CatParam[];
  const rows: ArgRow[] = params.map((p) => ({ name: p.name, kind: rowKind(block, p), text: got[p.name] ? exprText(got[p.name]) : "", required: p.required, options: p.options ?? [], note: p.note ?? p.type, positional: false }));
  for (const k of Object.keys(got)) if (!params.some((p) => p.name === k)) rows.push({ name: k, kind: "text", text: exprText(got[k]), required: false, options: [], note: "not a parameter of this block (the lint says so)", positional: false });
  return rows;
}

/** The text with one parameter set to `valueText` (an expression's text) or left out (null);
 * printed as the block's text always is (expr.ts argsText: by name, sorted). Throws ExprError when
 * the text or the value does not read. */
export function argsWith(text: string, name: string, valueText: string | null): string {
  const got = parseArgs(text);
  if (valueText === null || valueText.trim() === "") delete got[name];
  else got[name] = parseExpr(valueText);
  return argsText(got);
}

/** A function call's inputs as rows: the function's inputs in order (a value given by position or
 * by name), then any other named one. Null: the text does not read. */
export function callRows(def: Def | null, text: string): ArgRow[] | null {
  let got: { args: Expr[]; kwargs: Record<string, Expr> };
  try {
    got = parseCallArgs(text);
  } catch {
    return null;
  }
  const rows: ArgRow[] = [];
  const ps = def?.params ?? [];
  ps.forEach((p, i) => {
    const pos = got.args[i];
    const kw = got.kwargs[p.name];
    const v = pos ?? kw;
    const keyish = p.name === "key" || (p.default?.kind === "lit" && typeof p.default.value === "string" && (HOTKEYS as readonly string[]).includes(p.default.value));
    rows.push({ name: p.name, kind: keyish ? "key" : "text", text: v ? exprText(v) : "", required: p.default === null, options: [], note: p.default ? `default ${exprText(p.default)}` : "needed", positional: pos !== undefined });
  });
  got.args.slice(ps.length).forEach((a, i) => rows.push({ name: `${def?.varargs ? `*${def.varargs}` : "more"} ${i + 1}`, kind: "text", text: exprText(a), required: false, options: [], note: def?.varargs ? "one of its *inputs" : "more inputs than the function takes (the lint says so)", positional: true }));
  for (const [k, v] of Object.entries(got.kwargs)) if (!ps.some((p) => p.name === k)) rows.push({ name: k, kind: "text", text: exprText(v), required: false, options: [], note: def?.kwargs ? `one of its **${def.kwargs}` : "not an input of this function (the lint says so)", positional: false });
  return rows;
}

/** The call's text with the function's input `name` set (null: left out). An input given by
 * position stays by position; a new one goes by position when every input before it is given so,
 * else by name. Printed as expr.ts callArgsText prints. Throws ExprError on a text that does not
 * read. */
export function callArgsWith(def: Def | null, text: string, name: string, valueText: string | null): string {
  const got = parseCallArgs(text);
  const ps = def?.params ?? [];
  const i = ps.findIndex((p) => p.name === name);
  const v = valueText === null || valueText.trim() === "" ? null : parseExpr(valueText);
  if (i >= 0 && i < got.args.length) {
    if (v) got.args[i] = v;
    else if (i === got.args.length - 1) got.args.pop();
    else throw new ExprError(`${name} is given by position before other inputs: leave it, or change the text`);
  } else if (v) {
    if (i >= 0 && i === got.args.length && !(name in got.kwargs)) got.args.push(v);
    else got.kwargs[name] = v;
  } else delete got.kwargs[name];
  return callArgsText(got.args, got.kwargs);
}

/** The inputs a function's PARAMS text defines (the variables inside it). */
export function paramsOf(text: string): string[] {
  try {
    const p = parseParams(text);
    return [...p.params.map((x) => x.name), ...(p.varargs ? [p.varargs] : []), ...(p.kwargs ? [p.kwargs] : [])];
  } catch {
    return [];
  }
}

/** A literal's text for a picker row (a string in quotes, a number as is). */
export const litOf = (v: string | number | boolean): string => exprText({ kind: "lit", value: v } as Lit);
