"use client";

// The /flows page (MW2, docs/planning/mw2-block-editor.md): the workflow canvas, the block editor,
// lint, SIMULATE, JSON import / export and the Python view, all over MW1's IR. It never connects to
// the executor, the mux, an agent channel or any input path: the backend calls are computation
// only (lib/flow/api.ts). The heavy libraries load lazily on this page only.
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { InspectPanel, LintPanel, SimulatePanel, TextPanel, DEFAULT_SIM, scenarioOf, type SimForm } from "@/components/flows/Panels";
import { ApiError, type CatalogueDoc, FlowsApi, type LintDoc, type SimDoc, type WorldSource } from "@/lib/flow/api";
import type { Scope } from "@/lib/flow/blocks";
import { addBlock, type BlockProps, connectExit, type EditResult, removeBlock, removeExit, setStart, updateBlock, type XY } from "@/lib/flow/canvas";
import { exportText, importFlow } from "@/lib/flow/importer";
import { type AuthoredExit, canonical, emptyFlow, type Flow, MAX_JSON_BYTES } from "@/lib/flow/ir";
import { lintLine } from "@/lib/flow/status";
import { backendHttpBase } from "@/lib/ws";

const FlowCanvas = dynamic(() => import("@/components/flows/FlowCanvas"), {
  ssr: false,
  loading: () => <div className="p-4 text-sm text-neutral-400">Loading the canvas…</div>,
});
const BlockEditor = dynamic(() => import("@/components/flows/BlockEditor"), { ssr: false });

type Tab = "inspect" | "lint" | "simulate" | "json" | "python";
const TABS: [Tab, string][] = [
  ["inspect", "Inspect"],
  ["lint", "Lint"],
  ["simulate", "Simulate"],
  ["json", "JSON"],
  ["python", "Python"],
];
const LINT_DEBOUNCE_MS = 2500;

function scopeOf(flow: Flow, nodeId: string): { scope: Scope; title: string } | null {
  if (nodeId === "events:global") return { scope: { kind: "global" }, title: "Global events (every map)" };
  if (nodeId === "main") return { scope: { kind: "main" }, title: "main (a plain flow)" };
  const name = nodeId.startsWith("block:") ? nodeId.slice(6) : nodeId.startsWith("events:") ? nodeId.slice(7) : null;
  if (name && flow.workflow?.blocks.some((b) => b.name === name)) {
    return { scope: { kind: "block", name }, title: `Map block ${name}: main flow and map events` };
  }
  return null;
}

