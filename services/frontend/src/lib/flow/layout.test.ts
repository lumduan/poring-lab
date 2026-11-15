// Round 21 (the re-measure of round 20, live-blocks.md 12.5): every block of every tab of the
// ready-made projects and the frozen A/B arms ends before Blockly's controls at 390 px, by the
// model of zelos' rows (layout.ts) -- the reviewer's own re-measure of main is its positive case.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { DEF_BY_TYPE, titleLines } from "./blockdefs.ts";
import { SETTING_GAP_Y, settingHeight, tabToWorkspace } from "./blocks.ts";
import { BOX, blockHeight, blockRows, blockWidth, INDENT, overlaps, ROUND, rowsOf, STACK_GAP, stackTops, type TopBox } from "./layout.ts";
import { EXPR_SHOW_UNITS, WRAP_UNITS, wrapExpr } from "./pickers.ts";
import { type Project, sampleProject, xmasFunctionsProject, xmasHuntProject, xmasProject } from "./project.ts";
import { rowUnits, SETTING_GEOMETRY as G, SETTING_ROW_BUDGET, settingOfType, textUnits } from "./settings.ts";
import { sessionProject } from "./testkit.ts";

const fixture = (name: string): Project => JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8")) as Project;
const PROJECTS: Project[] = [xmasProject(), xmasHuntProject(), xmasFunctionsProject(), sampleProject(), sessionProject(), ...["project_xmas_dun02_stage2.json", "project_xmas_dun02_stage3.json", "project_xmas_dun02_stage4.json"].map(fixture)];
const [T1, T2] = titleLines("when the run starts: she stands on xmas_dun02");
/** The labels the editor fills, at their widest: the longest badge, "replaces Global's". */
const LABELS = { BADGE: "● verified RDP + S2", RUN: "", TITLE: T1, TITLE2: T2, SCOPE: "replaces Global's" };
/** The rows the editor hides while empty: the run line (no simulate yet), a setting's warning and
 * note rows (settings.test.ts measures those). */
const HIDDEN = (n: string) => n === "ROW_RUN" || n.startsWith("ROW_WARN") || n.startsWith("ROW_NOTE");

test("the positive case: the model gives main's three rows the reviewer re-measured at 390 as wide or wider (bb6d41eb's layout)", () => {
  // the rows as bb6d41eb drew them (one row each, at the hat's statement input), in its fields
  const num = (v: string) => Math.max(40, textUnits(v) + BOX);
  const box = (v: string) => textUnits(v) + BOX;
  const rows: [string, number, number][] = [
    ["the save point is on geffen x 119 y 40", INDENT + rowUnits([textUnits("the save point is"), textUnits("on"), box("geffen"), textUnits("x"), num("119"), textUnits("y"), num("40")]), (404 - 135) / 0.6],
    ['use_model ( model="xmas02" ) ● plays live', INDENT + rowUnits([textUnits("use_model"), textUnits("("), box('model="xmas02"'), textUnits(")"), textUnits("● plays live")]), (402 - 135) / 0.6],
    ["Fly Wing: call fly_wing Knife on: call knife_on", INDENT + rowUnits([textUnits("Fly Wing: call"), box("fly_wing"), textUnits("Knife on: call"), box("knife_on")]), (413 - 135) / 0.6],
  ];
  for (const [what, model, measured] of rows) {
    assert.ok(model >= measured && model <= measured * 1.15, `${what}: the model ${Math.round(model)} units, measured ${Math.round(measured)}`);
  }
});

test("every block of every tab ends before Blockly's controls at 390: no row past the 300-unit budget", () => {
  let widest = 0;
  for (const p of PROJECTS) {
    for (const n of p.nodes) {
      for (const t of n.tabs) {
        for (const b of tabToWorkspace(p, { node: n.id, tab: t.name }).blocks.blocks) {
          if (b.type.startsWith("pl_set_")) continue; // the setting blocks: settings.test.ts
          for (const r of rowsOf(b, LABELS, 0, HIDDEN)) {
            widest = Math.max(widest, r.w);
            assert.ok(r.w <= SETTING_ROW_BUDGET, `${p.name} ${n.id}/${t.name}: ${Math.round(r.w)} units: ${r.what}`);
          }
        }
      }
    }
  }
  assert.ok(widest > 250, String(widest)); // the measure measured something
});

