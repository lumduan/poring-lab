// The /hardware page (Batt, 2026-11-08): the backend's GET /hardware (poring_backend/hardware.py,
// its own REST model; not the WebSocket protocol) and the pure logic the page shows it with.
// Values are rendered as TEXT only. Times: `age_s` is on the backend's clock; the page adds only its
// OWN elapsed time since the fetch (browser clock), never a difference across the two clocks.

export interface Cpu {
  model: string | null;
  cores: number | null;
  busy_pct: number | null;
  core_pct: (number | null)[];
  core_mhz: (number | null)[];
  mhz_source: string | null;
  load: number[] | null;
}

export interface Memory {
  total_b: number | null;
  available_b: number | null;
  used_b: number | null;
  swap_total_b: number | null;
  swap_used_b: number | null;
  shmem_b: number | null;
}

export interface Filesystem {
  path: string;
  total_b: number;
  used_b: number;
  free_b: number;
  limit_b: number | null;
}

export interface Gpu {
  vendor: string;
  driver: string;
  card: string;
  pci_id: string | null;
  name: string | null;
  temp_c: number | null;
  power_w: number | null;
  power_max_w: number | null;
  fan_rpm: number | null;
  freq_act_mhz: number | null;
  freq_cur_mhz: number | null;
  freq_max_mhz: number | null;
  busy_pct: number | null;
  vram_used_b: number | null;
  vram_total_b: number | null;
}

export interface Temp {
  chip: string;
  label: string;
  c: number;
  max_c: number | null;
  crit_c: number | null;
}

export interface Power {
  server_w: number | null;
  server_avg_s: number | null;
  gpu_w: number | null;
  gpu_max_w: number | null;
  cpu_pkg_w: number | null;
}

export interface Sample {
  seq: number;
  t_mono_ns: number;
  t_wall: number;
  read_ms: number;
  cpu: Cpu;
  memory: Memory;
  shm: Filesystem | null;
  disk: Filesystem | null;
  gpu: Gpu | null;
  temps: Temp[];
  power: Power;
  na: Record<string, string>;
}

export type SeriesName =
  | "cpu_pct"
  | "mem_pct"
  | "gpu_busy_pct"
  | "cpu_temp_c"
  | "gpu_temp_c"
  | "server_w"
  | "gpu_w";

export interface History {
  t_s: number[]; // seconds relative to the newest sample (<= 0)
  series: Partial<Record<SeriesName, (number | null)[]>>;
}

export interface HardwareView {
  t_mono_ns: number;
  period_s: number;
  history_len: number;
  age_s: number | null;
  current: Sample | null;
  history: History;
}

export const POLL_MS = 2000;
export const STALE_S = 6; // a sample older than this is marked stale
export const WINDOW_S = 600; // the sparklines' 10 minutes

export type Tone = "ok" | "warn" | "crit";

/** "n/a: <the backend's reason>" for a null sensor ("n/a" when it gave none). */
export function naText(sample: Sample | null, ...keys: string[]): string {
  for (const key of keys) {
    const reason = sample?.na[key];
    if (reason) return `n/a: ${reason}`;
  }
  return "n/a";
}

const finite = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);

export function fmtPct(v: number | null | undefined, digits = 1): string | null {
  return finite(v) ? `${v.toFixed(digits)} %` : null;
}

/** Binary units, as `free -h` shows memory. */
export function fmtGiB(bytes: number | null | undefined): string | null {
  return finite(bytes) ? `${(bytes / 2 ** 30).toFixed(1)} GiB` : null;
}

/** Decimal units, as the lab's disk floors and rule 7's /dev/shm limit are stated. */
export function fmtGB(bytes: number | null | undefined, digits = 1): string | null {
  return finite(bytes) ? `${(bytes / 1e9).toFixed(digits)} GB` : null;
}

export function fmtW(v: number | null | undefined): string | null {
  return finite(v) ? `${v.toFixed(1)} W` : null;
}

export function fmtC(v: number | null | undefined): string | null {
  return finite(v) ? `${v.toFixed(0)} °C` : null;
}

export function fmtMHz(v: number | null | undefined): string | null {
  return finite(v) ? `${Math.round(v)} MHz` : null;
}

/** The sample's wall time in this browser's locale and zone (display only: `t_wall` is never
 * compared with this tab's clock). */
export function fmtWallTime(tWall: number | null | undefined): string | null {
  return finite(tWall) ? new Date(tWall * 1000).toLocaleTimeString() : null;
}

/** A share of a whole, or null when either part is missing (or the whole is 0). */
export function share(part: number | null | undefined, whole: number | null | undefined): number | null {
  return finite(part) && finite(whole) && whole > 0 ? (100 * part) / whole : null;
}

