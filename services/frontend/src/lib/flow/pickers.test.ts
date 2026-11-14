// Round 21 (live-blocks.md 12.5): the pickers' pure part (lib/flow/pickers.ts), in the spirit of
// matpilot's fields.test.ts (https://github.com/lumduan/matpilot at 4022c87, MIT; THIRD_PARTY.md):
// a value in is the same value out, the clamp, the step, the text shown, the search ranking, and a
// value that is not in the list KEPT, marked. The Blockly fields themselves (they save, load and
// show these) are in blockly_headless.test.ts.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";

import type { CatalogueDoc } from "./api.ts";
import { DEF_BY_TYPE } from "./blockdefs.ts";
import { exprText } from "./expr.ts";
import type { Models } from "./models.ts";
import {
  argRows,
  argsWith,
  buttonStep,
  callArgsWith,
  callRows,
  closedText,
  completions,
  complete,
  condFor,
  condOf,
  condText,
  defOn,
  exprProblem,
  fitDropDown,
  functionsOn,
  GAME_AREAS,
  matchScore,
  niceStep,
  numberOf,
  numText,
  optNumOf,
  pickerColours,
  type PickerData,
  pickerList,
  type PickSpec,
  pointIn,
  presetsOf,
  rankChoices,
  recipeNames,
  refChoices,
  refKnown,
  sensorsOf,
  skillKeysOn,
  sliderKey,
  snap,
  stepBy,
  stopReasons,
  toArea,
  TARGET_BLOCKS,
  toViewBox,
  typedProblem,
} from "./pickers.ts";
import * as PLACE from "./pickers.ts";
import { SETTINGS } from "./settings.ts";
import { BLOCK_STYLES, contrast } from "./theme.ts";
import { MAIN_TAB, nodeById, type Project, sampleProject, xmasHuntProject, xmasProject } from "./project.ts";

