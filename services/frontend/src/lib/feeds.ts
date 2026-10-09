// WHY an overlay is empty, per display channel (Batt 2026-10-08: tell "no data" from "broken";
// 2026-10-09 14:24 + 14:57: no flicker, a keyframe heartbeat for the scene, and "idle: no rule
// running" in grey apart from "stopped while a rule runs" in yellow). Pure, unit tested with
// `node --test` (src/lib/feeds.test.ts). The console steps it once per Status (~1 Hz); the HUD
// panel draws the three lines in a RESERVED slot, so no state ever moves the layout.
//
// Clocks: a feed's `age_ms` is the backend's own; every *Ms time here is this tab's
// performance.now(). Durations from both are compared, timestamps are never subtracted across
// the two domains.

import type { DisplayFeed, Status } from "./protocol.ts";

export type FeedKind = "HUD scene" | "HUD" | "Route preview";
export const FEED_KINDS: readonly FeedKind[] = ["HUD scene", "HUD", "Route preview"];

/** A channel is stale after this long without a message (Batt 2026-10-09 14:24: "stale after
 * 5 s; fresh again only after a new message"). */
export const FEED_STALE_MS = 5000;
/** The HUD scene's keyframe period: scripts/hud_scene.py KEYFRAME_S = 5.0, also each keyframe's
 * own `period_ms` (preferred when present). */
export const SCENE_KEYFRAME_MS = 5000;
/** The scene is stale after this many keyframe periods without a KEYFRAME (Batt 2026-10-09 14:57:
 * "~2.5 keyframe intervals"): 12.5 s at 5 s. Deltas and motion do not count -- they are sent only
 * when the scene changes, so their silence is normal; the keyframe is the scene's only periodic
 * message, and the one a new or desynced console needs. */
export const SCENE_KEYFRAME_PERIODS = 2.5;
/** A running RULE's agent id: every rule connects through ro_agent.session(f"rule:{name}")
 * (walk11.py and the walk rules rebound on it, loot1.py, talk1, the safety check ...); the
 * route previewer ("route-preview"), the HUD scene (not an agent), auto_recover and the harnesses
 * use other ids. Status.bot_agents lists the open agent connections' ids. */
export const RULE_AGENT_PREFIX = "rule:";

export type Tone = "none" | "grey" | "amber";
/** One channel's line: `none` = fresh, nothing to explain (the slot stays empty). */
export type FeedView = { tone: Tone; text: string };
export const FRESH: FeedView = { tone: "none", text: "" };

/** Hysteresis memory: stale, and the heartbeat count when it went stale. */
export type FeedMemo = { stale: boolean; beats: number };

/** Stale once `over`; once stale, fresh again only after a NEW heartbeat (the count moved), so a
 * channel never flickers around its threshold. A count that went DOWN is a restarted backend:
 * judged afresh. */
export function hysteresis(prev: FeedMemo | null, over: boolean, beats: number): FeedMemo {
  if (prev?.stale && beats === prev.beats) return prev;
  return { stale: over, beats };
}

/** The running rules' agent ids, or null when the backend does not report agents (older). */
export function runningRules(status: Status): string[] | null {
  const agents = (status as unknown as { bot_agents?: unknown }).bot_agents;
  if (!Array.isArray(agents)) return null;
  return agents
    .filter((a): a is string => typeof a === "string" && a.startsWith(RULE_AGENT_PREFIX))
    .sort();
}

function feedOf(kind: FeedKind, status: Status): DisplayFeed | null | undefined {
  const key = kind === "HUD" ? "hud_feed" : kind === "HUD scene" ? "scene_feed" : "route_feed";
  // an older backend's Status has no such key at all (undefined), whatever the generated type says
  return (status as unknown as Partial<Record<string, DisplayFeed | null>>)[key];
}

const secs = (ms: number) => Math.round(ms / 1000);
const notUpdated = (kind: FeedKind): FeedView => ({
  tone: "amber",
  text: `${kind}: backend not updated (it does not report this feed; restart pending)`,
});
const idle = (kind: FeedKind, why: string): FeedView => ({ tone: "grey", text: `${kind}: idle (${why})` });

