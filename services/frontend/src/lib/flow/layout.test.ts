// Round 21 (the re-measure of round 20, live-blocks.md 12.5): every block of every tab of the
// ready-made projects and the frozen A/B arms ends before Blockly's controls at 390 px, by the
// model of zelos' rows (layout.ts) -- the reviewer's own re-measure of main is its positive case.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { DEF_BY_TYPE, titleLines } from "./blockdefs.ts";
import { BADGE_TEXT } from "./api.ts";
import { placedIds, SETTING_GAP_Y, settingHeight, shelfItems, TAB_TOP_Y, tabFromWorkspace, tabToWorkspace, type Workspace } from "./blocks.ts";
import { canonical } from "./ir.ts";
import { BOX, blockHeight, blockRows, blockWidth, INDENT, layoutKey, overlaps, pushGrown, ROUND, rowsOf, SHELF_LEFT, shelfWidth, STACK_GAP, stackTops, type TopBox, WIDEST_BADGE } from "./layout.ts";
import { checkBody, projectRunBody } from "./liverun.ts";
import { EXPR_SHOW_UNITS, WRAP_UNITS, wrapExpr } from "./pickers.ts";
import { engineKey, forEngine, nodeById, type Project, sampleProject, tabOf, xmasFunctionsProject, xmasHuntProject, xmasProject } from "./project.ts";
import { exportProject, importProject } from "./projectfile.ts";
import { rowUnits, SETTING_BY_NAME, SETTING_GEOMETRY as G, SETTING_ROW_BUDGET, settingOfType, settingType, textUnits } from "./settings.ts";
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

// --- round 25 (live-blocks.md 12.9): remembered positions, left to right ---------------------------
// The shelf's widths: at 390 the canvas holds 313 units beside the toolbox and before Blockly's
// controls (settings.ts SETTING_ROW_BUDGET's measure); at 1440 the canvas beside the Python pane
// (studio.css .studio-side: 30vw = 432 px) and the toolbox (~150 px) is ~858 px at scale 0.75.
const W390 = 313;
const W1440 = shelfWidth(1440 - 432 - 150, 0.75);
const WIDTHS = [W390, 600, W1440, shelfWidth(1440 - 150, 0.75), 2400];

/** The top blocks of a tab as the shelf placed them, each with the box the shelf reserved. */
function shelfBoxes(p: Project, node: string, tab: string, width: number): TopBox[] {
  const ws = tabToWorkspace(p, { node, tab }, { width });
  const items = shelfItems(ws.blocks.blocks, tabOf(nodeById(p, node)!, tab));
  return ws.blocks.blocks.map((b, i) => ({ id: b.id ?? `#${i}`, x: b.x ?? 0, y: b.y ?? 0, w: items[i].w, h: items[i].h }));
}

test("round 25: a top block's key -- main, def:<name> (functions and events), var:<name> (variables and settings); none for a nameless or loose block", () => {
  assert.equal(layoutKey("pl_main", {}), "main");
  assert.equal(layoutKey("pl_def", { NAME: "heal" }), "def:heal");
  assert.equal(layoutKey("pl_event", { NAME: "drink" }), "def:drink");
  assert.equal(layoutKey("pl_vardecl", { NAME: "minutes" }), "var:minutes");
  assert.equal(layoutKey(settingType(SETTING_BY_NAME.get("END_HOT_S")!), { VALUE: 3.5 }), "var:END_HOT_S");
  assert.equal(layoutKey("pl_def", { NAME: "?" }), null);
  assert.equal(layoutKey("pl_press_key", { KEY: "F1" }), null);
  // every key the shelf can make is one the engine's model accepts (project.py LAYOUT_KEY)
  const engine = /^(main|(def|var):[A-Za-z][A-Za-z0-9_]{0,47})$/;
  for (const p of ALL) for (const n of p.nodes) for (const t of n.tabs) for (const b of tabToWorkspace(p, { node: n.id, tab: t.name }).blocks.blocks) {
    const k = layoutKey(b.type, b.fields);
    assert.ok(k && engine.test(k), `${p.name} ${n.id}/${t.name}: ${b.type} -> ${k}`);
  }
  // the shelf leaves room for the widest badge there is
  const widest = Math.max(...Object.values(BADGE_TEXT).map((t) => textUnits(`● ${t}`)));
  assert.equal(textUnits(WIDEST_BADGE), widest);
});

