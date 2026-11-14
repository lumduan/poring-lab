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

import { displayOf, PICK_NUM, PICK_TEXT, pickerDrag, pickerSession, setPickerSource, specOf } from "../../components/flows/blockly-pickers.ts";
import { register, syncExprWrap } from "../../components/flows/blockly-register.ts";
import { tabFromWorkspace, tabToWorkspace, type Workspace, type WsBlock } from "./blocks.ts";
import { canonical } from "./ir.ts";
import { pointIn } from "./pickers.ts";
import { MAIN_TAB, type Project, sampleProject, xmasProject } from "./project.ts";
import { SETTING_BY_NAME, SETTINGS, settingType } from "./settings.ts";
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
    assert.match(hunt.toString(), /home: fly_hom/); // the block's words (the search's) stay the value
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

test("the real Blockly builds the rows layout.ts measures: each runner role with its words in ONE end-row input", () => {
  const ws = new B.Workspace();
  const hunt = B.serialization.blocks.append({ type: "pl_dungeon_hunt" }, ws);
  const words: Record<string, string> = { HEAL: "heal:", FLY: "Fly Wing:", KNIFE_ON: "Knife on:", KNIFE_BACK: "Knife off:", HOME: "home:", RESPAWN: "died:", RESPAWN_OK: "confirm:", EAT: "eat:" };
  for (const [field, w] of Object.entries(words)) {
    const input = hunt.inputList.find((i) => i.fieldRow.some((f) => f.name === field))!;
    assert.ok(input instanceof B.inputs.EndRowInput, field); // the row ends after it (zelos)
    assert.deepEqual(input.fieldRow.map((f) => f.getText()), [w, String(hunt.getFieldValue(field))], field);
  }
  // the save point: three rows, each an end-row input
  const save = B.serialization.blocks.append({ type: "pl_save_point", fields: { MAP: "geffen", X: 119, Y: 40 } }, ws);
  const rows = save.inputList.filter((i) => i instanceof B.inputs.EndRowInput).map((i) => i.fieldRow.map((f) => f.getText()).join(" "));
  assert.deepEqual(rows.slice(0, 3), ["the save point is", "on geffen", "x 119 y 40"]);
  // the run line's row hides while it is empty, the badge's too (pl_label_rows)
  assert.equal(save.getInput("ROW_RUN")?.isVisible(), false);
  assert.equal(hunt.getInput("ROW_BADGE")?.isVisible(), false);
  ws.dispose();
});

// Round 23 (the reviewer: after Escape, Undo was enabled and Ctrl+Z RE-APPLIED the cancelled
// value -- stepper 3.5 -> 4, percent 50 -> 51, cell 119 -> 120, a condition "< 50" -> "<= 50"):
// Blockly fires its events on the next animation frame, which node does not have (it falls back
// to a timeout, which is why round 22's test passed). These tests give node a browser's frames.
const frame = (ms = 40) => new Promise((r) => setTimeout(r, ms));
async function withFrames(fn: () => Promise<void>): Promise<void> {
  const g = globalThis as { requestAnimationFrame?: (cb: () => void) => unknown };
  const had = g.requestAnimationFrame;
  g.requestAnimationFrame = (cb) => setTimeout(cb, 16);
  try {
    await fn();
  } finally {
    if (had) g.requestAnimationFrame = had;
    else delete g.requestAnimationFrame;
  }
}
const POINT = SETTINGS.fields.find((f) => f.kind === "point")!;
/** Each kind of picker: the block, the session's fields, the value it opens on, a preview and the
 * value kept (the reviewer's own examples first). */
const KINDS: { kind: string; block: BlocklyT.serialization.blocks.State; fields: string[]; preview: unknown[][]; kept: unknown[] }[] = [
  { kind: "stepper", block: { type: "pl_wait", fields: { SECONDS: 3.5 } }, fields: ["SECONDS"], preview: [[3.6], [3.8]], kept: [4] },
  { kind: "percent", block: { type: settingType(SETTING_BY_NAME.get("END_FLY_BELOW")!), fields: { VALUE: 50 } }, fields: ["VALUE"], preview: [[50.5], [50.8]], kept: [51] },
  { kind: "cell", block: { type: "pl_save_point", fields: { MAP: "geffen", X: 119, Y: 40 } }, fields: ["X", "Y"], preview: [[119.5, 40], [119.8, 41]], kept: [120, 42] },
  { kind: "point", block: { type: settingType(POINT), fields: { X: 645, Y: 481 } }, fields: ["X", "Y"], preview: [[640, 470], [600, 400]], kept: [128, 360] },
  { kind: "expr", block: { type: "pl_expr", fields: { TEXT: "hp_percent() < 50" } }, fields: ["TEXT"], preview: [["hp_percent() <"], ["hp_percent() <="]], kept: ["hp_percent() <= 50"] },
  { kind: "optnum", block: { type: "pl_event", fields: { NAME: "drink", RANK: "" } }, fields: ["RANK"], preview: [["2"], ["5"]], kept: ["3"] },
  { kind: "ref", block: { type: "pl_call", fields: { PROC: "heal", ARGS: "" } }, fields: ["PROC"], preview: [["fly"], ["fly_w"]], kept: ["fly_wing"] },
];

