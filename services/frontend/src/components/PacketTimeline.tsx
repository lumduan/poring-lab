"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

import {
  ageSeconds,
  describe,
  KINDS,
  kindOf,
  parseFeed,
  sourceView,
  summarize,
  Timeline,
  type Kind,
  type PacketEvent,
  type PacketSource,
  type PacketStats,
  type SourceView,
} from "@/lib/packets";
import { atTop, keepAnchor } from "@/lib/scroll";
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

const SOURCE_TONE: Record<SourceView["tone"], string> = {
  ok: "text-emerald-300",
  amber: "text-amber-300",
  neutral: "text-sky-300",
};

const KINDS_ALL: ReadonlySet<Kind> = new Set(KINDS);

type View = {
  events: PacketEvent[];
  stats: PacketStats | null;
  received: number;
  evicted: number;
  source: PacketSource | null;
  sourceAt: number | null; // this tab's clock (performance.now()) when the source line arrived
  now: number; // this tab's clock at this repaint
};

/** ADR-0007 packet ground truth, for the human only. Its own socket to /ws/packets, opened while
 * the panel is expanded; it never sends. Event ages are on the backend clock (the sniffer stamps
 * kernel receive times onto CLOCK_MONOTONIC), against the newest time seen on this socket.
 *
 * Its SOURCE STATE (Batt 2026-10-09 ~14:40) is always on its own line, and inside the list when
 * the list would be empty or its rows are history: sniffer live / offline since HH:MM:SS /
 * external by design (lib/packets.ts sourceView). Stable (14:24): every block has a fixed height,
 * the list scrolls inside a fixed box, and a reader scrolled down to older rows keeps them in
 * place while new rows arrive at the top. */
export default function PacketTimeline({ backendUrl }: Props) {
  const [open, setOpen] = useState(false);
  const [connected, setConnected] = useState(false);
  const [kinds, setKinds] = useState<ReadonlySet<Kind>>(() => new Set(KINDS));
  const [hideValidation, setHideValidation] = useState(false);
  const [timeline] = useState(() => new Timeline(1000));
  const [view, setView] = useState<View>({
    events: [], stats: null, received: 0, evicted: 0, source: null, sourceAt: null, now: 0,
  }); // fmt: skip
  const [nowNs, setNowNs] = useState(0);
  const listRef = useRef<HTMLOListElement>(null);
  // The row the reader looks at while scrolled away from the newest: its seq and px below the top.
  const anchorRef = useRef<{ seq: string; offset: number } | null>(null);

  useEffect(() => {
    if (!open) return;
    let stats: PacketStats | null = null;
    let source: PacketSource | null = null;
    let sourceAt: number | null = null;
    let newest = 0;
    let dirty = true;
    let painted = 0;
    const socket = new ReconnectingSocket(`${backendWsBase(backendUrl)}/ws/packets`, {
      onOpen: () => setConnected(true),
      onClose: () => {
        setConnected(false);
        source = null; // a new socket gets a fresh line at once; never show an old "live"
        sourceAt = null;
        dirty = true;
      },
      onText: (text) => {
        const msg = parseFeed(text);
        if (!msg) return;
        if (msg.type === "packet_source") {
          source = msg; // the backend's clock: never mixed into the events' ages
          sourceAt = performance.now();
        } else {
          if (msg.type === "packet_stats") stats = msg;
          else timeline.push(msg);
          newest = Math.max(newest, msg.t_mono_ns);
        }
        dirty = true;
      },
    });
    // Repaint at most 4 times a second (entity bursts arrive by the hundred), and at least once a
    // second so "no report for N s" can show when nothing arrives at all.
    const timer = setInterval(() => {
      const now = performance.now();
      if (!dirty && now - painted < 1000) return;
      dirty = false;
      painted = now;
      setNowNs(newest);
      setView({
        events: timeline.view(KINDS_ALL, false, 1000),
        stats,
        received: timeline.received,
        evicted: timeline.evicted,
        source,
        sourceAt,
        now,
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
  const src = sourceView({
    connected,
    source: view.source,
    receivedAgoMs: view.sourceAt == null ? null : Math.max(0, view.now - view.sourceAt),
    rows: shown.length,
  });
  const statLines = summarize(view.stats);
  const toggle = (k: Kind) => {
    const next = new Set(kinds);
    if (next.has(k)) next.delete(k);
    else next.add(k);
    setKinds(next);
  };

  // Rows arrive at the TOP. At the top, the reader sees them; scrolled down, the row they read
  // stays where it is (no jump), whatever arrived above it.
  const rememberAnchor = (box: HTMLOListElement) => {
    if (atTop(box)) {
      anchorRef.current = null;
      return;
    }
    for (const row of box.querySelectorAll<HTMLLIElement>("li[data-seq]")) {
      if (row.offsetTop + row.offsetHeight > box.scrollTop) {
        anchorRef.current = { seq: row.dataset.seq ?? "", offset: row.offsetTop - box.scrollTop };
        return;
      }
    }
  };
  useLayoutEffect(() => {
    const box = listRef.current;
    const anchor = anchorRef.current;
    if (!box || !anchor) return;
    const row = box.querySelector<HTMLLIElement>(`li[data-seq="${anchor.seq}"]`);
    if (row) box.scrollTop = keepAnchor(row.offsetTop, anchor.offset);
  }, [view, kinds, hideValidation]);

  return (
    <details
      data-layout="packet-timeline"
      className="rounded-md border border-neutral-800 p-3"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary className="cursor-pointer text-sm font-medium">
        Packet timeline <span className="text-xs text-neutral-500">(ground truth, human view only)</span>
      </summary>
      <div className="mt-2 flex flex-col gap-2 text-sm">
        <p
          data-layout="packet-source"
          data-state={src.kind}
          title={src.line}
          className={`h-4 truncate font-mono text-xs ${SOURCE_TONE[src.tone]}`}
        >
          {src.line}
        </p>
        <div className="h-12 overflow-hidden font-mono text-xs text-neutral-400">
          <p className="h-4 truncate">{statLines[0] ?? ""}</p>
          <p className="h-4 truncate">{statLines[1] ?? ""}</p>
          <p className="h-4 truncate">
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
        <ol
          ref={listRef}
          onScroll={(e) => rememberAnchor(e.currentTarget)}
          aria-label="Packet events, newest first"
          className="relative h-80 overflow-y-auto font-mono text-xs [overflow-anchor:none]"
        >
          {src.note && (
            <li
              className={`sticky top-0 z-10 mb-1 border-b border-neutral-800 bg-neutral-950 py-1 ${SOURCE_TONE[src.tone]}`}
            >
              {src.note}
            </li>
          )}
          {shown.map((e) => {
            const seq = timeline.seqOf(e);
            return (
              <li
                key={seq}
                data-seq={seq}
                className={`flex gap-2 ${KIND_TONE[kindOf(e)]} ${src.dim ? "opacity-40" : ""}`}
              >
                <span className="w-14 shrink-0 text-right text-neutral-500">{ageSeconds(e, nowNs)}</span>
                <span className="w-8 shrink-0 text-neutral-500">{e.dir === "cs" ? "C→S" : "S→C"}</span>
                <span className="break-all">
                  {describe(e)}
                  {e.gm_command ? " [gm]" : ""}
                  {e.validation_account ? " [validation]" : ""}
                </span>
              </li>
            );
          })}
        </ol>
      </div>
    </details>
  );
}
