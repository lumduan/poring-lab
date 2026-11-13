// The /flows page's calls to the backend's flow engine (services/backend routes_flows.py):
// COMPUTATION ONLY. Lint, simulate and the Python view take the IR and return documents; nothing
// here reaches the mux, the executor or any agent channel. POSTs carry the console's CSRF token
// (GET /settings/csrf, as the Settings page), fetched once and renewed on `csrf_invalid`.
import type { HuntRules } from "./hunt.ts";
import type { Flow } from "./ir.ts";
import type { Project } from "./project.ts";
import type { Models } from "./models.ts";
import type { ZonesCheck, ZonesFile } from "./zones.ts";

// "readiness" (Batt 2026-10-09, ADR-0020 contradictions #6): a binding not there YET for the target
// environment. Listed apart from errors: it blocks the RUN (the run-start check), not the design.
export type Severity = "error" | "readiness" | "warning" | "info";
export type Badge = "verified_rdp_s2" | "verified_rdp" | "verified_s2" | "unverified" | "unknown" | "core";
export type WorldSource = "local" | "sample";

export interface Finding {
  rule: string;
  severity: Severity;
  layer: number;
  path: string;
  text: string;
  message: string;
  ack: boolean;
  owner?: string; // IR 2's (block:<name> | global | flow); the project's findings name node and tab
  /** The project model (2026-11-13): the node and the tab a finding is on ("" = the project). */
  node?: string;
  tab?: string;
}

/** A node's (or IR 2 owner's) counts, whichever the lint carries; none -> undefined. */
export function countsFor(lint: Pick<LintDoc, "by_owner" | "by_node"> | null | undefined, id: string): Record<Severity, number> | undefined {
  return lint?.by_node?.[id] ?? lint?.by_owner?.[id];
}

/** A finding's statement path INSIDE its tab ("main.2", "heal.0"), from "<node>/<tab>/<site>". */
export function sitePath(f: Pick<Finding, "path" | "node" | "tab">): string {
  const pre = f.node && f.tab ? `${f.node}/${f.tab}/` : "";
  return pre && f.path.startsWith(pre) ? f.path.slice(pre.length) : f.path;
}

export interface EffectiveEvent {
  key: string;
  state: "built_in" | "inherited" | "overridden" | "extended" | "disabled" | "added";
  priority: string;
  rank: number; // the effective rank inside the class (IR 2, ADR-0020 #13)
  mode: string;
  label: string;
  active: boolean;
  safety_critical: boolean;
  built_in: boolean; // the engine's always-on definition (ADR-0020 contradictions #15)
  extension: string | null;
}

export interface LintDoc {
  flow_hash?: string;
  project_hash?: string;
  findings: Finding[];
  counts: Record<Severity, number>;
  /** IR 2's counts per canvas node; ABSENT on the project model's lint, which has `by_node` (per
   * node id). Read them through countsFor (matpilot round 15: /maps crashed on the missing key). */
  by_owner?: Record<string, Record<Severity, number>>;
  by_node?: Record<string, Record<Severity, number>>;
  run: { allowed: boolean; summary: string; reasons: string[] }; // the run-start check's verdict (MW3)
  effective: Record<string, EffectiveEvent[]>;
  world: { server: string | null; maps: string[] };
  world_notes?: string[]; // how the static data was found (e.g. no GAT here: routes are estimates)
}

export interface NodeRun {
  runs: number;
  total_s: number;
  first_t: number | null;
  last_t: number;
  last: string;
  outcomes: Record<string, number>;
}

export interface Transition {
  t: number;
  kind: "walk_exit" | "npc_warp" | "item_warp" | "death_respawn";
  from: string;
  to: string;
  entry: string | null;
  arrived: boolean;
  map: string | null;
  s: number;
}

export interface PathSegment {
  map: string;
  node: string;
  cells: [number, number][];
  estimated: boolean;
  count: number;
  t: number;
}

/** One step of the run in order (poring_flow.trace's `play`, 2026-11-10; the Maps page animates
 * it). Keys only: the page shows names from the static data. Absent on an older backend. */
