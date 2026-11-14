// THE SETTING BLOCKS (docs/planning/live-blocks.md section 12; Batt 2026-11-14 ~15:2x: "there should
// be no runner [page] ... everything in the xmas_dun02 flow, split into tabs ... make them ALL
// blocks, no hardcoding like this"). Every number and switch of the runner's hunt core is a
// PROJECT VARIABLE named like the setting (settings.gen.ts: the engine's registry,
// packages/poring_flow/src/poring_flow/settings.py, drift-tested), shown as a block of its own in the
// tab of its group (survival, knife, exits, respawn, start, fight, aim, loot, walk, safety, timing). A
// run on a map node takes, per setting: that node's block > Global's > the default (the project
// model's name rule); a deleted block falls back to the level below. The hotbar keys are no setting
// blocks: they come from the functions dungeon_hunt names (runnerKeysOn), as before.
//
// Pure data and functions (the block editor, the studio's Before Run pane and the tests use them);
// every value renders as text.
import type { Lit } from "./ir.ts";
import type { Project, Tab } from "./project.ts";
import { SETTINGS_REGISTRY } from "./settings.gen.ts";

export type SettingKind = "key" | "share" | "number" | "int" | "point" | "point_or_none" | "switch" | "choice";
export type SettingValue = string | number | boolean;
export type SettingField = {
  name: string; // the runner's name ("knife_hp_min", "vt.D0_PX")
  var: string; // its project variable ("knife_hp_min", "D0_PX")
  group: string; // its tab
  block: boolean; // a setting block (every field but the hotbar keys)
  kind: SettingKind;
  words: string;
  lo: number;
  hi: number;
  step: number;
  unit: string;
  flag: string;
  off: string;
  options: string[];
  warn: string; // what happens while it is off (a safety switch): its own row, a lint warning
  needs: [string, SettingValue][];
  default: SettingValue;
  find: string[]; // the words the block search finds it by (its group's and its own)
};
export type SettingGroup = { id: string; title: string; note: string };
export type SettingsRegistry = { version: number; groups: SettingGroup[]; fields: SettingField[]; keys: string[]; game_px: number[]; tabs: string[]; singular: Record<string, string>; runner_maps: string[] };

export const SETTINGS: SettingsRegistry = SETTINGS_REGISTRY;
export const SETTING_BY_NAME: ReadonlyMap<string, SettingField> = new Map(SETTINGS.fields.map((f) => [f.name, f]));
export const SETTING_BY_VAR: ReadonlyMap<string, SettingField> = new Map(SETTINGS.fields.map((f) => [f.var, f]));
/** The setting blocks, in the page's order. */
export const SETTING_BLOCKS: readonly SettingField[] = SETTINGS.fields.filter((f) => f.block);
/** The tabs the setting blocks live in, in the page's order (one per group but the keys). */
export const SETTING_TABS: readonly string[] = SETTINGS.tabs;
/** The maps whose runner "hunt with the runner" plays (poring_flow.functions.RUNNER_MAPS). */
export const RUNNER_MAPS: readonly string[] = SETTINGS.runner_maps;
export const groupOf = (id: string): SettingGroup | undefined => SETTINGS.groups.find((g) => g.id === id);

const onGrid = (v: number, step: number) => step <= 0 || Math.abs(v / step - Math.round(v / step)) < 1e-6;
/** A number without float noise (0.07 * 100 = 7.000000000000001). */
export const tidy = (v: number): number => Math.round(v * 1e6) / 1e6;

/** The text of a value as a person reads it (a share as a percent, a switch on / off). */
export function shownValue(f: SettingField, v: SettingValue): string {
  if (typeof v === "boolean") return v ? "on" : "off";
  if (typeof v !== "number") return String(v);
  if (f.kind === "share") return `${tidy(v * 100)}`;
  return String(tidy(v));
}

/** The unit after a value ("%" for a share); singular for a value of 1 ("1 cell": matpilot round 20
 * #4c; poring_flow.settings unit_of). */
