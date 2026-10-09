"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { FEED_KINDS, type FeedKind, type FeedView, type Tone } from "@/lib/feeds";
import {
  counterText,
  type HudFrame,
  hudAlive,
  lockedIndex,
  lockRemainingMs,
  lockText,
  logLines,
  plain,
  walkPx,
} from "@/lib/hud";
import { atBottom } from "@/lib/scroll";

type Props = { hud: HudFrame | null; feeds: Record<FeedKind, FeedView> };

const TONE: Record<Tone, string> = {
  none: "",
  grey: "text-neutral-500",
  amber: "text-amber-300",
};

/** The operator HUD's text half (Batt 2026-10-08): the rule's plain-words log, its counters, the
 * walk vector's text and the lock's countdown, under the stream so it never covers the game. Every
 * value is a React text node (never markup). It keeps the last message on screen, marked stale
 * once its ttl has passed, so a stopped rule's last words stay readable.
 *
 * A FIXED layout (Batt 2026-10-09 14:24): the status block on the left (fixed width, one line per
 * row), the decision log on the right (fixed height: all 12 lines of a message at desktop widths;
 * its own scroll, it follows new lines only
 * while the reader is at the newest), and a reserved three-line slot for the feed lines (empty
 * when fresh, grey when idle, amber when stopped: lib/feeds.ts). Nothing that arrives, goes stale
 * or comes back changes any box; only the narrow (< md) breakpoint stacks the columns. */
export default function HudPanel({ hud, feeds }: Props) {
  const [now, setNow] = useState<number | null>(null);
  const logRef = useRef<HTMLOListElement>(null);
  const followRef = useRef(true); // the reader is at the newest line

  useEffect(() => {
    if (!hud) return;
    const timer = setInterval(() => setNow(performance.now()), 200);
    return () => clearInterval(timer);
  }, [hud]);

  const msg = hud?.msg ?? null;
  const age = hud == null || now == null ? 0 : Math.max(0, now - hud.at);
  const alive = hud != null && hudAlive(msg, age);
  const walk = walkPx(msg, 1, 1);
  const lock = msg?.lock ? lockText(lockRemainingMs(msg, age)) : "";
  const lockInView = lockedIndex(msg) >= 0;
  const lines = logLines(msg);
  const logKey = lines.join("\n");

  // New lines append without moving the box; scroll to them only if the reader was at the newest.
  useLayoutEffect(() => {
    const box = logRef.current;
    if (box && followRef.current) box.scrollTop = box.scrollHeight;
  }, [logKey]);

  const rows: [string, string, string][] = [
    ["rule", msg ? plain(msg.label, 64) || "–" : "–", ""],
    ["units", msg ? counterText(msg) : "–", ""],
    ["walk", walk ? walk.text || "–" : "–", ""],
    ["lock", lock ? `${lock}${lockInView ? "" : " (target not in view)"}` : "–", lock ? "text-fuchsia-300" : ""],
    ["state", !hud ? "waiting for the agent" : alive ? "live" : `stale (${(age / 1000).toFixed(1)} s)`, ""],
  ];

  return (
    <section
      className={`rounded-md border border-neutral-800 p-3 text-xs ${hud && !alive ? "opacity-60" : ""}`}
      aria-label="Operator HUD"
    >
      <div className="grid gap-x-4 gap-y-2 md:grid-cols-[24rem_minmax(0,1fr)]">
        <div data-layout="hud-status" className="h-32 overflow-hidden md:h-52">
          <dl className="grid grid-cols-[3.5rem_minmax(0,1fr)] content-start gap-x-3 gap-y-1 font-mono">
            {rows.map(([label, value, tone]) => (
              <div key={label} className="contents">
                <dt className="text-neutral-500">{label}</dt>
                <dd className={`truncate ${tone}`} title={value}>
                  {value}
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-neutral-500">Display only; this tab sends nothing for it.</p>
        </div>
        <ol
          ref={logRef}
          data-layout="hud-log"
          aria-label="Decision log"
          onScroll={(e) => {
            followRef.current = atBottom(e.currentTarget);
          }}
          className="h-52 overflow-y-auto rounded border border-neutral-900 px-2 py-1 font-mono text-neutral-200 [overflow-anchor:none]"
        >
          {!hud ? (
            <li className="text-neutral-500">Operator HUD: waiting for the agent.</li>
          ) : lines.length === 0 ? (
            <li className="text-neutral-500">(no log lines)</li>
          ) : (
            lines.map((line, i) => (
              <li key={`${i}:${line}`} className="whitespace-pre-wrap break-words">
                {line}
              </li>
            ))
          )}
        </ol>
        <ul
          data-layout="hud-feeds"
          aria-label="Why the overlays are empty"
          className="h-12 overflow-hidden font-mono md:col-span-2"
        >
          {FEED_KINDS.map((kind) => {
            const view = feeds[kind];
            return (
              <li key={kind} className={`h-4 truncate ${TONE[view.tone]}`} title={view.text || undefined}>
                {view.text}
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
