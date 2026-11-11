"use client";

import { type ReactNode, useEffect, useMemo, useState } from "react";

import {
  consumableLines,
  type DashExport,
  DASH,
  dropLines,
  editCount,
  type ExportEntry,
  EXPORT_KEY,
  factorText,
  fmtInt,
  fmtOne,
  fmtPct,
  incomeLines,
  killLines,
  loadEdits,
  NO_EDITS,
  parseExport,
  parseList,
  parsePrice,
  type PriceEdits,
  type RunEntry,
  runAt,
  runLabel,
  saveEdits,
  setPrice,
  summary,
  flowText,
} from "@/lib/econ";
import { browserStorage, readText, writeChoice } from "@/lib/flow/prefs";
import { backendHttpBase } from "@/lib/ws";

const TH = "px-2 py-1.5 text-left text-xs font-semibold text-neutral-400";
const THR = "px-2 py-1.5 text-right text-xs font-semibold text-neutral-400";
const TD = "px-2 py-1 align-top";
const TDR = "px-2 py-1 text-right align-top font-mono tabular-nums";

/** An item or a monster: its run-time name (any language, plain text) and its numeric id. */
function Named({ name, id, kind, sub }: { name: string | null; id: number; kind: string; sub?: string | null }) {
  return (
    <span className="flex flex-col">
      <span className="break-words">
        {name ?? <span className="text-neutral-500">{kind}</span>} <span className="font-mono text-xs text-neutral-500">#{id}</span>
      </span>
      {sub && <span className="text-xs text-neutral-500">{sub}</span>}
    </span>
  );
}

/** A price a person may edit (this browser only). It commits every valid whole number as it is
 * typed; anything else is not taken and the field shows the price in force again on blur. */
function PriceInput({
  value,
  edited,
  label,
  onCommit,
}: {
  value: number | null;
  edited: boolean;
  label: string;
  onCommit: (v: number | null) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const shown = draft ?? (value === null ? "" : String(value));
  const invalid = draft !== null && draft.trim() !== "" && parsePrice(draft) === null;
  return (
    <span className="inline-flex items-center justify-end gap-1">
      <input
        type="text"
        inputMode="numeric"
        aria-label={label}
        aria-invalid={invalid || undefined}
        value={shown}
        placeholder="no price"
        onChange={(e) => {
          setDraft(e.target.value);
          const v = parsePrice(e.target.value);
          if (v !== null) onCommit(v);
        }}
        onBlur={() => setDraft(null)}
        className={`w-24 rounded border px-1.5 py-0.5 text-right font-mono tabular-nums ${
          invalid ? "border-red-500" : edited ? "border-amber-500 bg-amber-950/40" : "border-neutral-700 bg-neutral-900"
        }`}
      />
      {edited ? (
        <button
          type="button"
          onClick={() => {
            setDraft(null);
            onCommit(null);
          }}
          title="Reset to the NPC price"
          className="rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-amber-300 hover:bg-neutral-700"
        >
          reset
        </button>
      ) : (
        <span className="w-[2.75rem]" aria-hidden />
      )}
    </span>
  );
}

function Section({ title, formula, children, note }: { title: string; formula: ReactNode; children: ReactNode; note?: ReactNode }) {
  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-3" aria-label={title}>
      <h2 className="mb-2 text-sm font-semibold text-neutral-300">{title}</h2>
      <div className="overflow-x-auto">{children}</div>
      {note && <div className="mt-2 text-xs text-amber-300">{note}</div>}
      <p className="mt-2 font-mono text-xs text-neutral-500">{formula}</p>
    </section>
  );
}

function Empty({ cols, text }: { cols: number; text: string }) {
  return (
    <tr>
      <td colSpan={cols} className="px-2 py-2 text-neutral-500">
        {text}
      </td>
    </tr>
  );
}

function Tile({ title, value, tone = "plain", formula }: { title: string; value: number | null; tone?: "plain" | "net"; formula: string }) {
  const sign = tone === "net" && value !== null ? (value < 0 ? "loss" : "profit") : null;
  const color = tone === "net" && value !== null ? (value < 0 ? "text-red-300" : "text-emerald-300") : "text-neutral-100";
  return (
    <div className="flex flex-col rounded-lg border border-neutral-800 bg-neutral-900/60 p-3">
      <span className="text-xs text-neutral-400">{title}</span>
      <span className={`font-mono text-xl font-semibold tabular-nums ${color}`}>
        {value === null ? DASH : `${fmtInt(value)} z / h`}
        {sign && <span className="ml-2 text-xs font-semibold uppercase">({sign})</span>}
      </span>
      <span className="mt-1 font-mono text-xs text-neutral-500">{formula}</span>
    </div>
  );
}

