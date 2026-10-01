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
