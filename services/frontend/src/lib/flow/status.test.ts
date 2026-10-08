import assert from "node:assert/strict";
import { test } from "node:test";

import type { LintDoc, Trace } from "./api.ts";
import { toGraph } from "./canvas.ts";
import { edgeRuns, lintLine, lintOf, runLine } from "./status.ts";
import { fixture } from "./testkit.ts";

test("lint badges keep unsupported bindings apart from the flow's own errors", () => {
  const lint = { by_owner: { "block:town": { error: 3, warning: 1, info: 0, unsupported: 2 } } } as unknown as LintDoc;
  assert.deepEqual(lintLine(lintOf(lint, "block:town")), { text: "1 error · 1 warning · 2 unsupported", level: "error" });
  assert.deepEqual(lintLine(lintOf(lint, "block:farm")), { text: "lint ok", level: "ok" });
  assert.equal(lintLine({ error: 2, warning: 0, info: 0, unsupported: 2 }).level, "unsupported");
});

test("run lines and edge counts come from the trace", () => {
  assert.equal(runLine({ runs: 8, total_s: 21.6, first_t: 0, last_t: 9, last: "ok", outcomes: { ok: 8 } }), "▶ 8× ok · 21.6 s");
  assert.equal(runLine({ runs: 7, total_s: 3, first_t: 0, last_t: 9, last: "ok", outcomes: { interrupted: 1, ok: 6 } }), "▶ 7× interrupted 1, ok 6 · 3.0 s");
  const g = toGraph(fixture("town_warp_farm"));
  const trace = {
    transitions: [
      { t: 1, kind: "npc_warp", from: "town", to: "farm" },
      { t: 2, kind: "item_warp", from: "farm", to: "town" },
      { t: 3, kind: "npc_warp", from: "town", to: "farm" },
      { t: 4, kind: "death_respawn", from: "farm", to: "town" },
    ],
  } as unknown as Trace;
  const runs = edgeRuns(trace, g.edges);
  assert.equal(runs.get("exit:town.9"), 2);
  assert.equal(runs.get("exit:farm.1"), 1);
  assert.equal(runs.get("respawn:farm"), 1);
});
