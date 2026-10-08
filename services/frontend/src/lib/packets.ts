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
    case "entity_turn":
    case "act":
    case "floor_item_appear": // 2026-10-08 (loot@1): floor items, replay only until a rebuild
    case "floor_item_vanish":
      return "entity";
    // our own requests (2026-10-07 decoders; replay only until the sniffer image is rebuilt)
    case "attack_request":
    case "npc_contact":
    case "npc_choose":
    case "npc_next_click":
    case "npc_close_click":
    case "npc_number_input":
    case "npc_text_input":
    case "shop_deal_choice":
    case "shop_buy_request":
    case "shop_sell_request":
    case "stat_raise_request":
    case "skill_up_request":
    case "equip_request":
    case "unequip_request":
    case "use_item_request":
    case "pickup_request":
    case "drop_request":
      return "self";
    case "stat_change":
    case "stat_raise_result":
    case "skill_update":
    case "skill_list":
      return "stat";
    case "unknown":
    case "desync":
      return "error";
    default:
      return "session"; // login, char select, time sync, NPC dialogs, shop lists, item results
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
    case "entity_turn":
      return `turn #${e.gid} → ${e.heading ?? "?"}`;
    case "act":
      return describeAct(e);
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
    default:
      return describeInteraction(e);
  }
}

/** The 2026-10-07 events: NPC dialogs, shops, stat/skill points, equipment, items, attack clicks.
 * Exhaustive: a new event type without a line here fails the typecheck. */
function describeInteraction(e: Interaction): string {
  const npc = "npc_gid" in e ? `NPC #${e.npc_gid}` : "";
  switch (e.type) {
    case "npc_contact":
      return `click ${npc} (type ${e.contact_type})`;
    case "npc_say":
      return `${npc} says: ${e.text}`;
    case "npc_wait":
      return `${npc} shows next`;
    case "npc_close":
      return `${npc} shows close`;
    case "npc_menu":
      return `${npc} menu: ${e.options.map((o, i) => `${i + 1}) ${o}`).join(" · ")}`;
    case "npc_choose":
      return e.cancelled ? `${npc} menu cancelled` : `${npc} option ${e.choice}`;
    case "npc_next_click":
      return `${npc} next clicked`;
    case "npc_close_click":
      return `${npc} close clicked`;
    case "npc_number_prompt":
      return `${npc} asks for a number`;
    case "npc_number_input":
      return `${npc} ← number ${e.value}`;
    case "npc_text_prompt":
      return `${npc} asks for a text`;
    case "npc_text_input":
      return `${npc} ← text ${e.text}`;
    case "shop_deal_prompt":
      return `${npc} shop: buy or sell?`;
    case "shop_deal_choice":
      return `${npc} shop: ${e.kind}`;
    case "shop_buy_list":
      return `shop list: ${e.items.length} items for sale`;
    case "shop_buy_request":
      return `buy ${e.items.map((i) => `${i.amount}× item ${i.item_id}`).join(", ")}`;
    case "shop_buy_result":
      return e.ok ? "bought: deal done" : `buy result ${e.result}: no deal`;
    case "shop_sell_list":
      return `shop list: ${e.items.length} of ours it buys`;
    case "shop_sell_request":
      return `sell ${e.items.map((i) => `${i.amount}× slot ${i.index}`).join(", ")}`;
    case "shop_sell_result":
      return e.ok ? "sold: deal done" : `sell result ${e.result}: no deal`;
    case "stat_raise_request":
      return `raise ${e.name} +${e.amount}`;
    case "stat_raise_result":
      return e.ok ? `${e.name} raised to ${e.value}` : `${e.name} not raised (${e.value})`;
    case "skill_up_request":
      return `raise skill ${e.skill_id}`;
    case "skill_update":
      return `skill ${e.skill_id} at level ${e.level}`;
    case "skill_list":
      return `skill tree: ${e.skills.length} skills`;
    case "equip_request":
      return `wear slot ${e.index} at ${e.location}`;
    case "equip_result":
      return e.ok ? `wearing slot ${e.index}` : `slot ${e.index} not worn (${e.result})`;
    case "unequip_request":
      return `take off slot ${e.index}`;
    case "unequip_result":
      return e.ok ? `took off slot ${e.index}` : `slot ${e.index} not taken off`;
    case "use_item_request":
      return `use slot ${e.index}`;
    case "use_item_result":
      return `#${e.aid} used item ${e.item_id}: ${e.ok ? `${e.amount} left` : "not used"}`;
    case "attack_request":
      return e.is_attack
        ? `attack click #${e.target_gid}${e.action === 7 ? " (keep attacking)" : ""}`
        : `action request ${e.kind}`;
    case "floor_item_appear":
      return `${e.kind === "fall" ? "item falls" : "item in sight"} #${e.floor_id}: ${e.amount}× item ${e.item_id} ${cell(e.x, e.y)}`;
    case "floor_item_vanish":
      return `item #${e.floor_id} gone from the floor`;
    case "pickup_request":
      return `pick up #${e.floor_id}`;
    case "pickup_result":
      return e.ok ? `got ${e.amount}× item ${e.item_id} (slot ${e.index})` : `pickup failed: ${e.reason}`;
    case "drop_request":
      return `drop ${e.amount}× slot ${e.index}`;
    case "drop_result":
      return e.ok ? `dropped ${e.amount}× slot ${e.index}` : `drop of slot ${e.index} refused`;
  }
}

type Interaction = Exclude<
  PacketEvent,
  {
    type:
      | "chat" | "self_move" | "self_move_request" | "map_enter" | "map_change" | "entity_appear"
      | "entity_vanish" | "entity_stop" | "entity_turn" | "act" | "stat_change"
      | "login_accepted" | "char_selected" | "time_sync" | "unknown" | "desync";
  }
>;

/** ZC_NOTIFY_ACT: sit / stand / pickup, or a hit (0 damage is a miss). */
function describeAct(e: Extract<PacketEvent, { type: "act" }>): string {
  if (e.kind === "sit" || e.kind === "stand") return `#${e.src_gid} ${e.kind}s`;
  if (e.kind === "pickup") return `#${e.src_gid} picks up #${e.target_gid}`;
  const total = e.damage + e.damage2;
  const hits = e.div > 1 ? ` ×${e.div}` : "";
  const what = total === 0 ? "miss" : `${total}${hits}`;
  return `#${e.src_gid} → #${e.target_gid} ${e.kind} ${what} (${e.src_speed}/${e.dmotion} ms)`;
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
