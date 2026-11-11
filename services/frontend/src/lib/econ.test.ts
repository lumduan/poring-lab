import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buyPrice,
  consumableLines,
  dcPrice,
  type DashExport,
  discount,
  dropLines,
  editCount,
  factorText,
  fmtInt,
  fmtOne,
  fmtPct,
  incomeLines,
  killLines,
  loadEdits,
  NO_EDITS,
  ocPrice,
  overcharge,
  parseExport,
  parseList,
  parsePrice,
  perHour,
  PRICES_KEY,
  runAt,
  runLabel,
  saveEdits,
  SCHEMA,
  sellPrice,
  setPrice,
  skillRate,
  summary,
} from "./econ.ts";

// The server's price rules. Every expected value below was computed with the PYTHON functions the
// item table is built with -- scripts/econ_items.py `skill_rate`, `overcharge` and `discount`
// (2026-11-11, `python3 -c "import econ_items as ei; print([(v, ei.overcharge(v)) ...])"`) -- so
// the page and the table can never round differently.

test("skill rate: 5 + 2 lv - (lv == 10), 0 without the skill (econ_items.skill_rate)", () => {
  const py = [0, 7, 9, 11, 13, 15, 17, 19, 21, 23, 24]; // levels 0..10
  assert.deepEqual(py.map((_, lv) => skillRate(lv)), py);
});

test("Overcharge Lv 10 truncates per unit, never below 0 (econ_items.overcharge)", () => {
  const py: [number, number][] = [
    [0, 0], [1, 1], [3, 3], [4, 4], [5, 6], [7, 8], [9, 11], [25, 31], [40, 49], [99, 122],
    [100, 124], [333, 412], [1001, 1241], [9999, 12398], [123457, 153086], [1000000000, 1240000000],
  ];
  for (const [v, want] of py) assert.equal(overcharge(v), want, `overcharge(${v})`);
  for (const [v, want] of [[1, 1], [7, 8], [99, 113], [1001, 1151]]) assert.equal(overcharge(v, 5), want); // Lv 5
  assert.equal(overcharge(7, 0), 7); // no skill: unchanged
});

test("Discount Lv 10 truncates per unit, never below 1 (econ_items.discount)", () => {
  const py: [number, number][] = [
    [0, 1], [1, 1], [3, 2], [4, 3], [5, 3], [7, 5], [9, 6], [25, 19], [40, 30], [99, 75],
    [100, 76], [333, 253], [1001, 760], [9999, 7599], [123457, 93827], [1000000000, 760000000],
  ];
  for (const [v, want] of py) assert.equal(discount(v), want, `discount(${v})`);
  for (const [v, want] of [[1, 1], [7, 6], [99, 92], [1001, 930]]) assert.equal(discount(v, 1), want); // Lv 1
  assert.equal(factorText(24, true), "1.24");
  assert.equal(factorText(24, false), "0.76");
});

// A synthetic export: the same 30-minute synthetic run as services/backend/tests/test_econ_dash.py
// (synthetic ids 9xxxx, synthetic names and prices; the table's derived prices by the rules above).
const RUN = {
  session: "20261111T000000-synthetic-p7",
  map: "testmap",
  char: "rogue",
  minutes: 30,
  hours: 0.5,
  kills: 4,
  deaths: 0,
  items: [
    { item_id: 90001, name: "loot-a", type: "Etc", weight: 2, sellable: true, sell: 40, sell_oc: 49, picked: 1, stolen: 1, stolen_steal: 0, stolen_snatcher: 1, income: 2, other: 0, staged: 0, dropped: 2, picked_of_dropped: 1 },
    { item_id: 90002, name: null, type: "Etc", weight: 1, sellable: true, sell: 7, sell_oc: 8, picked: 2, stolen: 0, stolen_steal: 0, stolen_snatcher: 0, income: 2, other: 1, staged: 0, dropped: 2, picked_of_dropped: 2 },
    { item_id: 90200, name: null, type: null, weight: null, sellable: null, sell: null, sell_oc: null, picked: 0, stolen: 1, stolen_steal: 0, stolen_snatcher: 1, income: 1, other: 0, staged: 0, dropped: 0, picked_of_dropped: 0 },
  ],
  species: [
    { mob_id: 91002, name: null, kills: 1 },
    { mob_id: 91001, name: "mob-x", kills: 3 },
  ],
  consumables: [
    { item_id: 90300, name: null, type: "Usable", kind: "other", used: 1, npc_buy: null, npc_buy_dc: null },
    { item_id: 90100, name: "potion-x", type: "Healing", kind: "potion", used: 2, npc_buy: 50, npc_buy_dc: 38 },
  ],
  why: { unpriced_items: "not in the item table" },
};
const DOC = {
  schema: SCHEMA,
  name: "t1",
  exported_at: "2026-11-11T12:00:00+0000",
  sources: {},
  rules: { overcharge: { level: 10, rate_pct: 24, min_price: 0 }, discount: { level: 10, rate_pct: 24, min_price: 1 } },
  runs: [RUN],
  pooled: { ...RUN, session: "pooled (1 runs)", runs: 1 },
};

