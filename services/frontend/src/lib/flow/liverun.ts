// The /flows Run button (Batt 2026-11-13: "I put the bot on the map, press run, and it plays by
// itself"): the page's side of GET / POST /flows/run (routes_flowrun.py). The backend only passes a
// request to the host helper (scripts/flow_run.py), which runs the proven runner in player mode;
// these helpers decide which buttons a status allows and how it reads. Pure, tested.

export type LiveState = "no_helper" | "idle" | "starting" | "running" | "stopping" | "ended" | "failed" | "refused";

export type LiveStatus = {
  state: LiveState | string;
  helper_alive: boolean;
  detail?: string;
  flow?: string | null;
  label?: string | null;
  started?: string | null;
  ended?: string | null;
  rc?: number | null;
  log_tail?: string[];
  flows?: Record<string, { title: string; minutes: number }>;
  mode?: string;
};

export const ACTIVE: readonly string[] = ["starting", "running", "stopping"];

export type LiveButtons = { canStart: boolean; canStop: boolean; why: string | null };

/** Which buttons the status allows for `flow`, and why Start is off (the backend refuses the same). */
export function liveButtons(st: LiveStatus | null, flow: string): LiveButtons {
  if (st === null) return { canStart: false, canStop: false, why: "reading the Run helper…" };
  if (!st.helper_alive) return { canStart: false, canStop: false, why: st.detail || "the Run helper is not running on the bot server" };
  const active = ACTIVE.includes(st.state);
  if (active) return { canStart: false, canStop: st.state !== "stopping", why: null };
  if (!st.flows || !(flow in st.flows)) return { canStart: false, canStop: false, why: "the Run helper does not list this flow" };
  if (st.mode !== "ASSIST") return { canStart: false, canStop: false, why: "set the console to ASSIST first (the bot never takes over in HUMAN)" };
  return { canStart: true, canStop: false, why: null };
}

const WORDS: Record<string, string> = {
  no_helper: "the Run helper is not running",
  idle: "ready",
  starting: "starting…",
  running: "playing in the game",
  stopping: "stopping…",
  ended: "ended",
  failed: "failed",
  refused: "refused",
};

/** One line for the status pill. */
export function liveLabel(st: LiveStatus | null): string {
  if (st === null) return "…";
  if (!st.helper_alive) return WORDS.no_helper;
  return WORDS[st.state] ?? st.state;
}

/** The page's words for a refusal reason of POST /flows/run. */
export const REFUSALS: Record<string, string> = {
  helper_not_running: "The Run helper on the bot server is not running.",
  nothing_running: "Nothing is running.",
  unknown_flow: "The Run helper does not list this flow.",
  already_running: "A run is already going: press Stop first.",
  mode_not_assist: "Set the console to ASSIST first.",
  csrf_invalid: "The page's security token expired: reload the page and try again.",
  origin_required: "Open the console from its own address to use Run.",
  lab_host_peer: "Run is refused from the bot server itself: use your own browser on the LAN.",
  rate_limited: "Too many requests: wait a moment.",
  settings_same_key: "Two of your run settings use the same hotbar key: each one needs its own key.",
  settings_off_picture: "The respawn button's point must lie inside the 1280 x 720 game picture.",
  survival_file_broken: "The survival file on the bot server cannot be read: a person looks at settings/flowrun/survival.json first.",
  survival_map_missing: "Which map's numbers? (no map was named)",
};
