"use client";

// The /flows side panels: inspect a node, the lint findings, SIMULATE, and the JSON / Python views.
import { useEffect, useMemo, useState } from "react";

import PathMap from "@/components/flows/PathMap";
import type { FlowsApi, LintDoc, Scenario, SimDoc, WorldDoc, WorldSource } from "@/lib/flow/api";
import { ApiError } from "@/lib/flow/api";
import { type BlockProps, savePointBlock } from "@/lib/flow/canvas";
import { exportText } from "@/lib/flow/importer";
import { exitsOf, type Flow, type MapBlock } from "@/lib/flow/ir";
import { END_TEXT, lintLine, lintOf, runLine } from "@/lib/flow/status";

const SEV_CLASS: Record<string, string> = {
  error: "border-red-700 bg-red-950/50 text-red-200",
  warning: "border-amber-700 bg-amber-950/40 text-amber-100",
  info: "border-neutral-700 bg-neutral-900 text-neutral-200",
  unsupported: "border-sky-800 bg-sky-950/40 text-sky-100",
};
const btn = "rounded bg-neutral-800 px-2.5 py-1 text-xs hover:bg-neutral-700 disabled:opacity-50";
const input = "w-full rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs";

// --- inspect -------------------------------------------------------------------------------------
function ids(text: string): { kind: "mob"; id: number }[] | null {
  const parts = text.split(",").map((t) => t.trim()).filter(Boolean);
  if (!parts.every((p) => /^[0-9]{1,7}$/.test(p))) return null;
  return parts.map((p) => ({ kind: "mob" as const, id: Number(p) }));
}

