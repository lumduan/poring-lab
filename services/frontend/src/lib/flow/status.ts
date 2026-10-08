// What the canvas and the blocks SHOW from a lint and a simulate run (Node-RED's status badge idea:
// a line under each node). Pure functions, tested in status.test.ts.
import type { Finding, LintDoc, NodeRun, Severity, Trace } from "./api.ts";
import type { GEdge } from "./canvas.ts";

export type LintCounts = Record<Severity | "unsupported", number>;
const ZERO: LintCounts = { error: 0, warning: 0, info: 0, unsupported: 0 };

/** Findings of one canvas node (`block:<name>`, `global`, `flow`). Unsupported bindings (rule
 * `bindings`, ADR-0020 open question #6: no real flow lints clean today) are counted apart. */
export function lintOf(lint: LintDoc | null, owner: string): LintCounts {
  return { ...ZERO, ...(lint?.by_owner[owner] ?? {}) };
}

export function lintLine(c: LintCounts): { text: string; level: Severity | "ok" | "unsupported" } {
  const own = { error: c.error - c.unsupported, warning: c.warning, info: c.info };
  const parts: string[] = [];
  if (own.error) parts.push(`${own.error} error${own.error > 1 ? "s" : ""}`);
  if (own.warning) parts.push(`${own.warning} warning${own.warning > 1 ? "s" : ""}`);
  if (own.info) parts.push(`${own.info} info`);
  if (c.unsupported) parts.push(`${c.unsupported} unsupported`);
  const level = own.error ? "error" : own.warning ? "warning" : c.unsupported ? "unsupported" : own.info ? "info" : "ok";
  return { text: parts.length ? parts.join(" · ") : "lint ok", level };
}

export function findingsByPath(lint: LintDoc | null): Map<string, Finding[]> {
  const out = new Map<string, Finding[]>();
  for (const f of lint?.findings ?? []) {
    const k = f.path;
    out.set(k, [...(out.get(k) ?? []), f]);
  }
  return out;
}

export function runLine(r: NodeRun | undefined): string {
  if (!r) return "";
  const outcomes = Object.entries(r.outcomes)
    .map(([k, n]) => (Object.keys(r.outcomes).length > 1 ? `${k} ${n}` : k))
    .join(", ");
  return `▶ ${r.runs}× ${outcomes} · ${r.total_s.toFixed(1)} s`;
}

export function blockRunLine(trace: Trace | null, block: string): string {
  const b = trace?.blocks[block];
  if (!b) return trace ? "not reached" : "";
  return `${b.visits} visit${b.visits === 1 ? "" : "s"} · ${b.time_s.toFixed(0)} s`;
}

/** How often the run took each exit edge (matched by source, kind and target). */
export function edgeRuns(trace: Trace | null, edges: GEdge[]): Map<string, number> {
  const out = new Map<string, number>();
  if (!trace) return out;
  const count = new Map<string, number>();
  for (const t of trace.transitions) {
    const k = `block:${t.from}|${t.kind}|block:${t.to}`;
    count.set(k, (count.get(k) ?? 0) + 1);
  }
  for (const e of edges) {
    const k = `${e.source}|${e.data.kind}|${e.target}`;
    if (count.has(k)) out.set(e.id, count.get(k)!);
  }
  return out;
}

export const END_TEXT: Record<string, string> = {
  horizon: "the simulated time ran out (horizon)",
  done: "the flow ended",
  single_block_exit: "the map block took an exit (single node run)",
  max_runtime: "max_runtime_s reached",
  stop_when: "stop_when held",
  handler_runaway: "an event fired too often (runaway)",
  death_limit: "dead fired more than max_per_run",
  relocate_no_block: "relocation found no block for the map",
};
