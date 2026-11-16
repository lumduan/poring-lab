// Round 26 (live-blocks.md 12.10, the reviewer's 5c review): the tick's SAFETY and REQUIRED steps
// are LOCKED in the editor (cannot be deleted or dragged out of hunt_tick(), a padlock and a colour
// per class), a step is dragged out ALONE, the role pickers never offer the hunt core's own
// functions, the hunt core's two functions say what they are, a hunt block with no inputs hides
// its row, an INFO never shows a warning triangle, the old runner block is in Advanced. In the
// REAL Blockly 13 (headless, as blockly_headless.test.ts), where it needs Blockly.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import type * as BlocklyT from "blockly/core";

import { inTick, register, syncDefAbout, syncStepPlace, takeOutAlone, tickDragOf } from "../../components/flows/blockly-register.ts";
import { warningText } from "./api.ts";
import { ABOUT_FIELDS, argsRowShown, categoryOf, DEF_ABOUT_WORDS, defAbout, defTooltip, DEF_BY_TYPE, TICK_CATEGORY, toolbox, toolboxBlocks, toolboxCatalogue, varTooltip, WHY_FIELDS } from "./blockdefs.ts";
import { tabFromWorkspace, tabToWorkspace, type Workspace } from "./blocks.ts";
import { rowsOf } from "./layout.ts";
import { playsHunt, refChoices, type PickerData, type PickSpec } from "./pickers.ts";
import { HUNT_TAB, nodeById, tabOf, xmasFunctionsProject } from "./project.ts";
import { SETTING_ROW_BUDGET } from "./settings.ts";
import { BLOCK_STYLES, contrast } from "./theme.ts";
import { HUNT_CALL, isNeededClass, NEED_WORDS, placeWords, STEP_BLOCKS, STEP_STYLE, stepBlock, stepType, TICK_FN, TICK_STEPS, TICK_TAB, tickPlaces } from "./tick.ts";

const require = createRequire(import.meta.url);
const lib = (p: string) => fileURLToPath(new URL(`../../../node_modules/blockly/${p}`, import.meta.url));
const B = require(lib("blockly_compressed.js")) as typeof BlocklyT;
B.setLocale(require(lib("msg/en.js")) as Record<string, string>);
register(B);

const NODE = "xmas_dun02";
/** The functions box's tick tab, loaded in a headless workspace; its steps in hunt_tick()'s order. */
function tickTab(): { ws: BlocklyT.Workspace; def: BlocklyT.Block; steps: () => string[]; step: (name: string) => BlocklyT.Block } {
  const ws = new B.Workspace();
  B.Events.disable();
  try {
    B.serialization.workspaces.load(tabToWorkspace(xmasFunctionsProject(), { node: NODE, tab: TICK_TAB }) as unknown as object, ws);
  } finally {
    B.Events.enable();
  }
  const def = ws.getTopBlocks(false).find((b) => b.type === "pl_def" && b.getFieldValue("NAME") === TICK_FN)!;
  const steps = () => {
    const out: string[] = [];
    for (let b = def.getInputTargetBlock("DO"); b; b = b.getNextBlock()) out.push(b.type);
    return out;
  };
  const step = (name: string) => ws.getAllBlocks(false).find((b) => b.type === `pl_step_${name}`)!;
  return { ws, def, steps, step };
}

test("round 29: every step -- SAFETY and REQUIRED too -- can be deleted and dragged, in the tick and out of it (Batt: it must be editable)", () => {
  const { ws, def, step } = tickTab();
  assert.equal(def.getFieldValue("NAME"), TICK_FN);
  for (const t of TICK_STEPS) {
    const b = step(t.name);
    assert.ok(inTick(b), t.name);
    assert.ok(b.isDeletable(), `${t.name}: deletable`);
    assert.equal(b.isMovable(), true, `${t.name}: movable (no step is ever setMovable(false))`);
  }
  const loose = B.serialization.blocks.append({ type: stepType(TICK_STEPS.find((t) => t.name === "survive")!) }, ws);
  assert.ok(!inTick(loose) && loose.isDeletable());
  assert.ok(!inTick(def)); // the function itself: not "in" the tick
  ws.dispose();
});

