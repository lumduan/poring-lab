import assert from "node:assert/strict";
import { test } from "node:test";

import { bannerProblems, describeCleanRoom } from "./banner.ts";
import type { CleanRoom, Status } from "./protocol.ts";

const LINKS = { stream: true, input: true };
const D3D = /Direct3D|ro_agent\.py recover/;

function status(lock: Partial<NonNullable<Status["capture_backend"]>>, extra: Partial<Status> = {}): Status {
  return {
    type: "status",
    t_mono_ns: 1,
    frame_id: -1,
    mode: "ASSIST",
    lease_until_ns: null,
    bot_connected: false,
    rdp_window_present: lock.backend === "rdp",
    stream_window_present: lock.backend === "console",
    capture_backend: { backend: "rdp", seq: 0, phase: "steady", since: null, owner: null, reason: null, ...lock },
    cleanroom: null,
    capture_fps: 30,
    viewers: 1,
    clipboard_enabled: true,
    transfer_enabled: true,
    move_interval_ms: null,
    paint: "decode",
    game_black: false,
    human_secret: false,
    mode_restored: false,
    alarms: [],
    ...extra,
  } as Status;
}

function room(extra: Partial<CleanRoom> = {}): CleanRoom {
  return { variant: "V3", streaming: true, box_left_s: 720, hard_cap_left_s: 9660, ...extra };
}

test("rdp + black game: the D3D advice and ro_agent recover", () => {
  const problems = bannerProblems({ links: LINKS, status: status({ backend: "rdp" }, { game_black: true }) });
  assert.equal(problems.length, 1);
  assert.match(problems[0], D3D);
});

test("console + black game: no D3D advice, the stream shows no picture instead", () => {
  const problems = bannerProblems({
    links: LINKS,
    status: status({ backend: "console" }, { game_black: true }),
  });
  assert.ok(!problems.some((p) => D3D.test(p)), problems.join("\n"));
  assert.ok(problems.some((p) => /console stream shows no game picture/.test(p)));
});

test("a clean room between variants: black is expected, no handover notice, no D3D", () => {
  const s = status(
    { backend: "console", phase: "switching", reason: "cleanroom-hold", seq: 31 },
    { game_black: true, stream_window_present: false, cleanroom: room({ streaming: false, box_left_s: 0 }) },
  );
  const problems = bannerProblems({ links: LINKS, status: s, nowMs: 0 });
  assert.ok(!problems.some((p) => D3D.test(p) || /handover|game picture|missing/.test(p)), problems.join("\n"));
  assert.match(problems[0], /^Clean room \(ADR-0009\): between variants \(last V3\): no stream, as expected; hard cap in 2 h 41 min \(\d\d:\d\d\)\./);
});

test("a clean room streaming shows the variant, its box and the hard cap", () => {
  const s = status({ backend: "console", reason: "cleanroom", seq: 32 }, { cleanroom: room() });
  const problems = bannerProblems({ links: LINKS, status: s, nowMs: 0 });
  assert.match(problems[0], /V3 streaming; its box ends in 12 min; hard cap in 2 h 41 min/);
  assert.match(problems[0], /RDP holds until scripts\/cleanroom\.py end\./);
});

test("clean-room wording for the entry and a box that is over", () => {
  assert.match(describeCleanRoom(room({ variant: null, streaming: false, box_left_s: null }), 0), /entered, no variant streaming yet/);
  assert.doesNotMatch(describeCleanRoom(room({ box_left_s: 0 }), 0), /box/);
  assert.doesNotMatch(describeCleanRoom(room({ hard_cap_left_s: null }), 0), /hard cap/);
  assert.match(describeCleanRoom(room({ box_left_s: 59 }), 0), /box ends in 1 min/);
});

test("a missing window in a clean room says the variant, not a reconnect", () => {
  const s = status({ backend: "console", reason: "cleanroom" }, { stream_window_present: false, cleanroom: room() });
  const problems = bannerProblems({ links: LINKS, status: s });
  assert.ok(problems.some((p) => /clean-room variant is starting, or it exited/.test(p)));
  assert.ok(!problems.some((p) => /\(re\)connecting/.test(p)));
});

test("disconnected links and a dropped message are still reported", () => {
  const problems = bannerProblems({
    links: { stream: false, input: false },
    status: null,
    dropped: { type: "error", t_mono_ns: 1, frame_id: -1, channel: "input", ref_type: "key", reason: "bad" } as never,
  });
  assert.equal(problems.length, 3);
});

test("rdp reconnect notice stays rdp-only", () => {
  const rdp = bannerProblems({ links: LINKS, status: status({ backend: "rdp" }), rdpReconnected: true });
  assert.match(rdp[0], /reconnected less than a minute ago/);
  const console = bannerProblems({ links: LINKS, status: status({ backend: "console" }), rdpReconnected: true });
  assert.ok(!console.some((p) => /reconnected/.test(p)));
});

test("an automatic ASSIST restore is announced until a human chooses a mode", () => {
  const restored = bannerProblems({ links: LINKS, status: status({ backend: "rdp" }, { mode_restored: true }) });
  assert.match(restored[0], /^ASSIST restored automatically after a guarded restart/);
  assert.deepEqual(bannerProblems({ links: LINKS, status: status({ backend: "rdp" }) }), []);
});

test("a safety alarm is shown RED, apart from the amber notices", async () => {
  const { bannerAlarms } = await import("./banner.ts");
  const s = status({ backend: "console", reason: "cleanroom" }, { alarms: ["watchdog_down"] });
  const alarms = bannerAlarms(s);
  assert.equal(alarms.length, 1);
  assert.match(alarms[0], /^WATCHDOG DOWN/);
  assert.deepEqual(bannerAlarms(status({ backend: "rdp" })), []);
  assert.ok(!bannerProblems({ links: LINKS, status: s }).some((p) => /WATCHDOG/.test(p)));
});