test("main's stack at 390: the save point, use_model and the runner on rows; one role a row, its words with its picker", () => {
  const ws = tabToWorkspace(xmasProject(), { node: "xmas_dun02", tab: "main" });
  const rows = rowsOf(ws.blocks.blocks[0], LABELS, 0, HIDDEN).map((r) => r.what);
  for (const want of [
    "pl_save_point: the save point is",
    "pl_save_point: on [MAP]",
    "pl_save_point: x [X] y [Y]",
    "pl_action: [BLOCK]",
    "pl_action: ( [ARGS] )",
    "pl_action: [BADGE]",
    "pl_dungeon_hunt: heal: [HEAL]",
    "pl_dungeon_hunt: Fly Wing: [FLY]",
    "pl_dungeon_hunt: Knife on: [KNIFE_ON]",
    "pl_dungeon_hunt: Knife off: [KNIFE_BACK]",
    "pl_dungeon_hunt: home: [HOME]",
    "pl_dungeon_hunt: died: [RESPAWN]",
    "pl_dungeon_hunt: confirm: [RESPAWN_OK]",
    "pl_dungeon_hunt: eat: [EAT]",
  ]) {
    assert.ok(rows.includes(want), `${want} in ${JSON.stringify(rows)}`);
  }
  // the off-by-one of round 20 is gone: no row holds two roles, none a role's words without it
  assert.ok(!rows.some((r) => /\[[A-Z_]+\].*:/.test(r)), JSON.stringify(rows));
  // the whole stack ends before x 315 at 390 (135 + 300 x 0.6)
  assert.ok(Math.max(...blockRows(ws.blocks.blocks[0], LABELS, 0, HIDDEN)) <= SETTING_ROW_BUDGET);
});

test("the event and the function blocks: one or two fields a row; and / or a block of its terms", () => {
  const ws = tabToWorkspace(xmasProject(), { node: "xmas_dun02", tab: "survival" });
  const fly = ws.blocks.blocks.find((b) => b.fields?.NAME === "fly_away")!;
  assert.equal(fly.inputs?.WHEN?.block?.type, "pl_logic"); // sees_boss() or hp_percent() < 25: two rows
  const rows = rowsOf(fly, LABELS, 0, HIDDEN).map((r) => r.what);
  for (const want of ["pl_event: event [NAME]", "pl_event: class [PRIORITY]", "pl_event: rank [RANK]", "pl_event: mode [MODE]", "pl_event: then [THEN]", "pl_event: pause [COOLDOWN] s after each run", "pl_event: at most [MAX_RUN] a run"]) assert.ok(rows.includes(want), want);
  const recipe = tabToWorkspace(xmasProject(), { node: "xmas_dun02", tab: "monsters" }).blocks.blocks[0];
  assert.deepEqual(rowsOf(recipe, LABELS, 0, HIDDEN).slice(0, 3).map((r) => r.what), ["pl_def: function", "pl_def: [NAME]", "pl_def: ( [PARAMS] )"]);
});

test("round 22: a long expression WRAPS at token boundaries inside the budget; nothing is cut, every line fits", () => {
  // the budget for a top-level event's condition row: the 300 units less its sides, the box, the ends
  assert.equal(EXPR_SHOW_UNITS, SETTING_ROW_BUDGET - G.side - BOX - 2 * ROUND);
  assert.equal(WRAP_UNITS, EXPR_SHOW_UNITS); // the lines stay rows of ONE white box (one field a row)
  assert.deepEqual(wrapExpr("hp_percent() < 50"), ["hp_percent() < 50"]);
  for (const t of ['hotbar_count(key="F6") == 0', 'hotbar_count(key="F7") > 0', "sees_boss() or hp_percent() < 25 or weight_percent() >= 90 and not is_dead()"]) {
    const lines = wrapExpr(t);
    assert.ok(lines.length > 1, t);
    assert.equal(lines.join(" ").replace(/\( /g, "(").replace(/ \)/g, ")"), t, "whole, nothing cut");
    for (const l of lines) assert.ok(textUnits(l) <= WRAP_UNITS, `${l}: ${Math.round(textUnits(l))}`);
    assert.ok(!lines.some((l) => l.includes("…")));
  }
  // the two eat events' conditions no longer read the same (round 21's "hotbar_count(…) == 0" twice)
  assert.notDeepEqual(wrapExpr('hotbar_count(key="F6") == 0'), wrapExpr('hotbar_count(key="F7") == 0'));
  assert.ok(DEF_BY_TYPE.pl_expr.extensions?.includes("pl_expr_wrap"));
});

