"use client";

// The /flows Run button (Batt 2026-11-13): starts and stops the REAL runner in the game through the
// backend's POST /flows/run (routes_flowrun.py: the Settings page's write rules) and the host's Run
// helper (scripts/flow_run.py, player mode: it types no GM line and starts where she stands).
// Shows the helper's status every 2 s. Text only: every value from the backend renders as text.
//
// ONE poller per page (useLiveRun): the header's Run / Stop beside Simulate (Batt 2026-11-13: "a
// Run button next to Simulate, to run it for real on this map") and the status panel share it.
// The header's Run takes TWO presses (a second within ARM_MS): it sits beside Simulate, which
// runs nothing, and a live run must never start from a slip.
//
// THE LIVE TICKS (dungeon@9.45, Batt 2026-11-13 "do it"): "Check the game" (and once by itself
// when the panel opens and the helper is idle) asks the helper for the runner's read-only check;
// each checklist line then shows ✓ / ✗ / ? with what was read, greyed when the settings changed
// since. A ✗ never locks Run (Batt: warnings, not locks): the runner refuses on its own, and the
// Run button's title says so. THE FLOW'S KEYS (Batt 2026-11-13: every hotbar key from a function
// of the flow): ``keys`` goes with every start and check, and the checklist states those keys.
//
// THE PROJECT RUN (Batt 2026-11-13 ~21:4x, docs/planning/live-blocks.md stage 1): given a project
// and a map node (``run``), a start is POST /flows/run/project {project, node} -- the live block
// player plays the project's blocks from that node (/flows: the node shown; /maps: START) -- while
// the check (the runner's read-only check, ``flow``) and Stop are as before. One hook for both
// pages: the same amber button, the same press-twice confirm, the same live line.

import { useCallback, useEffect, useRef, useState } from "react";

import { type ChecklistItem, checklistWithKeys, type RunKeys } from "@/lib/flow/config";
import { ACTIVE, canCheck, checkStale, checkTime, liveButtons, liveLabel, liveLine, type LiveStatus, PROJECT_FLOW, type ProjectRun, projectRunBody, projectRunPath, refuseWarning, REFUSALS, runBody, runPath, tickFor } from "@/lib/flow/liverun";
import { backendHttpBase } from "@/lib/ws";

const POLL_MS = 2000;
export const ARM_MS = 4000;

export type Live = {
  base: string;
  flow: string;
  st: LiveStatus | null;
  err: string | null;
  busy: boolean;
  /** One request; ``keys`` (the flow's functions' five keys) go with a start or a check, else the
   * hook's own ``keys``. */
  send: (action: "start" | "stop" | "check", keys?: RunKeys | null) => Promise<void>;
  buttons: ReturnType<typeof liveButtons>;
  keys: RunKeys | null;
  /** the project run a start sends (null: the runner flow ``flow``) */
  run: ProjectRun | null;
};

/** ``keys``: the flow's functions' hotbar keys (all five), sent with every start and check of
 * this poller; null: the bot server's settings decide. ``run``: a PROJECT run (the project and the
 * map node it plays from): a start posts POST /flows/run/project instead of the runner flow's. */