export function unitOf(f: SettingField, v?: SettingValue): string {
  const u = f.kind === "share" ? "%" : f.unit;
  return typeof v === "number" && v === 1 ? (SETTINGS.singular[u] ?? u) : u;
}
const withUnit = (f: SettingField, v: SettingValue) => `${shownValue(f, v)}${unitOf(f, v) ? ` ${unitOf(f, v)}` : ""}`;
/** A value as the block and the /maps inspector show it: "40 %", "1.5 s", "2 cells", "on". */
export const settingValueText = (f: SettingField, v: SettingValue): string => withUnit(f, v);

/** PURE: why ``v`` cannot be the setting's value (null: it can) -- poring_flow.settings.problem_of. */
export function settingProblem(f: SettingField, v: unknown): string | null {
  if (f.kind === "switch") return typeof v === "boolean" ? null : `${f.words}: not on or off`;
  if (f.kind === "choice") return f.options.includes(String(v)) && typeof v === "string" ? null : `${f.words}: ${String(v)} is not one of ${f.options.join(", ")}`;
  if (f.kind === "key") return SETTINGS.keys.includes(String(v)) ? null : `the ${f.words}'s key ${String(v)} is not a row-1 hotbar key (F1-F9)`;
  if (f.kind === "point" || f.kind === "point_or_none") {
    if (f.kind === "point_or_none" && v === "none") return null;
    const m = /^(\d{1,4}),(\d{1,4})$/.exec(typeof v === "string" ? v : "");
    return m && Number(m[1]) < SETTINGS.game_px[0] && Number(m[2]) < SETTINGS.game_px[1] ? null : `${f.words}: ${String(v)} is not a point X,Y in the ${SETTINGS.game_px[0]} x ${SETTINGS.game_px[1]} picture`;
  }
  if (typeof v !== "number" || !Number.isFinite(v)) return `${f.words}: not a number`;
  if (f.kind === "int" && !Number.isInteger(v)) return `${f.words}: ${v} is not a whole number`;
  if (v < f.lo - 1e-9 || v > f.hi + 1e-9) return `${f.words}: ${withUnit(f, v)} is not from ${withUnit(f, f.lo)} to ${withUnit(f, f.hi)}`;
  if (!onGrid(v, f.step)) return `${f.words}: ${withUnit(f, v)} is not a step of ${withUnit(f, f.step)}`;
  return null;
}

/** PURE: a setting is IN USE when each of its needs holds and each needed setting is in use
 * (poring_flow.settings.in_use): one not in use is not passed to the runner. */
export function settingInUse(values: Record<string, SettingValue>, name: string, seen: ReadonlySet<string> = new Set()): boolean {
  const f = SETTING_BY_NAME.get(name);
  if (!f || seen.has(name)) return false;
  for (const [other, want] of f.needs) {
    if (!settingInUse(values, other, new Set([...seen, name]))) return false;
    const v = values[other];
    if (want === "!off" ? v === undefined || v === "off" || v === false : v !== want) return false;
  }
  return true;
}

/** The literal a setting's project variable holds. */
export const settingLit = (v: SettingValue): Lit => ({ kind: "lit", value: v });

/** PURE: the tabs with every setting block put in the tab of its group (an existing tab of that
 * name, else a new one after the others, in the page's order), each at ``values[name]`` or its
 * default; ``only`` keeps the settings it says yes to (a map node: only those it sets differently). */
export function withSettingTabs(tabs: Tab[], values: Record<string, SettingValue> = {}, only: (f: SettingField) => boolean = () => true): Tab[] {
  const out = tabs.map((t) => ({ ...t, vars: { ...t.vars } }));
  for (const f of SETTING_BLOCKS) {
    if (!only(f)) continue;
    let t = out.find((x) => x.name === f.group);
    if (!t) {
      t = { name: f.group, main: null, defs: [], vars: {} };
      out.push(t);
    }
    t.vars[f.var] = settingLit(values[f.name] ?? f.default);
  }
  return out;
}

/** Where a node's settings are read from: its own tabs, then Global's (the name rule). */
function levels(p: Project, nodeId: string): { where: string; vars: Record<string, Lit> }[] {
  const nodes = [...p.nodes.filter((n) => n.id === nodeId), ...p.nodes.filter((n) => n.kind === "global" && n.id !== nodeId)];
  return nodes.flatMap((n) => n.tabs.map((t) => ({ where: `${n.id}/${t.name}`, vars: t.vars })));
}

