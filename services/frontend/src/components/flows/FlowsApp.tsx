"use client";

// The /flows STUDIO (Batt 2026-11-09, docs/planning/flows-studio.md): matpilot.org/blocks's layout,
// so learners who know it are at home and can go on to real robots: a header (Blocks | Python, Load,
// Save, Start over, the green Simulate), notices, a context bar, the canvas (tabs, then the blocks or
// the workflow map) with the PYTHON BESIDE IT, a drawer of output panes, the problems under the
// blocks, and a status footer with the panel toggles. Everything of MW2's page is kept: the map-block
// workflow canvas (the "Map" tab), inspect, lint, SIMULATE, JSON import / export, the path map and
// the zones layer. Save and Load (2026-11-12, docs/planning/flows-save-load.md): on this computer and
// on GitHub, the dialogs shared with /maps (components/flowfile/).
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
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { EditorApi, EditorState } from "@/components/flows/BlockEditor";
import FlowFileDialogs, { type FileDialog, type Opened, useFileShortcuts } from "@/components/flowfile/FlowFileDialogs";
import CodeView from "@/components/flows/CodeView";
import ConfigPanel, { useConfig } from "@/components/flows/ConfigPanel";
import LiveRun, { LiveRunButtons, useLiveRun } from "@/components/flows/LiveRun";
import MapBinding from "@/components/flows/MapBinding";
import { DEFAULT_SIM, HuntRulesPanel, InspectPanel, LintPanel, PathPanel, scenarioOf, type SimForm, SimulatePanel } from "@/components/flows/Panels";
import { ApiError, type CatalogueDoc, type Finding, FlowsApi, type LintDoc, type SimDoc, type WorldSource } from "@/lib/flow/api";
import type { Scope } from "@/lib/flow/blocks";
import { addBlock, type BlockProps, type EditResult, removeBlock, setStart, setZonesRef, updateBlock } from "@/lib/flow/canvas";
import { configClash, effectiveConfig, startChecklist } from "@/lib/flow/config";
import { type FileMeta, newFileMeta, readFileMeta, writeFileMeta } from "@/lib/flow/file";
import { runnerKeys, runnerMapBlock } from "@/lib/flow/functions";
import { exportText, importFlow } from "@/lib/flow/importer";
import { canonical, emptyFlow, type Flow } from "@/lib/flow/ir";
import { browserStorage, KEYS, pythonDefault, readChoice, readShelf, readText, shelve, writeChoice, writeShelf } from "@/lib/flow/prefs";
import { ACTIVE } from "@/lib/flow/liverun";
import { LIVE_FLOWS, RUNNERS, runnerForMap } from "@/lib/flow/runners";
import { oneMapStarter, STARTER_NAME, STARTER_WORLD, starterFlow, XMAS_NAME, XMAS_WORLD, xmasFlow } from "@/lib/flow/starter";
import { lintLine } from "@/lib/flow/status";
import { lintErrors, looseText, PROBLEM_HEADS, statusText, tabOf } from "@/lib/flow/words";
import { refreshRule } from "@/lib/maps/rules";
import { backendHttpBase } from "@/lib/ws";

import FlowSwitcher, { type FlowItem } from "./FlowSwitcher";

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
type Pane = "inspect" | "lint" | "simulate" | "paths" | "hunt" | "run";
const PANES: [Pane, string][] = [
  ["run", "Run"], // a flow whose map holds the runner's block (2026-11-13)
  ["inspect", "Inspect"],
  ["lint", "Lint"],
  ["simulate", "Results"], // what it shows: "Simulate" always means RUN it (the green button)
  ["paths", "Path map"],
  ["hunt", "Hunt rules"],
];
type Tab = { key: string; label: string; scope: Scope };
type Notice = { text: string; tone: "ok" | "warn" | "error"; undo: { flow: Flow; world: WorldSource; file: FileMeta } | null };
const NO_EDITOR: EditorState = { ready: false, failed: false, issues: [], loose: [], canUndo: false, canRedo: false };

/** The tabs (Batt 2026-11-13: "take the Map tab off /flows, the Maps page is the map graph; each map
 * has its own flow, and a global flow every map shares, like a public class; functions in a tab of
 * their own"): one tab per map block (the START map first), then "every map" (the global events) and
 * "functions" (every function of the flow: any map's blocks call them). A plain flow: main first. */
