// The Zones layer's model and the editor's YAML (blocks-from-hunt-flow.md B2). The acceptance:
// an editor-made file loads with the sha256 of its hand-written twin (the bytes are the same), the
// import -> export round trip is exact, and the loader's error corpus shows in the editor as it is.
// The fixtures are written by scripts/gen_zones_fixtures.py from the backend (drift-tested there);
// syn_zones.yaml is hand-written, prt_fild08.yaml is config/map_zones' own file.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  addItem,
  addPoint,
  type Cell,
  cellOfPixel,
  checkLines,
  commentLines,
  type Draft,
  emptyReview,
  emptyZones,
  finished,
  modelFrom,
  printableLine,
  problems,
  removeItem,
  type Review,
  startDraft,
  suggestId,
  undoPoint,
  type ZoneKind,
  type ZonesCheck,
  type ZonesModel,
  zonesYaml,
} from "./zones.ts";

const dir = new URL("./fixtures/zones/", import.meta.url);
const bytes = (name: string) => readFileSync(new URL(name, dir));
const sha = (b: Buffer | string) => createHash("sha256").update(b).digest("hex");
type Fixture = { map: string; sha256: string; model: ZonesModel; review: { reviewed_by: string; reviewed: string; delegation: string }; notes: string[] };
const fixture = (name: string): Fixture => JSON.parse(bytes(`${name}.json`).toString("utf8")) as Fixture;

/** A person's clicks for one item, then its id and note (what the Zones layer does). */
function draw(model: ZonesModel, kind: ZoneKind, clicks: Cell[], id: string, note: string, close = false): ZonesModel {
  let d: Draft = startDraft(kind);
  for (const c of clicks) {
    const r = addPoint(d, c);
    assert.equal(r.error, null, `${id} ${c}`);
    assert.equal(r.closed, false);
    d = r.draft;
  }
  if (close) assert.equal(addPoint(d, clicks[0]).closed, true); // a click on the first corner
  assert.ok(finished(d));
  const r = addItem(model, d, id, note);
  assert.ok(r.ok, !r.ok ? r.error : "");
  return r.model;
}

test("an editor-made file has the bytes and the sha256 of its hand-written twin (synthetic)", () => {
  const twin = bytes("syn_zones.yaml");
  let m = emptyZones("syn_zones");
  m = { ...m, comment: commentLines(
    "A SYNTHETIC zones file, written BY HAND in the /flows editor's form (blocks-from-hunt-flow.md B2):\n" +
    "the twin of the file zones.test.ts draws click by click. Same bytes, same sha256.\n\n" +
    "  indented comment text is kept as written\n") };
  // a line double-clicked at its end: the second click of the double click adds nothing
  m = draw(m, "no_cross", [[10, 4], [10, 7], [13, 9], [13, 9]], "door_1", "the west gap");
  m = draw(m, "no_cross", [[30, 40], [34, 40]], "door 2", 'the "north" gap, near the café (path\\cell)');
  m = draw(m, "no_enter", [[50, 50], [60, 50], [60, 58], [50, 58]], "pit", "a room nobody should enter", true);
  const review: Review = { reviewed_by: "batt", reviewed: "2026-10-21", delegation: "" }; // typed by a person
  const r = zonesYaml(m, review);
  assert.ok(r.ok, !r.ok ? r.errors.join("; ") : "");
  assert.equal(r.text, twin.toString("utf8"));
  assert.equal(sha(r.text), sha(twin));
  assert.equal(sha(r.text), fixture("syn_zones").sha256); // the loader's own sha256 (backend fixture)
  assert.deepEqual(m, fixture("syn_zones").model); // and the model the backend reads from the twin
});

test("prt_fild08.yaml, drawn click by click, is byte for byte the committed file (its sha256)", () => {
  const f = fixture("prt_fild08");
  let m: ZonesModel = { ...emptyZones("prt_fild08"), comment: f.model.comment }; // the comment, as typed
  const [c1, c3] = f.model.items;
  m = draw(m, "no_cross", [[322, 88], [318, 91]], "c1-door", c1.note);
  m = draw(m, "no_cross", [[50, 36], [46, 36]], "c3-door", c3.note);
  const r = zonesYaml(m, f.review); // the reviewer exactly as Batt's delegation records it, TYPED
  assert.ok(r.ok);
  assert.equal(r.text, bytes("prt_fild08.yaml").toString("utf8"));
  assert.equal(sha(r.text), f.sha256); // the loader's sha256 of config/map_zones/prt_fild08.yaml
});

test("import -> export is exact for every file the backend read (round trip)", () => {
  for (const name of ["syn_zones", "prt_fild08"]) {
    const f = fixture(name);
    const m = modelFrom(f.model, f.map);
    assert.ok(m, name);
    assert.deepEqual(f.notes, []);
    const r = zonesYaml(m, f.review);
    assert.ok(r.ok, name);
    assert.equal(r.text, bytes(`${name}.yaml`).toString("utf8"), name);
  }
});