/** PURE: the settings a hunt core on ``nodeId`` takes and where each came from ("default", or
 * "<node>/<tab>"): the node's block > Global's > the default (poring_flow.settings.node_values). A
 * value a setting cannot take is no value: the default stands in (the lint says it; Run refuses). */
export function nodeSettings(p: Project, nodeId: string): { values: Record<string, SettingValue>; src: Record<string, string> } {
  const values: Record<string, SettingValue> = {};
  const src: Record<string, string> = {};
  for (const f of SETTINGS.fields) {
    values[f.name] = f.default;
    src[f.name] = "default";
  }
  const lv = levels(p, nodeId);
  for (const f of SETTING_BLOCKS) {
    const at = lv.find((l) => f.var in l.vars);
    const v = at?.vars[f.var]?.value;
    if (at && settingProblem(f, v) === null) {
      values[f.name] = v as SettingValue;
      src[f.name] = at.where;
    }
  }
  return { values, src };
}

/** PURE: what a setting block on ``nodeId`` falls back to when a person deletes it: Global's block
 * (a map node), else the default -- the words its tooltip says. */
export function settingFallback(p: Project, nodeId: string, f: SettingField): string {
  const node = p.nodes.find((n) => n.id === nodeId);
  if (node && node.kind !== "global") {
    for (const g of p.nodes.filter((n) => n.kind === "global")) {
      for (const t of g.tabs) {
        const v = t.vars[f.var]?.value;
        if (v !== undefined && settingProblem(f, v) === null) return `Global's ${withUnit(f, v as SettingValue)} (tab ${t.name})`;
      }
    }
  }
  return `the default, ${withUnit(f, f.default)}`;
}

/** What the tooltip knows of the block's place (BlockEditor fills it): what deleting it falls back
 * to, whether the project has a Global node (round 20 #4d: say Global only when there is one), and
 * the lint's words for THIS block (poring_flow lint/settings.py notes: not used here, a safety
 * switch off). */
export type SettingPlace = { fallback?: string; global?: boolean; note?: SettingNote | null };
/** The lint's rows for one setting block (POST /flows/lint ``settings[path]``). */
export type SettingNote = { unused?: string; safety?: string };

/** A setting block's tooltip: its variable, tab, words, range, default and what deleting it does. */
export function settingTooltip(f: SettingField, place: SettingPlace | string = {}): string {
  const at: SettingPlace = typeof place === "string" ? { fallback: place } : place;
  const range =
    f.kind === "switch"
      ? "on or off"
      : f.kind === "choice"
        ? `one of ${f.options.join(", ")}`
        : f.kind === "point" || f.kind === "point_or_none"
          ? `a point X, Y in the ${SETTINGS.game_px[0]} x ${SETTINGS.game_px[1]} game picture${f.kind === "point_or_none" ? ', or "none"' : ""}`
          : `${withUnit(f, f.lo)} to ${withUnit(f, f.hi)}, in steps of ${withUnit(f, f.step)}`;
  // round 21 (the re-measure of round 20): a switch without a flag of its own says WHICH settings
  // it turns on (weight_exit: weight_home), not "a switch for the settings it needs"
  const deps = SETTING_BLOCKS.filter((d) => d.needs.some(([n]) => n === f.name)).map((d) => `${d.var} (${d.words})`);
  const runner = f.flag === "--tune" ? `the runner's ${f.name} (--tune)` : f.flag ? `the runner's ${f.flag}` : deps.length ? `a switch with no flag of its own: ${deps.join(", ")} ${deps.length === 1 ? "is" : "are"} used only while it is on` : "a switch with no flag of its own";
  const global = at.global ? " A map's block replaces Global's there." : "";
  const fallback = at.fallback ?? (at.global ? "Global's value (a map node), else the default" : `the default, ${withUnit(f, f.default)}`);
  const note = at.note?.unused ? `\nIn a Run of this project: ${at.note.unused}.` : "";
  return `${f.var} = ... (tab ${f.group}): ${f.words}. ${range}; our default ${withUnit(f, f.default)}; ${runner}.${global} Delete this block: ${fallback} applies.${note}${f.warn ? `\nWhile it is off: ${f.warn}.` : ""}`;
}

