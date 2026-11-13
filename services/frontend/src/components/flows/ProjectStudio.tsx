"use client";

// THE /flows STUDIO ON THE PROJECT MODEL (Batt 2026-11-13, docs/planning/project-model.md): ONE NODE
// of the project at a time -- a login, a choose-character, a map or the Global node of /maps --
// with its TABS, as matpilot's block tabs (its ADR 0013): exactly one "main" (the node's program;
// Global has none) and the person's own tabs of functions, events and variables. Main imports its
// node's tabs and Global; a node's function, event or variable of a Global name REPLACES Global's on
// that node. The Python beside the blocks is one file per tab (the flow engine's view).
//
// The layout is the earlier studio's (matpilot.org/blocks: a header, notices, the canvas with the
// Python beside it, a drawer of panes, the problems, a footer), whose markup follows MatPilot's
// BlocksApp.tsx (https://github.com/lumduan/matpilot, MIT, Copyright (c) 2026 Sarat Sonsuk; the
// licence text is in studio.css and THIRD_PARTY.md).
//
// What runs in the game: only Run, on a map node whose blocks hold "hunt with the runner" (the
// runner scripts/dungeon_hunt.py through the host's Run helper; its keys are the node's functions).
// Everything else is SIMULATE (the flow engine; no game, no input).
import "./studio.css";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { EditorApi, EditorState } from "@/components/flows/BlockEditor";
import FlowFileDialogs, { type FileDialog, type Opened, useFileShortcuts } from "@/components/flowfile/FlowFileDialogs";
import CodeView from "@/components/flows/CodeView";
import NodeInspector from "@/components/maps/NodeInspector";
import ConfigPanel, { useConfig } from "@/components/flows/ConfigPanel";
import LiveRun, { LiveRunButtons, useLiveRun } from "@/components/flows/LiveRun";
import { DEFAULT_SIM, FlowSettings, HuntRulesPanel, LintPanel, PathPanel, scenarioOf, type SimForm, SimulatePanel } from "@/components/flows/Panels";
import { ApiError, type CatalogueDoc, type Finding, FlowsApi, type LintDoc, type PythonFiles, type SimDoc, sitePath, type WorldSource } from "@/lib/flow/api";
import type { ToolboxScope } from "@/lib/flow/blockdefs";
import { configClash, effectiveConfig, startChecklist } from "@/lib/flow/config";
import { type FileMeta, newFileMeta, readFileMeta, writeFileMeta } from "@/lib/flow/file";
import { canonical } from "@/lib/flow/ir";
import { ACTIVE } from "@/lib/flow/liverun";
import { browserStorage, hasOldFlow, KEYS, pythonDefault, readChoice, readProjectText, readShelf, shelve, writeChoice, writeProjectText, writeShelf } from "@/lib/flow/prefs";
import {
  GLOBAL_ID,
  globalOf,
  homeFunctionOn,
  MAIN_TAB,
  mainOf,
  mapNodes,
  namesOf,
  newTabName,
  nodeById,
  overriddenBy,
  overridesOn,
  type PNode,
  type Project,
  runnerBlockOn,
  runnerKeysOn,
  sampleProject,
  type Tab,
  tabNameProblem,
  xmasProject,
} from "@/lib/flow/project";
import { exportProject, importProject } from "@/lib/flow/projectfile";
import { LIVE_FLOWS, runnerForMap } from "@/lib/flow/runners";
import { lintLine } from "@/lib/flow/status";
import { lintErrors, looseText, PROBLEM_HEADS, statusText } from "@/lib/flow/words";
import { backendHttpBase } from "@/lib/ws";

import FlowSwitcher, { type FlowItem } from "./FlowSwitcher";

const BlockEditor = dynamic(() => import("@/components/flows/BlockEditor"), {
  ssr: false,
  loading: () => <div className="blocks-workspace" data-status="loading" />,
});

const LINT_DEBOUNCE_MS = 2500;
const PYTHON_DEBOUNCE_MS = 350;
const PYTHON_RETRY_MS = 5000;
const SAVE_DEBOUNCE_MS = 800;
const NOTICE_MS = 12_000;
const VIEWS = ["blocks", "python"] as const;
const OPEN_CLOSED = ["open", "closed"] as const;
const WORLDS = ["local", "sample"] as const;
type Pane = "inspect" | "lint" | "simulate" | "paths" | "hunt" | "run";
const PANES: [Pane, string][] = [
  ["run", "Before Run"], // matpilot 2026-11-13 #4: one button is "Run" (the game); this is its checklist
  ["inspect", "Inspect"],
  ["lint", "Lint"],
  ["simulate", "Results"],
  ["paths", "Path map"],
  ["hunt", "Hunt rules"],
];
type Notice = { text: string; tone: "ok" | "warn" | "error"; undo: { project: Project; world: WorldSource; file: FileMeta } | null };
const NO_EDITOR: EditorState = { ready: false, failed: false, issues: [], loose: [], canUndo: false, canRedo: false };

/** The READY-MADE projects, by name, with the static data each is linted and simulated on. */
const READY: Record<string, () => { project: Project; world: WorldSource }> = {
  xmas_dun02: () => ({ project: xmasProject(), world: "local" }),
  my_first_project: () => ({ project: sampleProject(), world: "sample" }),
};

const KIND_WORDS: Record<PNode["kind"], string> = { login: "login", character: "character", map: "map", global: "Global" };

