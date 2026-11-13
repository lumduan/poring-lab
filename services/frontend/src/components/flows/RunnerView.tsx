"use client";

// A RUNNER FLOW on /flows (Batt 2026-11-12: "make the flows of this map, so I can see how the bot
// works"): a live runner's loop (scripts/dungeon_hunt.py run, the xmas_dun02 Rogue) as blocks, its
// Python outline BESIDE them, in the studio's layout (matpilot.org/blocks). The description is
// GENERATED from the runner's code (scripts/runner_flow_export.py -> lib/flow/runners/*.gen.ts);
// this page only SHOWS it and SIMULATES it in the browser on an example (lib/flow/runner_sim.ts).
//
// Nothing here runs: no backend call at all (not even the flow engine's), no executor, no mux, no
// input path. The blocks are fixed in place; every extracted value is rendered as React text.
import "./flows.css"; // Blockly's hidden scrollbars stay hidden (the block editor's rule)
import "./studio.css";

import type * as BlocklyT from "blockly/core";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { registerRunner, runnerThemes } from "@/components/flows/blockly-runner";
import CodeView from "@/components/flows/CodeView";
import LiveRun, { LiveRunButtons, useLiveRun } from "@/components/flows/LiveRun";
import { EXIT_COLOURS } from "@/components/flows/FlowCanvas";
import { browserStorage, KEYS, pythonDefault, readChoice, writeChoice } from "@/lib/flow/prefs";
import { allNodes, commandPieces, findNode, markOf, type RunnerDoc, type RunnerNode, type RunnerSettingsDoc, type RunSettings, runnerWorkspace, settingsProblem, textOf, titleOf, valueText, withSettings } from "@/lib/flow/runner";
import { EXAMPLE, type SimResult, simulate } from "@/lib/flow/runner_sim";
import { INJECT } from "@/lib/flow/theme";

const VIEWS = ["blocks", "python"] as const;
const OPEN_CLOSED = ["open", "closed"] as const;
type Pane = "inspect" | "results" | "command";
const PANES: [Pane, string][] = [
  ["inspect", "Inspect"],
  ["results", "Results"],
  ["command", "Command"],
];
const PLAY_MS = 900;
const KIND_WORD: Record<RunnerNode["kind"], string> = { hat: "a start block", step: "a block", loop: "a loop", if: "an if block" };

const darkQuery = () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null);

// The runner flows the Run panel can start (scripts/flow_run.py's FLOWS; 2026-11-13)
const LIVE_FLOWS: readonly string[] = ["xmas_dun02_rogue"];

/** The person's Run settings, remembered per flow in this browser (a convenience; the Run helper
 * checks them again). Unknown or broken: the export's defaults. */
function readSettings(store: ReturnType<typeof browserStorage>, id: string, d: RunnerSettingsDoc): RunSettings {
  try {
    const v = JSON.parse(store?.getItem(`poring-lab.flows.runsettings.${id}.v1`) ?? "null") as Partial<RunSettings> | null;
    const s = { ...d.defaults, ...(v ?? {}) };
    return settingsProblem(s, d) === null ? s : { ...d.defaults };
  } catch {
    return { ...d.defaults };
  }
}