// --- the block's LAYOUT (matpilot round 20 #2) ------------------------------------------------------
// At 390 px the toolbox takes 0-123, the blocks start at x 135 at the phone's scale 0.6, and Blockly's
// trashcan / zoom column starts at x 323 (theme.ts BLOCKLY_CONTROLS): a block row wider than ~188 px
// (313 units) was cut at the screen's edge or sat under the controls (108 of 121 setting blocks were
// cut; alarm_fast showed 57 %). Blockly does not wrap fields, so the block is laid out on rows: its
// words wrapped over one or more label rows, then the value with its unit and "· var" (the var on a
// row of its own where that row would be too wide), then a safety switch's warning rows (shown while
// it is off), then up to SETTING_NOTE_ROWS rows for the lint's "not used" words. The widths are a
// MODEL of Blockly's own measuring (no browser here): per-character widths of a wide sans at the
// theme's 12 pt (16 px) and zelos' paddings, fitted to the reviewer's measurements of round 20
// (settings.test.ts pins the fit and that no row passes the budget).

/** Per-character widths in em (a WIDE sans, so the model errs wide). */
function charEm(c: string): number {
  if (c === " ") return 0.32;
  if ("il.,:;'!|j".includes(c)) return 0.28;
  if ("ftr".includes(c)) return 0.4;
  if ("()[]-".includes(c)) return 0.39;
  if (c === "·") return 0.32;
  if (c === "m") return 0.92;
  if (c === "w") return 0.8;
  if (c === "M") return 0.86;
  if (c === "W") return 0.99;
  if (c === "I") return 0.3;
  if (c === "%" || c === "⚠" || c === "…") return 0.95;
  if (c === "_") return 0.5;
  if (c === "=") return 0.84;
  if (/[0-9]/.test(c)) return 0.64;
  if (/[A-Z]/.test(c)) return 0.7;
  return 0.58;
}
/** zelos' spacing and the font's scale, FITTED to the reviewer's round-20 measurements at 1440 and
 * 390 (npc_guard's row 430 units, with its warning 1018, alarm_fast's 745: settings.test.ts): the
 * fit gave a scale of 1.166 on the table above and side + field + arrow = 72 with a gap of 8;
 * ``scale`` is taken at 1.2 so the model errs wide. */
export const SETTING_GEOMETRY = { scale: 1.2, side: 24, gap: 8, field: 24, arrow: 24, varPx: 12.8 } as const;
/** A text's width in workspace units at ``px`` (the theme's 12 pt = 16 px; the var label 0.8 em). */
export function textUnits(text: string, px = 16, bold = false): number {
  let em = 0;
  for (const c of text) em += charEm(c);
  return em * px * SETTING_GEOMETRY.scale * (bold ? 1.02 : 1);
}
/** No row of a setting block wider than this (workspace units): 313 fit beside the toolbox and
 * before the controls at 390 px (scale 0.6), kept 4 % under. */
export const SETTING_ROW_BUDGET = 300;
/** The rows the lint's "not used" words may take (BlockEditor fills them). */
export const SETTING_NOTE_ROWS = 3;

/** PURE: ``text`` wrapped into lines no wider than ``max`` units (a word longer stays whole). */
export function wrapUnits(text: string, max: number, px = 16, bold = false): string[] {
  const out: string[] = [];
  let line = "";
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const next = line ? `${line} ${word}` : word;
    if (line && textUnits(next, px, bold) > max) {
      out.push(line);
      line = word;
    } else line = next;
  }
  if (line) out.push(line);
  return out.length ? out : [""];
}
/** PURE: ``text`` in as many lines as wrapUnits gives at ``max``, but BALANCED: the narrowest
 * width that keeps that many lines (no lone last word: "look for items with the item / model"). */