function doc(): DashExport {
  return parseExport(JSON.parse(JSON.stringify(DOC)));
}

test("an export is checked field by field; the wrong schema or a bad number is refused", () => {
  const d = doc();
  assert.equal(d.runs.length, 1);
  assert.equal(d.rules.overcharge.rate_pct, 24);
  assert.equal(runAt(d, -1).session, "pooled (1 runs)");
  assert.equal(runAt(d, 0).session, RUN.session);
  assert.equal(runAt(d, 5).session, "pooled (1 runs)");
  assert.throws(() => parseExport({ ...DOC, schema: "other" }), /unknown schema/);
  assert.throws(() => parseExport(null), /not an export/);
  const bad = JSON.parse(JSON.stringify(DOC));
  bad.runs[0].items[0].picked = "3";
  assert.throws(() => parseExport(bad), /item 0 picked: not a number/);
  const noHours = JSON.parse(JSON.stringify(DOC));
  delete noHours.pooled.hours;
  assert.throws(() => parseExport(noHours), /pooled hours/);
  assert.deepEqual(parseList({ exports: [{ name: "b", bytes: 3, modified: 2 }, { bytes: 1 }, "x"] }), [{ name: "b", bytes: 3, modified: 2 }]);
  assert.deepEqual(parseList(null), []);
});

test("the P&L at the table's prices equals econ_dash.totals for the same run", () => {
  const s = summary(doc().runs[0], NO_EDITS);
  // test_econ_dash: gross 2 x 40 + 2 x 7 = 94 z, OC 2 x 49 + 2 x 8 = 114, cost 2 x 50 = 100, DC 2 x 38 = 76; 0.5 h
  assert.equal(s.grossH, 188);
  assert.equal(s.grossOcH, 228);
  assert.equal(s.costH, 200);
  assert.equal(s.costDcH, 152);
  assert.equal(s.netH, -12);
  assert.equal(s.netBestH, 76);
  assert.equal(s.killsH, 8);
  assert.deepEqual(s.unpricedIncome, [90200]);
  assert.deepEqual(s.unpricedCost, [90300]);
  assert.deepEqual(s.notIncome, { other: 1, staged: 0 }); // shown, never in the gross
});

test("an edited sell price recomputes Overcharge by the rule; reset restores the table's", () => {
  const r = doc().runs[0];
  const it = r.items[0];
  let e = setPrice(NO_EDITS, "sell", 90001, 99);
  assert.equal(sellPrice(it, e), 99);
  assert.equal(ocPrice(it, e), 122); // econ_items.overcharge(99)
  assert.equal(ocPrice(it, NO_EDITS), 49); // the table's
  assert.deepEqual(NO_EDITS, { sell: {}, buy: {} }); // never mutated
  const s = summary(r, e);
  assert.equal(s.grossH, (2 * 99 + 2 * 7) / 0.5);
  assert.equal(s.grossOcH, (2 * 122 + 2 * 8) / 0.5);
  e = setPrice(e, "sell", 90200, 10); // a price for the item the table lacks
  assert.deepEqual(summary(r, e).unpricedIncome, []);
  e = setPrice(e, "sell", 90001, null);
  assert.equal(sellPrice(it, e), 40);
  assert.equal(editCount(e), 1);
});

