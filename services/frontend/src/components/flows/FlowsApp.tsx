"use client";

// The /flows STUDIO (Batt 2026-11-09, docs/planning/flows-studio.md): matpilot.org/blocks's layout,
// so learners who know it are at home and can go on to real robots: a header (Blocks | Python, Load,
// Save, Start over, the green Simulate), notices, a context bar, the canvas (tabs, then the blocks or
// the workflow map) with the PYTHON BESIDE IT, a drawer of output panes, the problems under the
// blocks, and a status footer with the panel toggles. Everything of MW2's page is kept: the map-block
// workflow canvas (the "Map" tab), inspect, lint, SIMULATE, JSON import / export, the path map and
// the zones layer.
//
// NOTHING here runs live: the green button is SIMULATE (no game, no input). The backend calls are
// computation only (lib/flow/api.ts); the page never reaches the executor, the mux, an agent channel
// or any input path. The heavy libraries load lazily on this page only.
//
// The header and footer markup and the icons follow MatPilot's src/components/blocks/BlocksApp.tsx
// (https://github.com/lumduan/matpilot at commit d639909; MIT License, Copyright (c) 2026 Sarat
// Sonsuk; the licence text is in studio.css and THIRD_PARTY.md).
import "./studio.css";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { EditorApi, EditorState } from "@/components/flows/BlockEditor";
import CodeView from "@/components/flows/CodeView";
import { DEFAULT_SIM, HuntRulesPanel, InspectPanel, LintPanel, PathPanel, scenarioOf, type SimForm, SimulatePanel } from "@/components/flows/Panels";
import { ApiError, type CatalogueDoc, type Finding, FlowsApi, type LintDoc, type SimDoc, type WorldSource } from "@/lib/flow/api";
import type { Scope } from "@/lib/flow/blocks";
import { addBlock, type BlockProps, connectExit, type EditResult, removeBlock, removeExit, setStart, setZonesRef, updateBlock, type XY } from "@/lib/flow/canvas";
import { exportText, importFlow } from "@/lib/flow/importer";
import { type AuthoredExit, canonical, emptyFlow, type Flow, MAX_JSON_BYTES } from "@/lib/flow/ir";
import { browserStorage, KEYS, pythonDefault, readChoice, readText, writeChoice } from "@/lib/flow/prefs";
import { oneMapStarter, STARTER_WORLD, starterFlow } from "@/lib/flow/starter";
import { lintLine } from "@/lib/flow/status";
import { lintErrors, looseText, PROBLEM_HEADS, statusText, tabOf } from "@/lib/flow/words";
import { backendHttpBase } from "@/lib/ws";

const FlowCanvas = dynamic(() => import("@/components/flows/FlowCanvas"), {
  ssr: false,
  loading: () => <p className="muted studio-loading">Loading the map…</p>,
});
const BlockEditor = dynamic(() => import("@/components/flows/BlockEditor"), {
  ssr: false,
  loading: () => <div className="blocks-workspace" data-status="loading" />,
});
const ZonesEditor = dynamic(() => import("@/components/flows/ZonesEditor"), { ssr: false });

const LINT_DEBOUNCE_MS = 2500;
const PYTHON_DEBOUNCE_MS = 350; // after the last converted edit; one request in flight, the latest wins
const PYTHON_RETRY_MS = 5000; // after a "rate_limited"
const SAVE_DEBOUNCE_MS = 800;
const NOTICE_MS = 12_000;
const VIEWS = ["blocks", "python"] as const;
const OPEN_CLOSED = ["open", "closed"] as const;
const WORLDS = ["local", "sample"] as const;
type Pane = "inspect" | "lint" | "simulate" | "paths" | "hunt";
const PANES: [Pane, string][] = [
  ["inspect", "Inspect"],
  ["lint", "Lint"],
  ["simulate", "Results"], // what it shows: "Simulate" always means RUN it (the green button)
  ["paths", "Path map"],
  ["hunt", "Hunt rules"],
];
type Tab = { key: string; label: string; scope: Scope | null };
type Notice = { text: string; tone: "ok" | "warn" | "error"; undo: { flow: Flow; world: WorldSource } | null };
const NO_EDITOR: EditorState = { ready: false, failed: false, issues: [], loose: [], canUndo: false, canRedo: false };

function tabsOf(flow: Flow): Tab[] {
  const events: Tab = { key: "events", label: "events", scope: { kind: "global" } };
  if (!flow.workflow) return [{ key: "main", label: "main", scope: { kind: "main" } }, events];
  return [
    { key: "map", label: "Map", scope: null },
    ...flow.workflow.blocks.map((b) => ({ key: `block:${b.name}`, label: b.name, scope: { kind: "block" as const, name: b.name } })),
    events,
  ];
}