export function wrapBalanced(text: string, max: number, px = 16, bold = false): string[] {
  const n = wrapUnits(text, max, px, bold).length;
  let lo = 0;
  let hi = max;
  while (hi - lo > 1) {
    const mid = (lo + hi) / 2;
    if (wrapUnits(text, mid, px, bold).length <= n) hi = mid;
    else lo = mid;
  }
  return wrapUnits(text, hi, px, bold);
}
const G = SETTING_GEOMETRY;
const LINE_MAX = SETTING_ROW_BUDGET - G.side;
/** A row of fields' width: the side paddings, the fields, a gap between each two. */
export const rowUnits = (fields: number[]): number => G.side + fields.reduce((a, b) => a + b, 0) + G.gap * Math.max(0, fields.length - 1);
const numberUnits = (v: number | string): number => Math.max(40, textUnits(String(v)) + G.field);
const dropdownUnits = (options: string[]): number => Math.max(...options.map((o) => textUnits(o))) + G.field + G.arrow;
export const varText = (f: SettingField): string => `· ${f.var}`;
const varUnits = (f: SettingField) => textUnits(varText(f), G.varPx);

/** The value row's fields' widths (without the var label): a number with its unit, a switch's or a
 * choice's menu, a point's x and y. */
export function valueFieldUnits(f: SettingField): number[] {
  const wide = (lo: number, hi: number, step: number) => {
    const pct = f.kind === "share" ? 100 : 1;
    return [lo, hi, hi - step].map((x) => String(tidy(x * pct)));
  };
  switch (f.kind) {
    case "switch":
      return [dropdownUnits(["on", "off"])];
    case "choice":
      return [dropdownUnits(f.options)];
    case "point":
      return [textUnits("x"), numberUnits(SETTINGS.game_px[0] - 1), textUnits("y"), numberUnits(SETTINGS.game_px[1] - 1)];
    case "point_or_none": // its at / none menu is a row of its own (settingRows ``menuRow``)
      return [textUnits("x"), numberUnits(SETTINGS.game_px[0] - 1), textUnits("y"), numberUnits(SETTINGS.game_px[1] - 1)];
    default: {
      const widest = Math.max(...wide(f.lo, f.hi, f.step).map((t) => numberUnits(t)));
      const u = unitOf(f);
      return u ? [widest, textUnits(u)] : [widest];
    }
  }
}

/** A setting block's rows (matpilot round 20 #2): the words' lines, a point-or-none's at / none
 * menu on a row of its own, whether "· var" fits on the value row, and a safety switch's warning
 * lines ("⚠ off: " first). */
export type SettingRows = { words: string[]; menuRow: boolean; varOwnRow: boolean; warn: string[] };
export function settingRows(f: SettingField): SettingRows {
  const words = wrapBalanced(f.words, LINE_MAX);
  const varOwnRow = rowUnits([...valueFieldUnits(f), varUnits(f)]) > SETTING_ROW_BUDGET;
  const warn = f.warn ? wrapBalanced(`⚠ off: ${f.warn}`, LINE_MAX, 16, true) : [];
  return { words, menuRow: f.kind === "point_or_none", varOwnRow, warn };
}
/** PURE: the lint's "not used" words as the block's note rows (at most SETTING_NOTE_ROWS; the rest
 * in the tooltip), each line no wider than the budget. */
export function noteLines(text: string, mark = "·"): string[] {
  if (!text) return [];
  const lines = wrapBalanced(`${mark} ${text}`, LINE_MAX);
  return lines.length <= SETTING_NOTE_ROWS ? lines : [...lines.slice(0, SETTING_NOTE_ROWS - 1), `${lines[SETTING_NOTE_ROWS - 1]} …`];
}
/** Every row's width of a setting block as laid out (the test's measure; the note rows at their
 * widest: a line of the budget). */
export function settingRowUnits(f: SettingField): number[] {
  const r = settingRows(f);
  const out = r.words.map((w) => rowUnits([textUnits(w)]));
  if (r.menuRow) out.push(rowUnits([dropdownUnits(["at", "none"])]));
  out.push(rowUnits([...valueFieldUnits(f), ...(r.varOwnRow ? [] : [varUnits(f)])]));
  if (r.varOwnRow) out.push(rowUnits([varUnits(f)]));
  for (const w of r.warn) out.push(rowUnits([textUnits(w, 16, true)]));
  return out;
}