test("round 23: Escape / Cancel leaves the undo stack EXACTLY as before the picker opened -- every kind, Ctrl+Z included", async () => {
  await withFrames(async () => {
    for (const k of KINDS) {
      const ws = new B.Workspace();
      const b = B.serialization.blocks.append(k.block, ws);
      const fs = k.fields.map((n) => b.getField(n)!);
      const start = fs.map((f) => f.getValue());
      await frame();
      ws.clearUndo();
      const s = pickerSession(fs);
      for (const vs of k.preview) {
        s.run(() => vs.forEach((v, i) => fs[i].setValue(v))); // a drag, a tap, a key: the live preview
        await frame(); // the events fire, a frame later
      }
      assert.equal(ws.getUndoStack().length, 0, `${k.kind}: the preview is no undo step`);
      s.cancel();
      assert.deepEqual(fs.map((f) => f.getValue()), start, k.kind);
      await frame();
      assert.equal(ws.getUndoStack().length, 0, `${k.kind}: Undo stays greyed`);
      ws.undo(false); // Ctrl+Z
      await frame();
      assert.deepEqual(fs.map((f) => f.getValue()), start, `${k.kind}: Ctrl+Z after a cancel re-applies nothing`);
      assert.equal(ws.getRedoStack().length, 0, k.kind);
      ws.dispose();
    }
  });
});

test("round 23: a KEPT session is ONE undo step: Ctrl+Z puts back the value from before it opened, redo the kept one -- every kind", async () => {
  await withFrames(async () => {
    for (const k of KINDS) {
      for (const sameTick of [false, true]) {
        const ws = new B.Workspace();
        const b = B.serialization.blocks.append(k.block, ws);
        const fs = k.fields.map((n) => b.getField(n)!);
        const start = fs.map((f) => f.getValue());
        await frame();
        ws.clearUndo();
        const s = pickerSession(fs);
        for (const vs of [...k.preview, k.kept]) {
          s.run(() => vs.forEach((v, i) => fs[i].setValue(v)));
          if (!sameTick) await frame();
        }
        const kept = fs.map((f) => f.getValue());
        s.commit(); // Done, Enter, a tap outside, a pick from a list
        s.commit(); // once only
        s.cancel(); // too late: kept is kept
        await frame();
        const what = `${k.kind}${sameTick ? " (in one frame)" : ""}`;
        assert.deepEqual(fs.map((f) => f.getValue()), kept, what);
        const stack = ws.getUndoStack();
        assert.ok(stack.length >= 1, `${what}: one undo step`);
        assert.equal(new Set(stack.map((e) => e.group)).size, 1, `${what}: one undo step`);
        ws.undo(false); // Ctrl+Z
        await frame();
        assert.deepEqual(fs.map((f) => f.getValue()), start, `${what}: Ctrl+Z puts back what was there before`);
        assert.equal(ws.getUndoStack().length, 0, what);
        ws.undo(true); // redo
        await frame();
        assert.deepEqual(fs.map((f) => f.getValue()), kept, `${what}: redo`);
        ws.dispose();
      }
    }
  });
});

test("round 23: a wrapped condition's further rows open its picker (they are tappable labels, never saved)", () => {
  const ws = new B.Workspace();
  const long = B.serialization.blocks.append({ type: "pl_expr", fields: { TEXT: 'hotbar_count(key="F6") == 0 and hp_percent() < 50' } }, ws);
  syncExprWrap(B, long);
  const text = long.getField("TEXT")!;
  let opened = 0;
  text.showEditor = () => void opened++; // the picker itself needs a browser: count the opening
  const rows = long.inputList.filter((i) => /^WRAP[0-9]+$/.test(i.name));
  assert.ok(rows.length >= 1);
  for (const r of rows) {
    const label = r.fieldRow[0];
    assert.ok(label instanceof B.FieldLabel && label.isClickable(), r.name);
    label.showEditor();
  }
  assert.equal(opened, rows.length);
  const saved = B.serialization.blocks.save(long) as { fields?: Record<string, unknown> };
  assert.deepEqual(Object.keys(saved.fields ?? {}), ["TEXT"]);
  ws.dispose();
});

