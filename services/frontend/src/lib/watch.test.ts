import assert from "node:assert/strict";
import { test } from "node:test";

import { isHumanInput, mayForward, releaseNeeded, watchToggle } from "./watch.ts";

const INPUT = ["mouse_move", "mouse_button", "wheel", "key", "release_all", "clipboard_paste"] as const;
const CONTROL = ["set_mode", "secret_input", "ping", "viewer_timing"] as const;

test("every message that reaches the mux is input; mode, secret, ping and timing are control", () => {
  for (const type of INPUT) assert.equal(isHumanInput(type), true, type);
  for (const type of CONTROL) assert.equal(isHumanInput(type), false, type);
});

test("watch only forwards no input at all, except a release_all", () => {
  for (const type of INPUT) {
    assert.equal(mayForward(type, true), type === "release_all", type);
  }
});

test("watch only never blocks a mode switch (HUMAN stays one click away) or the other controls", () => {
  for (const type of CONTROL) assert.equal(mayForward(type, true), true, type);
});

test("with watch only off, everything is forwarded (instant takeover)", () => {
  for (const type of [...INPUT, ...CONTROL]) assert.equal(mayForward(type, false), true, type);
});

test("release_all is needed only while the tab holds a key or a button", () => {
  assert.equal(releaseNeeded(new Set(), new Set()), false);
  assert.equal(releaseNeeded(new Set(["ShiftLeft"]), new Set()), true);
  assert.equal(releaseNeeded(new Set(), new Set(["left"])), true);
  assert.equal(releaseNeeded(new Set(["KeyW"]), new Set(["right"])), true);
});

test("the toggle says which state it is in", () => {
  assert.match(watchToggle(true).label, /ON/);
  assert.doesNotMatch(watchToggle(false).label, /ON/);
  assert.match(watchToggle(true).title, /HUMAN/);
});
