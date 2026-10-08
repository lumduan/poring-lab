// Importing a flow file: HOSTILE input (ADR-0020 7.1). Checked here before anything parses it —
// size, nesting depth (a linear scan, as MW1's ir._depth), JSON, the top-level shape — and then the
// backend's /flows/lint validates it against MW1's schema. Nothing is evaluated.
import type { Flow } from "./ir.ts";
import { FLOW_NAME, MAX_JSON_BYTES, MAX_JSON_DEPTH } from "./ir.ts";

export type ImportResult = { ok: true; flow: Flow } | { ok: false; errors: string[] };

/** The bracket depth of a JSON text, outside strings (linear; before JSON.parse ever runs). */
export function jsonDepth(text: string): number {
  let depth = 0;
  let deepest = 0;
  let inStr = false;
  let esc = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inStr) {
      if (esc) esc = false;
      else if (ch === "\\") esc = true;
      else if (ch === '"') inStr = false;
    } else if (ch === '"') inStr = true;
    else if (ch === "[" || ch === "{") {
      depth++;
      if (depth > deepest) deepest = depth;
    } else if (ch === "]" || ch === "}") depth--;
  }
  return deepest;
}

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);

export function importFlow(text: string): ImportResult {
  const bytes = new TextEncoder().encode(text).length;
  if (bytes > MAX_JSON_BYTES) return { ok: false, errors: [`the file is ${bytes} bytes; at most ${MAX_JSON_BYTES}`] };
  if (jsonDepth(text) > MAX_JSON_DEPTH) return { ok: false, errors: [`nested deeper than ${MAX_JSON_DEPTH}`] };
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return { ok: false, errors: ["not JSON"] };
  }
  const errors: string[] = [];
  if (!isObj(data)) return { ok: false, errors: ["a flow is a JSON object"] };
  if (data.ir !== 1) errors.push("ir: only IR version 1 is supported");
  if (typeof data.name !== "string" || !FLOW_NAME.test(data.name)) errors.push("name: lower-case letters, digits and _");
  if (!isObj(data.target)) errors.push("target: missing");
  const hasMain = Array.isArray(data.main);
  const hasWf = isObj(data.workflow);
  if (hasMain === hasWf) errors.push("a flow has exactly one of main and workflow");
  if (hasWf && !Array.isArray((data.workflow as Record<string, unknown>).blocks)) errors.push("workflow.blocks: missing");
  if (data.handlers !== undefined && !Array.isArray(data.handlers)) errors.push("handlers: a list");
  if (errors.length) return { ok: false, errors };
  return { ok: true, flow: data as Flow };
}

/** The export file: the canonical IR, pretty-printed (key order as MW1's canonical JSON). */
export function exportText(flow: Flow): string {
  return JSON.stringify(sorted(flow), null, 2) + "\n";
}

function sorted(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(sorted);
  if (isObj(v)) return Object.fromEntries(Object.keys(v).sort().map((k) => [k, sorted(v[k])]));
  return v;
}
