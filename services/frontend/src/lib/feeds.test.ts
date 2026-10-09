import assert from "node:assert/strict";
import { test } from "node:test";

import {
  connectingViews,
  FEED_STALE_MS,
  type FeedObs,
  type FeedState,
  hysteresis,
  NOTHING_SEEN,
  runningRules,
  SCENE_KEYFRAME_MS,
  SCENE_KEYFRAME_PERIODS,
  type Seen,
  stepFeeds,
} from "./feeds.ts";
import type { DisplayFeed, Status } from "./protocol.ts";

const RULE = "rule:walk@17";

type Feeds = { hud?: DisplayFeed | null; route?: DisplayFeed | null; scene?: DisplayFeed | null };

function status(agents: string[] | undefined, f: Feeds): Status {
  const s: Record<string, unknown> = { type: "status", t_mono_ns: 1, mode: "ASSIST" };
  if (agents !== undefined) s.bot_agents = agents;
  if (f.hud !== undefined) s.hud_feed = f.hud;
  if (f.route !== undefined) s.route_feed = f.route;
  if (f.scene !== undefined) s.scene_feed = f.scene;
  return s as unknown as Status;
}

const feed = (relayed: number, age_ms: number | null, source = ""): DisplayFeed => ({ relayed, age_ms, source });

/** A console stepping once a second; `seen` is what it received besides Status. */
class Tab {
  state: FeedState | null = null;
  seen: Seen = structuredClone(NOTHING_SEEN);
  nowMs: number;
  watchSinceMs: number;
  constructor(nowMs = 1_000_000, watchSinceMs = 0) {
    this.nowMs = nowMs;
    this.watchSinceMs = watchSinceMs;
  }
  step(st: Status): FeedState {
    const obs: FeedObs = { status: st, nowMs: this.nowMs, watchSinceMs: this.watchSinceMs, seen: structuredClone(this.seen) };
    this.state = stepFeeds(this.state, obs);
    return this.state;
  }
  keyframe(periodMs = 5000): void {
    this.seen.keyframe = { count: this.seen.keyframe.count + 1, atMs: this.nowMs, periodMs };
  }
  route(active: boolean): void {
    this.seen.route = { atMs: this.nowMs, active };
  }
  hud(ttlMs: number): void {
    this.seen.hud = { atMs: this.nowMs, ttlMs };
  }
  wait(ms: number): void {
    this.nowMs += ms;
  }
}

test("hysteresis: stale once over; fresh again ONLY after a new heartbeat; a reset count re-judges", () => {
  let m = hysteresis(null, false, 3);
  assert.deepEqual(m, { stale: false, beats: 3 });
  m = hysteresis(m, true, 3);
  assert.equal(m.stale, true);
  assert.equal(hysteresis(m, false, 3).stale, true); // back under the threshold, no new message: still stale
  assert.equal(hysteresis(m, false, 4).stale, false); // a new message: fresh
  assert.equal(hysteresis(m, false, 1).stale, false); // the backend restarted (count went down)
});

test("running rules come from Status.bot_agents by the rule: prefix; an older backend says null", () => {
  assert.deepEqual(runningRules(status(["route-preview", RULE, "auto_recover"], {})), [RULE]);
  assert.deepEqual(runningRules(status(["route-preview"], {})), []);
  assert.equal(runningRules(status(undefined, {})), null);
});

