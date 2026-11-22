"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { browserStorage, readChoice, writeChoice } from "@/lib/flow/prefs";
import {
  NOTIFY_CHOICES,
  notifyPlan,
  notifyPlanText,
  newNotifications,
  panelModel,
  recordReasonText,
  ROUTEREC_NOTIFY_KEY,
  toastMs,
  toolbarLabel,
  wantsBrowserNotification,
  type NotifyApi,
  type NotifyChoice,
  type PanelModel,
  type RouteRecNotification,
  type RouteRecStatus,
} from "@/lib/routerec";
import { backendHttpBase } from "@/lib/ws";

/**
 * The console's "Record route" button (docs/planning/waypoints-npc-recording.md Amendments 11-12):
 * the PERSON records their own play once, so the route's waypoints come from the video. The page
 * asks the backend (GET / POST /routes/record), which hands ONE request file to the host helper
 * scripts/route_rec.py; the helper checks the game screen and runs the recorder. Nothing here sends
 * game input, and the panel works in Watch only too (it is not input).
 *
 * Every value from the backend is rendered as TEXT (React children only, never as markup): the
 * guide's words come from the helper's status file.
 */

const POLL_MS = 2000; // the helper rewrites its status every 2 s

type Act = "check" | "start" | "stop";
type Note = { tone: "error" | "info"; text: string };
export type RouteToast = RouteRecNotification & { until: number };

function notifyApi(): NotifyApi {
  if (typeof window === "undefined" || !("Notification" in window)) {
    return { present: false, secure: false, permission: "default" };
  }
  return { present: true, secure: window.isSecureContext, permission: Notification.permission };
}

export type RouteRec = {
  model: PanelModel;
  label: { text: string; recording: boolean };
  toasts: RouteToast[];
  note: Note | null;
  sending: Act | null;
  notifyChoice: NotifyChoice;
  notifyText: string;
  setNotifyChoice: (c: NotifyChoice) => void;
  act: (a: Act) => void;
  dismiss: (id: string) => void;
};

/** The panel's state: the status poll, the new guide notifications (toasts, and the browser's own
 * notification when allowed) and the three presses. Lives in the Console, so the recording sign and
 * the toasts show while the panel is closed. */
