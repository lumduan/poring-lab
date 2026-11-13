// The /flows studio's pure parts (2026-11-09, docs/planning/flows-studio.md): MatPilot's theme and
// our mapping onto it, the per-browser preferences and their fallbacks, the problems wording, the
// model blocks' menus, the block search, and the starter program.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { BLOCK_DEFS, categoryOf, toolbox, toolboxBlocks } from "./blockdefs.ts";
import { fromWorkspace, toWorkspace, type Workspace } from "./blocks.ts";
import { canonical, type Flow } from "./ir.ts";
import { classFor, classOptions, firstDetector, modelOptions, type Models, notAdopted } from "./models.ts";
import { browserStorage, forget, KEYS, pythonDefault, readChoice, readText, savedFlowName, type StorageLike, writeChoice } from "./prefs.ts";
import { matchEntries, normalise, searchFlyout, type SearchEntry } from "./search.ts";
import { oneMapStarter, STARTER_WORLD, starterFlow } from "./starter.ts";
import { BLOCK_STYLE, BLOCK_STYLES, CATEGORY_COLOURS, CATEGORY_STYLES, COMPONENT_STYLES, contrast, INJECT } from "./theme.ts";
import { blockWords, hatTitle, lintErrors, looseText, statusText, tabOf } from "./words.ts";

// --- the theme -------------------------------------------------------------------------------------
test("MatPilot's category colours, each >= 4.5:1 against white block text", () => {
  assert.equal(CATEGORY_COLOURS.input, "#0e7490"); // Sensors: the model blocks
  assert.equal(CATEGORY_COLOURS.movement, "#a21caf");
  assert.equal(CATEGORY_COLOURS.output, "#1d4ed8");
  assert.equal(CATEGORY_COLOURS.flow, "#b45309");
  for (const [name, c] of Object.entries(CATEGORY_COLOURS)) assert.ok(contrast(c, "#ffffff") >= 4.5, `${name} ${c} ${contrast(c, "#ffffff").toFixed(2)}`);
  assert.equal(BLOCK_STYLES.mp_start_blocks.hat, "cap"); // "when the program starts" is a cap hat
  assert.deepEqual(COMPONENT_STYLES.light.workspaceBackgroundColour, "#f6f7f9");
  assert.deepEqual(COMPONENT_STYLES.dark.workspaceBackgroundColour, "#111418");
  assert.equal(INJECT.zoom.wheel, false); // the wheel scrolls, never zooms
  assert.equal(INJECT.move.wheel, true);
  assert.equal(INJECT.media, "/blockly-media/"); // self-hosted: no CDN (the CSP)
});

test("every block type has a MatPilot style, as the brief maps them", () => {
  for (const d of BLOCK_DEFS) {
    assert.ok(d.style && BLOCK_STYLES[d.style], `${d.type}: ${d.style}`);
    assert.equal(d.colour, undefined, `${d.type} keeps a colour`);
  }
  const colour = (t: string) => BLOCK_STYLES[BLOCK_STYLE[t]].colourPrimary;
  assert.equal(colour("pl_walk_to"), "#a21caf"); // Movement
  assert.equal(colour("pl_hunt"), "#a21caf");
  for (const t of ["pl_talk_npc", "pl_choose_menu", "pl_use_item", "pl_open_window"]) assert.equal(colour(t), "#1d4ed8"); // Actions
  for (const t of ["pl_wait", "pl_wait_until", "pl_repeat", "pl_while", "pl_if", "pl_stop"]) assert.equal(colour(t), "#b45309"); // Control
  assert.equal(colour("pl_set"), "#be185d");
  assert.equal(colour("pl_call"), "#4338ca");
  assert.equal(colour("pl_detect_sees"), "#0e7490");
  assert.equal(BLOCK_STYLES[BLOCK_STYLE.pl_main].hat, "cap");
});

