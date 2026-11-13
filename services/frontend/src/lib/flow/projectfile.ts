// A PROJECT FILE (format 3; docs/planning/project-model.md): reading one is reading HOSTILE input
// (a dropped file, a GitHub file, this browser's storage), so the caps come first (size, depth),
// then the shape a page needs to show it. The flow engine validates it fully at the next lint.
// IR 2 flow files are not converted (Batt 2026-11-13: "refactor fresh"): they are refused with
// words that say so.
import { MAX_JSON_BYTES, MAX_JSON_DEPTH } from "./ir.ts";
import { jsonDepth } from "./importer.ts";
import { GLOBAL_ID, MAIN_TAB, PROJECT_FORMAT, PROJECT_VERSION, type Project } from "./project.ts";

export type ProjectImport = { ok: true; project: Project } | { ok: false; errors: string[] };

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const KINDS = ["login", "character", "map", "global"];
const ID = /^[A-Za-z][A-Za-z0-9_]{0,47}$/;

export function importProject(text: string): ProjectImport {
  const bytes = new TextEncoder().encode(text).length;
  if (bytes > MAX_JSON_BYTES) return { ok: false, errors: [`the file is ${bytes} bytes; at most ${MAX_JSON_BYTES}`] };
  if (jsonDepth(text) > MAX_JSON_DEPTH) return { ok: false, errors: [`nested deeper than ${MAX_JSON_DEPTH}`] };
  let v: unknown;
  try {
    v = JSON.parse(text);
  } catch {
    return { ok: false, errors: ["not JSON"] };
  }
  if (!isObj(v)) return { ok: false, errors: ["a project is a JSON object"] };
  if ("ir" in v && !("format" in v)) return { ok: false, errors: ["this is a flow of the OLD format (IR 2): the pages now read projects (nodes and tabs, format 3), and old flows are not converted"] };
  const errors: string[] = [];
  if (v.format !== PROJECT_FORMAT || v.version !== PROJECT_VERSION) errors.push(`not a project of format ${PROJECT_VERSION} ("format": "${PROJECT_FORMAT}", "version": ${PROJECT_VERSION})`);
  if (typeof v.name !== "string" || !/^[a-z][a-z0-9_]{0,47}$/.test(v.name)) errors.push("name: lower-case letters, digits and _");
  if (!Array.isArray(v.nodes) || !v.nodes.length) errors.push("nodes: at least one");
  if (!Array.isArray(v.edges)) errors.push("edges: a list");
  const ids = new Set<string>();
  let globals = 0;
  for (const [i, n] of (Array.isArray(v.nodes) ? v.nodes : []).entries()) {
    if (!isObj(n) || typeof n.id !== "string" || !ID.test(n.id) || !KINDS.includes(String(n.kind)) || !Array.isArray(n.tabs)) {
      errors.push(`nodes[${i}]: an id, a kind (login / character / map / global) and tabs`);
      continue;
    }
    if (ids.has(n.id)) errors.push(`nodes[${i}]: the id ${n.id} is there twice`);
    ids.add(n.id);
    if (n.kind === "global") {
      globals++;
      if (n.id !== GLOBAL_ID) errors.push(`nodes[${i}]: the Global node's id is "${GLOBAL_ID}"`);
    }
    const tabs = n.tabs as unknown[];
    const main = tabs.filter((t) => isObj(t) && t.name === MAIN_TAB);
    if (n.kind === "global" ? main.length : main.length !== 1) errors.push(`node ${n.id}: ${n.kind === "global" ? "Global has no main tab" : "exactly one main tab"}`);
    for (const t of tabs) if (!isObj(t) || typeof t.name !== "string" || !Array.isArray(t.defs) || !isObj(t.vars)) errors.push(`node ${n.id}: a tab has a name, defs and vars`);
  }
  if (globals > 1) errors.push("at most one Global node");
  if (typeof v.start !== "string" || !ids.has(v.start)) errors.push("start: a node's id");
  if (errors.length) return { ok: false, errors: errors.slice(0, 20) };
  return { ok: true, project: v as unknown as Project };
}

/** The file's text: pretty JSON (the engine's canonical form is its hash, not the file's). */
export function exportProject(p: Project): string {
  return `${JSON.stringify(p, null, 2)}\n`;
}