export function useLiveRun(backendUrl: string | null, flow: string, enabled = true, keys: RunKeys | null = null, run: ProjectRun | null = null): Live {
  const base = backendHttpBase(backendUrl);
  const [st, setSt] = useState<LiveStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const csrf = useRef<string | null>(null);
  const refresh = useRef<() => void>(() => {});
  const keysRef = useRef<RunKeys | null>(keys);
  useEffect(() => {
    keysRef.current = keys;
  }, [keys]);
  const runRef = useRef<ProjectRun | null>(run);
  useEffect(() => {
    runRef.current = run;
  }, [run]);

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    const tick = async () => {
      try {
        const r = await fetch(`${base}/flows/run`, { cache: "no-store" });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const body = (await r.json()) as LiveStatus;
        if (alive) setSt(body);
      } catch (e) {
        if (alive) {
          setSt(null);
          setErr(`The backend did not answer (${e instanceof Error ? e.message : String(e)}).`);
        }
      }
    };
    refresh.current = () => void tick();
    const first = setTimeout(() => void tick(), 0);
    const timer = setInterval(() => void tick(), POLL_MS);
    return () => {
      alive = false;
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [base, enabled]);

  const send = useCallback(
    async (action: "start" | "stop" | "check", given?: RunKeys | null): Promise<void> => {
      const k = given ?? keysRef.current;
      const project = action === "start" ? runRef.current : null; // the project run: its own route
      setBusy(true);
      setErr(null);
      try {
        for (let attempt = 0; attempt < 2; attempt++) {
          if (csrf.current === null) {
            const t = await fetch(`${base}/settings/csrf`, { cache: "no-store" });
            if (!t.ok) throw new Error(`the security token was refused (HTTP ${t.status})`);
            csrf.current = ((await t.json()) as { token: string }).token;
          }
          const r = await fetch(`${base}${project ? projectRunPath() : runPath(action)}`, {
            method: "POST",
            cache: "no-store",
            headers: { "content-type": "application/json", "x-csrf-token": csrf.current },
            // every other setting is the bot server's config
            body: JSON.stringify(project ? projectRunBody(project.project, project.node) : runBody(action, flow, k)),
          });
          if (r.ok) break;
          const body = (await r.json().catch(() => ({}))) as { detail?: { reason?: string; detail?: string } };
          const reason = body.detail?.reason ?? `HTTP ${r.status}`;
          if (reason === "csrf_invalid" && attempt === 0) {
            csrf.current = null; // a backend restart invalidates every token: fetch a new one once
            continue;
          }
          const more = body.detail?.detail ? `: ${body.detail.detail}` : "";
          setErr(`${REFUSALS[reason] ?? `Refused: ${reason}`}${more}`);
          break;
        }
        refresh.current();
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [base, flow],
  );

  return { base, flow, st, err, busy, send, buttons: liveButtons(st, run ? PROJECT_FLOW : flow), keys, run };
}

/** The header's Run / Stop, beside Simulate. Run arms on the first press and starts on a second
 * within ARM_MS; the armed button says what it will do. ``keys``: the flow's keys for this start
 * (else the poller's). A failed check's lines are in its title: the runner will refuse. */
export function LiveRunButtons({ live, blocked = null, keys = null }: { live: Live; blocked?: string | null; keys?: RunKeys | null }) {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return;
    const t = setTimeout(() => setArmed(false), ARM_MS);
    return () => clearTimeout(t);
  }, [armed]);
  const b = live.buttons;
  const running = b.canStop;
  const warn = refuseWarning(live.st?.check, live.flow);
  return (
    <>
      {running ? (
        <button type="button" className="button button-live button-live-stop" disabled={live.busy} onClick={() => void live.send("stop")} title="Stop the real run: it ends through its normal end" data-testid="runner-live-stop">
          <StopIcon />
          <span className="button-text">Stop</span>
        </button>
      ) : (
        <button
          type="button"
          className="button button-live"
          data-armed={armed ? "true" : "false"}
          disabled={!b.canStart || live.busy || blocked !== null}
          onClick={() => {
            if (!armed) {
              setArmed(true);
              return;
            }
            setArmed(false);
            void live.send("start", keys);
          }}
          title={blocked ?? (b.canStart ? (warn ?? (live.run ? `Run the project FOR REAL in the game, box by box from ${live.run.node}, where she stands (player mode). Press, then press again to confirm.` : "Run it FOR REAL in the game, on the map she stands on (player mode). Press, then press again to confirm.")) : (b.why ?? "Run is not available now"))}
          data-refuses={warn ? "true" : "false"}
          aria-label={armed ? "Confirm: run in the game" : "Run in the game"}
          data-testid="runner-live-run"
        >
          <RunIcon />
          <span className="button-text">{armed ? "Confirm: run in the game" : "Run"}</span>
        </button>
      )}
    </>
  );
}

/** `blocked`: why Run cannot be pressed now (a key clash, a broken settings file): the state then
 * never says "ready" (matpilot 2026-11-13 #6). `check` false: no checklist and no "Check the game"
 * (a node without the runner: the live block player checks its own start). */
