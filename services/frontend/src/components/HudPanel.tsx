"use client";

import { useEffect, useState } from "react";

import type { Status } from "@/lib/protocol";
import {
  counterText,
  feedLine,
  type HudFrame,
  hudAlive,
  lockedIndex,
  lockRemainingMs,
  lockText,
  logLines,
  plain,
  walkPx,
} from "@/lib/hud";

type Props = { hud: HudFrame | null; status: Status | null };

/** The operator HUD's text half (Batt 2026-10-08): the rule's plain-words log, its counters, the
 * walk vector's text and the lock's countdown, under the stream so it never covers the game. Every
 * value is a React text node (never markup). It keeps the last message on screen, marked stale
 * once its ttl has passed, so a stopped rule's last words stay readable. */
export default function HudPanel({ hud, status }: Props) {
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    if (!hud) return;
    const timer = setInterval(() => setNow(performance.now()), 200);
    return () => clearInterval(timer);
  }, [hud]);

  // WHY it may be empty (Batt 2026-10-08): no publisher, a stopped one, or an old backend
  const why = [feedLine("HUD", status), feedLine("Route preview", status)].filter((l): l is string => l != null);
  const reasons =
    why.length > 0 ? (
      <ul className="font-mono text-amber-300" aria-label="Why the overlays are empty">
        {why.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    ) : null;

  if (!hud) {
    return (
      <section className="grid gap-1 rounded-md border border-neutral-800 p-3 text-xs text-neutral-400">
        <span>Operator HUD: waiting for the agent. Display only; this tab sends nothing for it.</span>
        {reasons}
      </section>
    );
  }
  const msg = hud.msg;
  const age = now == null ? 0 : Math.max(0, now - hud.at);
  const alive = hudAlive(msg, age);
  const walk = walkPx(msg, 1, 1);
  const lock = msg.lock ? lockText(lockRemainingMs(msg, age)) : "";
  const lockInView = lockedIndex(msg) >= 0;
  const lines = logLines(msg);

  return (
    <section
      className={`grid gap-3 rounded-md border border-neutral-800 p-3 text-xs md:grid-cols-[1fr_2fr] ${alive ? "" : "opacity-60"}`}
      aria-label="Operator HUD"
    >
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 font-mono">
        <dt className="text-neutral-500">rule</dt>
        <dd>{plain(msg.label, 64) || "–"}</dd>
        <dt className="text-neutral-500">units</dt>
        <dd>{counterText(msg)}</dd>
        <dt className="text-neutral-500">walk</dt>
        <dd>{walk ? walk.text || "–" : "–"}</dd>
        <dt className="text-neutral-500">lock</dt>
        <dd className={lock ? "text-fuchsia-300" : ""}>
          {lock ? `${lock}${lockInView ? "" : " (target not in view)"}` : "–"}
        </dd>
        <dt className="text-neutral-500">state</dt>
        <dd>{alive ? "live" : `stale (${(age / 1000).toFixed(1)} s)`}</dd>
      </dl>
      {reasons && <div className="md:col-span-2">{reasons}</div>}
      <ol className="min-h-[3rem] font-mono text-neutral-200">
        {lines.length === 0 ? (
          <li className="text-neutral-500">(no log lines)</li>
        ) : (
          lines.map((line, i) => <li key={`${i}:${line}`}>{line}</li>)
        )}
      </ol>
    </section>
  );
}
