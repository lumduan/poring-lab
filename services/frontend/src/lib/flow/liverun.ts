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
  // matpilot's player test 2026-11-13: what she does while she plays, and the end in plain words
  live?: LiveSummary | null;
  end_png?: string | null; // set (the end time) when the last run left an end picture
  config?: Record<string, unknown> | null; // the values this run took
};
export type LiveSummary = {
  hp: number | null;
  hp_low: number | null;
  pos: number[] | null;
  doing: string;
  block: string | null; // the block to highlight (the export's id)
  elapsed_s: number | null;
  kills: number;
  loot_steps: number;
  pickups: number;
  knife: number;
  steals: number;
  potions: number;
  flies: number;
  end: { reason?: string; home?: boolean; dead?: boolean; respawned?: boolean };
};

/** PURE: the live line while she plays: HP, what she does, the counts, the time (of the time box). */
export function liveLine(l: LiveSummary | null | undefined, minutes: number | null): string | null {
  if (!l) return null;
  const t = l.elapsed_s ?? 0;
  const mm = `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
  const parts = [
    l.hp !== null ? `HP ${l.hp} %` : null,
    l.doing,
    `${l.kills} kill${l.kills === 1 ? "" : "s"}`,
    `${l.loot_steps} loot step${l.loot_steps === 1 ? "" : "s"}`,
    l.knife ? `${l.knife} Knife swaps (${l.steals} steals)` : null,
    l.potions ? `${l.potions} potions` : null,
    l.flies ? `${l.flies} Fly Wings` : null,
    minutes ? `${mm} of ${minutes} min` : mm,
  ];
  return parts.filter(Boolean).join(" · ");
}

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
  config_file_broken: "The settings file on the bot server cannot be read: a person looks at settings/flowrun/config.json first.",
  config_refused: "Not saved: that value cannot run.",
  config_engine_unavailable: "The bot server cannot read its settings list (scripts/flow_config.py) here.",
};
