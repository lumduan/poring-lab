import assert from "node:assert/strict";
import { test } from "node:test";

import {
  arrowHead,
  cellsText,
  classColour,
  counterText,
  hudAlive,
  hudBoxes,
  hudToggle,
  lockedIndex,
  lockRemainingMs,
  lockText,
  logLines,
  plain,
  unitLabel,
  walkPx,
  zonePx,
} from "./hud.ts";
import type { HudUnit, OperatorHud, Status } from "./protocol.ts";

const unit = (extra: Partial<HudUnit> = {}): HudUnit => ({
  cls: "monster",
  conf: 0.81,
  box: { x: 0.4, y: 0.3, w: 0.1, h: 0.2 },
  foot: { x: 0.45, y: 0.5 },
  dist_cells: 4,
  id: null,
  ...extra,
});

const hud = (extra: Partial<OperatorHud> = {}): OperatorHud =>
  ({
    type: "operator_hud",
    t_mono_ns: 1,
    frame_id: -1,
    label: "walk@12",
    ttl_ms: 1500,
    units: [unit(), unit({ cls: "npc", conf: 0.5, dist_cells: null, id: 7 })],
    lock: null,
    zone: null,
    walk: null,
    log: [],
    counters: { units: 2, det_fps: 4.25 },
    ...extra,
  }) as OperatorHud;

test("boxes scale to the canvas like detection boxes, labelled with class, confidence and CELLS", () => {
  const boxes = hudBoxes(hud(), 1000, 500);
  assert.equal(boxes.length, 2);
  assert.deepEqual(
    { x: boxes[0].x, y: boxes[0].y, w: boxes[0].w, h: boxes[0].h },
    { x: 400, y: 150, w: 100, h: 100 },
  );
  assert.deepEqual(boxes[0].foot, { x: 450, y: 250 });
  assert.equal(boxes[0].label, "monster 81% 4 cells");
  assert.equal(boxes[1].label, "npc 50% ? cells"); // no cell picked: never a pixel distance
  assert.equal(hudBoxes(null, 10, 10).length, 0);
});

test("a distance reads in cells, singular for one", () => {
  assert.equal(cellsText(0), "0 cells");
  assert.equal(cellsText(1), "1 cell");
  assert.equal(cellsText(12), "12 cells");
  assert.equal(cellsText(null), "? cells");
  assert.equal(unitLabel(unit({ conf: 0.996, dist_cells: 1 })), "monster 100% 1 cell");
});

test("the lock names a unit by index first, else by its track id; out of view = -1", () => {
  const lock = (index: number | null, id: number | null) => ({ index, id, lock_remaining_ms: 900 });
  assert.equal(lockedIndex(hud({ lock: lock(0, null) })), 0);
  assert.equal(lockedIndex(hud({ lock: lock(null, 7) })), 1);
  assert.equal(lockedIndex(hud({ lock: lock(5, 7) })), 1); // a stale index falls back to the id
  assert.equal(lockedIndex(hud({ lock: lock(5, null) })), -1);
  assert.equal(lockedIndex(hud({ lock: lock(null, 99) })), -1); // its unit is not in view
  assert.equal(lockedIndex(hud()), -1);
  const boxes = hudBoxes(hud({ lock: lock(null, 7) }), 100, 100);
  assert.deepEqual(boxes.map((b) => b.locked), [false, true]);
});

test("the lock counts down from the message's receipt, never below zero", () => {
  const h = hud({ lock: { index: 0, id: null, lock_remaining_ms: 1800 } });
  assert.equal(lockRemainingMs(h, 0), 1800);
  assert.equal(lockRemainingMs(h, 500), 1300);
  assert.equal(lockRemainingMs(h, 5000), 0);
  assert.equal(lockRemainingMs(hud(), 0), null);
  assert.equal(lockText(1300), "LOCK 1.3 s");
  assert.equal(lockText(null), "");
});

test("the HUD lives its ttl from the receipt; ttl 0 clears at once", () => {
  assert.equal(hudAlive(hud(), 0), true);
  assert.equal(hudAlive(hud(), 1499), true);
  assert.equal(hudAlive(hud(), 1500), false);
  assert.equal(hudAlive(hud({ ttl_ms: 0 }), 0), false);
  assert.equal(hudAlive(null, 0), false);
});

