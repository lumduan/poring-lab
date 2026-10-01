"use client";

import { useEffect, useState } from "react";

import {
  ageSeconds,
  describe,
  KINDS,
  kindOf,
  parseFeed,
  summarize,
  Timeline,
  type Kind,
  type PacketEvent,
  type PacketStats,
} from "@/lib/packets";
import { backendWsBase, ReconnectingSocket } from "@/lib/ws";

type Props = { backendUrl: string | null };

const KIND_TONE: Record<Kind, string> = {
  chat: "text-sky-300",
  self: "text-emerald-300",
  entity: "text-neutral-300",
  stat: "text-violet-300",
  session: "text-neutral-400",
  error: "text-amber-300",
};

const KINDS_ALL: ReadonlySet<Kind> = new Set(KINDS);

type View = { events: PacketEvent[]; stats: PacketStats | null; received: number; evicted: number };

/** ADR-0007 packet ground truth, for the human only. Its own socket to /ws/packets, opened while
 * the panel is expanded; it never sends. Event ages are on the backend clock (the sniffer stamps
 * kernel receive times onto CLOCK_MONOTONIC), against the newest time seen on this socket. */
export default function PacketTimeline({ backendUrl }: Props) {
  const [open, setOpen] = useState(false);
  const [connected, setConnected] = useState(false);
  const [kinds, setKinds] = useState<ReadonlySet<Kind>>(() => new Set(KINDS));
  const [hideValidation, setHideValidation] = useState(false);
  const [timeline] = useState(() => new Timeline(1000));
  const [view, setView] = useState<View>({ events: [], stats: null, received: 0, evicted: 0 });
  const [nowNs, setNowNs] = useState(0);

  useEffect(() => {
    if (!open) return;
    let stats: PacketStats | null = null;
    let newest = 0;
    let dirty = true;
    const socket = new ReconnectingSocket(`${backendWsBase(backendUrl)}/ws/packets`, {
      onOpen: () => setConnected(true),
      onClose: () => setConnected(false),
      onText: (text) => {
        const msg = parseFeed(text);
        if (!msg) return;
        if (msg.type === "packet_stats") stats = msg;
        else timeline.push(msg);
        newest = Math.max(newest, msg.t_mono_ns);
        dirty = true;
      },
    });
    // Repaint at most 4 times a second: entity bursts arrive by the hundred.
    const timer = setInterval(() => {
      if (!dirty) return;
      dirty = false;
      setNowNs(newest);
      setView({
        events: timeline.view(KINDS_ALL, false, 1000),
        stats,
        received: timeline.received,
        evicted: timeline.evicted,
      });
    }, 250);
    return () => {
      clearInterval(timer);
      socket.close();
      setConnected(false);
    };
  }, [open, backendUrl, timeline]);

  const shown = view.events
    .filter((e) => kinds.has(kindOf(e)) && !(hideValidation && (e.validation_account || e.gm_command)))
    .slice(0, 200);
  const toggle = (k: Kind) => {
    const next = new Set(kinds);
    if (next.has(k)) next.delete(k);
    else next.add(k);
    setKinds(next);
  };

  return (
    <details
      className="rounded-md border border-neutral-800 p-3"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary className="cursor-pointer text-sm font-medium">
        Packet timeline <span className="text-xs text-neutral-500">(ground truth, human view only)</span>
      </summary>
      <div className="mt-2 flex flex-col gap-2 text-sm">
        <div className="font-mono text-xs text-neutral-400">
          {!connected ? (
            <p className="text-amber-300">/ws/packets disconnected: reconnecting… (is the sniffer up?)</p>
          ) : (
            summarize(view.stats).map((line) => <p key={line}>{line}</p>)
          )}
          <p>
            {view.received} events received in this tab
            {view.evicted ? ` · ${view.evicted} oldest evicted` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs">
          {KINDS.map((k) => (
            <label key={k} className={`flex items-center gap-1 ${KIND_TONE[k]}`}>
              <input type="checkbox" checked={kinds.has(k)} onChange={() => toggle(k)} />
              {k}
            </label>
          ))}
          <label className="flex items-center gap-1 text-neutral-400">
            <input
              type="checkbox"
              checked={hideValidation}
              onChange={(e) => setHideValidation(e.target.checked)}
            />
            hide validation / GM
          </label>
        </div>
        <ol className="max-h-80 overflow-y-auto font-mono text-xs">
          {shown.map((e, i) => (
            <li key={`${e.t_mono_ns}-${i}`} className={`flex gap-2 ${KIND_TONE[kindOf(e)]}`}>
              <span className="w-14 shrink-0 text-right text-neutral-500">{ageSeconds(e, nowNs)}</span>
              <span className="w-8 shrink-0 text-neutral-500">{e.dir === "cs" ? "C→S" : "S→C"}</span>
              <span className="break-all">
                {describe(e)}
                {e.gm_command ? " [gm]" : ""}
                {e.validation_account ? " [validation]" : ""}
              </span>
            </li>
          ))}
        </ol>
      </div>
    </details>
  );
}