test("round 29: a SAFETY step deleted leaves a tick the converter keeps -- the lint and the Run refuse it in its words (test_routes_flowrun.py), Undo puts it back", async () => {
  const { ws, step, steps } = tickTab();
  await new Promise((r) => setTimeout(r, 0));
  ws.clearUndo();
  B.Events.setGroup(true); // as the context menu's Delete does: one undo step
  step("survive").dispose(true); // Delete: the tick heals, survive gone
  B.Events.setGroup(false);
  assert.deepEqual(steps(), TICK_STEPS.map(stepType).filter((t) => t !== "pl_step_survive"));
  const p = xmasFunctionsProject();
  const r = tabFromWorkspace(p, { node: NODE, tab: TICK_TAB }, B.serialization.workspaces.save(ws) as unknown as Workspace);
  assert.ok(r.ok, r.ok ? "" : r.errors.join(" | ")); // the design is kept: the engine says why it cannot run
  const body = tabOf(nodeById(r.project, NODE)!, TICK_TAB)!.defs[0].body;
  assert.ok(!body.some((s) => s.kind === "action" && s.block === "step_survive"));
  await new Promise((r) => setTimeout(r, 5));
  ws.undo(false); // Ctrl+Z
  await new Promise((r) => setTimeout(r, 5));
  assert.deepEqual(steps(), TICK_STEPS.map(stepType));
  ws.dispose();
});

test("round 26: deleting a step HEALS the tick and keeps the step under it (why no step is ever setMovable(false))", () => {
  const { ws, step, steps } = tickTab();
  const want = TICK_STEPS.map(stepType).filter((t) => t !== "pl_step_loot");
  step("loot").dispose(true); // Delete (Blockly heals the stack)
  assert.deepEqual(steps(), want, "loot gone, after (REQUIRED, under it) still in the tick");
  ws.dispose();
  // the positive case: had the lock been Blockly's setMovable(false), its heal would have taken the
  // unmovable step under loot WITH it (core/block.ts unplugFromStack) -- after deleted too
  const t2 = tickTab();
  t2.step("after").setMovable(false);
  t2.step("loot").dispose(true);
  assert.ok(!t2.steps().includes("pl_step_after"), "setMovable(false) would have deleted after with loot");
  t2.ws.dispose();
});

test("round 26: a step is dragged out ALONE -- the steps under it close up, whatever they are (round 29: a SAFETY step too)", () => {
  const { ws, step, steps } = tickTab();
  const loot = step("loot");
  takeOutAlone(loot); // what the tick's drag does before Blockly drags it
  assert.equal(loot.getParent(), null);
  assert.equal(loot.getNextBlock(), null, "loot alone (it took no step with it)");
  assert.deepEqual(steps(), TICK_STEPS.map(stepType).filter((t) => t !== "pl_step_loot"));
  // round 29: a SAFETY step comes out alone too (no lock)
  const survive = step("survive");
  takeOutAlone(survive);
  assert.equal(survive.getParent(), null);
  assert.deepEqual(steps(), TICK_STEPS.map(stepType).filter((t) => t !== "pl_step_loot" && t !== "pl_step_survive"));
  assert.ok(tickDragOf(B), "the tick's one-step drag (Blockly's BlockDragStrategy)");
  // Blockly's own pointer drag would take the stack (heal only with Ctrl / Meta): why ours heals
  const g = globalThis as { PointerEvent?: unknown };
  const had = g.PointerEvent;
  g.PointerEvent = class extends Event {};
  try {
    const base = new B.dragging.BlockDragStrategy(step("ready") as unknown as BlocklyT.BlockSvg) as unknown as { shouldHealStack(e: unknown): boolean };
    assert.ok(!base.shouldHealStack(new (g.PointerEvent as typeof Event)("pointerdown")), "Blockly drags the stack below");
  } finally {
    if (had) g.PointerEvent = had;
    else delete g.PointerEvent;
  }
  ws.dispose();
});

