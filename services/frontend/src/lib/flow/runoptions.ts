/**
 * The Run options (Batt 2026-11-19): ONE time limit for the whole Run, and what a Run does after a
 * code error (the retry). PURE: the page's Run options strip and the Logs tab build on these.
 *
 * Batt: "where did you set this? If I want to change it myself, make a UI." The time lived in two
 * places -- the project's run settings (max_runtime_s) and the hunt block `minutes` in a map
 * node's start tab -- so a Run stopped at the shorter one. The strip sets both at once: the
 * project's time, and every `minutes` block to 0 (the hunt core then follows the Run's time box:
 * flow_play gives it the time left).
 */
import type { Project } from "./project.ts";

/** The strip's choices, seconds; 0 = no time limit (ADR-0020 Amendment T). */
export const TIME_CHOICES = [0, 1_800, 3_600, 7_200, 14_400, 28_800, 43_200, 86_400, 172_800] as const;
/** The schema's sanity cap (ir.MAX_RUNTIME_S, 365 days). */
export const TIME_MAX_S = 31_536_000;

/** PURE: seconds in a person's words ("no time limit", "45 min", "2 h", "1 h 30 min", "2 days"). */
export function timeWords(s: number): string {
  if (!s) return "no time limit";
  const d = Math.floor(s / 86_400);
  const h = Math.floor((s % 86_400) / 3_600);
  const m = Math.round((s % 3_600) / 60);
  const parts = [d ? `${d} day${d === 1 ? "" : "s"}` : "", h ? `${h} h` : "", m ? `${m} min` : ""].filter(Boolean);
  return parts.length ? parts.join(" ") : `${s} s`;
}

/** PURE: every hunt block `minutes` the project sets to a number above 0: [where, minutes]. */
export function huntMinutes(p: Project): { where: string; minutes: number }[] {
  const out: { where: string; minutes: number }[] = [];
  for (const n of p.nodes) {
    for (const t of n.tabs) {
      const v = t.vars.minutes;
      if (v && v.kind === "lit" && typeof v.value === "number" && v.value > 0) out.push({ where: `${n.id}/${t.name}`, minutes: v.value });
    }
  }
  return out;
}

/** PURE: the time a Run of this project plays at most, in seconds (0 = none): the project's, or
 * a hunt block's shorter `minutes` (the hunt core stops there). */
export function effectiveLimitS(p: Project): number {
  const own = p.max_runtime_s;
  const hunt = huntMinutes(p).map((h) => h.minutes * 60);
  const all = [...(own ? [own] : []), ...hunt];
  return all.length ? Math.min(...all) : 0;
}

/** PURE: the project with ONE time limit: `secs` for the Run (0 = none) and every `minutes`
 * block at 0, so the hunt core follows the Run's time. A copy; the original is untouched. */
export function withTimeLimit(p: Project, secs: number): Project {
  if (!Number.isInteger(secs) || secs < 0 || secs > TIME_MAX_S) throw new Error(`a time limit is 0..${TIME_MAX_S} whole seconds`);
  return {
    ...p,
    max_runtime_s: secs,
    nodes: p.nodes.map((n) => ({
      ...n,
      tabs: n.tabs.map((t) => (t.vars.minutes && t.vars.minutes.kind === "lit" && t.vars.minutes.value !== 0 ? { ...t, vars: { ...t.vars, minutes: { kind: "lit", value: 0 } } } : t)),
    })) as Project["nodes"],
  };
}

/** PURE: a custom time typed as hours and minutes ("" = 0); null when it is not whole numbers. */
export function parseHoursMinutes(hours: string, minutes: string): number | null {
  const h = hours.trim() === "" ? 0 : Number(hours);
  const m = minutes.trim() === "" ? 0 : Number(minutes);
  if (!Number.isInteger(h) || !Number.isInteger(m) || h < 0 || m < 0 || m > 59) return null;
  const s = h * 3_600 + m * 60;
  return s <= TIME_MAX_S ? s : null;
}

/** The retry option as the backend serves it (GET /flows/run/options; poring_env.runoptions). */
export type RetryOptions = {
  retry_max: number;
  retry_wait_s: number;
  // econ-bag-count.md (Batt 2026-11-20): count the bag at the Run's start and end (the Economy)
  bag_count?: boolean;
  words: string;
  saved: boolean;
  bounds: { retry_max: [number, number]; retry_wait_s: [number, number] };
  defaults: { retry_max: number; retry_wait_s: number };
};
export const RETRY_CHOICES = [0, 1, 2, 3, 5, 10, 20] as const;
export const RETRY_WAIT_CHOICES = [10, 20, 30, 60, 120, 300] as const;

/** PURE: a story line's time ("m:ss" from the run's start, or "" before it). */
export function storyTime(t: number | null | undefined): string {
  if (t === null || t === undefined || t < 0) return "";
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}