test("the toolbox is in MatPilot's order, each category styled as MatPilot's", () => {
  const tb = toolbox({ walk_to: { concept: "nav.walk_to", timeout_s: 120 }, talk_npc: { concept: "npc.talk", timeout_s: 60 }, sit: { concept: "char.sit", timeout_s: 5 } }, "block");
  assert.deepEqual(tb.contents.map((c) => c.name), ["Search", "Movement", "Actions", "Control", "Conditions", "Sensors", "Operators", "Variables", "Functions", "Advanced"]);
  assert.equal(tb.contents[0].kind, "search");
  for (const c of tb.contents) assert.ok(CATEGORY_STYLES[c.categorystyle], c.name);
  const sensors = categoryOf(tb, "Sensors")!.contents.filter((i) => i.kind === "block").map((i) => (i as { type: string }).type);
  assert.deepEqual(sensors.slice(0, 2), ["pl_detect_sees", "pl_detect_count"]);
  assert.ok(categoryOf(tb, "More skills")!.contents.some((i) => i.kind === "block" && i.fields?.BLOCK === "sit"));
  // exits only in a map block's toolbox
  const exits = (s: "block" | "main") => toolboxBlocks(toolbox({}, s)).filter((e) => e.item.type.startsWith("pl_exit_")).length;
  assert.equal(exits("block"), 3);
  assert.equal(exits("main"), 0);
});

// --- the preferences ----------------------------------------------------------------------------
class MemoryStore implements StorageLike {
  data = new Map<string, string>();
  getItem(k: string) {
    return this.data.get(k) ?? null;
  }
  setItem(k: string, v: string) {
    this.data.set(k, v);
  }
  removeItem(k: string) {
    this.data.delete(k);
  }
}
const broken: StorageLike = {
  getItem: () => {
    throw new Error("SecurityError");
  },
  setItem: () => {
    throw new Error("QuotaExceededError");
  },
  removeItem: () => {
    throw new Error("SecurityError");
  },
};

test("preferences are remembered, and every storage failure falls back to the default", () => {
  const s = new MemoryStore();
  assert.equal(readChoice(s, KEYS.python, ["open", "closed"], "open"), "open");
  assert.ok(writeChoice(s, KEYS.python, "closed"));
  assert.equal(readChoice(s, KEYS.python, ["open", "closed"], "open"), "closed");
  s.setItem(KEYS.view, "something-else");
  assert.equal(readChoice(s, KEYS.view, ["blocks", "python"], "blocks"), "blocks"); // unknown -> default
  assert.equal(readChoice(broken, KEYS.python, ["open", "closed"], "open"), "open");
  assert.equal(writeChoice(broken, KEYS.python, "closed"), false);
  assert.equal(readText(broken, KEYS.flow), null);
  forget(broken, KEYS.flow); // never throws
  assert.equal(readChoice(null, KEYS.python, ["open", "closed"], "closed"), "closed");
  assert.equal(writeChoice(null, KEYS.python, "open"), false);
  assert.equal(browserStorage(), null); // node: no window
  assert.equal(KEYS.python, "poring-lab.flows.python-panel.v1");
  assert.equal(pythonDefault(true), "open"); // side by side on a wide screen (Batt: the key)
  assert.equal(pythonDefault(false), "closed");
});

// --- the words --------------------------------------------------------------------------------------
test("detached stacks are said in words, per tab", () => {
  const one = { id: "a", type: "pl_walk_to", words: "walk to prontera x 150 y 180", count: 1, value: false };
  assert.equal(looseText(one, { kind: "main" }), "“walk to prontera x 150 y 180” is not attached to “when the program starts”, so it does not run.");
  assert.match(looseText({ ...one, count: 3 }, { kind: "block", name: "farm" }), /and 2 more blocks are not attached to “when the flow arrives on farm”, so they do not run\.$/);
  assert.match(looseText(one, { kind: "global" }), /is not inside a “when …” event, so it does not run\.$/);
  assert.equal(looseText({ ...one, words: "detector v1 sees monster", value: true }, { kind: "main" }), "“detector v1 sees monster” is not plugged into a block, so it is not used.");
  assert.equal(hatTitle({ kind: "main" }), "when the program starts");
});

test("a block's words come from its definition, decorations left out", () => {
  assert.match(blockWords({ type: "pl_walk_to", fields: { MAP: "prt_fild08", X: 1, Y: 2 } }), /^walk\sto\sprt_fild08\sx\s1\sy\s2$/);
  assert.match(blockWords({ type: "pl_wait_until", fields: { TIMEOUT: 30 }, inputs: { COND: { block: { type: "pl_detect_sees", fields: { MODEL: "v1", CLASS: "monster" } } } } }), /^wait\suntil\s\(detector\sv1\ssees\smonster\)\sat\smost\s30\ss$/);
  assert.equal(blockWords({ type: "pl_hunt" }), "hunt the map's targets");
  assert.ok(blockWords({ type: "pl_talk_npc", fields: { NPC: "n_" + "x".repeat(80) } }).endsWith("…"));
});

