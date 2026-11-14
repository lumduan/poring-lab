// The Maps page's edits of the PROJECT (edit.ts): the session connections (one path), the exits
// drawn and deleted, nodes moved, renamed and deleted, a map node's own fields; and what a node
// says (nodewords.ts: its tabs, names and overrides, its lint).
import assert from "node:assert/strict";
import { test } from "node:test";

import type { LintDoc } from "../flow/api.ts";
import { def, globalOf, nodeById, pressKey, type Project, sampleProject, sessionPath, tab, xmasProject } from "../flow/project.ts";
import { sessionProject } from "../flow/testkit.ts";
import { connectExit, connectSession, exitsInto, moveNodes, removeExit, removeNode, removeSession, renameNode, renameProblem, sessionLinkProblem, setStart, setZones, updateMapNode } from "./edit.ts";
import { exitRows, nodeLinks } from "./links.ts";
import { addMapNode } from "./build.ts";
import { bySeverity, cappedFindings, findingWhere, lintGroups, nodeLint, nodeTitle, runnerSpecies, SEVERITY_WORDS, tabRows, tabSummary } from "./nodewords.ts";
import { readRules, ruleMaps, setUnknownMap } from "./rules.ts";

const ok = (r: { ok: true; project: Project } | { ok: false; error: string }): Project => {
  assert.ok(r.ok, r.ok ? "" : r.error);
  return r.project;
};

test("the session path is ONE path: login -> character -> a map's entry, a new connection replaces the old", () => {
  const p = sampleProject();
  assert.match(sessionLinkProblem(p, "login", "town") ?? "", /connects to a choose-character node/);
  assert.match(sessionLinkProblem(p, "character", "login") ?? "", /connects to a map node/);
  assert.match(sessionLinkProblem(p, "town", "field") ?? "", /EXITS/);
  assert.match(sessionLinkProblem(p, "global", "town") ?? "", /Global has no connections/);
  assert.match(sessionLinkProblem(p, "character", "field", "nowhere") ?? "", /no entry nowhere/);
  const q = ok(connectSession(p, "character", "field"));
  assert.deepEqual(q.edges, [{ from: "login", to: "character" }, { from: "character", to: "field", entry: "arrival" }]);
  assert.equal(sessionPath(q).map?.id, "field");
  const r = ok(removeSession(q, "character", "field"));
  assert.match(sessionPath(r).problems[0], /not connected to a map/);
  assert.equal(removeSession(r, "character", "field").ok, false);
  assert.deepEqual(p.edges, sampleProject().edges, "pure");
});

test("START: a map node (she stands on it) or a login node; never Global or a character node", () => {
  const p = sessionProject();
  const q = ok(setStart(p, "xmas_dun02"));
  assert.equal(q.start, "xmas_dun02");
  assert.equal(p.start, "login", "the old project is untouched");
  assert.equal(sessionPath(q).map?.id, "xmas_dun02");
  assert.equal(sessionPath(q).login, null);
  assert.equal(ok(setStart(q, "login")).start, "login");
  assert.match((setStart(p, "global") as { error: string }).error, /map node .* or on a login node, not on the Global node/);
  assert.match((setStart(p, "character") as { error: string }).error, /not on the choose-character node/);
  assert.match((setStart(p, "nowhere") as { error: string }).error, /no node nowhere/);
  // a rename follows the start (the one box)
  assert.equal(ok(renameNode(xmasProject(), "xmas_dun02", "dun")).start, "dun");
});

test("an exit drawn onto another map is a take_exit with placeholders; deleting it removes its statement", () => {
  const p = ok(connectExit(sampleProject(), "field", "walk_exit", "town"));
  const rows = exitRows(p, nodeById(p, "field")!);
  assert.deepEqual(rows.map((r) => [r.path, r.kind, r.toNode, r.toEntry]), [["field/main/main.1", "item_warp", "town", "spawn"], ["field/main/main.2", "walk_exit", "town", "spawn"]]);
  assert.equal(connectExit(p, "login", "walk_exit", "town").ok, false);
  const q = ok(removeExit(p, "field/main/main.2"));
  assert.deepEqual(q, sampleProject());
  assert.equal(removeExit(q, "field/main/main.0").ok, false, "not an exit");
  assert.equal(removeExit(q, "nowhere/main/main.0").ok, false);
  // a new map's "stop at once" is replaced by its first exit
  const r = sampleProject();
  r.nodes.push({ ...structuredClone(nodeById(r, "field")!), id: "cave", tabs: [{ name: "main", main: [{ kind: "stop", reason: "done" }], defs: [], vars: {} }] } as never);
  const s = ok(connectExit(r, "cave", "item_warp", "town"));
  assert.deepEqual(nodeById(s, "cave")!.tabs[0].main!.map((x) => x.kind), ["take_exit"]);
  assert.deepEqual(nodeById(ok(removeExit(s, "cave/main/main.0")), "cave")!.tabs[0].main, [{ kind: "stop", reason: "done" }], "a main keeps one statement");
});

