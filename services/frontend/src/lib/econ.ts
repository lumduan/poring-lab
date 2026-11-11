// The /economy page (Batt, 2026-11-11: "a dashboard page of business results (P&L), because I
// will teach economics too"): the exports of scripts/econ_dash.py, served read-only by the
// backend's GET /economy/list and /economy/data/{name}, and the PURE logic the page shows them
// with. docs/econ/economics.md defines every symbol.
//
// The export carries COUNTS and the hours they are divided by; the page recomputes every rate here
// with the prices a person may edit. Edited prices live ONLY in this browser (localStorage, every
// access wrapped): never sent anywhere. Everything is keyed by NUMERIC id; display names are
// run-time data in any language and are rendered as plain text, never matched or sorted on.

import type { StorageLike } from "./flow/prefs.ts";

export const SCHEMA = "poring-lab.econ-dashboard.v1";
export const OC_LEVEL = 10;
export const DC_LEVEL = 10;
export const MIN_SHOP_SELL = 0; // conf/battle/items.conf:138 (no lab override)
export const MIN_SHOP_BUY = 1; // conf/battle/items.conf:134
export const MAX_PRICE = 1_000_000_000; // MAX_ZENY: no price above it is meaningful
export const PRICES_KEY = "poring-lab.economy.prices.v1";
export const EXPORT_KEY = "poring-lab.economy.export.v1";

// --- the server's price rules (MIRRORS scripts/econ_items.py; econ.test.ts pins them) ----------

/** Discount / Overcharge percent at level `lv` (pc.cpp:5693, :5712): 5 + 2 lv - (lv == 10);
 * 0 below level 1 (econ_items.skill_rate). */
export function skillRate(lv: number): number {
  return lv > 0 ? 5 + 2 * lv - (lv === 10 ? 1 : 0) : 0;
}

/** pc_modifysellvalue (pc.cpp:5708-5719, econ_items.overcharge): the per-unit NPC sell price with
 * Overcharge `lv`: (int32)(value x (100 + rate) / 100.) -- a double TRUNCATED toward zero -- then
 * at least MIN_SHOP_SELL. The same IEEE double operations, in the same order, as the C++ and the
 * Python. */
export function overcharge(valueSell: number, lv: number = OC_LEVEL): number {
  const rate = skillRate(lv);
  const v = rate ? Math.trunc((valueSell * (100 + rate)) / 100) : valueSell;
  return Math.max(v, MIN_SHOP_SELL);
}

/** pc_modifybuyvalue (pc.cpp:5689-5703, econ_items.discount): the per-unit NPC buy price with
 * Discount `lv`: (int32)(price x (100 - rate) / 100.), truncated, then at least MIN_SHOP_BUY. */
export function discount(price: number, lv: number = DC_LEVEL): number {
  const rate = skillRate(lv);
  const v = rate ? Math.trunc((price * (100 - rate)) / 100) : price;
  return Math.max(v, MIN_SHOP_BUY);
}

// --- the export (econ_dash.py) ------------------------------------------------------------------

export interface ItemRow {
  item_id: number;
  name: string | null;
  type: string | null;
  weight: number | null;
  sellable: boolean | null;
  sell: number | null; // NPC sell per unit (0 when the db says Trade NoSell); null: not in the table
  sell_oc: number | null; // the same with Overcharge Lv 10
  picked: number;
  stolen: number; // stolen_steal + stolen_snatcher
  stolen_steal: number;
  stolen_snatcher: number;
  income: number; // picked + stolen
  other: number; // gains with no known cause: NOT income
  staged: number; // a staged set back from a looter: NOT income
  dropped: number; // units our kills dropped
  picked_of_dropped: number; // of those, units our pickups took
}

export interface SpeciesRow {
  mob_id: number;
  name: string | null;
  kills: number;
}

export interface ConsumableRow {
  item_id: number;
  name: string | null;
  type: string | null;
  kind: string;
  used: number;
  npc_buy: number | null; // the cheapest loaded shop; null: no NPC sells it
  npc_buy_dc: number | null; // Discount Lv 10 at the cheapest shop that gives it
}

export interface RunFlow {
  runner: string | null; // e.g. the runner's version
  strategy: string | null;
  search: string | null;
  label: string | null; // the run's own label (the session id's tail)
  flags: string[]; // the run's flags (its manifest's fixes)
}

