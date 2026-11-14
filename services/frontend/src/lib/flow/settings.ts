// THE SETTING BLOCKS (docs/planning/live-blocks.md section 12; Batt 2026-11-14 ~15:2x: "there should
// be no runner [page] ... everything in the xmas_dun02 flow, split into tabs ... make them ALL
// blocks, no hardcoding like this"). Every number and switch of the runner's hunt core is a
// PROJECT VARIABLE named like the setting (settings.gen.ts: the engine's registry,
// packages/poring_flow/src/poring_flow/settings.py, drift-tested), shown as a block of its own in the
// tab of its group (knife, survival, exits, respawn, start, fight, aim, loot, walk, safety, loop). A
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
  warn: string; // said while it is off (a safety technique)
  needs: [string, SettingValue][];
  default: SettingValue;
};
export type SettingGroup = { id: string; title: string; note: string };
export type SettingsRegistry = { version: number; groups: SettingGroup[]; fields: SettingField[]; keys: string[]; game_px: number[]; tabs: string[]; runner_maps: string[] };

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

/** The unit after a value ("%" for a share). */
export const unitOf = (f: SettingField): string => (f.kind === "share" ? "%" : f.unit);
const withUnit = (f: SettingField, v: SettingValue) => `${shownValue(f, v)}${unitOf(f) ? ` ${unitOf(f)}` : ""}`;

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

/** A setting block's tooltip: its variable, tab, words, range, default and what deleting it does. */
export function settingTooltip(f: SettingField, fallback?: string): string {
  const range =
    f.kind === "switch"
      ? "on or off"
      : f.kind === "choice"
        ? `one of ${f.options.join(", ")}`
        : f.kind === "point" || f.kind === "point_or_none"
          ? `a point X, Y in the ${SETTINGS.game_px[0]} x ${SETTINGS.game_px[1]} game picture${f.kind === "point_or_none" ? ', or "none"' : ""}`
          : `${withUnit(f, f.lo)} to ${withUnit(f, f.hi)}, in steps of ${withUnit(f, f.step)}`;
  const runner = f.flag === "--tune" ? `the runner's ${f.name} (--tune)` : f.flag ? `the runner's ${f.flag}` : "a switch for the settings it needs";
  return `${f.var} = ... (tab ${f.group}): ${f.words}. ${range}; our default ${withUnit(f, f.default)}; ${runner}. A map's block replaces Global's there. Delete this block: ${fallback ?? "Global's value (a map node), else the default"} applies.${f.warn ? `\nWhile it is off: ${f.warn}` : ""}`;
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
export function settingTabNote(tab: Tab, nodeKind: string): string | null {
  const g = groupOf(tab.name);
  const n = Object.keys(tab.vars).filter((k) => SETTING_BY_VAR.get(k)?.block).length;
  if (!g || g.id === "keys" || n === 0) return null;
  const rule = nodeKind === "global" ? "every map node takes these unless it sets its own" : "these replace Global's here; a deleted one falls back to Global's, else the default";
  return `${g.title} -- ${g.note}: ${n} setting${n === 1 ? "" : "s"} of the runner's hunt core (${rule})`;
}
