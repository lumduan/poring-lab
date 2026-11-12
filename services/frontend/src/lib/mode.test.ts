import assert from "node:assert/strict";
import { test } from "node:test";

import { MODE_ACTIVE_CLASS, modeBadge } from "./mode.ts";

test("BOT is red, pulsing and says the bot is in control", () => {
  const b = modeBadge("BOT", { state: "green" });
  assert.equal(b.tone, "bot");
  assert.equal(b.pulse, true);
  assert.match(b.label, /BOT/);
  assert.ok(b.className.includes("bg-red-600"));
  assert.match(b.detail, /verified/);
});

test("ASSIST is amber and HUMAN is blue; neither pulses", () => {
  const a = modeBadge("ASSIST", { state: "red", reason: "no_session" });
  assert.equal(a.tone, "assist");
  assert.ok(a.className.includes("bg-amber-500"));
  assert.match(a.detail, /blocked \(no_session\)/);
  const h = modeBadge("HUMAN", { state: "red", reason: "no_session" });
  assert.equal(h.tone, "human");
  assert.equal(h.pulse || a.pulse, false);
  assert.doesNotMatch(h.detail, /blocked/); // the interlock does not matter while a human drives
});

test("a declared green is never shown as verified (ADR-0023)", () => {
  for (const mode of ["BOT", "ASSIST"] as const) {
    const b = modeBadge(mode, { state: "green", reason: "declared", verified: false });
    assert.match(b.detail, /Allowed by a person's declaration, not verified\./);
    assert.doesNotMatch(b.detail, /session verified/);
  }
  assert.match(modeBadge("BOT", { state: "green", verified: true }).detail, /Lab session verified/);
});

test("no status is never shown as a safe mode", () => {
  const u = modeBadge(null);
  assert.equal(u.tone, "unknown");
  assert.match(u.label, /NO STATUS/);
});

test("the mode switch uses the badge's colours", () => {
  assert.ok(modeBadge("BOT").className.startsWith(MODE_ACTIVE_CLASS.BOT));
  assert.ok(modeBadge("ASSIST").className.startsWith(MODE_ACTIVE_CLASS.ASSIST));
  assert.ok(modeBadge("HUMAN").className.startsWith(MODE_ACTIVE_CLASS.HUMAN));
});
