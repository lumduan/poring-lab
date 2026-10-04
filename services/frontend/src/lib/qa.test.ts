import assert from "node:assert/strict";
import { test } from "node:test";

import { initialSession, toDetections } from "./qa.ts";

test("pixel boxes become normalized, clamped detections for the overlay", () => {
  const det = toDetections(
    { file: "1.png", frame_id: 1, t_mono_ns: 5, boxes: [{ x1: -10, y1: 100, x2: 392, y2: 625, cls: "monster", gid: 7 }] },
    [784, 625],
  );
  assert.equal(det.type, "detections");
  assert.deepEqual(det.boxes[0], { x1: 0, y1: 0.16, x2: 0.5, y2: 1, cls: "monster #7", conf: 1 });
});

test("/qa opens on the session a link names, else the newest; an unknown name is ignored", () => {
  const index = { sessions: [{ id: "a", title: "a", frames: 1 }, { id: "b", title: "b", frames: 1 }] };
  assert.equal(initialSession(index, "?session=a"), "a");
  assert.equal(initialSession(index, ""), "b");
  assert.equal(initialSession(index, "?session=nope"), "b");
  assert.equal(initialSession({ sessions: [] }, "?session=a"), null);
});
