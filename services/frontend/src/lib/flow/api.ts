// The /flows page's calls to the backend's flow engine (services/backend routes_flows.py):
// COMPUTATION ONLY. Lint, simulate and the Python view take the IR and return documents; nothing
// here reaches the mux, the executor or any agent channel. POSTs carry the console's CSRF token
// (GET /settings/csrf, as the Settings page), fetched once and renewed on `csrf_invalid`.
import type { Flow } from "./ir.ts";

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
  owner: string; // block:<name> | global | flow
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
  flow_hash: string;
  findings: Finding[];
  counts: Record<Severity, number>;
  by_owner: Record<string, Record<Severity, number>>;
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
  notes: string[];
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
  timeline?: { t: number; set?: Record<string, number | boolean>; sees?: Record<string, boolean> }[];
}

export interface SimDoc {
  flow_hash: string;
  trace: Trace;
  lint: LintDoc;
}

export interface CatalogueBlockDoc {
  name: string;
  spec: { concept: string; kind: string; timeout_s: number; params: { name: string; type: string; required: boolean }[]; note?: string | null };
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
}

export interface WorldMap {
  town: boolean;
  size: [number, number] | null;
  npcs: { key: string; x: number; y: number; menu: string[]; kafra: { services: string[]; save_cell: [number, number] | null } | null }[];
  warps: { x: number; y: number; to_map: string; to_x: number; to_y: number }[];
  spawns: { mob: number; count: number; boss: boolean }[];
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

  lint(flow: Flow, world: WorldSource): Promise<LintDoc> {
    return this.post("/flows/lint", { flow, world });
  }

  simulate(flow: Flow, world: WorldSource, scenario: Scenario): Promise<SimDoc> {
    return this.post("/flows/simulate", { flow, world, scenario });
  }

  python(flow: Flow): Promise<{ flow_hash: string; python: string }> {
    return this.post("/flows/python", { flow });
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