export default function LiveRun({ live, checklist = [], minutes = null, keys = null, blocked = null, check: withCheck = true }: { live: Live; checklist?: ChecklistItem[]; minutes?: number | null; keys?: RunKeys | null; blocked?: string | null; check?: boolean }) {
  const { st, err, buttons: b, flow } = live;
  const title = st?.flows?.[flow]?.title;
  const active = ACTIVE.includes(st?.state ?? "");
  const line = active ? liveLine(st?.live, minutes ?? st?.flows?.[flow]?.minutes ?? null) : null;
  const ended = st?.state === "ended" || st?.state === "failed";
  const logLines = (st?.log_tail ?? []).filter((ln) => ln.trim() !== (st?.detail ?? "").trim()); // matpilot: not twice
  const runKeys = keys ?? live.keys;
  const items = checklistWithKeys(checklist, runKeys); // the keys Run sends, in the text too
  const check = st?.check?.flow === flow ? st.check : null;
  const cc = canCheck(st, flow);
  const anyStale = items.some((it) => checkStale(check, flow, it.basis));
  // once by itself when the panel opens and the helper can check (Batt: "do it")
  const auto = useRef(false);
  const { send } = live;
  useEffect(() => {
    if (!withCheck || auto.current || !cc.can || st?.check?.state === "checking") return;
    auto.current = true;
    void send("check", runKeys);
  }, [withCheck, cc.can, st?.check?.state, send, runKeys]);
  return (
    <section className="notice" aria-label="Run in the game" data-testid="live-run">
      <p>
        <strong>Run in the game</strong> · <span data-testid="live-run-state">{stateWords(liveLabel(st), st?.state ?? null, blocked, items.some((it) => tickFor(check, flow, it.id, it.basis).mark === "fail"))}</span>
        {st?.label ? ` · ${st.label}` : ""}
      </p>
      {line && (
        <p className="live-line" data-testid="live-run-line">
          {line}
        </p>
      )}
      {!active && !withCheck && (
        <p>
          {live.run ? `The bot plays this project's blocks from ${live.run.node}, where she stands` : (title ?? "the bot plays this flow")}. Before Run (press it twice: the second press confirms): put her on the map yourself, the console in ASSIST. The player checks its own start (the map, the chat closed) and refuses with the reason before any input.
        </p>
      )}
      {!active && withCheck && (
        <>
          <p>{title ?? "the bot plays this flow"}. Before Run (press it twice: the second press confirms), check:</p>
          {/* matpilot: the start conditions were buried in a paragraph; dungeon@9.45: each ticked from the game screen */}
          <ul className="live-checklist" data-testid="live-run-checklist">
            {items.map((it) => {
              const t = tickFor(check, flow, it.id, it.basis);
              return (
                <li key={it.id} data-tick={t.mark} data-stale={t.stale ? "true" : "false"} data-testid={`live-check-${it.id}`}>
                  {/* matpilot round 15 #8: a greyed (stale) line shows no verdict: its tick was for other keys */}
                  <span className="live-tick" aria-label={t.stale ? "changed since the last check" : t.mark === "none" ? "not checked" : t.mark === "ok" ? "passes" : t.mark === "fail" ? "fails" : "not read"}>
                    {t.stale ? "·" : t.sign || "·"}
                  </span>{" "}
                  {it.text}
                  {t.value && !t.stale && <span className="live-tick-value"> · read: {t.value}</span>}
                  {t.mark !== "ok" && t.mark !== "none" && !t.stale && t.words && <span className="live-tick-words"> · {t.words}</span>}
                  {/* matpilot round 16 #2: a ✓ line says what was read from the icon too */}
                  {t.mark === "ok" && !t.stale && t.words?.includes(";") && <span className="live-tick-words"> · {t.words.split(";").pop()?.trim()}</span>}
                  {t.mark === "fail" && !t.refuses && <span className="live-tick-words"> (the runner goes on without it)</span>}
                  {/* matpilot #5: a key that reads none may simply be the wrong key */}
                  {t.mark === "fail" && /^0 /.test(t.value ?? "") && ["wings", "heals", "home"].includes(it.id) && (
                    <span className="live-tick-words"> · if the items are on another hotbar key, set that key in the function (this node&apos;s, or Global&apos;s keys tab)</span>
                  )}
                </li>
              );
            })}
            <li data-tick={st?.mode === "ASSIST" ? "ok" : st ? "fail" : "none"} data-stale="false" data-testid="live-check-assist">
              <span className="live-tick">{st?.mode === "ASSIST" ? "✓" : st ? "✗" : "·"}</span> the console in ASSIST
            </li>
          </ul>
          <p className="notice-sub live-check-bar">
            <button type="button" className="button" disabled={!cc.can || live.busy} onClick={() => void send("check", runKeys)} title={cc.why ?? "Read the game screen now: the runner's own start checks, read only (it presses nothing)"} data-testid="live-run-check">
              {st?.check?.state === "checking" ? "Checking the game…" : "Check the game"}
            </button>{" "}
            {check && check.state !== "checking" && (
              <span data-testid="live-run-check-time">
                last checked {checkTime(check.at)}
                {check.state !== "done" ? ` · ${check.detail ?? check.state}` : ""}
                {anyStale ? " · greyed lines: the keys or the settings changed since, check again" : ""}
                {check.keys_src ? ` · keys from ${check.keys_src}` : ""}
              </span>
            )}
          </p>
          <p className="notice-sub">The check only reads the screen: it presses nothing. The runner checks each of these itself before its first step, and refuses with the reason; a ✗ does not lock Run. It types no GM command.</p>
        </>
      )}
      {b.why && <p className="notice-sub">{b.why}</p>}
      {st?.detail && <p className={ended ? "live-end" : "notice-sub"}>{st.detail}</p>}
      {st?.started && (
        <p className="notice-sub">
          started {st.started}
          {st.ended ? ` · ended ${st.ended}` : ""}
          {st.rc !== null && st.rc !== undefined ? ` · rc ${st.rc}` : ""}
        </p>
      )}
      {ended && st?.end_png && <EndPicture base={live.base} stamp={st.end_png} />}
      {logLines.length > 0 && (
        <pre className="notice-sub" data-testid="live-run-log">
          {logLines.join("\n")}
        </pre>
      )}
      {err && (
        <p className="notice notice-warn" role="status">
          {err}
        </p>
      )}
    </section>
  );
}

