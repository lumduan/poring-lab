// Round 21 (live-blocks.md 12.5): the pickers' pure part (lib/flow/pickers.ts), in the spirit of
// matpilot's fields.test.ts (https://github.com/lumduan/matpilot at 4022c87, MIT; THIRD_PARTY.md):
// a value in is the same value out, the clamp, the step, the text shown, the search ranking, and a
// value that is not in the list KEPT, marked. The Blockly fields themselves (they save, load and
// show these) are in blockly_headless.test.ts.
import assert from "node:assert/strict";
import { test } from "node:test";

import type { CatalogueDoc } from "./api.ts";
import { DEF_BY_TYPE } from "./blockdefs.ts";
import { exprText } from "./expr.ts";
import type { Models } from "./models.ts";
import {
  argRows,
  argsWith,
  callArgsWith,
  callRows,
  closedText,
  completions,
  complete,
  condFor,
  condOf,
  condText,
  defOn,
  functionsOn,
  matchScore,
  numberOf,
  numText,
  optNumOf,
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
  sliderKey,
  snap,
  stepBy,
  stopReasons,
  typedProblem,
} from "./pickers.ts";
import { MAIN_TAB, nodeById, type Project, sampleProject, xmasProject } from "./project.ts";

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
  assert.deepEqual(presetsOf(r), [20, 40, 55, 75, 90]);
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
