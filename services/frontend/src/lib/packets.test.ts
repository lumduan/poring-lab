import assert from "node:assert/strict";
import { test } from "node:test";

import {
  describe,
  KINDS,
  kindOf,
  parseFeed,
  summarize,
  Timeline,
  type PacketEvent,
  type PacketStats,
} from "./packets.ts";

const base = { server: "map", dir: "sc", validation_account: false, gm_command: false } as const;

function chat(text: string, t = 1, extra: Partial<PacketEvent> = {}): PacketEvent {
  return {
    ...base, t_mono_ns: t, packet_id: 0x8d, type: "chat", kind: "public", gid: 7,
    speaker: "Poring", text, raw_hex: "", ...extra,
  } as PacketEvent;
}

test("parseFeed accepts events and stats, refuses junk and error replies", () => {
  assert.equal(parseFeed(JSON.stringify(chat("hi")))?.type, "chat");
  assert.equal(parseFeed('{"type":"packet_stats"}')?.type, "packet_stats");
  assert.equal(parseFeed("not json"), null);
  assert.equal(parseFeed('{"type":"error","channel":"ws_packets"}'), null);
  assert.equal(parseFeed("[1,2]"), null);
});

test("every event type maps to a kind the panel can filter", () => {
  assert.equal(kindOf(chat("x")), "chat");
  const walk = { ...base, t_mono_ns: 1, packet_id: 0x87, type: "self_move", server_tick: 5,
    x0: 1, y0: 1, x1: 3, y1: 2 } as PacketEvent;
  assert.equal(kindOf(walk), "self");
  assert.equal(describe(walk), "walk (1,1) → (3,2) @tick 5");
  const unknown = { ...base, t_mono_ns: 1, packet_id: 0xabc, type: "unknown", count: 2 } as PacketEvent;
  assert.equal(kindOf(unknown), "error");
  assert.equal(describe(unknown), "unknown packet 0x0abc ×2");
  assert.ok(KINDS.includes("session"));
});

test("the timeline is newest-first, filterable, and counts what it evicts", () => {
  const tl = new Timeline(3);
  for (let i = 0; i < 5; i++) tl.push(chat(`m${i}`, i));
  assert.equal(tl.received, 5);
  assert.equal(tl.evicted, 2);
  const all = new Set(KINDS);
  assert.deepEqual(tl.view(all, false).map((e) => (e.type === "chat" ? e.text : "")), ["m4", "m3", "m2"]);
  assert.deepEqual(tl.view(new Set(["entity"] as const), false), []);
});

test("validation-account and GM-command events can be hidden", () => {
  const tl = new Timeline();
  tl.push(chat("@where", 1, { gm_command: true }));
  tl.push(chat("gm session", 2, { validation_account: true }));
  tl.push(chat("player", 3));
  const shown = tl.view(new Set(KINDS), true);
  assert.deepEqual(shown.map((e) => (e.type === "chat" ? e.text : "")), ["player"]);
});

test("Thai chat text is shown as decoded", () => {
  assert.equal(describe(chat("สวัสดี")), "public Poring: สวัสดี");
});

test("the stats summary names every decode problem (never silent)", () => {
  const s: PacketStats = {
    type: "packet_stats", t_mono_ns: 1, packets: 120, unknown: 2, desyncs: 1, skipped_bytes: 40,
    tcp_gaps: 0, clock_steps: 0, map: "prontera", self_x: 150, self_y: 180.5, entities: 4,
    hp: 40, max_hp: 50, sp: null, max_sp: null, ingest_dropped: 3,
  };
  const [world, counters] = summarize(s);
  assert.match(world, /map prontera · self \(150\.0,180\.5\) · 4 entities · HP 40\/50 · SP –/);
  assert.match(counters, /2 unknown · 1 desyncs \(40 B skipped\) · 3 dropped before the backend/);
  assert.deepEqual(summarize(null), ["no stats from the sniffer yet"]);
});