test("an edited buy price recomputes Discount by the rule; unedited, the table's discount shop", () => {
  const r = doc().runs[0];
  const potion = r.consumables.find((c) => c.item_id === 90100);
  assert.ok(potion);
  assert.equal(dcPrice(potion, NO_EDITS), 38); // the table's npc_buy_dc
  const e = setPrice(NO_EDITS, "buy", 90100, 1200);
  assert.equal(buyPrice(potion, e), 1200);
  assert.equal(dcPrice(potion, e), 912); // econ_items.discount(1200)
  const noShop = r.consumables.find((c) => c.item_id === 90300);
  assert.ok(noShop);
  assert.equal(buyPrice(noShop, NO_EDITS), null); // no NPC sells it: no invented price
  assert.equal(dcPrice(noShop, NO_EDITS), null);
  const s = summary(r, setPrice(e, "buy", 90300, 3));
  assert.equal(s.costH, (2 * 1200 + 3) / 0.5);
  assert.equal(s.costDcH, (2 * 912 + discount(3)) / 0.5);
  assert.deepEqual(s.unpricedCost, []);
});

test("the tables: counts, per hour, shares, ordered by value then id (never by a name)", () => {
  const r = doc().runs[0];
  const inc = incomeLines(r, NO_EDITS);
  assert.deepEqual(inc.map((l) => l.item.item_id), [90001, 90002, 90200]); // 160, 28, null z/h
  assert.equal(inc[0].perH, 4);
  assert.equal(inc[0].zH, 160);
  assert.equal(inc[0].zHoc, 98 / 0.5);
  assert.equal(inc[2].zH, null);
  assert.deepEqual(killLines(r).map((l) => [l.species.mob_id, l.perH]), [[91001, 6], [91002, 2]]);
  const drops = dropLines(r); // the unpriced item was never dropped by a kill of ours: not listed
  assert.deepEqual(drops.map((l) => [l.item.item_id, l.perH, l.pickedShare]), [[90001, 4, 0.5], [90002, 4, 1]]);
  const cons = consumableLines(r, NO_EDITS);
  assert.deepEqual(cons.map((l) => [l.c.item_id, l.perH, l.costH, l.costHdc]), [[90100, 4, 200, 152], [90300, 2, null, null]]);
  assert.equal(perHour(3, 0), null);
  assert.equal(perHour(null, 1), null);
});

test("typed prices: whole zeny only, 0 to MAX_ZENY", () => {
  assert.equal(parsePrice("1200"), 1200);
  assert.equal(parsePrice(" 0 "), 0);
  for (const bad of ["", "-1", "1.5", "1e3", "abc", "1000000001", "12 3"]) assert.equal(parsePrice(bad), null, bad);
});

function memStore(init: Record<string, string> = {}) {
  const m = new Map(Object.entries(init));
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
    m,
  };
}

test("edited prices are kept in this browser only, and the page works without storage", () => {
  const s = memStore();
  const e = setPrice(setPrice(NO_EDITS, "sell", 90001, 99), "buy", 90100, 1200);
  assert.equal(saveEdits(s, e), true);
  assert.deepEqual(loadEdits(s), e);
  assert.equal(saveEdits(s, NO_EDITS), true);
  assert.equal(s.m.has(PRICES_KEY), false); // reset all: nothing left behind
  assert.deepEqual(loadEdits(memStore({ [PRICES_KEY]: "{not json" })), NO_EDITS);
  const odd = JSON.stringify({ sell: { "90001": 5, "../x": 1, "90002": -1, "90003": 1.5, "90004": "7" }, buy: [] });
  assert.deepEqual(loadEdits(memStore({ [PRICES_KEY]: odd })), { sell: { "90001": 5 }, buy: {} });
  const throwing = {
    getItem: () => {
      throw new Error("blocked");
    },
    setItem: () => {
      throw new Error("quota");
    },
    removeItem: () => {
      throw new Error("blocked");
    },
  };
  assert.deepEqual(loadEdits(throwing), NO_EDITS);
  assert.equal(saveEdits(throwing, e), false);
  assert.equal(saveEdits(null, e), false);
  assert.deepEqual(loadEdits(null), NO_EDITS);
});

test("formatting: grouped, units stated by the page, null stays a dash", () => {
  assert.equal(fmtInt(58223.3), "58,223");
  assert.equal(fmtOne(155.78), "155.8");
  assert.equal(fmtPct(0.5), "50.0 %");
  for (const f of [fmtInt, fmtOne, fmtPct]) {
    assert.equal(f(null), "–");
    assert.equal(f(Number.NaN), "–");
  }
  assert.equal(runLabel(doc().runs[0]), "p7 (20261111T000000)");
  assert.equal(runLabel({ ...doc().runs[0], session: "pooled (1 runs)" }), "pooled (1 runs)");
});