export function InspectPanel({
  flow,
  selected,
  lint,
  sim,
  onUpdate,
  onDelete,
  onStart,
  onOpen,
  onSimulateHere,
}: {
  flow: Flow;
  selected: string | null;
  lint: LintDoc | null;
  sim: SimDoc | null;
  onUpdate: (name: string, props: BlockProps) => void;
  onDelete: (name: string) => void;
  onStart: (name: string, entry: string) => void;
  onOpen: (id: string) => void;
  onSimulateHere: (block: string) => void;
}) {
  const block = selected?.startsWith("block:") ? flow.workflow?.blocks.find((b) => `block:${b.name}` === selected) : undefined;
  if (!selected) {
    const sp = savePointBlock(flow);
    return (
      <div className="space-y-2 text-xs text-neutral-300">
        <p>Click a node to inspect it; double-click a map block (or an events node) to open its blocks.</p>
        <p>Draw an exit from a port (walk exit, npc warp, item warp) onto another map block; select an exit and press Delete to remove it. The new exit gets placeholder details the linter names: fill them in the blocks.</p>
        <p className="text-neutral-400">
          death_respawn edges are DERIVED from the save point (MW1&apos;s IR refuses an authored one): {sp.why}.
        </p>
      </div>
    );
  }
  if (block) return <BlockInspector key={block.name + JSON.stringify(block.entries)} block={block} flow={flow} lint={lint} sim={sim} onUpdate={onUpdate} onDelete={onDelete} onStart={onStart} onOpen={onOpen} onSimulateHere={onSimulateHere} />;
  return (
    <div className="space-y-2 text-xs">
      <div className="font-semibold">{selected === "events:global" ? "Global events" : selected}</div>
      <button className={btn} onClick={() => onOpen(selected)}>
        Open in the block editor
      </button>
      {selected === "events:global" && (
        <ul className="space-y-1">
          {flow.handlers.map((h) => (
            <li key={h.name} className="rounded border border-neutral-800 p-1.5">
              <b>{h.name}</b> · {h.priority} · {h.mode} · then {h.then}
              {sim && <div className="text-fuchsia-300">{runLine(sim.trace.nodes[`${h.name}.0`]) || "did not fire"}</div>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function BlockInspector({
  block,
  flow,
  lint,
  sim,
  onUpdate,
  onDelete,
  onStart,
  onOpen,
  onSimulateHere,
}: {
  block: MapBlock;
  flow: Flow;
  lint: LintDoc | null;
  sim: SimDoc | null;
  onUpdate: (name: string, props: BlockProps) => void;
  onDelete: (name: string) => void;
  onStart: (name: string, entry: string) => void;
  onOpen: (id: string) => void;
  onSimulateHere: (block: string) => void;
}) {
  const e0 = block.entries[0];
  const [name, setName] = useState(block.name);
  const [map, setMap] = useState(block.map.map);
  const [entry, setEntry] = useState(e0.name);
  const [ex, setEx] = useState(e0.at ? String(e0.at.x) : "");
  const [ey, setEy] = useState(e0.at ? String(e0.at.y) : "");
  const [radius, setRadius] = useState(String(e0.radius));
  const [targets, setTargets] = useState(block.targets.map((m) => m.id).join(", "));
  const [ignore, setIgnore] = useState(block.ignore.map((m) => m.id).join(", "));
  const [resume, setResume] = useState(block.resume_here);
  const [err, setErr] = useState("");
  const eff = lint?.effective[block.name] ?? [];
  const save = () => {
    const t = ids(targets);
    const ig = ids(ignore);
    if (!t || !ig) return setErr("targets / ignore: mob ids, comma separated");
    const anywhere = ex.trim() === "" && ey.trim() === "";
    if (!anywhere && !(/^[0-9]+$/.test(ex) && /^[0-9]+$/.test(ey))) return setErr("the entry cell: two whole numbers, or both empty (anywhere)");
    setErr("");
    onUpdate(block.name, {
      name: name.trim(),
      map: { kind: "map", map: map.trim() },
      entries: [{ name: entry.trim(), at: anywhere ? null : { kind: "cell", map: map.trim(), x: Number(ex), y: Number(ey) }, radius: Number(radius) || 0 }, ...block.entries.slice(1)],
      targets: t,
      ignore: ig,
      resume_here: resume,
    });
  };
  const l = lintLine(lintOf(lint, `block:${block.name}`));
  return (
    <div className="space-y-3 text-xs">
      <div className="flex items-center gap-2">
        <span className="font-semibold">Map block {block.name}</span>
        <span className="text-neutral-400">{l.text}</span>
      </div>
      <div className="flex flex-wrap gap-2">
        <button className={btn} onClick={() => onOpen(`block:${block.name}`)}>Open blocks</button>
        <button className={btn} onClick={() => onSimulateHere(block.name)}>Simulate this node only</button>
        <button className={btn} onClick={() => onStart(block.name, block.entries[0].name)} disabled={flow.workflow?.start_block === block.name}>Start here</button>
        <button className={btn} onClick={() => onDelete(block.name)}>Delete block</button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <label>name<input className={input} value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label>map<input className={input} value={map} onChange={(e) => setMap(e.target.value)} /></label>
        <label>entry<input className={input} value={entry} onChange={(e) => setEntry(e.target.value)} /></label>
        <label>radius<input className={input} value={radius} onChange={(e) => setRadius(e.target.value)} /></label>
        <label>entry x<input className={input} value={ex} onChange={(e) => setEx(e.target.value)} /></label>
        <label>entry y<input className={input} value={ey} onChange={(e) => setEy(e.target.value)} /></label>
        <label>targets (mob ids)<input className={input} value={targets} onChange={(e) => setTargets(e.target.value)} /></label>
        <label>ignore (mob ids)<input className={input} value={ignore} onChange={(e) => setIgnore(e.target.value)} /></label>
      </div>
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={resume} onChange={(e) => setResume(e.target.checked)} /> resume here (the relocation target for its map)
      </label>
      <div className="flex items-center gap-2">
        <button className="rounded bg-sky-700 px-2.5 py-1 text-xs hover:bg-sky-600" onClick={save}>Apply</button>
        {err && <span className="text-red-300">{err}</span>}
      </div>
      <div>
        <div className="mb-1 font-semibold">Exits</div>
        <ul className="space-y-0.5">
          {exitsOf(block).map(({ path, exit }) => (
            <li key={path}>
              <code>{path}</code> {exit.kind} → {exit.to_block}.{exit.to_entry}
              {sim && <span className="text-fuchsia-300"> {runLine(sim.trace.nodes[path])}</span>}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <div className="mb-1 font-semibold">Effective events here (13.6.2, from the last lint)</div>
        <table className="w-full text-left">
          <tbody>
            {eff.map((e) => (
              <tr key={e.key} className={e.active ? "" : "text-neutral-500 line-through"}>
                <td>{e.safety_critical ? "(locked) " : ""}{e.key}</td>
                <td>{e.state}</td>
                <td>{e.priority}</td>
                <td>{e.mode}</td>
              </tr>
            ))}
            {!eff.length && (
              <tr>
                <td className="text-neutral-500">lint first</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// --- lint ------------------------------------------------------------------------------------------
export function LintPanel({ lint, stale, onSelect }: { lint: LintDoc | null; stale: boolean; onSelect: (owner: string) => void }) {
  const [showUnsupported, setShowUnsupported] = useState(false);
  if (!lint) return <div className="text-xs text-neutral-400">Not linted yet.</div>;
  const own = lint.findings.filter((f) => f.rule !== "bindings");
  const unsupported = lint.findings.filter((f) => f.rule === "bindings");
  return (
    <div className="space-y-2 text-xs">
      <div className={stale ? "text-amber-300" : "text-neutral-400"}>
        MW1&apos;s linter, layers 1-3 · {lint.counts.error} errors · {lint.counts.warning} warnings · {lint.counts.info} info · static data:{" "}
        {lint.world.server ?? "none"} ({lint.world.maps.join(", ") || "no sheets"}){stale ? " · STALE: the flow changed since" : ""}
      </div>
      <ul className="space-y-1">
        {own.map((f, i) => (
          <li key={i} className={`cursor-pointer rounded border p-1.5 ${SEV_CLASS[f.severity]}`} onClick={() => onSelect(f.owner)}>
            <span className="font-semibold">{f.severity}</span> · {f.rule} · L{f.layer}
            {f.ack ? " · acknowledge at approval" : ""}
            <div>{f.message}</div>
          </li>
        ))}
        {!own.length && <li className="text-emerald-300">No findings of the flow itself.</li>}
      </ul>
      {unsupported.length > 0 && (
        <div className={`rounded border p-1.5 ${SEV_CLASS.unsupported}`}>
          <button className="font-semibold" onClick={() => setShowUnsupported(!showUnsupported)}>
            {showUnsupported ? "▾" : "▸"} {unsupported.length} unsupported bindings (rule bindings, errors in MW1)
          </button>
          <div className="text-sky-200/80">
            Blocks whose L2 / L3 / L4 bindings are not there for this environment yet. Today no real flow lints clean
            (ADR-0020 open question #6), so they are listed apart here; MW1&apos;s severity is unchanged.
          </div>
          {showUnsupported && (
            <ul className="mt-1 space-y-0.5">
              {unsupported.map((f, i) => (
                <li key={i} className="cursor-pointer" onClick={() => onSelect(f.owner)}>{f.message}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

// --- simulate --------------------------------------------------------------------------------------
export type SimForm = {
  horizon: string;
  hp: string;
  weight: string;
  perAttack: string;
  deathAt: string;
  startBlock: string;
  single: boolean;
};

export const DEFAULT_SIM: SimForm = { horizon: "300", hp: "100", weight: "10", perAttack: "2", deathAt: "200", startBlock: "", single: false };

export function scenarioOf(f: SimForm): Scenario {
  const n = (s: string, d: number) => (Number.isFinite(Number(s)) && s.trim() !== "" ? Number(s) : d);
  const death = f.deathAt.trim() === "" ? null : n(f.deathAt, 200);
  return {
    horizon_s: n(f.horizon, 300),
    hp_percent: n(f.hp, 100),
    weight_percent: n(f.weight, 10),
    weight_per_attack: n(f.perAttack, 2),
    start_block: f.startBlock || null,
    single_block: f.single,
    timeline: death === null ? [] : [{ t: death, set: { is_dead: true, hp_percent: 0 } }],
  };
}

export function SimulatePanel({
  flow,
  form,
  setForm,
  sim,
  stale,
  busy,
  world,
  api,
  onRun,
}: {
  flow: Flow;
  form: SimForm;
  setForm: (f: SimForm) => void;
  sim: SimDoc | null;
  stale: boolean;
  busy: boolean;
  world: WorldSource;
  api: FlowsApi | null;
  onRun: () => void;
}) {
  const [maps, setMaps] = useState<WorldDoc | null>(null);
  const t = sim?.trace;
  const mapNames = useMemo(() => [...new Set((t?.paths ?? []).map((p) => p.map))].sort(), [t]);
  useEffect(() => {
    if (!api || !t || !mapNames.length) return;
    let alive = true;
    api
      .world(world, flow.target.server, mapNames, true)
      .then((w) => alive && setMaps(w))
      .catch(() => alive && setMaps(null));
    return () => {
      alive = false;
    };
  }, [api, t, mapNames, world, flow.target.server]);
  const blocks = flow.workflow?.blocks.map((b) => b.name) ?? [];
  const set = (k: keyof SimForm) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value });
  return (
    <div className="space-y-3 text-xs">
      <p className="text-neutral-400">
        SIMULATE runs MW1&apos;s simulated executor against the STATIC data ({world === "sample" ? "the synthetic sample sheets" : "local data/kb map sheets"}). No game, no input: nothing leaves the backend. The
        scenario values are YOUR assumptions, never measurements.
      </p>
      <div className="grid grid-cols-2 gap-2">
        <label>simulated seconds<input className={input} value={form.horizon} onChange={set("horizon")} /></label>
        <label>a death at t (s, empty: none)<input className={input} value={form.deathAt} onChange={set("deathAt")} /></label>
        <label>start HP %<input className={input} value={form.hp} onChange={set("hp")} /></label>
        <label>start weight %<input className={input} value={form.weight} onChange={set("weight")} /></label>
        <label>weight per attack (loot model)<input className={input} value={form.perAttack} onChange={set("perAttack")} /></label>
        <label>
          start block
          <select className={input} value={form.startBlock} onChange={set("startBlock")}>
            <option value="">the flow&apos;s start</option>
            {blocks.map((b) => (
              <option key={b} value={b}>{b}</option>
            ))}
          </select>
        </label>
      </div>
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={form.single} onChange={set("single")} /> run this map node only (stop at its exit)
      </label>
      <button className="rounded bg-fuchsia-700 px-3 py-1 text-xs hover:bg-fuchsia-600 disabled:opacity-50" disabled={busy || !api} onClick={onRun}>
        {busy ? "Simulating…" : "Simulate"}
      </button>
      {t && (
        <div className={`space-y-2 ${stale ? "opacity-60" : ""}`} data-testid="sim-result">
          <div className="rounded border border-fuchsia-800 bg-fuchsia-950/30 p-2">
            <div>
              <b>End:</b> {END_TEXT[t.end] ?? t.end} at t = {t.t_end_s} s{stale ? " (STALE: the flow changed since)" : ""}
            </div>
            <div>
              start {t.start.block ?? "main"}.{t.start.entry ?? "-"} on {t.start.map ?? "?"} → final {t.final.block ?? "main"} on {t.final.map ?? "?"}
              {t.final.cell ? ` (${t.final.cell[0]}, ${t.final.cell[1]})` : ""} · HP {t.final.hp_percent ?? "?"} % · weight {t.final.weight_percent ?? "?"} %
            </div>
            <div>save point: {t.save_point ? `${t.save_point.map} (${t.save_point.cell[0]}, ${t.save_point.cell[1]})` : "unknown"} · input batches a real run would send: {t.input_batches_counted} (counted, never built or sent)</div>
          </div>
          <div>
            <div className="mb-1 font-semibold">Exits taken</div>
            <ol className="max-h-40 space-y-0.5 overflow-auto">
              {t.transitions.map((x, i) => (
                <li key={i}>
                  t={x.t}s · <b>{x.kind}</b> {x.from} → {x.to}
                  {x.entry ? `.${x.entry}` : ""} on {x.map}
                  {x.arrived ? "" : " (NOT the expected block)"}
                </li>
              ))}
              {!t.transitions.length && <li className="text-neutral-500">none</li>}
            </ol>
          </div>
          {t.notes.length > 0 && (
            <ul className="rounded border border-amber-800 bg-amber-950/30 p-1.5 text-amber-100">
              {t.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}
          <div className="space-y-2">
            {mapNames.map((m) => (
              <PathMap
                key={m}
                name={m}
                rows={maps?.walk?.[m] ?? null}
                sheet={maps?.maps[m] ?? null}
                paths={t.paths.filter((p) => p.map === m)}
                marks={[
                  ...(maps?.maps[m]?.npcs ?? []).map((n) => ({ x: n.x, y: n.y, label: n.key, colour: "#f59e0b" })),
                  ...(t.save_point && t.save_point.map === m ? [{ x: t.save_point.cell[0], y: t.save_point.cell[1], label: "save point", colour: "#ef4444" }] : []),
                ]}
              />
            ))}
          </div>
          <details>
            <summary className="cursor-pointer">Per node ({Object.keys(t.nodes).length})</summary>
            <table className="mt-1 w-full text-left">
              <tbody>
                {Object.entries(t.nodes).map(([p, r]) => (
                  <tr key={p}>
                    <td className="pr-2"><code>{p}</code></td>
                    <td>{runLine(r)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
          <details>
            <summary className="cursor-pointer">Events fired ({t.events.length}{t.events_capped ? "+" : ""})</summary>
            <ol className="mt-1 max-h-48 overflow-auto">
              {t.events.map((e, i) => (
                <li key={i}>t={e.t}s {e.kind} {e.what}</li>
              ))}
            </ol>
          </details>
        </div>
      )}
    </div>
  );
}

// --- JSON and Python -------------------------------------------------------------------------------
export function TextPanel({ flow, kind, api }: { flow: Flow; kind: "json" | "python"; api: FlowsApi | null }) {
  const [python, setPython] = useState<{ text: string; for: Flow } | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    if (kind !== "python" || !api) return;
    let alive = true;
    api
      .python(flow)
      .then((r) => alive && (setPython({ text: r.python, for: flow }), setErr("")))
      .catch((e) => alive && setErr(e instanceof ApiError ? e.message : "the Python view is unavailable"));
    return () => {
      alive = false;
    };
  }, [kind, api, flow]);
  const text = kind === "json" ? exportText(flow) : python?.for === flow ? python.text : "";
  return (
    <div className="space-y-1 text-xs">
      <div className="text-neutral-400">
        {kind === "json"
          ? "The IR, MW1's canonical JSON (the single source of truth). Export / Import above."
          : "MW1's canonical Python view, READ-ONLY in MW2 (parsed, never run; importing Python waits for F3's sandbox)."}
      </div>
      {err && <div className="text-red-300">{err}</div>}
      <pre className="max-h-[70vh] overflow-auto rounded border border-neutral-800 bg-neutral-950 p-2 text-[11px] leading-snug" data-testid={`${kind}-view`}>
        {text || (kind === "python" && !err ? "…" : "")}
      </pre>
    </div>
  );
}