test("round 22: a long condition wraps onto rows of the same box, whole; the saved fields stay the text alone", () => {
  const ws = new B.Workspace();
  const long = B.serialization.blocks.append({ type: "pl_expr", fields: { TEXT: 'hotbar_count(key="F6") == 0' } }, ws);
  syncExprWrap(B, long);
  // the field shows the first line (displayOf), each further line is a label row
  const rows = long.inputList.map((i) => i.fieldRow.map((x) => (x.name === "TEXT" ? displayOf(x, x.getText()) : x.getText())).join(""));
  assert.ok(rows.length >= 2, JSON.stringify(rows));
  assert.equal(rows.join(" ").replace(/\( /g, "("), 'hotbar_count(key="F6") == 0'); // nothing cut
  assert.ok(long.isSimpleReporter()); // one field a row: Blockly draws it as ONE white box
  const saved = B.serialization.blocks.save(long) as { fields?: Record<string, unknown> };
  assert.deepEqual({ ...saved.fields }, { TEXT: 'hotbar_count(key="F6") == 0' });
  // a short one has no extra rows; a long one made short loses them
  long.getField("TEXT")!.setValue("hp_percent() < 50");
  syncExprWrap(B, long);
  assert.equal(long.inputList.length, 1);
  ws.dispose();
});

// --- round 24 (live-blocks.md 12.8): the FIRST drag after a point picker opens reads like the second
// The reviewer at 1440 (the picker COMPACT, the picture 176 x 99 at about (702, 505)): the first drag
// read 360 at 50 %, then 719 at 55 % and 90 %; a second drag read 360 / 396 / 648. The picker lives
// inside Blockly's injection div, so it moves with the canvas; on a wide screen the canvas moved UP
// after the press (the edit made the lint stale and the strip over the canvas lost its IN A RUN
// lines), and round 23 read the picture's box again at every move. These tests play the open
// sequence in order on the real drag code, with a fake picture whose box moves when the page does.
type Box = { left: number; top: number; width: number; height: number };
function fakePicture(box: Box, scrollTop = 0) {
  const root = { scrollTop };
  class Svg extends EventTarget {
    setPointerCapture(): void {}
    closest(sel: string): unknown {
      return sel === ".pl-picker" ? root : null;
    }
  }
  const svg = new Svg();
  const back = { getBoundingClientRect: () => ({ ...box }) }; // the drawn picture, wherever it is NOW
  const read: [number, number][] = [];
  pickerDrag(svg as unknown as SVGSVGElement, (fn) => fn(), (x, y) => void read.push(pointIn((x * 1280) / 256, (y * 720) / 144)), { el: back as unknown as Element, area: { x: 0.5, y: 0.5, width: 255, height: 143 } });
  const fire = (type: string, x: number, y: number) => svg.dispatchEvent(Object.assign(new Event(type, { cancelable: true }), { button: 0, pointerId: 1, clientX: x, clientY: y }));
  return { box, root, read, fire };
}

test("round 24: the canvas moves up after the press (the strip's IN A RUN lines go): the first drag reads 360 / 396 / 646, like the second", () => {
  const p = fakePicture({ left: 702, top: 505, width: 175.3, height: 98.3 }); // after Blockly's slide
  const T0 = { ...p.box }; // where the reviewer measured the picture before the first drag
  const at = (b: Box, f: number): [number, number] => [b.left + 0.5 * b.width, b.top + f * b.height];
  p.fire("pointerdown", ...at(T0, 0.5));
  p.box.top -= 56; // the edit makes the lint stale: the strip's three IN A RUN lines go, the canvas rises
  p.fire("pointermove", ...at(T0, 0.55));
  p.fire("pointermove", ...at(T0, 0.9));
  p.fire("pointerup", ...at(T0, 0.9));
  assert.deepEqual(p.read.map(([, y]) => y), [360, 396, 646], "the first drag (round 23 read 360 / 719 / 719)");
  assert.equal(p.read[1][0], 640); // x was always right
  // the second drag, measured where the picture is now
  const T1 = { ...p.box };
  p.read.length = 0;
  p.fire("pointerdown", ...at(T1, 0.5));
  p.fire("pointermove", ...at(T1, 0.55));
  p.fire("pointermove", ...at(T1, 0.9));
  p.fire("pointerup", ...at(T1, 0.9));
  assert.deepEqual(p.read.map(([, y]) => y), [360, 396, 646], "the second drag");
});

test("round 24: Blockly's slide and keepDropDownsInside's nudge landing after the press change nothing a move reads; a drag holds the picker's scroll", () => {
  const p = fakePicture({ left: 702, top: 489 + 8, width: 175.3, height: 98.3 }, 30); // mid-slide (16 px, 0.25 s)
  const pressAt: [number, number] = [p.box.left + 0.5 * p.box.width, p.box.top + 0.5 * p.box.height];
  p.fire("pointerdown", ...pressAt);
  p.box.top = 505; // the slide ends
  p.box.top -= 12; // the nudge back inside the blocks area
  p.root.scrollTop = 80; // and something scrolls the picker's root
  p.fire("pointermove", pressAt[0], pressAt[1] + 0.05 * p.box.height); // 5 % of the picture lower
  p.fire("pointerup", pressAt[0], pressAt[1] + 0.05 * p.box.height);
  assert.deepEqual(p.read.map(([, y]) => y), [360, 396]);
  assert.equal(p.root.scrollTop, 30); // held where it was at the press
});
