import assert from "node:assert/strict";
import { test } from "node:test";

import {
  chord,
  HeldKeys,
  isKnownCode,
  isMacPlatform,
  isReservedChord,
  keyDecision,
  type KeyEventLike,
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

// --- ADR-0004: which chords paste natively (Mac clipboard -> Windows) and which are forwarded ---

function k(code: string, mods: string = ""): KeyEventLike {
  return {
    code,
    metaKey: mods.includes("cmd"),
    ctrlKey: mods.includes("ctrl"),
    altKey: mods.includes("alt"),
    shiftKey: mods.includes("shift"),
  };
}

const MAC = true;
const PC = false;

test("macOS: Cmd+V pastes the Mac clipboard; physical Ctrl+V stays a Windows combo", () => {
  assert.equal(keyDecision(k("KeyV", "cmd"), MAC), "paste");
  assert.equal(keyDecision(k("KeyV", "cmd shift"), MAC), "paste"); // paste and match style
  assert.equal(keyDecision(k("KeyV", "ctrl"), MAC), "forward"); // Windows-internal paste
  assert.equal(keyDecision(k("KeyV", "cmd alt"), MAC), "local"); // Cmd+Opt+V is not a paste
  assert.equal(keyDecision(k("KeyV", "cmd ctrl"), MAC), "local");
  assert.equal(keyDecision(k("KeyC", "cmd"), MAC), "local"); // other Cmd combos stay local
  assert.equal(keyDecision(k("Tab", "cmd"), MAC), "local");
});

test("other OSes: Ctrl+V and Ctrl+Shift+V paste; Ctrl+Alt+V (AltGr) is forwarded", () => {
  assert.equal(keyDecision(k("KeyV", "ctrl"), PC), "paste");
  assert.equal(keyDecision(k("KeyV", "ctrl shift"), PC), "paste");
  assert.equal(keyDecision(k("KeyV", "ctrl alt"), PC), "forward");
  assert.equal(keyDecision(k("KeyV", "cmd"), PC), "local"); // Win+V: the viewer's own OS
});

test("Shift+Insert pastes everywhere; Ctrl+Insert (copy) is forwarded", () => {
  for (const platform of [MAC, PC]) {
    assert.equal(keyDecision(k("Insert", "shift"), platform), "paste");
    assert.equal(keyDecision(k("Insert", "ctrl"), platform), "forward");
    assert.equal(keyDecision(k("Insert", "shift ctrl"), platform), "forward");
    assert.equal(keyDecision(k("Insert"), platform), "forward");
  }
});

test("ordinary keys are forwarded by physical code; local-only and unknown keys are not", () => {
  for (const platform of [MAC, PC]) {
    assert.equal(keyDecision(k("KeyV"), platform), "forward"); // a plain V (game hotkey)
    assert.equal(keyDecision(k("KeyV", "shift"), platform), "forward");
    assert.equal(keyDecision(k("F5"), platform), "forward");
    assert.equal(keyDecision(k("KeyA", "alt"), platform), "forward");
    assert.equal(keyDecision(k("MetaLeft", "cmd"), platform), "local");
    assert.equal(keyDecision(k("Fn"), platform), "local");
    assert.equal(keyDecision(k(""), platform), "local");
  }
  // The modifiers themselves are forwarded (except Meta), so games keep Ctrl/Shift/Alt.
  assert.equal(keyDecision(k("ControlLeft", "ctrl"), MAC), "forward");
});

test("platform detection", () => {
  for (const p of ["MacIntel", "macOS", "iPad", "iPhone"]) assert.equal(isMacPlatform(p), true, p);
  for (const p of ["Win32", "Windows", "Linux x86_64", ""]) assert.equal(isMacPlatform(p), false, p);
});

test("a paste chord's key-up is a stray up and never reaches Windows", () => {
  const held = new HeldKeys();
  // Cmd+V on a Mac: Meta stays local and the V down is the paste chord, so neither was sent.
  assert.equal(held.apply({ code: "KeyV", action: "up" }), false);
  // Ctrl+V elsewhere: Ctrl was forwarded, then the paste releases everything held.
  assert.equal(held.apply({ code: "ControlLeft", action: "down" }), true);
  held.clear(); // releaseAll() before the ClipboardPaste
  assert.equal(held.apply({ code: "KeyV", action: "up" }), false);
  assert.equal(held.apply({ code: "ControlLeft", action: "up" }), false);
});