/** What this tab saw besides Status (this tab's clock). */
export type Seen = {
  /** HUD scene keyframes received, the last one's receipt and its period. */
  keyframe: { count: number; atMs: number | null; periodMs: number | null };
  /** The last route_preview's receipt, and whether it drew a route (false: a clear). */
  route: { atMs: number | null; active: boolean };
  /** The last operator_hud's receipt and its ttl (0: its rule cleared it). */
  hud: { atMs: number | null; ttlMs: number | null };
};
export const NOTHING_SEEN: Seen = {
  keyframe: { count: 0, atMs: null, periodMs: null },
  route: { atMs: null, active: false },
  hud: { atMs: null, ttlMs: null },
};

export type FeedObs = {
  status: Status;
  nowMs: number; // this tab's clock at this Status
  watchSinceMs: number; // when this tab's stream socket last opened (the scene's grace)
  seen: Seen;
};

export type FeedState = {
  rules: string[] | null; // null: an older backend (no bot_agents)
  ruleSinceMs: number | null; // this tab's clock: when the current set of rules began
  memo: Record<FeedKind, FeedMemo | null>;
  views: Record<FeedKind, FeedView>;
};

type Step = { view: FeedView; memo: FeedMemo | null };

/** The HUD SCENE (runs whether a rule runs or not): heartbeat = its KEYFRAME, stale after
 * SCENE_KEYFRAME_PERIODS periods without one, counted from the last keyframe or, if none came
 * yet, from when this tab started watching. */
export function sceneStep(feed: DisplayFeed | null | undefined, obs: FeedObs, prev: FeedMemo | null): Step {
  if (feed == null) return { view: notUpdated("HUD scene"), memo: null };
  const k = obs.seen.keyframe;
  if (feed.relayed === 0) {
    return {
      view: { tone: "amber", text: "HUD scene: no publisher running (nothing sent since the backend started)" },
      memo: null,
    };
  }
  const period = k.periodMs && k.periodMs > 0 ? k.periodMs : SCENE_KEYFRAME_MS;
  const since = Math.max(k.atMs ?? -Infinity, obs.watchSinceMs);
  const silence = obs.nowMs - since;
  const memo = hysteresis(prev, silence > SCENE_KEYFRAME_PERIODS * period, k.count);
  if (!memo.stale) return { view: FRESH, memo };
  const what = k.atMs == null ? `no keyframe since this page connected ${secs(silence)} s ago` : `no keyframe for ${secs(silence)} s`;
  return {
    view: { tone: "amber", text: `HUD scene: ${what} (one is due every ${secs(period)} s: the scene process or its frames stopped)` },
    memo,
  };
}

/** The operator HUD: a rule's own channel. No rule running: grey idle. A rule running: stale
 * after max(FEED_STALE_MS, the rule's own ttl for its HUD), counted at most from the rule's
 * start (grace: a rule that just started is never stale at once). */
export function hudStep(
  feed: DisplayFeed | null | undefined,
  obs: FeedObs,
  rules: string[] | null,
  ruleSinceMs: number | null,
  prev: FeedMemo | null,
): Step {
  if (feed == null) return { view: notUpdated("HUD"), memo: null };
  const ttl = obs.seen.hud.ttlMs;
  const threshold = Math.max(FEED_STALE_MS, ttl ?? 0);
  const fresh = feed.age_ms != null && feed.age_ms <= threshold;
  if (rules !== null && rules.length === 0) {
    return { view: fresh ? FRESH : idle("HUD", "no rule running"), memo: null };
  }
  const h = obs.seen.hud;
  if (rules !== null && ttl === 0 && h.atMs != null && ruleSinceMs != null && h.atMs >= ruleSinceMs) {
    return { view: idle("HUD", `cleared by ${feed.source || "its rule"}`), memo: null };
  }
  const sinceRule = ruleSinceMs == null ? Infinity : obs.nowMs - ruleSinceMs;
  const silence = Math.min(feed.age_ms ?? Infinity, sinceRule);
  const memo = hysteresis(prev, silence > threshold, feed.relayed);
  if (!memo.stale) return { view: FRESH, memo };
  if (rules === null) return { view: { tone: "amber", text: oldLine("HUD", feed) }, memo }; // older backend
  const who = rules.join(", ");
  const text = rules.includes(feed.source)
    ? `HUD: last message ${secs(feed.age_ms ?? 0)} s ago from ${feed.source} while it runs (its HUD sender stopped)`
    : `HUD: nothing from ${who} since it started ${secs(sinceRule)} s ago (it sends no HUD, or its sender stopped)`;
  return { view: { tone: "amber", text }, memo };
}