test("the loader's error corpus shows in the editor exactly as the CLI prints it", () => {
  const corpus = JSON.parse(bytes("errors.json").toString("utf8")) as { name: string; yaml: string; error: string }[];
  assert.ok(corpus.length >= 30);
  for (const c of corpus) {
    const reply: ZonesCheck = { map: "fix_map", ok: false, error: c.error, shape: [60, 60], sha256: sha(c.yaml) };
    const lines = checkLines(reply);
    assert.deepEqual(lines[0], { tone: "error", text: c.error }, c.name);
    assert.ok(c.error.startsWith("config/map_zones/fix_map.yaml: "), c.name);
  }
  const names = corpus.map((c) => c.name).join(" | ");
  for (const why of ["no reviewed_by", "never approves", "off the map", "cross", "not readable YAML", "needs a `delegation` note"]) {
    assert.ok(names.includes(why), why);
  }
});

test("the editor never fills the review; export waits for a person's reviewer and date", () => {
  const m = draw(emptyZones("syn_zones"), "no_cross", [[1, 1], [3, 1]], "a", "n");
  assert.deepEqual(emptyReview(), { reviewed_by: "", reviewed: "", delegation: "" });
  const r = zonesYaml(m, emptyReview());
  assert.ok(!r.ok);
  assert.ok(r.errors.some((e) => e.startsWith("reviewed_by: type the PERSON")));
  assert.ok(r.errors.some((e) => e.startsWith("reviewed: the review date")));
  assert.ok(!zonesYaml(m, { reviewed_by: "batt", reviewed: "2026-02-30", delegation: "" }).ok);
  assert.ok(zonesYaml(m, { reviewed_by: "batt", reviewed: "2026-02-28", delegation: "" }).ok);
  // no delegation line unless one is typed
  const t = zonesYaml(m, { reviewed_by: "batt", reviewed: "2026-02-28", delegation: "" });
  assert.ok(t.ok && !t.text.includes("delegation:"));
});

test("drawing refuses what the loader refuses, early", () => {
  let d = startDraft("no_enter");
  d = addPoint(d, [1, 1]).draft;
  d = addPoint(d, [5, 1]).draft;
  assert.equal(addPoint(d, [1, 1]).error, "an area needs 3 corners before it closes");
  assert.deepEqual(addPoint(d, [5, 1]), { draft: d, closed: false, error: null }); // a double click
  assert.equal(addPoint(d, [-1, 2]).error, "a cell on the map");
  d = addPoint(d, [5, 5]).draft;
  assert.match(addPoint(d, [5, 1]).error ?? "", /a corner repeats/);
  assert.equal(addPoint(d, [1, 1]).closed, true);
  assert.equal(undoPoint(d).points.length, 2);
  const line = addPoint(startDraft("no_cross"), [2, 2]).draft;
  assert.ok(!finished(line));
  const m = draw(emptyZones("syn_zones"), "no_cross", [[1, 1], [3, 1]], "nc1", "n");
  assert.equal(suggestId(m, "no_cross"), "nc2");
  assert.equal(suggestId(m, "no_enter"), "ne1");
  const two = addPoint(line, [4, 2]).draft;
  const dup = addItem(m, two, "nc1", "x");
  assert.ok(!dup.ok && dup.error.includes("taken"));
  const noNote = addItem(m, two, "nc2", "  ");
  assert.ok(!noNote.ok && noNote.error.includes("note"));
  const multi = addItem(m, two, "nc2", "two\nlines");
  assert.ok(!multi.ok);
  assert.deepEqual(removeItem(m, 0).items, []);
});

test("ids and the map are written plain only when YAML reads them back as the same string", () => {
  let m = emptyZones("syn_zones");
  for (const [i, id] of ["yes", "Off", "null", "1a", "a b", "ok_id", "c1-door", "~"].entries()) {
    m = draw(m, "no_cross", [[i, 0], [i, 3]], id, "n");
  }
  const r = zonesYaml(m, { reviewed_by: "batt", reviewed: "2026-10-21", delegation: "" });
  assert.ok(r.ok);
  const ids = r.text.split("\n").filter((l) => l.startsWith("  - id: ")).map((l) => l.slice(8));
  assert.deepEqual(ids, ['"yes"', '"Off"', '"null"', '"1a"', '"a b"', "ok_id", "c1-door", '"~"']);
  assert.ok(zonesYaml({ ...m, map: "1@tower" }, { reviewed_by: "b", reviewed: "2026-10-21", delegation: "" }).ok);
  assert.match(problems({ ...m, map: "../x" }, { reviewed_by: "b", reviewed: "2026-10-21", delegation: "" })[0], /not a file name/);
});