function tabsOf(flow: Flow): Tab[] {
  const events: Tab = { key: "events", label: "every map", scope: { kind: "global" } };
  const functions: Tab = { key: "functions", label: "functions", scope: { kind: "functions" } };
  if (!flow.workflow) return [{ key: "main", label: "main", scope: { kind: "main" } }, events, functions];
  const wf = flow.workflow;
  const blocks = [...wf.blocks.filter((b) => b.name === wf.start_block), ...wf.blocks.filter((b) => b.name !== wf.start_block)];
  return [...blocks.map((b) => ({ key: `block:${b.name}`, label: b.name, scope: { kind: "block" as const, name: b.name } })), events, functions];
}

/** The READY-MADE flows the FLOWS row offers by name (2026-11-13), with the static data each is
 * linted and simulated on. */
const READY: Record<string, () => { flow: Flow; world: WorldSource }> = {
  [STARTER_NAME]: () => ({ flow: starterFlow(), world: STARTER_WORLD }),
  [XMAS_NAME]: () => ({ flow: xmasFlow(), world: XMAS_WORLD }),
};

/** The node a tab is about (the Inspect pane shows it). */
function inspectOf(tab: string): string | null {
  if (tab === "events") return "events:global";
  if (tab.startsWith("block:")) return tab;
  return null;
}

/** The flow to start with: this browser's last one (checked like an imported file), else the starter. */
function initialFlow(): { flow: Flow; restored: boolean; broken: boolean } {
  const text = readText(browserStorage(), KEYS.flow);
  if (!text) return { flow: starterFlow(), restored: false, broken: false };
  const r = importFlow(text);
  return r.ok ? { flow: r.flow, restored: true, broken: false } : { flow: starterFlow(), restored: false, broken: true };
}

