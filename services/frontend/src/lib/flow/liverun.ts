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
  keys_src?: string | null; // the run's keys: "the flow's functions" or "the settings"
  check?: LiveCheck | null; // dungeon@9.45: the last check of the game screen
};

/** One line of the live check (scripts/dungeon_hunt.py check_item): ok true / false / null (not
 * read), its words, the value read, and whether the runner's own start refuses on it. */
export type CheckItem = { id: string; ok: boolean | null; words: string; value: string | null; refuses?: boolean };
/** The last check (the Run helper's status "check"; Batt 2026-11-13 "do it": the start checklist
 * ticked from the game screen, read only). */
export type LiveCheck = {
  state: "checking" | "done" | "refused" | "failed" | "timeout" | "cancelled" | string;
  at: string; // ISO time
  flow: string;
  items: CheckItem[];
  ok: boolean | null;
  refuses?: boolean;
  detail?: string;
  keys_src?: string;
  keys?: Record<string, string | null>;
  used?: Record<string, unknown>; // the values the check applied, by the settings' names
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

/** The body of POST /flows/run: a start or a check names the flow (and the flow's keys, when its
 * functions gave them); a stop names nothing. */
export function runBody(action: "start" | "stop" | "check", flow: string, keys?: Record<string, string> | null): Record<string, unknown> {
  if (action === "stop") return { action };
  if (action === "check") return keys ? { flow, keys } : { flow }; // POST /flows/run/check: no action
  return keys ? { action, flow, keys } : { action, flow };
}

/** Where a request goes: the read-only check has its OWN route (matpilot 2026-11-13 #16). */
export const runPath = (action: "start" | "stop" | "check"): string => (action === "check" ? "/flows/run/check" : "/flows/run");

/** Whether the game can be checked now, and why not (the backend refuses the same). */
export function canCheck(st: LiveStatus | null, flow: string): { can: boolean; why: string | null } {
  if (st === null) return { can: false, why: "reading the Run helper…" };
  if (!st.helper_alive) return { can: false, why: st.detail || "the Run helper is not running on the bot server" };
  if (ACTIVE.includes(st.state)) return { can: false, why: "a run is going: the game is checked before a run" };
  if (!st.flows || !(flow in st.flows)) return { can: false, why: "the Run helper does not list this flow" };
  if (st.check?.state === "checking") return { can: false, why: "checking the game…" };
  return { can: true, why: null };
}

/** PURE: the check was made with other values than these (``basis``: a checklist line's), or for
 * another flow: its result is outdated (shown greyed). */
export function checkStale(check: LiveCheck | null | undefined, flow: string, basis: Record<string, unknown>): boolean {
  if (!check) return false;
  if (check.flow !== flow) return true;
  const used = check.used ?? {};
  return Object.entries(basis).some(([k, v]) => (used[k] ?? null) !== (v ?? null));
}

export type Tick = { mark: "ok" | "fail" | "unread" | "none"; sign: string; words: string | null; value: string | null; stale: boolean; refuses: boolean };

/** PURE: a checklist line's tick from the last check: ✓ (ok), ✗ (fails: its words), ? (not read),
 * or none (no result for it); ``stale`` when the settings changed since. */
export function tickFor(check: LiveCheck | null | undefined, flow: string, id: string, basis: Record<string, unknown>): Tick {
  const it = check && check.state === "done" ? check.items.find((x) => x.id === id) : undefined;
  if (!it) return { mark: "none", sign: "", words: null, value: null, stale: false, refuses: false };
  const mark = it.ok === true ? "ok" : it.ok === false ? "fail" : "unread";
  return { mark, sign: mark === "ok" ? "✓" : mark === "fail" ? "✗" : "?", words: it.words, value: it.value, stale: checkStale(check, flow, basis), refuses: it.ok === false && it.refuses !== false };
}

/** PURE: the Run button's warning from the last check of this flow: the lines the runner refuses
 * on that failed (Batt: warnings, not locks -- Run stays pressable; the runner refuses itself). */
export function refuseWarning(check: LiveCheck | null | undefined, flow: string): string | null {
  if (!check || check.flow !== flow) return null;
  if (check.state === "refused") return `The last check: ${check.detail ?? "refused"}. The runner will refuse at its start.`;
  if (check.state !== "done") return null;
  const bad = check.items.filter((i) => i.ok === false && i.refuses !== false);
  if (bad.length === 0) return null;
  return `The last check of the game: ${bad.map((i) => i.words).join("; ")}. The runner will refuse at its start (Run still starts it: its own checks decide).`;
}

/** The check's time as the browser's local time of day (its "at" is ISO with an offset). */
export function checkTime(at: string | null | undefined): string {
  const t = at ? new Date(at) : null;
  if (!t || Number.isNaN(t.getTime())) return at ?? "";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(t.getHours())}:${p(t.getMinutes())}:${p(t.getSeconds())}`;
}

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
  check_has_its_own_route: "This page is older than the backend: reload it.",
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
  keys_refused: "The flow's hotbar keys cannot be used",
  check_running: "The game is being checked already: a moment.",
};
