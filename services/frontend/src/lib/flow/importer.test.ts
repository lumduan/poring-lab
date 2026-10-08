import assert from "node:assert/strict";
import { test } from "node:test";

import { exportText, importFlow, jsonDepth } from "./importer.ts";
import { canonical } from "./ir.ts";
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
    [JSON.stringify({ ...fixture("farm_loop"), ir: 2 }), /ir:/],
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