export interface PlayStep {
  kind: "walk" | "talk" | "menu" | "fight" | "item" | "loot" | "respawn" | "act" | "wait" | "exit" | "arrive";
  t0: number;
  t1: number;
  block: string | null;
  map: string | null;
  node?: string;
  action?: string;
  outcome?: string;
  cells?: [number, number][];
  estimated?: boolean;
  trimmed?: boolean;
  purpose?: "walk" | "npc" | "engage" | "exit";
  npc?: string | null;
  at?: [number, number] | null;
  options?: string[];
  option?: string | null;
  mob?: number | null;
  seen_t?: number;
  loot?: boolean;
  item?: number | null;
  item_kind?: string | null;
  /** an item warp by a FUNCTION (2026-11-13): the function, and the key its press_key presses */
  proc?: string | null;
  key?: string | null;
  exit?: "walk_exit" | "npc_warp" | "item_warp";
  from_block?: string | null;
  to_block?: string;
  to_entry?: string;
  to_map?: string | null;
  cell?: [number, number] | null;
  arrived?: boolean;
  warp?: [number, number] | null;
  via?: string;
}

export interface Trace {
  end: string;
  t_end_s: number;
  start: { block: string | null; entry: string | null; map: string | null; cell: [number, number] | null };
  final: { block: string | null; map: string | null; cell: [number, number] | null; hp_percent: number | null; weight_percent: number | null };
  save_point: { map: string; cell: [number, number] } | null;
  nodes: Record<string, NodeRun>;
  blocks: Record<string, { visits: number; time_s: number }>;
  transitions: Transition[];
  paths: PathSegment[];
  events: { t: number; kind: string; what: string }[];
  events_capped: boolean;
  input_batches_counted: number;
  // ADR-0020 #10: every /where read (it types) with its reason, against the flow's budget
  where: { count: number; budget: number; over: boolean; reads: { t: number; reason: string }[] };
  notes: string[];
  play?: PlayStep[]; // the run in order (absent before 2026-11-10's backend)
  play_capped?: boolean;
  scenario: Scenario;
  world: { server: string | null; maps: string[] };
}

export interface Scenario {
  start_block?: string | null;
  start_entry?: string | null;
  single_block?: boolean;
  horizon_s?: number;
  hp_percent?: number;
  sp_percent?: number;
  weight_percent?: number;
  weight_per_attack?: number;
  hp_per_attack?: number;
  attack_s?: number;
  // detects: "<model>/<class>" -> how many boxes the trained model finds from t on (ADR-0020
  // Amendment B; before any entry: 0)
  timeline?: { t: number; set?: Record<string, number | boolean>; sees?: Record<string, boolean>; detects?: Record<string, number> }[];
  // the Maps page (2026-11-10): a monster placed for each attack, repeatable by the seed
  encounters?: boolean;
  seed?: number;
}

export interface SimDoc {
  flow_hash?: string;
  project_hash?: string;
  trace: Trace;
  lint: LintDoc;
}

export interface CatalogueBlockDoc {
  name: string;
  spec: {
    concept: string;
    kind: string;
    timeout_s: number;
    // group / choices: a parameter that picks a RULE VERSION (the hunt block, Amendment A 1);
    // options / default / note: an OPTION parameter, plain values, absent = default (engage_source)
    params: {
      name: string;
      type: string;
      required: boolean;
      group?: string | null;
      choices?: string[];
      options?: string[];
      default?: string | null;
      note?: string | null;
    }[];
    note?: string | null;
    /** the LIVE BLOCK PLAYER plays it in the game (docs/planning/live-blocks.md stage 1; the
     * feat/live-player branch adds it): absent = not live (Run is greyed with the reason) */
    live?: boolean;
  };
  status: string;
  badge: Badge;
  purpose: string | null;
  verified_on: { path: string; server: string; rule: string; date: string }[];
}

export interface CatalogueDoc {
  version: number;
  blocks: Record<string, CatalogueBlockDoc>;
  sensors: Record<string, { name: string; badge: Badge; spec: { type: string; passive: boolean } }>;
  palette: string[];
  windows: string[];
  safety_critical: string[];
  // ADR-0020 #17: the CONFIGURED run-time limits (the backend's flows_settings.runtime_limits)
  runtime_limits?: { default_s: number; max_s: number };
  // B2: the hunt block's groups, rule versions and badges (config/flows/hunt; null when unread)
  hunt_rules?: HuntRules | null;
  hunt_rules_error?: string | null;
  // the trained models a detector block may name (poring_flow models.yaml; 2026-11-09)
  models?: Models;
  // the project model (2026-11-13): the maps that have a runner, the lab's credentials by name, and
  // the engine's tab-name rule (the browser refuses the same names at once)
  runner_maps?: string[];
  credentials?: string[];
  tab_name_rule?: { pattern: string; refused: string[] };
}

/** The Python view of a project: one file per tab. */
export interface PythonFiles {
  project_hash?: string;
  files: { node: string; tab: string; path: string; text: string }[];
}

