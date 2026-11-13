// The runner flows /flows can show (lib/flow/runner.ts): each a GENERATED description of a live
// runner (scripts/runner_flow_export.py). `?runner=<id or map>` opens one.
import type { RunnerDoc } from "../runner.ts";
import { XMAS_DUN02_ROGUE } from "./xmas_dun02_rogue.gen.ts";

export const RUNNERS: readonly RunnerDoc[] = [XMAS_DUN02_ROGUE];
/** The runner flows the Run helper can start (scripts/flow_run.py's FLOWS; 2026-11-13). */
export const LIVE_FLOWS: readonly string[] = ["xmas_dun02_rogue"];

/** A runner flow by its id, else the first one on that map; null when there is none. */
export function findRunner(key: string | null | undefined): RunnerDoc | null {
  if (!key) return null;
  return RUNNERS.find((r) => r.id === key) ?? RUNNERS.find((r) => r.map === key) ?? null;
}

/** The runner flow of a map (the Maps page's and the studio's "how the bot hunts here"). */
export const runnerForMap = (map: string | null | undefined): RunnerDoc | null => (map ? (RUNNERS.find((r) => r.map === map) ?? null) : null);

/** The /flows link that opens a runner flow: by its map's name while that names one flow
 * (Batt 2026-11-13: "name it after the map"), else by its id. */
export const runnerHref = (r: RunnerDoc) => `/flows?runner=${encodeURIComponent(RUNNERS.filter((x) => x.map === r.map).length === 1 ? r.map : r.id)}`;
