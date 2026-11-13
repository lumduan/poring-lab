// The SURVIVAL group (lib/flow/survival.ts, Batt 2026-11-13 ~14:2x: "a global config for every map's
// flow; a map's flow that sets them again overrides it"): the map's own first, then every map's,
// then the flow's defaults -- the Run helper's order (scripts/flow_run.py survival_of).
import assert from "node:assert/strict";
import { test } from "node:test";

import { allNodes, type RunnerPart, textOf } from "./runner.ts";
import { XMAS_DUN02_ROGUE as DOC } from "./runners/xmas_dun02_rogue.gen.ts";
import { effectiveSurvival, groupLevel, type SurvivalDoc, survivalProblem, withSurvival } from "./survival.ts";

const D = DOC.settings?.survival as SurvivalDoc;

test("the export carries the survival group: its strategy's own numbers as defaults", () => {
  assert.ok(D, "settings.survival");
  assert.deepEqual(D.defaults, { potion_below: 0.4, fly_below: 0.2, fly_rate: 150, fly_rate_below: 0.5 });
  assert.equal(DOC.params["strategy.potion_below"].value, 0.4); // the blocks' numbers are the same ones
  assert.deepEqual(D.flags, { potion_below: "--potion-below", fly_below: "--fly-below", fly_rate: "--fly-rate", fly_rate_below: "--fly-rate-below" });
});

test("the map's own numbers first, then every map's, then the defaults", () => {
  const none = effectiveSurvival(D, null, "xmas_dun02");
  assert.deepEqual(none.values, D.defaults);
  assert.equal(groupLevel(none.source), "default");
  const g = effectiveSurvival(D, { global: { potion_below: 0.3, fly_below: 0.15, fly_rate: 200, fly_rate_below: 0.6 }, maps: {} }, "xmas_dun02");
  assert.equal(g.values.potion_below, 0.3);
  assert.equal(groupLevel(g.source), "global");
  const cfg = { global: { potion_below: 0.3, fly_below: 0.15, fly_rate: 200, fly_rate_below: 0.6 }, maps: { xmas_dun02: { potion_below: 0.5, fly_below: 0.25, fly_rate: 120, fly_rate_below: 0.55 } } };
  const m = effectiveSurvival(D, cfg, "xmas_dun02");
  assert.deepEqual(m.values, cfg.maps.xmas_dun02);
  assert.equal(groupLevel(m.source), "map");
  // another map has no numbers of its own: every map's apply there
  assert.deepEqual(effectiveSurvival(D, cfg, "prt_fild08").values, cfg.global);
  // a partial level (a hand-edited file) fills only its own numbers
  const p = effectiveSurvival(D, { global: { fly_below: 0.1 }, maps: {} }, "xmas_dun02");
  assert.deepEqual(p.values, { ...D.defaults, fly_below: 0.1 });
  assert.deepEqual(p.source, { potion_below: "default", fly_below: "global", fly_rate: "default", fly_rate_below: "default" });
});

test("the numbers are checked against the export's choices", () => {
  assert.equal(survivalProblem(D.defaults, D), null);
  assert.equal(survivalProblem({ ...D.defaults, potion_below: 0.9, fly_below: 0.05, fly_rate: 1000, fly_rate_below: 0.2 }, D), null);
  assert.match(String(survivalProblem({ ...D.defaults, potion_below: 0.33 }, D)), /heal at HP under 33 %/);
  assert.match(String(survivalProblem({ ...D.defaults, fly_below: 0.7 }, D)), /Fly Wing at HP under 70 %/);
  for (const bad of [10, 2000, Number.NaN]) assert.match(String(survivalProblem({ ...D.defaults, fly_rate: bad }, D)), /fast fall/, String(bad));
});

test("the blocks show the numbers the next Run uses", () => {
  const mine = withSurvival(DOC, D, { potion_below: 0.55, fly_below: 0.25, fly_rate: 120, fly_rate_below: 0.65 });
  const words = (id: string) => {
    const n = allNodes(mine).find((x) => x.id === id);
    assert.ok(n, id);
    return [textOf(n.parts ?? []), ...(n.branches ?? []).map((b) => textOf(b.parts as RunnerPart[]))].join(" | ");
  };
  assert.match(words("potion"), /HP under 55 %: drink/);
  assert.match(words("wing_hp"), /HP under 25 %, or falling 120 HP\/s under 65 %/);
  assert.equal(mine.params["strategy.potion_below"].value, 0.55);
  assert.equal(mine.python, DOC.python);
  assert.match(textOf(allNodes(DOC).find((x) => x.id === "potion")?.branches?.[0].parts ?? []), /HP under 40 %/, "the export itself is unchanged");
});