test("round 25: LEFT TO RIGHT while the blocks fit -- the monsters tab's four recipes in one row at 1440, one column at 390", () => {
  const p = xmasProject();
  const at1440 = shelfBoxes(p, "xmas_dun02", "monsters", W1440);
  const firstRow = at1440.filter((b) => b.y === TAB_TOP_Y);
  assert.ok(firstRow.length >= 3, `${at1440.map((b) => `${b.x},${b.y}`).join(" ")}`);
  assert.deepEqual(firstRow.map((b) => b.x), [...firstRow.map((b) => b.x)].sort((a, c) => a - c)); // in their order
  const wide = shelfBoxes(p, "xmas_dun02", "monsters", shelfWidth(1440 - 150, 0.75)); // the Python pane closed
  assert.equal(wide.filter((b) => b.y === TAB_TOP_Y).length, 4);
  const at390 = shelfBoxes(p, "xmas_dun02", "monsters", W390);
  assert.ok(at390.every((b) => b.x === SHELF_LEFT), "a phone stays one column");
  // no width: round 23's list, one column, the same places as before
  assert.deepEqual(shelfBoxes(p, "xmas_dun02", "survival", 0).map((b) => b.x), shelfBoxes(p, "xmas_dun02", "survival", W390).map((b) => b.x));
});

test("round 25: no two top blocks overlap and none passes the canvas's edge -- every tab of the ready-made and the FROZEN projects, 390 to 2400", () => {
  let tabs = 0;
  for (const width of WIDTHS) {
    for (const p of ALL) {
      for (const n of p.nodes) {
        for (const t of n.tabs) {
          const boxes = shelfBoxes(p, n.id, t.name, width);
          for (let i = 0; i < boxes.length; i++) {
            const a = boxes[i];
            assert.ok(a.x === SHELF_LEFT || a.x + a.w <= SHELF_LEFT + width, `${width}: ${p.name} ${n.id}/${t.name}: ${a.id} past the edge`);
            for (let j = i + 1; j < boxes.length; j++) {
              const c = boxes[j];
              const apart = { ...c, x: c.x - STACK_GAP + 1, y: c.y - STACK_GAP + 1, w: c.w + 2 * STACK_GAP - 2, h: c.h + 2 * STACK_GAP - 2 };
              assert.ok(!overlaps(a, apart), `${width}: ${p.name} ${n.id}/${t.name}: ${a.id} and ${c.id} closer than ${STACK_GAP}`);
            }
          }
          tabs++;
        }
      }
    }
  }
  assert.ok(tabs > 150, String(tabs));
});

test("round 25: a REMEMBERED place wins -- the block where the person put it, the others left to right around it", () => {
  const p = xmasProject();
  const n = nodeById(p, "xmas_dun02")!;
  const t = tabOf(n, "monsters")!;
  t.layout = { "def:attack_cookie": [700, 900] };
  const boxes = shelfBoxes(p, "xmas_dun02", "monsters", W1440);
  const ws = tabToWorkspace(p, { node: "xmas_dun02", tab: "monsters" }, { width: W1440 });
  const i = ws.blocks.blocks.findIndex((b) => b.fields?.NAME === "attack_cookie");
  assert.deepEqual([boxes[i].x, boxes[i].y], [700, 900]);
  for (const [j, b] of boxes.entries()) if (j !== i) assert.ok(!overlaps(b, boxes[i]), b.id);
  assert.deepEqual([...placedIds(ws, t)], [ws.blocks.blocks[i].id]);
});

test("round 25: where the blocks are never changes the ENGINE's project -- every tab, every position, any order; the layout keeps only the placed blocks", () => {
  let seed = 7;
  const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31) * 3000;
  for (const p of ALL) {
    for (const n of p.nodes) {
      for (const t of n.tabs) {
        const scope = { node: n.id, tab: t.name };
        const ws = JSON.parse(JSON.stringify(tabToWorkspace(p, scope, { width: W1440 }))) as Workspace;
        for (const b of ws.blocks.blocks) [b.x, b.y] = [Math.round(rnd()), Math.round(rnd())];
        ws.blocks.blocks.reverse(); // Blockly's own order of top blocks, whatever it is
        const all = new Set(ws.blocks.blocks.map((b) => b.id ?? ""));
        const back = tabFromWorkspace(p, scope, ws, {}, all);
        assert.ok(back.ok, `${p.name} ${n.id}/${t.name}: ${back.ok ? "" : back.errors.join(" | ")}`);
        assert.equal(engineKey(back.project), engineKey(p), `${p.name} ${n.id}/${t.name}: the engine's project changed`);
        const lay = tabOf(nodeById(back.project, n.id)!, t.name)!.layout ?? {};
        assert.equal(Object.keys(lay).length, ws.blocks.blocks.length);
        // nothing placed: no layout at all (the JSON as before)
        const none = tabFromWorkspace(p, scope, ws, {}, new Set());
        assert.ok(none.ok && tabOf(nodeById(none.project, n.id)!, t.name)!.layout === undefined);
        assert.equal(canonical(none.ok ? none.project : null), canonical(p), `${p.name} ${n.id}/${t.name}`);
      }
    }
  }
});