test("moving nodes saves whole positions; nothing moved is the same project", () => {
  const p = sampleProject();
  const q = moveNodes(p, { town: { x: 600.6, y: 10.2 }, nowhere: { x: 1, y: 1 }, field: { x: NaN, y: 0 } });
  assert.deepEqual(nodeById(q, "town")!.pos, { x: 601, y: 10 });
  assert.deepEqual(nodeById(q, "field")!.pos, nodeById(p, "field")!.pos);
  assert.equal(moveNodes(p, { town: { ...nodeById(p, "town")!.pos } }), p);
});

test("a rename follows the connections, the start and every exit that names it", () => {
  const p = ok(renameNode(sampleProject(), "town", "home_town"));
  assert.deepEqual(p.edges.at(-1), { from: "character", to: "home_town", entry: "spawn" });
  assert.equal(exitRows(p, nodeById(p, "field")!)[0].toNode, "home_town");
  const q = ok(renameNode(p, "login", "sign_in"));
  assert.equal(q.start, "sign_in");
  assert.deepEqual(q.edges[0], { from: "sign_in", to: "character" });
  assert.match(renameProblem(q, "global", "shared") ?? "", /Global's id/);
  assert.match(renameProblem(q, "field", "global") ?? "", /Global node's id/);
  assert.match(renameProblem(q, "field", "home_town") ?? "", /exists/);
  assert.match(renameProblem(q, "field", "9lives") ?? "", /letters/);
  assert.equal(ok(renameNode(q, "field", "field")), q);
});

test("deleting: map nodes only, with their connections; exits into it are kept and counted", () => {
  const p = sampleProject();
  assert.match((removeNode(p, "login") as { error: string }).error, /stays/);
  assert.match((removeNode(p, "global") as { error: string }).error, /shared by every node/);
  assert.deepEqual(exitsInto(p, "town"), ["field"]);
  const r = removeNode(p, "town");
  assert.ok(r.ok);
  assert.equal(r.dangling, 1);
  assert.deepEqual(r.project.edges, [{ from: "login", to: "character" }]);
  assert.deepEqual(nodeLinks(r.project, "field")?.exits.map((x) => x.toMap), [null], "named, not hidden");
  // the unknown-map rule's maps follow
  const on = ok(setUnknownMap(p, "wing"));
  assert.deepEqual(ruleMaps(ok(removeNode(on, "field"))), ["town_1"]);
});

test("a map node's own fields: checked, an entry renamed in place is followed", () => {
  const p = sampleProject();
  const town = nodeById(p, "town")!;
  assert.ok(town.kind === "map");
  const v = { map: town.map, entries: [{ name: "plaza", at: { kind: "cell" as const, map: "town_1", x: 40, y: 40 }, radius: 3 }], targets: [], ignore: [{ kind: "mob" as const, id: 9109 }], resume_here: false };
  const q = ok(updateMapNode(p, "town", v));
  const t = nodeById(q, "town")!;
  assert.ok(t.kind === "map");
  assert.deepEqual([t.entries[0].name, t.entries[0].radius, t.ignore, t.resume_here], ["plaza", 3, [{ kind: "mob", id: 9109 }], false]);
  assert.deepEqual(q.edges.at(-1), { from: "character", to: "town", entry: "plaza" });
  assert.equal(exitRows(q, nodeById(q, "field")!)[0].toEntry, "plaza");
  assert.match((updateMapNode(p, "town", { ...v, entries: [] }) as { error: string }).error, /at least one entry/);
  assert.match((updateMapNode(p, "town", { ...v, entries: [v.entries[0], v.entries[0]] }) as { error: string }).error, /two entries/);
  assert.match((updateMapNode(p, "town", { ...v, map: { kind: "map", map: "no spaces" } }) as { error: string }).error, /not a map id/);
  assert.match((updateMapNode(p, "town", { ...v, targets: [{ kind: "mob", id: -3 }] }) as { error: string }).error, /monster id/);
  assert.equal(updateMapNode(p, "login", v).ok, false);
  // the zones reference: one map's, by its sha256; another map drops it
  const x = xmasProject();
  const sha = "a".repeat(64);
  assert.equal(setZones(x, "xmas_dun02", { map: "geffen", sha256: sha }).ok, false);
  const z = ok(setZones(x, "xmas_dun02", { map: "xmas_dun02", sha256: sha }));
  assert.equal((nodeById(z, "xmas_dun02") as { zones?: unknown }).zones !== undefined, true);
  assert.ok(!("zones" in nodeById(ok(setZones(z, "xmas_dun02", null)), "xmas_dun02")!));
});

test("what a node says: its tabs and names, the overrides both ways, its lint", () => {
  const p = sessionProject();
  const xm = nodeById(p, "xmas_dun02")!;
  xm.tabs.push(tab("hunt", [def("heal", [pressKey("F2")]), def("look", [{ kind: "stop", reason: "x" }], { params: [{ name: "far", default: { kind: "lit", value: 9 } }], varargs: "more" })], { WEIGHT: { kind: "lit", value: 50 } }));
  assert.equal(nodeTitle(xm), "xmas_dun02");
  assert.equal(nodeTitle(globalOf(p)!), "Global");
  const rows = tabRows(p, xm);
  assert.deepEqual(rows.map((r) => [r.tab, r.main]), [["main", true], ["hunt", false]]);
  assert.deepEqual(rows[1].rows.map((r) => [r.name, r.kind, r.text, r.overrides, r.key]), [
    ["heal", "def", "heal()", true, "F2"],
    ["look", "def", "look(far=9, *more)", false, null],
    ["WEIGHT", "var", "WEIGHT = 50", false, null],
  ]);
  // which keys are taken, and a clash marked where it is (matpilot 9): xmas_dun02's heal is F2 now
  assert.deepEqual(rows[1].rows[0].clash, []);
  globalOf(p)!.tabs[0].defs.push(def("emote", [pressKey("F2")]));
  assert.deepEqual(tabRows(p, xm)[1].rows[0].clash, ["emote"]);
  assert.deepEqual(tabRows(p, globalOf(p)!)[0].rows.find((r) => r.name === "heal")!.key, "F1", "on Global, Global's own heal");
  const g = tabRows(p, globalOf(p)!);
  assert.deepEqual(g.find((t) => t.tab === "keys")!.rows.find((r) => r.name === "heal")!.overriddenOn, ["xmas_dun02"]);
  assert.match(g.find((t) => t.tab === "safety")!.rows[0].text, /^hp_low · when hp_percent\(\) < 30 · survival · then resume$/);
  const lint = {
    findings: [
      { rule: "r", severity: "error", layer: 1, path: "xmas_dun02/main/main.0", text: "", message: "m", ack: false, node: "xmas_dun02", tab: "main" },
      { rule: "r", severity: "warning", layer: 1, path: "geffen/main/main.0", text: "", message: "m", ack: false },
    ],
    counts: { error: 1, warning: 1, readiness: 0, info: 0 },
    by_owner: {},
  } as unknown as LintDoc;
  assert.deepEqual(nodeLint(lint, "xmas_dun02").counts, { error: 1, readiness: 0, warning: 0, info: 0 });
  assert.deepEqual(nodeLint(lint, "geffen").counts, { error: 0, readiness: 0, warning: 1, info: 0 });
  assert.equal(readRules(p).custom, false);
});

// matpilot round 20 #6: "Tabs and names" listed 162 raw lines (potion_below = 0.4): each tab folds
// with a line saying what it holds; a setting shows its value as its block does; a changed one first
test("the inspector's tabs: a summary line each, the settings in words with units, a changed one first and marked", () => {
  const p = xmasProject();
  const xm = nodeById(p, "xmas_dun02")!;
  const aim = xm.tabs.find((t) => t.name === "aim")!;
  aim.vars.FAR_CELLS = { kind: "lit", value: 6 }; // a person changed it
  const rows = tabRows(p, xm);
  const by = Object.fromEntries(rows.map((t) => [t.tab, t]));
  assert.equal(tabSummary(by.aim), "33 settings (1 changed)");
  assert.equal(tabSummary(by.main), "the node's program, 4 statements");
  assert.equal(tabSummary(by.keys), "8 functions");
  assert.equal(tabSummary(by.survival), "5 events, 2 settings");
  assert.equal(tabSummary(by.monsters), "4 functions");
  assert.deepEqual(by.aim.rows[0], { name: "FAR_CELLS", kind: "var", text: "from this far: one click, no re-click 6 cells", overrides: false, overriddenOn: [], key: null, clash: [], setting: { var: "FAR_CELLS", changed: true } });
  assert.equal(by.aim.rows.find((r) => r.name === "WALKER_PX")?.text, "feet moving this far = a walking target 10 px");
  assert.equal(by.knife.rows.find((r) => r.name === "knife_hp_min")?.text, "or at once under HP 50 %");
  assert.equal(by.walk.rows.find((r) => r.name === "WALK_PICK_TOL")?.text, "the client's pick within 1 cell");
  assert.equal(by.knife.rows.find((r) => r.name === "knife_swap")?.text, "Batt's Knife swap on");
  // an ordinary variable keeps its line
  aim.vars.my_count = { kind: "lit", value: 3 };
  assert.equal(tabRows(p, xm).find((t) => t.tab === "aim")!.rows[0].text, "my_count = 3");
  assert.equal(tabSummary(tabRows(p, xm).find((t) => t.tab === "aim")!), "1 variable, 33 settings (1 changed)");
});

// matpilot round 16 #7: the /maps chip said "3 warnings", the xmas_dun02 card "2 warnings"; the
// third was on the project itself and nothing on the page showed it. The lint list (the chip opens
// it) and the Intro read lintGroups: every finding in exactly one group, the cards' groups the
// cards' own findings, so the page shows what the chip counts.
test("the lint list shows every finding the chip counts: the project's own first, each card's as the card counts it", () => {
  const added = addMapNode(xmasProject(), "geffen", null);
  assert.ok(added.ok);
  const p = added.project;
  const f = (severity: string, node: string, tab: string, path: string, text: string) => ({ rule: "r", severity, layer: 1, node, tab, path, text, message: path ? `${path}: ${text}` : text, ack: false });
  // the reviewer's lint (POST /flows/lint, fresh /maps + geffen): warning 3, info 6, readiness 1
  const findings = [
    f("warning", "xmas_dun02", "main", "xmas_dun02/main/main.0", "the save point is asserted, not set: ..."),
    f("warning", "xmas_dun02", "", "xmas_dun02", "hp_critical's escape on xmas_dun02 is unknown: ..."),
    f("warning", "", "", "", "a death returns to the save point on geffen, where no block is: a death then stops the run"),
    f("readiness", "geffen", "main", "geffen/main/main.0", "not there yet"),
    ...Array.from({ length: 5 }, (_, i) => f("info", "xmas_dun02", "survival", `xmas_dun02/survival/drink.${i}`, `info ${i}`)),
    f("info", "nowhere", "main", "nowhere/main/main.0", "a node this project does not have"),
  ];
  const lint = { findings, counts: { error: 0, readiness: 1, warning: 3, info: 6 }, by_node: {}, run: { allowed: false, summary: "", reasons: [] }, effective: {}, world: { server: null, maps: [] } } as unknown as LintDoc;
  const groups = lintGroups(lint, p);
  // what the page shows adds up to the chip, severity by severity
  for (const sev of ["error", "readiness", "warning", "info"] as const) {
    assert.equal(groups.reduce((n, g) => n + g.counts[sev], 0), lint.counts[sev], sev);
  }
  assert.equal(groups.flatMap((g) => g.findings).length, findings.length, "every finding in exactly one group");
  // the project's own first: the save-point warning, and the finding on a node that is not here
  assert.deepEqual(groups.map((g) => g.node), [null, "xmas_dun02", "geffen"]);
  assert.deepEqual(groups[0].findings.map((x) => x.text), ["a death returns to the save point on geffen, where no block is: a death then stops the run", "a node this project does not have"]);
  // each card's group is the card's own findings (nodeLint): its card says "2 warnings", as before
  for (const g of groups.slice(1)) assert.deepEqual(g.findings, nodeLint(lint, g.node!).findings);
  assert.equal(groups[1].counts.warning, 2);
  assert.deepEqual(lintGroups(null, p), []);
});

// matpilot round 17 N2: the /maps inspector showed a node's first 6 findings in layer order -- on
// xmas_dun02 6 unlabelled info lines -- and "...and 18 more (on /flows)" hid all 4 warnings.
test("a capped finding list shows the most serious first, labels each line and says what it hides", () => {
  const f = (severity: string, i: number) => ({ rule: "r", severity, layer: 2, node: "xmas_dun02", tab: "main", path: `xmas_dun02/main/main.${i}`, text: `${severity} ${i}`, message: `xmas_dun02/main/main.${i}: ${severity} ${i}`, ack: false });
  // the reviewer's node: "Lint: 4 warnings · 20 info", the info lines first in the engine's order
  const fs = [...Array.from({ length: 6 }, (_, i) => f("info", i)), f("warning", 6), ...Array.from({ length: 14 }, (_, i) => f("info", 7 + i)), f("warning", 21), f("warning", 22), f("warning", 23)] as never[];
  const c = cappedFindings(fs, 6);
  assert.deepEqual(c.shown.map((x: { text: string }) => x.text), ["warning 6", "warning 21", "warning 22", "warning 23", "info 0", "info 1"]);
  assert.equal(c.more, "…and 18 more (18 info): the lint chip lists every one; so does /flows' Lint pane");
  // an error and what is not ready lead; plural words; the order inside a severity is the engine's
  const mixed = [f("info", 0), f("readiness", 1), f("warning", 2), f("error", 3), f("readiness", 4), f("error", 5), f("warning", 6)] as never[];
  assert.deepEqual(bySeverity(mixed).map((x: { text: string }) => x.text), ["error 3", "error 5", "readiness 1", "readiness 4", "warning 2", "warning 6", "info 0"]);
  assert.equal(cappedFindings(mixed, 1).more, "…and 6 more (1 error, 2 not ready, 2 warnings, 1 info): the lint chip lists every one; so does /flows' Lint pane");
  assert.equal(cappedFindings(mixed, 7).more, null);
  assert.deepEqual(Object.values(SEVERITY_WORDS), ["error", "not ready", "warning", "info"]);
  assert.equal(findingWhere(fs[0] as never), "main main.0: ");
  // the node's own list (the card, the inspector) and the chip's list read the same order
  const lint = { findings: fs, counts: { error: 0, readiness: 0, warning: 4, info: 20 }, by_node: {} } as unknown as LintDoc;
  assert.deepEqual(nodeLint(lint, "xmas_dun02").findings.slice(0, 4).map((x) => x.severity), ["warning", "warning", "warning", "warning"]);
  assert.deepEqual(lintGroups(lint, xmasProject())[0].findings.slice(0, 5).map((x) => x.severity), ["warning", "warning", "warning", "warning", "info"]);
});

// matpilot round 17 N3: every xmas_dun02 spawn read "on neither list: treated as IGNORE" while the
// runner strikes four of them; the inspector now says who picks the targets on a runner node
test("on a node that runs the runner the inspector says the runner strikes by its model, and lists the engine's lines", () => {
  const p = xmasProject();
  const n = nodeById(p, "xmas_dun02");
  assert.ok(n && n.kind === "map");
  const line = "mob 1249 spawns on xmas_dun02: the runner strikes it (mystcase, a class of xmas02; its recipe attack_mystcase chooses how)";
  const lint = { findings: [{ rule: "species_lists", severity: "info", layer: 2, node: "xmas_dun02", tab: "", path: "xmas_dun02", text: line, message: `xmas_dun02: ${line}`, ack: false }, { rule: "escape", severity: "warning", layer: 2, node: "xmas_dun02", tab: "", path: "xmas_dun02", text: "x", message: "xmas_dun02: x", ack: false }], counts: { error: 0, readiness: 0, warning: 1, info: 1 }, by_node: {} } as unknown as LintDoc;
  const rs = runnerSpecies(n, lint);
  assert.ok(rs);
  // matpilot round 18 #2: plain words: "every monster that the model named in main (...) boxes as a target"
  assert.match(rs.words, /strikes every monster that the model named in main \(use_model\("xmas02"\)\) boxes as a target, whatever these two lists say/);
  assert.match(rs.words, /never WHETHER; the model's other classes/);
  assert.doesNotMatch(rs.words, /boxes as one it strikes/);
  assert.match(rs.words, /chooses HOW that monster is attacked, never WHETHER/);
  assert.match(rs.words, /The lists are the simulator's/);
  assert.deepEqual(rs.lines, [line]);
  assert.deepEqual(runnerSpecies(n, null)?.lines, []);
  // no use_model in main: the map's own detector picks, and the words stay true
  const noModel = JSON.parse(JSON.stringify(n).replaceAll('"block":"use_model"', '"block":"no_such_block"')) as typeof n;
  const rs0 = runnerSpecies(noModel, null);
  assert.ok(rs0);
  assert.match(rs0.words, /strikes every monster that the map's own detector \(main names no use_model\) boxes as a target/);
  assert.match(rs0.words, /never WHETHER; the detector's other classes/);
  assert.doesNotMatch(rs0.words, /model's other classes/);
  // a node without the runner: the lists decide (no such words)
  const town = nodeById(sampleProject(), "town");
  assert.ok(town && town.kind === "map");
  assert.equal(runnerSpecies(town, lint), null);
});
