import assert from "node:assert/strict";
import { test } from "node:test";

import { describeCapture } from "./capture.ts";
import type { Status } from "./protocol.ts";

function status(lock: Partial<NonNullable<Status["capture_backend"]>> | null, extra: Partial<Status> = {}): Status {
  return {
    type: "status",
    t_mono_ns: 1,
    frame_id: -1,
    mode: "ASSIST",
    lease_until_ns: null,
    bot_connected: false,
    rdp_window_present: true,
    stream_window_present: false,
    capture_backend: lock
      ? { backend: "rdp", seq: 0, phase: "steady", since: null, owner: null, reason: null, ...lock }
      : null,
    capture_fps: 30,
    viewers: 1,
    clipboard_enabled: true,
    transfer_enabled: true,
    move_interval_ms: null,
    paint: "decode",
    game_black: false,
    ...extra,
  } as Status;
}

test("rdp mode is quiet and expects the RDP window", () => {
  const view = describeCapture(status({ backend: "rdp" }));
  assert.deepEqual(view, { label: "rdp", notices: [], expect: "rdp" });
});

test("console mode says paste and files are unavailable and expects the stream", () => {
  const view = describeCapture(status({ backend: "console", seq: 4 }, { stream_window_present: true }));
  assert.equal(view.label, "console");
  assert.equal(view.expect, "stream");
  assert.equal(view.notices.length, 1);
  assert.match(view.notices[0], /paste and \\\\tsclient files are unavailable/);
});

test("a missing stream window in steady console mode is a notice; not while switching", () => {
  assert.equal(describeCapture(status({ backend: "console" })).notices.length, 2);
  const switching = describeCapture(status({ backend: "console", phase: "switching", seq: 9 }));
  assert.equal(switching.label, "console (switching)");
  assert.match(switching.notices[0], /handover to console in progress \(seq 9\)/);
  assert.equal(switching.notices.length, 2);
});

test("hold expects no client and explains why", () => {
  const view = describeCapture(status({ backend: "hold", phase: "", reason: "lock directory /lab-state is not mounted" }));
  assert.equal(view.label, "HOLD");
  assert.equal(view.expect, null);
  assert.match(view.notices[0], /not mounted/);
});

test("no status yet", () => {
  assert.deepEqual(describeCapture(null), { label: "–", notices: [], expect: "rdp" });
});
