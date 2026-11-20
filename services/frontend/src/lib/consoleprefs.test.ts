import assert from "node:assert/strict";
import { test } from "node:test";

import { CONSOLE_DEFAULTS, CONSOLE_KEYS, loadConsolePrefs, saveToggle, saveView } from "./consoleprefs.ts";
import type { StorageLike } from "./flow/prefs.ts";

function memory(): StorageLike & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
    removeItem: (k) => void data.delete(k),
  };
}

test("nothing stored, or no storage at all: every toggle off, Fit", () => {
  assert.deepEqual(loadConsolePrefs(memory()), CONSOLE_DEFAULTS);
  assert.deepEqual(loadConsolePrefs(null), CONSOLE_DEFAULTS);
});

test("what a person turned on comes back on the next load (Batt 2026-11-20)", () => {
  const s = memory();
  assert.ok(saveToggle(s, "hud", true));
  assert.ok(saveToggle(s, "watchOnly", true));
  assert.ok(saveToggle(s, "secret", true));
  assert.ok(saveView(s, "native"));
  assert.deepEqual(loadConsolePrefs(s), { hud: true, watchOnly: true, secret: true, view: "native" });
  saveToggle(s, "watchOnly", false);
  assert.equal(loadConsolePrefs(s).watchOnly, false);
});

test("a stored value it does not know is the default", () => {
  const s = memory();
  s.setItem(CONSOLE_KEYS.hud, "true");
  s.setItem(CONSOLE_KEYS.view, "zoom");
  assert.deepEqual(loadConsolePrefs(s), CONSOLE_DEFAULTS);
});

test("a storage that throws is the defaults, and a refused write says so", () => {
  const broken: StorageLike = {
    getItem: () => {
      throw new Error("blocked");
    },
    setItem: () => {
      throw new Error("quota");
    },
    removeItem: () => undefined,
  };
  assert.deepEqual(loadConsolePrefs(broken), CONSOLE_DEFAULTS);
  assert.equal(saveToggle(broken, "hud", true), false);
  assert.equal(saveView(null, "native"), false);
});
