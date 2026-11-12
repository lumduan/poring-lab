// Runner flows (lib/flow/runner.ts, 2026-11-12): the generated description of dungeon_hunt.py's
// xmas_dun02 Rogue is well formed, its blocks load in the REAL Blockly 13 (headless, in node) fixed
// in place with empty context menus, its words wrap without splitting a number, and the Python the
// code view marks belongs to the block that was clicked.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import type * as BlocklyT from "blockly/core";

import { registerRunner, runnerThemes } from "../../components/flows/blockly-runner.ts";
import { allNodes, blockType, checkDoc, commandPieces, findNode, markOf, message, nodeAtLine, RUNNER_STYLES, type RunnerDoc, type RunnerPart, runnerDefs, runnerWorkspace, textOf, wrapParts } from "./runner.ts";
import { findRunner, RUNNERS, runnerForMap, runnerHref } from "./runners/index.ts";
import { XMAS_DUN02_ROGUE as DOC } from "./runners/xmas_dun02_rogue.gen.ts";
import { BLOCK_STYLES, contrast } from "./theme.ts";

const require = createRequire(import.meta.url);
const lib = (p: string) => fileURLToPath(new URL(`../../../node_modules/blockly/${p}`, import.meta.url));
const B = require(lib("blockly_compressed.js")) as typeof BlocklyT;
B.setLocale(require(lib("msg/en.js")) as Record<string, string>);

const STYLES = { ...BLOCK_STYLES, ...RUNNER_STYLES };
const pyLines = DOC.python.replace(/\n$/, "").split("\n");

test("the committed description is well formed (styles, lines, numbers, flags)", () => {
  assert.deepEqual(checkDoc(DOC, STYLES), []);
  assert.equal(DOC.description_only, true);
  assert.equal(DOC.map, "xmas_dun02");
  assert.deepEqual(
    DOC.stacks.map((s) => s.id),
    ["run", "safety_rules", "knife_opener"],
  );
  assert.ok(DOC.stacks.every((s) => s.kind === "hat"));
});

test("a broken description is refused with its reasons", () => {
  const bad = structuredClone(DOC) as RunnerDoc;
  bad.stacks[0].lines = [1, pyLines.length + 5];
  bad.stacks[0].style = "no_such_style";
  bad.stacks[0].params = ["NO_SUCH_NUMBER"];
  const errs = checkDoc(bad, STYLES);
  assert.ok(errs.some((e) => e.includes("outside the Python")));
  assert.ok(errs.some((e) => e.includes("unknown style")));
  assert.ok(errs.some((e) => e.includes("NO_SUCH_NUMBER")));
});

test("the runner styles are readable with white text, and their hats get the cap", () => {
  for (const [name, s] of Object.entries(RUNNER_STYLES)) assert.ok(contrast(s.colourPrimary, "#ffffff") >= 4.5, name);
  assert.equal(RUNNER_STYLES.rd_safety_hat_blocks.hat, "cap");
  assert.equal(RUNNER_STYLES.rd_optional_hat_blocks.hat, "cap");
});

test("the numbers are the code's: each constant in the Python outline carries the doc's value", () => {
  for (const [id, p] of Object.entries(DOC.params)) {
    const name = id.split(".").pop() ?? id;
    if (!/^[A-Z][A-Z0-9_]+$/.test(name) || id.startsWith("PATROL_START")) continue;
    const line = pyLines.find((l) => l.startsWith(`${name} = `));
    assert.ok(line, `${name} is defined in the outline`);
    const literal = line.slice(name.length + 3).split("  #")[0];
    assert.deepEqual(JSON.parse(literal), p.value, name); // a number or a double-quoted string
  }
  // a block's words show the code's numbers: the kill gap's block names KILL_GAP_HITS and KILL_GAP_S
  const kill = findNode(DOC, "killgap");
  assert.ok(kill?.branches);
  const shown = kill.branches[0].parts.filter((p): p is { param: string; shown: string } => "param" in p);
  assert.deepEqual(
    shown.map((p) => p.param),
    ["KILL_GAP_HITS", "KILL_GAP_S"],
  );
  assert.deepEqual(
    shown.map((p) => p.shown),
    [String(DOC.params.KILL_GAP_HITS.value), String(DOC.params.KILL_GAP_S.value)],
  );
  // a share is shown as a percent: the potion rule's 0.4 reads "40"
  const potion = findNode(DOC, "potion");
  const pp = potion?.branches?.[0].parts.find((p) => "param" in p && p.param === "strategy.potion_below");
  assert.ok(pp && "shown" in pp);
  assert.equal(pp.shown, String(Math.round(Number(DOC.params["strategy.potion_below"].value) * 100)));
});

test("every flag of the base command is described with the code's own help text", () => {
  for (const f of DOC.command.base.filter((t) => t.startsWith("--"))) {
    const fl = DOC.flags[f];
    assert.ok(fl, f);
    assert.equal(fl.base, true, f);
    // --strategy and --minutes have no help= in the code (choices / a number): shown as they are
    if (!["--strategy", "--minutes"].includes(f)) assert.ok(fl.help && fl.help.length > 10, `${f} has its help`);
  }
  for (const f of DOC.command.optional.flatMap((o) => o.flags).filter((t) => t.startsWith("--"))) assert.equal(DOC.flags[f]?.base, false, f);
  // the base's value-target and the boss guard's confirmation are there, as Batt decided them
  assert.equal(DOC.flags["--value-target"].value, true);
  assert.equal(DOC.flags["--garm-confirm"].value, 2);
  assert.deepEqual(commandPieces(["--char", "rogue", "--hud", "--minutes", "25"]), ["--char rogue", "--hud", "--minutes 25"]);
});

