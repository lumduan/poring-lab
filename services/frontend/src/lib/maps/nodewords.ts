// What a project NODE says, in words (the Maps cards and the node inspector, which /flows also
// shows): its kind, its tabs and their names (functions with their inputs, events with their
// trigger, variables with their value), which of them OVERRIDE Global's on that node, and for
// Global's names the nodes that override them (project.ts overridesOn / overriddenBy), and the
// lint counts on the node. Pure functions, tested in project_maps.test.ts.
import type { Finding, LintDoc, Severity } from "../flow/api.ts";
import { countsFor, sitePath } from "../flow/api.ts";
import { exprText } from "../flow/expr.ts";
import type { Lit } from "../flow/ir.ts";
import { type Def, globalOf, keyOfCall, MAIN_TAB, type MapNode, modelOn, namesOf, overriddenBy, paramsText, type PNode, type Project, runnerBlockOn, type Trigger } from "../flow/project.ts";

export const KIND_TITLE: Record<PNode["kind"], string> = { login: "Login", character: "Choose character", map: "Map", global: "Global" };

/** The card's and the inspector's title: the map id for a map node, else the kind. */
export function nodeTitle(n: PNode): string {
  return n.kind === "map" ? n.map.map : KIND_TITLE[n.kind];
}

const litText = (l: Lit) => exprText(l);

/** A function's head as Python writes it: "heal()", "press(key, times=1, *args)". */
export function defHead(d: Def): string {
  return `${d.name}(${paramsText(d, litText)})`;
}

/** An event's trigger in a few words: "when hp_percent() < 30 · survival · then resume". */
export function triggerText(t: Trigger): string {
  const extra = [t.max_per_run !== null ? `at most ${t.max_per_run} a run` : ""].filter(Boolean);
  return [`when ${exprText(t.when)}`, t.priority, `then ${t.then}`, ...extra].join(" · ");
}

export type NameRow = {
  name: string;
  kind: "def" | "event" | "var";
  text: string; // "heal()" / "hp_low · when hp_percent() < 30 · ..." / "WEIGHT = 50"
  overrides: boolean; // a node's name that overrides Global's here
  overriddenOn: string[]; // a Global name: the nodes that override it
  key: string | null; // the one key a function without inputs presses (resolved on this node)
  clash: string[]; // other functions on this node that press the same key (matpilot 9: marked where it is)
};

/** The keys the functions WITHOUT inputs press on a node (its own, then Global's it does not
 * override), each resolved there (project.ts keyOfCall: one press_key, or one call of another). */
export function keysOn(p: Project, n: PNode): Map<string, string> {
  const out = new Map<string, string>();
  const names = new Map(namesOf(n));
  const g = globalOf(p);
  if (g && n.kind !== "global") for (const [k, v] of namesOf(g)) if (!names.has(k)) names.set(k, v);
  for (const [name, v] of names) {
    if (v.kind !== "def" || !v.def || v.def.params.length || v.def.varargs || v.def.kwargs) continue;
    const r = keyOfCall(p, n.id, name);
    if ("key" in r) out.set(name, r.key);
  }
  return out;
}
export type TabRow = { tab: string; main: boolean; statements: number; rows: NameRow[] };

/** A node's tabs, each with its names, marked for overrides (Global's: which nodes override). */
export function tabRows(p: Project, n: PNode): TabRow[] {
  const g = globalOf(p);
  const globalNames = new Set<string>();
  if (g && n.kind !== "global") for (const t of g.tabs) for (const d of t.defs) globalNames.add(d.name);
  if (g && n.kind !== "global") for (const t of g.tabs) for (const v of Object.keys(t.vars)) globalNames.add(v);
  const keys = keysOn(p, n);
  const clash = (name: string): string[] => {
    const k = keys.get(name);
    return k === undefined ? [] : [...keys].filter(([o, ok]) => o !== name && ok === k).map(([o]) => o).sort();
  };
  return n.tabs.map((t) => {
    const rows: NameRow[] = [];
    for (const d of t.defs) {
      rows.push({
        name: d.name,
        kind: d.on ? "event" : "def",
        text: d.on ? `${d.name} · ${triggerText(d.on)}` : defHead(d),
        overrides: globalNames.has(d.name),
        overriddenOn: n.kind === "global" ? overriddenBy(p, d.name) : [],
        key: d.on ? null : (keys.get(d.name) ?? null),
        clash: d.on ? [] : clash(d.name),
      });
    }
    for (const [k, v] of Object.entries(t.vars)) {
      rows.push({ name: k, kind: "var", text: `${k} = ${litText(v)}`, overrides: globalNames.has(k), overriddenOn: n.kind === "global" ? overriddenBy(p, k) : [], key: null, clash: [] });
    }
    return { tab: t.name, main: t.name === MAIN_TAB && t.main !== null, statements: t.main?.length ?? 0, rows };
  });
}

/** The node's tab names in order ("main, hunt, npc"), for a card line. */
export function tabList(n: PNode): string {
  return n.tabs.map((t) => t.name).join(", ") || "no tabs yet";
}

export type NodeLint = { counts: Record<Severity, number>; findings: Finding[] };

// --- the severity order (matpilot round 17 N2) ---------------------------------------------------
// The inspector showed a node's first 6 findings in the engine's (layer) order: on xmas_dun02 all
// 6 were info lines, unlabelled, and "...and 18 more" hid all 4 warnings. Every list the Maps page
// shows is ordered by severity now, each line labelled, and a capped list says what it hides.
/** Most serious first: an error, then what is not ready, then a warning, then an info line. */
export const SEVERITY_ORDER: readonly Severity[] = ["error", "readiness", "warning", "info"];
/** The word a line starts with (a finding's severity, always shown). */
export const SEVERITY_WORDS: Record<Severity, string> = { error: "error", readiness: "not ready", warning: "warning", info: "info" };