/** The canvas node a tab is about (the Inspect pane shows it). */
function inspectOf(tab: string, selected: string | null): string | null {
  if (tab === "map") return selected;
  if (tab === "events") return "events:global";
  if (tab.startsWith("block:")) return tab;
  return null;
}

/** The tab a canvas node opens. */
function tabFor(id: string): string | null {
  if (id === "events:global") return "events";
  if (id === "main") return "main";
  if (id.startsWith("block:")) return id;
  if (id.startsWith("events:")) return `block:${id.slice(7)}`;
  return null;
}

/** The flow to start with: this browser's last one (checked like an imported file), else the starter. */
function initialFlow(): { flow: Flow; restored: boolean; broken: boolean } {
  const text = readText(browserStorage(), KEYS.flow);
  if (!text) return { flow: starterFlow(), restored: false, broken: false };
  const r = importFlow(text);
  return r.ok ? { flow: r.flow, restored: true, broken: false } : { flow: starterFlow(), restored: false, broken: true };
}

export default function FlowsApp({ backendUrl }: { backendUrl: string | null }) {
  // Client-only (FlowsClient loads this with ssr: false): backendHttpBase reads window.location.
  const [api] = useState<FlowsApi>(() => new FlowsApi(backendHttpBase(backendUrl)));
  const [start] = useState(initialFlow);
  const [flow, setFlowState] = useState<Flow>(start.flow);
  const flowRef = useRef<Flow>(start.flow);
  const [epoch, setEpoch] = useState(0); // the flow was replaced from outside the blocks: reload them
  const [positions, setPositions] = useState<Record<string, XY>>({});
  // the static data the flow is linted and simulated on: the starter's are the sample sheets; a
  // restored flow keeps this browser's choice (2026-11-09 pm)
  const [world, setWorld] = useState<WorldSource>(() =>
    start.restored ? readChoice(browserStorage(), KEYS.world, WORLDS, "local") : STARTER_WORLD,
  );
  const [catalogue, setCatalogue] = useState<CatalogueDoc | null>(null);
  const [engineErr, setEngineErr] = useState<string | null>(null);
  const [lint, setLint] = useState<{ doc: LintDoc; for: string } | null>(null);
  const [sim, setSim] = useState<{ doc: SimDoc; for: string } | null>(null);
  const [simForm, setSimForm] = useState<SimForm>(DEFAULT_SIM);
  const [simBusy, setSimBusy] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [zonesFor, setZonesFor] = useState<string | null>(null);
  const [tab, setTab] = useState<string>(() => tabsOf(start.flow)[0].key);
  const [editor, setEditor] = useState<EditorState>(NO_EDITOR);
  const [editorApi, setEditorApi] = useState<EditorApi | null>(null);
  const pendingShow = useRef<{ tab: string; path: string } | null>(null);
  const [notice, setNotice] = useState<Notice | null>(
    start.broken ? { text: "Your saved flow could not be opened, so the starter program is shown instead.", tone: "warn", undo: null } : null,
  );
  const [canvasNotes, setCanvasNotes] = useState<string[]>([]);
  const [python, setPython] = useState<{ text: string; for: string } | null>(null);
  const [pythonErr, setPythonErr] = useState<string | null>(null);
  const [codeFile, setCodeFile] = useState<"py" | "json">("py");
  const [copied, setCopied] = useState<"idle" | "ok" | "failed">("idle");
  const [menu, setMenu] = useState(false);
  const [more, setMore] = useState(false); // the footer's "More" menu (phones)
  const store = useMemo(() => browserStorage(), []);
  const [view, setViewState] = useState<(typeof VIEWS)[number]>(() => readChoice(store, KEYS.view, VIEWS, "blocks"));
  const [pythonPanel, setPythonPanel] = useState<(typeof OPEN_CLOSED)[number]>(() => {
    const wide = typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(min-width: 48rem)").matches : true;
    return readChoice(store, KEYS.python, OPEN_CLOSED, pythonDefault(wide));
  });
  const [panes, setPanes] = useState<Record<Pane, boolean>>(() =>
    Object.fromEntries(PANES.map(([p]) => [p, readChoice(store, KEYS[p], OPEN_CLOSED, "closed") === "open"])) as Record<Pane, boolean>,
  );
  const fileRef = useRef<HTMLInputElement | null>(null);
  const codeRef = useRef<HTMLPreElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const key = useMemo(() => canonical(flow), [flow]);
  const tabs = useMemo(() => tabsOf(flow), [flow]);
  const active = tabs.find((t) => t.key === tab) ?? tabs[0];

  const setView = (v: (typeof VIEWS)[number]) => {
    setViewState(v);
    writeChoice(store, KEYS.view, v);
  };
  const togglePython = () => {
    const next = pythonPanel === "open" ? "closed" : "open";
    setPythonPanel(next);
    writeChoice(store, KEYS.python, next);
  };
  const setPane = useCallback(
    (p: Pane, open: boolean) => {
      setPanes((old) => ({ ...old, [p]: open }));
      writeChoice(store, KEYS[p], open ? "open" : "closed");
    },
    [store],
  );

  // --- the flow: from the blocks (no reload), or replaced from outside (the blocks reload) --------
  const fromBlocks = useCallback((f: Flow) => {
    flowRef.current = f;
    setFlowState(f);
  }, []);
  const replace = useCallback(
    (f: Flow, opts: { notice?: string; undo?: boolean; world?: WorldSource; keepView?: boolean } = {}) => {
      const prev = { flow: flowRef.current, world };
      flowRef.current = f;
      setFlowState(f);
      setEpoch((e) => e + 1);
      if (!opts.keepView) {
        setPositions({});
        setSim(null);
        setSelected(null);
        setTab(tabsOf(f)[0].key);
      }
      if (opts.world) setWorld(opts.world);
      if (opts.notice) setNotice({ text: opts.notice, tone: "ok", undo: opts.undo ? prev : null });
    },
    [world],
  );
  const edit = (r: EditResult) => {
    if (r.ok) replace(r.flow, { keepView: true });
    else setNotice({ text: r.error, tone: "error", undo: null });
  };

  // a notice with Undo folds away by itself
  useEffect(() => {
    if (!notice || notice.tone === "error") return;
    const t = setTimeout(() => setNotice(null), NOTICE_MS);
    return () => clearTimeout(t);
  }, [notice]);

  useEffect(() => {
    writeChoice(store, KEYS.world, world);
  }, [world, store]);

  // remember this browser's flow (a convenience: a reload does not lose the work)
  useEffect(() => {
    const t = setTimeout(() => writeChoice(store, KEYS.flow, exportText(flow)), SAVE_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [flow, store]);

  // close the Load menu on a click outside it
  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenu(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menu]);

  // --- the engine: catalogue, lint, Python ----------------------------------------------------------
  useEffect(() => {
    api
      .catalogue(flow.target.client)
      .then((c) => {
        setCatalogue(c);
        setEngineErr(null);
      })
      .catch((e) => setEngineErr(e instanceof ApiError ? e.reason : String(e)));
  }, [api, flow.target.client]);

  const runLint = useCallback(
    async (f: Flow, w: WorldSource) => {
      try {
        const doc = await api.lint(f, w);
        setLint({ doc, for: canonical(f) });
      } catch (e) {
        if (e instanceof ApiError && e.reason === "invalid_flow") setNotice({ text: `MW1 refuses this flow: ${e.errors.join(" · ")}`, tone: "error", undo: null });
        else if (!(e instanceof ApiError && e.reason === "rate_limited")) setNotice({ text: `Lint failed: ${e instanceof ApiError ? e.message : String(e)}`, tone: "error", undo: null });
      }
    },
    [api],
  );
  // lint a moment after the last change (the backend allows 20 lints and simulations a minute)
  useEffect(() => {
    const t = setTimeout(() => void runLint(flow, world), LINT_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [flow, world, runLint]);

  // the Python beside the blocks: the backend's canonical view, after every change; one request in
  // flight, the latest flow wins; a "rate_limited" waits and tries again with the latest
  const py = useRef<{ busy: boolean; want: Flow | null; until: number; timer: ReturnType<typeof setTimeout> | null }>({ busy: false, want: null, until: 0, timer: null });
  const pyPump = useRef<(() => void) | null>(null);
  useEffect(() => {
    const s = py.current;
    const pump = async (): Promise<void> => {
      if (s.busy || !s.want) return;
      const wait = s.until - Date.now();
      if (wait > 0) {
        s.timer ??= setTimeout(() => {
          s.timer = null;
          void pump();
        }, wait);
        return;
      }
      const f = s.want;
      s.want = null;
      s.busy = true;
      try {
        const r = await api.python(f);
        setPython({ text: r.python, for: canonical(f) });
        setPythonErr(null);
      } catch (e) {
        if (e instanceof ApiError && e.reason === "rate_limited") {
          s.until = Date.now() + PYTHON_RETRY_MS;
          s.want ??= f;
          setPythonErr("waiting a moment: the backend's request limit (it retries by itself)");
        } else setPythonErr(e instanceof ApiError ? e.message : "the Python view is unavailable");
      } finally {
        s.busy = false;
        if (s.want) void pump();
      }
    };
    pyPump.current = () => void pump();
  }, [api]);
  useEffect(() => {
    const t = setTimeout(() => {
      py.current.want = flowRef.current;
      pyPump.current?.();
    }, PYTHON_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [key]);

  // --- load, save, start over, simulate ----------------------------------------------------------
  const loadSample = async () => {
    setMenu(false);
    try {
      const s = await api.sample();
      replace(s.flow, {
        world: s.world,
        undo: true,
        notice: "Opened Batt's sample (town → NPC warp → farm loop; a death respawns in town). Synthetic maps and keys, simulated on the sample sheets.",
      });
      setSimForm(DEFAULT_SIM);
    } catch (e) {
      setNotice({ text: `No sample: ${e instanceof ApiError ? e.reason : String(e)}`, tone: "error", undo: null });
    }
  };
  const importFile = async (file: File) => {
    if (file.size > MAX_JSON_BYTES) return setNotice({ text: `${file.name}: larger than ${MAX_JSON_BYTES} bytes`, tone: "error", undo: null });
    const r = importFlow(await file.text());
    if (!r.ok) return setNotice({ text: `${file.name}: ${r.errors.join(" · ")}`, tone: "error", undo: null });
    replace(r.flow, { undo: true, notice: `Opened ${file.name}; the backend checks it with MW1's schema at the next lint.` });
  };
  const exportFile = () => {
    const url = URL.createObjectURL(new Blob([exportText(flowRef.current)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${flowRef.current.name}.flow.json`;
    a.click();
    URL.revokeObjectURL(url);
  };
  const startOver = () => {
    if (!window.confirm("Start a new program from the starter blocks? The flow here is replaced. (Undo, right after, brings it back.)")) return;
    replace(starterFlow(), { world: STARTER_WORLD, undo: true, notice: "Started a new program from the starter: two maps, on the sample sheets." });
  };
  const newWorkflow = () => {
    setMenu(false);
    replace(emptyFlow("new_flow", catalogue?.runtime_limits?.default_s), { undo: true, notice: "Started a new workflow: one map block, “start”. Add map blocks on the Map tab." });
  };
  const simulate = async (form: SimForm) => {
    setSimBusy(true);
    setPane("simulate", true);
    const f = flowRef.current;
    try {
      const doc = await api.simulate(f, world, scenarioOf(form));
      setSim({ doc, for: canonical(f) });
      setLint({ doc: doc.lint, for: canonical(f) });
    } catch (e) {
      setNotice({ text: `Simulate failed: ${e instanceof ApiError ? e.message : String(e)}`, tone: "error", undo: null });
    } finally {
      setSimBusy(false);
    }
  };
  const copy = () => {
    const text = codeFile === "py" ? (python?.text ?? "") : exportText(flowRef.current);
    void (navigator.clipboard?.writeText(text) ?? Promise.reject(new Error("no clipboard"))).then(
      () => setCopied("ok"),
      () => {
        setCopied("failed");
        // select it, so Ctrl+C / ⌘C copies it (the clipboard API needs a secure page)
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

  // --- problems and showing a block ---------------------------------------------------------------
  const lintDoc = lint?.doc ?? null;
  const lintStale = lint !== null && lint.for !== key;
  const simDoc = sim?.doc ?? null;
  const simStale = sim !== null && sim.for !== key;
  const errors = lintStale ? [] : lintErrors(lintDoc);
  const plain = !flow.workflow;
  /** Open a tab, unless this tab's blocks cannot become the flow yet: switching would drop them. */
  const goTab = (k: string): boolean => {
    if (k !== active.key && active.scope && editor.issues.length > 0) {
      setNotice({
        text: "Fix the problems under the blocks first (or press Undo): this tab's blocks cannot become the flow yet, and leaving the tab would lose them.",
        tone: "warn",
        undo: null,
      });
      return false;
    }
    setTab(k);
    return true;
  };
  const showFinding = (f: Finding) => {
    const t = tabOf(f, plain);
    if (t === "map") {
      if (!goTab("map")) return;
      setSelected(f.owner === "flow" ? null : f.owner);
      setPane("inspect", true);
      return;
    }
    if (t === active.key && editorApi) {
      editorApi.showPath(f.path);
      return;
    }
    if (!goTab(t)) return;
    pendingShow.current = { tab: t, path: f.path }; // shown once that tab's blocks are loaded
  };
  useEffect(() => {
    const want = pendingShow.current;
    if (!want || !editorApi || want.tab !== active.key) return;
    editorApi.showPath(want.path);
    pendingShow.current = null;
  }, [editorApi, active.key]);
  const openNode = (id: string) => {
    const t = tabFor(id);
    if (t && tabs.some((x) => x.key === t)) goTab(t);
  };
  const addMapBlock = () => {
    const before = new Set(flowRef.current.workflow?.blocks.map((b) => b.name) ?? []);
    const r = addBlock(flowRef.current);
    if (!r.ok) return setNotice({ text: r.error, tone: "error", undo: null });
    replace(r.flow, { keepView: true });
    const added = r.flow.workflow?.blocks.find((b) => !before.has(b.name));
    if (added) setTab(`block:${added.name}`);
  };

  const onEditorState = useCallback((s: EditorState) => setEditor(s), []);
  const onEditorApi = useCallback((a: EditorApi | null) => setEditorApi(() => a), []);
  const getFlow = useCallback(() => flowRef.current, []);
  const blockTab = active.scope !== null;
  const editorReady = editor.ready || !blockTab;
  const issues = blockTab ? editor.issues : [];
  const loose = blockTab ? editor.loose : [];
  const status = statusText({
    loading: blockTab && !editor.ready && !editor.failed,
    engine: engineErr,
    issues: issues.length,
    lintErrors: errors.length,
    simulating: simBusy,
    mapTab: !blockTab,
  });
  const total = lintDoc ? lintLine(lintDoc.counts) : null;
  const pythonOpen = view === "blocks" && pythonPanel === "open";
  const huntRules = catalogue?.hunt_rules ?? null;
  const openPanes = PANES.filter(([p]) => panes[p] && (p !== "hunt" || huntRules));
  const pyText = python?.text ?? "";
  const pyStale = python !== null && python.for !== key;
  const codeText = codeFile === "py" ? pyText : exportText(flow);
  const zonesBlock = zonesFor ? flow.workflow?.blocks.find((x) => x.name === zonesFor) : undefined;

  const paneToggles = (cls: string, after?: () => void) =>
    PANES.filter(([p]) => p !== "hunt" || huntRules).map(([p, label]) => (
      <button
        key={p}
        type="button"
        className={`toggle-button ${cls}`}
        aria-pressed={panes[p]}
        onClick={() => {
          setPane(p, !panes[p]);
          after?.();
        }}
        data-testid={cls ? `toggle-${p}` : `more-${p}`}
      >
        {label}
        {p === "lint" && !panes.lint && errors.length > 0 && (
          <span className="badge-dot badge-dot-error">
            <span className="visually-hidden"> errors</span>
          </span>
        )}
        {p === "simulate" && !panes.simulate && simDoc && !simStale && (
          <span className="badge-dot">
            <span className="visually-hidden"> a new run</span>
          </span>
        )}
      </button>
    ));

  const codePane = (full: boolean) => (
    <>
      <div className="studio-panel-header">
        <h2 id={full ? "python-full-heading" : "python-side-heading"}>{full ? "Python made from your blocks" : "Python"}</h2>
        <div className="button-row">
          <button type="button" className="button button-small" onClick={copy} disabled={codeText === ""} title={codeFile === "py" ? "Copy the Python" : "Copy the flow's JSON"}>
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
        {(["py", "json"] as const).map((k) => (
          <button key={k} type="button" role="tab" className="python-file" aria-selected={codeFile === k} onClick={() => setCodeFile(k)} data-testid={`python-file-${k}`}>
            {k === "py" ? `${flow.name}.py` : `${flow.name}.flow.json`}
          </button>
        ))}
      </div>
      {codeFile === "py" && (pythonErr || pyStale || issues.length > 0) && (
        <p className="studio-panel-note">
          {issues.length > 0
            ? "Not up to date: fix the problems under the blocks first."
            : pythonErr
              ? `Not up to date: ${pythonErr}`
              : "Updating…"}
        </p>
      )}
      {codeFile === "json" && <p className="studio-panel-note">The flow IR, MW1&apos;s canonical JSON: the one source of truth (Save downloads it, Load opens one).</p>}
      {codeFile === "py" && !pyText && !pythonErr ? (
        <p className="studio-panel-note">The Python view is made by the flow engine…</p>
      ) : (
        <CodeView ref={codeRef} code={codeText} colour={codeFile === "py"} label={codeFile === "py" ? `Python: ${flow.name}.py` : `JSON: ${flow.name}.flow.json`} testId={codeFile === "py" ? "python-code" : "json-code"} />
      )}
    </>
  );

  return (
    <main className="studio" data-view={view} data-testid="flows-app">
      <header className="studio-bar">
        <div className="studio-brand">
          <span className="studio-home">Flows</span>
          <span className="status-pill" title="Nothing on this page runs in the game">SIMULATE only</span>
          <h1 className="studio-title" title={flow.name}>
            {flow.name}
          </h1>
        </div>

        <div className="segmented" role="group" aria-label="View">
          {VIEWS.map((v) => (
            <button key={v} type="button" className="segmented-option" aria-pressed={view === v} onClick={() => setView(v)} data-testid={`view-${v}`}>
              {v === "blocks" ? "Blocks" : "Python"}
            </button>
          ))}
        </div>

        <div className="studio-actions">
          <div className="studio-menu" ref={menuRef}>
            <button type="button" className="button button-small button-file" onClick={() => setMenu(!menu)} aria-expanded={menu} title="Open a flow" data-testid="load">
              <FolderIcon />
              <span className="button-text">Load</span>
            </button>
            {menu && (
              <div className="studio-menu-list" role="menu">
                <button type="button" role="menuitem" className="studio-menu-item" onClick={() => (setMenu(false), fileRef.current?.click())}>
                  Open a flow file (.json)…<small>a flow saved here, or any IR JSON (checked before it opens)</small>
                </button>
                <button type="button" role="menuitem" className="studio-menu-item" onClick={() => void loadSample()} data-testid="load-sample">
                  Batt&apos;s sample<small>town → NPC warp → farm loop, on synthetic map sheets</small>
                </button>
                <button type="button" role="menuitem" className="studio-menu-item" onClick={newWorkflow}>
                  A new workflow<small>map blocks joined by exits, on the Map tab</small>
                </button>
                <button type="button" role="menuitem" className="studio-menu-item" onClick={() => (setMenu(false), replace(starterFlow(), { world: STARTER_WORLD, undo: true, notice: "Opened the starter: two maps." }))}>
                  Starter: two maps<small>town → NPC warp → field, a wing back (the first screen)</small>
                </button>
                <button type="button" role="menuitem" className="studio-menu-item" onClick={() => (setMenu(false), replace(oneMapStarter(), { undo: true, notice: "Opened the starter: one map." }))}>
                  Starter: one map<small>one tab, main: wait, wait until the detector sees a monster, stop</small>
                </button>
              </div>
            )}
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".json,application/json"
            className="visually-hidden"
            tabIndex={-1}
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) void importFile(f);
            }}
          />
          <button type="button" className="button button-small button-file" onClick={exportFile} title="Save the flow as a .json file" data-testid="save">
            <SaveIcon />
            <span className="button-text">Save</span>
          </button>
          <button type="button" className="button button-small button-file" onClick={startOver} title="Start a new program from the starter blocks" data-testid="start-over">
            <NewIcon />
            <span className="button-text">Start over</span>
          </button>
          <button
            type="button"
            className="button button-primary button-run"
            onClick={() => void simulate(simForm)}
            disabled={simBusy || issues.length > 0}
            title="Run the flow in the simulator: no game, no input"
            data-testid="simulate"
          >
            <PlayIcon />
            <span className="button-text">{simBusy ? "Simulating…" : "Simulate"}</span>
          </button>
        </div>
      </header>

      {notice && (
        <div className="studio-notices">
          <p className={`notice notice-${notice.tone} notice-actions`} role={notice.tone === "error" ? "alert" : "status"} data-testid="notice">
            <span>{notice.text}</span>
            {notice.undo && (
              <button
                type="button"
                className="button button-small"
                onClick={() => {
                  const u = notice.undo;
                  setNotice(null);
                  if (u) replace(u.flow, { world: u.world });
                }}
                data-testid="notice-undo"
              >
                Undo
              </button>
            )}
            <button type="button" className="icon-button" onClick={() => setNotice(null)} title="Hide">
              <CloseIcon />
              <span className="visually-hidden">Hide</span>
            </button>
          </p>
        </div>
      )}
      {(copied === "failed" || canvasNotes.length > 0) && (
        <div className="studio-notices">
          {copied === "failed" && (
            <p className="notice notice-warn" role="status">
              This browser would not copy automatically (the page is not a secure origin). The code is selected: press Ctrl+C (⌘C) to copy it.
            </p>
          )}
          {!blockTab &&
            canvasNotes.map((n) => (
              <p key={n} className="notice notice-warn" role="status">
                {n}
              </p>
            ))}
        </div>
      )}

      <div className="device-bar" aria-label="The flow">
        <div className="device-chip">
          <span className="device-label">flow</span>
          <span className="device-value">{plain ? "plain (one main)" : `${flow.workflow?.blocks.length} map block${flow.workflow?.blocks.length === 1 ? "" : "s"}`}</span>
        </div>
        <label className="device-chip">
          <span className="device-label">static data</span>
          <select value={world} onChange={(e) => setWorld(e.target.value as WorldSource)} data-testid="world">
            <option value="local">lab data/kb</option>
            <option value="sample">sample sheets</option>
          </select>
        </label>
        <div className="device-chip" data-level={!total ? undefined : lintStale ? undefined : total.level}>
          <span className="device-label">lint</span>
          <span className="device-value">{total ? `${total.text}${lintStale ? " (checking…)" : ""}` : "…"}</span>
        </div>
        <div className="device-chip device-chip-wide">
          <span className="device-label">hash</span>
          <code>{lintDoc && !lintStale ? lintDoc.flow_hash.slice(0, 12) : "…"}</code>
        </div>
      </div>

      <div className="studio-body" data-python-panel={pythonOpen ? "open" : "closed"}>
        <div className="studio-canvas">
          <div className="block-tabs-bar">
            <div className="block-tabs" role="tablist" aria-label="Tabs">
              {tabs.map((t) => (
                <div key={t.key} className="block-tab" data-active={t.key === active.key}>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={t.key === active.key}
                    className="block-tab-name"
                    onClick={() => goTab(t.key)}
                    title={t.scope === null ? "The workflow: map blocks joined by exits" : t.scope.kind === "global" ? "The global events (every map)" : undefined}
                    data-testid={`tab-${t.key}`}
                  >
                    {t.label}
                    {((t.key === active.key && issues.length > 0) || errors.some((f) => tabOf(f, plain) === t.key)) && <span className="block-tab-problem" aria-label="has problems" />}
                  </button>
                </div>
              ))}
              {!plain && (
                <button type="button" className="block-tab-add" onClick={addMapBlock} title="Add a map block (a new tab)">
                  + map block
                </button>
              )}
            </div>
          </div>
          <div className="blocks-area">
            {active.scope ? (
              <BlockEditor
                scope={active.scope}
                scopeKey={active.key}
                epoch={epoch}
                getFlow={getFlow}
                catalogue={catalogue}
                lint={lintStale ? null : lintDoc}
                trace={simDoc && !simStale ? simDoc.trace : null}
                hidden={view === "python"}
                onFlow={fromBlocks}
                onState={onEditorState}
                onApi={onEditorApi}
              />
            ) : (
              <div className="blocks-workspace" inert={view === "python"}>
                <FlowCanvas
                  flow={flow}
                  positions={positions}
                  lint={lintDoc}
                  lintStale={lintStale}
                  trace={simDoc && !simStale ? simDoc.trace : null}
                  catalogue={catalogue}
                  selected={selected}
                  onSelect={(id) => {
                    setSelected(id);
                    if (id) setPane("inspect", true);
                  }}
                  onOpen={openNode}
                  onMove={(p) => setPositions((old) => ({ ...old, ...p }))}
                  onConnectExit={(from: string, kind: AuthoredExit, to: string) => edit(connectExit(flowRef.current, from, kind, to))}
                  onDeleteExit={(path: string) => edit(removeExit(flowRef.current, path))}
                  onNotes={setCanvasNotes}
                />
              </div>
            )}
            {view === "blocks" && blockTab && editor.ready && (
              <div className="history-buttons" role="group" aria-label="Undo and redo">
                <button type="button" className="history-button" onClick={() => editorApi?.undo(false)} disabled={!editor.canUndo} title="Undo (Ctrl+Z)" data-testid="undo">
                  <UndoIcon />
                  <span className="visually-hidden">Undo</span>
                </button>
                <button type="button" className="history-button" onClick={() => editorApi?.undo(true)} disabled={!editor.canRedo} title="Redo (Ctrl+Shift+Z)" data-testid="redo">
                  <UndoIcon redo />
                  <span className="visually-hidden">Redo</span>
                </button>
              </div>
            )}
          </div>
          {view === "python" && (
            <section className="studio-python-full" aria-labelledby="python-full-heading">
              {codePane(true)}
            </section>
          )}
        </div>
        {pythonOpen && (
          <aside className="studio-side" aria-labelledby="python-side-heading" data-testid="python-side">
            {codePane(false)}
          </aside>
        )}
      </div>

      {openPanes.length > 0 && (
        <div className="studio-drawer" data-panes={openPanes.length}>
          {openPanes.map(([p, label]) => (
            <section key={p} className="pane" aria-labelledby={`pane-${p}`}>
              <div className="studio-panel-header">
                <h2 id={`pane-${p}`}>{label}</h2>
                <button type="button" className="icon-button" onClick={() => setPane(p, false)} title={`Close ${label}`}>
                  <CloseIcon />
                  <span className="visually-hidden">Close {label}</span>
                </button>
              </div>
              <div className="pane-body">
                {p === "inspect" && (
                  <InspectPanel
                    flow={flow}
                    selected={inspectOf(active.key, selected)}
                    lint={lintDoc}
                    sim={simDoc && !simStale ? simDoc : null}
                    api={api}
                    world={world}
                    onUpdate={(name: string, props: BlockProps) => {
                      edit(updateBlock(flowRef.current, name, props));
                      if (props.name !== name) {
                        if (active.key === `block:${name}`) setTab(`block:${props.name}`);
                        if (selected === `block:${name}`) setSelected(`block:${props.name}`);
                      }
                    }}
                    onDelete={(name) => {
                      edit(removeBlock(flowRef.current, name));
                      setSelected(null);
                    }}
                    onStart={(name, entry) => edit(setStart(flowRef.current, name, entry))}
                    onOpen={openNode}
                    onSimulateHere={(b) => {
                      const f = { ...simForm, startBlock: b, single: true };
                      setSimForm(f);
                      void simulate(f);
                    }}
                    limits={catalogue?.runtime_limits ?? null}
                    onFlow={(f) => replace(f, { keepView: true })}
                    onZones={setZonesFor}
                  />
                )}
                {p === "lint" && <LintPanel lint={lintDoc} stale={lintStale} onSelect={showFinding} />}
                {p === "simulate" && (
                  <SimulatePanel
                    flow={flow}
                    form={simForm}
                    setForm={setSimForm}
                    sim={simDoc}
                    stale={simStale}
                    busy={simBusy}
                    world={world}
                    models={catalogue?.models ?? null}
                    onRun={() => void simulate(simForm)}
                  />
                )}
                {p === "paths" && <PathPanel flow={flow} sim={simDoc} stale={simStale} world={world} api={api} />}
                {p === "hunt" && huntRules && <HuntRulesPanel rules={huntRules} l1={catalogue?.blocks.hunt?.badge ?? "unknown"} />}
              </div>
            </section>
          ))}
        </div>
      )}

      {(issues.length > 0 || errors.length > 0 || loose.length > 0) && (
        <div className="studio-problems" data-testid="problems">
          {issues.length > 0 && (
            <div className="notice notice-warn" data-testid="block-problems">
              <strong>{PROBLEM_HEADS.fix}</strong>
              <ul>
                {issues.map((it, i) => (
                  <li key={`${it.id ?? "tab"}-${i}`}>
                    {it.id ? (
                      <button type="button" className="problem-link" onClick={() => it.id && editorApi?.showBlock(it.id)} title="Show the block">
                        {it.where}: {it.text}
                      </button>
                    ) : (
                      `${it.where}: ${it.text}`
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {errors.length > 0 && (
            <div className="notice notice-error" data-testid="lint-problems">
              <strong>{PROBLEM_HEADS.lint}</strong>
              <ul>
                {errors.slice(0, 30).map((f, i) => (
                  <li key={`${f.rule}-${f.path}-${i}`}>
                    <button type="button" className="problem-link" onClick={() => showFinding(f)} title="Show the block">
                      {f.message}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {loose.length > 0 && active.scope && (
            <div className="notice" data-testid="loose-blocks">
              <strong>{PROBLEM_HEADS.loose}</strong>
              <ul>
                {loose.map((l, i) => (
                  <li key={l.id ?? i}>
                    <button type="button" className="problem-link" onClick={() => l.id && editorApi?.showBlock(l.id)} title="Show the block">
                      {looseText(l, active.scope!)}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <footer className="studio-status">
        <p className="studio-status-text" data-testid="program-status" aria-live="polite">
          {editorReady || !blockTab ? status : "Loading the block editor…"}
        </p>
        <div className="studio-toggles" role="group" aria-label="Panels">
          {view === "blocks" && (
            <button type="button" className="toggle-button" aria-pressed={pythonOpen} onClick={togglePython} data-testid="toggle-python">
              Python
            </button>
          )}
          {paneToggles("pane-toggle")}
          {/* phones (< 48rem): Python stays; the panes fold into one "More" menu */}
          <div className="toggles-more-wrap">
            <button type="button" className="toggle-button toggles-more" aria-expanded={more} onClick={() => setMore(!more)} data-testid="toggle-more">
              More ▾
              {!more && errors.length > 0 && (
                <span className="badge-dot badge-dot-error">
                  <span className="visually-hidden"> lint errors</span>
                </span>
              )}
            </button>
            {more && <div className="toggles-menu">{paneToggles("", () => setMore(false))}</div>}
          </div>
        </div>
      </footer>

      {zonesBlock && (
        // the Zones layer is its own full-window tool (dark, as before): its text colours restored
        <div className="text-neutral-100">
          <ZonesEditor
            api={api}
            world={world}
            server={flow.target.server}
            map={zonesBlock.map.map}
            block={zonesBlock.name}
            zonesRef={zonesBlock.zones ?? null}
            onReference={(ref) => edit(setZonesRef(flowRef.current, zonesBlock.name, ref))}
            onClose={() => setZonesFor(null)}
          />
        </div>
      )}
    </main>
  );
}

// --- icons (MatPilot's, BlocksApp.tsx) ---------------------------------------------------------
function CloseIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function FolderIcon() {
  return (
    <svg className="button-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path d="M1.75 4.25v8a1 1 0 0 0 1 1h10.5a1 1 0 0 0 1-1v-6a1 1 0 0 0-1-1H8L6.5 3.25H2.75a1 1 0 0 0-1 1z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

function SaveIcon() {
  return (
    <svg className="button-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path d="M8 2v7.5M4.75 6.5 8 9.75l3.25-3.25M2.5 10.5v2a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-2" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function NewIcon() {
  return (
    <svg className="button-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path d="M9.5 1.75H4a1 1 0 0 0-1 1v10.5a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V5.25zM9.5 1.75v3.5H13M8 7.5v4M6 9.5h4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
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

function UndoIcon({ redo = false }: { redo?: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false" style={redo ? { transform: "scaleX(-1)" } : undefined}>
      <path d="M9 14 4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 0 11H11" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