export default function FlowsApp({
  backendUrl,
  initialBlock = null,
  onRunner,
}: {
  backendUrl: string | null;
  initialBlock?: string | null;
  /** Open a runner flow (FlowsClient): the generated description of a live runner. */
  onRunner?: (id: string) => void;
}) {
  // Client-only (FlowsClient loads this with ssr: false): backendHttpBase reads window.location.
  const [api] = useState<FlowsApi>(() => new FlowsApi(backendHttpBase(backendUrl)));
  const [start] = useState(initialFlow);
  const [flow, setFlowState] = useState<Flow>(start.flow);
  const flowRef = useRef<Flow>(start.flow);
  const [epoch, setEpoch] = useState(0); // the flow was replaced from outside the blocks: reload them
  // the name it was saved as and the GitHub file it came from (shared with /maps through storage)
  const [file, setFileState] = useState<FileMeta>(() => (start.restored ? readFileMeta(browserStorage(), start.flow) : newFileMeta(start.flow)));
  const fileRef = useRef<FileMeta>(file);
  const [dialog, setDialog] = useState<FileDialog>(null);
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
  const [zonesFor, setZonesFor] = useState<string | null>(null);
  // `?block=<name>` (the Maps page's "Open flow", 2026-11-10): that map block's tab, if it is one
  const [tab, setTab] = useState<string>(() => {
    const all = tabsOf(start.flow);
    const want = initialBlock ? `block:${initialBlock}` : null;
    return want && all.some((t) => t.key === want) ? want : all[0].key;
  });
  const [editor, setEditor] = useState<EditorState>(NO_EDITOR);
  const [editorApi, setEditorApi] = useState<EditorApi | null>(null);
  const pendingShow = useRef<{ tab: string; path: string } | null>(null);
  const [notice, setNotice] = useState<Notice | null>(
    start.broken ? { text: "Your saved flow could not be opened, so the starter program is shown instead.", tone: "warn", undo: null } : null,
  );
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
  const codeRef = useRef<HTMLPreElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const key = useMemo(() => canonical(flow), [flow]);
  const tabs = useMemo(() => tabsOf(flow), [flow]);
  const active = tabs.find((t) => t.key === tab) ?? tabs[0];
  // RUN (Batt 2026-11-13: "the xmas_dun02 flow is a map tab like my_first_flow; every key a
  // function"): the flow's map block that holds the runner's block, on a map the Run helper plays.
  // Its keys come from the flow's functions (lib/flow/functions.ts), its other settings from the
  // bot server's file (every map's, and the map's own), as before.
  const runBlock = runnerMapBlock(flow);
  const runDoc = runBlock ? runnerForMap(runBlock.map.map) : null;
  const runnable = !!runDoc && LIVE_FLOWS.includes(runDoc.id);
  const live = useLiveRun(backendUrl, runDoc?.id ?? "", runnable);
  const cs = useConfig(backendUrl, runDoc?.map ?? "");
  const cdoc = runDoc?.config ?? null;
  const keysR = runBlock ? runnerKeys(flow, runBlock) : null;
  const runEff = cdoc && runDoc ? effectiveConfig(cdoc, cs.file, runDoc.map) : null;
  const runValues = runEff ? (keysR?.ok ? { ...runEff.values, ...keysR.keys } : runEff.values) : null;
  const runWhy = !runnable
    ? null
    : keysR && !keysR.ok
      ? `the keys: ${keysR.problems.join("; ")}`
      : cs.file?.broken
        ? `the settings file cannot be used: ${cs.file.broken}`
        : cdoc && runValues
          ? configClash(cdoc, runValues)
          : null;
  const keysLine = keysR?.ok
    ? (["heal_key", "fly_key", "home_key", "knife_key", "dagger_key"] as const).map((k) => `${keysR.keys[k]} ${keysR.from[k]}()`).join(" · ") + " (the functions tab)"
    : (keysR?.problems.join("; ") ?? "");

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
  // a run that is starting or playing shows the Run pane (its live line and the end): derived
  const runActive = runnable && ACTIVE.includes(live.st?.state ?? "");
  const shown: Record<Pane, boolean> = { ...panes, run: panes.run || runActive };

  // --- the flow: from the blocks (no reload), or replaced from outside (the blocks reload) --------
  const fromBlocks = useCallback((f: Flow) => {
    flowRef.current = f;
    setFlowState(f);
  }, []);
  const setFile = useCallback((m: FileMeta) => {
    fileRef.current = m;
    setFileState(m);
  }, []);
  const replace = useCallback(
    (f: Flow, opts: { notice?: string; undo?: boolean; world?: WorldSource; keepView?: boolean; file?: FileMeta } = {}) => {
      const prev = { flow: flowRef.current, world, file: fileRef.current };
      flowRef.current = f;
      setFlowState(f);
      setEpoch((e) => e + 1);
      // an edit keeps the file it came from; any other new flow starts unsaved (Undo puts it back)
      setFile(opts.file ?? (opts.keepView ? fileRef.current : newFileMeta(f)));
      if (!opts.keepView) {
        setSim(null);
        setTab(tabsOf(f)[0].key);
      }
      if (opts.world) setWorld(opts.world);
      if (opts.notice) setNotice({ text: opts.notice, tone: "ok", undo: opts.undo ? prev : null });
    },
    [world, setFile],
  );
  const edit = (r: EditResult) => {
    // the Maps page's unknown-map rule (if on) follows the map blocks: added, renamed, removed here
    if (r.ok) replace(refreshRule(r.flow), { keepView: true });
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

  // remember this browser's flow (a convenience: a reload does not lose the work) and its file meta;
  // the Maps page reads the same, so it is also written at once on the way there and when the page goes
  const flush = useCallback(() => {
    writeChoice(store, KEYS.flow, exportText(flowRef.current));
    writeFileMeta(store, fileRef.current, flowRef.current);
  }, [store]);
  useEffect(() => {
    const t = setTimeout(flush, SAVE_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [flow, file, flush]);
  useEffect(() => () => void flush(), [flush]);

  // THE FLOWS ROW (2026-11-13): switch to another flow by name; the one open now is KEPT on this
  // browser's shelf (a ready-made one opens fresh the first time)
  const [shelfNames, setShelfNames] = useState<string[]>(() => Object.keys(readShelf(store)));
  const switchTo = (name: string, wantTab?: string) => {
    flush();
    const here = flowRef.current;
    shelve(store, here.name, exportText(here), world);
    const shelf = readShelf(store);
    let next: { flow: Flow; world: WorldSource } | null = null;
    const kept = shelf[name];
    if (kept && name !== here.name) {
      const r = importFlow(kept.text);
      if (r.ok) next = { flow: r.flow, world: WORLDS.includes(kept.world as WorldSource) ? (kept.world as WorldSource) : "local" };
    }
    if (!next && READY[name]) next = READY[name]();
    if (!next) return setNotice({ text: `The flow ${name} could not be opened.`, tone: "error", undo: null });
    delete shelf[name];
    writeShelf(store, shelf);
    setShelfNames(Object.keys(readShelf(store)));
    replace(next.flow, { world: next.world, notice: `Opened ${next.flow.name}. ${here.name} is kept in this browser: the FLOWS row opens it again.` });
    if (wantTab && tabsOf(next.flow).some((t) => t.key === wantTab)) setTab(wantTab);
  };
  // `?block=<map>` when this browser's flow has no such block, but a ready-made flow has it (e.g.
  // xmas_dun02, the Rogue's map since 2026-11-13): open that flow on that tab (this one is kept)
  useEffect(() => {
    if (!initialBlock || tabsOf(start.flow).some((t) => t.key === `block:${initialBlock}`)) return;
    const ready = Object.entries(READY).find(([, make]) => make().flow.workflow?.blocks.some((b) => b.name === initialBlock));
    if (ready) switchTo(ready[0], `block:${initialBlock}`);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const flowItems: FlowItem[] = (() => {
    const names = [...new Set([flow.name, ...shelfNames, ...Object.keys(READY)])];
    return names.map((n) => ({
      name: n,
      state: n === flow.name ? ("open" as const) : shelfNames.includes(n) ? ("kept" as const) : ("starter" as const),
      run: n === flow.name ? runnerMapBlock(flow) !== undefined : n === XMAS_NAME,
    }));
  })();

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
  // Save and Load (components/flowfile/): a loaded file is already checked into a scratch flow
  const onOpened = (o: Opened) => {
    setDialog(null);
    replace(o.flow, { undo: true, file: o.meta, notice: `${o.notice} The backend checks it with MW1's schema at the next lint.` });
  };
  const pythonCached = useCallback((f: Flow) => (python && python.for === canonical(f) ? python.text : null), [python]);
  const pythonFor = useCallback(
    (f: Flow): Promise<string> => {
      const have = pythonCached(f);
      return have !== null ? Promise.resolve(have) : api.python(f).then((r) => r.python, () => "");
    },
    [api, pythonCached],
  );
  const startOver = () => {
    if (!window.confirm("Start a new program from the starter blocks? The flow here is replaced. (Undo, right after, brings it back.)")) return;
    replace(starterFlow(), { world: STARTER_WORLD, undo: true, notice: "Started a new program from the starter: two maps, on the sample sheets." });
  };
  const newWorkflow = () => {
    setMenu(false);
    replace(emptyFlow("new_flow", catalogue?.runtime_limits?.default_s), { undo: true, notice: "Started a new workflow: one map block, “start”. Add maps with “+ map block”, or on the Maps page." });
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
  const procs = Object.keys(flow.procedures);
  const startBlock = flow.workflow?.start_block ?? null;
  const showFinding = (f: Finding) => {
    const t = tabOf(f, plain, procs, startBlock);
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
    const t = id === "events:global" ? "events" : id.startsWith("events:") ? `block:${id.slice(7)}` : id;
    if (tabs.some((x) => x.key === t)) goTab(t);
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
  const editorReady = editor.ready;
  const issues = editor.issues;
  const loose = editor.loose;
  const status = statusText({
    loading: !editor.ready && !editor.failed,
    engine: engineErr,
    issues: issues.length,
    lintErrors: errors.length,
    simulating: simBusy,
    mapTab: false,
  });
  const total = lintDoc ? lintLine(lintDoc.counts) : null;
  const pythonOpen = view === "blocks" && pythonPanel === "open";
  const huntRules = catalogue?.hunt_rules ?? null;
  const openPanes = PANES.filter(([p]) => shown[p] && (p !== "hunt" || huntRules) && (p !== "run" || runnable));
  const pyText = python?.text ?? "";
  const pyStale = python !== null && python.for !== key;
  const codeText = codeFile === "py" ? pyText : exportText(flow);
  const zonesBlock = zonesFor ? flow.workflow?.blocks.find((x) => x.name === zonesFor) : undefined;
  useFileShortcuts(
    (d) => {
      setMenu(false);
      setDialog(d);
    },
    dialog,
    !zonesBlock,
  );

  const paneToggles = (cls: string, after?: () => void) =>
    PANES.filter(([p]) => (p !== "hunt" || huntRules) && (p !== "run" || runnable)).map(([p, label]) => (
      <button
        key={p}
        type="button"
        className={`toggle-button ${cls}`}
        aria-pressed={shown[p]}
        onClick={() => {
          setPane(p, !shown[p]);
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
      {codeFile === "json" && <p className="studio-panel-note">The flow IR, MW1&apos;s canonical JSON: the one source of truth (Save keeps it with this Python, on this computer or on GitHub; Load opens one).</p>}
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
                {/* the MAP FLOWS first, under their map's name (Batt 2026-11-13: "I don't see the
                    xmas_dun02 flow; name it after the map") */}
                <button type="button" role="menuitem" className="studio-menu-item studio-menu-item-map" onClick={() => (setMenu(false), switchTo(XMAS_NAME))} data-testid="load-xmas">
                  {XMAS_NAME}
                  <small>the Rogue&apos;s map: hunt with the runner, a Butterfly Wing home to Geffen; every key a function; Simulate, or Run in the game (this flow is kept)</small>
                </button>
                {onRunner &&
                  RUNNERS.map((r) => (
                    <button key={r.id} type="button" role="menuitem" className="studio-menu-item" onClick={() => (setMenu(false), flush(), onRunner(r.id))} data-testid={`load-runner-${r.id}`}>
                      Inside {r.script}
                      <small>the runner {r.title} plays, as blocks made from its code (read only): what &ldquo;hunt with the runner&rdquo; does</small>
                    </button>
                  ))}
                <button type="button" role="menuitem" className="studio-menu-item" onClick={() => (setMenu(false), setDialog("load"))} data-testid="load-saved">
                  Open a saved flow…<small>from this computer or from GitHub (checked before it opens; Ctrl+O)</small>
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
                <button type="button" role="menuitem" className="studio-menu-item" onClick={() => (setMenu(false), replace(oneMapStarter(), { undo: true, notice: "Opened the starter: one program, bound to no map." }))}>
                  Starter: one program (no map)<small>a plain flow, one tab “main”: wait, wait until the detector sees a monster, stop. Runs wherever the character stands</small>
                </button>
              </div>
            )}
          </div>
          <button type="button" className="button button-small button-file" onClick={() => (setMenu(false), setDialog("save"))} title="Save the flow: on this computer or on GitHub (Ctrl+S)" data-testid="save">
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
          {runnable && <LiveRunButtons live={live} blocked={runWhy} />}
        </div>
      </header>

      <FlowSwitcher items={flowItems} onPick={(n) => switchTo(n)} />

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
                  if (u) replace(u.flow, { world: u.world, file: u.file });
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
      {copied === "failed" && (
        <div className="studio-notices">
          {copied === "failed" && (
            <p className="notice notice-warn" role="status">
              This browser would not copy automatically (the page is not a secure origin). The code is selected: press Ctrl+C (⌘C) to copy it.
            </p>
          )}
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
                    title={t.scope.kind === "global" ? "Every map: the events every map shares (a map's tab may override, extend or disable one)" : t.scope.kind === "functions" ? "The functions: every map's blocks can call them; Save and Load carry them" : t.scope.kind === "block" ? `The flow of the map block ${t.scope.name}` : undefined}
                    data-testid={`tab-${t.key}`}
                  >
                    {t.label}
                    {((t.key === active.key && issues.length > 0) || errors.some((f) => tabOf(f, plain, procs, startBlock) === t.key)) && <span className="block-tab-problem" aria-label="has problems" />}
                  </button>
                </div>
              ))}
              {!plain && (
                <button type="button" className="block-tab-add" onClick={addMapBlock} title="Add a map block (a new tab)">
                  + map block
                </button>
              )}
            </div>
            <MapPicker flow={flow} tab={active.key} onTab={goTab} onLeave={flush} onRunner={onRunner ? (id) => (flush(), onRunner(id)) : undefined} />
          </div>
          <MapBinding flow={flow} tab={active.key} onTab={goTab} onLeave={flush} onLoadStarter={() => replace(starterFlow(), { world: STARTER_WORLD, undo: true, notice: "Opened the starter: two maps." })} />
          <div className="blocks-area">
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
            {view === "blocks" && editor.ready && (
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
                    selected={inspectOf(active.key)}
                    lint={lintDoc}
                    sim={simDoc && !simStale ? simDoc : null}
                    api={api}
                    world={world}
                    onUpdate={(name: string, props: BlockProps) => {
                      edit(updateBlock(flowRef.current, name, props));
                      if (props.name !== name) {
                        if (active.key === `block:${name}`) setTab(`block:${props.name}`);
                      }
                    }}
                    onDelete={(name) => {
                      edit(removeBlock(flowRef.current, name));
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
                {p === "run" && runDoc && (
                  <div className="run-pane" data-testid="run-pane">
                    <p className="muted">
                      Run plays <code>{runDoc.script}</code> on {runDoc.map} as a player (no GM line), from where she stands. Its keys are your functions: {keysLine}.{" "}
                      {onRunner && (
                        <button type="button" className="mb-link" onClick={() => (flush(), onRunner(runDoc.id))} data-testid="run-inside">
                          See inside the runner (read only) ↗
                        </button>
                      )}
                    </p>
                    <LiveRun live={live} checklist={cdoc && runValues ? startChecklist(cdoc, runValues, runDoc.map) : []} minutes={runValues ? Number(runValues.minutes) : null} />
                    {cdoc && <ConfigPanel d={cdoc} map={runDoc.map} cs={cs} problem={runWhy} replaced={{ keys: keysLine }} />}
                  </div>
                )}
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
          {editorReady ? status : "Loading the block editor…"}
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

      <FlowFileDialogs
        open={dialog}
        onClose={() => setDialog(null)}
        meta={file}
        onMeta={setFile}
        getFlow={getFlow}
        pythonCached={pythonCached}
        pythonFor={pythonFor}
        onOpened={onOpened}
      />

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

/** WHICH MAP this tab's flow is bound to (Batt 2026-11-10: "like binding a program to a robot in
 * matpilot"): at the end of the tab row, as matpilot's Robot choice is. Each map block's tab IS its
 * map's flow; the choice opens another map's tab, and "Maps" goes back to the maps graph (the
 * Maps page) with this map selected. */
function MapPicker({ flow, tab, onTab, onLeave, onRunner }: { flow: Flow; tab: string; onTab: (key: string) => boolean; onLeave: () => void; onRunner?: (id: string) => void }) {
  const wf = flow.workflow;
  const block = tab.startsWith("block:") ? wf?.blocks.find((b) => `block:${b.name}` === tab) : undefined;
  const runner = runnerForMap(block?.map.map); // a live runner's description of this map (2026-11-12)
  const title = !wf
    ? "None: a plain flow, one program with no map blocks. The Maps page shows the login before it."
    : block
      ? `This tab's flow is bound to the map ${block.map.map} (its map block ${block.name}): what the bot does on that map.`
      : "Every map's events, or the functions. Choose a map to open its flow (its map block's tab).";
  return (
    <div className="block-tabs-trailing robot-picker" data-testid="map-picker">
      <label className="robot-picker-label" title={title}>
        <span className="robot-picker-name">Map</span>
        <select className="robot-picker-select" value={block ? tab : ""} onChange={(e) => onTab(e.target.value || "events")} disabled={!wf} data-testid="map-picker-select">
          <option value="">{wf ? "every map" : "none"}</option>
          {wf?.blocks.map((b) => (
            <option key={b.name} value={`block:${b.name}`}>
              {b.map.map} · {b.name}
            </option>
          ))}
        </select>
      </label>
      {runner && onRunner && (
        <button type="button" className="runner-chip-button" onClick={() => onRunner(runner.id)} title={`What "hunt with the runner" does: ${runner.script} as blocks made from its code (read only)`} data-testid="map-picker-runner">
          Inside the runner ↗
        </button>
      )}
      <Link href={block ? `/maps?node=${encodeURIComponent(`block:${block.name}`)}` : "/maps"} className="robot-picker-link" onClick={onLeave} title="The maps graph: login, characters, the maps and their exits, and the simulator">
        ◂ Maps
      </Link>
    </div>
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
