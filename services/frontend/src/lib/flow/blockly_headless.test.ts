// The block editor's Blockly side in the REAL Blockly 13 (headless, in node: no DOM, no jsdom):
// what the studio registers (components/flows/blockly-register.ts, blockly-fields.ts,
// blockly-search.ts), the toolbox's blocks, the IR -> Blockly -> IR round trip through Blockly's
// own serialization, and the model blocks' menus keeping a loaded value. The page's rendering (the
// toolbox row, the flyouts, the themes on screen) needs a browser; this covers everything else.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import type * as BlocklyT from "blockly/core";

import { followModel, registerDetectorMenus } from "../../components/flows/blockly-fields.ts";
import { register, themesOf } from "../../components/flows/blockly-register.ts";
import { registerSearch, SEARCH_KIND } from "../../components/flows/blockly-search.ts";
import { BLOCK_DEFS, toolbox, toolboxBlocks } from "./blockdefs.ts";
import { fromWorkspace, type Scope, toWorkspace, type Workspace } from "./blocks.ts";
import { canonical, clone, type Flow } from "./ir.ts";
import type { Models } from "./models.ts";
import { starterFlow } from "./starter.ts";
import { FIXTURES, fixture } from "./testkit.ts";

const require = createRequire(import.meta.url);
const lib = (p: string) => fileURLToPath(new URL(`../../../node_modules/blockly/${p}`, import.meta.url));
const B = require(lib("blockly_compressed.js")) as typeof BlocklyT;
B.setLocale(require(lib("msg/en.js")) as Record<string, string>);

const MODELS: Models = {
  v1: { kind: "detector", status: "live", file: "a.onnx", sha256: "32b448a1d197", maps: [], classes: ["player", "monster", "npc"], untrained: [], mobs: {}, why: "", available: true, counts: true },
  xmas02: { kind: "detector", status: "live", file: "b.onnx", sha256: "293dca922e3e", maps: ["xmas_dun02"], classes: ["player", "mystcase", "cruiser", "cookie", "cookie_xmas"], untrained: ["npc", "warp"], mobs: {}, why: "", available: true, counts: true },
  "stormy-v1": { kind: "boss_recognizer", status: "not_adopted", file: "c.npz", sha256: "a1287571e264", maps: ["xmas_dun02"], classes: ["party"], untrained: [], mobs: {}, why: "failed", available: false, counts: false },
};
register(B);
registerDetectorMenus(B, () => MODELS);
registerSearch(B, () => null);

const scopes = (f: Flow): Scope[] => [{ kind: "global" }, ...(f.workflow ? f.workflow.blocks.map((b) => ({ kind: "block" as const, name: b.name })) : [{ kind: "main" as const }])];

function detectFlow(): Flow {
  const f = clone(fixture("visit_and_choose"));
  const sense = (sensor: string, model: string, label: string) => ({ kind: "sense" as const, sensor, args: { label: { kind: "lit" as const, value: label }, model: { kind: "lit" as const, value: model } } });
  f.main = [
    { kind: "wait_until", cond: sense("detector_sees", "xmas02", "cookie_xmas"), timeout_s: 30, outcome_to: null },
    // values the menus do not offer (not adopted; not a class of v1): kept exactly
    { kind: "if", cond: sense("detector_sees", "stormy-v1", "party"), then: [{ kind: "stop", reason: "boss" }], orelse: [] },
    { kind: "if", cond: { kind: "cmp", op: ">", left: sense("detector_count", "v1", "dragon"), right: { kind: "lit", value: 2 } }, then: [], orelse: [] },
    ...(f.main ?? []),
  ];
  return f;
}

test("every block type is created by the real Blockly", () => {
  const ws = new B.Workspace();
  for (const d of BLOCK_DEFS) assert.ok(B.serialization.blocks.append({ type: d.type }, ws), d.type);
  ws.dispose();
});

test("every block the toolbox offers loads, and its words are what the search finds", () => {
  const cat = { walk_to: { concept: "nav.walk_to", timeout_s: 120 }, talk_npc: { concept: "npc.talk", timeout_s: 60 }, use_item: { concept: "inv.use_item", timeout_s: 10 }, sit: { concept: "char.sit", timeout_s: 5 } };
  const ws = new B.Workspace();
  const words = new Map<string, string>();
  for (const scope of ["block", "global", "main"] as const) {
    for (const { item } of toolboxBlocks(toolbox(cat, scope, null, {}, { model: "v1", label: "monster", notes: [] }))) {
      const { kind: _kind, ...state } = item;
      void _kind;
      const b = B.serialization.blocks.append(state as unknown as BlocklyT.serialization.blocks.State, ws);
      words.set(item.type, b.toString());
    }
  }
  assert.match(words.get("pl_wait") ?? "", /^wait\s1\sseconds/);
  assert.match(words.get("pl_detect_sees") ?? "", /detector\sv1\ssees\smonster/);
  assert.match(words.get("pl_walk_to") ?? "", /^walk\sto\s/);
  ws.dispose();
});

