import assert from "node:assert/strict";
import test from "node:test";

import { closePane, openPane, parsePaneOrder, setPaneOpen } from "./panes.ts";

test("panes stack in the order opened; a closed one lets the rest move up; reopened goes last (Batt 2026-11-21)", () => {
  let o: string[] = [];
  o = openPane(o, "run");
  o = openPane(o, "paths");
  o = openPane(o, "lint");
  assert.deepEqual(o, ["run", "paths", "lint"]);
  o = closePane(o, "run"); // the top one closed: the others move up
  assert.deepEqual(o, ["paths", "lint"]);
  o = openPane(o, "run"); // opened again: at the bottom
  assert.deepEqual(o, ["paths", "lint", "run"]);
  assert.deepEqual(openPane(o, "paths"), o); // already open: where it is
  assert.deepEqual(setPaneOpen(o, "lint", false), ["paths", "run"]);
});

test("a stored order keeps the known panes once each; anything else is no order", () => {
  const known = ["run", "paths", "lint"] as const;
  assert.deepEqual(parsePaneOrder('["lint","run","lint","nope",3]', known), ["lint", "run"]);
  assert.deepEqual(parsePaneOrder("[]", known), []);
  assert.equal(parsePaneOrder(null, known), null);
  assert.equal(parsePaneOrder("{", known), null);
  assert.equal(parsePaneOrder('{"a":1}', known), null);
});