// --- the block's fields (blockdefs.ts settingDef defines them; blocks.ts converts) ------------------
export const SETTING_TYPE_PREFIX = "pl_set_";
export const settingType = (f: SettingField): string => `${SETTING_TYPE_PREFIX}${f.var}`;
export const settingOfType = (type: string): SettingField | undefined => (type.startsWith(SETTING_TYPE_PREFIX) ? SETTING_BY_VAR.get(type.slice(SETTING_TYPE_PREFIX.length)) : undefined);
const xy = (v: string): [number, number] => {
  const [x, y] = v.split(",").map(Number);
  return [x, y];
};

/** PURE: a valid value as the block's fields (a share as its percent, a point as X and Y). */
export function settingFields(f: SettingField, v: SettingValue): Record<string, string | number> {
  switch (f.kind) {
    case "switch":
      return { VALUE: v === true ? "on" : "off" };
    case "choice":
    case "key":
      return { VALUE: String(v) };
    case "share":
      return { VALUE: tidy(Number(v) * 100) };
    case "point": {
      const [x, y] = xy(String(v));
      return { X: x, Y: y };
    }
    case "point_or_none": {
      const none = v === "none";
      const [x, y] = xy(none ? String(f.default === "none" ? "0,0" : f.default) : String(v));
      return { AT: none ? "none" : "at", X: x, Y: y };
    }
    default:
      return { VALUE: Number(v) };
  }
}

/** PURE: the block's fields as the setting's value, or why they are not one. */
export function settingFromFields(f: SettingField, fields: Record<string, unknown> | undefined): { value: SettingValue } | { error: string } {
  const fl = fields ?? {};
  let v: SettingValue;
  switch (f.kind) {
    case "switch":
      if (fl.VALUE !== "on" && fl.VALUE !== "off") return { error: "on or off" };
      v = fl.VALUE === "on";
      break;
    case "choice":
    case "key":
      v = String(fl.VALUE ?? "");
      break;
    case "share":
      v = tidy(Number(fl.VALUE) / 100);
      break;
    case "point":
    case "point_or_none":
      v = f.kind === "point_or_none" && fl.AT === "none" ? "none" : `${Math.round(Number(fl.X))},${Math.round(Number(fl.Y))}`;
      break;
    default:
      v = Number(fl.VALUE);
  }
  const why = settingProblem(f, v);
  return why === null ? { value: v } : { error: why };
}

// --- the start checklist (Before Run; the runner's read-only check ticks each line) ---------------
/** The start checklist's lines, in the page's order. Each id is a line the live check ticks from
 * the game screen (scripts/dungeon_hunt.py CHECK_IDS; test_live_check.py pins the two lists equal):
 * who plays, her cell, the chat input, the bag, the Fly Wings, the heal items, the Butterfly Wings,
 * the Knife in the bag and the dagger worn (the last two with the Knife swap only). */
export const CHECKLIST_IDS = ["identity", "cell", "chat", "weight", "wings", "heals", "home", "knife", "dagger"];

/** The five hotbar keys a project's functions give a Run and a check (poring_flow.settings
 * KEY_FIELDS; Batt 2026-11-13: every key from a FUNCTION of the flow). */
export const RUN_KEY_NAMES = ["heal_key", "fly_key", "home_key", "knife_key", "dagger_key"];
export type RunKeys = Record<string, string>;

/** One checklist line: its id (the check's), the text a person reads, and the values it states
 * (``basis``: a check made with other values is shown greyed, as outdated). */
export type ChecklistItem = { id: string; text: string; basis: Record<string, SettingValue>; map: string };

/** PURE: the run's values with the project's keys over them (the five keys only). */
export function withRunKeys(values: Record<string, SettingValue>, keys: RunKeys | null | undefined): Record<string, SettingValue> {
  const out = { ...values };
  for (const k of RUN_KEY_NAMES) if (keys && typeof keys[k] === "string") out[k] = keys[k];
  return out;
}