test("round 29: each class its mark and colour -- SAFETY red, REQUIRED blue ('needed to run', no padlock), optional green; white words readable", () => {
  for (const t of TICK_STEPS) {
    const d = DEF_BY_TYPE[stepType(t)];
    assert.equal(d.style, STEP_STYLE[t.klass]);
    const head = rowsOf({ type: stepType(t), id: "x" }, {}, 20)[0].what;
    // (the mark is the class line's words, true wherever a copy stands; no padlock label any more)
    const line1 = rowsOf({ type: stepType(t), id: "x" }, {}, 20)[1].what;
    if (isNeededClass(t.klass)) assert.equal(line1, `${stepType(t)}: ${t.klass.toUpperCase()} · ${NEED_WORDS}`);
    else assert.ok(line1.startsWith(`${stepType(t)}: optional ·`), line1);
    assert.ok(!(d.args0 ?? []).some((a) => "name" in a && (a.name === "LOCK" || a.name === "NEED")), "no padlock any more");
    assert.ok(!String(d.message0).includes("🔒"));
    assert.ok(head.endsWith(`${stepBlock(t)}()`), head);
    assert.match(String(d.tooltip), isNeededClass(t.klass) ? /NEEDED TO RUN: a Run of a tick without it is refused/ : /OPTIONAL/);
    for (const r of rowsOf({ type: stepType(t), id: "x" }, {}, 20)) assert.ok(r.w <= SETTING_ROW_BUDGET, `${t.name}: ${r.what}`);
  }
  const colours = Object.values(STEP_STYLE).map((s) => BLOCK_STYLES[s].colourPrimary);
  assert.equal(new Set(colours).size, 3);
  for (const c of colours) assert.ok(contrast(c, "#ffffff") >= 4.5, c);
});

test("round 26: hunt_tick() says who plays it, hunt_loop() that t is not an input to pass; any other function shows no such row", () => {
  const ws = new B.Workspace();
  for (const [name, words] of Object.entries(DEF_ABOUT_WORDS)) {
    const b = B.serialization.blocks.append({ type: "pl_def", fields: { NAME: name, PARAMS: name === HUNT_CALL ? "t=False" : "" } }, ws);
    syncDefAbout(B, b);
    const shown = ABOUT_FIELDS.map((f) => b.getFieldValue(f)).filter(Boolean).join(" ");
    assert.equal(shown, words);
    assert.ok(b.getInput("ROW_ABOUT")!.isVisible());
    const rows = rowsOf({ type: "pl_def", id: "x", fields: { NAME: name, PARAMS: "t=False" } }, defAbout(name));
    for (const r of rows) assert.ok(r.w <= SETTING_ROW_BUDGET, `${name}: ${Math.round(r.w)}: ${r.what}`);
    b.getField("NAME")!.setValue("my_function"); // renamed: the rows go
    syncDefAbout(B, b);
    for (const row of ["ROW_ABOUT", "ROW_ABOUT2", "ROW_ABOUT3"]) assert.ok(!b.getInput(row)!.isVisible(), row);
  }
  assert.match(DEF_ABOUT_WORDS[TICK_FN], /find_target and fight_target, every tick/);
  assert.match(DEF_ABOUT_WORDS[HUNT_CALL], /^t: the target/);
  ws.dispose();
});

