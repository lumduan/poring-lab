// Round 21 (live-blocks.md 12.5): the picker FIELDS in the REAL Blockly 13 (headless, in node, as
// blockly_headless.test.ts): they are the registered field_pl_num / field_pl_text, every value goes
// in and comes out exactly (a number stays a number, a text a text; an unknown function, a model
// not in models.yaml, a cell past any slider's end are KEPT, never clamped by a picker), the
// workspace of every tab of every ready-made and FROZEN project saves back field for field, and a
// reference shows ▾ and ⚠ (unknown) without changing its value. The pickers' DOM (the DropDownDiv)
// needs a browser: the re-measure list in live-blocks.md 12.5.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import type * as BlocklyT from "blockly/core";

import { displayOf, PICK_NUM, PICK_TEXT, setPickerSource, specOf } from "../../components/flows/blockly-pickers.ts";
import { register } from "../../components/flows/blockly-register.ts";
import { tabFromWorkspace, tabToWorkspace, type Workspace, type WsBlock } from "./blocks.ts";
import { canonical } from "./ir.ts";
import { MAIN_TAB, type Project, sampleProject, xmasProject } from "./project.ts";
import { SETTING_BY_NAME, settingType } from "./settings.ts";
import { sessionProject } from "./testkit.ts";

const require = createRequire(import.meta.url);
const lib = (p: string) => fileURLToPath(new URL(`../../../node_modules/blockly/${p}`, import.meta.url));
const B = require(lib("blockly_compressed.js")) as typeof BlocklyT;
B.setLocale(require(lib("msg/en.js")) as Record<string, string>);
register(B);

const fixture = (name: string): Project => JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8")) as Project;
/** The ready-made projects and the three FROZEN A/B arms (their sha256 pinned by the backend's
 * test_settings_blocks.py): every tab of each must save back exactly. */
const PROJECTS: [string, Project][] = [
  ["xmas", xmasProject()],
  ["sample", sampleProject()],
  ["session", sessionProject()],
  ...["project_xmas_dun02.json", "project_xmas_dun02_stage2.json", "project_xmas_dun02_stage3.json", "project_xmas_dun02_stage4.json", "project_sample.json", "project_session.json"].map((f): [string, Project] => [f, fixture(f)]),
];

/** Every block's fields in the order the workspace holds them (top blocks, inputs, next). */
function fieldsOf(ws: Workspace): [string, Record<string, unknown>][] {
  const out: [string, Record<string, unknown>][] = [];
  const walk = (b: WsBlock | undefined) => {
    for (let cur = b; cur; cur = cur.next?.block) {
      out.push([cur.type, cur.fields ?? {}]);
      for (const k of Object.keys(cur.inputs ?? {}).sort()) walk(cur.inputs?.[k]?.block);
    }
  };
  for (const b of ws.blocks.blocks) walk(b);
  return out;
}

test("the converted fields are the picker fields: a number is a FieldNumber, a text a FieldTextInput", () => {
  const ws = new B.Workspace();
  const call = B.serialization.blocks.append({ type: "pl_call", fields: { PROC: "heal", ARGS: "" } }, ws);
  assert.ok(call.getField("PROC") instanceof B.FieldTextInput);
  assert.equal(specOf(call.getField("PROC")!)?.kind, "ref");
  assert.equal(specOf(call.getField("ARGS")!)?.kind, "expr");
  const wait = B.serialization.blocks.append({ type: "pl_wait", fields: { SECONDS: 1 } }, ws);
  assert.ok(wait.getField("SECONDS") instanceof B.FieldNumber);
  assert.equal(specOf(wait.getField("SECONDS")!)?.kind, "stepper");
  assert.ok(B.registry.hasItem(B.registry.Type.FIELD, PICK_NUM) && B.registry.hasItem(B.registry.Type.FIELD, PICK_TEXT));
  // the names a block DEFINES stay plain text: a variable's, an event's
  const v = B.serialization.blocks.append({ type: "pl_vardecl", fields: { NAME: "x" } }, ws);
  assert.equal(specOf(v.getField("NAME")!), undefined);
  ws.dispose();
});