export default function RunnerView({ doc: rawDoc, onBack, backendUrl = null }: { doc: RunnerDoc; onBack: () => void; backendUrl?: string | null }) {
  const store = useMemo(() => browserStorage(), []);
  // 2026-11-13 (Batt): the hotbar keys and the weight limit are the person's, shown in the blocks
  const sdoc = rawDoc.settings ?? null;
  const [runSettings, setRunSettingsState] = useState<RunSettings | null>(() => (sdoc ? readSettings(store, rawDoc.id, sdoc) : null));
  const setRunSettings = useCallback(
    (s: RunSettings) => {
      setRunSettingsState(s);
      try {
        store?.setItem(`poring-lab.flows.runsettings.${rawDoc.id}.v1`, JSON.stringify(s));
      } catch {
        // unremembered: this tab keeps them
      }
    },
    [store, rawDoc.id],
  );
  const doc = useMemo(() => (runSettings ? withSettings(rawDoc, runSettings) : rawDoc), [rawDoc, runSettings]);
  const settingsWhy = runSettings && sdoc ? settingsProblem(runSettings, sdoc) : null;
  const isLive = LIVE_FLOWS.includes(doc.id);
  const live = useLiveRun(backendUrl, doc.id, isLive); // one poller: the header's Run and the panel
  const [view, setViewState] = useState<(typeof VIEWS)[number]>(() => readChoice(store, KEYS.view, VIEWS, "blocks"));
  const [pythonPanel, setPythonPanel] = useState<(typeof OPEN_CLOSED)[number]>(() => {
    const wide = typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(min-width: 48rem)").matches : true;
    return readChoice(store, KEYS.python, OPEN_CLOSED, pythonDefault(wide));
  });
  const [panes, setPanes] = useState<Record<Pane, boolean>>({ inspect: true, results: false, command: false });
  const [selected, setSelected] = useState<string>(doc.stacks[0]?.id ?? "");
  const [knife, setKnife] = useState(false);
  const [sim, setSim] = useState<SimResult | null>(null);
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [follow, setFollow] = useState<string | null>(null); // the block the simulation is on
  const [copied, setCopied] = useState<"idle" | "ok" | "failed">("idle");
  const codeRef = useRef<HTMLPreElement | null>(null);

  const node = findNode(doc, selected) ?? doc.stacks[0];
  const mark = node ? markOf(node) : null;
  const pythonOpen = view === "blocks" && pythonPanel === "open";
  const nBlocks = useMemo(() => allNodes(doc).length, [doc]);

  const setView = (v: (typeof VIEWS)[number]) => {
    setViewState(v);
    writeChoice(store, KEYS.view, v);
  };
  const togglePython = () => {
    const next = pythonPanel === "open" ? "closed" : "open";
    setPythonPanel(next);
    writeChoice(store, KEYS.python, next);
  };
  const setPane = (p: Pane, open: boolean) => setPanes((old) => ({ ...old, [p]: open }));

  // --- SIMULATE: the example, in the browser (no game, no input, no backend)
  const show = useCallback((r: SimResult | null, i: number) => {
    if (!r || !r.steps.length) return;
    const k = Math.max(0, Math.min(r.steps.length - 1, i));
    setStep(k);
    setSelected(r.steps[k].block);
    setFollow(r.steps[k].block);
  }, []);
  const run = () => {
    const r = simulate(doc, EXAMPLE, { knife });
    setSim(r);
    show(r, 0);
    setPlaying(true);
    setPane("results", true);
  };
  const goStep = useCallback((i: number) => show(sim, i), [show, sim]);
  // Play: one step every PLAY_MS (the state changes in the timer, never in the effect itself)
  useEffect(() => {
    if (!playing || !sim) return;
    const t = setTimeout(() => (step >= sim.steps.length - 1 ? setPlaying(false) : goStep(step + 1)), PLAY_MS);
    return () => clearTimeout(t);
  }, [playing, step, sim, goStep]);

  // a block the person clicked: the inspector and the Python follow it, and a playing simulation
  // pauses (its highlight goes: the block in view is the one clicked)
  const onBlock = useCallback((id: string) => {
    setSelected(id);
    setPlaying(false);
    setFollow(null);
  }, []);

  const copy = () => {
    void (navigator.clipboard?.writeText(doc.python) ?? Promise.reject(new Error("no clipboard"))).then(
      () => setCopied("ok"),
      () => {
        setCopied("failed");
        const pre = codeRef.current;
        const sel = window.getSelection();
        if (pre && sel) sel.selectAllChildren(pre);
      },
    );
  };
  useEffect(() => {
    if (copied !== "ok") return;
    const t = setTimeout(() => setCopied("idle"), 2000);
    return () => clearTimeout(t);
  }, [copied]);

  const cur = sim?.steps[step] ?? null;
  const openPanes = PANES.filter(([p]) => panes[p]);
  const status = cur
    ? `Simulation step ${step + 1} of ${sim?.steps.length}, at ${cur.t} s: ${cur.text}`
    : "A description of the runner: click a block to see its numbers, its flags and its Python. Simulate plays an example.";

  const codePane = (full: boolean) => (
    <>
      <div className="studio-panel-header">
        <h2 id={full ? "runner-python-full" : "runner-python-side"}>{full ? "Python: an outline of the runner" : "Python"}</h2>
        <div className="button-row">
          <button type="button" className="button button-small" onClick={copy} title="Copy the Python outline">
            {copied === "ok" ? "Copied" : "Copy"}
          </button>
        </div>
        {!full && (
          <button type="button" className="icon-button" onClick={togglePython} title="Close the Python panel">
            <CloseIcon />
            <span className="visually-hidden">Close the Python panel</span>
          </button>
        )}
      </div>
      <div className="python-files" role="tablist" aria-label="Files">
        <button type="button" role="tab" className="python-file" aria-selected={true}>
          {doc.file}
        </button>
      </div>
      <p className="studio-panel-note">An outline of {doc.script} with the code&apos;s own numbers (generated); it is not the runner and never runs.</p>
      {runSettings && (
        <p className="studio-panel-note" data-testid="runner-python-settings">
          Your Run settings (added to the command when you press Run): <code>--fly-key {runSettings.fly_key} --player-home-key {runSettings.home_key} --weight-home {runSettings.weight_home.toFixed(2)}</code>
        </p>
      )}
      <CodeView ref={codeRef} code={doc.python} colour mark={mark} label={`Python: ${doc.file}`} testId="runner-python" />
    </>
  );

  return (
    <main className="studio" data-view={view} data-testid="runner-view">
      <header className="studio-bar">
        <div className="studio-brand">
          <span className="studio-home">Flows</span>
          <span className="status-pill" title="A description of the runner; Simulate plays an example; Run (beside it) starts the real runner in the game">
            {LIVE_FLOWS.includes(doc.id) ? "DESCRIPTION · SIMULATE · RUN" : "DESCRIPTION · SIMULATE only"}
          </span>
          <h1 className="studio-title" title={doc.title}>
            {doc.title}
          </h1>
        </div>
        <div className="segmented" role="group" aria-label="View">
          {VIEWS.map((v) => (
            <button key={v} type="button" className="segmented-option" aria-pressed={view === v} onClick={() => setView(v)} data-testid={`runner-view-${v}`}>
              {v === "blocks" ? "Blocks" : "Python"}
            </button>
          ))}
        </div>
        <div className="studio-actions">
          <button type="button" className="button button-small button-file" onClick={onBack} title="Back to the flow you were editing" data-testid="runner-back">
            <span aria-hidden="true">◂</span>
            <span className="button-text">My flow</span>
          </button>
          <button type="button" className="button button-primary button-run" onClick={run} title="Play an example run of this description: no game, no input" data-testid="runner-simulate">
            <PlayIcon />
            <span className="button-text">Simulate</span>
          </button>
          {isLive && <LiveRunButtons live={live} settings={runSettings} blocked={settingsWhy} />}
        </div>
      </header>

      <div className="studio-notices">
        <p className="notice" role="note" data-testid="runner-notice">
          A DESCRIPTION of <code>{doc.script}</code>, made from its code by <code>scripts/runner_flow_export.py</code>: the blocks are the runner&apos;s loop in plain words, and every number
          and flag is the code&apos;s own. Click a block to see them. The blocks and Simulate run nothing in the game
          {isLive ? "; Run (at the top, beside Simulate) starts the real runner on this map (player mode)." : "."}
        </p>
        {isLive && <LiveRun live={live} />}
        {copied === "failed" && (
          <p className="notice notice-warn" role="status">
            This browser would not copy automatically (the page is not a secure origin). The code is selected: press Ctrl+C (⌘C) to copy it.
          </p>
        )}
      </div>

      <RunnerBinding doc={doc} />
      {sdoc && runSettings && <RunSettingsStrip d={sdoc} s={runSettings} why={settingsWhy} onChange={setRunSettings} />}

      <div className="device-bar" aria-label="The runner">
        <Chip label="runner" value={doc.script} />
        <Chip label="version" value={doc.version} />
        <Chip label="map" value={doc.map} />
        <Chip label="character" value={String(doc.params["cmd.char"]?.value ?? doc.char)} />
        <Chip label="strategy" value={String(doc.params["cmd.strategy"]?.value ?? "")} />
        <Chip label="time box" value={`${valueText(doc.params["cmd.minutes"]?.value)} min`} />
        <Chip label="blocks" value={String(nBlocks)} />
      </div>

      <div className="studio-body" data-python-panel={pythonOpen ? "open" : "closed"}>
        <div className="studio-canvas">
          <div className="block-tabs-bar">
            <div className="block-tabs" role="tablist" aria-label="Tabs">
              <div className="block-tab" data-active={true}>
                <button type="button" role="tab" aria-selected={true} className="block-tab-name" title="The runner's loop, its safety rules and the optional flag set">
                  how it hunts
                </button>
              </div>
            </div>
            <div className="block-tabs-trailing robot-picker">
              <span className="robot-picker-label" title={`This description is bound to the map ${doc.map}`}>
                <span className="robot-picker-name">Map</span> <strong>{doc.map}</strong>
              </span>
            </div>
          </div>
          <div className="blocks-area">
            <RunnerBlocks doc={doc} follow={follow} hidden={view === "python"} onSelect={onBlock} />
          </div>
          {view === "python" && (
            <section className="studio-python-full" aria-labelledby="runner-python-full">
              {codePane(true)}
            </section>
          )}
        </div>
        {pythonOpen && (
          <aside className="studio-side" aria-labelledby="runner-python-side" data-testid="runner-python-side">
            {codePane(false)}
          </aside>
        )}
      </div>

      {openPanes.length > 0 && (
        <div className="studio-drawer" data-panes={openPanes.length}>
          {openPanes.map(([p, label]) => (
            <section key={p} className="pane" aria-labelledby={`runner-pane-${p}`}>
              <div className="studio-panel-header">
                <h2 id={`runner-pane-${p}`}>{label}</h2>
                <button type="button" className="icon-button" onClick={() => setPane(p, false)} title={`Close ${label}`}>
                  <CloseIcon />
                  <span className="visually-hidden">Close {label}</span>
                </button>
              </div>
              <div className="pane-body">
                {p === "inspect" && node && <InspectRunner doc={doc} node={node} />}
                {p === "results" && (
                  <ResultsPane
                    sim={sim}
                    step={step}
                    playing={playing}
                    knife={knife}
                    onKnife={setKnife}
                    onRun={run}
                    onStep={(i) => {
                      setPlaying(false);
                      goStep(i);
                    }}
                    onPlay={() => setPlaying(!playing)}
                  />
                )}
                {p === "command" && <CommandPane doc={doc} />}
              </div>
            </section>
          ))}
        </div>
      )}

      <footer className="studio-status">
        <p className="studio-status-text" data-testid="runner-status" aria-live="polite">
          {status}
        </p>
        <div className="studio-toggles" role="group" aria-label="Panels">
          {view === "blocks" && (
            <button type="button" className="toggle-button" aria-pressed={pythonOpen} onClick={togglePython}>
              Python
            </button>
          )}
          {PANES.map(([p, label]) => (
            <button key={p} type="button" className="toggle-button" aria-pressed={panes[p]} onClick={() => setPane(p, !panes[p])} data-testid={`runner-toggle-${p}`}>
              {label}
            </button>
          ))}
        </div>
      </footer>
    </main>
  );
}

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <div className="device-chip">
      <span className="device-label">{label}</span>
      <span className="device-value">{value}</span>
    </div>
  );
}

