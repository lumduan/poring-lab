import assert from "node:assert/strict";
import { test } from "node:test";

import {
  diskLine,
  elapsedText,
  newNotifications,
  panelModel,
  recordReasonText,
  sizeText,
  wantsBrowserNotification,
  type RouteRecCheck,
  type RouteRecNotification,
  type RouteRecRecording,
  type RouteRecStatus,
} from "./routerec.ts";

function check(over: Partial<RouteRecCheck> = {}): RouteRecCheck {
  return {
    id: "req1",
    at: "2026-11-22T15:00:00+07:00",
    ready: true,
    missing: [],
    missing_words: null,
    basic_info: true,
    chat_window: true,
    minimap: "present",
    xy: [93, 82],
    format: "h264",
    recorder: null,
    disk: { usable_bytes: 2_460_000_000, rate_bytes_per_min: 41e6, minutes: 60, max_minutes: 60, verdict: "ok", rate_source: "default" },
    busy: null,
    can_start: true,
    words: "ready; about 60 minutes fit",
    ...over,
  };
}

function recording(over: Partial<RouteRecRecording> = {}): RouteRecRecording {
  return {
    id: "20261122T150000",
    dir: "/store/recordings/2026-11-22/20261122T150000-xmas_dun02-route",
    map: "xmas_dun02",
    format: "h264",
    fps: 5,
    split: "held-out",
    started: "2026-11-22T15:00:00+07:00",
    state: "recording",
    elapsed_s: 754,
    max_s: 3570,
    disk_used_bytes: 520_000_000,
    minutes_left: 47,
    rate_source: "default",
    ready: true,
    missing: [],
    missing_words: null,
    minimap: "present",
    xy: [93, 82],
    session: "20261122T150001-console-route",
    session_path: "/home/bot/poring-lab-rec/20261122T150001-console-route",
    ...over,
  };
}

function status(over: Partial<RouteRecStatus> = {}): RouteRecStatus {
  return { state: "idle", helper_alive: true, detail: "waiting for the Record button", busy: null, check: null, recording: null, last: null, notifications: [], ...over };
}

function note(id: string, level = "action", kind = "map_change"): RouteRecNotification {
  return { id, kind, level, text: "New map: type /where in the chat.", at: "2026-11-22T15:01:00+07:00", recording: "20261122T150000" };
}

test("times and sizes read as a person says them", () => {
  assert.equal(elapsedText(0), "0:00");
  assert.equal(elapsedText(754.9), "12:34");
  assert.equal(elapsedText(3723), "1:02:03");
  assert.equal(sizeText(520_000_000), "520 MB");
  assert.equal(sizeText(41_000_000), "41.0 MB");
  assert.equal(sizeText(2_460_000_000), "2.5 GB");
});

test("no helper, or a dead one, disables every button and says why", () => {
  const m = panelModel(null);
  assert.equal(m.helper, "down");
  assert.ok(!m.canCheck && !m.canStart && !m.canStop);
  assert.match(m.headline, /poring-lab-routerec\.service/);
  const dead = panelModel(status({ helper_alive: false, detail: "the Record route helper has not answered for 31 s" }));
  assert.equal(dead.helper, "down");
  assert.match(dead.headline, /31 s/);
});

test("a ready check: every item ok, the minimap reported, the minutes that fit", () => {
  const m = panelModel(status({ check: check() }));
  assert.equal(m.ready, true);
  assert.ok(m.canCheck && m.canStart && !m.canStop);
  assert.deepEqual(m.items.map((i) => [i.key, i.ok]), [["capture_lock", true], ["basic_info", true], ["chat_window", true], ["minimap", null]]);
  assert.match(m.items[3].text, /93 82/);
  assert.equal(m.disk?.level, "ok");
  assert.match(m.disk?.text ?? "", /About 60 minutes fit/);
});

test("a check that is not ready names the missing item; the minimap is never required", () => {
  const m = panelModel(status({ check: check({ ready: false, missing: ["basic_info"], minimap: "absent", xy: null, can_start: false }) }));
  assert.equal(m.ready, false);
  const basic = m.items.find((i) => i.key === "basic_info");
  assert.equal(basic?.ok, false);
  assert.match(basic?.text ?? "", /status window/);
  const mm = m.items.find((i) => i.key === "minimap");
  assert.equal(mm?.ok, null);
  assert.match(mm?.text ?? "", /indoors/);
  // without a picture only the lock is known, the windows are not listed as missing
  const nopic = panelModel(status({ check: check({ ready: false, missing: ["frame"], minimap: null, xy: null }) }));
  assert.deepEqual(nopic.items.map((i) => [i.key, i.ok]), [["frame", false], ["capture_lock", true], ["minimap", null]]);
});

test("the recorder's own refusal is shown as an item, in its words", () => {
  const m = panelModel(status({ check: check({ recorder: "--out must be /home/bot/poring-lab-rec", can_start: false }) }));
  const r = m.items.find((i) => i.key === "recorder");
  assert.equal(r?.ok, false);
  assert.match(r?.text ?? "", /would refuse: --out must be/);
});