const MODELS: Models = {
  v1: { kind: "detector", status: "live", file: "a.onnx", sha256: "a", maps: [], classes: ["monster"], untrained: [], mobs: {}, why: "", available: true, counts: true },
  xmas02: { kind: "detector", status: "live", file: "b.onnx", sha256: "b", maps: ["xmas_dun02"], classes: ["mystcase", "cookie"], untrained: [], mobs: { mystcase: [1061], cookie: [1265] }, strikes: ["mystcase", "cookie"], why: "", available: true, counts: true },
  "stormy-v1": { kind: "boss_recognizer", status: "not_adopted", file: "c.npz", sha256: "c", maps: ["xmas_dun02"], classes: ["party"], untrained: [], mobs: {}, why: "failed", available: false, counts: false },
};
const sensor = (type: string, more: Record<string, unknown> = {}) => ({ name: "", badge: "unverified" as const, spec: { type, passive: true, ...more } });
/** A catalogue as the backend serves it (the parts the pickers read), synthetic. */
const CAT = {
  version: 1,
  blocks: {
    use_model: { name: "use_model", spec: { concept: "core.use_model", kind: "core", timeout_s: 1, params: [{ name: "model", type: "str", required: true, note: "a trained model's id" }] }, status: "", badge: "core", purpose: null, verified_on: [] },
    use_skill: { name: "use_skill", spec: { concept: "combat.use_skill", kind: "action", timeout_s: 30, params: [{ name: "skill", type: "skill", required: false }, { name: "key", type: "str", required: false, options: ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9"] }] }, status: "", badge: "unverified", purpose: null, verified_on: [] },
  },
  sensors: {
    hp_percent: sensor("percent", { range: [0, 100], live: true }),
    weight_percent: sensor("percent", { range: [0, 100], live: true }),
    is_dead: sensor("bool", { live: true }),
    hotbar_count: sensor("int", { range: [0, 999], live: true, params: [{ name: "key", type: "str", required: true, options: ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9"] }] }),
    current_map: sensor("map", { live: true }),
    position: sensor("cell"),
    detector_sees: sensor("bool"),
  },
  palette: [],
  windows: ["basic_info", "inventory"],
  safety_critical: [],
  models: MODELS,
  servers: [{ id: "lab-rathena", status: "allowed", lab: true }],
} as unknown as CatalogueDoc;
const xmas = (tab = MAIN_TAB, extra: Partial<PickerData> = {}): PickerData => ({ project: xmasProject(), node: "xmas_dun02", tab, catalogue: CAT, maps: { server: "lab-rathena", source: "sample", maps: [{ id: "town_b", kafra: true }, { id: "field_a", kafra: false }, { id: "town_a", kafra: true }], notes: [] }, ...extra });
const at = (blockType: string, field: string, siblings: Record<string, string> = {}, more: Partial<{ parentInput: string | null; params: string[] }> = {}) => ({ blockType, field, sibling: (n: string) => siblings[n] ?? "", ...more });
const ref = (r: Extract<PickSpec, { kind: "ref" }>["ref"], more: { role?: string; optional?: string } = {}): Extract<PickSpec, { kind: "ref" }> => ({ kind: "ref", ref: r, title: "", ...more });

test("the search ranks: the word itself, then a start, a word's start, inside, letters in order; ties keep the list's order", () => {
  const cs = ["fly_home", "fly_wing", "butterfly_wing", "wield_knife", "knife_on", "heal"].map((v) => ({ value: v, label: v }));
  assert.deepEqual(rankChoices("fly", cs).map((c) => c.value), ["fly_home", "fly_wing", "butterfly_wing"]);
  assert.deepEqual(rankChoices("knife", cs).map((c) => c.value), ["knife_on", "wield_knife"]);
  assert.deepEqual(rankChoices("fly wing", cs).map((c) => c.value), ["fly_wing", "butterfly_wing"]);
  assert.deepEqual(rankChoices("flwg", cs).map((c) => c.value), ["fly_wing", "butterfly_wing"]); // fuzzy
  assert.deepEqual(rankChoices("heal", cs).map((c) => c.value), ["heal"]);
  assert.deepEqual(rankChoices("", cs), cs); // nothing typed: the whole list, in order
  assert.equal(matchScore("HEAL", { value: "heal", label: "heal" }), 0);
  assert.equal(matchScore("zzz", { value: "heal", label: "heal" }), null);
  // a hint matches last
  assert.deepEqual(rankChoices("F8", [{ value: "a", label: "a", note: "presses F8" }, { value: "f8x", label: "f8x" }]).map((c) => c.value), ["f8x", "a"]);
});

test("a value that is not in the list is KEPT and leads, marked; a typed word is offered as typed, or refused with why", () => {
  const cs = [{ value: "heal", label: "heal" }];
  const l = pickerList("", cs, { current: "no_such_fn" });
  assert.equal(l[0].value, "no_such_fn");
  assert.match(l[0].note ?? "", /kept as it is/);
  const typed = pickerList("my_new", cs, { typed: (w) => typedProblem("function", w) });
  assert.deepEqual(typed.at(-1), { value: "my_new", label: "my_new", note: "use it as typed", group: "typed" });
  const bad = pickerList("2bad", cs, { typed: (w) => typedProblem("function", w) });
  assert.equal(bad.at(-1)?.group, "refused");
  // a model cannot be typed in: choose one of the list (a loaded unknown one is still kept)
  assert.match(typedProblem("model", "xmas03") ?? "", /choose one/);
  // an optional field offers its empty word first
  assert.deepEqual(pickerList("", cs, { empty: "none" })[0], { value: "", label: "none", group: "none" });
});

test("numbers: the step, the grid, the clamp of the CONTROL; the keys of a slider (matpilot's sliderKey)", () => {
  const r = { lo: 20, hi: 90, step: 5 };
  assert.equal(snap(57, r), 55);
  assert.equal(snap(140, r), 90); // the control's range: the steppers and the slider stop at its ends
  assert.equal(snap(-3, r), 20);
  assert.equal(stepBy(50, 1, r), 55);
  assert.equal(stepBy(52, 1, r), 55); // off the grid (loaded so): to the next line in that direction
  assert.equal(stepBy(52, -1, r), 50);
  assert.equal(stepBy(90, 1, r), 90);
  assert.equal(stepBy(50, 1, r, true), 90);
  assert.equal(stepBy(0.7, 1, { lo: 0, hi: 30, step: 0.1 }), 0.8); // no float noise
  assert.equal(sliderKey("Home", 50, r), 20);
  assert.equal(sliderKey("End", 50, r), 90);
  assert.equal(sliderKey("PageDown", 80, r), 30);
  assert.equal(sliderKey("ArrowLeft", 50, r), 45);
  assert.equal(sliderKey("a", 50, r), null);
  assert.equal(numText(1, "cells", "cell"), "1 cell");
  assert.equal(numText(2.5, "s"), "2.5 s");
  assert.deepEqual(presetsOf(r), [25, 40, 50, 75, 90]); // round 22: round values near the quarters
  assert.deepEqual(presetsOf({ lo: 5, hi: 95, step: 1 }), [10, 25, 50, 75, 90]); // not 5 / 28 / 50 / 73 / 95
  assert.deepEqual(presetsOf({ lo: 0, hi: 60, step: 0.5 }, [0.5, 1, 2, 5, 10, 99]), [0.5, 1, 2, 5, 10]);
  assert.deepEqual(pointIn(1500, -4), [1279, 0]);
  // an optional number in a text field: empty = none / the default, garbage kept (NaN), never a guess
  assert.equal(optNumOf(""), null);
  assert.equal(optNumOf(" 7 "), 7);
  assert.ok(Number.isNaN(optNumOf("abc") as number));
});

test("what a picker field shows closed: a reference with ▾, ⚠ when it is unknown, an empty optional one its word", () => {
  const role = ref("role", { role: "home", optional: "none" });
  assert.equal(closedText(role, "fly_home", "fly_home", true), "fly_home ▾");
  assert.equal(closedText(role, "fly_hom", "fly_hom", false), "fly_hom ⚠ ▾");
  assert.equal(closedText(role, "", "", true), "none ▾");
  const opt: PickSpec = { kind: "optnum", lo: 1, hi: 60, step: 1, empty: "—", none: "no limit", title: "" };
  assert.equal(closedText(opt, "", ""), "—");
  assert.equal(closedText(opt, "5", "5"), "5");
  assert.equal(closedText(opt, "abc", "abc"), "abc ⚠");
  const num: PickSpec = { kind: "stepper", lo: 0, hi: 60, step: 0.5, title: "" };
  assert.equal(closedText(num, "1.5", "1.5"), "1.5"); // a number shows as the plain field did (the width model holds)
});

test("references list what exists at edit time: the node's and Global's functions, a role's usual one first", () => {
  const d = xmas();
  const fns = functionsOn(d).map((f) => f.name);
  for (const n of ["heal", "fly_wing", "eat", "drink", "knife_on", "fly_home", "attack_mystcase"]) assert.ok(fns.includes(n), n);
  const call = refChoices(ref("function"), d);
  assert.equal(call.find((c) => c.value === "heal")?.note, "presses F1 · tab keys");
  assert.equal(call.find((c) => c.value === "knife_on")?.note, "calls wield_knife · tab knife");
  assert.equal(call.find((c) => c.value === "eat")?.note, "(key) · tab keys");
  assert.equal(call.find((c) => c.value === "respawn_ok")?.note, "clicks a point · tab exits");
  // events come after the functions
  const firstEvent = call.findIndex((c) => c.group === "events");
  assert.ok(firstEvent > 0 && call.slice(firstEvent).every((c) => c.group === "events"));
  // a role: its usual function first, then the ones that press a key, never an event
  const heal = refChoices(ref("role", { role: "heal" }), d);
  assert.equal(heal[0].value, "heal");
  assert.match(heal[0].note ?? "", /^the usual one · presses F1/);
  assert.ok(!heal.some((c) => c.value === "drink"));
  assert.ok(heal.findIndex((c) => c.value === "butterfly_wing") < heal.findIndex((c) => c.value === "fly_home"));
  // escalate: functions only
  assert.ok(!refChoices(ref("escalate"), d).some((c) => c.group === "events"));
  // a function written on the tab and not converted yet is callable at once
  assert.ok(refChoices(ref("function"), { ...d, extraDefs: ["brand_new"] }).some((c) => c.value === "brand_new"));
  // Global's functions on a map node (the sample: Global's butterfly_wing)
  const s = sampleProject();
  const map = s.nodes.find((n) => n.kind === "map")!;
  assert.ok(refChoices(ref("function"), { project: s, node: map.id, tab: MAIN_TAB, catalogue: null, maps: null }).some((c) => c.value === "butterfly_wing" && /Global/.test(c.note ?? "")));
});

test("models, maps, stop reasons, nodes, entries, windows, servers and variables", () => {
  const d = xmas();
  const models = refChoices(ref("model"), d);
  assert.deepEqual(models.map((c) => c.value), ["v1", "xmas02", "stormy-v1"]); // the not adopted last
  assert.equal(models[1].note, "a detector · xmas_dun02 · live");
  assert.equal(models[2].note, "a boss recognizer · xmas_dun02 · not adopted");
  // the save point's map: the maps with a Kafra first; the project's own map marked
  assert.deepEqual(refChoices(ref("save_map"), d).map((c) => c.value), ["town_a", "town_b", "field_a", "xmas_dun02"]);
  const map = refChoices(ref("map"), d);
  assert.equal(map[0].value, "xmas_dun02");
  assert.equal(map[0].note, "a map of this project");
  // stop reasons: the project's (xmas: "home", twice), then the usual ones
  assert.deepEqual([...stopReasons(d.project)], [["home", 2]]);
  assert.deepEqual(refChoices(ref("stop"), d).map((c) => c.value), ["home", "done"]);
  assert.deepEqual(refChoices(ref("node"), d).map((c) => c.value), ["xmas_dun02"]);
  assert.deepEqual(refChoices(ref("entry"), d, at("pl_exit_walk", "TO_ENTRY", { TO_BLOCK: "xmas_dun02" })).map((c) => c.value), ["here"]);
  assert.deepEqual(refChoices(ref("window"), d).map((c) => c.value), ["basic_info", "inventory"]);
  assert.deepEqual(refChoices(ref("server"), d).map((c) => c.value), ["lab-rathena"]);
  const vars = refChoices(ref("variable"), d, at("pl_set", "VAR", {}, { params: ["t", "priority"] }));
  assert.deepEqual(vars.slice(0, 2).map((c) => c.value), ["t", "priority"]);
  assert.ok(vars.some((c) => c.value === "knife_swap" && /tab knife/.test(c.note ?? "")));
});

test("known or not: an unknown value is marked, an empty optional one is fine, and unknown while the list is not here", () => {
  const d = xmas();
  assert.equal(refKnown(ref("function"), "heal", d), true);
  assert.equal(refKnown(ref("function"), "no_such_fn", d), false);
  assert.equal(refKnown(ref("role", { role: "home", optional: "none" }), "", d), true);
  assert.equal(refKnown(ref("role", { role: "heal" }), "", d), false);
  assert.equal(refKnown(ref("model"), "xmas03", d), false);
  assert.equal(refKnown(ref("model"), "xmas03", { ...d, catalogue: null }), null); // no catalogue: cannot tell
  assert.equal(refKnown(ref("save_map"), "nowhere", d), false);
  assert.equal(refKnown(ref("save_map"), "nowhere", { ...d, maps: null }), null); // the list not here yet
  assert.equal(refKnown(ref("map"), "xmas_dun02", { ...d, maps: null }), true); // the project's own map
  assert.equal(refKnown(ref("stop"), "any_reason", d), true); // a stop reason is the run's words
  assert.equal(refKnown(ref("function"), "heal", { ...d, project: null }), null);
});

test("conditions: the parts of `hp_percent() < 50` print back EXACTLY; a percent's new condition is under 50", () => {
  for (const t of ["hp_percent() < 50", "hp_percent() >= 51", "weight_percent() >= 50", 'hotbar_count(key="F6") >= 1', "is_dead()", "not is_dead()", "current_map() == map_id(\"xmas_dun02\")", "x != 3"]) {
    const c = condOf(t);
    assert.ok(c, t);
    assert.equal(condText(c), t, t);
  }
  for (const t of ["hp_percent() < 50 and is_dead()", "1 + 2", "hp_percent(", "", "x"]) assert.equal(condOf(t), null, t);
  const c = condOf("hp_percent() < 50")!;
  assert.equal(c.name, "hp_percent");
  assert.equal(c.op, "<");
  // a new value, a new comparison: printed by the block's own printer
  assert.equal(condText({ ...c, right: { kind: "lit", value: 30 } }), "hp_percent() < 30");
  assert.equal(condText({ ...c, op: ">=" }), "hp_percent() >= 50");
  const s = sensorsOf(xmas());
  assert.ok(!s.some((x) => x.name === "position" || x.name.startsWith("detector_"))); // cells and the models' own blocks
  assert.equal(s.find((x) => x.name === "heal")?.fn, true); // the node's functions: their value
  const hp = s.find((x) => x.name === "hp_percent")!;
  assert.equal(condText(condFor(hp, null)), "hp_percent() < 50");
  const hot = s.find((x) => x.name === "hotbar_count")!;
  assert.equal(condText(condFor(hot, null)), 'hotbar_count(key="F1") >= 0');
  assert.equal(condText(condFor(s.find((x) => x.name === "is_dead")!, c)), "is_dead()");
  assert.equal(condText(condFor(hp, condOf("weight_percent() >= 70"))), "hp_percent() >= 70"); // keeps its comparison and value
  assert.equal(numberOf("3"), 3);
  assert.equal(numberOf("x"), null);
});

test("every event condition of the ready-made projects that the picker shows prints back byte for byte", () => {
  let shown = 0;
  let all = 0;
  for (const p of [xmasProject(), sampleProject()] as Project[]) {
    for (const n of p.nodes) for (const t of n.tabs) for (const d of t.defs) {
      for (const e of [d.on?.when, d.on?.until, d.on?.rearm]) {
        if (!e) continue;
        all++;
        // the block and the Python show this text (blocks.ts exprBlock); the picker edits that text
        const text = exprText(e);
        const c = condOf(text);
        if (!c) continue;
        shown++;
        assert.equal(condText(c), text, text);
      }
    }
  }
  assert.ok(all >= 6 && shown >= 4, `${shown} of ${all}`);
});

test("the typed fallback completes sensors, functions and variables; after a value, the comparisons; after key=, the keys", () => {
  const d = xmas();
  const hp = completions("hp_p", 4, d);
  assert.equal(hp.from, 0);
  assert.equal(hp.choices[0].value, "hp_percent()");
  assert.deepEqual(complete("hp_p", hp, hp.choices[0].value), { text: "hp_percent()", caret: 12 });
  const hot = completions("hotb", 4, d);
  assert.equal(hot.choices[0].value, 'hotbar_count(key="F1")');
  const ops = completions("hp_percent() ", 13, d);
  assert.deepEqual(ops.choices.slice(0, 6).map((c) => c.label), ["<", "<=", ">", ">=", "==", "!="]);
  assert.equal(completions("hp_percent() < 50 and ", 22, d).choices.length, 0); // no comparison after "and"
  const key = completions('hotbar_count(key="F', 19, d);
  assert.equal(key.from, 17);
  assert.equal(complete('hotbar_count(key="F', key, key.choices[0].value).text, 'hotbar_count(key="F1"');
  const fn = completions("kni", 3, d);
  assert.ok(fn.choices.some((c) => c.value === "knife_on()"));
  const v = completions("t", 1, d, at("pl_expr", "TEXT", {}, { params: ["target_mob"] }));
  assert.equal(v.choices[0].value, "target_mob");
  assert.ok(completions("an", 2, d).choices.some((c) => c.value === "and"));
});

test("a block's inputs as rows: use_model's model from the list, the text printed as the block always prints it", () => {
  const rows = argRows("use_model", 'model="xmas02"', CAT)!;
  assert.deepEqual(rows.map((r) => [r.name, r.kind, r.text]), [["model", "model", '"xmas02"']]);
  assert.equal(argsWith('model="xmas02"', "model", '"v1"'), 'model="v1"');
  // an unknown parameter is a row too (kept; the lint names it)
  assert.deepEqual(argRows("use_model", 'model="xmas03", speed=2', CAT)!.map((r) => r.name), ["model", "speed"]);
  assert.equal(argsWith('model="xmas03", speed=2', "speed", null), 'model="xmas03"');
  const skill = argRows("use_skill", 'key="F6"', CAT)!;
  assert.equal(skill.find((r) => r.name === "key")?.kind, "key");
  assert.equal(argRows("use_model", "model=", CAT), null); // a text that does not read: fix it first
  assert.throws(() => argsWith("model=", "model", '"v1"'));
});

test("live blocks 5b-2: a hunt block's target is a variable row, use_skill's key the declared one", () => {
  const cat = { ...CAT, blocks: { ...CAT.blocks, fight_target: { spec: { params: [{ name: "target", type: "mob", required: true }] } }, strike: { spec: { params: [{ name: "target", type: "mob", required: true }] } } } } as unknown as typeof CAT;
  for (const b of ["fight_target", "strike"]) assert.deepEqual(argRows(b, "target=t", cat)!.map((r) => [r.name, r.kind, r.text]), [["target", "variable", "t"]]);
  assert.ok(TARGET_BLOCKS.has("loot") && TARGET_BLOCKS.has("walk_to_target") && !TARGET_BLOCKS.has("use_skill"));
  // the declared keys: the hunt core's heal key (the hunt box's F1); none on a node without one
  const p = xmasHuntProject();
  assert.deepEqual(skillKeysOn({ project: p, node: "xmas_dun02", tab: "hunt", catalogue: null, maps: null }), ["F1"]);
  assert.deepEqual(skillKeysOn({ project: sampleProject(), node: "town", tab: "main", catalogue: null, maps: null }), []);
  // the variable list for VAR and a target: the hunt loop's input t first
  const v = refChoices({ kind: "ref", ref: "variable", title: "" }, { project: p, node: "xmas_dun02", tab: "hunt", catalogue: null, maps: null }, at("pl_hunt_take", "VAR", {}, { params: ["t"] }));
  assert.equal(v[0].value, "t");
});

test("a call's inputs as rows: eat(key) by position stays by position; a new one by name", () => {
  const d = xmas("keys");
  const eat = defOn(d, "eat")!;
  const rows = callRows(eat, '"F6"')!;
  assert.deepEqual(rows.map((r) => [r.name, r.kind, r.text, r.positional]), [["key", "key", '"F6"', true]]);
  assert.equal(callArgsWith(eat, '"F6"', "key", '"F7"'), '"F7"');
  assert.equal(callArgsWith(eat, "", "key", '"F7"'), '"F7"');
  assert.equal(callArgsWith(eat, '"F6"', "key", null), "");
  assert.equal(callArgsWith(eat, "key=\"F6\"", "key", '"F9"'), 'key="F9"');
  assert.deepEqual(callRows(eat, '"F6", 2')!.map((r) => r.name), ["key", "more 1"]); // more than it takes: kept, a row
  assert.equal(callRows(null, "x=")?.length, undefined);
});

test("the monsters tab suggests a recipe's name for each monster of the node's model (a name stays free text)", () => {
  const d = xmas("monsters");
  const names = recipeNames(d, "xmas02");
  assert.deepEqual(names.map((c) => c.value).sort(), ["attack_cookie", "attack_mystcase"]);
  assert.ok(names.every((c) => /written already/.test(c.note ?? "") === (c.group === "written")));
  assert.deepEqual(recipeNames(xmas("keys"), "xmas02"), []);
});

test("every picker in the block definitions is a field the converter reads (a number or a text)", () => {
  let n = 0;
  for (const d of Object.values(DEF_BY_TYPE)) {
    for (const args of [d.args0, d.args1, d.args2, d.args3, d.args4, d.args5, d.args6, d.args7, d.args8]) {
      for (const a of args ?? []) {
        if (!("pick" in a) || !a.pick) continue;
        n++;
        const numeric = a.pick.kind === "stepper" || a.pick.kind === "percent" || a.pick.kind === "point" || a.pick.kind === "cell";
        assert.equal(a.type, numeric ? "field_pl_num" : "field_pl_text", `${d.type}.${a.name}`);
        if (a.pick.kind === "point" || a.pick.kind === "cell") assert.ok(args!.some((b) => "name" in b && b.name === (a.pick as { pair: string }).pair), `${d.type}.${a.name}'s pair`);
      }
    }
  }
  assert.ok(n >= 120, String(n)); // the setting blocks' values and points, and the blocks' fields
  // the names a block DEFINES stay text: a function's (with suggestions), a variable's, an event's
  const def = DEF_BY_TYPE.pl_def.args0!;
  assert.deepEqual(def.filter((a) => a.type !== "input_end_row").map((a) => ("pick" in a && a.pick ? a.pick.kind : a.type)), ["name", "field_input"]);
  assert.equal(DEF_BY_TYPE.pl_vardecl.args0![0].type, "field_input");
  assert.equal(DEF_BY_TYPE.pl_event.args1![0].type, "field_input");
  assert.ok(nodeById(xmasProject(), "xmas_dun02"));
});

// --- round 22 (the reviewer's measure of round 21 in a real browser) -------------------------------
test("round 22: a picker opens below or above its field, scrolls the field to where it fits, then compact, then capped -- never over it", () => {
  const { placePicker, PICKER_GAP, PICKER_MARGIN } = PLACE;
  // 390 x 844: the blocks area 416 px tall from y 400; a field mid-area; a 407 px picker
  const area = { areaTop: 400, areaBottom: 816 };
  const mid = { ...area, fieldTop: 560, fieldBottom: 584 };
  assert.deepEqual(placePicker({ ...mid, height: 150 }, true, false), { side: "below", scrollBy: 0, compact: false, maxHeight: null });
  assert.deepEqual(placePicker({ ...area, fieldTop: 780, fieldBottom: 804, height: 300 }, true, false), { side: "above", scrollBy: 0, compact: false, maxHeight: null });
  // fits on neither side, but the area holds the field and the picker: scroll the field to the top
  const sc = placePicker({ ...mid, height: 340 }, true, false);
  assert.equal(sc.side, "below");
  assert.equal(sc.scrollBy, 560 - (400 + PICKER_MARGIN)); // the shorter scroll: the field to the top
  assert.equal(placePicker({ ...area, fieldTop: 640, fieldBottom: 664, height: 340 }, true, false).side, "above"); // nearer the bottom: to the bottom
  // after that scroll it fits below
  const after = { ...area, fieldTop: 560 - sc.scrollBy, fieldBottom: 584 - sc.scrollBy, height: 340 };
  assert.equal(placePicker(after, false, false).side, "below");
  assert.ok(after.fieldBottom + PICKER_GAP + 340 <= area.areaBottom);
  // too tall for the area even after a scroll: compact first, then capped to the larger side
  assert.deepEqual(placePicker({ ...mid, height: 407 }, true, false), { side: "below", scrollBy: 0, compact: true, maxHeight: null });
  const cap = placePicker({ ...mid, height: 407 }, false, true);
  assert.equal(cap.compact, true);
  assert.ok(cap.maxHeight !== null && 584 + PICKER_GAP + cap.maxHeight <= area.areaBottom, JSON.stringify(cap));
  // never over the field: whatever the case, the side it takes holds the picker as planned
  for (let top = 410; top < 800; top += 37) {
    for (const h of [120, 250, 340, 407]) {
      const m = { ...area, fieldTop: top, fieldBottom: top + 24, height: h };
      let p = placePicker(m, true, false);
      const scrolled = { ...m, fieldTop: m.fieldTop - p.scrollBy, fieldBottom: m.fieldBottom - p.scrollBy };
      if (p.scrollBy) p = placePicker(scrolled, false, false);
      if (p.compact) p = placePicker(scrolled, false, true);
      const height = p.maxHeight ?? h;
      if (p.side === "below") assert.ok(scrolled.fieldBottom + PICKER_GAP + height <= area.areaBottom, `${top} ${h}`);
      else assert.ok(scrolled.fieldTop - PICKER_GAP - height >= area.areaTop, `${top} ${h}`);
    }
  }
});

test("round 22: the point picture maps a pointer through its own box: 50 % and 55 % read 360 and 396 (the mouse drag read y 691)", () => {
  // the picture 256 x 144 drawn at (100, 300) on the screen, 256 px wide (as the picker draws it)
  const box = { left: 100, top: 300, width: 256, height: 144 };
  const view = { width: 256, height: 144 };
  const read = (fx: number, fy: number) => {
    const [x, y] = toViewBox(box.left + fx * box.width, box.top + fy * box.height, box, view);
    return pointIn((x * 1280) / 256, (y * 720) / 144);
  };
  assert.deepEqual(read(0.5, 0.5), [640, 360]);
  assert.deepEqual(read(0.55, 0.55), [704, 396]);
  assert.deepEqual(read(0.6, 0.6), [768, 432]); // not stuck at 719
  // a picture drawn smaller (max-width) maps the same
  assert.deepEqual(toViewBox(150, 336, { left: 100, top: 300, width: 128, height: 72 }, view), [100, 72]);
  // the client's fixed windows are outlined inside the picture
  for (const a of GAME_AREAS) {
    const [x, y, w, h] = a.box;
    assert.ok(x >= 0 && y >= 0 && x + w <= 1280 && y + h <= 720, a.name);
  }
});

test("round 22: +/- take a nice step (about 1 % of the range), never finer than the field's; presets are round", () => {
  assert.equal(niceStep({ lo: 0.5, hi: 30, step: 0.01 }), 0.5); // END_HOT_S: 59 taps, not 2,950
  assert.equal(buttonStep(2, 1, { lo: 0.5, hi: 30, step: 0.01 }), 2.5);
  assert.equal(niceStep({ lo: 1, hi: 30, step: 1 }), 1); // never finer than the field's step
  assert.equal(niceStep({ lo: 0, hi: 1000, step: 1 }), 10);
  assert.equal(niceStep({ lo: 0, hi: 3600, step: 0.1 }), 50);
  assert.equal(niceStep({ lo: 20, hi: 90, step: 5 }), 5);
  assert.equal(niceStep({ lo: 0, hi: 0.2, step: 0.001 }), 0.002);
});

test("round 22: an unfinished condition says so in a learner's words", () => {
  assert.equal(exprProblem("hp_percent() >= "), "the condition is not finished: a value is missing after >=");
  assert.equal(exprProblem("hp_percent() < 50 and"), "the condition is not finished: a value is missing after and");
  assert.equal(exprProblem("hotbar_count(key=\"F6\""), "a ( is not closed: add ) after its inputs");
  assert.equal(exprProblem('hotbar_count(key="F6) > 0'), 'a text in quotes is not closed: add " at its end');
  assert.equal(exprProblem("hp_percent() < 50"), "");
  assert.doesNotMatch(exprProblem("hp_percent() >= "), /col [0-9]+|unexpected "end"/);
});

test("round 22: a picker on a greyed block reads at 4.5:1 or more (every block style, light and dark)", () => {
  for (const [name, st] of Object.entries(BLOCK_STYLES)) {
    const c = pickerColours(st.colourPrimary, (st as { colourTertiary?: string }).colourTertiary ?? st.colourPrimary);
    assert.ok(contrast(c.primary, "#ffffff") >= 4.5, `${name}: ${c.primary} ${contrast(c.primary, "#ffffff").toFixed(2)}:1`);
  }
  const grey = pickerColours("#cbd5e1", "#94a3b8"); // the greyed (not used) setting block
  assert.notEqual(grey.primary, "#cbd5e1");
  assert.ok(contrast(grey.primary, "#ffffff") >= 4.5);
  assert.deepEqual(pickerColours("#0e7490", "#0b5d73"), { primary: "#0e7490", tertiary: "#0b5d73" }); // already readable: kept
});

test("round 22: a role lists only what it can call -- no inputs needed, no event, no monster's recipe; eat takes its key", () => {
  const d = xmas();
  const heal = refChoices(ref("role", { role: "heal" }), d).map((c) => c.value);
  assert.ok(heal.includes("heal") && heal.includes("fly_wing") && heal.includes("knife_on"));
  for (const no of ["attack_mystcase", "attack_cookie", "drink", "eat"]) assert.ok(!heal.includes(no), no);
  assert.ok(refChoices(ref("role", { role: "eat" }), d).some((c) => c.value === "eat")); // eat(key): the box's events call eat("F6")
  assert.equal(refKnown(ref("role", { role: "heal" }), "attack_mystcase", d), false); // loaded: kept, marked
  assert.ok(!refChoices(ref("escalate"), d).some((c) => c.value === "attack_mystcase"));
});

test("round 22: the outlined windows are the UI anchors' home places (no picture is shown or kept)", () => {
  const ui = new URL("../../../../../packages/poring_env/src/poring_env/ui_anchors.py", import.meta.url);
  if (!existsSync(ui)) return;
  const py = readFileSync(ui, "utf8");
  for (const [name, x, y] of [["basic_info", 0, 0], ["hotbar", 230, 0], ["minimap", 1136, 18], ["chat", 0, 531]] as const) {
    assert.match(py, new RegExp(`"${name}": \\(${x}, ${y}\\)`), name);
  }
  assert.match(py, /"basic_info": WindowSpec\("basic_info", size=\(220, 140\)/);
  assert.match(py, /"minimap", size=\(128, 142\)/);
});

// --- round 23 (live-blocks.md 12.7) -----------------------------------------------------------------
test("round 23: presets and the lever's ticks are ROUND (END_HOT_S 2 / 10 / 15 / 25 / 30 s, not 1.5 / 10 / 15.25 / 21.5 / 30)", () => {
  assert.deepEqual(presetsOf({ lo: 0.5, hi: 30, step: 0.01 }), [2, 10, 15, 25, 30]); // END_HOT_S
  assert.deepEqual(presetsOf({ lo: 5, hi: 95, step: 1 }), [10, 25, 50, 75, 90]); // END_FLY_BELOW: not 5 / 28 / 50 / 73 / 95
  assert.deepEqual(presetsOf({ lo: 10, hi: 99, step: 1 }), [20, 40, 50, 75, 90]); // REGEN_STOP: not 10 / 32 / 55 / 77 / 99
  // every number setting: at most two significant digits, in the range, on the grid, apart
  for (const f of SETTINGS.fields) {
    if (f.kind !== "number" && f.kind !== "int" && f.kind !== "share") continue;
    const pct = (v: number) => Math.round(v * 100 * 1e6) / 1e6;
    const r = f.kind === "share" ? { lo: pct(f.lo), hi: pct(f.hi), step: pct(f.step) } : { lo: f.lo, hi: f.hi, step: f.kind === "int" ? Math.max(1, f.step) : f.step };
    const ps = presetsOf(r);
    assert.ok(ps.length >= 3, `${f.name}: ${ps}`);
    for (const v of ps) {
      assert.ok(v === 0 || Number(v.toPrecision(2)) === v, `${f.name}: ${v} is not round (${ps})`);
      assert.ok(v >= r.lo && v <= r.hi && snap(v, r) === v, `${f.name}: ${v}`);
    }
    for (let i = 1; i < ps.length; i++) assert.ok(ps[i] - ps[i - 1] >= (r.hi - r.lo) * 0.1 - 1e-9, `${f.name}: ${ps} (two labels collide)`);
  }
});

test("round 23: a broken condition says what to do in a learner's words -- never a column, a token or 'unexpected'", () => {
  assert.equal(exprProblem("hp_percent() < and sees_boss()"), "after < a value is missing"); // was "and cannot stand here (character 17)"
  assert.equal(exprProblem("hp_percent() <  and"), "after < a value is missing");
  assert.equal(exprProblem("hp_percent( < 50"), "after ( a value is missing before <");
  assert.equal(exprProblem("x = 3"), "= cannot stand here: to compare two values, use ==");
  assert.equal(exprProblem("[1, 2"), "a [ is not closed: add ] after its items");
  assert.equal(exprProblem("hp_percent() <= 50)"), ") cannot stand here: no ( is open before it");
  assert.equal(exprProblem("hp_percent() < 'abc"), 'a text goes in double quotes: "like this"');
  const broken = ["hp_percent() < ", "hp_percent() <", "(hp_percent() < 50", 'hotbar_count(key="F6"', 'hotbar_count(key="F6) > 0', "1 < 2 < 3", 'hotbar_count(key="F6", "F7")', "f(a=1, a=2)", "1e999 > 0", "hp_percent() << 5", "hp_percent() < 50 50", ")", "hp_percent() > >", "not", "5 +", "x = 3", "[1, 2", "@", "a.b", "f(,)", "hp_percent() < 'abc", "and", "hp_percent() < 50 or or 1"];
  for (const t of broken) {
    const m = exprProblem(t);
    assert.ok(m !== "", t);
    assert.doesNotMatch(m, /\bcol\b|character [0-9]|unexpected|expected "|\btoken\b|"end"|EOF/, `${t}: ${m}`);
  }
});

test("round 23: the point picture reads the same place full (256 x 144) and COMPACT (176 x 99): 55 % is y 396, never 719", () => {
  const area = { x: 0.5, y: 0.5, width: 255, height: 143 }; // the drawn picture's rect in the svg's units
  const game = ([x, y]: [number, number]) => pointIn((x * 1280) / 256, (y * 720) / 144);
  for (const drawn of [{ left: 100, top: 300, width: 255, height: 143 }, { left: 702, top: 505, width: 175.3, height: 98.3 }]) {
    const at = (fx: number, fy: number) => game(toArea(drawn.left + fx * drawn.width, drawn.top + fy * drawn.height, drawn, area));
    assert.deepEqual(at(0.5, 0.5), [640, 360]);
    assert.deepEqual(at(0.55, 0.55), [704, 396]);
    assert.deepEqual(at(0.9, 0.9), [1150, 646]);
    assert.deepEqual(at(1.2, 1.2), [1279, 719]); // past the picture: its edge
  }
  // the lever's bar, drawn 200 px wide in the compact picker (its 260-unit svg): the middle is the middle
  const bar = { x: 10, y: 10, width: 240, height: 24 };
  const [x] = toArea(300 + 0.5 * (200 * (240 / 260)), 0, { left: 300, top: 0, width: 200 * (240 / 260), height: 18 }, bar);
  assert.ok(Math.abs(x - 130) < 1e-9, String(x));
});

test("round 23: a Blockly menu past the blocks area moves back inside (at most 12 px), the rest scrolls", () => {
  const area = { top: 100, bottom: 700 };
  assert.deepEqual(fitDropDown({ top: 400, bottom: 690 }, area), { shift: 0, shrink: 0 }); // inside, 4 px margin
  assert.deepEqual(fitDropDown({ top: 400, bottom: 700 }, area), { shift: -4, shrink: 0 }); // 4 px past the margin
  assert.deepEqual(fitDropDown({ top: 400, bottom: 711 }, area), { shift: -12, shrink: 3 }); // 15 px past the area
  assert.deepEqual(fitDropDown({ top: 98, bottom: 300 }, area), { shift: 6, shrink: 0 }); // above the area's top
});
