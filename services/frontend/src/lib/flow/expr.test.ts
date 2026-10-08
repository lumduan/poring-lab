import assert from "node:assert/strict";
import { test } from "node:test";

import { argsText, ExprError, exprText, hasDo, parseArgs, parseExpr } from "./expr.ts";
import { canonical, type Expr } from "./ir.ts";
import { allExprs, expr, FIXTURES, fixture, Rng } from "./testkit.ts";

const same = (a: unknown, b: unknown) => assert.equal(canonical(a), canonical(b));

test("every expression of the fixtures round-trips through its text", () => {
  let n = 0;
  for (const name of FIXTURES) {
    for (const e of allExprs(fixture(name))) {
      if (hasDo(e)) continue;
      same(parseExpr(exprText(e)), e);
      n++;
    }
  }
  assert.ok(n > 30, `${n} expressions`);
});

test("random expressions round-trip (seeded)", () => {
  for (let seed = 1; seed <= 400; seed++) {
    const e = expr(new Rng(seed), 0, false);
    same(parseExpr(exprText(e)), e);
  }
});

test("the text form reads like the Python view", () => {
  same(parseExpr("hp_percent() < 50"), {
    kind: "cmp",
    op: "<",
    left: { kind: "sense", sensor: "hp_percent", args: {} },
    right: { kind: "lit", value: 50 },
  });
  same(parseExpr("not sees(mob=mob(9109), within=15)"), {
    kind: "not",
    term: {
      kind: "sense",
      sensor: "sees",
      args: { mob: { kind: "lit", value: { kind: "mob", id: 9109 } }, within: { kind: "lit", value: 15 } },
    },
  });
  same(parseExpr("engaged_species() in [mob(1), mob(2)]").kind, "cmp");
  same(parseExpr('x not in [WING, item(3)]'), {
    kind: "cmp",
    op: "not in",
    left: { kind: "var", name: "x" },
    right: { kind: "list", items: [{ kind: "var", name: "WING" }, { kind: "lit", value: { kind: "item", id: 3 } }] },
  });
  same(parseExpr("a and b and c"), {
    kind: "and",
    terms: [{ kind: "var", name: "a" }, { kind: "var", name: "b" }, { kind: "var", name: "c" }],
  });
  same(parseExpr("(a and b) and c"), {
    kind: "and",
    terms: [{ kind: "and", terms: [{ kind: "var", name: "a" }, { kind: "var", name: "b" }] }, { kind: "var", name: "c" }],
  });
  same(parseExpr("FAILED"), { kind: "outcome", value: "failed" });
  same(parseExpr("-5"), { kind: "lit", value: -5 });
  same(parseExpr('cell("map_1", 3, 4)'), { kind: "lit", value: { kind: "cell", map: "map_1", x: 3, y: 4 } });
  same(parseExpr("skill(5, level=3)"), { kind: "lit", value: { kind: "skill", id: 5, level: 3 } });
  assert.equal(exprText(parseExpr("1 + 2 * 3")), "1 + (2 * 3)");
});

test("bad text is refused with a column, and nothing is ever evaluated", () => {
  const bad = [
    "",
    "hp_percent( < 50",
    "1 < 2 < 3",
    "sees(mob(1))", // sensor arguments by name
    "cell(1, 2)",
    "[1, 2]", // a list holds references or variables
    "__import__('os')",
    "x.y",
    "a = 1",
    '"unterminated',
    "x" + "(".repeat(70) + ")".repeat(70),
    "a".repeat(3000),
  ];
  for (const src of bad) assert.throws(() => parseExpr(src), ExprError, src);
  // a text literal that looks like code stays text
  same(parseExpr('"eval(1)"'), { kind: "lit", value: "eval(1)" });
});

test("parameters by name round-trip", () => {
  const p: Record<string, Expr> = {
    within: { kind: "lit", value: 12 },
    all_except: { kind: "list", items: [{ kind: "var", name: "WING" }, { kind: "var", name: "POTION" }] },
  };
  same(parseArgs(argsText(p)), p);
  same(parseArgs(""), {});
  assert.throws(() => parseArgs("12"), ExprError);
});