/** PURE: the findings by severity (SEVERITY_ORDER), each severity's in the engine's own order. */
export function bySeverity(fs: readonly Finding[]): Finding[] {
  const rank = (f: Finding) => {
    const i = SEVERITY_ORDER.indexOf(f.severity);
    return i < 0 ? SEVERITY_ORDER.length : i;
  };
  return fs.map((f, i) => ({ f, i })).sort((a, b) => rank(a.f) - rank(b.f) || a.i - b.i).map((x) => x.f);
}

/** PURE: a list capped at `max` lines: the most serious first, and what the rest are in words
 * ("…and 18 more (18 info): the lint chip lists every one; so does /flows' Lint pane"), or null. */
export function cappedFindings(fs: readonly Finding[], max: number): { shown: Finding[]; more: string | null } {
  const all = bySeverity(fs);
  const shown = all.slice(0, Math.max(0, max));
  const rest = all.slice(shown.length);
  if (!rest.length) return { shown, more: null };
  const kinds = SEVERITY_ORDER.map((s) => [s, rest.filter((f) => f.severity === s).length] as const).filter(([, n]) => n > 0);
  const what = kinds.map(([s, n]) => (s === "info" ? `${n} info` : `${n} ${SEVERITY_WORDS[s]}${s === "readiness" ? "" : n === 1 ? "" : "s"}`)).join(", ");
  return { shown, more: `…and ${rest.length} more (${what}): the lint chip lists every one; so does /flows' Lint pane` };
}

/** Where a finding is inside its node ("main main.0: "), or "" for the node or the project itself. */
export function findingWhere(f: Finding): string {
  if (!f.tab) return "";
  const site = sitePath(f);
  return `${f.tab}${site && site !== f.path ? ` ${site}` : ""}: `;
}
const ZERO = (): Record<Severity, number> => ({ error: 0, readiness: 0, warning: 0, info: 0 });
/** A finding is ON a node: the project model's `node` field, else a path that starts with its id. */
const onNode = (f: Finding, id: string) => (f.node !== undefined ? f.node === id : f.path === id || f.path.startsWith(`${id}/`));

/** The findings ON a node (the project model's `node` field, else a path that starts with the
 * node's id), counted by severity and listed most serious first (bySeverity, round 17 N2); the
 * engine's by_owner[node] when no finding names a node. */
export function nodeLint(lint: LintDoc | null, id: string): NodeLint {
  const counts = ZERO();
  if (!lint) return { counts, findings: [] };
  const findings = bySeverity(lint.findings.filter((f) => onNode(f, id)));
  for (const f of findings) counts[f.severity] += 1;
  const own = countsFor(lint, id); // the project lint's by_node (IR 2's by_owner as before)
  if (!findings.length && own) return { counts: { ...counts, ...own }, findings };
  return { counts, findings };
}

/** One group of the Maps page's lint list: a node's findings (as its card counts them), or the
 * PROJECT's own (`node` null: on no node, or on a node id this project does not have). */
export type LintGroup = { node: string | null; findings: Finding[]; counts: Record<Severity, number> };

/** Every finding of the lint, where the page shows it (matpilot round 16 #7: the chip said "3
 * warnings", the cards 2; the third, "a death returns to the save point on geffen, where no block
 * is", was on the project itself and no card showed it). The project's own first, then each
 * node's in the project's order, by the same rule as the cards (nodeLint). Every finding is in
 * exactly one group, so the groups add up to the lint's counts: the chip's words. Each group's
 * findings by severity (round 17 N2). */
export function lintGroups(lint: LintDoc | null, p: Project): LintGroup[] {
  if (!lint) return [];
  const groups = new Map<string | null, Finding[]>([[null, []], ...p.nodes.map((n): [string, Finding[]] => [n.id, []])]);
  for (const f of lint.findings) groups.get(p.nodes.find((n) => onNode(f, n.id))?.id ?? null)!.push(f);
  return [...groups]
    .filter(([, fs]) => fs.length > 0)
    .map(([node, fs]) => {
      const counts = ZERO();
      for (const f of fs) counts[f.severity] += 1;
      return { node, findings: bySeverity(fs), counts };
    });
}

/** PURE (matpilot round 17 N3): on a map node whose main runs the RUNNER (dungeon_hunt), who
 * picks the targets -- the runner, by its hunt core's model, never the node's TARGET / IGNORE
 * lists, and never a recipe (a recipe chooses HOW) -- and the engine's line for each spawn ("mob
 * 1249 spawns on xmas_dun02: the runner strikes it (...)", the species_lists lint); null on a
 * node without the runner (there the lists decide, as the lint says). */
export function runnerSpecies(n: MapNode, lint: LintDoc | null): { words: string; lines: string[] } | null {
  if (runnerBlockOn(n) === null) return null;
  const model = modelOn(n);
  // matpilot round 18 #2: "every monster ${by} boxes as one it strikes" was hard to parse
  const by = model ? `the model named in main (use_model("${model}"))` : "the map's own detector (main names no use_model)";
  const its = model ? "the model's" : "the detector's";
  const words = `This node runs the runner (hunt with the runner): in the game it strikes every monster that ${by} boxes as a target, whatever these two lists say. A monster's function (attack_<monster>, the monsters tab) chooses HOW that monster is attacked, never WHETHER; ${its} other classes and the monsters it has no class for (the map's boss) are never struck: the runner's own rules. The lists are the simulator's.${lint ? " The lint names each spawn:" : ""}`;
  const lines = lint ? nodeLint(lint, n.id).findings.filter((f) => f.rule === "species_lists").map((f) => f.text || f.message) : [];
  return { words, lines };
}