/** The live route preview: sent ~20 times a second by the previewer while a route is ACTIVE and
 * cleared (an empty message) when the walk ends. No rule running, or no route active since the
 * rule started: grey idle. Stale only mid-route, after FEED_STALE_MS without a message. */
export function routeStep(
  feed: DisplayFeed | null | undefined,
  obs: FeedObs,
  rules: string[] | null,
  ruleSinceMs: number | null,
  prev: FeedMemo | null,
): Step {
  if (feed == null) return { view: notUpdated("Route preview"), memo: null };
  const fresh = feed.age_ms != null && feed.age_ms <= FEED_STALE_MS;
  if (rules !== null && rules.length === 0) {
    return { view: fresh ? FRESH : idle("Route preview", "no rule running"), memo: null };
  }
  const r = obs.seen.route;
  const active = r.active && r.atMs != null && (ruleSinceMs == null || r.atMs >= ruleSinceMs);
  if (rules !== null && !active) {
    return { view: fresh ? FRESH : idle("Route preview", "no route active"), memo: null };
  }
  const sinceRule = ruleSinceMs == null ? Infinity : obs.nowMs - ruleSinceMs;
  const silence = Math.min(feed.age_ms ?? Infinity, sinceRule);
  const memo = hysteresis(prev, silence > FEED_STALE_MS, feed.relayed);
  if (!memo.stale) return { view: FRESH, memo };
  if (rules === null) return { view: { tone: "amber", text: oldLine("Route preview", feed) }, memo };
  const text = `Route preview: last message ${secs(feed.age_ms ?? 0)} s ago from ${feed.source || "the previewer"} mid-route while ${rules.join(", ")} runs (the previewer stopped)`;
  return { view: { tone: "amber", text }, memo };
}

/** The 2026-10-08 wording, for a backend that does not report its agents. */
function oldLine(kind: FeedKind, feed: DisplayFeed): string {
  if (feed.relayed === 0) return `${kind}: no publisher running (nothing sent since the backend started)`;
  const who = feed.source ? ` from ${feed.source}` : "";
  return `${kind}: last message ${secs(feed.age_ms ?? 0)} s ago${who} (its publisher stopped or is idle)`;
}

/** One step per Status: who runs, then each channel. */
export function stepFeeds(prev: FeedState | null, obs: FeedObs): FeedState {
  const rules = runningRules(obs.status);
  const same =
    prev !== null &&
    (rules === null ? prev.rules === null : prev.rules !== null && rules.join("\n") === prev.rules.join("\n"));
  // a new set of rules is a new rule session: its grace starts now (none running: no grace)
  const ruleSinceMs = same ? prev.ruleSinceMs : rules && rules.length > 0 ? obs.nowMs : null;
  const memo = prev?.memo ?? { "HUD scene": null, HUD: null, "Route preview": null };
  const scene = sceneStep(feedOf("HUD scene", obs.status), obs, memo["HUD scene"]);
  const hud = hudStep(feedOf("HUD", obs.status), obs, rules, ruleSinceMs, same ? memo.HUD : null);
  const route = routeStep(feedOf("Route preview", obs.status), obs, rules, ruleSinceMs, same ? memo["Route preview"] : null);
  return {
    rules,
    ruleSinceMs,
    memo: { "HUD scene": scene.memo, HUD: hud.memo, "Route preview": route.memo },
    views: { "HUD scene": scene.view, HUD: hud.view, "Route preview": route.view },
  };
}

/** Before the first Status: every channel says so (amber: we know nothing yet). */
export function connectingViews(): Record<FeedKind, FeedView> {
  const v = (kind: FeedKind): FeedView => ({ tone: "amber", text: `${kind}: no backend status yet (connecting)` });
  return { "HUD scene": v("HUD scene"), HUD: v("HUD"), "Route preview": v("Route preview") };
}
