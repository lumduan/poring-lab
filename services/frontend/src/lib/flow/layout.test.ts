// Round 21 (the re-measure of round 20, live-blocks.md 12.5): every block of every tab of the
// ready-made projects and the frozen A/B arms ends before Blockly's controls at 390 px, by the
// model of zelos' rows (layout.ts) -- the reviewer's own re-measure of main is its positive case.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { DEF_BY_TYPE, titleLines } from "./blockdefs.ts";
import { tabToWorkspace } from "./blocks.ts";
import { BOX, blockRows, INDENT, ROUND, rowsOf } from "./layout.ts";
import { EXPR_SHOW_UNITS, shortExpr } from "./pickers.ts";
import { type Project, sampleProject, xmasProject } from "./project.ts";
import { rowUnits, SETTING_GEOMETRY as G, SETTING_ROW_BUDGET, textUnits } from "./settings.ts";
import { sessionProject } from "./testkit.ts";

const fixture = (name: string): Project => JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8")) as Project;
const PROJECTS: Project[] = [xmasProject(), sampleProject(), sessionProject(), ...["project_xmas_dun02_stage2.json", "project_xmas_dun02_stage3.json", "project_xmas_dun02_stage4.json"].map(fixture)];
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

test("a long expression shows shortened on a phone only where it would pass the budget; its head and tail kept", () => {
  // the budget for a top-level event's condition row: the 300 units less its sides, the box, the ends
  assert.equal(EXPR_SHOW_UNITS, SETTING_ROW_BUDGET - G.side - BOX - 2 * ROUND);
  assert.equal(shortExpr("hp_percent() < 50"), "hp_percent() < 50");
  const s = shortExpr('hotbar_count(key="F6") == 0');
  assert.ok(s.startsWith("hotbar_count(") && s.includes("…") && s.endsWith(" == 0"), s);
  assert.ok(textUnits(s) <= EXPR_SHOW_UNITS);
  assert.ok(DEF_BY_TYPE.pl_expr); // (the pl_expr field is an expression picker: blockly_pickers.test.ts)
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