export function useRouteRec(backendUrl: string | null): RouteRec {
  const base = useMemo(() => (typeof window === "undefined" ? "" : backendHttpBase(backendUrl)), [backendUrl]);
  const store = useMemo(() => browserStorage(), []);
  const [status, setStatus] = useState<RouteRecStatus | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [sending, setSending] = useState<Act | null>(null);
  const [note, setNote] = useState<Note | null>(null);
  const [toasts, setToasts] = useState<RouteToast[]>([]);
  const [notifyChoice, setChoiceState] = useState<NotifyChoice>("on");
  const [api, setApi] = useState<NotifyApi>({ present: false, secure: false, permission: "default" });
  const seenRef = useRef<string[] | null>(null); // null until the first poll: a reload replays nothing
  const planRef = useRef<ReturnType<typeof notifyPlan>>("unavailable");
  const csrf = useRef<string | null>(null);

  // restored after the first render (the server render has no storage), like the console's toggles
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- browser-only state, read once
    setChoiceState(readChoice(store, ROUTEREC_NOTIFY_KEY, NOTIFY_CHOICES, "on"));
    setApi(notifyApi());
  }, [store]);

  const plan = notifyPlan(api, notifyChoice);
  useEffect(() => {
    planRef.current = plan;
  }, [plan]);

  const setNotifyChoice = useCallback(
    (c: NotifyChoice) => {
      setChoiceState(c);
      writeChoice(store, ROUTEREC_NOTIFY_KEY, c);
    },
    [store],
  );

  const take = useCallback((st: RouteRecStatus) => {
    setStatus(st);
    const { fresh, seen } = newNotifications(st.notifications, seenRef.current);
    seenRef.current = seen;
    if (fresh.length === 0) return;
    const now = Date.now();
    setToasts((old) => [...old.filter((t) => t.until > now), ...fresh.map((n) => ({ ...n, until: now + toastMs(n) }))]);
    if (planRef.current === "show") {
      for (const n of fresh.filter(wantsBrowserNotification)) {
        try {
          new Notification("poring-lab: Record route", { body: n.text, tag: n.id });
        } catch {
          // a browser that refuses at show time: the toast is still in the page
        }
      }
    }
  }, []);

  // the poll: every 2 s while the tab is visible; one at once when it becomes visible again
  useEffect(() => {
    if (!base) return;
    let stop = false;
    const poll = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const r = await fetch(`${base}/routes/record`, { cache: "no-store" });
        const body = (await r.json().catch(() => null)) as RouteRecStatus | null;
        if (!stop && body && typeof body === "object" && "state" in body) take(body);
        else if (!stop && !r.ok) setStatus({ state: "no_helper", helper_alive: false, detail: `The backend refused the status (HTTP ${r.status}).` });
      } catch {
        if (!stop) setStatus({ state: "no_helper", helper_alive: false, detail: "The backend did not answer." });
      }
    };
    void poll();
    const id = setInterval(() => void poll(), POLL_MS);
    const onVis = () => void poll();
    document.addEventListener("visibilitychange", onVis);
    return () => {
      stop = true;
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [base, take]);

  // expired toasts leave on their own
  useEffect(() => {
    if (toasts.length === 0) return;
    const next = Math.min(...toasts.map((t) => t.until)) - Date.now();
    const id = setTimeout(() => setToasts((old) => old.filter((t) => t.until > Date.now())), Math.max(250, next));
    return () => clearTimeout(id);
  }, [toasts]);

  const model = useMemo(() => panelModel(status, pendingId), [status, pendingId]);

  /** One press with the CSRF token (a stale token is fetched again once). */
  const act = useCallback(
    (a: Act) => {
      if (!base) return;
      setSending(a);
      setNote(null);
      // the browser asks its permission only on a person's press: Start is the one Amendment 11 names
      if (a === "start" && planRef.current === "ask") {
        try {
          void Notification.requestPermission().then(() => setApi(notifyApi()));
        } catch {
          // an old browser without the promise form: the toasts stay
        }
      }
      const once = async (): Promise<Response> => {
        if (!csrf.current) {
          const t = await fetch(`${base}/settings/csrf`, { cache: "no-store" });
          csrf.current = t.ok ? ((await t.json()) as { token: string }).token : "";
        }
        return fetch(`${base}/routes/record`, {
          method: "POST",
          headers: { "content-type": "application/json", "x-csrf-token": csrf.current ?? "" },
          body: JSON.stringify({ action: a }),
        });
      };
      void (async () => {
        try {
          let r = await once();
          if (r.status === 403) {
            const peek = await r.clone().json().catch(() => null);
            if (peek?.detail?.reason === "csrf_invalid") {
              csrf.current = null;
              r = await once();
            }
          }
          const body = await r.json().catch(() => null);
          if (r.ok) {
            setPendingId(a === "stop" ? null : ((body as { id?: string } | null)?.id ?? null));
          } else {
            const d = (body as { detail?: { reason?: string; detail?: string } } | null)?.detail ?? {};
            setNote({ tone: "error", text: recordReasonText(d.reason ?? `http_${r.status}`, d.detail) });
          }
        } catch {
          setNote({ tone: "error", text: "The backend did not answer: nothing was asked." });
        } finally {
          setSending(null);
        }
      })();
    },
    [base],
  );

  const dismiss = useCallback((id: string) => setToasts((old) => old.filter((t) => t.id !== id)), []);

  return {
    model,
    label: toolbarLabel(model),
    toasts,
    note,
    sending,
    notifyChoice,
    notifyText: notifyPlanText(plan),
    setNotifyChoice,
    act,
    dismiss,
  };
}

const TOAST_TONE: Record<string, string> = {
  action: "border-amber-500 bg-amber-950/95 text-amber-50",
  warn: "border-red-700 bg-red-950/95 text-red-100",
  info: "border-sky-700 bg-sky-950/90 text-sky-100",
};