test("the status sentence says what to do next, and never offers a live run", () => {
  const base = { loading: false, engine: null, issues: 0, lintErrors: 0, simulating: false, mapTab: false };
  assert.equal(statusText(base), "Ready. Press Simulate to run the flow in the simulator (nothing here runs in the game).");
  assert.equal(statusText({ ...base, loading: true }), "Loading the block editor…");
  assert.equal(statusText({ ...base, issues: 2 }), "Fix the problems below to simulate the flow.");
  assert.match(statusText({ ...base, lintErrors: 1 }), /^Lint found 1 error:/);
  assert.match(statusText({ ...base, engine: "http_503" }), /not reachable \(http_503\)/);
  for (const s of [base, { ...base, mapTab: true }]) assert.doesNotMatch(statusText(s), /\brun the bot\b|live/i);
  assert.equal(tabOf({ owner: "block:farm" }, false), "block:farm");
  assert.equal(tabOf({ owner: "global" }, true), "events");
  assert.equal(tabOf({ owner: "flow" }, true), "main");
  assert.equal(tabOf({ owner: "flow" }, false), "map");
  assert.deepEqual(lintErrors(null), []);
});

// --- the model blocks --------------------------------------------------------------------------
const MODELS: Models = {
  v1: { kind: "detector", status: "live", file: "a.onnx", sha256: "32b448a1d197", maps: [], classes: ["player", "monster", "npc"], untrained: [], mobs: {}, why: "", available: true, counts: true },
  xmas02: { kind: "detector", status: "live", file: "b.onnx", sha256: "293dca922e3e", maps: ["xmas_dun02"], classes: ["player", "mystcase", "cookie_xmas"], untrained: ["npc", "warp"], mobs: {}, why: "", available: true, counts: true },
  "stormy-v1": { kind: "boss_recognizer", status: "not_adopted", file: "c.npz", sha256: "a1287571e264", maps: ["xmas_dun02"], classes: ["party"], untrained: [], mobs: {}, why: "failed", available: false, counts: false },
};

test("a not-adopted model is never offered as a working sensor", () => {
  assert.deepEqual(modelOptions(MODELS, null, false).map(([, v]) => v), ["v1", "xmas02"]);
  assert.deepEqual(modelOptions(MODELS, "v1", false)[1], ["xmas02 (xmas_dun02)", "xmas02"]);
  // an imported flow keeps its value, marked
  assert.deepEqual(modelOptions(MODELS, "stormy-v1", false).at(-1), ["stormy-v1 (not adopted)", "stormy-v1"]);
  assert.deepEqual(modelOptions(MODELS, "v9", true).at(-1), ["v9 (unknown model)", "v9"]);
  assert.deepEqual(modelOptions(null, null, false), [["v1", "v1"]]);
  assert.deepEqual(notAdopted(MODELS), ["stormy-v1: not adopted, so not offered (a boss recognizer)"]);
  assert.deepEqual(firstDetector(MODELS), { model: "v1", label: "monster" });
});

test("the class menu follows the model; an untrained class is not offered", () => {
  assert.deepEqual(classOptions(MODELS, "xmas02", "cookie_xmas").map(([, v]) => v), ["player", "mystcase", "cookie_xmas"]);
  assert.equal(classOptions(MODELS, "xmas02", "cookie_xmas")[2][0], "cookie xmas");
  assert.deepEqual(classOptions(MODELS, "xmas02", "npc").at(-1), ["npc (not a class of xmas02)", "npc"]);
  assert.equal(classFor(MODELS, "xmas02", "monster"), "player"); // a new model: its first class
  assert.equal(classFor(MODELS, "v1", "monster"), "monster"); // still fits: kept
});

