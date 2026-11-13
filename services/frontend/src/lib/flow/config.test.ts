// THE FLOW CONFIG on /flows (lib/flow/config.ts; Batt 2026-11-13: "nothing is fixed, we only put the
// defaults"; "a global config for every map's flow; a map's flow that sets them again overrides
// it"; "move them too"; "all of them"): the registry the export carries, the map's own value
// first, the checks, the flags, and the blocks showing what the next Run uses.
import assert from "node:assert/strict";
import { test } from "node:test";

import { belowValue, configArgv, configClash, type ConfigDoc, configShownMatchesExport, effectiveConfig, fieldProblem, FIRST_GROUPS, inUse, levelAfter, notInUseWhy, shownValue, withConfig } from "./config.ts";
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

// --- 2026-11-13 ~15:2x (Batt: "do all of them": the techniques' switches) ---------------------
test("a technique switched off: its settings are not in use, not passed, its blocks greyed", () => {
  const d = effectiveConfig(C, null, "xmas_dun02").values;
  assert.equal(d.knife_swap, true);
  const off = { ...d, knife_swap: false };
  for (const n of ["bare_ready", "steal_cue", "swap_gap", "knife_key", "dagger_key", "knife_max_s", "knife_hp_min"]) assert.equal(inUse(C, off, n), false, n);
  assert.match(String(notInUseWhy(C, off, "knife_max_s")), /needs Batt's Knife swap on/);
  const a = configArgv(C, off, effectiveConfig(C, null, "xmas_dun02").source);
  for (const flag of ["--bare-steal", "--bare-ready", "--steal-opener", "--dagger-key", "--knife-max-s"]) assert.ok(!a.includes(flag), flag);
  assert.equal(configClash(C, { ...off, dagger_key: "F9" }), null); // an unused key clashes with nothing
  const mine = withConfig(DOC, C, off);
  for (const id of ["knife_opener", "knife_back_fn", "knife_on_call", "knife_back_call"]) {
    const n = allNodes(mine).find((x) => x.id === id);
    assert.ok(n && n.style.startsWith("rd_off"), id);
    assert.match(words(mine, id), /^off: /, id);
  }
  assert.ok(!allNodes(withConfig(DOC, C, d)).some((n) => n.style.startsWith("rd_off")), "with the defaults nothing is off");
});

test("switches, choices and a chain of needs", () => {
  const d = effectiveConfig(C, null, "xmas_dun02").values;
  const src = effectiveConfig(C, null, "xmas_dun02").source;
  assert.ok(configArgv(C, { ...d, exp_first: false }, src).includes("--no-exp-first"));
  assert.ok(configArgv(C, { ...d, respawn: false }, src).includes("--no-respawn"));
  assert.ok(!configArgv(C, { ...d, respawn: false }, src).includes("--respawn-at"));
  assert.ok(!configArgv(C, { ...d, loot: "v1" }, src).includes("--loot-items"));
  assert.ok(!configArgv(C, { ...d, loot_items: "off" }, src).includes("--loot-memory"));
  assert.equal(inUse(C, { ...d, box_strike: false }, "lead_press"), false); // lead -> still_target -> box_now -> box_strike
  assert.equal(fieldProblem(F("loot"), "nope", C) !== null, true);
  assert.equal(fieldProblem(F("hud"), true, C), null);
  assert.match(String(configClash(C, { ...d, hud_fast: 0.5, BOX_EVERY_S: 0.5 })), /faster than the detector/);
  assert.equal(shownValue(F("hud"), false), "off");
});

test("the start checklist says what must be true, from the values the run takes", async () => {
  const { startChecklist, CHECKLIST_IDS } = await import("./config.ts");
  const d = effectiveConfig(C, null, "xmas_dun02").values;
  const items = startChecklist(C, d, "xmas_dun02");
  const c = items.map((x) => x.text);
  assert.ok(c.some((x) => /stands on xmas_dun02/.test(x)));
  assert.ok(c.some((x) => /bag under 48 %/.test(x)));
  assert.ok(c.some((x) => /at least 5 Fly Wings on F8/.test(x)));
  assert.ok(c.some((x) => /heal items on F1/.test(x)));
  assert.ok(c.some((x) => /Knife on F4/.test(x)));
  assert.ok(c.some((x) => /dagger worn \(F5/.test(x)));
  // each line's id is the live check's (scripts/dungeon_hunt.py CHECK_IDS), in that order
  assert.deepEqual(
    items.map((x) => x.id),
    CHECKLIST_IDS,
  );
  const noKnife = startChecklist(C, { ...d, knife_swap: false }, "xmas_dun02");
  assert.ok(!noKnife.some((x) => /Knife|dagger/.test(x.text)));
  assert.deepEqual(
    noKnife.map((x) => x.id),
    CHECKLIST_IDS.filter((x) => x !== "knife" && x !== "dagger"),
  );
  assert.ok(startChecklist(C, { ...d, fly_key: "F6", PLAYER_MIN_WINGS: 3 }, "xmas_dun02").some((x) => /at least 3 Fly Wings on F6/.test(x.text)));
  // a line states the values it needs (a check made with others is outdated)
  const wings = items.find((x) => x.id === "wings");
  assert.deepEqual(wings?.basis, { PLAYER_MIN_WINGS: 5, fly_key: "F8" });
});

// Batt 2026-11-13: every hotbar key from a FUNCTION of the flow -- the checklist states those keys
test("the flow's keys go over the settings' in the checklist", async () => {
  const { startChecklist, checklistWithKeys, withRunKeys, RUN_KEY_NAMES } = await import("./config.ts");
  const d = effectiveConfig(C, null, "xmas_dun02").values;
  const keys = { heal_key: "F2", fly_key: "F3", home_key: "F6", knife_key: "F7", dagger_key: "F9" };
  const k = startChecklist(C, d, "xmas_dun02", keys);
  const t = (id: string) => k.find((x) => x.id === id)?.text ?? "";
  assert.match(t("wings"), /on F3$/);
  assert.match(t("heals"), /on F2$/);
  assert.match(t("home"), /on F6 /);
  assert.match(t("knife"), /on F7 /);
  assert.match(t("dagger"), /\(F9 empty/);
  // the same from the settings' list with the keys put over it (LiveRun's keys prop)
  assert.deepEqual(checklistWithKeys(startChecklist(C, d, "xmas_dun02"), keys), k);
  assert.deepEqual(checklistWithKeys(k, null), k);
  // only the five keys go over: nothing else a request could carry
  const w = withRunKeys(d, { ...keys, PLAYER_MIN_WINGS: "1" } as Record<string, string>);
  assert.equal(w.PLAYER_MIN_WINGS, 5);
  assert.deepEqual(RUN_KEY_NAMES, ["heal_key", "fly_key", "home_key", "knife_key", "dagger_key"]);
  assert.deepEqual(withRunKeys(d, null), d);
});