/** The last run's end picture (matpilot: "show it as an image, not a server path"), fetched over
 * the backend connection the page already has (the CSP's img-src stays 'self' blob: data:). */
function EndPicture({ base, stamp }: { base: string; stamp: string }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    let made: string | null = null;
    void fetch(`${base}/flows/run/end.png`, { cache: "no-store" })
      .then((r) => (r.ok ? r.blob() : null))
      .then((blob) => {
        if (!alive || !blob) return;
        made = URL.createObjectURL(blob);
        setUrl(made);
      })
      .catch(() => {});
    return () => {
      alive = false;
      if (made) URL.revokeObjectURL(made);
    };
  }, [base, stamp]);
  if (!url) return null;
  return (
    <figure className="live-end-picture">
      {/* eslint-disable-next-line @next/next/no-img-element -- a blob: URL of the backend's picture */}
      <img src={url} alt="The game screen when the run ended" data-testid="live-run-end-picture" />
      <figcaption className="notice-sub">the screen when the run ended ({stamp})</figcaption>
    </figure>
  );
}

function RunIcon() {
  return (
    <svg className="button-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M6.5 5.25v5.5l4.25-2.75z" fill="currentColor" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg className="button-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <rect x="4" y="4" width="8" height="8" rx="1" fill="currentColor" />
    </svg>
  );
}

/** The state's words: never "ready" while Run is blocked or a check line fails (matpilot #6). */
export function stateWords(label: string, state: string | null, blocked: string | null, failing: boolean): string {
  if (state !== "idle" && state !== "ended" && state !== "failed" && state !== null) return label;
  if (blocked) return "not ready: Run is blocked (see why under it)";
  if (failing) return "not ready: a line below fails (✗)";
  return label;
}

/** Run where the bot cannot play this node's blocks live yet (Batt 2026-11-13: "every flow has
 * Simulate and Run"): the same button, greyed, saying why. */
export function RunNotReady({ why }: { why: string }) {
  return (
    <button type="button" className="button button-live" disabled title={why} aria-label={`Run in the game: not available (${why})`} data-testid="runner-live-run-not-ready">
      <RunIcon />
      <span className="button-text">Run</span>
    </button>
  );
}