/** The guide's notifications over the stream view (newest last). */
export function RouteRecToasts({ rr }: { rr: RouteRec }) {
  if (rr.toasts.length === 0) return null;
  return (
    <div className="flex flex-col items-end gap-1.5" aria-live="polite">
      {rr.toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          className={`flex max-w-md items-start gap-2 rounded-md border px-3 py-1.5 text-sm shadow-lg ${TOAST_TONE[t.level] ?? TOAST_TONE.info}`}
        >
          <span>{t.text}</span>
          <button
            type="button"
            className="pointer-events-auto text-xs opacity-70 hover:opacity-100"
            title="Hide"
            onClick={() => rr.dismiss(t.id)}
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}

const button =
  "rounded-md border border-neutral-700 bg-neutral-900 px-2.5 py-1 text-sm hover:bg-neutral-800 disabled:opacity-40";
const stopButton =
  "rounded-md border border-red-500 bg-red-900/60 px-2.5 py-1 text-sm font-semibold text-red-100 hover:bg-red-900 disabled:opacity-40";

const MARK: Record<string, { sign: string; cls: string }> = {
  ok: { sign: "✓", cls: "text-emerald-400" },
  bad: { sign: "✗", cls: "text-red-400" },
  info: { sign: "·", cls: "text-neutral-400" },
};

const DISK_TONE: Record<string, string> = {
  ok: "text-emerald-300",
  warn: "text-amber-300",
  bad: "text-red-300",
  unknown: "text-neutral-300",
};

/** The panel under the toolbar: readiness, the disk, the recording, and Check / Start / Stop. */
export default function RouteRecPanel({ rr }: { rr: RouteRec }) {
  const m = rr.model;
  return (
    <section data-layout="routerec-panel" className="rounded-md border border-neutral-800 p-3 text-sm" aria-label="Record route">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`font-medium ${m.rec ? "text-red-300" : ""}`}>{m.headline}</span>
        {m.helper === "down" && <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-300">helper not running</span>}
      </div>
      {m.items.length > 0 && (
        <ul className="mt-2 space-y-0.5">
          {m.items.map((it) => {
            const mk = MARK[it.ok === null ? "info" : it.ok ? "ok" : "bad"];
            return (
              <li key={it.key} className="flex gap-2">
                <span className={`w-4 shrink-0 text-center ${mk.cls}`} aria-hidden>
                  {mk.sign}
                </span>
                <span>{it.text}</span>
              </li>
            );
          })}
        </ul>
      )}
      {m.disk && <p className={`mt-2 ${DISK_TONE[m.disk.level]}`}>{m.disk.text}</p>}
      {m.rec && (
        <p className="mt-2 font-mono text-xs text-neutral-300">
          {m.rec.elapsed} · {m.rec.size} · {m.rec.left} · {m.rec.map} · {m.rec.split}
        </p>
      )}
      {m.last && !m.rec && <p className="mt-2 text-xs text-neutral-400">{m.last}</p>}
      {rr.note && <p className={`mt-2 ${rr.note.tone === "error" ? "text-red-300" : "text-neutral-300"}`}>{rr.note.text}</p>}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button type="button" className={button} disabled={!m.canCheck || rr.sending !== null} onClick={() => rr.act("check")}>
          {rr.sending === "check" || m.checking ? "Checking…" : "Check"}
        </button>
        <button
          type="button"
          className={button}
          title="Checks the game screen first; the recording starts only when it is ready"
          disabled={!m.canStart || rr.sending !== null}
          onClick={() => rr.act("start")}
        >
          Start recording
        </button>
        <button type="button" className={stopButton} disabled={!m.canStop || rr.sending !== null} onClick={() => rr.act("stop")}>
          Stop
        </button>
        <label className="ml-auto flex items-center gap-1.5 text-xs text-neutral-400" title={rr.notifyText}>
          <input
            type="checkbox"
            checked={rr.notifyChoice === "on"}
            onChange={(e) => rr.setNotifyChoice(e.target.checked ? "on" : "off")}
          />
          Browser notifications
        </label>
      </div>
      <p className="mt-1 text-xs text-neutral-500">{rr.notifyText}</p>
    </section>
  );
}