test("round 26: the role pickers never offer the hunt core's own functions -- hunt_loop, hunt_tick, a function playing its blocks, an event; main's call lists them all", () => {
  const p = xmasFunctionsProject();
  const hunt = tabOf(nodeById(p, NODE)!, HUNT_TAB)!;
  hunt.defs.push({ name: "my_finder", params: [], varargs: null, kwargs: null, body: [{ kind: "action", block: "find_target", concept: "combat.hunt", params: {}, timeout_s: 120, on_fail: "stop", outcome_to: "t", note: null }], on: null });
  const data: PickerData = { project: p, node: NODE, tab: HUNT_TAB, catalogue: null, maps: null };
  const role = (r: string) => refChoices({ kind: "ref", ref: "role", role: r, title: "x" } as Extract<PickSpec, { kind: "ref" }>, data).map((c) => c.value);
  for (const r of ["heal", "fly", "knife_on", "knife_back", "home", "respawn", "respawn_confirm", "eat"]) {
    const offered = role(r);
    for (const no of [HUNT_CALL, TICK_FN, "my_finder", "drink", "fly_away"]) assert.ok(!offered.includes(no), `${r} offers ${no}`);
    assert.ok(offered.length > 3, r);
  }
  assert.ok(role("heal").includes("heal") && role("fly").includes("fly_wing"));
  const call = refChoices({ kind: "ref", ref: "function", title: "x" } as Extract<PickSpec, { kind: "ref" }>, data).map((c) => c.value);
  for (const yes of [HUNT_CALL, TICK_FN, "my_finder"]) assert.ok(call.includes(yes), yes); // main's plain call: everything
  assert.ok(playsHunt([{ kind: "while", cond: { kind: "lit", value: true }, body: [{ kind: "call", proc: HUNT_CALL, args: [], kwargs: {} }], max_iter: null, max_s: null }]));
  assert.ok(!playsHunt([{ kind: "call", proc: "heal", args: [], kwargs: {} }]));
});

test("round 26: a hunt block with no inputs hides its inputs' row; an INFO never shows a warning; each line once", () => {
  assert.equal(argsRowShown([], ""), false); // find_target: no inputs, none held
  assert.equal(argsRowShown([], " x=1 "), true); // a typed one stays, to be read and taken out
  assert.equal(argsRowShown([{ name: "target" }], ""), true); // fight_target takes one
  assert.equal(argsRowShown(undefined, ""), true); // the catalogue not here yet
  const info = { severity: "info" as const, text: "find_target is played by the runner's own code: nothing to set up for it here" };
  assert.equal(warningText([], [info, info]), null);
  const warn = { severity: "warning" as const, text: "something" };
  assert.equal(warningText([{ text: "bad" }, { text: "bad" }], [warn, warn, info]), "error: bad\nwarning: something");
});

test("round 26: the old one-block runner is in Advanced (Old projects), so main's toolbox shows hunt_loop() first; the Hunt header never names it", () => {
  const CAT = {
    dungeon_hunt: { concept: "combat.hunt", timeout_s: 600 },
    find_target: { concept: "combat.hunt", timeout_s: 120 },
    fight_target: { concept: "combat.attack_target", timeout_s: 300 },
    ...Object.fromEntries(STEP_BLOCKS.map((b) => [b, { concept: "core.tick_step", timeout_s: 1, kind: "core" }])),
  };
  const tb = toolbox(CAT, { node: "map", main: true, tab: "main" });
  const items = toolboxBlocks(tb);
  const old = items.find((x) => x.item.type === "pl_dungeon_hunt")!;
  assert.equal(old.category, "Old projects");
  assert.ok(categoryOf(tb, "Advanced"));
  const movement = items.filter((x) => x.category === "Movement").map((x) => x.item);
  assert.ok(movement.some((i) => i.type === "pl_call" && (i.fields as Record<string, unknown>).PROC === HUNT_CALL));
  assert.ok(!movement.some((i) => i.type === "pl_dungeon_hunt"));
  const labels = (c: ReturnType<typeof toolbox>) => JSON.stringify(c).match(/"text":"[^"]*"/g) ?? [];
  assert.ok(labels(tb).some((l) => l.includes("the old one-block runner (old projects")));
  const hunt = toolbox(CAT, { node: "map", main: false, tab: HUNT_TAB });
  assert.ok(!labels(hunt).some((l) => /dungeon_hunt/.test(l)), labels(hunt).join(" "));
});

// --- round 27 (live-blocks.md 12.11, the reviewer's round-26 re-measure) ---------------------------
/** A catalogue as GET /flows/catalogue serves it, its kinds the engine's (the step blocks are CORE:
 * core.tick_step; the hunt loop's are actions). */