test("every block definition's messages name each of their args exactly once (a row's end is never lost)", () => {
  for (const d of Object.values(DEF_BY_TYPE)) {
    const r = d as unknown as Record<string, unknown>;
    for (let m = 0; m <= 12; m++) {
      const msg = r[`message${m}`] as string | undefined;
      if (msg === undefined) continue;
      const args = (r[`args${m}`] as unknown[] | undefined) ?? [];
      const refs = [...msg.matchAll(/%([0-9]+)/g)].map((x) => Number(x[1])).sort((a, b) => a - b);
      assert.deepEqual(refs, args.map((_, i) => i + 1), `${d.type} message${m}`);
    }
  }
});

// --- round 23 (live-blocks.md 12.7): the tab's top blocks never overlap ---------------------------
// The reviewer measured f3898e8b's survival tab: drink / fly_away overlapped 78 px at 390 (scale 0.6)
// and 97 at 1440 (0.75), fly_away / bag_full 131 / 164, bag_full / eat_cane 78 / 96 -- 8 fields
// hidden. f3898e8b placed them 710, 710 and 664 units apart, so the blocks are 710 + 130 = 840,
// 710 + 218 = 928 and 664 + 129 = 793 units tall (both widths say the same, within a unit). Node
// cannot draw Blockly (no SVG layout), so these tests use the HEIGHT MODEL (layout.ts blockHeight),
// held to those measured heights; the page stacks with the heights Blockly measures (BlockEditor
// settle), the re-measure list's item.
const MEASURED: Record<string, number> = { drink: 840, fly_away: 928, bag_full: 793 };
const OLD_STEP: Record<string, number> = { drink: 710, fly_away: 710, bag_full: 664 }; // f3898e8b's placement

const ALL: Project[] = [...PROJECTS, ...["project_xmas_dun02.json", "project_sample.json", "project_session.json"].map(fixture)];
const nameOf = (b: { fields?: Record<string, unknown> }) => String(b.fields?.NAME ?? "");
/** A top block's box as placed: a setting block by its own rows (settings.test.ts measures those). */
function placedBoxes(p: Project, node: string, tab: string): TopBox[] {
  return tabToWorkspace(p, { node, tab }).blocks.blocks.map((b, i) => ({
    id: b.id ?? `#${i}`,
    x: b.x ?? 0,
    y: b.y ?? 0,
    w: blockWidth(b, LABELS),
    h: settingOfType(b.type) ? settingHeight(b.type, b.fields) - SETTING_GAP_Y : blockHeight(b, PLACED, HIDDEN),
  }));
}
/** What a placed block is drawn with at first (blocks.ts PLACED_LABELS): its badge, no run line. */
const PLACED = { BADGE: "●" };

test("round 23: the height model gives the survival events the reviewer measured, or a little more (never less)", () => {
  const ws = tabToWorkspace(xmasProject(), { node: "xmas_dun02", tab: "survival" });
  for (const [name, measured] of Object.entries(MEASURED)) {
    const b = ws.blocks.blocks.find((x) => x.type === "pl_event" && nameOf(x) === name);
    assert.ok(b, name);
    const model = blockHeight(b, PLACED, HIDDEN);
    assert.ok(model >= measured && model <= measured * 1.06, `${name}: the model ${model} units, measured ${measured}`);
    console.log(`# ${name}: the model ${model} units, measured ${measured} (+${(((model - measured) / measured) * 100).toFixed(1)} %)`);
  }
});