test("HUD: idle (grey) -> rule starts (grace) -> fresh -> stale (amber) -> fresh -> idle", () => {
  const tab = new Tab();
  // no rule, channel silent for minutes: neutral grey, never amber
  let s = tab.step(status(["route-preview"], { hud: feed(40, 600_000, RULE) }));
  assert.deepEqual(s.views.HUD, { tone: "grey", text: "HUD: idle (no rule running)" });
  // the rule starts; its HUD has been silent for 10 min: NOT stale at once (grace = one threshold)
  tab.wait(1000);
  s = tab.step(status([RULE], { hud: feed(40, 601_000, RULE) }));
  assert.equal(s.views.HUD.tone, "none");
  tab.wait(FEED_STALE_MS - 1000);
  s = tab.step(status([RULE], { hud: feed(40, 605_000, RULE) }));
  assert.equal(s.views.HUD.tone, "none"); // still within the grace
  // its first HUD arrives (ttl 8 s: the rule's own lifetime for it)
  tab.wait(500);
  tab.hud(8000);
  s = tab.step(status([RULE], { hud: feed(41, 100, RULE) }));
  assert.equal(s.views.HUD.tone, "none");
  // a 6 s click step: under the rule's own 8 s ttl, so no false yellow
  tab.wait(6000);
  s = tab.step(status([RULE], { hud: feed(41, 6100, RULE) }));
  assert.equal(s.views.HUD.tone, "none");
  // it stops sending while it still runs: amber, naming the sender
  tab.wait(3000);
  s = tab.step(status([RULE], { hud: feed(41, 9100, RULE) }));
  assert.equal(s.views.HUD.tone, "amber");
  assert.match(s.views.HUD.text, /last message 9 s ago from rule:walk@17 while it runs/);
  // fresh again only with a NEW message
  tab.wait(1000);
  tab.hud(8000);
  s = tab.step(status([RULE], { hud: feed(42, 50, RULE) }));
  assert.equal(s.views.HUD.tone, "none");
  // the rule ends (it cleared its HUD, ttl 0) and disconnects: grey idle
  tab.wait(1000);
  tab.hud(0);
  s = tab.step(status([RULE], { hud: feed(43, 10, RULE) }));
  assert.deepEqual(s.views.HUD, { tone: "grey", text: "HUD: idle (cleared by rule:walk@17)" });
  tab.wait(1000);
  s = tab.step(status([], { hud: feed(43, 1010, RULE) }));
  assert.equal(s.views.HUD.tone, "none"); // fresh still (1 s old): nothing to explain
  tab.wait(9000);
  s = tab.step(status([], { hud: feed(43, 10_010, RULE) }));
  assert.deepEqual(s.views.HUD, { tone: "grey", text: "HUD: idle (no rule running)" });
});

test("HUD: a rule that never sends a HUD is amber after the grace, worded as such", () => {
  const tab = new Tab();
  tab.step(status([], { hud: feed(5, 900_000, "rule:old") }));
  tab.wait(1000);
  tab.step(status(["rule:safety-check"], { hud: feed(5, 901_000, "rule:old") }));
  tab.wait(FEED_STALE_MS + 1000);
  const s = tab.step(status(["rule:safety-check"], { hud: feed(5, 907_000, "rule:old") }));
  assert.equal(s.views.HUD.tone, "amber");
  assert.match(s.views.HUD.text, /nothing from rule:safety-check since it started 6 s ago/);
});

test("HUD: no flicker around the threshold -- once stale it waits for a new message", () => {
  const tab = new Tab();
  tab.step(status([RULE], { hud: feed(10, 100, RULE) }));
  tab.wait(FEED_STALE_MS + 1000);
  let s = tab.step(status([RULE], { hud: feed(10, FEED_STALE_MS + 1000, RULE) }));
  assert.equal(s.views.HUD.tone, "amber");
  // a backend age that dips under the threshold without a new message (e.g. clock rounding)
  tab.wait(1000);
  s = tab.step(status([RULE], { hud: feed(10, FEED_STALE_MS - 1, RULE) }));
  assert.equal(s.views.HUD.tone, "amber");
});

test("route: idle without a rule; idle while no route is active; amber only mid-route", () => {
  const tab = new Tab();
  let s = tab.step(status([], { route: feed(0, null) }));
  assert.deepEqual(s.views["Route preview"], { tone: "grey", text: "Route preview: idle (no rule running)" });
  // a rule starts; the channel is silent (it types /where, checks windows): no route active
  tab.wait(1000);
  s = tab.step(status([RULE, "route-preview"].sort(), { route: feed(0, null) }));
  tab.wait(20_000);
  s = tab.step(status([RULE, "route-preview"].sort(), { route: feed(0, null) }));
  assert.deepEqual(s.views["Route preview"], { tone: "grey", text: "Route preview: idle (no route active)" });
  // a route starts: ~20 Hz messages
  tab.route(true);
  s = tab.step(status([RULE, "route-preview"].sort(), { route: feed(300, 40, "route-preview") }));
  assert.equal(s.views["Route preview"].tone, "none");
  // the previewer stops mid-route
  tab.wait(FEED_STALE_MS + 1000);
  s = tab.step(status([RULE, "route-preview"].sort(), { route: feed(300, FEED_STALE_MS + 1040, "route-preview") }));
  assert.equal(s.views["Route preview"].tone, "amber");
  assert.match(s.views["Route preview"].text, /mid-route while rule:walk@17 runs/);
  // it resumes, then the walk ends with a clear: grey again
  tab.wait(500);
  tab.route(true);
  s = tab.step(status([RULE, "route-preview"].sort(), { route: feed(301, 30, "route-preview") }));
  assert.equal(s.views["Route preview"].tone, "none");
  tab.wait(500);
  tab.route(false);
  tab.wait(FEED_STALE_MS + 2000);
  s = tab.step(status([RULE, "route-preview"].sort(), { route: feed(302, FEED_STALE_MS + 2000, "route-preview") }));
  assert.deepEqual(s.views["Route preview"], { tone: "grey", text: "Route preview: idle (no route active)" });
});

