// THE FLOW CONFIG on /flows (Batt 2026-11-13: "nothing is fixed, we only put the defaults"; "a
// global config for every map's flow; a map's flow that sets them again overrides it"; "move them
// too"; "all of them"). The export carries the registry (scripts/flow_config.py: each setting's
// group, kind, range, words, default, the doc params that show it); the backend's GET / PUT
// /flows/config hold the values (every map's, each map's own). Pure data and functions: the panel
// (components/flows/ConfigPanel.tsx) and the tests use them. Every value renders as text.
import type { RunnerDoc, RunnerNode, RunnerPart } from "./runner.ts";

export type ConfigKind = "key" | "share" | "number" | "int" | "point" | "point_or_none" | "switch" | "choice";
export type ConfigValue = string | number | boolean;
export type ConfigField = {
  name: string;
  group: string;
  kind: ConfigKind;
  words: string;
  lo: number;
  hi: number;
  step: number;
  unit: string;
  flag: string; // its own runner flag, "--tune", or "" (a switch that gates others only)
  off?: string; // a switch the runner has on by default: the flag that turns it off
  options?: string[]; // a choice's values ("off": no flag at all)
  warn?: string; // said beside it while it is off (a safety technique)
  needs?: [string, ConfigValue][]; // in use only while these hold (else not passed, greyed)
  default: ConfigValue;
  params: string[]; // the doc params whose numbers show it in the blocks
};
export type ConfigGroup = { id: string; title: string; note: string };
export type ConfigDoc = { groups: ConfigGroup[]; fields: ConfigField[]; keys: string[]; game_px: [number, number]; map: string };
/** The backend's file, as GET /flows/config returns it. */
export type ConfigFile = { global: Record<string, ConfigValue>; maps: Record<string, Record<string, ConfigValue>>; broken?: string };
export type Level = "default" | "global" | "map";

/** The groups shown open (the person's everyday settings); the rest fold under "more". */
export const FIRST_GROUPS = ["keys", "knife", "survival", "exits", "respawn"];

/** PURE: every setting's value on ``map`` and where it came from: the map's own first, then every
 * map's, then the default (the Run helper's order: scripts/flow_config.py effective). */
export function effectiveConfig(d: ConfigDoc, file: ConfigFile | null, map: string): { values: Record<string, ConfigValue>; source: Record<string, Level> } {
  const values: Record<string, ConfigValue> = {};
  const source: Record<string, Level> = {};
  for (const f of d.fields) {
    values[f.name] = f.default;
    source[f.name] = "default";
  }
  const levels: [Level, Record<string, ConfigValue> | undefined][] = [
    ["global", file?.global],
    ["map", file?.maps?.[map]],
  ];
  for (const [level, lvl] of levels) {
    for (const [k, v] of Object.entries(lvl ?? {})) {
      if (k in values) {
        values[k] = v;
        source[k] = level;
      }
    }
  }
  return { values, source };
}

/** PURE: the value the level BELOW ``scope`` gives (what a value equal to it need not store). */
export function belowValue(d: ConfigDoc, file: ConfigFile | null, scope: "global" | "map", name: string): ConfigValue | undefined {
  const f = d.fields.find((x) => x.name === name);
  if (!f) return undefined;
  return scope === "map" ? (file?.global?.[name] ?? f.default) : f.default;
}

const onGrid = (v: number, step: number) => step <= 0 || Math.abs(v / step - Math.round(v / step)) < 1e-6;

/** PURE: a setting is IN USE when each of its needs holds and each needed setting is in use
 * (scripts/flow_config.py in_use): one not in use is not passed, and the page greys it. */
export function inUse(d: ConfigDoc, values: Record<string, ConfigValue>, name: string, seen: ReadonlySet<string> = new Set()): boolean {
  const f = d.fields.find((x) => x.name === name);
  if (!f || seen.has(name)) return false;
  for (const [other, want] of f.needs ?? []) {
    if (!inUse(d, values, other, new Set([...seen, name]))) return false;
    const v = values[other];
    if (want === "!off" ? v === undefined || v === "off" || v === false : v !== want) return false;
  }
  return true;
}

/** PURE: why a setting is not in use (its first unmet need, in a person's words); null: it is. */
export function notInUseWhy(d: ConfigDoc, values: Record<string, ConfigValue>, name: string): string | null {
  const f = d.fields.find((x) => x.name === name);
  if (!f || inUse(d, values, name)) return null;
  for (const [other, want] of f.needs ?? []) {
    const o = d.fields.find((x) => x.name === other);
    const v = values[other];
    const met = inUse(d, values, other) && (want === "!off" ? v !== undefined && v !== "off" && v !== false : v === want);
    if (!met) return `needs ${o?.words ?? other}${want === true ? " on" : want === "!off" ? "" : ` = ${String(want)}`}`;
  }
  return "not in use";
}