test("the disk: fewer than ten minutes warns, nothing refuses, no rate is unknown", () => {
  assert.equal(diskLine({ minutes: 7, verdict: "warn", usable_bytes: 287e6 }).level, "warn");
  assert.match(diskLine({ minutes: 7, verdict: "warn" }).text, /Only about 7 minutes/);
  assert.equal(diskLine({ minutes: 0, verdict: "refuse", usable_bytes: 0 }).level, "bad");
  const unk = diskLine({ minutes: null, verdict: "unknown", usable_bytes: 40e9 });
  assert.equal(unk.level, "unknown");
  assert.equal(unk.minutes, null);
  assert.match(unk.text, /not known yet/);
  assert.match(diskLine({ minutes: 900, verdict: "ok", max_minutes: 60 }).text, /stops at 60 min/);
  assert.match(diskLine({ minutes: null, verdict: "refuse", error: "OSError: gone" }).text, /could not be read/);
  assert.match(diskLine({ minutes: 0, verdict: "refuse", usable_bytes: 0, limit: "floor" }).text, /keeps free on the bot server's disk/);
  assert.match(diskLine({ minutes: 0, verdict: "refuse", usable_bytes: 0, limit: "unshipped" }).text, /waiting to be shipped/);
});

test("recording: elapsed, size, minutes left, Stop only; a stopping one cannot be stopped twice", () => {
  const m = panelModel(status({ state: "recording", recording: recording() }));
  assert.ok(m.recording && m.canStop && !m.canStart && !m.canCheck);
  assert.equal(m.headline, "Recording 12:34");
  assert.deepEqual(m.rec, { elapsed: "12:34", size: "520 MB used on the disk", left: "about 47 min left on the disk", map: "xmas_dun02", split: "held-out", stopping: false });
  assert.equal(m.disk, null);
  const unk = panelModel(status({ state: "recording", recording: recording({ minutes_left: null, map: null }) }));
  assert.match(unk.rec?.left ?? "", /not known yet/);
  assert.match(unk.rec?.map ?? "", /type \/where/);
  const stopping = panelModel(status({ state: "stopping", recording: recording({ state: "stopping" }) }));
  assert.ok(!stopping.canStop && stopping.rec?.stopping);
  assert.match(stopping.headline, /Stopping/);
  const lost = panelModel(status({ state: "recording", recording: recording({ ready: false, missing: ["chat_window"] }) }));
  assert.equal(lost.ready, false);
  assert.equal(lost.items.find((i) => i.key === "chat_window")?.ok, false);
});

test("a bot of ours playing disables Start, not Check", () => {
  const m = panelModel(status({ state: "busy", busy: "the live block player is playing (one input writer at a time)" }));
  assert.ok(m.canCheck && !m.canStart);
  assert.match(m.headline, /bot of ours is playing/);
});

test("a check asked and not answered yet shows checking until the helper writes its id", () => {
  const before = panelModel(status({ check: check({ id: "old" }) }), "req2");
  assert.ok(before.checking && !before.canCheck && !before.canStart);
  assert.match(before.headline, /Checking/);
  const after = panelModel(status({ check: check({ id: "req2" }) }), "req2");
  assert.ok(!after.checking && after.canStart);
});

test("the last recording's end is said in words", () => {
  const m = panelModel(status({ state: "ended", last: { id: "x", dir: "d", ended: "t", stop_reason: "you pressed Stop", rc: 0, bytes: 1_230_000_000, session: "s", session_path: "/home/bot/poring-lab-rec/s", split: "train", refused: false } }));
  assert.equal(m.last, "The last recording stopped: you pressed Stop (1.2 GB).");
});

test("new notifications by id: nothing on the first poll, then only the ones not seen", () => {
  const first = newNotifications([note("r-1", "info", "started"), note("r-2")], null);
  assert.deepEqual(first.fresh, []);
  assert.deepEqual(first.seen, ["r-1", "r-2"]);
  const next = newNotifications([note("r-1", "info", "started"), note("r-2"), note("r-3", "warn", "low_disk")], first.seen);
  assert.deepEqual(next.fresh.map((n) => n.id), ["r-3"]);
  const again = newNotifications([note("r-2"), note("r-3"), note("r-4")], next.seen); // the oldest dropped
  assert.deepEqual(again.fresh.map((n) => n.id), ["r-4"]);
  assert.deepEqual(again.seen, ["r-2", "r-3", "r-4"]);
  assert.deepEqual(newNotifications(undefined, again.seen), { fresh: [], seen: [] });
});

test("the browser's own notification only for what asks the person to act, or warns", () => {
  assert.equal(wantsBrowserNotification(note("a", "action")), true);
  assert.equal(wantsBrowserNotification(note("b", "warn", "low_disk")), true);
  assert.equal(wantsBrowserNotification(note("c", "info", "started")), false);
});

test("refusals read as words", () => {
  assert.match(recordReasonText("input_writer_busy", "an A/B series is running"), /your own play.*\(an A\/B series is running\)/);
  assert.match(recordReasonText("helper_not_running"), /poring-lab-routerec\.service/);
  assert.match(recordReasonText("lab_host_peer"), /another computer on the LAN/);
  assert.match(recordReasonText("something_new"), /Refused \(something_new\)/);
});
