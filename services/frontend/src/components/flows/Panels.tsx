"use client";

// The /flows studio's DRAWER panes (2026-11-09, flows-studio.md; the side panels before it):
// Inspect (a map block, the flow's run settings, the static data), Lint, Simulate, the Path map and
// the hunt rules. Styled with the studio's tokens (studio.css), text only: every value from a file
// or the backend is rendered as React text.
import { useEffect, useMemo, useState } from "react";

import PathMap from "@/components/flows/PathMap";
import type { FlowsApi, LintDoc, Scenario, SimDoc, WorldDoc, WorldSource } from "@/lib/flow/api";
import { ApiError, BADGE_TEXT } from "@/lib/flow/api";
import { type BlockProps, savePointBlock } from "@/lib/flow/canvas";
import { badgeText, GROUP_TITLE, type HuntRules } from "@/lib/flow/hunt";
import { builtInEvents, exitsOf, type Flow, type MapBlock, runSettings } from "@/lib/flow/ir";
import { classOptions, type Models, modelOptions } from "@/lib/flow/models";
import { END_TEXT, lintLine, lintOf, runLine } from "@/lib/flow/status";

const btn = "button button-small";

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
  api,
  world,
  onUpdate,
  onDelete,
  onStart,
  onOpen,
  onSimulateHere,
  limits,
  onFlow,
  onZones,
}: {
  flow: Flow;
  selected: string | null;
  lint: LintDoc | null;
  sim: SimDoc | null;
  api: FlowsApi | null;
  world: WorldSource;
  onUpdate: (name: string, props: BlockProps) => void;
  onDelete: (name: string) => void;
  onStart: (name: string, entry: string) => void;
  onOpen: (id: string) => void;
  onSimulateHere: (block: string) => void;
  limits: { default_s: number; max_s: number } | null;
  onFlow: (flow: Flow) => void;
  onZones: (block: string) => void;
}) {
  const block = selected?.startsWith("block:") ? flow.workflow?.blocks.find((b) => `block:${b.name}` === selected) : undefined;
  if (!selected || selected === "main") {
    const sp = savePointBlock(flow);
    return (
      <div className="stack">
        <FlowSettings key={`${flow.max_runtime_s}|${flow.where_budget}`} flow={flow} limits={limits} onFlow={onFlow} />
        {flow.workflow ? (
          <>
            <p className="muted">On the Map tab: click a map block to inspect it here; double-click it (or its tab) to open its blocks.</p>
            <p className="muted">
              Draw an exit from a port (walk exit, npc warp, item warp) onto another map block; select an exit and press Delete to remove it. The new exit
              gets placeholder details the linter names: fill them in the blocks.
            </p>
            <p className="muted">death_respawn edges are DERIVED from the save point (MW1&apos;s IR refuses an authored one): {sp.why}.</p>
          </>
        ) : (
          <p className="muted">A plain flow: one program, the tab “main”. Load a workflow (Load ▸ A new workflow) to organise a flow by map blocks.</p>
        )}
      </div>
    );
  }
  if (block) {
    return (
      <>
        <BlockInspector key={block.name + JSON.stringify(block.entries)} block={block} flow={flow} lint={lint} sim={sim} onUpdate={onUpdate} onDelete={onDelete} onStart={onStart} onOpen={onOpen} onSimulateHere={onSimulateHere} onZones={onZones} />
        <StaticData api={api} world={world} server={flow.target.server} map={block.map.map} />
      </>
    );
  }
  return (
    <div className="stack">
      <div className="strong">{selected === "events:global" ? "Global events" : selected}</div>
      {selected !== "events:global" && (
        <button className={btn} onClick={() => onOpen(selected)}>
          Open its blocks
        </button>
      )}
      {selected === "events:global" && (
        <ul className="plain-list">
          {builtInEvents(flow).map((k) => (
            <li key={k} className="box">
              <b>(locked) {k}</b> · built in, always on · read-only: the compiler adds it to every flow (ADR-0020 #15); write it in the global events only to
              make it stricter
              {sim && <div className="run-text">{runLine(sim.trace.nodes[`${k}.0`]) || "did not fire"}</div>}
            </li>
          ))}
          {flow.handlers.map((h) => (
            <li key={h.name} className="box">
              <b>{h.name}</b> · {h.priority}
              {h.rank === null ? "" : ` rank ${h.rank}`} · {h.mode} · then {h.then}
              {sim && <div className="run-text">{runLine(sim.trace.nodes[`${h.name}.0`]) || "did not fire"}</div>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** The flow's run settings (ADR-0020 #17 max_runtime_s, #10 where_budget). A change is part of
 * the flow, so it shows in its JSON export / diff; the global default and maximum are the
 * Settings page's (human-only writes, audited). */
/** The run's time box and /where budget (a flow's, now a PROJECT's: the same two fields). */
export function FlowSettings<F extends { name: string; max_runtime_s: number; where_budget: number }>({ flow, limits, onFlow }: { flow: F; limits: { default_s: number; max_s: number } | null; onFlow: (f: F) => void }) {
  const [runtime, setRuntime] = useState(String(flow.max_runtime_s));
  const [budget, setBudget] = useState(String(flow.where_budget));
  const [err, setErr] = useState("");
  const apply = () => {
    const r = runSettings(flow, runtime, budget, limits?.max_s ?? null);
    if (!r.ok) return setErr(r.error);
    setErr("");
    onFlow(r.flow);
  };
  const hours = (s: number) => `${(s / 3600).toFixed(s % 3600 ? 2 : 0)} h`;
  return (
    <div className="box stack">
      <div className="strong">{flow.name}: run settings</div>
      <div className="grid2">
        <label>
          max_runtime_s ({hours(Number(runtime) || 0)})
          <input className="field" value={runtime} onChange={(e) => setRuntime(e.target.value)} />
        </label>
        <label>
          where_budget (/where reads a run)
          <input className="field" value={budget} onChange={(e) => setBudget(e.target.value)} />
        </label>
      </div>
      <div className="muted">
        {limits
          ? `Configured on the Settings page: default ${hours(limits.default_s)}, maximum ${hours(limits.max_s)}. A run above the maximum is refused.`
          : "The configured limits are not loaded yet."}
      </div>
      <div className="row">
        <button className={btn} onClick={apply}>
          Apply
        </button>
        {err && <span className="err-text">{err}</span>}
      </div>
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
  onZones,
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
  onZones: (block: string) => void;
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
  const zoneFindings = (lint?.findings ?? []).filter((f) => f.owner === `block:${block.name}` && f.rule.startsWith("zones_")).map((f) => f.rule);
  return (
    <div className="stack">
      <div className="row">
        <span className="strong">Map block {block.name}</span>
        <span className="muted">{l.text}</span>
      </div>
      <div className="row">
        <button className={btn} onClick={() => onOpen(`block:${block.name}`)}>
          Open its blocks
        </button>
        <button className={btn} onClick={() => onSimulateHere(block.name)}>
          Simulate this node only
        </button>
        <button className={btn} onClick={() => onStart(block.name, block.entries[0].name)} disabled={flow.workflow?.start_block === block.name}>
          Start here
        </button>
        <button className={btn} onClick={() => onDelete(block.name)}>
          Delete block
        </button>
      </div>
      <div className="grid2">
        <label>name<input className="field" value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label>map<input className="field" value={map} onChange={(e) => setMap(e.target.value)} /></label>
        <label>entry<input className="field" value={entry} onChange={(e) => setEntry(e.target.value)} /></label>
        <label>radius<input className="field" value={radius} onChange={(e) => setRadius(e.target.value)} /></label>
        <label>entry x<input className="field" value={ex} onChange={(e) => setEx(e.target.value)} /></label>
        <label>entry y<input className="field" value={ey} onChange={(e) => setEy(e.target.value)} /></label>
        <label>targets (mob ids)<input className="field" value={targets} onChange={(e) => setTargets(e.target.value)} /></label>
        <label>ignore (mob ids)<input className="field" value={ignore} onChange={(e) => setIgnore(e.target.value)} /></label>
      </div>
      <label className="check">
        <input type="checkbox" checked={resume} onChange={(e) => setResume(e.target.checked)} /> resume here (the relocation target for its map)
      </label>
      <div className="row">
        <button className="button button-small button-primary" onClick={save}>
          Apply
        </button>
        {err && <span className="err-text">{err}</span>}
      </div>
      <div className="box stack">
        <div className="strong">Zones (map-node data, config/map_zones/{block.map.map}.yaml)</div>
        <div>
          {block.zones ? `this node names ${block.zones.map} ${block.zones.sha256.slice(0, 12)}…` : "this node names no zones file"}
          {zoneFindings.length > 0 && <span className="err-text"> · {zoneFindings.join(" · ")}</span>}
        </div>
        <button className={btn} onClick={() => onZones(block.name)}>
          Open the Zones layer
        </button>
      </div>
      <div>
        <div className="strong">Exits</div>
        <ul className="plain-list">
          {exitsOf(block).map(({ path, exit }) => (
            <li key={path}>
              <code>{path}</code> {exit.kind} → {exit.to_block}.{exit.to_entry}
              {sim && <span className="run-text"> {runLine(sim.trace.nodes[path])}</span>}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <div className="strong">Effective events here (13.6.2, from the last lint)</div>
        <table className="kv">
          <tbody>
            {eff.map((e) => (
              <tr key={e.key} className={e.active ? "" : "struck"}>
                <td>
                  {e.safety_critical ? "(locked) " : ""}
                  {e.key}
                </td>
                <td>
                  {e.state === "built_in" ? "built in" : e.state}
                  {e.built_in && e.state !== "built_in" ? " (built in)" : ""}
                </td>
                <td>
                  {e.priority} · rank {e.rank}
                </td>
                <td>{e.mode}</td>
              </tr>
            ))}
            {!eff.length && (
              <tr>
                <td className="muted">lint first</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** What the static data says about a map (keys to use in the blocks; names for display only). */
function StaticData({ api, world, server, map }: { api: FlowsApi | null; world: WorldSource; server: string; map: string }) {
  const [doc, setDoc] = useState<{ for: string; w: WorldDoc | null; err: string } | null>(null);
  const want = `${world}|${server}|${map}`;
  useEffect(() => {
    if (!api) return;
    let alive = true;
    api
      .world(world, server, [map])
      .then((w) => alive && setDoc({ for: want, w, err: "" }))
      .catch((e) => alive && setDoc({ for: want, w: null, err: e instanceof ApiError ? e.reason : "unavailable" }));
    return () => {
      alive = false;
    };
  }, [api, world, server, map, want]);
  if (!doc || doc.for !== want) return <div className="muted">Loading the static data…</div>;
  const sheet = doc.w?.maps[map];
  const label = (k: string) => doc.w?.labels?.npcs[k];
  const opt = (k: string) => doc.w?.labels?.options[k];
  return (
    <div className="box stack" data-testid="static-data">
      <div className="strong">
        Static data for {map} ({world === "sample" ? "synthetic sample sheets" : `local data/kb, ${server}`})
      </div>
      {doc.err && <div className="err-text">{doc.err}</div>}
      {(doc.w?.notes ?? []).map((n) => (
        <div key={n} className="warn-text">
          {n}
        </div>
      ))}
      {!sheet && !doc.err && <div className="err-text">No map sheet for {map}: blocks on it are unsupported (fail closed).</div>}
      {sheet && (
        <>
          <div className="muted">
            walk grid {sheet.size ? `${sheet.size[0]}×${sheet.size[1]}` : "none (routes are estimates)"} · {sheet.warps.length} warps · {sheet.npcs.length} NPCs ·{" "}
            {sheet.spawns.length} spawn lines
          </div>
          <details open={sheet.npcs.length <= 8}>
            <summary>NPCs (key · name · cell · menu keys)</summary>
            <ul className="plain-list">
              {sheet.npcs.map((n) => (
                <li key={n.key}>
                  <code>{n.key}</code> {label(n.key) ? `· ${label(n.key)} ` : ""}· ({n.x}, {n.y}){n.kafra ? " · Kafra" : ""}
                  {n.menu.length > 0 && (
                    <div className="muted">
                      {n.menu.map((k) => (
                        <span key={k} className="mr-2">
                          <code>{k}</code>
                          {opt(k) ? ` ${opt(k)}` : ""}
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </details>
          <details>
            <summary>Warps (cell → map)</summary>
            <ul className="plain-list">
              {sheet.warps.map((w, i) => (
                <li key={i}>
                  ({w.x}, {w.y}) → {w.to_map} ({w.to_x}, {w.to_y})
                </li>
              ))}
            </ul>
          </details>
          <details>
            <summary>Spawns (mob id × count)</summary>
            <ul className="plain-list">
              {sheet.spawns.map((sp, i) => (
                <li key={i}>
                  {sp.mob}
                  {doc.w?.mobs[String(sp.mob)]?.label ? ` ${doc.w.mobs[String(sp.mob)].label}` : ""} × {sp.count}
                  {sp.boss ? " (boss)" : ""}
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
    </div>
  );
}

// --- lint ------------------------------------------------------------------------------------------
export function LintPanel({ lint, stale, onSelect }: { lint: LintDoc | null; stale: boolean; onSelect: (f: LintDoc["findings"][number]) => void }) {
  const [showReadiness, setShowReadiness] = useState(false);
  if (!lint) return <div className="muted">Not linted yet.</div>;
  const own = lint.findings.filter((f) => f.severity !== "readiness");
  const readiness = lint.findings.filter((f) => f.severity === "readiness");
  return (
    <div className="stack" data-testid="lint-pane">
      <div className={stale ? "warn-text" : "muted"}>
        MW1&apos;s linter, layers 1-3 · {lint.counts.error} errors · {lint.counts.warning} warnings · {lint.counts.info} info · {lint.counts.readiness} not ready ·
        static data: {lint.world.server ?? "none"} ({lint.world.maps.join(", ") || "no sheets"})
        {stale ? " · STALE: the flow changed since" : ""}
      </div>
      <div className={lint.run.allowed ? "ok-text" : "muted"}>Run-start check (what a live run needs, MW3): {lint.run.summary}</div>
      {(lint.world_notes ?? []).map((n) => (
        <div key={n} className="warn-text">
          {n}
        </div>
      ))}
      <ul className="plain-list">
        {own.map((f, i) => (
          <li key={i} className="finding" data-severity={f.severity} onClick={() => onSelect(f)} title="Show the block">
            <span className="strong">{f.severity}</span> · {f.rule} · L{f.layer}
            {f.ack ? " · acknowledge at approval" : ""}
            <div>{f.message}</div>
          </li>
        ))}
        {!own.length && <li className="ok-text">No findings of the flow itself.</li>}
      </ul>
      {readiness.length > 0 && (
        <div className="finding" data-severity="readiness">
          <button className="problem-link strong" onClick={() => setShowReadiness(!showReadiness)}>
            {showReadiness ? "▾" : "▸"} {readiness.length} readiness item{readiness.length > 1 ? "s" : ""}: bindings not there yet
          </button>
          <div className="muted">
            Blocks whose L2 / L3 / L4 bindings are not there for this environment yet. They block the RUN (the run-start check refuses), not the design: the flow
            can still be designed, linted and simulated (ADR-0020 contradictions #6, Batt 2026-10-09).
          </div>
          {showReadiness && (
            <ul className="plain-list">
              {readiness.map((f, i) => (
                <li key={i} onClick={() => onSelect(f)}>
                  {f.message}
                </li>
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
  // a trained model's sighting (ADR-0020 Amendment B): at t, the model boxes N of the class
  detectAt: string;
  detectModel: string;
  detectClass: string;
  detectCount: string;
};

export const DEFAULT_SIM: SimForm = {
  horizon: "300",
  hp: "100",
  weight: "10",
  perAttack: "2",
  deathAt: "200",
  startBlock: "",
  single: false,
  detectAt: "",
  detectModel: "v1",
  detectClass: "monster",
  detectCount: "1",
};

export function scenarioOf(f: SimForm): Scenario {
  const n = (s: string, d: number) => (Number.isFinite(Number(s)) && s.trim() !== "" ? Number(s) : d);
  const death = f.deathAt.trim() === "" ? null : n(f.deathAt, 200);
  const timeline: NonNullable<Scenario["timeline"]> = death === null ? [] : [{ t: death, set: { is_dead: true, hp_percent: 0 } }];
  if (f.detectAt.trim() !== "") {
    timeline.push({ t: n(f.detectAt, 0), detects: { [`${f.detectModel}/${f.detectClass}`]: Math.max(0, Math.round(n(f.detectCount, 1))) } });
  }
  return {
    horizon_s: n(f.horizon, 300),
    hp_percent: n(f.hp, 100),
    weight_percent: n(f.weight, 10),
    weight_per_attack: n(f.perAttack, 2),
    start_block: f.startBlock || null,
    single_block: f.single,
    timeline,
  };
}

export function SimulatePanel({
  blocks,
  form,
  setForm,
  sim,
  stale,
  busy,
  world,
  models,
  onRun,
}: {
  /** The map nodes a run may start on (empty: the project's start). */
  blocks: string[];
  form: SimForm;
  setForm: (f: SimForm) => void;
  sim: SimDoc | null;
  stale: boolean;
  busy: boolean;
  world: WorldSource;
  models: Models | null;
  onRun: () => void;
}) {
  const t = sim?.trace;
  const set = (k: keyof SimForm) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value });
  return (
    <div className="stack" data-testid="simulate-pane">
      <p className="muted">
        SIMULATE runs MW1&apos;s simulated executor against the STATIC data ({world === "sample" ? "the synthetic sample sheets" : "local data/kb map sheets"}).
        No game, no input: nothing leaves the backend. The scenario values are YOUR assumptions, never measurements.
      </p>
      <div className="grid2">
        <label>simulated seconds<input className="field" value={form.horizon} onChange={set("horizon")} /></label>
        <label>a death at t (s, empty: none)<input className="field" value={form.deathAt} onChange={set("deathAt")} /></label>
        <label>start HP %<input className="field" value={form.hp} onChange={set("hp")} /></label>
        <label>start weight %<input className="field" value={form.weight} onChange={set("weight")} /></label>
        <label>weight per attack (loot model)<input className="field" value={form.perAttack} onChange={set("perAttack")} /></label>
        <label>
          start on the map
          <select className="field" value={form.startBlock} onChange={set("startBlock")}>
            <option value="">the project&apos;s start (login)</option>
            {blocks.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="box stack">
        <div className="strong">A detector sighting (the model blocks): until then each detector sees nothing</div>
        <div className="grid2">
          <label>at t (s, empty: none)<input className="field" value={form.detectAt} onChange={set("detectAt")} data-testid="sim-detect-at" /></label>
          <label>
            boxes
            <input className="field" value={form.detectCount} onChange={set("detectCount")} />
          </label>
          <label>
            model
            <select className="field" value={form.detectModel} onChange={set("detectModel")}>
              {modelOptions(models, form.detectModel, false).map(([label, v]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            class
            <select className="field" value={form.detectClass} onChange={set("detectClass")}>
              {classOptions(models, form.detectModel, form.detectClass).map(([label, v]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      <label className="check">
        <input type="checkbox" checked={form.single} onChange={set("single")} /> run this map node only (stop at its exit)
      </label>
      <div className="row">
        <button className="button button-small button-run button-primary" disabled={busy} onClick={onRun}>
          {busy ? "Simulating…" : "Simulate"}
        </button>
      </div>
      {t && (
        <div className="stack" data-testid="sim-result" style={stale ? { opacity: 0.6 } : undefined}>
          <div className="notice notice-ok">
            <div>
              <b>End:</b> {END_TEXT[t.end] ?? t.end} at t = {t.t_end_s} s{stale ? " (STALE: the flow changed since)" : ""}
            </div>
            <div>
              start {t.start.block ?? "main"}.{t.start.entry ?? "-"} on {t.start.map ?? "?"} → final {t.final.block ?? "main"} on {t.final.map ?? "?"}
              {t.final.cell ? ` (${t.final.cell[0]}, ${t.final.cell[1]})` : ""} · HP {t.final.hp_percent ?? "?"} % · weight {t.final.weight_percent ?? "?"} %
            </div>
            <div>
              save point: {t.save_point ? `${t.save_point.map} (${t.save_point.cell[0]}, ${t.save_point.cell[1]})` : "unknown"} · input batches a real run would send:{" "}
              {t.input_batches_counted} (counted, never built or sent)
            </div>
            {t.where && (
              <div className={t.where.over ? "warn-text" : ""}>
                /where reads (they type; use as few as possible): {t.where.count} of the flow&apos;s budget {t.where.budget}
                {t.where.reads.length > 0 && ` · ${t.where.reads.map((r) => `${r.reason} @${r.t} s`).join(", ")}`}
              </div>
            )}
          </div>
          <div>
            <div className="strong">Exits taken</div>
            <ol className="plain-list">
              {t.transitions.map((x, i) => (
                <li key={i}>
                  t={x.t}s · <b>{x.kind}</b> {x.from} → {x.to}
                  {x.entry ? `.${x.entry}` : ""} on {x.map}
                  {x.arrived ? "" : " (NOT the expected block)"}
                </li>
              ))}
              {!t.transitions.length && <li className="muted">none</li>}
            </ol>
          </div>
          {t.notes.length > 0 && (
            <ul className="notice notice-warn plain-list">
              {t.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}
          <details>
            <summary>Per node ({Object.keys(t.nodes).length})</summary>
            <table className="kv">
              <tbody>
                {Object.entries(t.nodes).map(([p, r]) => (
                  <tr key={p}>
                    <td>
                      <code>{p}</code>
                    </td>
                    <td>{runLine(r)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
          <details>
            <summary>
              Events fired ({t.events.length}
              {t.events_capped ? "+" : ""})
            </summary>
            <ol className="plain-list">
              {t.events.map((e, i) => (
                <li key={i}>
                  t={e.t}s {e.kind} {e.what}
                </li>
              ))}
            </ol>
          </details>
        </div>
      )}
    </div>
  );
}

// --- the path map of the last run ------------------------------------------------------------------
export function PathPanel({ server, sim, stale, world, api }: { server: string; sim: SimDoc | null; stale: boolean; world: WorldSource; api: FlowsApi | null }) {
  const [maps, setMaps] = useState<WorldDoc | null>(null);
  const t = sim?.trace;
  const mapNames = useMemo(() => [...new Set((t?.paths ?? []).map((p) => p.map))].sort(), [t]);
  useEffect(() => {
    if (!api || !t || !mapNames.length) return;
    let alive = true;
    api
      .world(world, server, mapNames, true)
      .then((w) => alive && setMaps(w))
      .catch(() => alive && setMaps(null));
    return () => {
      alive = false;
    };
  }, [api, t, mapNames, world, server]);
  if (!t) return <div className="muted">Simulate first: the cells each map node walked are drawn here.</div>;
  if (!mapNames.length) return <div className="muted">The last run walked no map (a plain flow, or no route).</div>;
  return (
    <div className="stack" style={stale ? { opacity: 0.6 } : undefined}>
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
  );
}

// --- the hunt block's rules ------------------------------------------------------------------------
/** The hunt block's groups as lists of rule versions with their badges and numbers (read-only:
 * a new number is a new version, pre-registered; ADR-0020 section 12 point 4). Text only. */
export function HuntRulesPanel({ rules, l1 }: { rules: HuntRules; l1: keyof typeof BADGE_TEXT }) {
  return (
    <div className="stack" data-testid="hunt-rules">
      <div className="strong">hunt · L1: {BADGE_TEXT[l1]}</div>
      <div className="muted">
        Hunting evidence (Batt D8): {rules.evidence.badges.length ? rules.evidence.badges.join(", ") : "none"} · {rules.evidence.rule}. ★ the adopted base&apos;s
        rule, ◆ hunting evidence.
      </div>
      {rules.evidence.verdicts.map((v) => (
        <div key={v.entry} className={v.d8 ? "ok-text" : "muted"}>
          {v.entry} · v{v.version} · {v.map} · {v.path} · {v.hours} h · GM {v.gm} · {v.verdict}
          {v.d8 ? "" : ` · no badge: ${v.why_not}`}
        </div>
      ))}
      {rules.groups.map((g) => (
        <div key={g.name} className="box stack">
          <div className="strong">{GROUP_TITLE[g.name] ?? g.name}</div>
          {g.note && <div className="muted">{g.note}</div>}
          {g.params.map((p) => (
            <div key={p.name}>
              <div>
                {p.name} (default {p.default}
                {p.kind === "option" ? "; an option, not a rule version" : ""})
              </div>
              {p.note && <div className="muted">{p.note}</div>}
              <ul className="plain-list">
                {p.choices.map((c) => (
                  <li key={c.id}>
                    <details>
                      <summary>
                        <code>{c.id}</code> {badgeText(c, rules.adopted)}
                      </summary>
                      <ul className="plain-list muted">
                        {Object.entries(c.values).map(([k, v]) => (
                          <li key={k}>
                            {k} = {JSON.stringify(v)}
                          </li>
                        ))}
                        {!Object.keys(c.values).length && <li>{c.option ? "(an option: no numbers)" : "(no numbers: the rule is off)"}</li>}
                      </ul>
                    </details>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