/** The text of a value as a person reads it (a share as a whole percent, as the export shows). */
export function shownValue(f: ConfigField, v: ConfigValue): string {
  if (typeof v === "boolean") return v ? "on" : "off";
  if (typeof v !== "number") return String(v);
  if (f.kind === "share") return `${Math.round(v * 10000) / 100}`;
  return String(Math.round(v * 10000) / 10000);
}

/** PURE: why ``v`` cannot be the field's value (null: it can) -- flow_config.problem_of's rules. */
export function fieldProblem(f: ConfigField, v: unknown, d: ConfigDoc): string | null {
  if (f.kind === "switch") return typeof v === "boolean" ? null : `${f.words}: not on or off`;
  if (f.kind === "choice") return (f.options ?? []).includes(String(v)) ? null : `${f.words}: ${String(v)} is not one of ${(f.options ?? []).join(", ")}`;
  if (f.kind === "key") return d.keys.includes(String(v)) ? null : `the ${f.words}'s key ${String(v)} is not a row-1 hotbar key (F1-F9)`;
  if (f.kind === "point" || f.kind === "point_or_none") {
    if (f.kind === "point_or_none" && v === "none") return null;
    const m = /^(\d{1,4}),(\d{1,4})$/.exec(typeof v === "string" ? v : "");
    return m && Number(m[1]) < d.game_px[0] && Number(m[2]) < d.game_px[1] ? null : `${f.words}: ${String(v)} is not a point X,Y in the ${d.game_px[0]} x ${d.game_px[1]} picture`;
  }
  if (typeof v !== "number" || !Number.isFinite(v)) return `${f.words}: not a number`;
  if (f.kind === "int" && !Number.isInteger(v)) return `${f.words}: ${v} is not a whole number`;
  const unit = f.kind === "share" ? " %" : f.unit ? ` ${f.unit}` : "";
  const s = (x: number) => `${shownValue(f, x)}${unit}`;
  if (v < f.lo - 1e-9 || v > f.hi + 1e-9) return `${f.words}: ${s(v)} is not from ${s(f.lo)} to ${s(f.hi)}`;
  if (!onGrid(v, f.step)) return `${f.words}: ${s(v)} is not a step of ${s(f.step)}`;
  return null;
}

/** PURE: why these values cannot run together (null: they can): each hotbar key its own. */
export function configClash(d: ConfigDoc, values: Record<string, ConfigValue>): string | null {
  const seen = new Map<string, ConfigField>();
  for (const f of d.fields) {
    if (f.kind !== "key" || !inUse(d, values, f.name)) continue;
    const v = String(values[f.name]);
    const other = seen.get(v);
    if (other) return `the ${other.words} and the ${f.words} are both on ${v}: each needs its own key`;
    seen.set(v, f);
  }
  const hf = values.hud_fast;
  const be = values.BOX_EVERY_S;
  if (typeof hf === "number" && typeof be === "number" && inUse(d, values, "hud_fast") && !(hf < be)) return `the HUD's fresh box every ${hf} s must be faster than the detector (${be} s)`;
  return null;
}

/** PURE: a group's values at a level after one change: only those that differ from the level
 * below are kept (an unchanged number keeps following the default). */
export function levelAfter(d: ConfigDoc, file: ConfigFile | null, scope: "global" | "map", map: string, group: string, name: string, v: ConfigValue): Record<string, ConfigValue> {
  const lvl = scope === "map" ? (file?.maps?.[map] ?? {}) : (file?.global ?? {});
  const out: Record<string, ConfigValue> = {};
  for (const f of d.fields) {
    if (f.group !== group) continue;
    const cur = f.name === name ? v : lvl[f.name];
    if (cur === undefined) continue;
    if (cur !== belowValue(d, file, scope, f.name)) out[f.name] = cur;
  }
  return out;
}

/** A value as the runner's flag takes it (scripts/flow_config.py flag_value). */
export function flagValue(f: ConfigField, v: ConfigValue): string {
  if (typeof v === "boolean") return v ? "on" : "off";
  if (typeof v !== "number") return String(v);
  if (f.kind === "share") return v.toFixed(2);
  if (f.kind === "int") return String(Math.round(v));
  return String(Math.round(v * 10000) / 10000);
}

