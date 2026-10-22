// The HUNT block in the block editor (docs/planning/blocks-from-hunt-flow.md B2; ADR-0020
// Amendment A 1 + 3, DRAFT; Batt D2 2026-10-21: one `hunt` block with groups). Pure data.
//
// - Its parameters are a person's CHOICES: each one a RULE VERSION (`name@N`, PARAMS[N]'s numbers,
//   read-only) from the registry's list (blocks.yaml `choices`), grouped as Batt decided (engage;
//   dead + loot; search; stop = the enclosing loop). The block has a dropdown per parameter and
//   NOTHING else: no gate, safety number, reader or constant can be a field (the plan's section 6:
//   "no gate has a field"); the engine keeps them.
// - The lists and their BADGES come from the backend (GET /flows/catalogue `hunt_rules`,
//   poring_flow.hunt_rules): ★ the adopted base's rule, ◆ hunting evidence under Batt's D8 rule
//   (a pre-registered verdict, hard bars 0, >= 4 h; one path, one map, an immune GM), and the
//   PARAMS versions that hold it. The L1 badge (verified / unverified) stays beside them.
// - OPTION parameters (Batt 2026-10-22: `engage_source`, detector | melee_ring) sit in their group
//   as a dropdown of plain values: no version, no numbers, no badge; the registry's `default` is
//   what an ABSENT parameter means, and the editor writes the parameter only when it differs from
//   it (an explicit default stays a generic block, exactly). The linter refuses melee_ring on a map
//   with an IGNORE list or a non-TARGET species and on any server but the lab's (lint/hunt.py).
import type { BlockDef } from "./blockdefs.ts";

export type HuntEvidence = { entry: string; version: number; map: string; path: string; hours: number; verdict: string; gm: string };
export type HuntChoice = {
  id: string;
  known: boolean;
  values: Record<string, unknown>;
  versions: number[];
  adopted: boolean;
  evidence: HuntEvidence[];
  option?: boolean; // an OPTION's value, not a rule version
  is_default?: boolean; // the option's default (what an absent parameter means)
};
export type HuntParam = { name: string; choices: HuntChoice[]; default: string; kind?: "rule" | "option"; required?: boolean; note?: string };
export type HuntGroup = { name: string; params: HuntParam[]; note?: string };
export type HuntRules = {
  block: string;
  adopted: number;
  groups: HuntGroup[];
  evidence: { badges: string[]; rule: string; verdicts: (HuntEvidence & { d8: boolean; why_not: string; hard_bars: number[] })[] };
};

export const HUNT_TYPE = "pl_hunt";
export const GROUP_TITLE: Record<string, string> = {
  engage: "engage",
  dead_loot: "dead + loot",
  search: "search",
  stop: "stop",
};

/** The Blockly field that holds a parameter (P_STRIKE ...); reversible (param names are
 * [a-z][a-z0-9_]*). */
export const fieldOf = (param: string) => `P_${param.toUpperCase()}`;
export const paramOf = (field: string) => (field.startsWith("P_") ? field.slice(2).toLowerCase() : null);

export function params(rules: HuntRules): HuntParam[] {
  return rules.groups.flatMap((g) => g.params);
}

/** The optional parameters and their defaults: the editor leaves one out of the IR at its default
 * (absent = the default), so a flow written before the option keeps its JSON and its hash. */
export function omitted(rules: HuntRules): Record<string, string> {
  return Object.fromEntries(params(rules).filter((p) => p.required === false).map((p) => [p.name, p.default]));
}

/** A rule version's badges as text (the dropdown and the panel). */
export function badgeText(c: HuntChoice, adopted: number): string {
  if (c.option) return `option${c.is_default ? " · the default (absent = this)" : ""}`;
  const out: string[] = [];
  if (c.adopted) out.push(`★ adopted base v${adopted}`);
  if (c.evidence.length) {
    const where = [...new Set(c.evidence.map((e) => `${e.path.toUpperCase()} ${e.map}`))].join(", ");
    out.push(`◆ ${where} (${c.evidence.map((e) => e.entry).join(", ")})`);
  }
  if (!c.known) out.push("not in the index");
  out.push(c.versions.length ? `in v${c.versions[0]}${c.versions.length > 1 ? `..v${c.versions[c.versions.length - 1]} (${c.versions.length})` : ""}` : "in no version");
  return out.join(" · ");
}

const optionText = (c: HuntChoice) =>
  c.option ? `${c.id}${c.is_default ? " (default)" : ""}` : `${c.id}${c.adopted ? " ★" : ""}${c.evidence.length ? " ◆" : ""}`;

/** The pl_hunt block type, built from the catalogue (its lists change only with blocks.yaml). */
export function huntDef(rules: HuntRules, colour: string): BlockDef {
  const badge = { type: "field_label" as const, name: "BADGE", text: "", class: "pl-badge" };
  const evidence = { type: "field_label" as const, name: "EVIDENCE", text: "", class: "pl-evidence" };
  const run = { type: "field_label" as const, name: "RUN", text: "", class: "pl-run" };
  const def: BlockDef & Record<string, unknown> = {
    type: HUNT_TYPE,
    message0: "hunt %1 %2 %3",
    args0: [badge, evidence, run],
    previousStatement: null,
    nextStatement: null,
    colour,
    mutator: "pl_state",
    tooltip: "hunt: hunt-flow's adopted rules as ONE block (Batt D2). Each parameter is a rule version; its numbers come with it, read-only. Gates, safety, readers and constants stay in the engine.",
  };
  let i = 1;
  for (const g of rules.groups) {
    if (g.params.length) {
      def[`message${i}`] = `${GROUP_TITLE[g.name] ?? g.name}: ${g.params.map((p, k) => `${p.name.replaceAll("_", " ")} %${k + 1}`).join("  ")}`;
      def[`args${i}`] = g.params.map((p) => ({
        type: "field_dropdown",
        name: fieldOf(p.name),
        options: p.choices.map((c) => [optionText(c), c.id] as [string, string]),
      }));
    } else {
      def[`message${i}`] = `${GROUP_TITLE[g.name] ?? g.name}: %1`;
      def[`args${i}`] = [{ type: "field_label", name: `NOTE_${g.name.toUpperCase()}`, text: g.note ?? "" }];
    }
    i++;
  }
  return def;
}

/** The block's tooltip: every parameter's choices with their badges and numbers. */
export function huntTooltip(rules: HuntRules, l1: string): string {
  const lines = [`hunt · L1: ${l1}${rules.evidence.badges.length ? ` · hunting evidence (D8): ${rules.evidence.badges.join(", ")}` : ""}`];
  for (const p of params(rules)) {
    if (p.kind === "option" && p.note) lines.push(`${p.name}: ${p.note}`);
    for (const c of p.choices) {
      const nums = Object.entries(c.values).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ");
      lines.push(`${p.name} ${c.id}: ${badgeText(c, rules.adopted)}${nums ? ` · ${nums}` : ""}`);
    }
  }
  return lines.join("\n");
}

/** The toolbox block's default fields: the adopted base's rule for each parameter. */
export function defaultFields(rules: HuntRules): Record<string, string> {
  return Object.fromEntries(params(rules).map((p) => [fieldOf(p.name), p.default]));
}