test("route: an active route left by an EARLIER rule does not make a new rule's channel stale", () => {
  const tab = new Tab();
  tab.route(true); // a crashed rule's route, never cleared
  tab.step(status(["rule:old"], { route: feed(9, 100, "route-preview") }));
  tab.wait(60_000);
  tab.step(status([], { route: feed(9, 60_100, "route-preview") }));
  tab.wait(1000);
  tab.step(status([RULE], { route: feed(9, 61_100, "route-preview") }));
  tab.wait(FEED_STALE_MS * 3);
  const s = tab.step(status([RULE], { route: feed(9, 76_100, "route-preview") }));
  assert.deepEqual(s.views["Route preview"], { tone: "grey", text: "Route preview: idle (no route active)" });
});

test("HUD scene: the KEYFRAME is the heartbeat; deltas do not reset it; 2.5 periods; no flicker", () => {
  const threshold = SCENE_KEYFRAME_PERIODS * SCENE_KEYFRAME_MS; // 12.5 s
  assert.equal(threshold, 12_500);
  const tab = new Tab(1_000_000, 1_000_000);
  // a still scene: no deltas for 3 s is NORMAL (the 2026-10-09 complaint)
  tab.keyframe();
  tab.wait(3000);
  let s = tab.step(status([], { scene: feed(50, 3000, "hud-scene") }));
  assert.equal(s.views["HUD scene"].tone, "none");
  // keyframes every 5 s keep it fresh; then they stop while deltas still arrive (relayed grows)
  tab.wait(2000);
  tab.keyframe();
  tab.wait(threshold); // exactly at the threshold: not over
  s = tab.step(status([], { scene: feed(80, 20, "hud-scene") }));
  assert.equal(s.views["HUD scene"].tone, "none");
  tab.wait(1000);
  s = tab.step(status([], { scene: feed(95, 20, "hud-scene") }));
  assert.equal(s.views["HUD scene"].tone, "amber");
  assert.match(s.views["HUD scene"].text, /no keyframe for 14 s \(one is due every 5 s/);
  // fresh again only with a new KEYFRAME
  tab.wait(1000);
  s = tab.step(status([], { scene: feed(99, 20, "hud-scene") }));
  assert.equal(s.views["HUD scene"].tone, "amber");
  tab.keyframe();
  s = tab.step(status([], { scene: feed(100, 0, "hud-scene") }));
  assert.equal(s.views["HUD scene"].tone, "none");
});

test("HUD scene: a freshly connected tab waits one threshold for its first keyframe", () => {
  const tab = new Tab(5_000_000, 5_000_000);
  let s = tab.step(status([], { scene: feed(1000, 300, "hud-scene") }));
  assert.equal(s.views["HUD scene"].tone, "none");
  tab.wait(13_000);
  s = tab.step(status([], { scene: feed(1010, 300, "hud-scene") }));
  assert.match(s.views["HUD scene"].text, /no keyframe since this page connected 13 s ago/);
  // the period comes from the keyframe itself when it says so
  const t2 = new Tab(0, 0);
  t2.keyframe(2000);
  t2.wait(5001);
  assert.equal(t2.step(status([], { scene: feed(5, 0) })).views["HUD scene"].tone, "amber");
});

test("HUD scene: no publisher at all, and the old-backend / no-status lines", () => {
  const tab = new Tab();
  let s = tab.step(status([], { scene: feed(0, null) }));
  assert.match(s.views["HUD scene"].text, /no publisher running/);
  s = tab.step(status([], {})); // a backend that does not report the feeds
  for (const v of Object.values(s.views)) {
    assert.equal(v.tone, "amber");
    assert.match(v.text, /backend not updated/);
  }
  for (const v of Object.values(connectingViews())) assert.match(v.text, /no backend status yet/);
});

test("a backend without bot_agents keeps the 2026-10-08 behaviour (amber when stale), with hysteresis", () => {
  const tab = new Tab();
  let s = tab.step(status(undefined, { hud: feed(0, null), route: feed(3, 9000, "route-preview") }));
  assert.match(s.views.HUD.text, /no publisher running/);
  assert.match(s.views["Route preview"].text, /last message 9 s ago from route-preview/);
  tab.wait(1000);
  s = tab.step(status(undefined, { hud: feed(0, null), route: feed(3, 100, "route-preview") }));
  assert.equal(s.views["Route preview"].tone, "amber"); // same count: no new message yet
  s = tab.step(status(undefined, { hud: feed(0, null), route: feed(4, 100, "route-preview") }));
  assert.equal(s.views["Route preview"].tone, "none");
});