/** PURE: the flags a Run adds for these values (scripts/flow_config.py argv: a field with a flag
 * always; a runner number only when a level set it). */
export function configArgv(d: ConfigDoc, values: Record<string, ConfigValue>, source: Record<string, Level>): string[] {
  const out: string[] = [];
  for (const f of d.fields) {
    if (!inUse(d, values, f.name)) continue;
    const v = values[f.name];
    if (f.kind === "switch") {
      if (v === true && f.flag) out.push(f.flag);
      else if (v === false && f.off) out.push(f.off);
    } else if (f.kind === "choice" && v === "off") {
      // "off": no flag at all
    } else if (f.flag && f.flag !== "--tune") out.push(f.flag, flagValue(f, v));
    else if (f.flag === "--tune" && source[f.name] !== "default") out.push("--tune", `${f.name}=${flagValue(f, v)}`);
  }
  return out;
}

/** PURE: the doc with these values in its blocks and its params (the Python outline is left as
 * exported: its lines are the blocks' marks). */
export function withConfig(doc: RunnerDoc, d: ConfigDoc, values: Record<string, ConfigValue>): RunnerDoc {
  const byParam = new Map<string, [string, ConfigValue]>();
  for (const f of d.fields) for (const id of f.params) byParam.set(id, [shownValue(f, values[f.name]), values[f.name]]);
  const parts = (ps: RunnerPart[] | undefined) => ps?.map((p) => ("param" in p && byParam.has(p.param) ? { param: p.param, shown: (byParam.get(p.param) as [string, ConfigValue])[0] } : p));
  // a block of a technique switched off (its gate not on): greyed, its words begin "off:"
  const off = (n: RunnerNode) => n.gate !== undefined && !(inUse(d, values, n.gate) && values[n.gate] === true);
  const node = (n: RunnerNode): RunnerNode => {
    const dim = off(n);
    const ps = parts(n.parts);
    return {
      ...n,
      style: dim ? (n.kind === "hat" ? "rd_off_hat_blocks" : "rd_off_blocks") : n.style,
      parts: dim && ps ? [{ text: "off: " }, ...ps] : ps,
      branches: n.branches?.map((b, k) => ({ ...b, parts: dim && k === 0 ? [{ text: "off: " }, ...(parts(b.parts) ?? b.parts)] : (parts(b.parts) ?? b.parts), body: b.body.map(node) })),
      body: n.body?.map(node),
    };
  };
  const params = { ...doc.params };
  for (const [id, [, value]] of byParam) if (params[id]) params[id] = { ...params[id], value };
  return { ...doc, params, stacks: doc.stacks.map(node) };
}

/** PURE: the export's own text for every setting's params equals shownValue of its default (the
 * page's numbers and the export's are written the same way). */
export function configShownMatchesExport(doc: RunnerDoc, d: ConfigDoc): boolean {
  const want = new Map<string, string>();
  for (const f of d.fields) for (const id of f.params) want.set(id, shownValue(f, f.default));
  const walk = (ps: RunnerPart[] | undefined) => (ps ?? []).every((p) => !("param" in p) || !want.has(p.param) || want.get(p.param) === p.shown);
  const ok = (n: RunnerNode): boolean => walk(n.parts) && (n.branches ?? []).every((b) => walk(b.parts) && b.body.every(ok)) && (n.body ?? []).every(ok);
  return doc.stacks.every(ok);
}

/** PURE: what must be true before Run, in a person's words, from the values the run will take
 * (matpilot 2026-11-13: "the start conditions are buried in a long paragraph"). */
export function startChecklist(d: ConfigDoc, values: Record<string, ConfigValue>, map: string): string[] {
  const v = (n: string) => values[n];
  const pct = (n: string) => Math.round(Number(v(n)) * 100);
  const out = [
    `she stands on ${map}, on its open ground`,
    "the chat input closed (no white input bar under the chat)",
    `the bag under ${pct("WEIGHT_MAX")} %`,
    `at least ${String(v("PLAYER_MIN_WINGS"))} Fly Wings on ${String(v("fly_key"))}`,
    `at least ${String(v("PLAYER_MIN_HEALS"))} heal items on ${String(v("heal_key"))}`,
    `Butterfly Wings on ${String(v("home_key"))} (the way home at the end)`,
  ];
  if (inUse(d, values, "knife_key") && v("knife_swap") === true) out.push(`the Knife on ${String(v("knife_key"))} (in the bag) and the dagger worn (${String(v("dagger_key"))})`);
  return out;
}