const ENGINE_CAT = {
  blocks: Object.fromEntries([
    ...STEP_BLOCKS.map((n) => [n, { name: n, spec: { kind: "core", concept: "core.tick_step", timeout_s: 1 }, badge: "core" }]),
    ...["find_target", "fight_target", "dungeon_hunt"].map((n) => [n, { name: n, spec: { kind: "action", concept: "combat.hunt", timeout_s: n === "fight_target" ? 300 : 120 }, badge: "unverified" }]),
    ["use_model", { name: "use_model", spec: { kind: "core", concept: "core.use_model", timeout_s: 1 }, badge: "core" }],
    ["some_core", { name: "some_core", spec: { kind: "core", concept: "core.x", timeout_s: 1 }, badge: "core" }],
  ]),
};

test("round 27: the tab tick offers its 20 step blocks in a 'Tick steps' category -- through the page's own catalogue filter (it dropped every core block)", () => {
  const cat = toolboxCatalogue(ENGINE_CAT); // what BlockEditor's toolboxOf hands toolbox()
  for (const b of STEP_BLOCKS) assert.ok(cat[b], `${b} offered`);
  assert.ok(!cat.some_core && cat.use_model); // other core blocks as before
  const tb = toolbox(cat, { node: "map", main: false, tab: TICK_TAB });
  const tick = toolboxBlocks(tb).filter((x) => x.category === TICK_CATEGORY).map((x) => x.item);
  assert.deepEqual([tick[0].type, (tick[0].fields as Record<string, unknown>).NAME], ["pl_def", TICK_FN]);
  assert.deepEqual(tick.slice(1).map((i) => i.type), TICK_STEPS.map(stepType));
  // the positive case: round 26's filter (core blocks but the four) left the tab no category at all
  const old = Object.fromEntries(Object.entries(cat).filter(([n]) => ["assert_save_point", "use_model", "wait_steal", "wait_kill"].includes(n) || ENGINE_CAT.blocks[n as keyof typeof ENGINE_CAT.blocks]?.spec.kind !== "core"));
  assert.equal(categoryOf(toolbox(old, { node: "map", main: false, tab: TICK_TAB }), TICK_CATEGORY), undefined);
  // only the tab tick of a map node has it
  assert.equal(categoryOf(toolbox(cat, { node: "map", main: false, tab: "keys" }), TICK_CATEGORY), undefined);
  assert.equal(categoryOf(toolbox(cat, { node: "global", main: false, tab: TICK_TAB }), TICK_CATEGORY), undefined);
});

test("round 27: the flyout's step blocks are the real ones -- each found by its name and its words", () => {
  const tb = toolbox(toolboxCatalogue(ENGINE_CAT), { node: "map", main: false, tab: TICK_TAB });
  const ws = new B.Workspace();
  const words = new Map<string, string>();
  for (const { item } of toolboxBlocks(tb).filter((x) => x.category === TICK_CATEGORY && x.item.type !== "pl_def")) {
    const { kind: _k, ...state } = item;
    void _k;
    const b = B.serialization.blocks.append(state as unknown as BlocklyT.serialization.blocks.State, ws); // as the flyout and the search make them
    words.set(b.type, b.toString());
    assert.ok(b.isDeletable(), `${b.type}: deletable`);
  }
  assert.equal(words.size, 20);
  const find = (q: string) => [...words].filter(([, w]) => w.toLowerCase().includes(q)).map(([t]) => t);
  assert.deepEqual(find("survive"), ["pl_step_survive"]); // the search's words (blockly-search.ts: toString)
  assert.ok(find("loot").includes("pl_step_loot"));
  assert.ok(find("potion").includes("pl_step_survive")); // by what it does
  ws.dispose();
});

