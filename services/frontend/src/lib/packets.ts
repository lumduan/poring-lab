// Hand-written helpers around the GENERATED packet-event types (packets.gen.ts, ADR-0007).
// The console's "Packet timeline" is a HUMAN view of offline ground truth: nothing here ever feeds
// an input, and the agent cannot open /ws/packets (the backend refuses compose peers).

import type { PacketStats, PoringPackets } from "./packets.gen";

export type * from "./packets.gen";

export type PacketEvent = PoringPackets["event"];
export type FeedMessage = PacketEvent | PacketStats;

export const KINDS = ["chat", "self", "entity", "stat", "session", "error"] as const;
export type Kind = (typeof KINDS)[number];

export function kindOf(e: PacketEvent): Kind {
  switch (e.type) {
    case "chat":
      return "chat";
    case "self_move":
    case "self_move_request":
    case "map_enter":
    case "map_change":
      return "self";
    case "entity_appear":
    case "entity_vanish":
    case "entity_stop":
      return "entity";
    case "stat_change":
      return "stat";
    case "unknown":
    case "desync":
      return "error";
    default:
      return "session"; // login_accepted, char_selected, time_sync
  }
}

/** One text frame from /ws/packets; null for anything that is not a packet event or stats. The
 * backend re-serialises every line through the same Pydantic models the types come from. */
export function parseFeed(text: string): FeedMessage | null {
  try {
    const msg = JSON.parse(text) as { type?: unknown };
    return typeof msg?.type === "string" && msg.type !== "error" ? (msg as FeedMessage) : null;
  } catch {
    return null;
  }
}

/** Newest-last ring of events with eviction counted (never silent). */
export class Timeline {
  private items: PacketEvent[] = [];
  received = 0;
  evicted = 0;
  readonly capacity: number;

  constructor(capacity = 500) {
    this.capacity = capacity;
  }

  push(e: PacketEvent): void {
    this.items.push(e);
    this.received += 1;
    if (this.items.length > this.capacity) {
      this.items.shift();
      this.evicted += 1;
    }
  }

  /** Newest first, filtered by kind; validation-account / GM-command events optionally hidden. */
  view(kinds: ReadonlySet<Kind>, hideValidation: boolean, limit = 200): PacketEvent[] {
    const out: PacketEvent[] = [];
    for (let i = this.items.length - 1; i >= 0 && out.length < limit; i--) {
      const e = this.items[i];
      if (!kinds.has(kindOf(e))) continue;
      if (hideValidation && (e.validation_account || e.gm_command)) continue;
      out.push(e);
    }
    return out;
  }
}

const cell = (x: number, y: number) => `(${x},${y})`;

/** A one-line, human-readable summary. */
export function describe(e: PacketEvent): string {
  switch (e.type) {
    case "chat":
      return `${e.kind}${e.speaker ? ` ${e.speaker}` : ""}: ${e.text}`;
    case "self_move":
      return `walk ${cell(e.x0, e.y0)} → ${cell(e.x1, e.y1)} @tick ${e.server_tick}`;
    case "self_move_request":
      return `click-to-walk ${cell(e.x, e.y)}`;
    case "map_enter":
      return `on map at ${cell(e.x, e.y)} facing ${e.facing}`;
    case "map_change":
      return `→ ${e.map} ${cell(e.x, e.y)}`;
    case "entity_appear": {
      const dest = e.x1 != null && e.y1 != null ? ` → ${cell(e.x1, e.y1)}` : "";
      return `${e.kind} #${e.gid} ${e.name || `job ${e.job}`} ${cell(e.x, e.y)}${dest}`;
    }
    case "entity_vanish":
      return `gone #${e.gid} (${VANISH[e.reason] ?? e.reason})`;
    case "entity_stop":
      return `stop #${e.gid} ${cell(e.x, e.y)}`;
    case "stat_change":
      return `${e.name} = ${e.value}`;
    case "login_accepted":
      return `login accepted (aid ${e.aid})`;
    case "char_selected":
      return `character ${e.char_id} → ${e.map}`;
    case "time_sync":
      return `server tick ${e.server_tick}`;
    case "unknown":
      return `unknown packet 0x${e.packet_id.toString(16).padStart(4, "0")} ×${e.count}`;
    case "desync":
      return `stream desync: ${e.skipped_bytes} bytes skipped`;
  }
}

const VANISH: Record<number, string> = {
  0: "out of sight",
  1: "died",
  2: "logged out",
  3: "teleport",
  4: "trick dead",
};

/** Event age against the newest backend-clock time we have seen (both CLOCK_MONOTONIC). */
export function ageSeconds(e: PacketEvent, nowNs: number): string {
  const s = Math.max(0, (nowNs - e.t_mono_ns) / 1e9);
  return s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)} min`;
}

/** Status line from the sniffer's 1 Hz stats ("never silent" counters included). */
export function summarize(s: PacketStats | null): string[] {
  if (!s) return ["no stats from the sniffer yet"];
  const pos = s.self_x != null && s.self_y != null ? `(${s.self_x.toFixed(1)},${s.self_y.toFixed(1)})` : "–";
  const hp = s.hp != null && s.max_hp != null ? `${s.hp}/${s.max_hp}` : "–";
  const sp = s.sp != null && s.max_sp != null ? `${s.sp}/${s.max_sp}` : "–";
  const problems = [
    s.unknown ? `${s.unknown} unknown` : "",
    s.desyncs ? `${s.desyncs} desyncs (${s.skipped_bytes} B skipped)` : "",
    s.tcp_gaps ? `${s.tcp_gaps} TCP gaps` : "",
    s.clock_steps ? `${s.clock_steps} clock steps` : "",
    s.ingest_dropped ? `${s.ingest_dropped} dropped before the backend` : "",
  ].filter(Boolean);
  return [
    `map ${s.map ?? "–"} · self ${pos} · ${s.entities} entities · HP ${hp} · SP ${sp}`,
    `${s.packets} packets${problems.length ? ` · ${problems.join(" · ")}` : " · no decode problems"}`,
  ];
}