test("round 25: the layout follows a rename, and without `placed` the blocks the layout had keep theirs (at where they are now)", () => {
  const p = xmasProject();
  const scope = { node: "xmas_dun02", tab: "keys" };
  const ws = JSON.parse(JSON.stringify(tabToWorkspace(p, scope))) as Workspace;
  const heal = ws.blocks.blocks.find((b) => b.fields?.NAME === "heal")!;
  [heal.x, heal.y] = [640.4, 120.6];
  heal.fields = { ...heal.fields, NAME: "drink_potion" };
  const r = tabFromWorkspace(p, scope, ws, {}, new Set([heal.id!]));
  assert.ok(r.ok);
  const q = r.project;
  assert.deepEqual(tabOf(nodeById(q, "xmas_dun02")!, "keys")!.layout, { "def:drink_potion": [640, 121] });
  // the next conversion, from the project that has the layout, with no `placed` (another caller)
  const ws2 = JSON.parse(JSON.stringify(tabToWorkspace(q, scope))) as Workspace;
  const moved = ws2.blocks.blocks.find((b) => b.fields?.NAME === "drink_potion")!;
  assert.deepEqual([moved.x, moved.y], [640, 121]); // where it was put
  moved.y = 300;
  const r2 = tabFromWorkspace(q, scope, ws2);
  assert.ok(r2.ok);
  assert.deepEqual(tabOf(nodeById(r2.project, "xmas_dun02")!, "keys")!.layout, { "def:drink_potion": [640, 300] });
  // the file keeps it; the engine never gets it
  const back = importProject(exportProject(r2.project));
  assert.ok(back.ok && canonical(back.project) === canonical(r2.project));
  assert.equal(JSON.stringify(forEngine(r2.project)).includes('"layout"'), false);
  assert.equal(projectRunBody(r2.project, "xmas_dun02").project.nodes.some((n) => n.tabs.some((t) => "layout" in t)), false);
  assert.equal(checkBody(r2.project, "xmas_dun02").project.nodes.some((n) => n.tabs.some((t) => "layout" in t)), false);
  assert.equal(engineKey(r2.project), engineKey(q)); // moving it again is no new engine project
});

test("round 25: a block that GROWS pushes only what it now reaches; a person's own overlapping drop and a block beside it stay", () => {
  const box = (id: string, x: number, y: number, w: number, h: number): TopBox => ({ id, x, y, w, h });
  const prev = (bs: TopBox[], grow: Record<string, { w: number; h: number }>) => new Map(bs.map((b) => [b.id, grow[b.id] ?? { w: b.w, h: b.h }]));
  // a grew from 300 to 500 tall: b (under it, 24 apart) goes down and pushes c; d beside a stays
  const bs = [box("a", 20, 90, 300, 500), box("b", 20, 414, 300, 200), box("c", 20, 638, 300, 100), box("d", 344, 90, 300, 900)];
  const m = pushGrown(bs, prev(bs, { a: { w: 300, h: 300 } }), STACK_GAP);
  assert.deepEqual(Object.fromEntries(m), { b: [20, 614], c: [20, 838] });
  // e was dropped ONTO a by a person (it overlapped before): it stays where it was dropped
  const drop = [box("a", 20, 90, 300, 500), box("e", 60, 200, 300, 200)];
  assert.equal(pushGrown(drop, prev(drop, { a: { w: 300, h: 300 } }), STACK_GAP).size, 0);
  // nothing grew (a shrink, a move): nothing moves
  assert.equal(pushGrown(bs, prev(bs, { a: { w: 300, h: 700 } }), STACK_GAP).size, 0);
  // a grew WIDER (a badge arrived): the block right of it in its row moves right, the gap kept
  const row = [box("a", 20, 90, 360, 300), box("b", 344, 90, 300, 300), box("c", 668, 90, 300, 300)];
  assert.deepEqual(Object.fromEntries(pushGrown(row, prev(row, { a: { w: 300, h: 300 } }), STACK_GAP)), { b: [404, 90], c: [728, 90] });
});