function checklistText(id: string, b: Record<string, SettingValue>, map: string): string {
  const s = (n: string) => String(b[n]);
  switch (id) {
    case "identity":
      return "her character on screen (the runner knows her name plate and job)";
    case "cell":
      // dungeon@9.46: the map is read from the minimap's PICTURE (scripts/minimap_id.py), her cell
      // from its readout; the tick needs both. "?" when the picture cannot tell: you check the map
      return `she stands on ${map} (the minimap's picture says the map), on its open ground (her cell)`;
    case "chat":
      return "the chat input closed (no white input bar under the chat)";
    case "weight":
      return `the bag under ${Math.round(Number(b.WEIGHT_MAX) * 100)} %`;
    case "wings":
      return `at least ${s("PLAYER_MIN_WINGS")} Fly Wings on ${s("fly_key")}`;
    case "heals":
      return `at least ${s("PLAYER_MIN_HEALS")} heal items on ${s("heal_key")}`;
    case "home":
      return `Butterfly Wings on ${s("home_key")} (the way home at the end)`;
    case "knife":
      return `the Knife on ${s("knife_key")} (in the bag)`;
    case "dagger":
      return `the dagger worn (${s("dagger_key")} empty on the hotbar)`;
    default:
      return id;
  }
}

/** PURE: what must be true before Run, in a person's words, from the values the run will take
 * (the node's setting blocks, nodeSettings) with the project's keys over them (``keys``: what the
 * check sends). Each line's id is the live check's. */
export function startChecklist(values: Record<string, SettingValue>, map: string, keys?: RunKeys | null): ChecklistItem[] {
  const v = withRunKeys(values, keys);
  const knife = settingInUse(v, "knife_key") && v.knife_swap === true;
  const basis: Record<string, string[]> = {
    identity: [],
    cell: [],
    chat: [],
    weight: ["WEIGHT_MAX"],
    wings: ["PLAYER_MIN_WINGS", "fly_key"],
    heals: ["PLAYER_MIN_HEALS", "heal_key"],
    home: ["home_key"],
    knife: ["knife_key", "knife_swap"],
    dagger: ["dagger_key", "knife_swap"],
  };
  return CHECKLIST_IDS.filter((id) => knife || (id !== "knife" && id !== "dagger")).map((id) => {
    const b: Record<string, SettingValue> = {};
    for (const n of basis[id]) b[n] = v[n];
    return { id, text: checklistText(id, b, map), basis: b, map };
  });
}

/** PURE: the lines with the project's keys over their values, their text written again (LiveRun's
 * ``keys``: the checklist states the keys a check sends). */
export function checklistWithKeys(items: ChecklistItem[], keys: RunKeys | null | undefined): ChecklistItem[] {
  if (!keys) return items;
  return items.map((it) => {
    const b = { ...it.basis };
    for (const k of Object.keys(b)) if (RUN_KEY_NAMES.includes(k) && typeof keys[k] === "string") b[k] = keys[k];
    return { ...it, basis: b, text: checklistText(it.id, b, it.map) };
  });
}

/** PURE: the setting tabs' one line on /flows' strip ("SETTINGS: the Knife swap -- Batt's technique
 * ...: 6 settings; a map's block replaces Global's, a deleted one falls back"), or null for a tab
 * that is not a settings group's or holds none. */
export function settingTabNote(tab: Tab, nodeKind: string, hasGlobal = true): string | null {
  const g = groupOf(tab.name);
  const n = Object.keys(tab.vars).filter((k) => SETTING_BY_VAR.get(k)?.block).length;
  if (!g || g.id === "keys" || n === 0) return null;
  // round 21 (the re-measure of round 20): Global is named only where the project has a Global node
  const rule = nodeKind === "global" ? "every map node takes these unless it sets its own" : hasGlobal ? "these replace Global's here; a deleted one falls back to Global's, else the default" : "a deleted one falls back to the default";
  return `${g.title} -- ${g.note}: ${n} setting${n === 1 ? "" : "s"} of the runner's hunt core (${rule})`;
}