test("round 27: hunt_tick's and hunt_loop's ABOUT rows show on the page's path -- a workspace LOADED with events off, and a toolbox item", () => {
  for (const [tab, name] of [[TICK_TAB, TICK_FN], [HUNT_TAB, HUNT_CALL]] as const) {
    const ws = new B.Workspace();
    B.Events.disable();
    try {
      B.serialization.workspaces.load(tabToWorkspace(xmasFunctionsProject(), { node: NODE, tab }) as unknown as object, ws); // as BlockEditor loads a tab
    } finally {
      B.Events.enable();
    }
    const def = ws.getTopBlocks(false).find((b) => b.type === "pl_def" && b.getFieldValue("NAME") === name)!;
    const shown = ABOUT_FIELDS.map((f) => def.getFieldValue(f)).filter(Boolean).join(" ");
    assert.equal(shown, DEF_ABOUT_WORDS[name], `${name} on load`);
    assert.ok(def.getInput("ROW_ABOUT")!.isVisible());
    assert.match(String(def.getTooltip()), new RegExp(DEF_ABOUT_WORDS[name].slice(0, 20).replace(/[()]/g, "\\$&")));
    // a function renamed by typing loses the rows (the validator follows the value)
    def.getField("NAME")!.setValue("my_function");
    assert.ok(!def.getInput("ROW_ABOUT")!.isVisible());
    ws.dispose();
  }
  // the flyout's hunt_tick def (the toolbox item, fields from JSON)
  const ws = new B.Workspace();
  const item = toolboxBlocks(toolbox(toolboxCatalogue(ENGINE_CAT), { node: "map", main: false, tab: TICK_TAB })).find((x) => x.item.type === "pl_def")!.item;
  const { kind: _k, ...state } = item;
  void _k;
  const def = B.serialization.blocks.append(state as unknown as BlocklyT.serialization.blocks.State, ws);
  assert.equal(ABOUT_FIELDS.map((f) => def.getFieldValue(f)).filter(Boolean).join(" "), DEF_ABOUT_WORDS[TICK_FN]);
  ws.dispose();
});