test("the Python mark of a block is its own lines; a line finds its innermost block", () => {
  for (const n of allNodes(DOC)) {
    const [a, b] = markOf(n);
    assert.ok(a >= 1 && a <= b && b <= pyLines.length, n.id);
  }
  const run = findNode(DOC, "run");
  assert.ok(run);
  assert.equal(pyLines[markOf(run)[0] - 1], "def run():"); // a hat marks its header, not the whole stack
  const kill = findNode(DOC, "kill");
  assert.ok(kill);
  assert.match(pyLines[kill.lines[0] - 1], /kills\.append\(now\)/);
  assert.equal(nodeAtLine(DOC, kill.lines[0])?.id, "kill");
  const gap = findNode(DOC, "killgap");
  assert.ok(gap);
  assert.match(pyLines[gap.head[0] - 1], /kill_gapped\(/);
  assert.equal(nodeAtLine(DOC, gap.head[0])?.id, "killgap");
});

test("words wrap into rows without splitting a number, and keep every word", () => {
  const parts: RunnerPart[] = [{ text: "HP under " }, { param: "a", shown: "40" }, { text: " %, or falling " }, { param: "b", shown: "150" }, { text: " HP/s under " }, { param: "c", shown: "50" }, { text: " %: escape" }];
  const rows = wrapParts(parts, 20);
  assert.ok(rows.length > 1);
  assert.equal(rows.map(textOf).join("").replace(/\s+/g, " "), textOf(parts).replace(/\s+/g, " "));
  for (const r of rows) assert.ok(r.filter((p) => "param" in p).every((p) => ["40", "150", "50"].includes((p as { shown: string }).shown)));
  assert.deepEqual(wrapParts([{ text: "one row" }]), [[{ text: "one row" }]]);
});

test("a row becomes a Blockly message: numbers are pills, % is escaped, no reference runs into a digit", () => {
  const c = { n: 0 };
  const m = message([{ text: "HP under " }, { param: "a", shown: "40" }, { text: " % now" }], c);
  assert.equal(m.message, "HP under %1 %% now");
  assert.deepEqual(m.args, [{ type: "field_input", name: "P0", text: "40" }]);
  const m2 = message([{ param: "x", shown: "5" }, { text: "0 times" }], c);
  assert.equal(m2.message, "%1 0 times"); // never "%10"
  assert.equal(m2.args[0].name, "P1"); // field names stay unique across a block's rows
});

test("the runner blocks load in the real Blockly, fixed in place, nested as the description says", () => {
  registerRunner(B, DOC);
  registerRunner(B, DOC); // a second time is a no-op
  const ws = new B.Workspace();
  B.serialization.workspaces.load(runnerWorkspace(DOC) as unknown as object, ws);
  const nodes = allNodes(DOC);
  assert.equal(ws.getAllBlocks(false).length, nodes.length);
  assert.deepEqual(
    ws
      .getTopBlocks(false)
      .map((b) => b.id)
      .sort(),
    ["knife_opener", "run", "safety_rules"],
  );
  for (const n of nodes) {
    const b = ws.getBlockById(n.id);
    assert.ok(b, n.id);
    assert.equal(b.type, blockType(DOC, n));
    assert.equal(b.isMovable(), false, n.id);
    assert.equal(b.isDeletable(), false, n.id);
    assert.equal(b.isEditable(), false, n.id);
    const menu: unknown[] = [1, 2, 3];
    (b as unknown as { customContextMenu?: (o: unknown[]) => void }).customContextMenu?.(menu);
    assert.equal(menu.length, 0, `${n.id}: an empty context menu`);
  }
  // nesting: the kill inside the kill-gap rule, the rule inside "locked", the loop inside the run's stack
  assert.equal(ws.getBlockById("kill")?.getSurroundParent()?.id, "killgap");
  assert.equal(ws.getBlockById("killgap")?.getSurroundParent()?.id, "locked");
  assert.equal(ws.getBlockById("look")?.getSurroundParent()?.id, "loop");
  assert.equal(ws.getBlockById("loop")?.getRootBlock().id, "run");
  assert.equal(ws.getBlockById("potion")?.getRootBlock().id, "safety_rules");
  // a number is a pill showing the code's value
  assert.equal(ws.getBlockById("identity")?.getFieldValue("P0"), String(DOC.params["cmd.char"].value));
  ws.dispose();
});

test("the definitions are one per block, and the themes carry the runner styles", () => {
  const defs = runnerDefs(DOC);
  assert.equal(new Set(defs.map((d) => d.type)).size, allNodes(DOC).length);
  const th = runnerThemes(B);
  for (const t of [th.light, th.dark]) for (const name of Object.keys(RUNNER_STYLES)) assert.ok((t as unknown as { blockStyles: Record<string, unknown> }).blockStyles[name], name);
});

test("a runner flow is found by its id or its map; its link opens /flows", () => {
  assert.equal(RUNNERS.length >= 1, true);
  assert.equal(findRunner("xmas_dun02_rogue")?.id, "xmas_dun02_rogue");
  assert.equal(findRunner("xmas_dun02")?.id, "xmas_dun02_rogue");
  assert.equal(findRunner("prt_fild08"), null);
  assert.equal(findRunner(null), null);
  assert.equal(runnerForMap("xmas_dun02")?.id, "xmas_dun02_rogue");
  assert.equal(runnerForMap(undefined), null);
  assert.equal(runnerHref(DOC), "/flows?runner=xmas_dun02_rogue");
});