export interface RunEntry {
  session: string | null;
  started: string | null; // the judged window's start, wall clock (ICT), "YYYY-MM-DD HH:MM:SS"
  ended: string | null; // its end
  flow: RunFlow | null;
  map: string | null;
  char: string | null;
  minutes: number | null;
  hours: number;
  kills: number;
  deaths: number;
  items: ItemRow[];
  species: SpeciesRow[];
  consumables: ConsumableRow[];
  why: Record<string, unknown>;
  runs?: number;
}

export interface Rule {
  level: number;
  rate_pct: number;
  min_price: number;
  source?: string;
}

export interface DashExport {
  schema: string;
  name: string;
  exported_at: string | null;
  sources: Record<string, unknown>;
  rules: { overcharge: Rule; discount: Rule };
  runs: RunEntry[];
  pooled: RunEntry;
}

export interface ExportEntry {
  name: string;
  bytes: number;
  modified: number;
}

function isObj(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

function num(x: unknown, what: string): number {
  if (typeof x !== "number" || !Number.isFinite(x)) throw new Error(`${what}: not a number`);
  return x;
}

function numOrNull(x: unknown, what: string): number | null {
  return x === null || x === undefined ? null : num(x, what);
}

function strOrNull(x: unknown): string | null {
  return typeof x === "string" ? x : x === null || x === undefined ? null : String(x);
}

function arr(x: unknown, what: string): unknown[] {
  if (!Array.isArray(x)) throw new Error(`${what}: not a list`);
  return x;
}

function item(x: unknown, i: number): ItemRow {
  if (!isObj(x)) throw new Error(`item ${i}: not an object`);
  const w = `item ${i}`;
  return {
    item_id: num(x.item_id, `${w} id`),
    name: strOrNull(x.name),
    type: strOrNull(x.type),
    weight: numOrNull(x.weight, `${w} weight`),
    sellable: typeof x.sellable === "boolean" ? x.sellable : null,
    sell: numOrNull(x.sell, `${w} sell`),
    sell_oc: numOrNull(x.sell_oc, `${w} sell_oc`),
    picked: num(x.picked, `${w} picked`),
    stolen: num(x.stolen, `${w} stolen`),
    stolen_steal: num(x.stolen_steal ?? 0, `${w} stolen_steal`),
    stolen_snatcher: num(x.stolen_snatcher ?? 0, `${w} stolen_snatcher`),
    income: num(x.income, `${w} income`),
    other: num(x.other ?? 0, `${w} other`),
    staged: num(x.staged ?? 0, `${w} staged`),
    dropped: num(x.dropped, `${w} dropped`),
    picked_of_dropped: num(x.picked_of_dropped, `${w} picked_of_dropped`),
  };
}

function species(x: unknown, i: number): SpeciesRow {
  if (!isObj(x)) throw new Error(`species ${i}: not an object`);
  return { mob_id: num(x.mob_id, `species ${i} id`), name: strOrNull(x.name), kills: num(x.kills, `species ${i} kills`) };
}

function consumable(x: unknown, i: number): ConsumableRow {
  if (!isObj(x)) throw new Error(`consumable ${i}: not an object`);
  const w = `consumable ${i}`;
  return {
    item_id: num(x.item_id, `${w} id`),
    name: strOrNull(x.name),
    type: strOrNull(x.type),
    kind: strOrNull(x.kind) ?? "other",
    used: num(x.used, `${w} used`),
    npc_buy: numOrNull(x.npc_buy, `${w} npc_buy`),
    npc_buy_dc: numOrNull(x.npc_buy_dc, `${w} npc_buy_dc`),
  };
}

/** A run's flow (Batt 2026-11-11: "which flow the bot ran, when it started, when it ended"); null
 * for the pooled row or an older export. Every value is plain text. */
export function flowOf(x: unknown): RunFlow | null {
  if (!isObj(x)) return null;
  const flags = Array.isArray(x.flags) ? x.flags.filter((f): f is string => typeof f === "string") : [];
  return {
    runner: strOrNull(x.runner),
    strategy: strOrNull(x.strategy),
    search: strOrNull(x.search),
    label: strOrNull(x.label),
    flags,
  };
}

/** One line for the runs table: "label (runner, strategy search)". */
export function flowText(f: RunFlow | null): string {
  if (!f) return "-";
  const how = [f.runner, [f.strategy, f.search].filter(Boolean).join(" ")].filter(Boolean).join(", ");
  return [f.label ?? "", how ? `(${how})` : ""].filter(Boolean).join(" ") || "-";
}

function run(x: unknown, what: string): RunEntry {
  if (!isObj(x)) throw new Error(`${what}: not an object`);
  return {
    session: strOrNull(x.session),
    started: strOrNull(x.started),
    ended: strOrNull(x.ended),
    flow: flowOf(x.flow),
    map: strOrNull(x.map),
    char: strOrNull(x.char),
    minutes: numOrNull(x.minutes, `${what} minutes`),
    hours: num(x.hours, `${what} hours`),
    kills: num(x.kills, `${what} kills`),
    deaths: num(x.deaths ?? 0, `${what} deaths`),
    items: arr(x.items, `${what} items`).map(item),
    species: arr(x.species, `${what} species`).map(species),
    consumables: arr(x.consumables, `${what} consumables`).map(consumable),
    why: isObj(x.why) ? x.why : {},
    runs: typeof x.runs === "number" ? x.runs : undefined,
  };
}

function rule(x: unknown, level: number, minPrice: number): Rule {
  if (!isObj(x)) return { level, rate_pct: skillRate(level), min_price: minPrice };
  const lv = typeof x.level === "number" ? x.level : level;
  return {
    level: lv,
    rate_pct: typeof x.rate_pct === "number" ? x.rate_pct : skillRate(lv),
    min_price: typeof x.min_price === "number" ? x.min_price : minPrice,
    source: strOrNull(x.source) ?? undefined,
  };
}

/** An export as the backend serves it, checked field by field; throws with the first problem. */
export function parseExport(x: unknown): DashExport {
  if (!isObj(x)) throw new Error("not an export (not an object)");
  if (x.schema !== SCHEMA) throw new Error(`unknown schema ${JSON.stringify(x.schema)} (want ${SCHEMA})`);
  const rules = isObj(x.rules) ? x.rules : {};
  return {
    schema: SCHEMA,
    name: strOrNull(x.name) ?? "",
    exported_at: strOrNull(x.exported_at),
    sources: isObj(x.sources) ? x.sources : {},
    rules: {
      overcharge: rule(rules.overcharge, OC_LEVEL, MIN_SHOP_SELL),
      discount: rule(rules.discount, DC_LEVEL, MIN_SHOP_BUY),
    },
    runs: arr(x.runs, "runs").map((r, i) => run(r, `run ${i}`)),
    pooled: run(x.pooled, "pooled"),
  };
}

/** GET /economy/list's answer: the exports, newest first (the backend's order). */
export function parseList(x: unknown): ExportEntry[] {
  if (!isObj(x)) return [];
  return arr(x.exports ?? [], "exports").flatMap((e) =>
    isObj(e) && typeof e.name === "string"
      ? [{ name: e.name, bytes: typeof e.bytes === "number" ? e.bytes : 0, modified: typeof e.modified === "number" ? e.modified : 0 }]
      : [],
  );
}

// --- prices a person edits (this browser only) -----------------------------------------------------

export interface PriceEdits {
  sell: Record<string, number>; // item id -> NPC sell per unit
  buy: Record<string, number>; // item id -> NPC buy per unit
}

export const NO_EDITS: PriceEdits = { sell: {}, buy: {} };

/** A typed price: a whole number of zeny, 0 ... MAX_PRICE; anything else is null (not taken). */
export function parsePrice(text: string): number | null {
  const t = text.trim();
  if (!/^\d{1,10}$/.test(t)) return null;
  const v = Number(t);
  return v <= MAX_PRICE ? v : null;
}

/** A new edits object with `id`'s `side` price set (`value` null: back to the NPC price). */
export function setPrice(edits: PriceEdits, side: "sell" | "buy", id: number, value: number | null): PriceEdits {
  const next = { ...edits[side] };
  if (value === null) delete next[String(id)];
  else next[String(id)] = value;
  return { ...edits, [side]: next };
}

export function editedSell(edits: PriceEdits, id: number): number | null {
  return edits.sell[String(id)] ?? null;
}

export function editedBuy(edits: PriceEdits, id: number): number | null {
  return edits.buy[String(id)] ?? null;
}

/** The NPC sell price in force: the edited one, else the table's (null: not in the table). */
export function sellPrice(it: ItemRow, edits: PriceEdits): number | null {
  return editedSell(edits, it.item_id) ?? it.sell;
}

/** The Overcharge price in force: from an edited sell price by the rule, else the table's. */
export function ocPrice(it: ItemRow, edits: PriceEdits, lv: number = OC_LEVEL): number | null {
  const e = editedSell(edits, it.item_id);
  if (e !== null) return overcharge(e, lv);
  return it.sell_oc ?? (it.sell === null ? null : overcharge(it.sell, lv));
}

/** The NPC buy price in force: the edited one, else the cheapest shop's (null: no NPC sells it). */
export function buyPrice(c: ConsumableRow, edits: PriceEdits): number | null {
  return editedBuy(edits, c.item_id) ?? c.npc_buy;
}

/** The Discount price in force: from an edited buy price by the rule; else the table's (the
 * cheapest shop that gives the discount, which can be another shop than the cheapest plain one). */
export function dcPrice(c: ConsumableRow, edits: PriceEdits, lv: number = DC_LEVEL): number | null {
  const e = editedBuy(edits, c.item_id);
  if (e !== null) return discount(e, lv);
  return c.npc_buy_dc ?? (c.npc_buy === null ? null : discount(c.npc_buy, lv));
}

function validPrices(x: unknown): Record<string, number> {
  const out: Record<string, number> = {};
  if (!isObj(x)) return out;
  for (const [k, v] of Object.entries(x)) {
    if (/^\d{1,9}$/.test(k) && typeof v === "number" && Number.isInteger(v) && v >= 0 && v <= MAX_PRICE) out[k] = v;
  }
  return out;
}

/** The stored edits (anything malformed is dropped); none when the storage is missing or throws. */
export function loadEdits(store: StorageLike | null): PriceEdits {
  try {
    const raw = store?.getItem(PRICES_KEY);
    if (!raw) return NO_EDITS;
    const x: unknown = JSON.parse(raw);
    return isObj(x) ? { sell: validPrices(x.sell), buy: validPrices(x.buy) } : NO_EDITS;
  } catch {
    return NO_EDITS;
  }
}

/** Store the edits; false when the storage refused (the page works on, unremembered). */
export function saveEdits(store: StorageLike | null, edits: PriceEdits): boolean {
  try {
    if (!store) return false;
    if (!Object.keys(edits.sell).length && !Object.keys(edits.buy).length) store.removeItem(PRICES_KEY);
    else store.setItem(PRICES_KEY, JSON.stringify(edits));
    return true;
  } catch {
    return false;
  }
}

export function editCount(edits: PriceEdits): number {
  return Object.keys(edits.sell).length + Object.keys(edits.buy).length;
}

// --- the tables ----------------------------------------------------------------------------------

/** count / hours, or null (no hours: never a division by zero). */
export function perHour(n: number | null, hours: number): number | null {
  return n === null || !(hours > 0) ? null : n / hours;
}

function byValueThenId<T>(value: (x: T) => number | null, id: (x: T) => number) {
  return (a: T, b: T) => {
    const va = value(a) ?? -Infinity;
    const vb = value(b) ?? -Infinity;
    return vb !== va ? vb - va : id(a) - id(b);
  };
}

export interface IncomeLine {
  item: ItemRow;
  perH: number | null; // income units / h
  sell: number | null;
  oc: number | null;
  zH: number | null; // zeny / h at the NPC sell price
  zHoc: number | null; // zeny / h at the Overcharge price
  edited: boolean;
}

/** Income: every item we gained as income (picked + stolen), most zeny / h first, then id. */
export function incomeLines(run: RunEntry, edits: PriceEdits, ocLv: number = OC_LEVEL): IncomeLine[] {
  return run.items
    .filter((it) => it.income > 0)
    .map((it) => {
      const sell = sellPrice(it, edits);
      const oc = ocPrice(it, edits, ocLv);
      return {
        item: it,
        perH: perHour(it.income, run.hours),
        sell,
        oc,
        zH: sell === null ? null : perHour(it.income * sell, run.hours),
        zHoc: oc === null ? null : perHour(it.income * oc, run.hours),
        edited: editedSell(edits, it.item_id) !== null,
      };
    })
    .sort(byValueThenId((l) => l.zH, (l) => l.item.item_id));
}

export interface KillLine {
  species: SpeciesRow;
  perH: number | null;
}

export function killLines(run: RunEntry): KillLine[] {
  return run.species
    .map((s) => ({ species: s, perH: perHour(s.kills, run.hours) }))
    .sort(byValueThenId((l) => l.species.kills, (l) => l.species.mob_id));
}

export interface DropLine {
  item: ItemRow;
  perH: number | null;
  pickedShare: number | null; // picked_of_dropped / dropped
}

/** Drops: what our kills dropped per item, and the share our pickups took. */
export function dropLines(run: RunEntry): DropLine[] {
  return run.items
    .filter((it) => it.dropped > 0)
    .map((it) => ({ item: it, perH: perHour(it.dropped, run.hours), pickedShare: it.picked_of_dropped / it.dropped }))
    .sort(byValueThenId((l) => l.item.dropped, (l) => l.item.item_id));
}

export interface ConsumableLine {
  c: ConsumableRow;
  perH: number | null;
  buy: number | null;
  dc: number | null;
  costH: number | null;
  costHdc: number | null;
  edited: boolean;
}

export function consumableLines(run: RunEntry, edits: PriceEdits, dcLv: number = DC_LEVEL): ConsumableLine[] {
  return run.consumables
    .map((c) => {
      const buy = buyPrice(c, edits);
      const dc = dcPrice(c, edits, dcLv);
      return {
        c,
        perH: perHour(c.used, run.hours),
        buy,
        dc,
        costH: buy === null ? null : perHour(c.used * buy, run.hours),
        costHdc: dc === null ? null : perHour(c.used * dc, run.hours),
        edited: editedBuy(edits, c.item_id) !== null,
      };
    })
    .sort(byValueThenId((l) => l.costH, (l) => l.c.item_id));
}

export interface Summary {
  hours: number;
  killsH: number | null;
  grossH: number | null; // gross plain: sum income x NPC sell / h
  grossOcH: number | null; // gross with Overcharge
  costH: number | null; // cost plain: sum used x NPC buy / h
  costDcH: number | null; // cost with Discount
  netH: number | null; // gross plain - cost plain
  netBestH: number | null; // gross Overcharge - cost Discount
  unpricedIncome: number[]; // item ids left out of the gross (no price)
  unpricedCost: number[]; // item ids left out of the cost (no NPC sells them, none typed)
  notIncome: { other: number; staged: number };
}

/** The P&L per hour (the same sums econ_dash.totals makes at the table's prices). */
export function summary(run: RunEntry, edits: PriceEdits, ocLv: number = OC_LEVEL, dcLv: number = DC_LEVEL): Summary {
  const inc = incomeLines(run, edits, ocLv);
  const cons = consumableLines(run, edits, dcLv);
  const sum = (xs: (number | null)[]) => xs.reduce<number>((a, x) => a + (x ?? 0), 0);
  const h = run.hours;
  const grossH = perHour(sum(inc.map((l) => (l.sell === null ? null : l.item.income * l.sell))), h);
  const grossOcH = perHour(sum(inc.map((l) => (l.oc === null ? null : l.item.income * l.oc))), h);
  const costH = perHour(sum(cons.map((l) => (l.buy === null ? null : l.c.used * l.buy))), h);
  const costDcH = perHour(sum(cons.map((l) => (l.dc === null ? null : l.c.used * l.dc))), h);
  const sub = (a: number | null, b: number | null) => (a === null || b === null ? null : a - b);
  return {
    hours: h,
    killsH: perHour(run.kills, h),
    grossH,
    grossOcH,
    costH,
    costDcH,
    netH: sub(grossH, costH),
    netBestH: sub(grossOcH, costDcH),
    unpricedIncome: inc.filter((l) => l.sell === null).map((l) => l.item.item_id),
    unpricedCost: cons.filter((l) => l.buy === null).map((l) => l.c.item_id),
    notIncome: { other: sum(run.items.map((it) => it.other)), staged: sum(run.items.map((it) => it.staged)) },
  };
}

/** The runs a person can pick: index -1 is the pooled entry, else the run's index. */
export function runAt(doc: DashExport, index: number): RunEntry {
  return index >= 0 && index < doc.runs.length ? doc.runs[index] : doc.pooled;
}

/** A run's short label for the picker: its pilot tag when the session id ends in one, else the
 * session id (text only). */
export function runLabel(r: RunEntry): string {
  const s = r.session ?? "?";
  const m = /-(p\d+)$/.exec(s);
  return m ? `${m[1]} (${s.slice(0, 15)})` : s;
}

// --- formatting (English UI; units stated; null stays null, never a fake zero) ----------------------

const INT = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const ONE = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export const DASH = "–";

export function fmtInt(n: number | null | undefined): string {
  return n === null || n === undefined || !Number.isFinite(n) ? DASH : INT.format(n);
}

export function fmtOne(n: number | null | undefined): string {
  return n === null || n === undefined || !Number.isFinite(n) ? DASH : ONE.format(n);
}

export function fmtPct(share: number | null | undefined): string {
  return share === null || share === undefined || !Number.isFinite(share) ? DASH : `${ONE.format(share * 100)} %`;
}

/** The multiplier a rule applies, as course text: "1.24" (Overcharge), "0.76" (Discount). */
export function factorText(ratePct: number, up: boolean): string {
  return ((up ? 100 + ratePct : 100 - ratePct) / 100).toFixed(2);
}
