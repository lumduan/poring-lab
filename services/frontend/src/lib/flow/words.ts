// What the /flows studio SAYS (Batt 2026-11-09, matpilot's /blocks wording): a block's own words,
// the start hat's title per tab, the problems under the blocks ("Fix before simulating", "Not
// running (the faded blocks)") and the status sentence in the footer. Pure functions over the
// workspace JSON (no Blockly), tested in words.test.ts.
import { type ArgDef, type BlockDef, DEF_BY_TYPE } from "./blockdefs.ts";
import type { Scope, WsBlock } from "./blocks.ts";
import type { Finding, LintDoc } from "./api.ts";

/** A detached stack: its top block, how many blocks it holds, and whether it is a value block. */
export type Loose = { id: string | null; type: string; words: string; count: number; value: boolean };
/** A block that cannot become the IR: where (a node path or a field), why, and its block. */
export type Issue = { where: string; text: string; id: string | null };

const DECORATION = new Set(["BADGE", "RUN", "EVIDENCE"]);

function argWords(a: ArgDef, b: WsBlock, depth: number): string {
  switch (a.type) {
    case "input_value": {
      const child = b.inputs?.[a.name]?.block;
      return child ? `(${blockWords(child, 200, depth + 1)})` : "…";
    }
    case "input_statement":
    case "input_dummy":
    case "field_image":
      return "";
    case "field_label":
      return DECORATION.has(a.name) ? "" : (a.text ?? "");
    default: {
      const v = b.fields?.[a.name];
      return v === undefined || v === "" ? "…" : String(v);
    }
  }
}

/** A block's words as it shows them ("walk to prontera x 150 y 180"), at most `max` characters. */
export function blockWords(b: WsBlock, max = 60, depth = 0): string {
  const def: BlockDef | undefined = DEF_BY_TYPE[b.type];
  let text: string;
  if (b.type === "pl_hunt") text = "hunt the map's targets";
  else if (!def || depth > 3) text = b.type.replace(/^pl_/, "").replaceAll("_", " ");
  else {
    const parts: string[] = [];
    const d = def as BlockDef & Record<string, unknown>;
    for (let n = 0; n < 6; n++) {
      const msg = d[`message${n}`] as string | undefined;
      if (msg === undefined) break;
      const args = (d[`args${n}`] as ArgDef[] | undefined) ?? [];
      parts.push(msg.replace(/%(\d+)/g, (_, k: string) => (args[Number(k) - 1] ? argWords(args[Number(k) - 1], b, depth) : "")));
    }
    text = parts.join(" ");
  }
  text = text.replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** The start hat's title: what a learner reads at the top of the tab's program. */
export function hatTitle(scope: Scope): string {
  if (scope.kind === "main") return "when the program starts";
  if (scope.kind === "block") return `when the flow arrives on ${scope.name}`;
  return "when … (an event)";
}

/** One line of "Not running (the faded blocks)", in words. */
export function looseText(l: Loose, scope: Scope): string {
  const more = l.count > 1 ? ` and ${l.count - 1} more block${l.count > 2 ? "s" : ""}` : "";
  const are = l.count > 1 ? "are" : "is";
  const does = l.count > 1 ? "they do" : "it does";
  if (l.value) return `“${l.words}” is not plugged into a block, so it is not used.`;
  if (scope.kind === "global") return `“${l.words}”${more} ${are} not inside a “when …” event, so ${does} not run.`;
  return `“${l.words}”${more} ${are} not attached to “${hatTitle(scope)}”, so ${does} not run.`;
}

/** How many blocks a stack holds (its top, the blocks after it and inside it). */
export function stackSize(b: WsBlock | undefined): number {
  let n = 0;
  for (let cur = b; cur; cur = cur.next?.block) {
    n++;
    for (const inp of Object.values(cur.inputs ?? {})) {
      const child = inp.block;
      if (child && DEF_BY_TYPE[child.type]?.output === undefined) n += stackSize(child); // statements only
    }
  }
  return n;
}

/** The tab a lint finding belongs to: its map block's, every map's (the global events), the
 * functions tab (a finding under a function: its node path starts with the function's name), or
 * the flow's own: main in a plain flow, else the START map's tab (2026-11-13, Batt: no Map tab on
 * /flows any more; the maps graph is the Maps page). */
export function tabOf(f: Pick<Finding, "owner"> & { path?: string }, plain: boolean, procs: readonly string[] = [], start: string | null = null): string {
  if (f.owner.startsWith("block:")) return f.owner;
  if (f.owner === "global") return "events";
  const root = (f.path ?? "").split(".", 1)[0].split(":", 1)[0];
  if (root && procs.includes(root)) return "functions";
  if (plain) return "main";
  return start ? `block:${start}` : "functions";
}

/** The lint ERRORS, for the problems list (warnings and readiness stay in the Lint pane). */
export function lintErrors(lint: LintDoc | null): Finding[] {
  return (lint?.findings ?? []).filter((f) => f.severity === "error");
}

export const PROBLEM_HEADS = {
  fix: "Fix before simulating:",
  lint: "Lint errors (Simulate still shows what would happen; a run is never approved with them):",
  loose: "Not running (the faded blocks):",
};

export type StatusIn = {
  loading: boolean;
  engine: string | null; // why the flow engine is unreachable
  issues: number; // blocks that cannot become the IR
  lintErrors: number;
  simulating: boolean;
  mapTab: boolean;
};

/** The footer's sentence: what to do next, never a live run. */
export function statusText(s: StatusIn): string {
  if (s.loading) return "Loading the block editor…";
  if (s.engine) return `The flow engine is not reachable (${s.engine}): the blocks still work; lint, Python and Simulate wait for it.`;
  if (s.issues) return "Fix the problems below to simulate the flow.";
  if (s.simulating) return "Simulating… (nothing runs in the game)";
  if (s.lintErrors) return `Lint found ${s.lintErrors} error${s.lintErrors > 1 ? "s" : ""}: press Simulate to see what would happen; a run is never approved with them.`;
  if (s.mapTab) return "Ready. Press Simulate (nothing here runs in the game).";
  return "Ready. Press Simulate to run the flow in the simulator (nothing here runs in the game).";
}
