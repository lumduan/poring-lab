import assert from "node:assert/strict";
import { test } from "node:test";

import {
  chord,
  HeldKeys,
  isKnownCode,
  isReservedChord,
  shouldForwardPhysical,
  TOOLBAR,
} from "./keys.ts";

test("event.code values the backend maps are known; others are not", () => {
  for (const code of ["KeyA", "Digit1", "F1", "F12", "Escape", "Tab", "Backspace", "ArrowUp"]) {
    assert.equal(isKnownCode(code), true, code);
  }
  for (const code of ["Fn", "OSLeft", "BrowserBack", "", "KeyÄ"]) {
    assert.equal(isKnownCode(code), false, code);
  }
});

test("physical Win/Cmd stays local, the toolbar can still send it", () => {
  assert.equal(shouldForwardPhysical("MetaLeft"), false);
  assert.equal(shouldForwardPhysical("MetaRight"), false);
  assert.equal(isKnownCode("MetaLeft"), true);
  assert.equal(shouldForwardPhysical("F5"), true);
});

test("reserved xfreerdp chords need both Ctrl and Alt", () => {
  const ctrlAlt = new Set(["ControlLeft", "AltRight"]);
  for (const code of ["KeyD", "Enter", "NumpadEnter"]) {
    assert.equal(isReservedChord(ctrlAlt, code), true, code);
  }
  assert.equal(isReservedChord(new Set(["ControlLeft"]), "KeyD"), false);
  assert.equal(isReservedChord(new Set(["AltLeft"]), "Enter"), false);
  assert.equal(isReservedChord(ctrlAlt, "End"), false);
});

test("chord presses in order and releases in reverse", () => {
  assert.deepEqual(chord(["AltLeft", "Tab"]), [
    { code: "AltLeft", action: "down" },
    { code: "Tab", action: "down" },
    { code: "Tab", action: "up" },
    { code: "AltLeft", action: "up" },
  ]);
});

test("every toolbar sequence uses known codes, never a reserved chord, and ends released", () => {
  for (const [name, { steps }] of Object.entries(TOOLBAR)) {
    const held = new HeldKeys();
    for (const step of steps) {
      assert.equal(held.apply(step), true, `${name}: ${step.code} ${step.action}`);
    }
    assert.equal(held.codes.size, 0, `${name} leaves keys held`);
  }
});

test("Ctrl+Alt+Del is sent as Ctrl+Alt+End", () => {
  assert.deepEqual(
    TOOLBAR.ctrlAltDel.steps.filter((s) => s.action === "down").map((s) => s.code),
    ["ControlLeft", "AltLeft", "End"],
  );
});

test("HeldKeys refuses reserved chords, unknown codes and stray ups", () => {
  const held = new HeldKeys();
  assert.equal(held.apply({ code: "ControlLeft", action: "down" }), true);
  assert.equal(held.apply({ code: "AltLeft", action: "down" }), true);
  assert.equal(held.apply({ code: "KeyD", action: "down" }), false);
  assert.equal(held.apply({ code: "Fn", action: "down" }), false);
  assert.equal(held.apply({ code: "KeyQ", action: "up" }), false);
  held.clear();
  assert.equal(held.codes.size, 0);
});