/** The node a page opens first: `?node=`, else the start map's (the first map), else the first. */
function firstNode(p: Project, want: string | null): string {
  if (want && nodeById(p, want)) return want;
  const start = p.edges.find((e) => nodeById(p, e.to)?.kind === "map")?.to;
  return start ?? mapNodes(p)[0]?.id ?? p.nodes[0].id;
}

/** The main tab's start words. */
function startWords(n: PNode): string {
  if (n.kind === "login") return "when the run starts: log in";
  if (n.kind === "character") return "after the login: choose the character";
  if (n.kind === "map") return `when she arrives on ${n.map.map}`;
  return "";
}

function initialProject(): { project: Project; world: WorldSource; restored: boolean; note: string | null } {
  const store = browserStorage();
  const text = readProjectText(store);
  if (text) {
    const r = importProject(text);
    if (r.ok) return { project: r.project, world: readChoice(store, KEYS.world, WORLDS, "local"), restored: true, note: null };
  }
  const note = hasOldFlow(store) ? "The flow format changed (2026-11-13: nodes and tabs): this browser's old flow is not converted. The ready-made project xmas_dun02 is open; Load has the others." : null;
  return { ...READY.xmas_dun02(), restored: false, note };
}

export default function ProjectStudio({ backendUrl, initialNode = null, onRunner }: { backendUrl: string | null; initialNode?: string | null; onRunner?: (id: string) => void }) {
  const [api] = useState<FlowsApi>(() => new FlowsApi(backendHttpBase(backendUrl)));
  const [start] = useState(initialProject);
  const [project, setProjectState] = useState<Project>(start.project);
  const projectRef = useRef<Project>(start.project);
  const [epoch, setEpoch] = useState(0);
  const [world, setWorld] = useState<WorldSource>(start.world);
  const [file, setFileState] = useState<FileMeta>(() => (start.restored ? readFileMeta(browserStorage(), start.project) : newFileMeta(start.project)));
  const fileRef = useRef<FileMeta>(file);
  const [nodeId, setNodeId] = useState<string>(() => firstNode(start.project, initialNode));
  const [tabName, setTabName] = useState<string>(MAIN_TAB);
  const [renaming, setRenaming] = useState<{ tab: string; text: string } | null>(null);
  const [catalogue, setCatalogue] = useState<CatalogueDoc | null>(null);
  const [engineErr, setEngineErr] = useState<string | null>(null);
  const [lint, setLint] = useState<{ doc: LintDoc; for: string } | null>(null);
  const [sim, setSim] = useState<{ doc: SimDoc; for: string } | null>(null);
  const [simForm, setSimForm] = useState<SimForm>(DEFAULT_SIM);
  const [simBusy, setSimBusy] = useState(false);
  const [python, setPython] = useState<{ doc: PythonFiles; for: string } | null>(null);
  const [pythonErr, setPythonErr] = useState<string | null>(null);
  const [codeFile, setCodeFile] = useState<string | null>(null);
  const [copied, setCopied] = useState<"idle" | "ok" | "failed">("idle");
  const [editor, setEditor] = useState<EditorState>(NO_EDITOR);
  const [editorApi, setEditorApi] = useState<EditorApi | null>(null);
  const pendingShow = useRef<{ key: string; path: string } | null>(null);
  const [notice, setNotice] = useState<Notice | null>(start.note ? { text: start.note, tone: "warn", undo: null } : null);
  const [menu, setMenu] = useState(false);
  const [more, setMore] = useState(false);
  const [dialog, setDialog] = useState<FileDialog>(null);
  const store = useMemo(() => browserStorage(), []);
  const [view, setViewState] = useState<(typeof VIEWS)[number]>(() => readChoice(store, KEYS.view, VIEWS, "blocks"));
  const [pythonPanel, setPythonPanel] = useState<(typeof OPEN_CLOSED)[number]>(() => {
    const wide = typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(min-width: 48rem)").matches : true;
    return readChoice(store, KEYS.python, OPEN_CLOSED, pythonDefault(wide));
  });
  const [panes, setPanes] = useState<Record<Pane, boolean>>(() =>
    Object.fromEntries(PANES.map(([p]) => [p, readChoice(store, KEYS[p], OPEN_CLOSED, "closed") === "open"])) as Record<Pane, boolean>,
  );
  const menuRef = useRef<HTMLDivElement | null>(null);
  const codeRef = useRef<HTMLPreElement | null>(null);
  const key = useMemo(() => canonical(project), [project]);

  const node: PNode = nodeById(project, nodeId) ?? project.nodes[0];
  const tabs: Tab[] = node.kind === "global" ? node.tabs : [...node.tabs.filter((t) => t.name === MAIN_TAB), ...node.tabs.filter((t) => t.name !== MAIN_TAB)];
  const tab: Tab | undefined = tabs.find((t) => t.name === tabName) ?? tabs[0];
  const scopeKey = tab ? `${node.id}/${tab.name}` : `${node.id}/`;
  const toolboxScope: ToolboxScope = { node: node.kind, main: tab?.name === MAIN_TAB && node.kind !== "global" };

  // --- RUN: a map node whose blocks hold the runner's block, on a map the Run helper plays -----------
  const runDoc = node.kind === "map" && runnerBlockOn(node) ? runnerForMap(node.map.map) : null;
  const runnable = !!runDoc && LIVE_FLOWS.includes(runDoc.id);
  const keysR = runnable ? runnerKeysOn(project, node.id) : null;
  const runKeys = keysR?.ok ? keysR.keys : null;
  const live = useLiveRun(backendUrl, runDoc?.id ?? "", runnable, runKeys);
  const cs = useConfig(backendUrl, runDoc?.map ?? "");
  const cdoc = runDoc?.config ?? null;
  const runEff = cdoc && runDoc ? effectiveConfig(cdoc, cs.file, runDoc.map) : null;
  const runValues = runEff ? (runKeys ? { ...runEff.values, ...runKeys } : runEff.values) : null;
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
    ? (["heal_key", "fly_key", "home_key", "knife_key", "dagger_key"] as const).map((k) => `${keysR.keys[k]} ${keysR.from[k]}()`).join(" · ")
    : (keysR?.problems.join("; ") ?? "");
  const runActive = runnable && ACTIVE.includes(live.st?.state ?? "");
  const shown: Record<Pane, boolean> = { ...panes, run: panes.run || runActive };

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

  // --- the project: from the blocks (no reload), or replaced from outside (the blocks reload) -------
  const fromBlocks = useCallback((p: Project) => {
    projectRef.current = p;
    setProjectState(p);
  }, []);
  const setFile = useCallback((m: FileMeta) => {
    fileRef.current = m;
    setFileState(m);
  }, []);
  const replace = useCallback(
    (p: Project, opts: { notice?: string; undo?: boolean; world?: WorldSource; keepView?: boolean; file?: FileMeta; node?: string } = {}) => {
      const prev = { project: projectRef.current, world, file: fileRef.current };
      projectRef.current = p;
      setProjectState(p);
      setEpoch((e) => e + 1);
      setFile(opts.file ?? (opts.keepView ? fileRef.current : newFileMeta(p)));
      if (!opts.keepView) {
        setSim(null);
        setNodeId(firstNode(p, opts.node ?? null));
        setTabName(MAIN_TAB);
      }
      if (opts.world) setWorld(opts.world);
      if (opts.notice) setNotice({ text: opts.notice, tone: "ok", undo: opts.undo ? prev : null });
    },
    [world, setFile],
  );

  useEffect(() => {
    if (!notice || notice.tone === "error") return;
    const t = setTimeout(() => setNotice(null), NOTICE_MS);
    return () => clearTimeout(t);
  }, [notice]);
  useEffect(() => {
    writeChoice(store, KEYS.world, world);
  }, [world, store]);
  // this browser's project, shared with /maps (written at once on the way there, and as the page goes)
  const flush = useCallback(() => {
    writeProjectText(store, exportProject(projectRef.current));
    writeFileMeta(store, fileRef.current, projectRef.current);
  }, [store]);
  useEffect(() => {
    const t = setTimeout(flush, SAVE_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [project, file, flush]);
  useEffect(() => () => void flush(), [flush]);

  // the browser tab names the node
  useEffect(() => {
    const before = document.title;
    const want = `${node.id} · ${project.name} · poring-lab flows`;
    const apply = () => {
      if (document.title !== want) document.title = want;
    };
    apply();
    const mo = typeof MutationObserver !== "undefined" ? new MutationObserver(apply) : null;
    mo?.observe(document.head, { childList: true, subtree: true, characterData: true });
    return () => {
      mo?.disconnect();
      document.title = before;
    };
  }, [node.id, project.name]);

  // close the Load menu on a click outside it, and on Escape (matpilot 2026-11-13 #15)
  useEffect(() => {
    if (!menu) return;
    const out = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenu(false);
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenu(false);
    };
    document.addEventListener("mousedown", out);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", out);
      document.removeEventListener("keydown", esc);
    };
  }, [menu]);

  // --- the engine: the catalogue, lint, the Python files -------------------------------------------
  useEffect(() => {
    api
      .catalogue(project.target.client)
      .then((c) => {
        setCatalogue(c);
        setEngineErr(null);
      })
      .catch((e) => setEngineErr(e instanceof ApiError ? e.reason : String(e)));
  }, [api, project.target.client]);

  const runLint = useCallback(
    async (p: Project, w: WorldSource) => {
      try {
        const doc = await api.lint(p, w);
        setLint({ doc, for: canonical(p) });
      } catch (e) {
        if (e instanceof ApiError && (e.reason === "invalid_flow" || e.reason === "invalid_project")) setNotice({ text: `The flow engine refuses this project: ${e.errors.join(" · ")}`, tone: "error", undo: null });
        else if (!(e instanceof ApiError && e.reason === "rate_limited")) setNotice({ text: `Lint failed: ${e instanceof ApiError ? e.message : String(e)}`, tone: "error", undo: null });
      }
    },
    [api],
  );
  useEffect(() => {
    const t = setTimeout(() => void runLint(project, world), LINT_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [project, world, runLint]);

  const py = useRef<{ busy: boolean; want: Project | null; until: number; timer: ReturnType<typeof setTimeout> | null }>({ busy: false, want: null, until: 0, timer: null });
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
      const p = s.want;
      s.want = null;
      s.busy = true;
      try {
        const doc = await api.python(p);
        setPython({ doc, for: canonical(p) });
        setPythonErr(null);
      } catch (e) {
        if (e instanceof ApiError && e.reason === "rate_limited") {
          s.until = Date.now() + PYTHON_RETRY_MS;
          s.want ??= p;
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
      py.current.want = projectRef.current;
      pyPump.current?.();
    }, PYTHON_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [key]);

  // --- the FLOWS row: projects by name; the one left is KEPT on this browser's shelf ----------------
  const [shelfNames, setShelfNames] = useState<string[]>(() => Object.keys(readShelf(store)).filter((n) => importProject(readShelf(store)[n].text).ok));
  const switchTo = (name: string) => {
    flush();
    const here = projectRef.current;
    shelve(store, here.name, exportProject(here), world);
    const shelf = readShelf(store);
    let next: { project: Project; world: WorldSource } | null = null;
    const kept = shelf[name];
    if (kept && name !== here.name) {
      const r = importProject(kept.text);
      if (r.ok) next = { project: r.project, world: WORLDS.includes(kept.world as WorldSource) ? (kept.world as WorldSource) : "local" };
    }
    if (!next && READY[name]) next = READY[name]();
    if (!next) return setNotice({ text: `The project ${name} could not be opened.`, tone: "error", undo: null });
    delete shelf[name];
    writeShelf(store, shelf);
    setShelfNames(Object.keys(readShelf(store)).filter((n) => importProject(readShelf(store)[n].text).ok));
    replace(next.project, { world: next.world, notice: `Opened ${next.project.name}. ${here.name} is kept in this browser: the FLOWS row opens it again.` });
  };
  // matpilot #14: the row's order never changes on a press (by name, not "the open one first")
  const flowItems: FlowItem[] = [...new Set([project.name, ...shelfNames, ...Object.keys(READY)])].sort().map((n) => ({
    name: n,
    state: n === project.name ? "open" : shelfNames.includes(n) ? "kept" : "starter",
    run: n === project.name ? mapNodes(project).some((m) => runnerBlockOn(m) !== null) : n === "xmas_dun02",
  }));

  // --- load, save, start over, simulate -------------------------------------------------------------
  const loadGlobals = useRef(false);
  const onOpened = (o: Opened) => {
    setDialog(null);
    if (loadGlobals.current) {
      // SHARING A MODULE: the opened project's Global tabs join this one's; a tab name this
      // project's Global has already keeps ours
      loadGlobals.current = false;
      const into = structuredClone(projectRef.current);
      const g = globalOf(into);
      const from = globalOf(o.project);
      if (!g || !from) return setNotice({ text: "One of the two projects has no Global node.", tone: "error", undo: null });
      const added: string[] = [];
      const kept: string[] = [];
      for (const t of from.tabs) {
        if (g.tabs.some((x) => x.name === t.name)) kept.push(t.name);
        else {
          g.tabs.push(structuredClone(t));
          added.push(t.name);
        }
      }
      replace(into, { undo: true, keepView: true, notice: `Global tabs of ${o.project.name}: ${added.length ? `added ${added.join(", ")}` : "nothing new"}${kept.length ? `; yours kept (the same name): ${kept.join(", ")}` : ""}.` });
      return;
    }
    replace(o.project, { undo: true, file: o.meta, notice: `${o.notice} The flow engine checks it at the next lint.` });
  };
  const pythonText = useCallback((d: PythonFiles) => d.files.map((f) => `# --- ${f.path}\n${f.text}`).join("\n"), []);
  const pythonCached = useCallback((p: Project) => (python && python.for === canonical(p) ? pythonText(python.doc) : null), [python, pythonText]);
  const pythonFor = useCallback(
    (p: Project): Promise<string> => {
      const have = pythonCached(p);
      return have !== null ? Promise.resolve(have) : api.python(p).then((r) => pythonText(r), () => "");
    },
    [api, pythonCached, pythonText],
  );
  useFileShortcuts(
    (d) => {
      loadGlobals.current = false;
      setMenu(false);
      setDialog(d);
    },
    dialog,
    true,
  );
  const startOver = () => {
    if (!window.confirm("Open the ready-made xmas_dun02 project again? The project here is replaced (Undo, right after, brings it back).")) return;
    replace(READY.xmas_dun02().project, { world: "local", undo: true, notice: "Opened the ready-made project xmas_dun02." });
  };
  const simulate = async (form: SimForm) => {
    setSimBusy(true);
    setPane("simulate", true);
    const p = projectRef.current;
    try {
      const doc = await api.simulate(p, world, scenarioOf(form));
      setSim({ doc, for: canonical(p) });
      setLint({ doc: doc.lint, for: canonical(p) });
    } catch (e) {
      setNotice({ text: `Simulate failed: ${e instanceof ApiError ? e.message : String(e)}`, tone: "error", undo: null });
    } finally {
      setSimBusy(false);
    }
  };

  // --- tabs: open, add, rename, close (matpilot's ADR 0013 decision 1) -------------------------------
  const goTab = (name: string, id: string = node.id): boolean => {
    if ((name !== tab?.name || id !== node.id) && editor.issues.length > 0) {
      setNotice({ text: "Fix the problems under the blocks first (or press Undo): this tab's blocks cannot become the project yet, and leaving the tab would lose them.", tone: "warn", undo: null });
      return false;
    }
    if (id !== node.id) setNodeId(id);
    setTabName(name);
    return true;
  };
  const editNode = (f: (n: PNode) => void) => {
    const p = structuredClone(projectRef.current);
    const n = nodeById(p, node.id);
    if (!n) return;
    f(n);
    replace(p, { keepView: true });
  };
  const addTab = () => {
    if (editor.issues.length > 0) return goTab(tab?.name ?? MAIN_TAB);
    const name = newTabName(node);
    editNode((n) => n.tabs.push({ name, main: null, defs: [], vars: {} }));
    setTabName(name);
    setRenaming({ tab: name, text: name });
  };
  const renameTab = (from: string, to: string) => {
    setRenaming(null);
    if (to === from) return;
    const why = tabNameProblem(node, to, from);
    if (why) return setNotice({ text: `The tab cannot be called “${to.slice(0, 30)}”: ${why}.`, tone: "error", undo: null });
    editNode((n) => {
      const t = n.tabs.find((x) => x.name === from);
      if (t) t.name = to;
    });
    if (tab?.name === from) setTabName(to);
  };
  const closeTab = (name: string) => {
    const t = node.tabs.find((x) => x.name === name);
    if (!t || (name === MAIN_TAB && node.kind !== "global")) return;
    if ((t.defs.length || Object.keys(t.vars).length) && !window.confirm(`Close the tab “${name}”? Its ${t.defs.length} function(s) and ${Object.keys(t.vars).length} variable(s) go with it (Undo brings them back).`)) return;
    const prev = { project: projectRef.current, world, file: fileRef.current };
    editNode((n) => {
      n.tabs = n.tabs.filter((x) => x.name !== name);
    });
    if (tab?.name === name) setTabName(MAIN_TAB);
    setNotice({ text: `Closed the tab “${name}”.`, tone: "ok", undo: prev });
  };

  // --- problems and showing a block --------------------------------------------------------------------
  const lintDoc = lint?.doc ?? null;
  const lintStale = lint !== null && lint.for !== key;
  const simDoc = sim?.doc ?? null;
  const simStale = sim !== null && sim.for !== key;
  const errors = lintStale ? [] : lintErrors(lintDoc);
  const showFinding = (f: Finding) => {
    const id = f.node && nodeById(project, f.node) ? f.node : node.id;
    const t = f.tab || MAIN_TAB;
    if (id === node.id && t === tab?.name && editorApi) {
      editorApi.showPath(sitePath(f));
      return;
    }
    if (!goTab(t, id)) return;
    pendingShow.current = { key: `${id}/${t}`, path: sitePath(f) };
  };
  useEffect(() => {
    const want = pendingShow.current;
    if (!want || !editorApi || want.key !== scopeKey) return;
    editorApi.showPath(want.path);
    pendingShow.current = null;
  }, [editorApi, scopeKey]);

  const onEditorState = useCallback((s: EditorState) => setEditor(s), []);
  const onEditorApi = useCallback((a: EditorApi | null) => setEditorApi(() => a), []);
  const getProject = useCallback(() => projectRef.current, []);
  const issues = editor.issues;
  const loose = editor.loose;
  const status = statusText({ loading: !editor.ready && !editor.failed, engine: engineErr, issues: issues.length, lintErrors: errors.length, simulating: simBusy, mapTab: false });
  const total = lintDoc ? lintLine(lintDoc.counts) : null;
  const pythonOpen = view === "blocks" && pythonPanel === "open";
  const huntRules = catalogue?.hunt_rules ?? null;
  const visiblePanes = PANES.filter(([p]) => (p !== "hunt" || huntRules) && (p !== "run" || runnable));
  const openPanes = visiblePanes.filter(([p]) => shown[p]);
  const tabErrors = (t: string) => errors.some((f) => (f.node || node.id) === node.id && (f.tab || MAIN_TAB) === t);
  const nodeErrors = (id: string) => errors.some((f) => f.node === id);

  // the Python files: this node's tabs, then Global's (main imports them)
  const files = python?.doc.files ?? [];
  const mine = files.filter((f) => f.node === node.id);
  const globalFiles = node.kind === "global" ? [] : files.filter((f) => f.node === GLOBAL_ID);
  const fileShown = [...mine, ...globalFiles].find((f) => f.path === codeFile) ?? mine.find((f) => f.tab === tab?.name) ?? mine[0] ?? null;
  const pyStale = python !== null && python.for !== key;
  const copy = () => {
    const text = fileShown?.text ?? "";
    void (navigator.clipboard?.writeText(text) ?? Promise.reject(new Error("no clipboard"))).then(
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

  const codePane = (full: boolean) => (
    <>
      <div className="studio-panel-header">
        <h2 id={full ? "python-full-heading" : "python-side-heading"}>{full ? "Python made from your blocks" : "Python"}</h2>
        <div className="button-row">
          <button type="button" className="button button-small" onClick={copy} disabled={!fileShown} title="Copy this file">
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
        {[...mine, ...globalFiles].map((f) => (
          <button key={f.path} type="button" role="tab" className="python-file" aria-selected={fileShown?.path === f.path} onClick={() => setCodeFile(f.path)} data-testid={`python-file-${f.path}`}>
            {f.path}
          </button>
        ))}
      </div>
      {(pythonErr || pyStale || issues.length > 0) && (
        <p className="studio-panel-note">{issues.length > 0 ? "Not up to date: fix the problems under the blocks first." : pythonErr ? `Not up to date: ${pythonErr}` : "Updating…"}</p>
      )}
      {node.kind !== "global" && globalFiles.length > 0 && <p className="studio-panel-note">main imports this node&apos;s other tabs and Global&apos;s ({globalFiles.map((f) => f.tab).join(", ")}); a name of this node replaces Global&apos;s here.</p>}
      {fileShown ? (
        <CodeView ref={codeRef} code={fileShown.text} colour label={`Python: ${fileShown.path}`} testId="python-code" />
      ) : (
        <p className="studio-panel-note">The Python view is made by the flow engine…</p>
      )}
    </>
  );

  const paneToggles = (cls: string, after?: () => void) =>
    visiblePanes.map(([p, label]) => (
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
      </button>
    ));

  const overrides = overridesOn(project, node.id);
  const strip = nodeStrip(project, node, overrides);

  return (
    <main className="studio" data-view={view} data-testid="flows-app">
      <header className="studio-bar">
        <div className="studio-brand">
          <span className="studio-home">Flows</span>
          {/* matpilot 2026-11-13 #3: the badge says what THIS page can do */}
          <span className="status-pill" title={runnable ? "Simulate plays the blocks without the game; Run (amber) plays the runner in the game" : "Nothing on this node runs in the game: Simulate only"}>
            {runnable ? "SIMULATE · RUN" : "SIMULATE only"}
          </span>
          <h1 className="studio-title" title={`${project.name}: ${node.id}`}>
            {project.name} <span className="muted">· {node.id}</span>
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
            <button type="button" className="button button-small button-file" onClick={() => setMenu(!menu)} aria-expanded={menu} title="Open a project" data-testid="load">
              <FolderIcon />
              <span className="button-text">Load</span>
            </button>
            {menu && (
              <div className="studio-menu-list" role="menu">
                <button type="button" role="menuitem" className="studio-menu-item studio-menu-item-map" onClick={() => (setMenu(false), switchTo("xmas_dun02"))} data-testid="load-xmas">
                  xmas_dun02
                  <small>the Rogue: login → character → xmas_dun02 (hunt with the runner, a Butterfly Wing home); every key a function in Global; Run in the game (the project open now is kept)</small>
                </button>
                <button type="button" role="menuitem" className="studio-menu-item" onClick={() => (setMenu(false), switchTo("my_first_project"))} data-testid="load-sample-project">
                  my_first_project
                  <small>the two-map sample: town → NPC warp → field, a Butterfly Wing back (synthetic maps; Simulate only)</small>
                </button>
                <button type="button" role="menuitem" className="studio-menu-item" onClick={() => ((loadGlobals.current = false), setMenu(false), setDialog("load"))} data-testid="load-saved">
                  Open a saved project…<small>from this computer or from GitHub (checked before it opens; Ctrl+O)</small>
                </button>
                <button type="button" role="menuitem" className="studio-menu-item" onClick={() => ((loadGlobals.current = true), setMenu(false), setDialog("load"))} data-testid="load-globals">
                  Add the Global tabs of a saved project…<small>a shared module: its Global tabs join this project&apos;s Global (a tab name you have already keeps yours)</small>
                </button>
                {onRunner &&
                  runDoc && (
                    <button type="button" role="menuitem" className="studio-menu-item" onClick={() => (setMenu(false), flush(), onRunner(runDoc.id))} data-testid="load-inside">
                      Inside {runDoc.script}
                      <small>what the block “hunt with the runner” does, as blocks made from its code (read only)</small>
                    </button>
                  )}
              </div>
            )}
          </div>
          <button type="button" className="button button-small button-file" onClick={() => (setMenu(false), setDialog("save"))} title="Save the project: on this computer or on GitHub (Ctrl+S)" data-testid="save">
            <SaveIcon />
            <span className="button-text">Save</span>
          </button>
          <button type="button" className="button button-small button-file" onClick={startOver} title="Open the ready-made project again" data-testid="start-over">
            <NewIcon />
            <span className="button-text">Start over</span>
          </button>
          <button type="button" className="button button-primary button-run" onClick={() => void simulate(simForm)} disabled={simBusy || issues.length > 0} title="Play the project in the simulator: no game, no input" data-testid="simulate">
            <PlayIcon />
            <span className="button-text">{simBusy ? "Simulating…" : "Simulate"}</span>
          </button>
          {runnable && <LiveRunButtons live={live} blocked={runWhy} keys={runKeys} />}
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
                  if (u) replace(u.project, { world: u.world, file: u.file, keepView: true });
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
          <p className="notice notice-warn" role="status">
            This browser would not copy automatically (the page is not a secure origin). The code is selected: press Ctrl+C (⌘C) to copy it.
          </p>
        </div>
      )}

      <div className="device-bar" aria-label="The project">
        <label className="device-chip" title="The node of /maps this page shows: its tabs">
          <span className="device-label">node</span>
          <select
            value={node.id}
            onChange={(e) => {
              const n = nodeById(project, e.target.value);
              goTab(n?.kind === "global" ? (n.tabs[0]?.name ?? MAIN_TAB) : MAIN_TAB, e.target.value);
            }}
            data-testid="node-select"
          >
            {project.nodes.map((n) => (
              <option key={n.id} value={n.id}>
                {/* matpilot #12: never "xmas_dun02 · xmas_dun02" */}
                {n.kind === "map" && n.map.map !== n.id ? `${n.id} (map ${n.map.map})` : n.kind === "map" ? `${n.id} (map)` : `${n.id} (${KIND_WORDS[n.kind]})`}
                {nodeErrors(n.id) ? " ⚠" : ""}
              </option>
            ))}
          </select>
        </label>
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
        <Link href={`/maps?node=${encodeURIComponent(node.id)}`} className="device-chip robot-picker-link" onClick={flush} title="The maps graph: every node and how they link" data-testid="to-maps">
          ◂ Maps
        </Link>
        {onRunner && runDoc && (
          <button type="button" className="device-chip runner-chip-button" onClick={() => (flush(), onRunner(runDoc.id))} title={`What "hunt with the runner" does: ${runDoc.script} as blocks made from its code (read only)`} data-testid="inside-runner">
            Inside the runner ↗
          </button>
        )}
      </div>

      <div className="studio-body" data-python-panel={pythonOpen ? "open" : "closed"}>
        <div className="studio-canvas">
          <div className="block-tabs-bar">
            <div className="block-tabs" role="tablist" aria-label="Tabs">
              {tabs.map((t) => (
                <div key={t.name} className="block-tab" data-active={t.name === tab?.name}>
                  {renaming?.tab === t.name ? (
                    <input
                      className="block-tab-rename"
                      value={renaming.text}
                      autoFocus
                      maxLength={20}
                      onChange={(e) => setRenaming({ tab: t.name, text: e.target.value.toLowerCase().replace(/\s+/g, "_") })}
                      onBlur={() => renameTab(t.name, renaming.text)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") renameTab(t.name, renaming.text);
                        if (e.key === "Escape") setRenaming(null);
                      }}
                      aria-label="The tab's name"
                      data-testid="tab-rename"
                    />
                  ) : (
                    <button
                      type="button"
                      role="tab"
                      aria-selected={t.name === tab?.name}
                      className="block-tab-name"
                      onClick={() => goTab(t.name)}
                      onDoubleClick={() => t.name !== MAIN_TAB && setRenaming({ tab: t.name, text: t.name })}
                      title={t.name === MAIN_TAB ? "main: this node's program (it imports the other tabs and Global)" : "A tab of functions, events and variables (double-click to rename)"}
                      data-testid={`tab-${t.name}`}
                    >
                      {t.name}
                      {((t.name === tab?.name && issues.length > 0) || tabErrors(t.name)) && <span className="block-tab-problem" aria-label="has problems" />}
                    </button>
                  )}
                  {t.name !== MAIN_TAB && (
                    <button type="button" className="block-tab-close" onClick={() => closeTab(t.name)} title={`Close the tab ${t.name}`} aria-label={`Close the tab ${t.name}`} data-testid={`tab-close-${t.name}`}>
                      ×
                    </button>
                  )}
                </div>
              ))}
              <button type="button" className="block-tab-add" onClick={addTab} title="A new tab of functions, events and variables" data-testid="tab-add">
                + tab
              </button>
            </div>
          </div>
          <div className="map-binding" data-kind={node.kind} data-testid="node-strip">
            {strip.map((s) => (
              <span key={s.head} className="map-binding-part">
                <span className="map-binding-head">{s.head}</span> {s.text}
              </span>
            ))}
          </div>
          <div className="blocks-area">
            {tab ? (
              <BlockEditor
                scope={{ node: node.id, tab: tab.name }}
                toolboxScope={toolboxScope}
                title={startWords(node)}
                scopeKey={scopeKey}
                epoch={epoch}
                getProject={getProject}
                catalogue={catalogue}
                lint={lintStale ? null : lintDoc}
                trace={simDoc && !simStale ? simDoc.trace : null}
                hidden={view === "python"}
                onProject={fromBlocks}
                onState={onEditorState}
                onApi={onEditorApi}
              />
            ) : (
              <div className="blocks-workspace">
                <p className="muted studio-loading">The Global node has no tab yet: press “+ tab” to write its first functions.</p>
              </div>
            )}
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
                  <div className="stack" data-testid="inspect-pane">
                    <NodeInspector
                      project={project}
                      nodeId={node.id}
                      lint={lintStale ? null : lintDoc}
                      credentials={catalogue?.credentials}
                      canOpen={false}
                      onChange={(p) => replace(p, { keepView: true })}
                      onOpen={(id) => goTab(MAIN_TAB, id)}
                      onRenamed={(_from, to) => setNodeId(to)}
                    />
                    <FlowSettings flow={project} limits={catalogue?.runtime_limits ?? null} onFlow={(f) => replace(f, { keepView: true })} />
                  </div>
                )}
                {p === "lint" && <LintPanel lint={lintDoc} stale={lintStale} onSelect={showFinding} />}
                {p === "simulate" && (
                  <SimulatePanel
                    blocks={mapNodes(project).map((m) => m.id)}
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
                {p === "paths" && <PathPanel server={project.target.server} sim={simDoc} stale={simStale} world={world} api={api} />}
                {p === "hunt" && huntRules && <HuntRulesPanel rules={huntRules} l1={catalogue?.blocks.hunt?.badge ?? "unknown"} />}
                {p === "run" && runDoc && (
                  <div className="run-pane" data-testid="run-pane">
                    <p className="muted">
                      Run (the amber button at the top) plays <code>{runDoc.script}</code> on {runDoc.map} as a player (no GM line), from where she stands. Its keys are this node&apos;s functions
                      (its own first, then Global&apos;s): {keysLine}.
                    </p>
                    <LiveRun live={live} checklist={cdoc && runValues ? startChecklist(cdoc, runValues, runDoc.map, runKeys ?? undefined) : []} minutes={runValues ? Number(runValues.minutes) : null} keys={runKeys} blocked={runWhy} />
                    {/* matpilot #7: say where these are kept */}
                    <p className="muted">The settings below are saved on the bot server the moment one changes (every browser sees them). The blocks and their functions are this browser&apos;s, until you Save.</p>
                    {cdoc && <ConfigPanel d={cdoc} map={runDoc.map} cs={cs} problem={runWhy} replaced={{ keys: `${keysLine} (this node's functions)` }} />}
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
                      {f.node && f.node !== node.id ? `${f.node} · ${f.tab}: ` : f.tab && f.tab !== tab?.name ? `${f.tab}: ` : ""}
                      {f.message}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {loose.length > 0 && (
            <div className="notice" data-testid="loose-blocks">
              <strong>{PROBLEM_HEADS.loose}</strong>
              <ul>
                {loose.map((l, i) => (
                  <li key={l.id ?? i}>
                    <button type="button" className="problem-link" onClick={() => l.id && editorApi?.showBlock(l.id)} title="Show the block">
                      {looseText(l, { kind: "main" })}
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
          {editor.ready ? status : "Loading the block editor…"}
        </p>
        <div className="studio-toggles" role="group" aria-label="Panels">
          {view === "blocks" && (
            <button type="button" className="toggle-button" aria-pressed={pythonOpen} onClick={togglePython} data-testid="toggle-python">
              Python
            </button>
          )}
          {paneToggles("pane-toggle")}
          <div className="toggles-more-wrap">
            <button type="button" className="toggle-button toggles-more" aria-expanded={more} onClick={() => setMore(!more)} data-testid="toggle-more">
              More ▾
            </button>
            {more && <div className="toggles-menu">{paneToggles("", () => setMore(false))}</div>}
          </div>
        </div>
      </footer>

      <FlowFileDialogs
        open={dialog}
        onClose={() => ((loadGlobals.current = false), setDialog(null))}
        meta={file}
        onMeta={setFile}
        getFlow={getProject}
        pythonCached={pythonCached}
        pythonFor={pythonFor}
        onOpened={onOpened}
      />
    </main>
  );
}

/** The strip under the tabs: what this node is, what it imports, what it replaces of Global's. */
function nodeStrip(p: Project, n: PNode, overrides: string[]): { head: string; text: string }[] {
  const out: { head: string; text: string }[] = [];
  const g = globalOf(p);
  if (n.kind === "global") {
    const names = [...namesOf(n).entries()];
    out.push({ head: "GLOBAL", text: `shared by every node: ${n.tabs.length} tab${n.tabs.length === 1 ? "" : "s"} (${n.tabs.map((t) => t.name).join(", ") || "none yet"})` });
    const replaced = names.map(([k]) => [k, overriddenBy(p, k)] as const).filter(([, by]) => by.length);
    if (replaced.length) out.push({ head: "REPLACED ON", text: replaced.map(([k, by]) => `${k}: ${by.join(", ")}`).join(" · ") });
    return out;
  }
  if (n.kind === "login") {
    const s = mainOf(n)?.main?.find((x) => x.kind === "action" && x.block === "login");
    const arg = (k: string) => (s && s.kind === "action" && s.params[k]?.kind === "lit" ? String((s.params[k] as { value: unknown }).value) : "?");
    out.push({ head: "LOGIN", text: `to ${arg("server")} with the credential ${arg("credential")} (a name: never a password) · simulated; the bot's real login is its own Python` });
  } else if (n.kind === "character") {
    out.push({ head: "CHARACTER", text: "the slot the client remembers, unless a name is given · simulated" });
  } else {
    const arrives = p.edges.filter((e) => e.to === n.id).map((e) => `${e.entry ?? n.entries[0]?.name}: from ${e.from}`);
    out.push({ head: "MAP", text: `${n.map.map}${arrives.length ? ` · arrives ${arrives.join(", ")}` : ""}` });
    const home = homeFunctionOn(n);
    const exits: string[] = [];
    for (const t of n.tabs) for (const s of [...(t.main ?? []), ...t.defs.flatMap((d) => d.body)]) if (s.kind === "take_exit") exits.push(`→ ${s.exit.to_block} (${s.exit.kind === "item_warp" ? (s.exit.proc ? `${s.exit.proc}()` : "an item") : s.exit.kind.replace("_", " ")})`);
    if (exits.length) out.push({ head: "EXITS", text: exits.join(" · ") });
    if (home && runnerBlockOn(n)) out.push({ head: "RUN", text: "hunt with the runner: Run (amber, at the top) plays it in the game" });
  }
  out.push({ head: "IMPORTS", text: `${n.tabs.length > 1 ? `its tabs (${n.tabs.filter((t) => t.name !== MAIN_TAB).map((t) => t.name).join(", ")}) and ` : ""}Global${g ? ` (${g.tabs.map((t) => t.name).join(", ") || "no tab yet"})` : ""}` });
  if (overrides.length) out.push({ head: "REPLACES GLOBAL'S", text: overrides.join(", ") });
  return out;
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
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path d="M1.5 4.5v8h13v-6.5H7.5L6 4.5z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}
function SaveIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path d="M8 2v8M4.5 6.5L8 10l3.5-3.5M2.5 13.5h11" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function NewIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path d="M3.5 1.5h6l3 3v10h-9zM9.5 1.5v3h3M8 7v5M5.5 9.5h5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  );
}
function PlayIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path d="M5 3.5v9l7-4.5z" fill="currentColor" />
    </svg>
  );
}
function UndoIcon({ redo = false }: { redo?: boolean }) {
  return (
    <svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true" focusable="false" style={redo ? { transform: "scaleX(-1)" } : undefined}>
      <path d="M5.5 4.5L2.5 7.5l3 3M2.5 7.5h7a4 4 0 010 8h-2" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
