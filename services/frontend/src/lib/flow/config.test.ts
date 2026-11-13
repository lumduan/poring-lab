// THE FLOW CONFIG on /flows (lib/flow/config.ts; Batt 2026-11-13: "nothing is fixed, we only put the
// defaults"; "a global config for every map's flow; a map's flow that sets them again overrides
// it"; "move them too"; "all of them"): the registry the export carries, the map's own value
// first, the checks, the flags, and the blocks showing what the next Run uses.
import assert from "node:assert/strict";
import { test } from "node:test";

import { belowValue, configArgv, configClash, type ConfigDoc, configShownMatchesExport, effectiveConfig, fieldProblem, FIRST_GROUPS, levelAfter, shownValue, withConfig } from "./config.ts";
import { allNodes, textOf } from "./runner.ts";
import { XMAS_DUN02_ROGUE as DOC } from "./runners/xmas_dun02_rogue.gen.ts";

const C = DOC.config as ConfigDoc;
const F = (name: string) => {
  const f = C.fields.find((x) => x.name === name);
  assert.ok(f, name);
  return f;
};
const words = (d: typeof DOC, id: string) => {
  const n = allNodes(d).find((x) => x.id === id);
  assert.ok(n, id);
  return [textOf(n.parts ?? []), ...(n.branches ?? []).map((b) => textOf(b.parts))].join(" | ");
};

test("the export carries every setting: groups, kinds, defaults, the params that show it", () => {
  assert.ok(C, "config");
  assert.equal(C.map, "xmas_dun02");
  assert.ok(C.fields.length >= 70);
  const groups = new Set(C.groups.map((g) => g.id));
  for (const g of FIRST_GROUPS) assert.ok(groups.has(g), g);
  for (const f of C.fields) {
    assert.ok(groups.has(f.group), f.name);
    assert.equal(fieldProblem(f, f.default, C), null, `${f.name}'s default ${String(f.default)} is a valid value`);
    for (const p of f.params) assert.ok(p in DOC.params, `${f.name} shows as ${p}`);
  }
  assert.equal(F("heal_key").default, "F1");
  assert.equal(F("potion_below").default, 0.4);
  assert.equal(F("LOOT_TRIM_HOVERS").default, 9);
  assert.equal(F("LOOT_TRIM_HOVERS").flag, "--tune");
  assert.equal(configClash(C, effectiveConfig(C, null, "xmas_dun02").values), null);
});

test("with the defaults, every block reads exactly as the export wrote it", () => {
  assert.ok(configShownMatchesExport(DOC, C));
  const same = withConfig(DOC, C, effectiveConfig(C, null, "xmas_dun02").values);
  for (const n of allNodes(DOC)) assert.equal(words(same, n.id), words(DOC, n.id), n.id);
});

test("the map's own value first, then every map's, then the default", () => {
  const file = { global: { potion_below: 0.3, LOOT_TRIM_HOVERS: 12, fly_key: "F7" }, maps: { xmas_dun02: { potion_below: 0.5 }, prt_fild08: { fly_key: "F6" } } };
  const e = effectiveConfig(C, file, "xmas_dun02");
  assert.equal(e.values.potion_below, 0.5);
  assert.equal(e.source.potion_below, "map");
  assert.equal(e.values.fly_key, "F7"); // another map's own is not this map's
  assert.equal(e.source.LOOT_TRIM_HOVERS, "global");
  assert.equal(e.source.home_key, "default");
  assert.equal(belowValue(C, file, "map", "potion_below"), 0.3);
  assert.equal(belowValue(C, file, "global", "potion_below"), 0.4);
});