test("only one-line printable text reaches the file (PyYAML's reader refuses the rest)", () => {
  for (const ok of ["plain", "café", "naïve résumé", "a \"q\" \\ b", "emoji 🐟"]) assert.ok(printableLine(ok), ok);
  for (const bad of ["a\nb", "tab\there", "nel\u0085", "ls ", "bom﻿", "del\u007f", "lone\ud800"]) {
    assert.ok(!printableLine(bad), JSON.stringify(bad));
  }
  assert.deepEqual(commentLines(""), []);
  assert.deepEqual(commentLines("a\r\nb\n"), ["a", "b"]);
  assert.equal(modelFrom({ map: "other", comment: [], items: [] }, "syn_zones"), null);
  assert.equal(modelFrom({ map: "m", comment: [], items: [{ kind: "wall", id: "a", note: "n", points: [] }] }, "m"), null);
});

test("the map node's zones reference: set, kept by every view, removed as an absent key", async () => {
  const { setZonesRef, toGraph, fromGraph } = await import("./canvas.ts");
  const { fromWorkspace, toWorkspace } = await import("./blocks.ts");
  const { canonical, clone } = await import("./ir.ts");
  const { fixture: flowFixture } = await import("./testkit.ts");
  const flow = flowFixture("town_warp_farm");
  const ref = { map: "field_1", sha256: "a".repeat(64) };
  const r = setZonesRef(flow, "farm", ref);
  assert.ok(r.ok);
  const farm = r.flow.workflow!.blocks.find((b) => b.name === "farm")!;
  assert.deepEqual(farm.zones, ref);
  assert.equal(canonical(fromGraph(JSON.parse(JSON.stringify(toGraph(r.flow))))), canonical(r.flow));
  const ws = JSON.parse(JSON.stringify(toWorkspace(r.flow, { kind: "block", name: "farm" })));
  const back = fromWorkspace(r.flow, { kind: "block", name: "farm" }, ws);
  assert.ok(back.ok && canonical(back.flow) === canonical(r.flow));
  const wrong = setZonesRef(flow, "farm", { map: "town_1", sha256: "a".repeat(64) });
  assert.ok(!wrong.ok && wrong.error.includes("not field_1's"));
  assert.ok(!setZonesRef(flow, "farm", { map: "field_1", sha256: "xyz" }).ok);
  const removed = setZonesRef(r.flow, "farm", null);
  assert.ok(removed.ok);
  assert.ok(!("zones" in removed.flow.workflow!.blocks.find((b) => b.name === "farm")!));
  assert.equal(canonical(removed.flow), canonical(clone(flow))); // the hash MW1 computes is the old one
});

test("the Zones layer and the hunt block stay CSP clean: no script, no remote source, no link from data", () => {
  const root = new URL("../../", import.meta.url);
  for (const f of ["components/flows/ZonesEditor.tsx", "components/flows/PathMap.tsx", "components/flows/BlockEditor.tsx", "lib/flow/zones.ts", "lib/flow/hunt.ts"]) {
    const text = readFileSync(new URL(f, root), "utf8");
    for (const bad of ["<script", "dangerouslySetInnerHTML", "innerHTML", "eval(", "new Function", "javascript:", "http://", "https://", "<iframe", "srcDoc"]) {
      assert.ok(!text.includes(bad), `${f}: ${bad}`);
    }
  }
  const z = readFileSync(new URL("components/flows/ZonesEditor.tsx", root), "utf8");
  assert.deepEqual(z.match(/\.href = [^;]+;/g), [".href = url;"]); // the one link: the export's blob
  assert.match(z, /const url = URL\.createObjectURL\(new Blob\(\[text\]/);
});

test("a canvas pixel maps to its cell: every pixel of a cell, y north, nothing off the map", () => {
  // zoom 2 on a 100 x 100 map: cell (x, y) covers content pixels [2x, 2x + 1] x [2(99 - y), 2(99 - y) + 1]
  for (const [dx, dy, want] of [
    [0, 0, [0, 99]], [1, 1, [0, 99]], [2, 1, [1, 99]], [21, 159, [10, 20]], [20, 158, [10, 20]],
    [199, 199, [99, 0]], [200, 10, null], [-1, 10, null], [10, 200, null],
  ] as [number, number, Cell | null][]) {
    assert.deepEqual(cellOfPixel(dx, dy, 2, 100, 100), want, `${dx},${dy}`);
  }
  assert.deepEqual(cellOfPixel(7.9, 0, 8, 10, 10), [0, 9]);
  assert.deepEqual(cellOfPixel(8, 0, 8, 10, 10), [1, 9]);
});