export interface WorldMap {
  town: boolean;
  size: [number, number] | null;
  npcs: { key: string; x: number; y: number; menu: string[]; kafra: { services: string[]; save_cell: [number, number] | null } | null }[];
  warps: { x: number; y: number; to_map: string; to_x: number; to_y: number }[];
  spawns: { mob: number; count: number; boss: boolean; area?: [number, number, number, number] | null }[];
}

export interface WorldDoc {
  server: string;
  maps: Record<string, WorldMap>;
  mobs: Record<string, { label: string | null; level: number }>;
  items: Record<string, { label: string | null; kind: string }>;
  walk?: Record<string, string[]>;
  labels?: { npcs: Record<string, string>; options: Record<string, string> }; // display only
  notes?: string[];
}

export class ApiError extends Error {
  reason: string;
  errors: string[];
  status: number;
  constructor(status: number, reason: string, errors: string[] = []) {
    super(errors.length ? `${reason}: ${errors.join("; ")}` : reason);
    this.status = status;
    this.reason = reason;
    this.errors = errors;
  }
}

async function errorOf(r: Response): Promise<ApiError> {
  try {
    const body = (await r.json()) as { detail?: { reason?: string; errors?: string[] } };
    return new ApiError(r.status, body.detail?.reason ?? `http_${r.status}`, body.detail?.errors ?? []);
  } catch {
    return new ApiError(r.status, `http_${r.status}`);
  }
}

export class FlowsApi {
  private base: string;
  private csrf: string | null = null;

  constructor(base: string) {
    this.base = base.replace(/\/+$/, "");
  }

  private async get<T>(path: string): Promise<T> {
    const r = await fetch(`${this.base}${path}`, { cache: "no-store" });
    if (!r.ok) throw await errorOf(r);
    return (await r.json()) as T;
  }

  private async token(): Promise<string> {
    if (this.csrf === null) {
      const r = await fetch(`${this.base}/settings/csrf`, { cache: "no-store" });
      if (!r.ok) throw await errorOf(r);
      this.csrf = ((await r.json()) as { token: string }).token;
    }
    return this.csrf;
  }

  private async post<T>(path: string, body: unknown, retry = true): Promise<T> {
    const r = await fetch(`${this.base}${path}`, {
      method: "POST",
      cache: "no-store",
      headers: { "content-type": "application/json", "x-csrf-token": await this.token() },
      body: JSON.stringify(body),
    });
    if (r.ok) return (await r.json()) as T;
    const err = await errorOf(r);
    if (retry && err.reason === "csrf_invalid") {
      this.csrf = null;
      return this.post<T>(path, body, false);
    }
    throw err;
  }

  catalogue(client: string): Promise<CatalogueDoc> {
    return this.get(`/flows/catalogue?client=${encodeURIComponent(client)}`);
  }

  sample(): Promise<{ flow: Flow; flow_hash: string; world: WorldSource }> {
    return this.get("/flows/sample");
  }

  world(source: WorldSource, server: string, maps: string[], walk = false): Promise<WorldDoc> {
    const q = new URLSearchParams({ source, server, maps: maps.join(","), walk: String(walk) });
    return this.get(`/flows/world?${q}`);
  }

  lint(project: Project, world: WorldSource): Promise<LintDoc> {
    return this.post("/flows/lint", { project, world });
  }

  simulate(project: Project, world: WorldSource, scenario: Scenario): Promise<SimDoc> {
    return this.post("/flows/simulate", { project, world, scenario });
  }

  python(project: Project): Promise<PythonFiles> {
    return this.post("/flows/python", { project });
  }

  /** B2: config/map_zones/<map>.yaml as the editor imports it (never its reviewer). */
  zonesFile(map: string, source: WorldSource, server: string): Promise<ZonesFile> {
    const q = new URLSearchParams({ map, source, server });
    return this.get(`/flows/zones/file?${q}`);
  }

  /** B2: the runner's zones loader on the editor's YAML text (checked, never written: D6). */
  zonesCheck(map: string, yaml: string, world: WorldSource, server: string): Promise<ZonesCheck> {
    return this.post("/flows/zones/check", { map, yaml, world, server });
  }
}

export const BADGE_TEXT: Record<Badge, string> = {
  verified_rdp_s2: "verified RDP + S2",
  verified_rdp: "verified RDP",
  verified_s2: "verified S2",
  unverified: "unverified",
  unknown: "unknown",
  core: "core",
};