// --- the search -------------------------------------------------------------------------------
test("the search finds blocks by their words, other words and their Python", () => {
  const entries: SearchEntry[] = [
    { category: "Control", item: { kind: "block", type: "pl_wait" }, text: "wait 1 seconds" },
    { category: "Movement", item: { kind: "block", type: "pl_walk_to" }, text: "walk to … x 0 y 0" },
    { category: "Sensors", item: { kind: "block", type: "pl_detect_sees" }, text: "detector v1 sees monster" },
  ];
  const types = (q: string) => matchEntries(q, entries).map((e) => e.item.type);
  assert.deepEqual(types("wait"), ["pl_wait"]);
  assert.deepEqual(types("sleep"), ["pl_wait"]); // "I still cannot find sleep" (matpilot, 2026-11-08)
  assert.deepEqual(types("walk_to"), ["pl_walk_to"]); // the Python name
  assert.deepEqual(types("detector sees"), ["pl_detect_sees"]);
  assert.deepEqual(types("see"), ["pl_detect_sees"]);
  assert.deepEqual(types("zzz"), []);
  assert.equal(normalise("Walk_To, colour!"), "walk to color");
  const fly = searchFlyout("wa", entries);
  assert.deepEqual(fly.map((f) => f.kind === "label" ? `label:${f.text}` : f.type), ["label:Control", "pl_wait", "label:Movement", "pl_walk_to"]);
  assert.equal(searchFlyout("", entries)[0].kind, "label");
});

// --- the starter -------------------------------------------------------------------------------------
test("the starters are their committed canonical fixtures, and every tab round-trips", () => {
  const load = (n: string) => JSON.parse(readFileSync(new URL(`./fixtures/${n}.json`, import.meta.url), "utf8")) as Flow;
  // the FIRST SCREEN (2026-11-09 pm): two map blocks, so the studio opens on the Map tab
  const two = starterFlow();
  assert.equal(canonical(two), canonical(load("starter")));
  assert.deepEqual(two.workflow?.blocks.map((b) => b.name), ["town", "field"]);
  assert.equal(two.workflow?.start_block, "town");
  assert.equal(STARTER_WORLD, "sample"); // the sample's synthetic sheets
  const exits = two.workflow!.blocks.flatMap((b) => b.main.filter((st) => st.kind === "take_exit").map((st) => st.kind === "take_exit" && `${b.name}->${st.exit.kind}->${st.exit.to_block}`));
  assert.deepEqual(exits, ["town->npc_warp->field", "field->item_warp->town"]);
  const one = oneMapStarter();
  assert.equal(canonical(one), canonical(load("starter_one_map")));
  assert.equal(one.workflow, null);
  for (const [flow, scopes] of [
    [two, [{ kind: "block", name: "town" }, { kind: "block", name: "field" }, { kind: "global" }]],
    [one, [{ kind: "main" }, { kind: "global" }]],
  ] as const) {
    for (const scope of scopes) {
      const ws = JSON.parse(JSON.stringify(toWorkspace(flow, scope))) as Workspace;
      const back = fromWorkspace(flow, scope, ws);
      assert.ok(back.ok && canonical(back.flow) === canonical(flow), `${flow.name} ${JSON.stringify(scope)}`);
    }
  }
  // the town's save point shows as its sentence block (Actions)
  const town = toWorkspace(two, { kind: "block", name: "town" }).blocks.blocks[0].inputs?.DO?.block;
  assert.equal(town?.type, "pl_set_save_point");
});

// 2026-11-13 (Batt: "on /flows I don't see this flow's name"): the flows row names the studio's flow
test("the flows row reads the studio's saved flow name, never failing", () => {
  const mem = (v: string | null): StorageLike => ({ getItem: () => v, setItem: () => {}, removeItem: () => {} });
  assert.equal(savedFlowName(mem(JSON.stringify({ name: "my_first_workflow", ir: 1 }))), "my_first_workflow");
  assert.equal(savedFlowName(mem(null)), "my flow");
  assert.equal(savedFlowName(mem("{broken")), "my flow");
  assert.equal(savedFlowName(mem(JSON.stringify({ name: 7 }))), "my flow");
  assert.equal(savedFlowName(mem(JSON.stringify({ name: "  " }))), "my flow");
  assert.equal(savedFlowName(null), "my flow");
  const throws: StorageLike = { getItem: () => { throw new Error("blocked"); }, setItem: () => {}, removeItem: () => {} };
  assert.equal(savedFlowName(throws), "my flow");
});
