// The /flows Run button (Batt 2026-11-13: "I put the bot on the map, press run, and it plays by
// itself"): the page's side of GET / POST /flows/run (routes_flowrun.py). The backend only passes a
// request to the host helper (scripts/flow_run.py), which runs the proven runner in player mode;
// these helpers decide which buttons a status allows and how it reads. Pure, tested.
//
// THE PROJECT RUN (Batt 2026-11-13 ~21:4x, docs/planning/live-blocks.md stage 1: "on the Maps page
// add a Run button too: it runs from START, box by box"): POST /flows/run/project {project, node}
// asks the Run helper's LIVE BLOCK PLAYER (scripts/flow_play.py, the feat/live-player branch) to
// play the project's blocks in the game from that map node. Its status is GET /flows/run with the
// flow id "project" (PROJECT_FLOW); Stop is POST /flows/run {action: "stop"}, as a runner's.
//
// ➡️ 2026-11-14 ~15:2x (live-blocks.md 12: the runner page is gone, every setting is a block): a
// start is always a project's; the read-only CHECK is a project's too, POST /flows/run/check
// {project, node}: the backend takes the node's keys (its functions) and settings (its setting
// blocks) from the project, as the Run does.

import { forEngine, type Project } from "./project.ts";

export type LiveState = "no_helper" | "idle" | "busy" | "starting" | "running" | "stopping" | "ended" | "failed" | "refused";

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
  // matpilot round 17 N5: another input writer of ours plays (a night chain, a runner, the live
  // block player, an A/B series; scripts/flow_run.py writer_busy), in its words; null: none. The
  // helper's state is then "busy" (or a last run's end, which keeps its words)
  busy?: string | null;
  // Batt 2026-11-18 ("log the status, the checklist and the errors more"; "Alt+Tab: only pause"):
  // the Run's OWN start check (its log's CHECK line) and its pause (no picture: Batt 2026-11-18)
  run_check?: LiveCheck | null;
  identity?: "any" | "known" | "mine" | "unreadable" | string; // Settings: who may play a Run (ADR-0020 Amendments Q, R)
  pause?: RunPause | null;
};

/** A Run's pause while the game is off the screen (scripts/flow_run.py RunLog.pause). */
export type RunPause = { paused: boolean; since: string | null; why: string | null; count: number; paused_s: number };

/** PURE: the pause in a person's words: paused now (since when, why, what the bot does), or how
 * often it paused; null: it never paused. */
export function pauseLine(p: RunPause | null | undefined): string | null {
  if (!p || p.count <= 0) return null;
  if (p.paused) return `PAUSED since ${p.since ?? "?"}: ${p.why ?? "the game is not on the screen"}. The bot waits and presses nothing; it plays on by itself when the game is back on the screen.`;
  return `Paused ${p.count} time${p.count === 1 ? "" : "s"} (${Math.round(p.paused_s)} s in all): the game was off the screen; it played on by itself each time.`;
}

/** PURE: the Run's own start check, one line per item, the failing ones first. */
export function runCheckLines(c: LiveCheck | null | undefined): { id: string; mark: "ok" | "fail" | "unread"; sign: string; words: string; value: string | null }[] {
  if (!c || !Array.isArray(c.items)) return [];
  const rank = { fail: 0, unread: 1, ok: 2 } as const;
  return c.items
    .map((it) => {
      const mark: "ok" | "fail" | "unread" = it.ok === true ? "ok" : it.ok === false ? "fail" : "unread";
      return { id: it.id, mark, sign: mark === "ok" ? "✓" : mark === "fail" ? "✗" : "?", words: it.words, value: it.value ?? null };
    })
    .sort((a, b) => rank[a.mark] - rank[b.mark]);
}

/** PURE: why Run (``what`` "run") or the check (``what`` "check") waits: another input writer of
 * ours plays (null: none). matpilot round 18 (c): "Check the game"'s title said "Run waits": it is
 * the CHECK that waits there (the backend refuses a check meanwhile too, input_writer_busy). */
export function busyWhy(st: LiveStatus | null, what: "run" | "check" = "run"): string | null {
  if (!st?.busy) return null;
  return what === "check" ? `${st.busy}: the check waits until it ends (the Run helper refuses a check meanwhile)` : `${st.busy}: Run waits until it ends (the Run helper refuses to start meanwhile)`;
}

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
  end: { reason?: string; home?: boolean; dead?: boolean; respawned?: boolean; words?: string };
  // 2026-11-19 (Batt: a Logs tab -- what she does, is she attacking): the last events in words
  retries?: number;
  story?: { t_s: number | null; words: string }[];
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

/** The body of POST /flows/run: Stop names nothing else (a start and a check are a project's:
 * projectRunBody, checkBody). */
export function runBody(action: "stop"): Record<string, unknown> {
  return { action };
}

/** The body of POST /flows/run/check (2026-11-14): the project and the map node it checks; the
 * backend reads the node's keys and its setting blocks from it (no action, no keys, no values). */
export function checkBody(project: Project, node: string): { project: Project; node: string } {
  return { project: forEngine(project), node }; // round 25: never a tab's layout
}

/** Where a request goes: the read-only check has its OWN route (matpilot 2026-11-13 #16). */
export const runPath = (action: "start" | "stop" | "check"): string => (action === "check" ? "/flows/run/check" : "/flows/run");