function whyLines(why: Record<string, unknown>): string[] {
  return Object.entries(why).flatMap(([k, v]) => {
    if (typeof v === "string") return [`${k}: ${v}`];
    if (v && typeof v === "object") return Object.entries(v as Record<string, unknown>).map(([s, t]) => `${k} (${s.slice(0, 15)}…${s.slice(-4)}): ${String(t)}`);
    return [`${k}: ${String(v)}`];
  });
}

function shortRef(x: unknown): string {
  return typeof x === "string" ? x.slice(0, 10) : DASH;
}

/** One run (or the pool) of an export: the facts, the P&L tiles and the four tables. Pure but for
 * the price inputs, which hand every edit to `update`. */
export function RunView({
  doc,
  name,
  runIx,
  edits,
  update,
}: {
  doc: DashExport;
  name: string;
  runIx: number;
  edits: PriceEdits;
  update: (next: PriceEdits) => void;
}) {
  const current = doc;
  const run: RunEntry = runAt(doc, runIx);
  const oc = doc.rules.overcharge;
  const dc = doc.rules.discount;
  const s = summary(run, edits, oc.level, dc.level);
  const income = incomeLines(run, edits, oc.level);
  const kills = killLines(run);
  const drops = dropLines(run);
  const cons = consumableLines(run, edits, dc.level);
  const ocText = `Overcharge Lv ${oc.level}: NPC sell x ${factorText(oc.rate_pct, true)} per unit, truncated toward zero as the server does, at least ${oc.min_price}`;
  const dcText = `Discount Lv ${dc.level}: NPC buy x ${factorText(dc.rate_pct, false)} per unit, truncated toward zero, at least ${dc.min_price}`;
  const table = (doc.sources.items_table ?? {}) as Record<string, unknown>;
  return (
    <>
      <Section
        title="Runs"
        formula="judged window: the run's start to its end (events run_start..run_end); kills / h = our kills / judged hours; a kill = the monster's death <= 1.5 s after our damaging hit (packets)"
      >
        <table className="w-full min-w-[40rem] text-sm">
          <thead>
            <tr className="border-b border-neutral-800">
              <th scope="col" className={TH}>Run</th>
              <th scope="col" className={TH}>Flow</th>
              <th scope="col" className={TH}>Start</th>
              <th scope="col" className={TH}>End</th>
              <th scope="col" className={TH}>Map</th>
              <th scope="col" className={TH}>Character</th>
              <th scope="col" className={THR}>Judged minutes</th>
              <th scope="col" className={THR}>Kills</th>
              <th scope="col" className={THR}>Kills / h</th>
              <th scope="col" className={THR}>Deaths</th>
            </tr>
          </thead>
          <tbody>
            {[...current.runs.map((r, i) => [r, i] as const), [current.pooled, -1] as const].map(([r, i]) => (
              <tr key={`${r.session}-${i}`} className={`border-b border-neutral-900 ${i === runIx ? "bg-neutral-800/60" : ""}`}>
                <td className={`${TD} font-mono text-xs`}>{i === -1 ? `Pooled (${current.runs.length} runs)` : r.session}</td>
                <td className={`${TD} text-xs`} title={r.flow ? r.flow.flags.join(", ") : undefined}>{flowText(r.flow)}</td>
                <td className={`${TD} font-mono text-xs`}>{r.started ?? "-"}</td>
                <td className={`${TD} font-mono text-xs`}>{r.ended ?? "-"}</td>
                <td className={TD}>{r.map}</td>
                <td className={TD}>{r.char}</td>
                <td className={TDR}>{fmtOne(r.minutes)}</td>
                <td className={TDR}>{fmtInt(r.kills)}</td>
                <td className={TDR}>{fmtOne(r.hours > 0 ? r.kills / r.hours : null)}</td>
                <td className={TDR}>{fmtInt(r.deaths)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <section aria-label="Profit and loss per hour" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Tile title="Gross, NPC sell" value={s.grossH} formula="sum (picked + stolen) x NPC sell / hours" />
        <Tile title="Cost, NPC buy" value={s.costH} formula="sum used x NPC buy / hours" />
        <Tile title="Net, plain" value={s.netH} tone="net" formula="gross plain - cost plain" />
        <Tile title={`Gross, Overcharge Lv ${oc.level}`} value={s.grossOcH} formula="sum (picked + stolen) x Overcharge price / hours" />
        <Tile title={`Cost, Discount Lv ${dc.level}`} value={s.costDcH} formula="sum used x Discount price / hours" />
        <Tile title="Net, best" value={s.netBestH} tone="net" formula="gross at Overcharge - cost at Discount" />
      </section>
      <p className="text-xs text-neutral-500">
        {fmtOne(s.killsH)} kills / h over {fmtOne(s.hours * 60)} judged minutes. &quot;Best&quot; is what a Merchant with both skills at Lv {oc.level} would
        make; our characters have neither. Values are mark-to-market: what the items would fetch, not zeny actually received.
        {s.unpricedIncome.length > 0 && ` Left out of the gross (no price): item ${s.unpricedIncome.map((i) => `#${i}`).join(", ")}.`}
        {s.unpricedCost.length > 0 && ` Left out of the cost (no NPC sells it): item ${s.unpricedCost.map((i) => `#${i}`).join(", ")}.`}
      </p>

      <Section
        title="Income"
        formula={`total = picked + stolen (Steal + Snatcher); per hour = total / hours; zeny / h = total x price / hours. ${ocText}.`}
        note={
          s.notIncome.other + s.notIncome.staged > 0
            ? `Not income, not counted: ${s.notIncome.other} gain(s) with no known cause, ${s.notIncome.staged} staged item(s) back from a looter.`
            : null
        }
      >
        <table className="w-full min-w-[56rem] text-sm">
          <thead>
            <tr className="border-b border-neutral-800">
              <th scope="col" className={TH}>Item</th>
              <th scope="col" className={THR}>Picked</th>
              <th scope="col" className={THR}>Stolen</th>
              <th scope="col" className={THR}>Total</th>
              <th scope="col" className={THR}>Per hour</th>
              <th scope="col" className={THR}>NPC sell (z)</th>
              <th scope="col" className={THR}>Overcharge (z)</th>
              <th scope="col" className={THR}>z / h plain</th>
              <th scope="col" className={THR}>z / h Overcharge</th>
            </tr>
          </thead>
          <tbody>
            {income.length === 0 && <Empty cols={9} text="No item gained in this window." />}
            {income.map((l) => (
              <tr key={l.item.item_id} className="border-b border-neutral-900">
                <td className={TD}>
                  <Named name={l.item.name} id={l.item.item_id} kind="item" sub={l.item.sellable === false ? `${l.item.type ?? ""} · NPCs do not buy it` : l.item.type} />
                </td>
                <td className={TDR}>{fmtInt(l.item.picked)}</td>
                <td className={TDR} title={`Steal ${l.item.stolen_steal}, Snatcher ${l.item.stolen_snatcher}`}>
                  {fmtInt(l.item.stolen)}
                </td>
                <td className={TDR}>{fmtInt(l.item.income)}</td>
                <td className={TDR}>{fmtOne(l.perH)}</td>
                <td className={TDR}>
                  <PriceInput
                    value={l.sell}
                    edited={l.edited}
                    label={`NPC sell price of item ${l.item.item_id}`}
                    onCommit={(v) => update(setPrice(edits, "sell", l.item.item_id, v === l.item.sell ? null : v))}
                  />
                </td>
                <td className={TDR}>{fmtInt(l.oc)}</td>
                <td className={TDR}>{fmtInt(l.zH)}</td>
                <td className={TDR}>{fmtInt(l.zHoc)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <Section title="Kills" formula="kills / h = our kills of the species / hours (the species: the monster's id when it last appeared before the kill)">
          <table className="w-full min-w-[24rem] text-sm">
            <thead>
              <tr className="border-b border-neutral-800">
                <th scope="col" className={TH}>Species</th>
                <th scope="col" className={THR}>Kills</th>
                <th scope="col" className={THR}>Per hour</th>
              </tr>
            </thead>
            <tbody>
              {kills.length === 0 && <Empty cols={3} text="No kill of ours in this window." />}
              {kills.map((l) => (
                <tr key={l.species.mob_id} className="border-b border-neutral-900">
                  <td className={TD}>
                    {l.species.mob_id === -1 ? (
                      <span className="text-neutral-500">unknown species</span>
                    ) : (
                      <Named name={l.species.name} id={l.species.mob_id} kind="monster" />
                    )}
                  </td>
                  <td className={TDR}>{fmtInt(l.species.kills)}</td>
                  <td className={TDR}>{fmtOne(l.perH)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <Section
          title="Drops"
          formula="dropped = units our kills dropped (fell -0.6..+1.5 s around the death, <= 4 cells); per hour = dropped / hours; picked share = units of those our pickups took / dropped"
        >
          <table className="w-full min-w-[28rem] text-sm">
            <thead>
              <tr className="border-b border-neutral-800">
                <th scope="col" className={TH}>Item</th>
                <th scope="col" className={THR}>Dropped by our kills</th>
                <th scope="col" className={THR}>Per hour</th>
                <th scope="col" className={THR}>Picked share</th>
              </tr>
            </thead>
            <tbody>
              {drops.length === 0 && <Empty cols={4} text="Our kills dropped nothing in this window." />}
              {drops.map((l) => (
                <tr key={l.item.item_id} className="border-b border-neutral-900">
                  <td className={TD}>
                    <Named name={l.item.name} id={l.item.item_id} kind="item" sub={l.item.type} />
                  </td>
                  <td className={TDR}>{fmtInt(l.item.dropped)}</td>
                  <td className={TDR}>{fmtOne(l.perH)}</td>
                  <td className={TDR}>{fmtPct(l.pickedShare)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      </div>

      <Section
        title="Consumables"
        formula={`per hour = used / hours; cost / h = used x price / hours (our successful item uses, packets). ${dcText}; unedited, the cheapest shop that gives the discount.`}
      >
        <table className="w-full min-w-[52rem] text-sm">
          <thead>
            <tr className="border-b border-neutral-800">
              <th scope="col" className={TH}>Item</th>
              <th scope="col" className={THR}>Used</th>
              <th scope="col" className={THR}>Per hour</th>
              <th scope="col" className={THR}>NPC buy (z)</th>
              <th scope="col" className={THR}>Discount (z)</th>
              <th scope="col" className={THR}>Cost / h plain</th>
              <th scope="col" className={THR}>Cost / h Discount</th>
            </tr>
          </thead>
          <tbody>
            {cons.length === 0 && <Empty cols={7} text="No item used in this window (no Fly Wing, no potion): the cost is 0." />}
            {cons.map((l) => (
              <tr key={l.c.item_id} className="border-b border-neutral-900">
                <td className={TD}>
                  <Named name={l.c.name} id={l.c.item_id} kind="item" sub={[l.c.type, l.c.kind].filter(Boolean).join(" · ")} />
                </td>
                <td className={TDR}>{fmtInt(l.c.used)}</td>
                <td className={TDR}>{fmtOne(l.perH)}</td>
                <td className={TDR}>
                  <PriceInput
                    value={l.buy}
                    edited={l.edited}
                    label={`NPC buy price of item ${l.c.item_id}`}
                    onCommit={(v) => update(setPrice(edits, "buy", l.c.item_id, v === l.c.npc_buy ? null : v))}
                  />
                </td>
                <td className={TDR}>{fmtInt(l.dc)}</td>
                <td className={TDR}>{fmtInt(l.costH)}</td>
                <td className={TDR}>{fmtInt(l.costHdc)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      {Object.keys(run.why).length > 0 && (
        <section className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-3" aria-label="Notes">
          <h2 className="mb-1 text-sm font-semibold text-neutral-300">Notes from the judges</h2>
          <ul className="list-disc pl-5 font-mono text-xs text-neutral-400">
            {whyLines(run.why).map((t, i) => (
              <li key={i} className="break-words">
                {t}
              </li>
            ))}
          </ul>
        </section>
      )}
      <p className="font-mono text-xs text-neutral-500">
        export {name} · made {current.exported_at ?? DASH} · item table rAthena {shortRef(table.rathena_ref)} ({String(table.mode ?? DASH)}), built{" "}
        {String(table.built_at ?? DASH)}
      </p>
    </>
  );
}

/** Economy (Batt 2026-11-11): a run's business results at FIXED NPC prices, from the exports of
 * scripts/econ_dash.py (GET /economy/*, read-only). The NPC prices can be edited per item; the edits
 * live in this browser only and are never sent. Nothing here sends input. */
export default function EconomyDashboard({ backendUrl }: { backendUrl: string | null }) {
  const store = useMemo(() => browserStorage(), []);
  const [list, setList] = useState<ExportEntry[] | null>(null);
  const [name, setName] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<{ name: string; doc: DashExport } | null>(null);
  const [runIx, setRunIx] = useState(-1); // -1: pooled
  const [edits, setEdits] = useState<PriceEdits>(NO_EDITS);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(true);

  useEffect(() => {
    let alive = true;
    const base = backendHttpBase(backendUrl);
    void (async () => {
      try {
        const r = await fetch(`${base}/economy/list`, { cache: "no-store" });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const entries = parseList(await r.json());
        if (!alive) return;
        const remembered = readText(store, EXPORT_KEY);
        setEdits(loadEdits(store)); // this browser's prices, applied with the first answer
        setList(entries);
        setName((prev) => prev ?? (entries.find((e) => e.name === remembered) ?? entries[0])?.name ?? null);
        setError(null);
      } catch (e) {
        if (alive) {
          setEdits(loadEdits(store));
          setList([]);
          setError(e instanceof Error ? e.message : String(e));
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [backendUrl, store]);

  useEffect(() => {
    if (name === null) return;
    let alive = true;
    const base = backendHttpBase(backendUrl);
    void (async () => {
      try {
        const r = await fetch(`${base}/economy/data/${encodeURIComponent(name)}`, { cache: "no-store" });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const d = parseExport(await r.json());
        if (alive) {
          setLoaded({ name, doc: d }); // keyed by the file's name, whatever the JSON calls itself
          setError(null);
        }
      } catch (e) {
        if (alive) setError(`${name}: ${e instanceof Error ? e.message : String(e)}`);
      }
    })();
    return () => {
      alive = false;
    };
  }, [backendUrl, name]);

  const update = (next: PriceEdits) => {
    setEdits(next);
    setSaved(saveEdits(store, next));
  };
  const pick = (n: string) => {
    setName(n);
    setRunIx(-1);
    writeChoice(store, EXPORT_KEY, n);
  };

  const current = loaded !== null && loaded.name === name ? loaded.doc : null;
  const nEdits = editCount(edits);

  return (
    <main className="mx-auto flex max-w-[1600px] flex-col gap-3 p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold tracking-tight">Economy</h1>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <label className="flex items-center gap-2">
            <span className="text-neutral-400">Export</span>
            <select
              value={name ?? ""}
              onChange={(e) => pick(e.target.value)}
              className="max-w-[16rem] rounded-md border border-neutral-700 bg-neutral-900 px-2 py-1"
              disabled={!list?.length}
            >
              {!list?.length && <option value="">{list === null ? "loading…" : "no export"}</option>}
              {list?.map((e) => (
                <option key={e.name} value={e.name}>
                  {e.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2">
            <span className="text-neutral-400">Run</span>
            <select
              value={runIx}
              onChange={(e) => setRunIx(Number(e.target.value))}
              className="max-w-[18rem] rounded-md border border-neutral-700 bg-neutral-900 px-2 py-1"
              disabled={!current}
            >
              <option value={-1}>Pooled ({current?.runs.length ?? 0} runs)</option>
              {current?.runs.map((r, i) => (
                <option key={`${r.session}-${i}`} value={i}>
                  {runLabel(r)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => update(NO_EDITS)}
            disabled={nEdits === 0}
            className="rounded-md bg-neutral-800 px-3 py-1 text-white hover:bg-neutral-700 disabled:opacity-40"
          >
            Reset all prices{nEdits ? ` (${nEdits} edited)` : ""}
          </button>
        </div>
      </header>

      {error && <p className="font-mono text-xs text-red-300">backend: {error}</p>}
      {list !== null && list.length === 0 && !error && (
        <p className="text-sm text-neutral-400">
          No export yet. Make one on the lab host: <span className="font-mono">scripts/econ_dash.py export SESSION_DIR ... --name NAME</span>
        </p>
      )}
      <p className="text-xs text-neutral-500">
        Fixed NPC prices only (no player market, no rares). Edited prices stay in this browser{saved ? "" : " (not stored: this browser refuses site storage)"} and are
        never sent to the server. All rates are counts divided by the judged hours.
      </p>

      {current && name !== null && <RunView doc={current} name={name} runIx={runIx} edits={edits} update={update} />}
    </main>
  );
}