test("a change stores only what differs from the level below", () => {
  const file = { global: { potion_below: 0.3 }, maps: {} };
  assert.deepEqual(levelAfter(C, file, "map", "xmas_dun02", "survival", "potion_below", 0.45), { potion_below: 0.45 });
  assert.deepEqual(levelAfter(C, file, "map", "xmas_dun02", "survival", "potion_below", 0.3), {}); // = every map's: nothing of its own
  assert.deepEqual(levelAfter(C, file, "global", "xmas_dun02", "survival", "fly_below", 0.25), { potion_below: 0.3, fly_below: 0.25 });
  assert.deepEqual(levelAfter(C, file, "global", "xmas_dun02", "survival", "potion_below", 0.4), {}); // = the default
});

test("each value is checked as the bot server checks it", () => {
  assert.equal(fieldProblem(F("knife_max_s"), 0.2, C), null); // Batt's "F4, wait 200 ms, F5"
  assert.match(String(fieldProblem(F("knife_max_s"), 0.1, C)), /is not from/);
  assert.match(String(fieldProblem(F("potion_below"), 0.33, C)), /step of 5 %/);
  assert.match(String(fieldProblem(F("LOOT_TRIM_HOVERS"), 2.5, C)), /whole number/);
  assert.match(String(fieldProblem(F("fly_key"), "F12", C)), /not a row-1 hotbar key/);
  assert.equal(fieldProblem(F("respawn_confirm_at"), "none", C), null); // a server that asks nothing
  for (const bad of ["1280,10", "10,720", "x,1", "645", ""]) assert.match(String(fieldProblem(F("respawn_at"), bad, C)), /not a point/, bad);
  const vals = effectiveConfig(C, null, "xmas_dun02").values;
  assert.match(String(configClash(C, { ...vals, dagger_key: "F4" })), /the Knife and the dagger are both on F4/);
  assert.match(String(configClash(C, { ...vals, home_key: "F1" })), /the heal item and the Butterfly Wing are both on F1/);
});

test("the flags: each setting's own always, a runner number only when someone set it", () => {
  const e = effectiveConfig(C, { global: { LOOT_TRIM_HOVERS: 12 }, maps: { xmas_dun02: { knife_max_s: 0.2 } } }, "xmas_dun02");
  const a = configArgv(C, e.values, e.source);
  assert.equal(a[a.indexOf("--knife-max-s") + 1], "0.2");
  assert.equal(a[a.indexOf("--weight-home") + 1], "0.50");
  assert.equal(a[a.indexOf("LOOT_TRIM_HOVERS=12") - 1], "--tune");
  assert.ok(!a.some((x) => x.startsWith("KILL_GAP_S=")), "an unset runner number is the runner's own");
  // with no config the flags are the export's own base command's
  const d = effectiveConfig(C, null, "xmas_dun02");
  const base = DOC.command.base;
  const own = configArgv(C, d.values, d.source);
  assert.deepEqual(base.slice(base.length - own.length), own);
});

test("the blocks show what the next Run uses", () => {
  const vals = { ...effectiveConfig(C, null, "xmas_dun02").values, potion_below: 0.55, fly_key: "F6", dagger_key: "F7", knife_max_s: 0.2, LOOT_TRIM_HOVERS: 12 };
  const mine = withConfig(DOC, C, vals);
  assert.match(words(mine, "potion"), /HP under 55 %: drink/);
  assert.match(words(mine, "loot"), /12 at most/);
  assert.match(words(mine, "knife_off"), /0\.2 s/);
  assert.match(words(mine, "press_dagger"), /press F7/);
  assert.ok(!allNodes(mine).some((n) => /Fly Wing \(F2\)/.test(words(mine, n.id))), "the Fly Wing's key is the person's, never F2 in the words");
  assert.ok(allNodes(mine).some((n) => /Fly Wing \(F6\)/.test(words(mine, n.id))));
  assert.equal(mine.params["LOOT_TRIM_HOVERS"].value, 12);
  assert.equal(mine.python, DOC.python); // its lines are the blocks' marks
  assert.equal(shownValue(F("WEIGHT_MAX"), 0.48), "48");
});