test("round 23: the positive case -- f3898e8b's placement with the measured heights overlaps exactly as the reviewer saw; this round's does not", () => {
  const ws = tabToWorkspace(xmasProject(), { node: "xmas_dun02", tab: "survival" });
  const ev = ws.blocks.blocks.filter((b) => b.type === "pl_event");
  assert.deepEqual(ev.slice(0, 4).map(nameOf), ["drink", "fly_away", "bag_full", "eat_cane"]);
  for (let i = 0; i < 3; i++) {
    const name = nameOf(ev[i]);
    const old = { id: "a", x: 20, y: 0, w: 300, h: MEASURED[name] };
    assert.ok(overlaps(old, { id: "b", x: 20, y: OLD_STEP[name], w: 300, h: 100 }), `${name}: the old step overlaps`);
    // the reviewer's px at 390 (scale 0.6) and 1440 (0.75), within a pixel
    assert.ok(Math.abs((MEASURED[name] - OLD_STEP[name]) * 0.6 - [78, 131, 78][i]) <= 1, name);
    assert.ok(Math.abs((MEASURED[name] - OLD_STEP[name]) * 0.75 - [97, 164, 96][i]) <= 1.5, name);
    // this round: the next block starts below the measured bottom, the gap or more apart
    const gap = (ev[i + 1].y ?? 0) - (ev[i].y ?? 0) - MEASURED[name];
    assert.ok(gap >= STACK_GAP, `${name} -> ${nameOf(ev[i + 1])}: ${gap} units apart`);
  }
});

test("round 23: no two top blocks of any tab overlap as placed -- every tab of the ready-made and the FROZEN projects", () => {
  let tabs = 0;
  for (const p of ALL) {
    for (const n of p.nodes) {
      for (const t of n.tabs) {
        const boxes = placedBoxes(p, n.id, t.name);
        for (let i = 0; i < boxes.length; i++) {
          for (let j = i + 1; j < boxes.length; j++) assert.ok(!overlaps(boxes[i], boxes[j]), `${p.name} ${n.id}/${t.name}: ${boxes[i].id} and ${boxes[j].id}`);
        }
        // in their order, top to bottom (the converter reads them so: the project never changes)
        assert.deepEqual(boxes.map((b) => b.y), [...boxes.map((b) => b.y)].sort((a, c) => a - c));
        tabs++;
      }
    }
  }
  assert.ok(tabs > 30, String(tabs));
});

test("round 23: stackTops packs a tab from its top, pushes only down, keeps the order and the columns", () => {
  const box = (id: string, y: number, h: number, x = 20, w = 300): TopBox => ({ id, x, y, w, h });
  // the survival tab as f3898e8b placed it, with the measured heights: packed, nothing overlaps
  const tab = [box("drink", 90, 840), box("fly_away", 800, 928), box("bag_full", 1510, 793), box("eat_cane", 2174, 600)];
  const packed = stackTops(tab, "pack", STACK_GAP, 90);
  const at = tab.map((b) => ({ ...b, y: packed.get(b.id) ?? b.y }));
  assert.deepEqual(at.map((b) => b.y), [90, 954, 1906, 2723]);
  for (let i = 1; i < at.length; i++) assert.ok(!overlaps(at[i - 1], at[i]));
  // push: a block that grew pushes the ones under it, never pulls them up; one far enough stays
  const grown = stackTops([box("a", 90, 500), box("b", 400, 100), box("c", 2000, 100)], "push", STACK_GAP, 90);
  assert.deepEqual([...grown], [["b", 614]]);
  assert.equal(stackTops([box("a", 90, 100), box("b", 900, 100)], "push", STACK_GAP, 90).size, 0); // a shrink moves nothing
  // a block BESIDE the grown one (another column) stays; the order by y is kept (ties by x)
  const cols = stackTops([box("a", 90, 500, 20, 300), box("b", 200, 100, 400, 200), box("c", 300, 100, 20, 300)], "push", STACK_GAP, 90);
  assert.equal(cols.get("b"), undefined);
  assert.equal(cols.get("c"), 614);
});