/** How old the shown sample is now: its age when fetched (backend clock) plus the time since the
 * fetch (this tab's clock). Null before the first answer or the first sample. */
export function staleAgeS(ageS: number | null, fetchedAtMs: number | null, nowMs: number): number | null {
  if (ageS == null || fetchedAtMs == null) return null;
  return ageS + Math.max(0, nowMs - fetchedAtMs) / 1000;
}

export function isStale(age: number | null): boolean {
  return age == null || age > STALE_S;
}

/** A temperature against its own limits: crit at or over crit, warn at or over max (or within
 * 10 °C of crit when the chip states no max). */
export function tempTone(c: number, maxC: number | null, critC: number | null): Tone {
  if (critC != null && c >= critC) return "crit";
  if (maxC != null ? c >= maxC : critC != null && c >= critC - 10) return "warn";
  return "ok";
}

/** A use against a limit (rule 7's /dev/shm 4 GB, the GPU's power limit): warn from 75 %. */
export function limitTone(used: number | null, limit: number | null): Tone {
  const pct = share(used, limit);
  if (pct == null) return "ok";
  if (pct >= 100) return "crit";
  return pct >= 75 ? "warn" : "ok";
}

export const TONE_WORD: Record<Tone, string> = { ok: "", warn: "high", crit: "over limit" };

/** The temperatures grouped by chip, in the backend's order (coretemp's package first). */
export function groupTemps(temps: Temp[]): { chip: string; items: Temp[] }[] {
  const groups: { chip: string; items: Temp[] }[] = [];
  for (const t of temps) {
    const last = groups.at(-1);
    if (last && last.chip === t.chip) last.items.push(t);
    else groups.push({ chip: t.chip, items: [t] });
  }
  return groups;
}

export interface SparkOpts {
  width: number;
  height: number;
  windowS?: number;
  min?: number; // fixed bounds (0..100 for a percentage); else from the data
  max?: number;
}

/** Bounds for a series: the fixed ones, else the data's (padded when flat), else 0..1. */
export function sparkRange(values: (number | null)[], opts: Pick<SparkOpts, "min" | "max">): [number, number] {
  const data = values.filter(finite);
  let lo = opts.min ?? (data.length ? Math.min(...data) : 0);
  let hi = opts.max ?? (data.length ? Math.max(...data) : 1);
  if (hi <= lo) {
    const pad = Math.max(1, Math.abs(hi) * 0.05);
    if (opts.min == null) lo -= pad;
    if (opts.max == null) hi += pad;
    if (hi <= lo) hi = lo + 1;
  }
  return [lo, hi];
}

const r1 = (v: number): number => Math.round(v * 10) / 10;

export interface SparkPoint {
  x: number;
  y: number;
  move: boolean; // starts a segment (the first point, or the first after a gap)
}

/** A sparkline's points: x by time over the window (the newest sample at the right edge), y by
 * value; a null starts a new segment, so a gap stays a gap. Points older than the window are left
 * out; values beyond fixed bounds are clamped to them. */
export function sparkPoints(t: number[], values: (number | null)[], opts: SparkOpts): SparkPoint[] {
  const windowS = opts.windowS ?? WINDOW_S;
  const [lo, hi] = sparkRange(values, opts);
  const points: SparkPoint[] = [];
  let pen = false;
  const n = Math.min(t.length, values.length);
  for (let i = 0; i < n; i++) {
    const v = values[i];
    const ts = t[i];
    if (!finite(v) || !finite(ts) || ts < -windowS) {
      pen = false;
      continue;
    }
    const clamped = Math.min(hi, Math.max(lo, v));
    points.push({
      x: r1(opts.width * (1 + ts / windowS)),
      y: r1(opts.height - ((clamped - lo) / (hi - lo)) * opts.height),
      move: !pen,
    });
    pen = true;
  }
  return points;
}

/** The SVG path `d` of sparkPoints. */
export function sparkPath(t: number[], values: (number | null)[], opts: SparkOpts): string {
  return sparkPoints(t, values, opts)
    .map((p) => `${p.move ? "M" : "L"}${p.x} ${p.y}`)
    .join(" ");
}

/** "last 10 min: min 3.2, max 41.0" (the sparkline's accessible name), or a no-data note. */
export function sparkSummary(values: (number | null)[], unit: string): string {
  const data = values.filter(finite);
  if (!data.length) return "no history yet";
  const f = (v: number) => `${v.toFixed(1)}${unit}`;
  return `last ${Math.round(WINDOW_S / 60)} min: min ${f(Math.min(...data))}, max ${f(Math.max(...data))}`;
}