export default function FlowsApp({ backendUrl }: { backendUrl: string | null }) {
  // Client-only (FlowsClient loads this with ssr: false): backendHttpBase reads window.location.
  const [api] = useState<FlowsApi>(() => new FlowsApi(backendHttpBase(backendUrl)));
  const [flow, setFlow] = useState<Flow>(() => emptyFlow());
  const [positions, setPositions] = useState<Record<string, XY>>({});
  const [world, setWorld] = useState<WorldSource>("local");
  const [catalogue, setCatalogue] = useState<CatalogueDoc | null>(null);
  const [lint, setLint] = useState<{ doc: LintDoc; for: string } | null>(null);
  const [sim, setSim] = useState<{ doc: SimDoc; for: string } | null>(null);
  const [simForm, setSimForm] = useState<SimForm>(DEFAULT_SIM);
  const [simBusy, setSimBusy] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [editor, setEditor] = useState<{ scope: Scope; title: string } | null>(null);
  const [tab, setTab] = useState<Tab>("inspect");
  const [message, setMessage] = useState<{ tone: "info" | "error"; text: string } | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const key = useMemo(() => canonical(flow), [flow]);

  useEffect(() => {
    if (!api) return;
    api
      .catalogue(flow.target.client)
      .then(setCatalogue)
      .catch((e) => setMessage({ tone: "error", text: `The flow engine is not reachable: ${e instanceof ApiError ? e.reason : String(e)}` }));
  }, [api, flow.target.client]);

  const runLint = useCallback(
    async (f: Flow, w: WorldSource) => {
      if (!api) return;
      try {
        const doc = await api.lint(f, w);
        setLint({ doc, for: canonical(f) });
      } catch (e) {
        if (e instanceof ApiError && e.reason === "invalid_flow") setMessage({ tone: "error", text: `MW1 refuses this flow: ${e.errors.join(" · ")}` });
        else setMessage({ tone: "error", text: `Lint failed: ${e instanceof ApiError ? e.message : String(e)}` });
      }
    },
    [api],
  );

  // lint automatically a moment after the last change (the backend allows 20 computations a minute)
  useEffect(() => {
    if (!api) return;
    const t = setTimeout(() => void runLint(flow, world), LINT_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [api, flow, world, runLint]);

  const edit = (r: EditResult) => {
    if (r.ok) {
      setFlow(r.flow);
      setMessage(null);
    } else setMessage({ tone: "error", text: r.error });
  };

  const loadSample = async () => {
    if (!api) return;
    try {
      const s = await api.sample();
      setFlow(s.flow);
      setWorld(s.world);
      setPositions({});
      setSim(null);
      setSelected(null);
      setSimForm(DEFAULT_SIM);
      setMessage({ tone: "info", text: "Loaded Batt's sample (town → NPC warp → farm loop; a death respawns in town). Synthetic maps and keys; simulated on the synthetic sample sheets." });
    } catch (e) {
      setMessage({ tone: "error", text: `No sample: ${e instanceof ApiError ? e.reason : String(e)}` });
    }
  };

  const importFile = async (file: File) => {
    if (file.size > MAX_JSON_BYTES) return setMessage({ tone: "error", text: `${file.name}: larger than ${MAX_JSON_BYTES} bytes` });
    const r = importFlow(await file.text());
    if (!r.ok) return setMessage({ tone: "error", text: `${file.name}: ${r.errors.join(" · ")}` });
    setFlow(r.flow);
    setPositions({});
    setSim(null);
    setSelected(null);
    setMessage({ tone: "info", text: `${file.name}: imported; the backend validates it with MW1's schema at the next lint.` });
  };

  const exportFile = () => {
    const url = URL.createObjectURL(new Blob([exportText(flow)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${flow.name}.flow.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const simulate = async (form: SimForm) => {
    if (!api) return;
    setSimBusy(true);
    try {
      const doc = await api.simulate(flow, world, scenarioOf(form));
      setSim({ doc, for: canonical(flow) });
      setLint({ doc: doc.lint, for: canonical(flow) });
      setTab("simulate");
    } catch (e) {
      setMessage({ tone: "error", text: `Simulate failed: ${e instanceof ApiError ? e.message : String(e)}` });
    } finally {
      setSimBusy(false);
    }
  };

  const open = (id: string) => {
    const s = scopeOf(flow, id);
    if (s) setEditor(s);
  };

  const lintDoc = lint?.doc ?? null;
  const lintStale = lint !== null && lint.for !== key;
  const simDoc = sim?.doc ?? null;
  const simStale = sim !== null && sim.for !== key;
  const total = lintDoc
    ? lintLine({ ...lintDoc.counts, unsupported: lintDoc.findings.filter((f) => f.rule === "bindings").length })
    : null;

  return (
    <main className="flex h-[calc(100vh-49px)] flex-col" data-testid="flows-app">
      <div className="flex flex-wrap items-center gap-2 border-b border-neutral-800 px-4 py-2 text-sm">
        <span className="font-semibold">Flows</span>
        <span className="text-neutral-400">
          {flow.name} · {flow.workflow ? `${flow.workflow.blocks.length} map block(s)` : "plain flow"} · hash{" "}
          <code>{lintDoc && !lintStale ? lintDoc.flow_hash.slice(0, 12) : "…"}</code>
        </span>
        <span className="rounded bg-amber-900/60 px-2 py-0.5 text-xs text-amber-200">SIMULATE only · no live run in MW2</span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <button className="rounded bg-neutral-800 px-2.5 py-1 text-xs hover:bg-neutral-700" onClick={() => void loadSample()}>Load sample</button>
          <button className="rounded bg-neutral-800 px-2.5 py-1 text-xs hover:bg-neutral-700" onClick={() => { setFlow(emptyFlow()); setPositions({}); setSim(null); setSelected(null); }}>New</button>
          <button className="rounded bg-neutral-800 px-2.5 py-1 text-xs hover:bg-neutral-700" onClick={() => fileRef.current?.click()}>Import JSON</button>
          <input ref={fileRef} type="file" accept=".json,application/json" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void importFile(f); }} />
          <button className="rounded bg-neutral-800 px-2.5 py-1 text-xs hover:bg-neutral-700" onClick={exportFile}>Export JSON</button>
          <button className="rounded bg-neutral-800 px-2.5 py-1 text-xs hover:bg-neutral-700" onClick={() => edit(addBlock(flow))} disabled={!flow.workflow}>+ Map block</button>
          <label className="text-xs text-neutral-400">
            static data{" "}
            <select className="rounded border border-neutral-700 bg-neutral-900 px-1 py-0.5 text-xs" value={world} onChange={(e) => setWorld(e.target.value as WorldSource)}>
              <option value="local">local data/kb (lab)</option>
              <option value="sample">synthetic sample sheets</option>
            </select>
          </label>
          <button className="rounded bg-sky-800 px-2.5 py-1 text-xs hover:bg-sky-700" onClick={() => void runLint(flow, world)}>Lint</button>
          <button className="rounded bg-fuchsia-800 px-2.5 py-1 text-xs hover:bg-fuchsia-700 disabled:opacity-50" disabled={simBusy} onClick={() => void simulate(simForm)}>Simulate</button>
        </div>
      </div>
      {(message || total || notes.length > 0) && (
        <div className="flex flex-wrap gap-3 border-b border-neutral-900 px-4 py-1 text-xs">
          {total && <span className={lintStale ? "text-neutral-500" : "text-neutral-300"}>lint: {total.text}{lintStale ? " (stale)" : ""}</span>}
          {notes.map((n) => <span key={n} className="text-amber-300">{n}</span>)}
          {message && <span className={message.tone === "error" ? "text-red-300" : "text-sky-300"}>{message.text}</span>}
        </div>
      )}
      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1">
          <FlowCanvas
            flow={flow}
            positions={positions}
            lint={lintDoc}
            lintStale={lintStale}
            trace={simDoc && !simStale ? simDoc.trace : null}
            catalogue={catalogue}
            selected={selected}
            onSelect={(id) => { setSelected(id); if (id) setTab("inspect"); }}
            onOpen={open}
            onMove={(p) => setPositions((old) => ({ ...old, ...p }))}
            onConnectExit={(from: string, kind: AuthoredExit, to: string) => edit(connectExit(flow, from, kind, to))}
            onDeleteExit={(path: string) => edit(removeExit(flow, path))}
            onNotes={setNotes}
          />
        </div>
        <aside className="flex w-[460px] shrink-0 flex-col border-l border-neutral-800">
          <div className="flex gap-1 border-b border-neutral-800 px-2 py-1">
            {TABS.map(([t, label]) => (
              <button key={t} className={`rounded px-2.5 py-1 text-xs ${tab === t ? "bg-neutral-800 text-white" : "text-neutral-400 hover:bg-neutral-900"}`} onClick={() => setTab(t)}>
                {label}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-3">
            {tab === "inspect" && (
              <InspectPanel
                flow={flow}
                selected={selected}
                lint={lintDoc}
                sim={simDoc && !simStale ? simDoc : null}
                onUpdate={(name: string, props: BlockProps) => { edit(updateBlock(flow, name, props)); if (props.name !== name) setSelected(`block:${props.name}`); }}
                onDelete={(name) => { edit(removeBlock(flow, name)); setSelected(null); }}
                onStart={(name, entry) => edit(setStart(flow, name, entry))}
                onOpen={open}
                onSimulateHere={(b) => { const f = { ...simForm, startBlock: b, single: true }; setSimForm(f); void simulate(f); }}
              />
            )}
            {tab === "lint" && <LintPanel lint={lintDoc} stale={lintStale} onSelect={(o) => setSelected(o.startsWith("block:") ? o : o === "global" ? "events:global" : null)} />}
            {tab === "simulate" && (
              <SimulatePanel flow={flow} form={simForm} setForm={setSimForm} sim={simDoc} stale={simStale} busy={simBusy} world={world} api={api} onRun={() => void simulate(simForm)} />
            )}
            {(tab === "json" || tab === "python") && <TextPanel flow={flow} kind={tab} api={api} />}
          </div>
        </aside>
      </div>
      {editor && (
        <BlockEditor
          flow={flow}
          scope={editor.scope}
          title={editor.title}
          catalogue={catalogue}
          lint={lintStale ? null : lintDoc}
          trace={simDoc && !simStale ? simDoc.trace : null}
          onClose={() => setEditor(null)}
          onApply={(f, warnings) => {
            setFlow(f);
            setEditor(null);
            setMessage(
              canonical(f) === key
                ? { tone: "info", text: "Applied: no change (the IR is identical)." }
                : { tone: "info", text: `Applied to the flow.${warnings.length ? ` ${warnings.join(" · ")}` : ""}` },
            );
          }}
        />
      )}
    </main>
  );
}
