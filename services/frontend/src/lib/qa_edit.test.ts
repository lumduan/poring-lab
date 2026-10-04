import assert from "node:assert/strict";
import { test } from "node:test";

import {
  applyDrag,
  classForKey,
  type EditBox,
  frameEdit,
  fromAuto,
  fromHandCheck,
  hitTest,
  newBox,
  statusOf,
  toHandCheck,
  toImage,
} from "./qa_edit.ts";

const SIZE: [number, number] = [1280, 720];
const box = (x1: number, y1: number, x2: number, y2: number, cls: EditBox["cls"] = "monster", gid: number | null = 7): EditBox => ({
  x1,
  y1,
  x2,
  y2,
  cls,
  gid,
});

test("corner handles win over the body, the topmost box wins", () => {
  const boxes = [box(100, 100, 200, 200), box(150, 150, 250, 250, "npc", 8)];
  assert.deepEqual(hitTest(boxes, 101, 99), { index: 0, part: "nw" });
  assert.deepEqual(hitTest(boxes, 249, 251), { index: 1, part: "se" });
  assert.deepEqual(hitTest(boxes, 175, 175), { index: 1, part: "move" }); // overlap: the last drawn
  assert.deepEqual(hitTest(boxes, 120, 180), { index: 0, part: "move" });
  assert.equal(hitTest(boxes, 10, 10), null);
});

test("move keeps the size and stays inside the image; resize normalizes", () => {
  const b = box(100, 100, 200, 150);
  assert.deepEqual(applyDrag(b, "move", 30, -20, SIZE), box(130, 80, 230, 130));
  assert.deepEqual(applyDrag(b, "move", 5000, 0, SIZE), box(1180, 100, 1280, 150));
  const flipped = applyDrag(b, "se", -150, 0, SIZE); // dragged past the left edge of the box
  assert.deepEqual([flipped.x1, flipped.x2], [50, 100]);
  assert.deepEqual(applyDrag(b, "nw", -500, -500, SIZE), box(0, 0, 200, 150));
});

test("new boxes need a real drag; classes come from keys 1/2/3", () => {
  assert.equal(newBox(10, 10, 12, 40, "player", SIZE), null);
  assert.deepEqual(newBox(50, 60, 10, 20, "npc", SIZE), box(10, 20, 50, 60, "npc", null));
  assert.deepEqual(["1", "2", "3", "4"].map(classForKey), ["player", "monster", "npc", null]);
});

test("untouched auto-labels are accepted; any change is edited", () => {
  const frame = { file: "1.png", frame_id: 12, t_mono_ns: 5, boxes: [{ x1: 1, y1: 2, x2: 30, y2: 40, cls: "monster", gid: 7 }] };
  const auto = fromAuto(frame.boxes);
  assert.equal(statusOf(auto, auto), "accepted");
  assert.equal(frameEdit(frame, auto).status, "accepted");
  assert.equal(statusOf(auto, [applyDrag(auto[0], "move", 3, 0, SIZE)]), "edited");
  assert.equal(statusOf(auto, []), "edited"); // a deleted box
  assert.equal(statusOf(auto, [{ ...auto[0], cls: "npc" }]), "edited"); // a class change
});

test("the saved document holds reviewed frames in order and round-trips", () => {
  const edits = {
    20: { frame_id: 20, t_mono_ns: 9, status: "edited" as const, boxes: [box(1.234, 2, 3, 4)] },
    10: { frame_id: 10, t_mono_ns: 8, status: "accepted" as const, boxes: [] },
  };
  const doc = toHandCheck("20261004T120000-console-x", SIZE, "batt", edits);
  assert.deepEqual(
    doc.frames.map((f) => f.frame_id),
    [10, 20],
  );
  assert.equal(doc.frames[1].boxes[0].x1, 1.2);
  assert.deepEqual(Object.keys(fromHandCheck(doc)).map(Number), [10, 20]);
  assert.deepEqual(fromHandCheck(null), {});
});

test("overlay pixels map to image pixels under scaling", () => {
  assert.deepEqual(toImage(110, 60, { left: 10, top: 10, width: 640, height: 360 }, SIZE), [200, 100]);
});