/** The blocks: Blockly (zelos, the studio's themes), every block fixed in place. A click on a block
 * selects it (the inspector and the Python follow); the simulation's block is highlighted (Blockly's
 * glow, as for code being stepped through) and scrolled into view. */
function RunnerBlocks({ doc, follow, hidden, onSelect }: { doc: RunnerDoc; follow: string | null; hidden: boolean; onSelect: (id: string) => void }) {
  const host = useRef<HTMLDivElement | null>(null);
  const ws = useRef<BlocklyT.WorkspaceSvg | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const latest = useRef(onSelect);
  useEffect(() => {
    latest.current = onSelect;
  });

  useEffect(() => {
    let disposed = false;
    let resize: ResizeObserver | null = null;
    const media = darkQuery();
    let onMedia: (() => void) | null = null;
    void (async () => {
      try {
        const B = await import("blockly/core");
        const En = await import("blockly/msg/en");
        if (disposed || !host.current) return;
        B.setLocale(En as unknown as Record<string, string>);
        registerRunner(B, doc);
        const th = runnerThemes(B);
        const w = B.inject(host.current, {
          ...INJECT,
          trashcan: false,
          theme: media?.matches ? th.dark : th.light,
        } as unknown as BlocklyT.BlocklyOptions);
        ws.current = w;
        B.Events.disable();
        try {
          B.serialization.workspaces.load(runnerWorkspace(doc) as unknown as object, w);
          B.renderManagement.triggerQueuedRenders(w); // drawn now: the layout needs their sizes
          layout(B, w, doc);
        } finally {
          B.Events.enable();
        }
        w.clearUndo();
        // a person's click on a block (Blockly's CLICK event: gestures only, never a selection
        // made by code)
        w.addChangeListener((e: BlocklyT.Events.Abstract) => {
          if (e.type !== B.Events.CLICK) return;
          const c = e as BlocklyT.Events.Click;
          if (c.targetType === "block" && c.blockId && w.getBlockById(c.blockId)) latest.current(c.blockId);
        });
        resize = new ResizeObserver(() => B.svgResize(w));
        resize.observe(host.current);
        onMedia = () => w.setTheme(media?.matches ? th.dark : th.light);
        media?.addEventListener("change", onMedia);
        setState("ready");
      } catch (e) {
        console.warn("the runner's blocks could not be loaded", e);
        setState("failed");
      }
    })();
    return () => {
      disposed = true;
      resize?.disconnect();
      if (onMedia) media?.removeEventListener("change", onMedia);
      ws.current?.dispose();
      ws.current = null;
    };
  }, [doc]);

  // the simulation's block: highlighted and scrolled into view
  useEffect(() => {
    const w = ws.current;
    if (!w || state !== "ready") return;
    w.highlightBlock(null);
    if (follow && w.getBlockById(follow)) {
      w.highlightBlock(follow, true);
      w.centerOnBlock(follow);
    }
  }, [follow, state]);

  return (
    <>
      <div ref={host} className="blocks-workspace" data-testid="runner-blocks" data-status={state} inert={hidden} />
      {state === "failed" && <p className="notice notice-error blocks-failed">The blocks could not be loaded. Reload the page to try again.</p>}
    </>
  );
}

