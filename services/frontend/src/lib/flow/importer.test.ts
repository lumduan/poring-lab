import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { exportText, importFlow, jsonDepth } from "./importer.ts";
import { canonical, emptyFlow, runSettings } from "./ir.ts";
import { FIXTURES, fixture } from "./testkit.ts";

test("JSON export -> import is exact", () => {
  for (const name of FIXTURES) {
    const flow = fixture(name);
    const r = importFlow(exportText(flow));
    assert.ok(r.ok);
    if (r.ok) assert.equal(canonical(r.flow), canonical(flow));
  }
});

test("hostile files are refused with a message, before anything parses them", () => {
  const cases: [string, RegExp][] = [
    ["x".repeat((1 << 20) + 1), /bytes; at most/],
    ["[".repeat(300) + "]".repeat(300), /nested deeper/],
    ["{not json", /not JSON/],
    ["[1, 2]", /JSON object/],
    [JSON.stringify({ ...fixture("farm_loop"), ir: 3 }), /ir: IR version 3 is not supported: this editor reads IR 2 \(and converts IR 1\)/],
    [JSON.stringify({ ...fixture("farm_loop"), main: [] }), /exactly one of main and workflow/],
    [JSON.stringify({ ...fixture("farm_loop"), name: "Bad Name" }), /name:/],
  ];
  for (const [text, msg] of cases) {
    const r = importFlow(text);
    assert.equal(r.ok, false);
    if (!r.ok) assert.match(r.errors.join("; "), msg);
  }
  assert.equal(jsonDepth('{"a": "[[[[[["}'), 1); // brackets inside strings do not count
});

test("an IR 1 file converts to IR 2 exactly as MW1's ir.upgrade does (ADR-0020 #13)", () => {
  // farm_loop.ir1.json: the canonical JSON of Batt's example before IR 2 (the same copy MW1's
  // test_rank.py converts); farm_loop.json: MW1's IR 2 canonical JSON of the same flow
  const ir1 = readFileSync(new URL("./fixtures/farm_loop.ir1.json", import.meta.url), "utf8");
  assert.equal(JSON.parse(ir1).ir, 1);
  const r = importFlow(ir1);
  assert.ok(r.ok, JSON.stringify(r));
  if (r.ok) assert.equal(canonical(r.flow), canonical(fixture("farm_loop")));
});

test("the run settings stay inside the configured maximum (ADR-0020 #17) and the /where budget (#10)", () => {
  const f = fixture("farm_loop");
  const ok = runSettings(f, "7200", "3", 86_400);
  assert.ok(ok.ok && ok.flow.max_runtime_s === 7200 && ok.flow.where_budget === 3 && f.max_runtime_s === 14_400);
  const over = runSettings(f, "90000", "3", 86_400);
  assert.ok(!over.ok && /1\.\.86400 \(the configured maximum\)/.test(over.error));
  assert.ok(!runSettings(f, "0", "3", 86_400).ok);
  assert.ok(!runSettings(f, "3600", "1001", 86_400).ok);
  assert.ok(runSettings(f, "600000", "0", null).ok); // no configured value known: the schema cap only
  assert.equal(emptyFlow("x", 7200).max_runtime_s, 7200);
  assert.equal(emptyFlow().max_runtime_s, 14_400);
});
