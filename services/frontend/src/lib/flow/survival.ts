// THE SURVIVAL GROUP (Batt 2026-11-13 ~14:2x: "the heal and escape numbers can be set: make them a
// GLOBAL config for every map's flow; a map's flow that sets them again overrides it, with that
// map's config first"). Pure data and functions; the strip (components/flows/SurvivalStrip.tsx)
// reads and writes the backend's GET / PUT /flows/survival, and the Run helper
// (scripts/flow_run.py survival_of) takes, per number: the flow's default < every map's < the map's.
import type { RunnerDoc, RunnerNode, RunnerPart } from "./runner.ts";

export type SurvivalKey = "potion_below" | "fly_below" | "fly_rate" | "fly_rate_below";
export type Survival = Record<SurvivalKey, number>;
export const SURVIVAL_KEYS: SurvivalKey[] = ["potion_below", "fly_below", "fly_rate", "fly_rate_below"];
export type SurvivalLevel = "default" | "global" | "map";
/** The backend's file, as GET /flows/survival returns it. */
export type SurvivalConfig = { global: Partial<Survival>; maps: Record<string, Partial<Survival>>; broken?: boolean };
/** The export's part (lib/flow/runners/*.gen.ts settings.survival). */
export type SurvivalDoc = {
  defaults: Survival;
  params: Record<SurvivalKey, string[]>;
  choices: Record<Exclude<SurvivalKey, "fly_rate">, number[]>;
  fly_rate: [number, number];
  flags: Record<SurvivalKey, string>;
};

/** PURE: the numbers a Run uses on ``map`` and where each comes from (the map's own first). */
export function effectiveSurvival(d: SurvivalDoc, cfg: SurvivalConfig | null, map: string): { values: Survival; source: Record<SurvivalKey, SurvivalLevel> } {
  const values = { ...d.defaults };
  const source = Object.fromEntries(SURVIVAL_KEYS.map((k) => [k, "default"])) as Record<SurvivalKey, SurvivalLevel>;
  const levels: [SurvivalLevel, Partial<Survival> | undefined][] = [
    ["global", cfg?.global],
    ["map", cfg?.maps?.[map]],
  ];
  for (const [level, grp] of levels) {
    for (const k of SURVIVAL_KEYS) {
      const v = grp?.[k];
      if (typeof v === "number" && Number.isFinite(v)) {
        values[k] = v;
        source[k] = level;
      }
    }
  }
  return { values, source };
}

/** PURE: the level a person reads for the whole group: the highest one any number comes from. */
export function groupLevel(source: Record<SurvivalKey, SurvivalLevel>): SurvivalLevel {
  const ls = SURVIVAL_KEYS.map((k) => source[k]);
  return ls.includes("map") ? "map" : ls.includes("global") ? "global" : "default";
}

/** PURE: why these numbers cannot be saved (null: they can), against the export's choices. */
export function survivalProblem(v: Survival, d: SurvivalDoc): string | null {
  const words: Record<SurvivalKey, string> = {
    potion_below: "heal at HP under",
    fly_below: "Fly Wing at HP under",
    fly_rate: "the fast fall",
    fly_rate_below: "the fast fall's HP",
  };
  for (const k of ["potion_below", "fly_below", "fly_rate_below"] as const) {
    if (!d.choices[k].some((c) => Math.abs(c - v[k]) < 1e-9)) return `${words[k]} ${Math.round(v[k] * 100)} %: not one of the choices`;
  }
  const [lo, hi] = d.fly_rate;
  if (!(Number.isFinite(v.fly_rate) && v.fly_rate >= lo && v.fly_rate <= hi)) return `the fast fall ${v.fly_rate} HP/s is not from ${lo} to ${hi}`;
  return null;
}

/** The text a block shows for a number (the export's own format: a share as a whole percent). */
export const survivalShown = (k: SurvivalKey, v: number) => (k === "fly_rate" ? String(Math.round(v)) : String(Math.round(v * 100)));

/** PURE: the doc with these survival numbers in its blocks and its params (the Python outline is
 * left as exported, as withSettings does). */
export function withSurvival(doc: RunnerDoc, d: SurvivalDoc, v: Survival): RunnerDoc {
  const byParam = new Map<string, [string, number]>();
  for (const k of SURVIVAL_KEYS) for (const id of d.params[k] ?? []) byParam.set(id, [survivalShown(k, v[k]), v[k]]);
  const parts = (ps: RunnerPart[] | undefined) => ps?.map((p) => ("param" in p && byParam.has(p.param) ? { param: p.param, shown: (byParam.get(p.param) as [string, number])[0] } : p));
  const node = (n: RunnerNode): RunnerNode => ({
    ...n,
    parts: parts(n.parts),
    branches: n.branches?.map((b) => ({ ...b, parts: parts(b.parts) ?? b.parts, body: b.body.map(node) })),
    body: n.body?.map(node),
  });
  const params = { ...doc.params };
  for (const [id, [, value]] of byParam) if (params[id]) params[id] = { ...params[id], value };
  return { ...doc, params, stacks: doc.stacks.map(node) };
}