/** The stacks side by side by their drawn size: the run on the left, the safety rules and the
 * optional flag set to its right. */
function layout(B: typeof BlocklyT, w: BlocklyT.WorkspaceSvg, doc: RunnerDoc): void {
  const tops = doc.stacks.map((s) => w.getBlockById(s.id) as BlocklyT.BlockSvg | null);
  const main = tops[0];
  if (!main) return;
  const x = 24 + main.getHeightWidth().width + 72;
  let y = 24;
  for (const b of tops.slice(1)) {
    if (!b) continue;
    b.moveTo(new B.utils.Coordinate(x, y));
    y += b.getHeightWidth().height + 56;
  }
}

function InspectRunner({ doc, node }: { doc: RunnerDoc; node: RunnerNode }) {
  const [a, b] = markOf(node);
  return (
    <div className="stack runner-inspect" data-testid="runner-inspect">
      <p>
        <span className="muted">{KIND_WORD[node.kind]}</span> <strong>{titleOf(node)}</strong>
      </p>
      {node.branches && node.branches.length > 1 && (
        <ul className="runner-list">
          {node.branches.map((br, i) => (
            <li key={i}>{textOf(br.parts)}</li>
          ))}
        </ul>
      )}
      <p>{node.why}</p>
      {node.params.length > 0 && (
        <table className="runner-table">
          <caption className="muted">Numbers, read from the code</caption>
          <thead>
            <tr>
              <th scope="col">number</th>
              <th scope="col">value</th>
              <th scope="col">where it comes from</th>
            </tr>
          </thead>
          <tbody>
            {node.params.map((id) => {
              const p = doc.params[id];
              return (
                <tr key={id}>
                  <td>
                    <code>{id}</code>
                  </td>
                  <td className="strong">{valueText(p?.value)}</td>
                  <td>
                    {p?.source}
                    {p?.note ? <span className="muted"> · {p.note}</span> : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {node.flags.length > 0 && (
        <div>
          <p className="muted">Flags (the help text is the code&apos;s own)</p>
          <ul className="runner-list">
            {node.flags.map((f) => {
              const fl = doc.flags[f];
              return (
                <li key={f}>
                  <code>{f}</code> <span className="strong">{fl ? (fl.kind === "bool" ? (fl.base ? "on in the base" : "optional") : `${valueText(fl.value)}${fl.base ? "" : " (optional)"}`) : ""}</span>
                  {fl?.help ? <span className="muted"> · {fl.help}</span> : null}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {node.code.length > 0 && (
        <p>
          <span className="muted">In the code: </span>
          {node.code.map((c, i) => (
            <span key={c}>
              {i > 0 ? ", " : ""}
              <code>{c.includes(".") ? c : `dungeon_hunt.${c}`}</code>
            </span>
          ))}
        </p>
      )}
      <p className="muted">
        Python lines {a}
        {b !== a ? `-${b}` : ""} of {doc.file}
      </p>
    </div>
  );
}

function ResultsPane(p: { sim: SimResult | null; step: number; playing: boolean; knife: boolean; onKnife: (on: boolean) => void; onRun: () => void; onStep: (i: number) => void; onPlay: () => void }) {
  const { sim, step } = p;
  const list = useRef<HTMLOListElement | null>(null);
  useEffect(() => {
    // the current step kept in view inside the list (never the page)
    const ol = list.current;
    const li = ol?.children[step] as HTMLElement | undefined;
    const box = ol?.closest(".pane-body") as HTMLElement | null | undefined;
    if (!li || !box) return;
    const top = li.offsetTop - box.offsetTop;
    if (top < box.scrollTop || top + li.offsetHeight > box.scrollTop + box.clientHeight) box.scrollTop = Math.max(0, top - box.clientHeight / 2);
  }, [step, sim]);
  return (
    <div className="stack" data-testid="runner-results">
      <p className="studio-panel-note">
        {EXAMPLE.note} The simulation models the blocks&apos; rules with the code&apos;s numbers; it is not the runner and plays no game.
      </p>
      <div className="row">
        <label className="row">
          <input type="checkbox" checked={p.knife} onChange={(e) => p.onKnife(e.target.checked)} data-testid="runner-knife" />
          with the Knife opener (an optional flag set)
        </label>
        <button type="button" className="button button-small" onClick={p.onRun}>
          {sim ? "Simulate again" : "Simulate"}
        </button>
      </div>
      {sim && (
        <>
          <p>
            <span className="strong">{sim.kills}</span> kills · <span className="strong">{sim.picks}</span> items picked · <span className="strong">{sim.strikes}</span> strikes ·{" "}
            <span className="strong">{sim.potions}</span> potions · <span className="strong">{sim.wings}</span> Fly Wings · ended by <span className="strong">{sim.end}</span>
          </p>
          <div className="row" role="group" aria-label="Steps">
            <button type="button" className="button button-small" onClick={() => p.onStep(step - 1)} disabled={step <= 0}>
              ◂ Back
            </button>
            <button type="button" className="button button-small" onClick={p.onPlay}>
              {p.playing ? "Pause" : "Play"}
            </button>
            <button type="button" className="button button-small" onClick={() => p.onStep(step + 1)} disabled={step >= sim.steps.length - 1}>
              Next ▸
            </button>
            <span className="muted">
              step {step + 1} of {sim.steps.length}
            </span>
          </div>
          <ol className="runner-steps" ref={list} data-testid="runner-steps">
            {sim.steps.map((s, i) => (
              <li key={i} data-active={i === step} data-tone={s.tone}>
                <button type="button" className="problem-link" onClick={() => p.onStep(i)}>
                  <span className="muted">{s.t} s</span> {s.text}
                </button>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}

function CommandPane({ doc }: { doc: RunnerDoc }) {
  const flags = Object.entries(doc.flags);
  return (
    <div className="stack" data-testid="runner-command">
      <p className="muted">The base command (as the night pilots ran it; --seed and --label vary per run):</p>
      <p className="runner-command">
        <code>{doc.script}</code> {commandPieces(doc.command.base).join(" ")}
      </p>
      {doc.command.optional.map((o) => (
        <div key={o.name}>
          <p>
            <span className="strong">Optional: {o.title}</span> <code>{o.flags.join(" ")}</code>
          </p>
          <p className="muted">{o.note}</p>
        </div>
      ))}
      <table className="runner-table">
        <caption className="muted">Every flag above, with the code&apos;s own help text</caption>
        <thead>
          <tr>
            <th scope="col">flag</th>
            <th scope="col">here</th>
            <th scope="col">default</th>
            <th scope="col">what it does</th>
          </tr>
        </thead>
        <tbody>
          {flags.map(([f, fl]) => (
            <tr key={f}>
              <td>
                <code>{f}</code>
              </td>
              <td className="strong">{fl.base ? valueText(fl.value) : `optional: ${valueText(fl.value)}`}</td>
              <td>{valueText(fl.default)}</td>
              <td>{fl.help ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">Generated by {doc.generated_by}.</p>
    </div>
  );
}

// --- icons (MatPilot's, as FlowsApp has them) ---------------------------------------------------
function CloseIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function PlayIcon() {
  return (
    <svg className="button-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path d="M5 3.5v9l7.5-4.5z" fill="currentColor" />
    </svg>
  );
}

/** The binding strip (as /flows' MapBinding): the map this runner plays, where its flow begins and
 * the map's EXITS it takes (dungeon@9.41, Batt 2026-11-13: a bag over 50 % -> a Butterfly Wing
 * home; a death -> respawn at the save point), from the export (an older one has none). */
function RunnerBinding({ doc }: { doc: RunnerDoc }) {
  const exits = doc.exits ?? [];
  return (
    <div className="map-binding" data-kind="block" data-testid="runner-binding">
      <span className="mb-part">
        <span className="mb-key">bound to map</span> <strong>{doc.map}</strong> <span className="muted">(the {doc.char}&apos;s runner)</span>
      </span>
      {doc.entry && (
        <span className="mb-part">
          <span className="mb-key">starts</span>
          {doc.entry}
        </span>
      )}
      <span className="mb-part" data-testid="runner-exits">
        <span className="mb-key">exits</span>
        {exits.length === 0 && <span className="muted">none in this export: the run ends on the map</span>}
        {exits.map((x, i) => (
          <span key={x.id} style={{ color: EXIT_COLOURS[x.kind] }}>
            {i > 0 && " · "}→ {x.to} <span className="mb-how">({x.when}: {x.how})</span>
          </span>
        ))}
      </span>
    </div>
  );
}

/** The Run settings strip (2026-11-13, Batt: "the Butterfly Wing on F9, the Fly Wing on F8; don't
 * hard-code them, a user changes them"): the hotbar keys and the weight limit, each from the
 * export's fixed choices; the blocks show the choice at once, and Run sends it. */
function RunSettingsStrip({ d, s, why, onChange }: { d: RunnerSettingsDoc; s: RunSettings; why: string | null; onChange: (s: RunSettings) => void }) {
  const keys = d.keys.filter((k) => !d.reserved.includes(k));
  return (
    <div className="map-binding run-settings" data-kind={why ? "plain" : "block"} data-testid="run-settings">
      <span className="mb-part">
        <span className="mb-key">your run settings</span>
      </span>
      <label className="mb-part">
        Fly Wing key{" "}
        <select value={s.fly_key} onChange={(e) => onChange({ ...s, fly_key: e.target.value })} data-testid="run-settings-fly">
          {keys.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </label>
      <label className="mb-part">
        Butterfly Wing key{" "}
        <select value={s.home_key} onChange={(e) => onChange({ ...s, home_key: e.target.value })} data-testid="run-settings-home">
          {keys.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </label>
      <label className="mb-part">
        go home when the bag is over{" "}
        <select value={String(s.weight_home)} onChange={(e) => onChange({ ...s, weight_home: Number(e.target.value) })} data-testid="run-settings-weight">
          {d.weights.map((w) => (
            <option key={w} value={String(w)}>
              {Math.round(w * 100)} %
            </option>
          ))}
        </select>
      </label>
      <RespawnAt s={s} onChange={onChange} />
      <button type="button" className="mb-link" onClick={() => onChange({ ...d.defaults })} data-testid="run-settings-reset">
        defaults ({d.defaults.fly_key}, {d.defaults.home_key}, {Math.round(d.defaults.weight_home * 100)} %, respawn at {d.defaults.respawn_at})
      </button>
      <span className="mb-part muted">taken by the run: {d.reserved.join(", ")}</span>
      {why && (
        <span className="mb-part mb-warn" role="status">
          {why}
        </span>
      )}
    </div>
  );
}

/** The respawn button's point, X and Y in the game picture (Batt 2026-11-13: another server's death
 * menu may differ; the respawn function block shows it). Typed numbers; checked by settingsProblem. */
function RespawnAt({ s, onChange }: { s: RunSettings; onChange: (s: RunSettings) => void }) {
  const [x, y] = (s.respawn_at ?? "").split(",");
  const set = (nx: string, ny: string) => onChange({ ...s, respawn_at: `${nx.replace(/\D/g, "").slice(0, 4)},${ny.replace(/\D/g, "").slice(0, 4)}` });
  return (
    <span className="mb-part" title="Where the respawn function block presses: the death menu's 'move to saved location' button, in game-picture pixels">
      respawn button at x{" "}
      <input className="run-settings-num" value={x ?? ""} onChange={(e) => set(e.target.value, y ?? "")} inputMode="numeric" size={4} aria-label="respawn button x" data-testid="run-settings-respawn-x" />{" "}
      y{" "}
      <input className="run-settings-num" value={y ?? ""} onChange={(e) => set(x ?? "", e.target.value)} inputMode="numeric" size={4} aria-label="respawn button y" data-testid="run-settings-respawn-y" />
    </span>
  );
}

