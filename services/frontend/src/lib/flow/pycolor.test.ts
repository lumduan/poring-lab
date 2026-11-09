// The Python view's colours (pycolor.ts): MatPilot's rules (the parent's list, 2026-11-09), so the
// code reads the same on /flows as on matpilot.org/blocks.
import assert from "node:assert/strict";
import { test } from "node:test";

import { colouredPieces } from "./pycolor.ts";

const kinds = (code: string) => colouredPieces(code).filter((p) => p.kind).map((p) => `${p.text}:${p.kind}`);

test("control words are control; def / class / True / None / and ... are keywords", () => {
  const code = [
    "if a:", "elif b:", "else:", "for x in y:", "while z:", "return", "import m", "from m import n",
    "break", "continue", "pass", "raise", "try:", "except:", "finally:", "with w as v:",
  ].join("\n");
  const control = kinds(code).filter((k) => k.endsWith(":control")).map((k) => k.split(":")[0]);
  assert.deepEqual(control, ["if", "elif", "else", "for", "while", "return", "import", "from", "import", "break",
    "continue", "pass", "raise", "try", "except", "finally", "with", "as"]);
  const kw = kinds("def f(): pass\nclass A: pass\nlambda: True and False or None\nnot x in y is z\nglobal G");
  for (const w of ["def", "class", "lambda", "True", "and", "False", "or", "None", "not", "in", "is", "global"]) {
    assert.ok(kw.includes(`${w}:keyword`), w);
  }
});

test("a name before ( is a function; after def a function, after class a class", () => {
  assert.deepEqual(kinds("walk_to(cell)"), ["walk_to:function", "(:bracket1", "cell:variable", "):bracket1"]);
  assert.deepEqual(kinds("wait_until (x)").slice(0, 1), ["wait_until:function"]); // spaces before ( too
  assert.deepEqual(kinds("def town():"), ["def:keyword", "town:function", "(:bracket1", "):bracket1"]);
  assert.deepEqual(kinds("class Robot:"), ["class:keyword", "Robot:class"]);
  assert.deepEqual(kinds("@on(x)"), ["on:function", "(:bracket1", "x:variable", "):bracket1"]);
});

test("ALL_CAPS names are constants, CapWords classes, other names variables", () => {
  assert.deepEqual(kinds("POTION = item(9001)"), ["POTION:constant", "item:function", "(:bracket1", "9001:number", "):bracket1"]);
  assert.deepEqual(kinds("path=S2, priority=CRITICAL"), ["path:variable", "S2:constant", "priority:variable", "CRITICAL:constant"]);
  assert.deepEqual(kinds("Color + x"), ["Color:class", "x:variable"]);
  assert.deepEqual(kinds("X"), ["X:variable"]); // one capital letter is not ALL_CAPS (MatPilot's rule)
});

test("strings, their escapes, prefixes and triple quotes", () => {
  assert.deepEqual(kinds('stop("done")'), ["stop:function", "(:bracket1", '"done":string', "):bracket1"]);
  assert.deepEqual(kinds("x = 'a\\n' + \"b\\\"c\""), ["x:variable", "'a:string", "\\n:escape", "':string", '"b:string', '\\":escape', 'c":string']);
  assert.deepEqual(kinds('r"\\d" f"{x}" b\'z\''), ['r"\\d":string', 'f"{x}":string', "b'z':string"]);
  assert.deepEqual(kinds('"""one\n"two"\nthree"""'), ['"""one\n"two"\nthree""":string']);
  assert.deepEqual(kinds('"\\u0e01\\x41"'), ['":string', "\\u0e01:escape", "\\x41:escape", '":string']);
  assert.deepEqual(kinds('"ไทย"'), ['"ไทย":string']); // Thai text stays one string
  assert.deepEqual(kinds('"open\nx'), ['"open:string', "x:variable"]); // unterminated: ends at the line
});

test("numbers, comments and nothing else is coloured", () => {
  assert.deepEqual(kinds("timeout_s=30.0, x=-12, y=1e-3, z=0x1F  # wait"), [
    "timeout_s:variable", "30.0:number", "x:variable", "12:number", "y:variable", "1e-3:number", "z:variable", "0x1F:number",
    "# wait:comment",
  ]);
  assert.deepEqual(kinds("# --- Main ---------\nstop()"), ["# --- Main ---------:comment", "stop:function", "(:bracket1", "):bracket1"]);
  const plain = colouredPieces("a = b, c").filter((p) => !p.kind).map((p) => p.text);
  assert.deepEqual(plain, [" = ", ", "]); // operators and commas are plain text
});

test("brackets cycle 1 / 2 / 3 by depth", () => {
  assert.deepEqual(kinds("f([{(x)}])").filter((k) => !/^[fx]:/.test(k)), [
    "(:bracket1", "[:bracket2", "{:bracket3", "(:bracket1", "):bracket1", "}:bracket3", "]:bracket2", "):bracket1",
  ]);
  assert.deepEqual(kinds(")("), ["):bracket1", "(:bracket1"]); // never below depth 0
});

test("every character is kept, in order, for the read-only view", () => {
  const code = '# --- Config ---\nflow(\n    ir=2,\n    name="t",\n)\n\n@map_block(map_id("x"), entries=[entry_anywhere("a")])\ndef town():\n    if detector_sees("v1", "monster") and not is_dead():\n        stop("done")\n';
  assert.equal(colouredPieces(code).map((p) => p.text).join(""), code);
  assert.deepEqual(colouredPieces(""), []);
});

test("the engine's own Python colours as expected", () => {
  const code = 'wait_until(detector_sees("v1", "monster"), timeout_s=30.0)';
  assert.deepEqual(kinds(code), [
    "wait_until:function", "(:bracket1", "detector_sees:function", "(:bracket2", '"v1":string', '"monster":string',
    "):bracket2", "timeout_s:variable", "30.0:number", "):bracket1",
  ]);
});
