"use client";

// The /flows Run button (Batt 2026-11-13): starts and stops the REAL runner in the game through the
// backend's POST /flows/run (routes_flowrun.py: the Settings page's write rules) and the host's Run
// helper (scripts/flow_run.py, player mode: it types no GM line and starts where she stands).
// Shows the helper's status every 2 s. Text only: every value from the backend renders as text.

import { useCallback, useEffect, useRef, useState } from "react";

import { liveButtons, liveLabel, type LiveStatus, REFUSALS } from "@/lib/flow/liverun";
import { backendHttpBase } from "@/lib/ws";

const POLL_MS = 2000;

export default function LiveRun({ backendUrl, flow }: { backendUrl: string | null; flow: string }) {
  const base = backendHttpBase(backendUrl);
  const [st, setSt] = useState<LiveStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const csrf = useRef<string | null>(null);

  const refresh = useRef<() => void>(() => {});

  useEffect(() => {
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
  }, [base]);

  const send = useCallback(
    async (action: "start" | "stop"): Promise<void> => {
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
            body: JSON.stringify(action === "start" ? { action, flow } : { action }),
          });
          if (r.ok) break;
          const body = (await r.json().catch(() => ({}))) as { detail?: { reason?: string } };
          const reason = body.detail?.reason ?? `HTTP ${r.status}`;
          if (reason === "csrf_invalid" && attempt === 0) {
            csrf.current = null; // a backend restart invalidates every token: fetch a new one once
            continue;
          }
          setErr(REFUSALS[reason] ?? `Refused: ${reason}`);
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

  const b = liveButtons(st, flow);
  const title = st?.flows?.[flow]?.title;
  return (
    <section className="notice" aria-label="Run in the game" data-testid="live-run">
      <p>
        <strong>Run in the game</strong> · <span data-testid="live-run-state">{liveLabel(st)}</span>
        {st?.label ? ` · ${st.label}` : ""}
      </p>
      <p>
        {title ?? "the bot plays this flow"}. Put her on the map yourself (open ground, chat closed, the bag under 48 %, at least 5 Fly Wings and 5 heal items on the hotbar), set the console to
        ASSIST, then press Run. She plays until you press Stop, until her Fly Wings run low (one stays for the escape; a Butterfly Wing on F8 takes her home), or for at most
        {` ${st?.flows?.[flow]?.minutes ?? 120} `}
        minutes. It types no GM command.
      </p>
      <div className="button-row">
        <button type="button" className="button button-primary button-run" disabled={!b.canStart || busy} onClick={() => void send("start")} data-testid="live-run-start">
          Run
        </button>
        <button type="button" className="button button-small" disabled={!b.canStop || busy} onClick={() => void send("stop")} data-testid="live-run-stop">
          Stop
        </button>
      </div>
      {b.why && <p className="notice-sub">{b.why}</p>}
      {st?.detail && <p className="notice-sub">{st.detail}</p>}
      {st?.started && (
        <p className="notice-sub">
          started {st.started}
          {st.ended ? ` · ended ${st.ended}` : ""}
          {st.rc !== null && st.rc !== undefined ? ` · rc ${st.rc}` : ""}
        </p>
      )}
      {st?.log_tail && st.log_tail.length > 0 && (
        <pre className="notice-sub" data-testid="live-run-log">
          {st.log_tail.join("\n")}
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