test("the work zone is the game area with the client's UI windows taken out", () => {
  const z = zonePx(
    hud({
      zone: {
        area: { x: 0.1, y: 0.1, w: 0.8, h: 0.8 },
        exclude: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.3 }],
      },
    }),
    1000,
    1000,
  );
  assert.deepEqual(z?.area, { x: 100, y: 100, w: 800, h: 800 });
  assert.deepEqual(z?.exclude, [{ x: 100, y: 100, w: 200, h: 300 }]);
  assert.equal(zonePx(hud(), 10, 10), null);
});

test("the walk vector: the agent's words, else the destination cell; points only when given", () => {
  const w = walkPx(
    hud({ walk: { dest: { x: 102, y: 110 }, text: "", start: { x: 0.5, y: 0.5 }, end: { x: 0.6, y: 0.4 } } }),
    1000,
    1000,
  );
  assert.equal(w?.text, "to (102,110)");
  assert.equal(w?.dest, "(102,110)");
  assert.deepEqual(w?.start, { x: 500, y: 500 });
  assert.deepEqual(w?.end, { x: 600, y: 400 });
  const off = walkPx(hud({ walk: { dest: { x: 3, y: 4 }, text: "walking to (3,4)", start: null, end: null } }), 10, 10);
  assert.equal(off?.text, "walking to (3,4)");
  assert.equal(off?.start, null);
  assert.equal(walkPx(hud(), 10, 10), null);
});

test("the arrowhead sits behind the end, symmetric about the vector", () => {
  const head = arrowHead({ x: 0, y: 0 }, { x: 100, y: 0 }, 10);
  assert.ok(head);
  const [a, b] = head;
  assert.deepEqual([a.x, b.x], [90, 90]);
  assert.equal(a.y, -b.y);
  assert.equal(Math.abs(a.y), 5);
  assert.equal(arrowHead({ x: 1, y: 1 }, { x: 1, y: 1 }), null); // no direction: no head
});

test("counters and the log read as plain text", () => {
  assert.equal(counterText(hud()), "2 units · det 4.3 fps");
  assert.equal(counterText(hud({ counters: { units: 1, det_fps: null } })), "1 unit · det – fps");
  const log = Array.from({ length: 12 }, (_, i) => `line ${i}`);
  assert.deepEqual(logLines(hud({ log: log as OperatorHud["log"] }), 3), ["line 9", "line 10", "line 11"]);
  assert.deepEqual(logLines(null), []);
});

test("text is one bounded line: control characters out, length capped", () => {
  assert.equal(plain("a\nb\tc\u001b[31m", 96), "a b c [31m");
  assert.equal(plain("x".repeat(200), 96).length, 96);
  assert.equal(plain("<b>bold</b>", 96), "<b>bold</b>"); // markup stays literal TEXT (never parsed)
  assert.deepEqual(logLines(hud({ log: ["refused:\u0007 TALK cell"] })), ["refused:  TALK cell"]);
});

test("each class has its colour; an unknown one a default", () => {
  const colours = ["monster", "player", "npc", "other"].map(classColour);
  assert.equal(new Set(colours).size, 4);
});

test("the toggle says which state it is in and that it sends nothing", () => {
  assert.match(hudToggle(true).label, /ON/);
  assert.doesNotMatch(hudToggle(false).label, /ON/);
  assert.match(hudToggle(true).title, /sends nothing/);
  assert.match(hudToggle(false).title, /off on every load/);
});

// --- the empty-overlay status line (Batt 2026-10-08) ---------------------------------------------
import { FEED_STALE_MS, feedLine } from "./hud.ts";

test("an empty overlay says why: no status, an old backend, no publisher, a stopped one, or live", () => {
  const base = { type: "status" } as unknown as Status;
  assert.match(feedLine("HUD", null) ?? "", /no backend status yet/);
  assert.match(feedLine("HUD", base) ?? "", /backend not updated/); // an older backend: no key
  const feed = (relayed: number, age_ms: number | null, source = "") =>
    ({ ...base, hud_feed: { relayed, age_ms, source }, route_feed: { relayed, age_ms, source } }) as Status;
  assert.match(feedLine("HUD", feed(0, null)) ?? "", /no publisher running/);
  assert.match(feedLine("Route preview", feed(4, FEED_STALE_MS + 9000, "route-preview")) ?? "",
    /last message 12 s ago from route-preview/);
  assert.equal(feedLine("HUD", feed(9, 200, "walk@12")), null); // live: nothing to explain
});