test("actions and turns are entity events with a readable line (M3)", () => {
  const act = (kind: string, damage: number, extra: object = {}) =>
    ({
      ...base, t_mono_ns: 1, packet_id: 0x8c8, type: "act", src_gid: 7, target_gid: 2000001,
      server_tick: 5, src_speed: 672, dmotion: 480, damage, damage2: 0, div: 1, action: 0, kind,
      sp_damage: false, ...extra,
    }) as PacketEvent;
  assert.equal(kindOf(act("normal", 12)), "entity");
  assert.equal(describe(act("normal", 12)), "#7 → #2000001 normal 12 (672/480 ms)");
  assert.equal(describe(act("normal", 0)), "#7 → #2000001 normal miss (672/480 ms)");
  assert.equal(describe(act("multi_hit", 30, { div: 2 })), "#7 → #2000001 multi_hit 30 ×2 (672/480 ms)");
  assert.equal(describe(act("sit", 0, { target_gid: 0 })), "#7 sits");
  const turn = { ...base, t_mono_ns: 1, packet_id: 0x9c, type: "entity_turn", gid: 7, heading: 6,
    head_dir: 0 } as PacketEvent;
  assert.equal(kindOf(turn), "entity");
  assert.equal(describe(turn), "turn #7 → 6");
});

test("NPC, shop, stat and attack-click events get a kind and a line (2026-10-07, replay only)", () => {
  const ev = (type: string, fields: object, dir: "cs" | "sc" = "sc") =>
    ({ ...base, dir, t_mono_ns: 1, packet_id: 1, type, ...fields }) as PacketEvent;
  const menu = ev("npc_menu", { npc_gid: 9, options: ["a", "", "c"], raw_hex: "" });
  assert.equal(kindOf(menu), "session");
  assert.equal(describe(menu), "NPC #9 menu: 1) a · 2)  · 3) c");
  const choose = ev("npc_choose", { npc_gid: 9, choice: 255, cancelled: true }, "cs");
  assert.equal(kindOf(choose), "self");
  assert.equal(describe(choose), "NPC #9 menu cancelled");
  const click = ev("attack_request", { target_gid: 7, action: 7, kind: "repeat", is_attack: true }, "cs");
  assert.equal(kindOf(click), "self");
  assert.equal(describe(click), "attack click #7 (keep attacking)");
  const sit = ev("attack_request", { target_gid: 0, action: 2, kind: "sit", is_attack: false }, "cs");
  assert.equal(describe(sit), "action request sit");
  assert.equal(describe(ev("shop_buy_result", { result: 1, ok: false })), "buy result 1: no deal");
  const raised = ev("stat_raise_result", { stat: 13, name: "str", ok: true, value: 2 });
  assert.equal(kindOf(raised), "stat");
  assert.equal(describe(raised), "str raised to 2");
  const buy = ev("shop_buy_request", { items: [{ item_id: 9001, amount: 3 }] }, "cs");
  assert.equal(describe(buy), "buy 3× item 9001");
});

test("floor items, pickups and drops get a kind and a line (2026-10-08 loot@1, replay only)", () => {
  const ev = (type: string, fields: object, dir: "cs" | "sc" = "sc") =>
    ({ ...base, dir, t_mono_ns: 1, packet_id: 1, type, ...fields }) as PacketEvent;
  const fall = ev("floor_item_appear", { kind: "fall", floor_id: 77, item_id: 9001, item_type: 3,
    identified: true, x: 150, y: 201, sub_x: 4, sub_y: 9, amount: 2, drop_effect: false });
  assert.equal(kindOf(fall), "entity");
  assert.equal(describe(fall), "item falls #77: 2× item 9001 (150,201)");
  assert.equal(describe(ev("floor_item_vanish", { floor_id: 77 })), "item #77 gone from the floor");
  const pick = ev("pickup_request", { floor_id: 77 }, "cs");
  assert.equal(kindOf(pick), "self");
  assert.equal(describe(pick), "pick up #77");
  const got = ev("pickup_result", { index: 7, amount: 2, item_id: 9001, identified: true,
    item_type: 3, result: 0, reason: "ok", ok: true, refine: 0 });
  assert.equal(kindOf(got), "session");
  assert.equal(describe(got), "got 2× item 9001 (slot 7)");
  const refused = ev("pickup_result", { index: 2, amount: 0, item_id: 0, identified: false,
    item_type: 0, result: 6, reason: "refused", ok: false, refine: 0 });
  assert.equal(describe(refused), "pickup failed: refused");
  assert.equal(describe(ev("drop_request", { index: 6, amount: 1 }, "cs")), "drop 1× slot 6");
  assert.equal(describe(ev("drop_result", { index: 6, amount: 0, ok: false })), "drop of slot 6 refused");
});

// --- the source state (Batt 2026-10-09 ~14:40) ---------------------------------------------------
import { clockText, SOURCE_REPORT_STALE_MS, sourceView, type PacketSource } from "./packets.ts";