/** The flow id a PROJECT run has in GET /flows/run's status (the live block player). */
export const PROJECT_FLOW = "project";
/** The project run to start: the project (format 3) and the MAP node it starts on. */
export type ProjectRun = { project: Project; node: string };
/** The body of POST /flows/run/project: the whole project, and the map node it plays from. */
export function projectRunBody(project: Project, node: string): { project: Project; node: string } {
  return { project: forEngine(project), node }; // round 25: never a tab's layout (outside the run)
}
/** Where a project run's start goes (a stop stays POST /flows/run {action: "stop"}). */
export const projectRunPath = (): string => "/flows/run/project";

/** Whether the game can be checked now, and why not (the backend refuses the same). */
export function canCheck(st: LiveStatus | null, flow: string): { can: boolean; why: string | null } {
  if (st === null) return { can: false, why: "reading the Run helper…" };
  if (!st.helper_alive) return { can: false, why: st.detail || "the Run helper is not running on the bot server" };
  if (ACTIVE.includes(st.state)) return { can: false, why: "a run is going: the game is checked before a run" };
  if (busyWhy(st)) return { can: false, why: busyWhy(st, "check") };
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

/** PURE (matpilot round 16 #2, round 18 #1): what a ✓ line adds after its value -- the words after
 * the line's last ";" OUTSIDE parentheses (the runner writes "<what was checked>; <what was read>").
 * A ";" inside a parenthesis is part of that aside, never a cut: the identity line's "(her
 * references; no DB, as the player start)" showed as "no DB, as the player start)", its ")" with no
 * "(". null when there is no such ";" (the value says it all). */
export function okTail(words: string | null | undefined): string | null {
  if (!words) return null;
  let depth = 0;
  let cut = -1;
  for (let i = 0; i < words.length; i += 1) {
    const c = words[i];
    if (c === "(") depth += 1;
    else if (c === ")") depth = Math.max(0, depth - 1);
    else if (c === ";" && depth === 0) cut = i;
  }
  const tail = cut < 0 ? "" : words.slice(cut + 1).trim();
  return tail === "" ? null : tail;
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

/** The console modes a Run may start in (Batt 2026-11-18: "with BOT it must run too"; ADR-0020
 * Amendment 2026-11-18): ASSIST, where the person can take the lease, and BOT, where the mux drops
 * the person's input so watching the Console never pauses the run. Never HUMAN. The backend's
 * RUN_MODES, the same two. */
export const RUN_MODES: readonly string[] = ["ASSIST", "BOT"];

export type LiveButtons = { canStart: boolean; canStop: boolean; why: string | null };

/** Which buttons the status allows for `flow`, and why Start is off (the backend refuses the same).
 * A PROJECT run (PROJECT_FLOW) needs no entry in the helper's flow list: the player plays any
 * project the backend's checks pass (its refusals come back in words, REFUSALS). */
export function liveButtons(st: LiveStatus | null, flow: string): LiveButtons {
  if (st === null) return { canStart: false, canStop: false, why: "reading the Run helper…" };
  if (!st.helper_alive) return { canStart: false, canStop: false, why: st.detail || "the Run helper is not running on the bot server" };
  const active = ACTIVE.includes(st.state);
  if (active) return { canStart: false, canStop: st.state !== "stopping", why: null };
  if (busyWhy(st)) return { canStart: false, canStop: false, why: busyWhy(st) }; // round 17 N5
  if (flow !== PROJECT_FLOW && (!st.flows || !(flow in st.flows))) return { canStart: false, canStop: false, why: "the Run helper does not list this flow" };
  if (!RUN_MODES.includes(st.mode ?? "")) return { canStart: false, canStop: false, why: `the console is in ${st.mode ?? "an unknown mode"}: set ASSIST or BOT first (the bot never plays in HUMAN)` };
  return { canStart: true, canStop: false, why: null };
}

const WORDS: Record<string, string> = {
  no_helper: "the Run helper is not running",
  idle: "ready",
  busy: "busy: another input writer of ours plays",
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
  if (st.busy && !ACTIVE.includes(st.state)) return `busy: ${st.busy}`; // round 17 N5, in its words
  return WORDS[st.state] ?? st.state;
}

/** The page's words for a refusal reason of POST /flows/run. */
export const REFUSALS: Record<string, string> = {
  helper_not_running: "The Run helper on the bot server is not running.",
  check_has_its_own_route: "This page is older than the backend: reload it.",
  nothing_running: "Nothing is running.",
  unknown_flow: "The Run helper does not list this flow.",
  already_running: "A run is already going: press Stop first.",
  input_writer_busy: "Another input writer of ours plays (a night chain, a runner, the live block player or an A/B series): Run waits until it ends.",
  mode_human: "The console is in HUMAN: set ASSIST or BOT first (the bot never plays in HUMAN).",
  csrf_invalid: "The page's security token expired: reload the page and try again.",
  origin_required: "Open the console from its own address to use Run.",
  lab_host_peer: "Run is refused from the bot server itself: use your own browser on the LAN.",
  rate_limited: "Too many requests: wait a moment.",
  keys_refused: "The flow's hotbar keys cannot be used",
  // 2026-11-14 (live-blocks.md 12): a project's check
  settings_refused: "A setting block cannot be used (Lint names it)",
  no_hunt_core: "This node has no hunt with the runner: the check is the runner's.",
  not_a_map_node: "Run and the check belong to a map node.",
  check_running: "The game is being checked already: a moment.",
  // the PROJECT run (POST /flows/run/project; the live block player)
  lint_errors: "The flow engine finds errors in the project: fix them first (Lint lists them).",
  not_live: "A block on the way cannot be played in the game yet (Simulate plays it).",
  run_start_refused: "The run-start check refused it.",
  invalid_project: "The flow engine refuses this project.",
};
