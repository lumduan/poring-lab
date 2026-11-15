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

import { inTick, lockedStep, register, syncDefAbout, takeOutAlone, tickDragOf } from "../../components/flows/blockly-register.ts";
import { warningText } from "./api.ts";
import { ABOUT_FIELDS, argsRowShown, categoryOf, DEF_ABOUT_WORDS, defAbout, DEF_BY_TYPE, toolbox, toolboxBlocks } from "./blockdefs.ts";
import { tabToWorkspace } from "./blocks.ts";
import { rowsOf } from "./layout.ts";
import { playsHunt, refChoices, type PickerData, type PickSpec } from "./pickers.ts";
import { HUNT_TAB, nodeById, tabOf, xmasFunctionsProject } from "./project.ts";
import { SETTING_ROW_BUDGET } from "./settings.ts";
import { BLOCK_STYLES, contrast } from "./theme.ts";
import { HUNT_CALL, isLockedClass, PADLOCK, STEP_BLOCKS, STEP_STYLE, stepBlock, stepType, TICK_FN, TICK_STEPS, TICK_TAB } from "./tick.ts";

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

test("round 26: a SAFETY or REQUIRED step in hunt_tick() cannot be deleted; an optional one can; out of the tick, any can", () => {
  const { ws, def, step } = tickTab();
  assert.equal(def.getFieldValue("NAME"), TICK_FN);
  for (const t of TICK_STEPS) {
    const b = step(t.name);
    assert.ok(inTick(b), t.name);
    assert.equal(lockedStep(b), isLockedClass(t.klass), t.name);
    assert.equal(b.isDeletable(), !isLockedClass(t.klass), `${t.name}: deletable`);
    assert.equal(b.isMovable(), true, `${t.name}: Blockly-movable (the lock is the drag's, never setMovable)`);
  }
  // a locked class outside the tick (a block from the toolbox, not placed yet) is deletable
  const loose = B.serialization.blocks.append({ type: stepType(TICK_STEPS.find((t) => t.name === "survive")!) }, ws);
  assert.ok(!inTick(loose) && !lockedStep(loose) && loose.isDeletable());
  assert.ok(!inTick(def)); // the function itself: not "in" the tick
  ws.dispose();
});

test("round 26: deleting an optional step HEALS the tick and keeps the locked one under it (why the lock is never setMovable)", () => {
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

test("round 26: a step is dragged out ALONE -- the steps under it close up, whatever they are; a locked step's drag moves nothing", () => {
  const { ws, step, steps } = tickTab();
  const loot = step("loot");
  takeOutAlone(loot); // what the tick's drag does before Blockly drags it
  assert.equal(loot.getParent(), null);
  assert.equal(loot.getNextBlock(), null, "loot alone (it took no step with it)");
  assert.deepEqual(steps(), TICK_STEPS.map(stepType).filter((t) => t !== "pl_step_loot"));
  // the tick's drag strategy (Blockly's BlockDragStrategy): a locked step's drag is a no-op
  const Drag = tickDragOf(B);
  assert.ok(Drag);
  const survive = step("survive");
  const before = steps();
  const d = new Drag(survive as unknown as BlocklyT.BlockSvg);
  assert.equal(d.startDrag(), survive); // no disconnect, nothing dragged out
  d.endDrag(undefined, 0 as unknown as Parameters<BlocklyT.IDragStrategy["endDrag"]>[1]);
  d.revertDrag();
  assert.deepEqual(steps(), before);
  assert.ok(inTick(survive));
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

test("round 26: each class its padlock and colour -- SAFETY red, REQUIRED blue (locked, 🔒), optional green; white words readable", () => {
  for (const t of TICK_STEPS) {
    const d = DEF_BY_TYPE[stepType(t)];
    assert.equal(d.style, STEP_STYLE[t.klass]);
    const head = rowsOf({ type: stepType(t), id: "x" }, {}, 20)[0].what;
    assert.equal(head.includes(PADLOCK), isLockedClass(t.klass), `${t.name}: ${head}`);
    assert.ok(head.endsWith(`${stepBlock(t)}()`));
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