test("round 27: a function's and a variable's tooltip names Global only where the project has one", () => {
  assert.doesNotMatch(defTooltip("heal", false), /Global/);
  assert.match(defTooltip("heal", true), /replaces Global's there/);
  assert.doesNotMatch(varTooltip(false), /Global/);
  assert.match(varTooltip(true), /Global/);
  assert.doesNotMatch(String(DEF_BY_TYPE.pl_def.tooltip), /Global/); // the static one (the flyout)
  for (const n of [TICK_FN, HUNT_CALL]) assert.ok(defTooltip(n, false).includes(DEF_ABOUT_WORDS[n]) && !/Global/.test(defTooltip(n, false)), n);
});

// --- round 28 (live-blocks.md 12.12, the reviewer's round-27 re-measure) ---------------------------
/** The cases the engine's rule is pinned by too (test_runner_functions.py PLACE_CASES): a tick's
 * step blocks -> the places that are not "ok" ([index, kind, where]). */
const A = [...STEP_BLOCKS];
const without = (b: string) => A.filter((x) => x !== b);
const PLACE_CASES: [string, (string | null)[], [number, string, string][]][] = [
  ["in order", A, []],
  ["a second survive after pace", [...A, "step_survive"], [[20, "extra", ""]]],
  ["a second survive at the top", ["step_survive", ...A], [[0, "extra", ""]]],
  ["a second survive beside it", [...A.slice(0, 6), "step_survive", ...A.slice(6)], [[6, "extra", ""]]],
  ["loot put back at the end", [...without("step_loot"), "step_loot"], [[19, "misplaced", "it goes after step_hold() and before step_after()"]]],
  ["sense before begin", [A[1], A[0], ...A.slice(2)], [[0, "misplaced", "it goes after step_begin() and before step_hook()"]]],
  ["survive only at the end", [...without("step_survive"), "step_survive"], [[19, "misplaced", "it goes after step_battle_log() and before step_engage()"]]],
  ["two loots, none in place", [...without("step_loot"), "step_loot", "step_loot"], [[19, "misplaced", "it goes after step_hold() and before step_after()"], [20, "extra", ""]]],
  ["a call in the tick", [...A.slice(0, 3), null, ...A.slice(3)], [[3, "other", ""]]],
];

test("round 28: which copy the tick accepts -- the lint's rule (the same cases pin the engine's)", () => {
  for (const [why, blocks, want] of PLACE_CASES) {
    const got = tickPlaces(blocks).flatMap((p, i): [number, string, string][] => (p.kind === "ok" ? [] : [[i, p.kind, p.where]]));
    assert.deepEqual(got, want, why);
  }
  assert.equal(placeWords({ kind: "extra", where: "" }), "an extra copy: delete it (each step plays once a tick)");
  assert.equal(placeWords({ kind: "misplaced", where: "it goes after step_hold() and before step_after()" }), "out of its place: it goes after step_hold() and before step_after()");
  assert.equal(placeWords({ kind: "ok", where: "" }), "");
});

test("round 28: a SECOND step_survive dropped after step_pace says why; deleting the copy leaves a tick the lint takes (round 29: every copy deletable)", () => {
  const { ws, step, steps } = tickTab(); // the page's path: a tab LOADED with events off
  const original = step("survive");
  // a person drops step_survive from the toolbox after step_pace (Blockly makes it from the item)
  const item = toolboxBlocks(toolbox(toolboxCatalogue(ENGINE_CAT), { node: "map", main: false, tab: TICK_TAB })).find((x) => x.item.type === stepType(TICK_STEPS.find((t) => t.name === "survive")!))!.item;
  const { kind: _k, ...state } = item;
  void _k;
  const copy = B.serialization.blocks.append(state as unknown as BlocklyT.serialization.blocks.State, ws);
  step("pace").nextConnection!.connect(copy.previousConnection!);
  assert.equal(steps().length, 21);
  assert.ok(inTick(copy) && copy.isDeletable() && original.isDeletable());
  syncStepPlace(B, copy);
  syncStepPlace(B, original);
  assert.equal(WHY_FIELDS.map((f) => copy.getFieldValue(f)).filter(Boolean).join(" "), "an extra copy: delete it (each step plays once a tick)");
  assert.ok(copy.getInput("ROW_WHY")!.isVisible());
  assert.ok(!original.getInput("ROW_WHY")!.isVisible());
  copy.dispose(true);
  assert.deepEqual(steps(), TICK_STEPS.map(stepType));
  const names = steps().map((t) => stepBlock(TICK_STEPS.find((s) => stepType(s) === t)!));
  assert.ok(tickPlaces(names).every((p) => p.kind === "ok"));
  ws.dispose();
});

test("round 28: a misplaced copy of a SAFETY step says where it goes; moved back, its rows clear", () => {
  const { ws, step } = tickTab();
  const survive = step("survive");
  takeOutAlone(survive);
  step("pace").nextConnection!.connect(survive.previousConnection!); // survive, the only copy, last
  syncStepPlace(B, survive);
  assert.equal(WHY_FIELDS.map((f) => survive.getFieldValue(f)).filter(Boolean).join(" "), "out of its place: it goes after step_battle_log() and before step_engage()");
  takeOutAlone(survive);
  step("battle_log").nextConnection!.connect(survive.previousConnection!); // back in its place
  syncStepPlace(B, survive);
  assert.ok(!survive.getInput("ROW_WHY")!.isVisible());
  ws.dispose();
});

test("round 29: a box whose main holds the old one-block runner loads but is no real Run -- the Run button's words are the engine's", async () => {
  const { OLD_RUNNER_WORDS, oldRunnerOn, sampleProject, xmasCookieNoSwapProject, xmasFunctionsCookieNoSwapProject, xmasHuntProject, xmasProject } = await import("./project.ts");
  const mapOf = (p: ReturnType<typeof xmasProject>) => p.nodes.find((n) => n.kind === "map");
  for (const p of [xmasProject(), xmasHuntProject(), xmasCookieNoSwapProject()]) assert.ok(oldRunnerOn(mapOf(p)), p.name);
  assert.ok(!oldRunnerOn(mapOf(xmasFunctionsProject())), "the functions box runs");
  assert.ok(!oldRunnerOn(mapOf(xmasFunctionsCookieNoSwapProject())), "the no-swap example (functions shape) runs");
  assert.ok(!sampleProject().nodes.some((n) => oldRunnerOn(n)));
  assert.ok(!oldRunnerOn(undefined));
  // (test_routes_flowrun.py pins these words to poring_flow.project.OLD_RUNNER_WORDS)
  assert.equal(OLD_RUNNER_WORDS, "this box uses the old one-block runner; real runs use hunt_loop() (load xmas_dun02)");
});