const T_1431 = Date.UTC(2026, 9, 9, 7, 31, 5); // 14:31:05 ICT
function source(extra: Partial<PacketSource> = {}): PacketSource {
  return {
    type: "packet_source", t_mono_ns: 1, state: "live", reason: "ok", ingest_connected: true,
    heartbeat_age_ms: 400, stale_after_ms: 5000, last_feed_unix_ms: T_1431 + 60_000,
    last_event_unix_ms: T_1431, ...extra,
  };
}
const TZ = "Asia/Bangkok";

test("wall times are formatted HH:MM:SS (the backend's unix ms; never a cross-clock subtraction)", () => {
  assert.equal(clockText(T_1431, TZ), "14:31:05");
  assert.equal(clockText(Date.UTC(2026, 9, 9, 17, 0, 9), TZ), "00:00:09");
});

test("live: the heartbeat and the last game packet; an empty list still says why", () => {
  const v = sourceView({ connected: true, source: source(), receivedAgoMs: 300, rows: 0, timeZone: TZ });
  assert.equal(v.kind, "live");
  assert.equal(v.line, "Sniffer live · heartbeat 0.4 s ago · last game packet 14:31:05");
  assert.match(v.note ?? "", /no game packets in this tab yet/); // never a bare empty list
  assert.equal(sourceView({ connected: true, source: source(), receivedAgoMs: 300, rows: 5 }).note, null);
  const idle = sourceView({ connected: true, source: source({ last_event_unix_ms: null }), receivedAgoMs: 0, rows: 0 });
  assert.match(idle.line, /no game packet since the backend started/);
});

test("sniffer offline: 'Sniffer offline (no packets since HH:MM:SS)', in the list too, rows dimmed", () => {
  const off = source({ state: "sniffer_offline", reason: "heartbeat_stale", heartbeat_age_ms: 9000 });
  const v = sourceView({ connected: true, source: off, receivedAgoMs: 200, rows: 12, timeZone: TZ });
  assert.equal(v.kind, "sniffer_offline");
  assert.equal(v.line, "Sniffer offline (no packets since 14:32:05) · its 1 Hz heartbeat stopped");
  assert.equal(v.note, v.line);
  assert.equal(v.dim, true);
  const never = source({ state: "sniffer_offline", reason: "never_heard", last_feed_unix_ms: null, last_event_unix_ms: null });
  assert.match(sourceView({ connected: true, source: never, receivedAgoMs: 0, rows: 0 }).line,
    /^Sniffer offline \(no packets since the backend started\)/);
  for (const reason of ["ingest_disconnected", "not_attesting"]) {
    const line = sourceView({ connected: true, source: source({ state: "sniffer_offline", reason }), receivedAgoMs: 0, rows: 0 }).line;
    assert.match(line, /^Sniffer offline/);
  }
});

test("external: the by-design line, shown only when the backend says so", () => {
  const v = sourceView({ connected: true, source: source({ state: "external", reason: "external_environment" }), receivedAgoMs: 0, rows: 3 });
  assert.equal(v.kind, "external");
  assert.equal(v.line, "External server: packet log not available (not captured by design)");
  assert.equal(v.note, v.line);
  assert.equal(v.tone, "neutral");
});

test("disconnected, an old backend, and a backend that stopped reporting are never shown as live", () => {
  assert.equal(sourceView({ connected: false, source: source(), receivedAgoMs: 0, rows: 0 }).kind, "disconnected");
  const old = sourceView({ connected: true, source: null, receivedAgoMs: null, rows: 0 });
  assert.equal(old.kind, "unknown");
  assert.match(old.line, /not reported/);
  assert.match(old.note ?? "", /does not say whether the sniffer is live/);
  const quiet = sourceView({ connected: true, source: source(), receivedAgoMs: SOURCE_REPORT_STALE_MS + 1000, rows: 4 });
  assert.equal(quiet.kind, "unknown");
  assert.match(quiet.line, /no report from the backend for 6 s/);
});

test("every event gets a stable sequence number (row keys survive new arrivals)", () => {
  const t = new Timeline(3);
  const a = chat("a"), b = chat("b"), c = chat("c"), d = chat("d");
  for (const e of [a, b, c]) t.push(e);
  assert.deepEqual([t.seqOf(a), t.seqOf(b), t.seqOf(c)], [1, 2, 3]);
  t.push(d); // evicts a
  assert.deepEqual(t.view(new Set(KINDS), false).map((e) => t.seqOf(e)), [4, 3, 2]);
  assert.equal(t.seqOf(chat("never pushed")), -1);
});
