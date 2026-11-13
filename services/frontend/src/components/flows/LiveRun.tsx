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

import { useCallback, useEffect, useRef, useState } from "react";

import { type ChecklistItem, checklistWithKeys, type RunKeys } from "@/lib/flow/config";
import { ACTIVE, canCheck, checkStale, checkTime, liveButtons, liveLabel, liveLine, type LiveStatus, refuseWarning, REFUSALS, runBody, tickFor } from "@/lib/flow/liverun";
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
};

/** ``keys``: the flow's functions' hotbar keys (all five), sent with every start and check of
 * this poller; null: the bot server's settings decide. */
export function useLiveRun(backendUrl: string | null, flow: string, enabled = true, keys: RunKeys | null = null): Live {
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
      setBusy(true);
      setErr(null);
      try {
        for (let attempt = 0; attempt < 2; attempt++) {
          if (csrf.current === null) {
            const t = await fetch(`${base}/settings/csrf`, { cache: "no-store" });
            if (!t.ok) throw new Error(`the security token was refused (HTTP ${t.status})`);
            csrf.current = ((await t.json()) as { token: string }).token;
          }
          const r = await fetch(`${base}/flows/run`, {
            method: "POST",
            cache: "no-store",
            headers: { "content-type": "application/json", "x-csrf-token": csrf.current },
            body: JSON.stringify(runBody(action, flow, k)), // every other setting is the bot server's config
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

  return { base, flow, st, err, busy, send, buttons: liveButtons(st, flow), keys };
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
          title={blocked ?? (b.canStart ? (warn ?? "Run it FOR REAL in the game, on the map she stands on (player mode). Press, then press again to confirm.") : (b.why ?? "Run is not available now"))}
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

export default function LiveRun({ live, checklist = [], minutes = null, keys = null }: { live: Live; checklist?: ChecklistItem[]; minutes?: number | null; keys?: RunKeys | null }) {
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
    if (auto.current || !cc.can || st?.check?.state === "checking") return;
    auto.current = true;
    void send("check", runKeys);
  }, [cc.can, st?.check?.state, send, runKeys]);
  return (
    <section className="notice" aria-label="Run in the game" data-testid="live-run">
      <p>
        <strong>Run in the game</strong> · <span data-testid="live-run-state">{liveLabel(st)}</span>
        {st?.label ? ` · ${st.label}` : ""}
      </p>
      {line && (
        <p className="live-line" data-testid="live-run-line">
          {line}
        </p>
      )}
      {!active && (
        <>
          <p>{title ?? "the bot plays this flow"}. Before Run (press it twice: the second press confirms), check:</p>
          {/* matpilot: the start conditions were buried in a paragraph; dungeon@9.45: each ticked from the game screen */}
          <ul className="live-checklist" data-testid="live-run-checklist">
            {items.map((it) => {
              const t = tickFor(check, flow, it.id, it.basis);
              return (
                <li key={it.id} data-tick={t.mark} data-stale={t.stale ? "true" : "false"} data-testid={`live-check-${it.id}`}>
                  <span className="live-tick" aria-label={t.mark === "none" ? "not checked" : t.mark === "ok" ? "passes" : t.mark === "fail" ? "fails" : "not read"}>
                    {t.sign || "·"}
                  </span>{" "}
                  {it.text}
                  {t.value && <span className="live-tick-value"> · read: {t.value}</span>}
                  {t.mark !== "ok" && t.mark !== "none" && t.words && <span className="live-tick-words"> · {t.words}</span>}
                  {t.mark === "fail" && !t.refuses && <span className="live-tick-words"> (the runner goes on without it)</span>}
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
                {anyStale ? " · greyed lines: the settings changed since, check again" : ""}
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
