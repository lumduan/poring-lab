import assert from "node:assert/strict";
import { test } from "node:test";

import { identityReasonText, MODE_CHOICES, nameProblem, plateRgba } from "./runidentity.ts";

test("the modes are any (first, the default), known and mine (Batt 2026-11-19)", () => {
  assert.deepEqual(MODE_CHOICES.map((m) => m.mode), ["any", "known", "mine"]);
  assert.match(MODE_CHOICES[0].title, /default/);
  assert.ok(MODE_CHOICES.every((m) => !/RUN_IDENTITY|\.env/.test(m.title + m.help)), "a Settings choice, no .env word");
});

test("a name is any script, trimmed, unique, at most max_name characters", () => {
  assert.equal(nameProblem("Rogue76bd", 24, []), null);
  assert.equal(nameProblem("โร้กสายฟ้า", 24, []), null); // Thai: the bot compares the picture
  assert.equal(nameProblem("도적", 24, []), null); // Korean
  assert.match(nameProblem("", 24, []) ?? "", /Type/);
  assert.match(nameProblem(" a", 24, []) ?? "", /spaces/);
  assert.match(nameProblem("x".repeat(25), 24, []) ?? "", /At most 24/);
  assert.equal(nameProblem("ก".repeat(24), 24, []), null); // counted in characters, not bytes
  assert.match(nameProblem("a\u0007b", 24, []) ?? "", /control/);
  assert.match(nameProblem("rogue76BD", 24, ["Rogue76bd"]) ?? "", /already/);
});

test("the name line's RGB bytes become canvas pixels, or null when the size is wrong", () => {
  const rgb = Buffer.from([1, 2, 3, 4, 5, 6]).toString("base64");
  assert.deepEqual([...(plateRgba(rgb, 2, 1) ?? [])], [1, 2, 3, 255, 4, 5, 6, 255]);
  assert.equal(plateRgba(rgb, 3, 1), null);
  assert.equal(plateRgba("%%%", 1, 1), null);
});

test("refusals read as words, with the backend's detail", () => {
  assert.match(identityReasonText("plate_failed", "the name line is blank"), /could not be read: the name line is blank\.$/);
  assert.match(identityReasonText("already_remembered", "Rogue76bd"), /as “Rogue76bd”/);
  assert.match(identityReasonText("lab_host_peer"), /another computer on the LAN/);
  assert.match(identityReasonText("something_new"), /Refused \(something_new\)/);
});