test("IR -> the real Blockly -> IR is exact: the fixtures, the starter and the model blocks", () => {
  const flows: Flow[] = [...FIXTURES.map((n) => fixture(n)), starterFlow(), detectFlow()];
  for (const flow of flows) {
    for (const scope of scopes(flow)) {
      const ws = new B.Workspace();
      B.serialization.workspaces.load(toWorkspace(flow, scope) as unknown as object, ws);
      const saved = B.serialization.workspaces.save(ws) as unknown as Workspace;
      const back = fromWorkspace(flow, scope, saved);
      assert.ok(back.ok, `${flow.name} ${JSON.stringify(scope)}: ${!back.ok && back.errors.join("; ")}`);
      if (back.ok) assert.equal(canonical(back.flow), canonical(flow), `${flow.name} ${JSON.stringify(scope)}`);
      ws.dispose();
    }
  }
});

test("a loaded model block keeps its value; the menus offer the live models and that model's classes", () => {
  const ws = new B.Workspace();
  const load = (model: string, label: string) => B.serialization.blocks.append({ type: "pl_detect_sees", fields: { MODEL: model, CLASS: label } }, ws);
  const a = load("xmas02", "cookie_xmas");
  assert.equal(a.getFieldValue("MODEL"), "xmas02");
  assert.equal(a.getFieldValue("CLASS"), "cookie_xmas");
  assert.equal(a.getField("CLASS")!.getText(), "cookie xmas"); // shown as itself, not the default
  const menu = (b: BlocklyT.Block, f: string) => (b.getField(f) as BlocklyT.FieldDropdown).getOptions(false).map(([, v]) => v);
  assert.deepEqual(menu(a, "MODEL"), ["v1", "xmas02"]); // the not-adopted recognizer is not offered
  assert.deepEqual(menu(a, "CLASS"), ["player", "mystcase", "cruiser", "cookie", "cookie_xmas"]);
  const s = load("stormy-v1", "party");
  assert.equal(s.getFieldValue("MODEL"), "stormy-v1"); // kept (an imported flow): the linter names it
  assert.match(s.getField("MODEL")!.getText(), /not adopted/);
  const d = load("v1", "dragon");
  assert.equal(d.getFieldValue("CLASS"), "dragon");
  assert.match(d.getField("CLASS")!.getText(), /not a class of v1/);
  ws.dispose();
});

test("after another model is picked, the class follows (its first) unless it still fits", () => {
  const ws = new B.Workspace();
  const b = B.serialization.blocks.append({ type: "pl_detect_count", fields: { MODEL: "v1", CLASS: "monster" } }, ws);
  const listen = followModel(B, ws as unknown as BlocklyT.WorkspaceSvg, () => MODELS);
  b.getField("MODEL")!.setValue("xmas02");
  listen(new B.Events.BlockChange(b, "field", "MODEL", "v1", "xmas02"));
  assert.equal(b.getFieldValue("CLASS"), "player");
  b.getField("CLASS")!.setValue("cookie");
  b.getField("MODEL")!.setValue("xmas02");
  listen(new B.Events.BlockChange(b, "field", "MODEL", "xmas02", "xmas02"));
  assert.equal(b.getFieldValue("CLASS"), "cookie"); // still a class of xmas02: kept
  // a count names only detectors: a recognizer is not in its model menu
  assert.ok(!(b.getField("MODEL") as BlocklyT.FieldDropdown).getOptions(false).some(([, v]) => v === "stormy-v1"));
  ws.dispose();
});

test("MatPilot's themes and the search row are registered", () => {
  const th = themesOf(B);
  assert.equal(th.light.blockStyles.mp_sensor_blocks.colourPrimary, "#0e7490");
  assert.equal(th.dark.blockStyles.mp_movement_blocks.colourPrimary, "#a21caf");
  assert.equal(th.light.blockStyles.mp_start_blocks.hat, "cap");
  assert.ok(B.registry.hasItem(B.registry.Type.TOOLBOX_ITEM, SEARCH_KIND));
});