test("value in = value out: unknown references, odd texts and numbers past any slider are kept exactly", () => {
  const ws = new B.Workspace();
  const cases: [string, Record<string, string | number>][] = [
    ["pl_call", { PROC: "no_such_fn", ARGS: '"F6", times=2' }],
    ["pl_save_point", { MAP: "nowhere_town", X: 9999, Y: -3 }],
    ["pl_walk_to", { MAP: "", X: 1234, Y: 0 }],
    ["pl_stop", { REASON: "my_reason" }],
    ["pl_wait", { SECONDS: 0.3 }],
    ["pl_wait_until", { TIMEOUT: 900 }],
    ["pl_action", { BLOCK: "use_model", ARGS: 'model="xmas03"' }],
    ["pl_expr", { TEXT: "hp_percent( <" }], // a text that does not read: kept (the converter says why)
    ["pl_event", { NAME: "drink", RANK: "abc", COOLDOWN: 0.7, MAX_RUN: "", MAX_MIN: "70", MAX_10: "", FAILS: "4", ESCALATE: "nobody" }],
    ["pl_dungeon_hunt", { HEAL: "heal", FLY: "fly_wing", KNIFE_ON: "knife_on", KNIFE_BACK: "knife_back", HOME: "", RESPAWN: "", RESPAWN_OK: "", EAT: "not_here" }],
    ["pl_login", { SERVER: "another-server", CREDENTIAL: "lab_gm" }],
    ["pl_exit_walk", { MAP: "m", X: 3, Y: 4, TO_BLOCK: "gone_node", TO_ENTRY: "gone_entry" }],
    [settingType(SETTING_BY_NAME.get("knife_hp_min")!), { VALUE: 55 }],
    [settingType(SETTING_BY_NAME.get("respawn_at")!), { X: 645, Y: 481 }],
  ];
  for (const [type, fields] of cases) {
    const b = B.serialization.blocks.append({ type, fields }, ws);
    const saved = B.serialization.blocks.save(b) as { fields?: Record<string, unknown> };
    for (const [k, v] of Object.entries(fields)) assert.strictEqual(saved.fields?.[k], v, `${type}.${k}`);
    b.dispose(false);
  }
  // a setting's number keeps its registry range (the field's own min / max, as before round 21)
  const knife = B.serialization.blocks.append({ type: settingType(SETTING_BY_NAME.get("knife_hp_min")!), fields: { VALUE: 55 } }, ws);
  knife.getField("VALUE")!.setValue(150);
  assert.equal(knife.getFieldValue("VALUE"), 90);
  ws.dispose();
});

test("every tab of the ready-made and the frozen projects -> the real Blockly -> saves back FIELD FOR FIELD, and the project exactly", () => {
  for (const [name, p] of PROJECTS) {
    for (const n of p.nodes) {
      for (const t of n.tabs) {
        const scope = { node: n.id, tab: t.name };
        const before = tabToWorkspace(p, scope);
        const ws = new B.Workspace();
        B.serialization.workspaces.load(before as unknown as object, ws);
        const saved = B.serialization.workspaces.save(ws) as unknown as Workspace;
        const a = fieldsOf(before);
        const b = fieldsOf(saved);
        assert.equal(b.length, a.length, `${name} ${n.id}/${t.name}`);
        a.forEach(([type, fields], i) => {
          assert.equal(b[i][0], type);
          for (const [k, v] of Object.entries(fields)) assert.strictEqual(b[i][1][k], v, `${name} ${n.id}/${t.name}: ${type}.${k}`);
        });
        const back = tabFromWorkspace(p, scope, saved);
        assert.ok(back.ok, `${name} ${n.id}/${t.name}: ${!back.ok && back.errors.join("; ")}`);
        if (back.ok) assert.equal(canonical(back.project), canonical(p), `${name} ${n.id}/${t.name}`);
        ws.dispose();
      }
    }
  }
});

test("a reference shows ▾, and ⚠ when it is not one of what exists; its value and its words stay", () => {
  const p = xmasProject();
  setPickerSource(() => ({ project: p, node: "xmas_dun02", tab: MAIN_TAB, catalogue: null, maps: null }));
  try {
    const ws = new B.Workspace();
    const hunt = B.serialization.blocks.append({ type: "pl_dungeon_hunt", fields: { HEAL: "heal", FLY: "fly_wing", KNIFE_ON: "knife_on", KNIFE_BACK: "knife_back", HOME: "fly_hom", RESPAWN: "", RESPAWN_OK: "", EAT: "eat" } }, ws);
    const shows = (f: string) => displayOf(hunt.getField(f)!, String(hunt.getFieldValue(f)));
    assert.equal(shows("HEAL"), "heal ▾");
    assert.equal(shows("HOME"), "fly_hom ⚠ ▾"); // a typo: kept, marked
    assert.equal(shows("RESPAWN"), "none ▾"); // an empty optional role
    assert.equal(hunt.getFieldValue("HOME"), "fly_hom");
    assert.match(hunt.toString(), /home \(Butterfly Wing\): call fly_hom/); // the block's words (the search's) stay the value
    const ev = B.serialization.blocks.append({ type: "pl_event", fields: { NAME: "e", MAX_RUN: "", RANK: "x" } }, ws);
    assert.equal(displayOf(ev.getField("MAX_RUN")!, ""), "—");
    assert.equal(displayOf(ev.getField("RANK")!, "x"), "x ⚠");
    // a number field shows as before (the width model of round 20 holds)
    const wait = B.serialization.blocks.append({ type: "pl_wait", fields: { SECONDS: 2 } }, ws);
    assert.match(wait.toString(), /^wait 2 seconds/);
    ws.dispose();
  } finally {
    setPickerSource(null);
  }
});
