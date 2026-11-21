import assert from "node:assert/strict";
import test from "node:test";

import { EXPR_HELP, exprTooltip } from "./exprwords.ts";

test("the expression's tooltip says what THIS expression means (Batt 2026-11-21: the weight field showed HP)", () => {
  assert.equal(
    exprTooltip("weight_percent() >= 75"),
    `On when the bag's weight (% of the most she can carry) is at or over 75.\n(weight_percent() >= 75)\n${EXPR_HELP}`,
  );
  assert.match(exprTooltip("hp_percent() < 50"), /^On when her HP \(%\) is under 50\./);
  assert.match(exprTooltip("hp_percent() < 25 or weight_percent() >= 90"), /her HP \(%\) is under 25 or the bag's weight/);
  assert.match(exprTooltip("hotbar_count(F6) <= 3"), /the count on hotbar key F6 is at or under 3/);
  // one it cannot say: its text, then the general help; empty: the general help
  assert.equal(exprTooltip("sees_boss() or hp_percent() < 25"), `sees_boss() or hp_percent() < 25\n${EXPR_HELP}`);
  assert.equal(exprTooltip(""), EXPR_HELP);
  assert.match(EXPR_HELP, /weight_percent\(\) >= 75/);
});
