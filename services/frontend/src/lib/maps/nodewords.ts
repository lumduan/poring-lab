// What a project NODE says, in words (the Maps cards and the node inspector, which /flows also
// shows): its kind, its tabs and their names (functions with their inputs, events with their
// trigger, variables with their value), which of them OVERRIDE Global's on that node, and for
// Global's names the nodes that override them (project.ts overridesOn / overriddenBy), and the
// lint counts on the node. Pure functions, tested in project_maps.test.ts.
import type { Finding, LintDoc, Severity } from "../flow/api.ts";
import { countsFor } from "../flow/api.ts";
import { exprText } from "../flow/expr.ts";
import type { Lit } from "../flow/ir.ts";
import { type Def, globalOf, keyOfCall, MAIN_TAB, namesOf, overriddenBy, paramsText, type PNode, type Project, type Trigger } from "../flow/project.ts";

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
const ZERO = (): Record<Severity, number> => ({ error: 0, readiness: 0, warning: 0, info: 0 });

/** The findings ON a node (the project model's `node` field, else a path that starts with the
 * node's id), by severity; the engine's by_owner[node] when no finding names a node. */
export function nodeLint(lint: LintDoc | null, id: string): NodeLint {
  const counts = ZERO();
  if (!lint) return { counts, findings: [] };
  const findings = lint.findings.filter((f) => (f.node !== undefined ? f.node === id : f.path === id || f.path.startsWith(`${id}/`)));
  for (const f of findings) counts[f.severity] += 1;
  const own = countsFor(lint, id); // the project lint's by_node (IR 2's by_owner as before)
  if (!findings.length && own) return { counts: { ...counts, ...own }, findings };
  return { counts, findings };
}
