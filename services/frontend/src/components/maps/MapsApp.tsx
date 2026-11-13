"use client";

// The MAPS page on the PROJECT model (Batt 2026-11-13, docs/planning/project-model.md: "a login
// node, a choose-character node, a node for each map (all of them can be linked into a work flow),
// and a GLOBAL node that can share variables and functions; double-click a node and it comes to
// /flows"). The graph is the project's own nodes (lib/maps/graph.ts): Login -> Choose character ->
// the start map are the project's connections (n8n's way: drawn, dragged, deleted, one path); map
// -> map links are the map nodes' EXITS (take_exit statements in their tabs); Global is shared by
// every node and has no ports. Matpilot's mat for maps stays: SIMULATE plays the bot through the
// session and the maps' tabs on each map's walk grid (walking, monsters, NPCs, warps), the graph
// following it.
//
// The green button is SIMULATE (no game, no input). RUN (amber, beside it; Batt 2026-11-13 ~21:4x:
// "on the Maps page add a Run button too: it runs from START, box by box") is the ONE live path:
// on a project whose START is a map node (the one box: START > xmas_dun02, where a person put her),
// it asks the Run helper's live block player to play the project from there (POST
// /flows/run/project, components/flows/LiveRun.tsx: the same button, the same press-twice confirm
// as /flows'), greyed with the reason while a block on the way is not live yet or START is a login
// node (login is not live yet). A credential is a NAME (the login node's), never a secret. Every
// other backend call is computation only (lib/flow/api.ts: lint, simulate, the Python view, the
// static data); the page never reaches the mux, an agent channel or any input path itself. Every
// name is rendered as text.
//
// The project is /flows' own (the same browser storage, prefs.ts PROJECT_STORE): double-click a
// node, or its "Open flow", and /flows opens that node's tabs (/flows?node=<id>). The layout follows
// MatPilot's Mats page (src/components/mats/MatsApp.tsx at commit d639909; MIT License, Copyright
// (c) 2026 Sarat Sonsuk; the licence text is in studio.css and THIRD_PARTY.md): the stage with the
// playback bar over it, the panel beside it.
import "@/components/flows/studio.css";
import "./maps.css";

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import CodeView from "@/components/flows/CodeView";
import { LiveRunButtons, RunNotReady, useLiveRun } from "@/components/flows/LiveRun";
import { CaretIcon, CloseIcon, FolderIcon, PlayIcon, SaveIcon } from "@/components/maps/icons";
import LinksPanel from "@/components/maps/LinksPanel";
import LintList from "@/components/maps/LintList";
import NodeInspector from "@/components/maps/NodeInspector";
import RulesPanel from "@/components/maps/RulesPanel";
import { DEFAULT_RUN, PlaybackBar, RunPanel, type RunForm, SPEEDS } from "@/components/maps/SidePanels";
import { ApiError, type CatalogueDoc, FlowsApi, type LintDoc, type PythonFiles, type Scenario, type SimDoc, type WorldDoc, type WorldMap, type WorldSource } from "@/lib/flow/api";
import { type AuthoredExit, canonical, MAP_ID } from "@/lib/flow/ir";
import { browserStorage, hasOldFlow, KEYS, readChoice, readProjectText, readText, writeChoice, writeProjectText } from "@/lib/flow/prefs";
import { ACTIVE, liveLabel, liveLine, PROJECT_FLOW } from "@/lib/flow/liverun";
import { liveReady } from "@/lib/flow/liveready";
import { mapNodes, nodeById, type Project, runnerBlockOn, runnerKeysOn, sampleProject, sessionPath, startMap as mapStartOf, xmasProject } from "@/lib/flow/project";
import { LIVE_FLOWS, runnerForMap } from "@/lib/flow/runners";
import { exportProject, importProject } from "@/lib/flow/projectfile";
import { type FileMeta, newFileMeta, readFileMeta, writeFileMeta } from "@/lib/flow/file";
import FlowFileDialogs, { type FileDialog, type Opened, useFileShortcuts } from "@/components/flowfile/FlowFileDialogs";
import { lintLine } from "@/lib/flow/status";
import { addMapNode, type MapFacts } from "@/lib/maps/build";
import { connectExit, connectSession, type Edit, moveNodes, removeExit, removeSession, retargetExit, setStart, setZones } from "@/lib/maps/edit";
import { activeEdgeAt, mapsGraph, type XY } from "@/lib/maps/graph";
import { type LintGroup, lintGroups, nodeTitle } from "@/lib/maps/nodewords";
import { beatAt, beatText, buildTimeline, type Check, type Labels, poseAt, runChecks, type Timeline } from "@/lib/maps/play";
import { refreshRule } from "@/lib/maps/rules";
import { characterOf, credentialOf, loginOf, sessionOf, sessionProblems, sessionSteps, slotText } from "@/lib/maps/session";
import { WANDER_KEY } from "@/lib/maps/wander";
import { backendHttpBase } from "@/lib/ws";

const MapsCanvas = dynamic(() => import("@/components/maps/MapsCanvas"), {
  ssr: false,
  loading: () => <p className="muted studio-loading">Loading the maps…</p>,
});
const MatView = dynamic(() => import("@/components/maps/MatView"), { ssr: false });
const ZonesEditor = dynamic(() => import("@/components/flows/ZonesEditor"), { ssr: false });

const LINT_DEBOUNCE_MS = 2500;
const PYTHON_DEBOUNCE_MS = 500;
const SAVE_DEBOUNCE_MS = 800;
const NOTICE_MS = 12_000;
const WORLDS = ["local", "sample"] as const;
const SIDES = ["node", "run", "python"] as const;
type Side = (typeof SIDES)[number];
const OPEN_CLOSED = ["open", "closed"] as const;
const BOTTOMS = ["links", "map"] as const; // round 6: the panel under the graph
type Bottom = (typeof BOTTOMS)[number];
const MK = {
  side: "poring-lab.maps.side.v1",
  mat: "poring-lab.maps.mat-view.v1",
  panel: "poring-lab.maps.panel.v1",
  run: "poring-lab.maps.run.v1",
  bottom: "poring-lab.maps.bottom.v1",
} as const;
const EXAMPLE_MAPS = ["xmas_dun02", "geffen", "town_1", "field_1"];
const RULES = "rules"; // the side panel's world rules (not a node id: ids are names, "rules" too, so it is checked first)
const PROJECT_FILE = ".project.json";
type Notice = { text: string; tone: "ok" | "warn" | "error"; undo: { project: Project; world: WorldSource } | null };
type Sim = { doc: SimDoc; for: string; tl: Timeline; seed: number | null; old: boolean; mock: boolean };
// "lint": the lint chip's list (matpilot round 16 #7: every finding the chip counts, the project's own too)
type Selection = { kind: "node"; id: string } | { kind: "rules" } | { kind: "lint" } | null;

/** The ready-made projects (project.ts; docs/planning/project-model.md section 7). */
const READY: { id: string; make: () => Project; world: WorldSource; title: string; words: string }[] = [
  { id: "xmas", make: xmasProject, world: "local", title: "xmas_dun02", words: "the Rogue, ONE box: START → xmas_dun02, where you put her (hunt with the runner; it flies home on the Butterfly Wing itself); every key a function in its keys tab" },
  { id: "sample", make: sampleProject, world: "sample", title: "my_first_project", words: "two SYNTHETIC maps on the sample sheets: a town (save point, NPC warp) and a field (attack 5 times, a wing back)" },
];

function initialProject(store: ReturnType<typeof browserStorage>): { project: Project; restored: boolean; broken: boolean } {
  const text = readProjectText(store);
  if (!text) return { project: xmasProject(), restored: false, broken: false };
  const r = importProject(text);
  return r.ok ? { project: r.project, restored: true, broken: false } : { project: xmasProject(), restored: false, broken: true };
}

function readRun(store: ReturnType<typeof browserStorage>): RunForm {
  try {
    const v = JSON.parse(readText(store, MK.run) ?? "null") as Partial<RunForm> | null;
    if (!v) return DEFAULT_RUN;
    const s = (x: unknown, d: string) => (typeof x === "string" && x.length < 50 ? x : d);
    return { from: s(v.from, DEFAULT_RUN.from), seed: s(v.seed, DEFAULT_RUN.seed), horizon: s(v.horizon, DEFAULT_RUN.horizon), deathAt: s(v.deathAt, DEFAULT_RUN.deathAt) };
  } catch {
    return DEFAULT_RUN;
  }
}

const num = (s: string, d: number, lo: number, hi: number) => {
  const n = Number(s);
  return s.trim() !== "" && Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : d;
};

/** The project without its nodes' positions: moving a node is no new run, lint or Python (n8n
 * saves positions in the file; they change nothing the engine checks or plays). */
function contentKey(p: Project): string {
  return canonical({ ...p, nodes: p.nodes.map((n) => ({ ...n, pos: null })) });
}


export default function MapsApp({ backendUrl, initialNode }: { backendUrl: string | null; initialNode: string | null }) {
  const router = useRouter();
  const [api] = useState<FlowsApi>(() => new FlowsApi(backendHttpBase(backendUrl)));
  const store = useMemo(() => browserStorage(), []);
  const [start] = useState(() => initialProject(store));
  const [project, setProjectState] = useState<Project>(start.project);
  const projectRef = useRef<Project>(start.project);
  const [world, setWorld] = useState<WorldSource>(() => (start.restored ? readChoice(store, KEYS.world, WORLDS, "local") : "local"));
  const worldRef = useRef(world);
  useEffect(() => {
    worldRef.current = world;
  }, [world]);
  const [catalogue, setCatalogue] = useState<CatalogueDoc | null>(null);
  const [engineErr, setEngineErr] = useState<string | null>(null);
  const [lint, setLint] = useState<{ doc: LintDoc; for: string } | null>(null);
  const [python, setPython] = useState<{ doc: PythonFiles; for: string } | null>(null);
  const [pythonErr, setPythonErr] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection>(() =>
    initialNode === RULES ? { kind: "rules" } : initialNode && nodeById(start.project, initialNode) ? { kind: "node", id: initialNode } : null,
  );
  // the selection follows the project: a deleted node is no longer selected
  const selected = selection?.kind === "node" && nodeById(project, selection.id) ? selection.id : null;
  const [side, setSideState] = useState<Side>(() => readChoice(store, MK.side, SIDES, "node"));
  const [panelOpen, setPanelOpen] = useState(() => readChoice(store, MK.panel, OPEN_CLOSED, "open") === "open");
  const [matOpen, setMatOpen] = useState(() => readChoice(store, MK.mat, OPEN_CLOSED, "open") === "open");
  const [bottom, setBottomState] = useState<Bottom>(() => readChoice(store, MK.bottom, BOTTOMS, "links"));
  const setBottom = useCallback(
    (b: Bottom) => {
      setBottomState(b);
      writeChoice(store, MK.bottom, b);
    },
    [store],
  );
  const [notice, setNotice] = useState<Notice | null>(
    start.broken ? { text: "Your saved project could not be opened, so the two-map sample is shown instead.", tone: "warn", undo: null } : null,
  );
  // Batt 2026-11-13 ("refactor fresh"): an old flow (IR 2) in this browser is not converted
  const [oldFlow, setOldFlow] = useState(() => !start.restored && hasOldFlow(store));
  const [runForm, setRunFormState] = useState<RunForm>(() => readRun(store));
  const [sim, setSim] = useState<Sim | null>(null);
  const [simBusy, setSimBusy] = useState(false);
  const [time, setTimeState] = useState(0);
  const timeRef = useRef(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<number>(4);
  const [zoom, setZoom] = useState(1);
  const [worldDoc, setWorldDoc] = useState<WorldDoc | null>(null);
  const [matChoice, setMatChoice] = useState<string | null>(null); // a map picked by hand (no run)
  const [menu, setMenu] = useState(false);
  const [adding, setAdding] = useState<string | null>(null); // "+ map": the map id typed
  const [addBusy, setAddBusy] = useState(false);
  const [codeFile, setCodeFile] = useState<string>("");
  const [copied, setCopied] = useState<"idle" | "ok" | "failed">("idle");
  const [zonesFor, setZonesFor] = useState<string | null>(null);
  // round 5 (Batt: "make it an option"): the map's other monsters as decoration; off by default
  const [decorOn, setDecorOn] = useState(() => readChoice(store, WANDER_KEY, ["on", "off"] as const, "off") === "on");
  const [graphFolded, setGraphFolded] = useState(false); // round 3: the map gets the height in a run
  const menuRef = useRef<HTMLDivElement | null>(null);
  const codeRef = useRef<HTMLPreElement | null>(null);
  const matRef = useRef<HTMLElement | null>(null);
  const [dialog, setDialog] = useState<FileDialog>(null);
  const [fileMeta, setFileState] = useState<FileMeta>(() => (start.restored ? readFileMeta(store, start.project) : newFileMeta(start.project)));
  const fileRef = useRef<FileMeta>(fileMeta);
  const setFile = useCallback((m: FileMeta) => {
    fileRef.current = m;
    setFileState(m);
  }, []);
  const scrollToMat = useRef(false); // a phone: after Simulate, the map (not the panel) comes into view
  const key = useMemo(() => contentKey(project), [project]);
  const maps = useMemo(() => mapNodes(project).map((n) => ({ id: n.id, map: n.map.map })), [project]);
  const graph = useMemo(() => mapsGraph(project), [project]);

  const setTime = useCallback((t: number) => {
    timeRef.current = t;
    setTimeState(t);
  }, []);
  const openPanel = useCallback(
    (s: Side) => {
      setSideState(s);
      writeChoice(store, MK.side, s);
      setPanelOpen(true);
      writeChoice(store, MK.panel, "open");
    },
    [store],
  );
  const setRunForm = (f: RunForm) => {
    setRunFormState(f);
    writeChoice(store, MK.run, JSON.stringify(f));
  };

  // --- the project (shared with /flows through this browser's storage) -----------------------------
  const flush = useCallback(() => {
    writeProjectText(store, JSON.stringify(projectRef.current));
    writeChoice(store, KEYS.world, worldRef.current);
    writeFileMeta(store, fileRef.current, projectRef.current);
  }, [store]);
  const replace = useCallback(
    (p: Project, opts: { notice?: string; undo?: boolean; world?: WorldSource; keepView?: boolean } = {}) => {
      const prev = { project: projectRef.current, world: worldRef.current };
      projectRef.current = p;
      setProjectState(p);
      if (!opts.keepView) {
        setSim(null);
        setSelection(null);
        setPlaying(false);
        setTime(0);
        setMatChoice(null);
      }
      if (opts.world) setWorld(opts.world);
      if (opts.notice) setNotice({ text: opts.notice, tone: "ok", undo: opts.undo ? prev : null });
    },
    [setTime],
  );
  /** An edit of the project: the unknown-map rule's maps follow (rules.ts), an error is said. */
  const edit = useCallback(
    (r: Edit | { ok: true; project: Project } | { ok: false; error: string }, notice?: string) => {
      if (r.ok) replace(refreshRule(r.project), { keepView: true, ...(notice ? { notice, undo: true } : {}) });
      else setNotice({ text: r.error, tone: "error", undo: null });
    },
    [replace],
  );
  useEffect(() => {
    const t = setTimeout(flush, SAVE_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [project, world, flush]);
  useEffect(() => flush, [flush]); // leaving the page: the latest project is kept for /flows
  useEffect(() => {
    if (!notice || notice.tone === "error") return;
    const t = setTimeout(() => setNotice(null), NOTICE_MS);
    return () => clearTimeout(t);
  }, [notice]);
  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenu(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setMenu(false); // matpilot 15: Escape closes Load
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [menu]);

  // --- the engine: catalogue (the credentials' names), lint, the Python, the static data -----------
  useEffect(() => {
    api
      .catalogue(project.target.client)
      .then((c) => (setCatalogue(c), setEngineErr(null)))
      .catch((e) => setEngineErr(e instanceof ApiError ? e.reason : String(e)));
  }, [api, project.target.client]);
  useEffect(() => {
    const t = setTimeout(() => {
      const p = projectRef.current;
      api
        .lint(p, world)
        .then((doc) => setLint({ doc, for: contentKey(p) }))
        .catch(() => undefined); // the lint chip keeps "…"; /flows shows lint in full
    }, LINT_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [key, world, api]);
  useEffect(() => {
    let alive = true;
    const t = setTimeout(() => {
      const p = projectRef.current;
      api
        .python(p)
        .then((doc) => alive && (setPython({ doc, for: contentKey(p) }), setPythonErr(null)))
        .catch((e) => alive && setPythonErr(e instanceof ApiError ? e.reason : "the Python view is unavailable"));
    }, PYTHON_DEBOUNCE_MS);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [key, api]);
  // every map of the project and of the last run, with their walk grids (one request a change)
  const mapNames = useMemo(() => [...new Set([...maps.map((b) => b.map), ...(sim?.tl.maps ?? []), ...(matChoice ? [matChoice] : [])])].filter((m) => MAP_ID.test(m)).sort().slice(0, 20), [maps, sim, matChoice]);
  const mapsKey = mapNames.join(",");
  useEffect(() => {
    if (!mapsKey) return;
    let alive = true;
    api
      .world(world, project.target.server, mapsKey.split(","), true)
      .then((w) => alive && setWorldDoc(w))
      .catch(() => alive && setWorldDoc(null));
    return () => {
      alive = false;
    };
  }, [api, world, project.target.server, mapsKey]);
  const labels: Labels | null = useMemo(() => {
    if (!worldDoc) return null;
    const pick = <T,>(o: Record<string, T>, f: (v: T) => string | null) => Object.fromEntries(Object.entries(o).flatMap(([k, v]) => (f(v) ? [[k, f(v) as string]] : [])));
    return { mobs: pick(worldDoc.mobs, (m) => m.label), items: pick(worldDoc.items, (i) => i.label), npcs: worldDoc.labels?.npcs ?? {}, options: worldDoc.labels?.options ?? {} };
  }, [worldDoc]);

  // --- simulate and play back ---------------------------------------------------------------------
  /** `from`: a map node's id, else ("" or a session node) the project's start (its login node). */
  const simulate = async (from: string) => {
    const p = projectRef.current;
    const fromMap = mapNodes(p).some((n) => n.id === from) ? from : "";
    const form = { ...runForm, from: fromMap };
    setRunForm(form);
    const seed = Math.round(num(form.seed, 1, 0, 2 ** 31 - 1));
    const death = form.deathAt.trim() === "" ? null : num(form.deathAt, 200, 0, 3600);
    const base: Scenario = {
      horizon_s: num(form.horizon, 120, 1, 3600),
      start_block: fromMap || null,
      single_block: false,
      timeline: death === null ? [] : [{ t: death, set: { is_dead: true, hp_percent: 0 } }],
    };
    setSimBusy(true);
    setPlaying(false);
    try {
      let old = false;
      let doc: SimDoc;
      try {
        doc = await api.simulate(p, world, { ...base, encounters: true, seed });
      } catch (e) {
        // an older backend (before 2026-11-10) refuses the two new scenario fields: run without
        if (!(e instanceof ApiError && e.reason === "invalid_scenario" && e.errors.some((x) => /encounters|seed/.test(x)))) throw e;
        old = true;
        doc = await api.simulate(p, world, base);
      }
      // TODO(engine): the trace's own session steps (play kinds "login" / "character") replace this
      // MOCK timeline as soon as the backend names them (play.ts traceHasSession); until then the
      // login and character nodes are played as lib/maps/session.ts's fixed mock steps.
      const mock = fromMap || mapStartOf(p) ? null : sessionSteps(sessionOf(p)); // a map START has no session
      const tl = buildTimeline(doc.trace, mock);
      setSim({ doc, for: contentKey(p), tl, seed: old ? null : seed, old: old || !Array.isArray(doc.trace.play), mock: tl.offset > 0 });
      setLint({ doc: doc.lint, for: contentKey(p) });
      setMatChoice(null);
      setTime(0);
      setPlaying(true);
      setBottom("map"); // the run plays on the map view
      if (!matOpen) {
        setMatOpen(true);
        writeChoice(store, MK.mat, "open");
      }
      openPanel("run");
      const narrow = typeof window !== "undefined" && Boolean(window.matchMedia?.("(max-width: 48rem)").matches);
      scrollToMat.current = narrow; // a phone: bring the map into view
      if (!narrow) setGraphFolded(true); // a wide screen: the map gets the graph's height ("Show the graph" brings it back)
    } catch (e) {
      setNotice({ text: `Simulate failed: ${e instanceof ApiError ? e.message : String(e)}`, tone: "error", undo: null });
    } finally {
      setSimBusy(false);
    }
  };
  const tl = sim?.tl ?? null;
  const end = tl?.end ?? 0;
  useEffect(() => {
    if (!scrollToMat.current || !sim || !matOpen) return;
    scrollToMat.current = false;
    matRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [sim, matOpen]);
  useEffect(() => {
    if (!playing || !tl) return;
    let last = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const next = Math.min(end, timeRef.current + ((now - last) / 1000) * speed);
      last = now;
      setTime(next);
      if (next >= end) setPlaying(false);
      else frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, tl, end, setTime]);
  const pose = tl ? poseAt(tl, time) : null;
  const current = tl ? Math.max(0, beatAt(tl, time)) : -1;
  const beat = tl && current >= 0 ? tl.beats[current] : null;
  const activeNode = playing || time > 0 ? pose?.node || null : null;
  const activeEdge = useMemo(() => (tl && (playing || time > 0) ? activeEdgeAt(tl, current, graph.edges) : null), [tl, current, playing, time, graph]);
  const seek = useCallback(
    (t: number) => {
      setPlaying(false);
      setMatChoice(null); // the view follows the character to that time
      setTime(Math.max(0, Math.min(end, t)));
    },
    [end, setTime],
  );
  /** To the next step's start, or back to the start of the one before. */
  const step = useCallback(
    (dir: -1 | 1) => {
      if (!tl) return;
      const t = timeRef.current;
      if (dir > 0) {
        const next = tl.beats.find((b) => b.t0 > t + 1e-6);
        seek(next ? next.t0 : end);
      } else {
        const before = [...tl.beats].reverse().find((b) => b.t0 < t - 1e-6);
        seek(before ? before.t0 : 0);
      }
    },
    [tl, end, seek],
  );

  // the map the view shows: the character's during a run, else the one picked, else the selection's
  const selectedNode = selected ? nodeById(project, selected) : undefined;
  const selectedMap = selectedNode?.kind === "map" ? selectedNode : undefined;
  const startMap = sessionPath(project).map;
  const matMap = (playing ? pose?.map : null) || matChoice || (tl ? pose?.map : null) || selectedMap?.map.map || tl?.maps[0] || startMap?.map.map || null;
  const sheet: WorldMap | null = matMap ? (worldDoc?.maps[matMap] ?? null) : null;
  const rows = matMap ? (worldDoc?.walk?.[matMap] ?? null) : null;
  const simStale = sim !== null && sim.for !== key;
  const folded = matOpen && graphFolded && tl !== null; // the graph folds only while a run is shown

  // --- load, save, add a map ---------------------------------------------------------------------
  const openReady = (r: (typeof READY)[number]) => {
    setMenu(false);
    // matpilot round 15 #4: a Load replaces the project open now; say so before (Undo brings it back)
    if (!window.confirm(`Open the ready-made project ${r.title}? It replaces the project open now (${projectRef.current.name}): Save that first if you want to keep a copy; Undo, right after, brings it back.`)) return;
    replace(r.make(), { world: r.world, undo: true, notice: `Opened the ready-made project ${r.title}; the one before is back with Undo.` });
  };
  // Save and Load: the SAME dialogs as /flows (Batt 2026-11-13: "/maps is the project's save; save
  // and load on /flows call the same"): on this computer or on GitHub, one file format
  const onOpened = (o: Opened) => {
    setDialog(null);
    replace(o.project, { undo: true, notice: `${o.notice} The one before comes back with Undo.` });
    setFile(o.meta);
  };
  const pythonText = useCallback((d: PythonFiles) => d.files.map((f) => `# --- ${f.path}\n${f.text}`).join("\n"), []);
  const pythonCached = useCallback((p: Project) => (python && python.for === contentKey(p) ? pythonText(python.doc) : null), [python, pythonText]);
  const pythonFor = useCallback(
    (p: Project): Promise<string> => {
      const have = pythonCached(p);
      return have !== null ? Promise.resolve(have) : api.python(p).then((r) => pythonText(r), () => "");
    },
    [api, pythonCached, pythonText],
  );
  const getProject = useCallback(() => projectRef.current, []);
  useFileShortcuts(
    (d) => {
      setMenu(false);
      setDialog(d);
    },
    dialog,
    !zonesFor,
  );
  const facts = async (map: string): Promise<{ facts: MapFacts | null; why: string }> => {
    try {
      const w = await api.world(worldRef.current, projectRef.current.target.server, [map], true);
      const m = w.maps[map];
      if (!m) return { facts: null, why: `the ${worldRef.current === "local" ? "lab data" : "sample sheets"} have no sheet for ${map}` };
      const r = w.walk?.[map] ?? null;
      return { facts: { rows: r, spawns: m.spawns }, why: r ? "" : `no walk grid for ${map} in the static data (the backend's GAT mount): the entry is "anywhere"` };
    } catch (e) {
      return { facts: null, why: `the static data could not be read (${e instanceof ApiError ? e.reason : String(e)})` };
    }
  };
  const addMap = async () => {
    if (adding === null) return;
    const map = adding.trim();
    if (!MAP_ID.test(map)) return setNotice({ text: `${JSON.stringify(map)} is not a map id`, tone: "error", undo: null });
    // matpilot round 15 #11: a second node of the same map makes "which node does a wing land on?"
    // a question; say so before
    const same = projectRef.current.nodes.filter((n) => n.kind === "map" && n.map.map === map).map((n) => n.id);
    if (same.length && !window.confirm(`The project has a node of ${map} already (${same.join(", ")}). Add a second one? A warp or a wing to ${map} lands on the one its exit names; a death respawns on the first.`)) return;
    setAddBusy(true);
    const got = await facts(map);
    setAddBusy(false);
    const r = addMapNode(projectRef.current, map, got.facts);
    if (!r.ok) return setNotice({ text: r.error, tone: "error", undo: null });
    replace(refreshRule(r.project), { keepView: true });
    setSelection({ kind: "node", id: r.id });
    const n = nodeById(r.project, r.id);
    const at = n?.kind === "map" ? n.entries[0].at : null;
    const guess = [
      at ? `the entry (${at.x}, ${at.y}) is the walkable cell nearest the centre` : "the entry is anywhere (no walk grid)",
      n?.kind === "map" && n.targets.length ? `targets ${n.targets.map((m) => m.id).join(", ")}` : "no targets (no spawns in the static data)",
    ].join("; ");
    setNotice({ text: `Added the map node ${r.id}: ${guess}: a first guess, change it in the inspector.${got.why ? ` Note: ${got.why}.` : ""} Draw an exit from a map's + port onto it.`, tone: "ok", undo: null });
    setAdding(null);
  };
  const openFlow = useCallback(
    (id: string) => {
      flush();
      router.push(`/flows?node=${encodeURIComponent(id)}`);
    },
    [flush, router],
  );
  const simulateRef = useRef<((from: string) => Promise<void>) | null>(null);
  useEffect(() => {
    simulateRef.current = simulate;
  });
  const simulateFrom = useCallback((id: string) => void simulateRef.current?.(id), []);
  const onConnectSession = useCallback((from: string, to: string, entry?: string) => edit(connectSession(projectRef.current, from, to, entry)), [edit]);
  const onSetStart = useCallback((id: string) => edit(setStart(projectRef.current, id), `START is ${id} now: the run starts there, where a person puts her.`), [edit]);
  const onDeleteSession = useCallback((from: string, to: string) => edit(removeSession(projectRef.current, from, to), `Deleted the connection ${from} → ${to}.`), [edit]);
  const onConnectExit = useCallback((from: string, kind: AuthoredExit, to: string) => edit(connectExit(projectRef.current, from, kind, to)), [edit]);
  const onRetargetExit = useCallback((path: string, to: string, entry?: string) => edit(retargetExit(projectRef.current, path, to, entry)), [edit]);
  const onDeleteExit = useCallback((path: string) => edit(removeExit(projectRef.current, path), "Deleted the exit (its take_exit statement)."), [edit]);
  const onMove = useCallback((p: Record<string, XY>) => replace(moveNodes(projectRef.current, p), { keepView: true }), [replace]);
  const onSelect = useCallback(
    (id: string | null) => {
      setSelection(id ? { kind: "node", id } : null);
      if (id) openPanel("node");
      // a map node clicked while nothing plays: the view shows its map
      const n = id ? nodeById(projectRef.current, id) : undefined;
      if (n?.kind === "map" && !playing) setMatChoice(n.map.map);
    },
    [openPanel, playing],
  );
  const onRules = useCallback(() => {
    setSelection({ kind: "rules" });
    openPanel("node");
  }, [openPanel]);
  // matpilot round 16 #7: the lint chip opens the list of every finding it counts (on a phone the
  // panel is under the graph: it is brought into view)
  const sideRef = useRef<HTMLElement | null>(null);
  const onLint = useCallback(() => {
    setSelection({ kind: "lint" });
    openPanel("node");
    requestAnimationFrame(() => sideRef.current?.scrollIntoView({ block: "nearest" }));
  }, [openPanel]);
  // the Python pane: the selected node's files (else every file), and the project's JSON
  const files = python?.doc.files ?? [];
  const shown = selected && files.some((f) => f.node === selected) ? files.filter((f) => f.node === selected) : files;
  const jsonName = `${project.name}${PROJECT_FILE}`;
  const file = shown.find((f) => f.path === codeFile) ?? (codeFile === jsonName ? null : shown[0]) ?? null;
  const codeText = file ? file.text : codeFile === jsonName || !shown.length ? exportProject(project) : "";
  const copy = () => {
    void (navigator.clipboard?.writeText(codeText) ?? Promise.reject(new Error("no clipboard"))).then(
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

  // --- words --------------------------------------------------------------------------------------
  const lintDoc = lint?.doc ?? null;
  const total = lintDoc ? lintLine(lintDoc.counts) : null;
  const projectLint = lintGroups(lintDoc, project).find((g) => g.node === null) ?? null; // on no node: no card shows it
  const session = sessionOf(project);
  const problems = sessionProblems(session, project.target.server);
  const sp = sessionPath(project);
  // --- RUN: the project from START, box by box (the live block player) ----------------------------
  const sm = mapStartOf(project);
  const startReady = sm ? liveReady(project, sm.id, catalogue?.blocks ?? null) : null;
  const smRunner = sm && runnerBlockOn(sm) ? runnerForMap(sm.map.map) : null;
  const runnable = !!sm && startReady?.ready === true && (!runnerBlockOn(sm) || (!!smRunner && LIVE_FLOWS.includes(smRunner.id)));
  const keysR = runnable && sm && smRunner ? runnerKeysOn(project, sm.id) : null;
  // matpilot round 16 #4: a lint ERROR blocks Run (the Run route refuses it too: lint_errors)
  const lintErr = lintDoc && lintDoc.counts.error > 0 ? (lintDoc.findings.find((f) => f.severity === "error")?.message ?? "") : null;
  const runBlocked = keysR && !keysR.ok ? `the keys: ${keysR.problems.join("; ")}` : lintErr !== null ? `the lint has ${lintDoc?.counts.error} error(s): ${lintErr}` : null;
  const notRunWhy = !sm
    ? "login is not live yet: put START on a map node (drag START's connection onto a map, or “Start here” in a map node's inspector); the run then starts where a person put her"
    : runnerBlockOn(sm) && !smRunner
      ? `"hunt with the runner" plays only a map that has a runner (today xmas_dun02), not ${sm.map.map}`
      : startReady && !startReady.ready
        ? startReady.why
        : "Run is not available now";
  const projectRun = runnable && sm ? { project, node: sm.id } : null; // the hook keeps the latest in a ref
  const live = useLiveRun(backendUrl, PROJECT_FLOW, runnable, null, projectRun);
  const liveActive = ACTIVE.includes(live.st?.state ?? "");
  const liveText = liveActive ? liveLine(live.st?.live, live.st?.flows?.[PROJECT_FLOW]?.minutes ?? null) : null;
  const checks: Check[] = useMemo(() => (sim ? runChecks(sim.tl, sim.doc.trace, maps, END_TEXT[sim.doc.trace.end] ?? sim.doc.trace.end, sim.seed) : []), [sim, maps]);
  const status = engineErr
    ? `The flow engine is not reachable (${engineErr}): the graph works, Simulate does not.`
    : simBusy
      ? "Simulating…"
      : tl && beat
        ? `${playing ? "Playing" : "Paused"} at ${time.toFixed(1)} s of ${end.toFixed(1)} s · ${beat.node && beat.kind !== "session" ? `${beat.node}: ` : ""}${beatText(beat, labels)}`
        : sm
          ? `Ready. Simulate plays the project from START (${sm.id}) without the game; Run (amber) plays it in the game from there, box by box.`
          : "Ready. Press Simulate to watch the bot log in, choose its character and walk its maps (simulated: nothing runs in the game).";
  const zonesNode = zonesFor ? nodeById(project, zonesFor) : undefined;
  const zonesMap = zonesNode?.kind === "map" ? zonesNode : undefined;
  const loginNode = sp.login ?? undefined;
  const charNode = sp.character ?? undefined;
  const lg = loginOf(loginNode);



  return (
    <main className="studio maps-page" data-run={tl ? "true" : "false"} data-testid="maps-app">
      <header className="studio-bar">
        <div className="studio-brand">
          <span className="studio-home">Maps</span>
          <span className="status-pill" title={runnable ? "Simulate plays the project without the game; Run (amber) plays it in the game from START" : `Simulate plays the project without the game; Run: ${notRunWhy}`}>
            {runnable ? "SIMULATE · RUN" : "SIMULATE · RUN not ready"}
          </span>
          <h1 className="studio-title" title={project.name}>
            {project.name}
          </h1>
        </div>
        <div className="studio-actions">
          <div className="studio-menu" ref={menuRef}>
            <button type="button" className="button button-small button-file" onClick={() => setMenu(!menu)} aria-expanded={menu} aria-label="Load a project" title="Open a project" data-testid="maps-load">
              <FolderIcon />
              <span className="button-text">Load</span>
              <CaretIcon />
            </button>
            {menu && (
              <div className="studio-menu-list" role="menu">
                {READY.map((r) => (
                  <button key={r.id} type="button" role="menuitem" className="studio-menu-item" onClick={() => openReady(r)} data-testid={`maps-load-${r.id}`}>
                    {r.title}
                    <small>{r.words}</small>
                  </button>
                ))}
                <button type="button" role="menuitem" className="studio-menu-item" onClick={() => (setMenu(false), setDialog("load"))} data-testid="maps-load-saved">
                  Open a saved project…<small>from this computer or from GitHub (checked before it opens; Ctrl+O)</small>
                </button>
                <p className="studio-menu-note muted">Old flows (the format before projects) are not converted.</p>
              </div>
            )}
          </div>
          <button type="button" className="button button-small button-file" onClick={() => (setMenu(false), setDialog("save"))} aria-label="Save the project" title="Save the project: on this computer or on GitHub (Ctrl+S)" data-testid="maps-save">
            <SaveIcon />
            <span className="button-text">Save</span>
          </button>
          <button
            type="button"
            className="button button-primary button-run"
            onClick={() => void simulate(maps.some((b) => b.id === runForm.from) ? runForm.from : "")}
            disabled={simBusy}
            title="Run it in the simulator: no game, no input"
            data-testid="maps-simulate"
          >
            <PlayIcon />
            <span className="button-text">{simBusy ? "Simulating…" : "Simulate"}</span>
          </button>
          {runnable ? <LiveRunButtons live={live} blocked={runBlocked} /> : <RunNotReady why={notRunWhy} />}
        </div>
      </header>

      {(notice || graph.notes.length > 0 || copied === "failed" || oldFlow || (runnable && (liveActive || live.err || live.st?.flow === PROJECT_FLOW))) && (
        <div className="studio-notices">
          {runnable && (liveActive || live.st?.flow === PROJECT_FLOW) && (
            <p className="notice notice-ok" role="status" data-testid="maps-live">
              <strong>Run in the game</strong> · {liveLabel(live.st)}
              {liveText ? <span className="live-line"> · {liveText}</span> : null}
              {!liveActive && live.st?.detail ? ` · ${live.st.detail}` : ""}
            </p>
          )}
          {runnable && live.err && (
            <p className="notice notice-warn" role="status" data-testid="maps-live-error">
              {live.err}
            </p>
          )}
          {oldFlow && (
            <p className="notice notice-warn notice-actions" data-testid="maps-old-format">
              <span>The flow format changed: old flows are not converted. This browser&apos;s old flow stays where it was; open a ready-made project:</span>
              {READY.map((r) => (
                <button key={r.id} type="button" className="button button-small" onClick={() => (setOldFlow(false), openReady(r))}>
                  {r.title}
                </button>
              ))}
              <button type="button" className="icon-button" onClick={() => setOldFlow(false)} title="Hide" aria-label="Hide">
                <CloseIcon />
              </button>
            </p>
          )}
          {notice && (
            <p className={`notice notice-${notice.tone} notice-actions`} role={notice.tone === "error" ? "alert" : "status"} data-testid="maps-notice">
              <span>{notice.text}</span>
              {notice.undo && (
                <button
                  type="button"
                  className="button button-small"
                  onClick={() => {
                    const u = notice.undo;
                    setNotice(null);
                    if (u) replace(u.project, { world: u.world });
                  }}
                >
                  Undo
                </button>
              )}
              <button type="button" className="icon-button" onClick={() => setNotice(null)} title="Hide" aria-label="Hide">
                <CloseIcon />
              </button>
            </p>
          )}
          {copied === "failed" && <p className="notice notice-warn">This browser would not copy automatically (the page is not a secure origin). The code is selected: press Ctrl+C (⌘C).</p>}
          {graph.notes.map((n) => (
            <p key={n} className="notice notice-warn">
              {n}
            </p>
          ))}
        </div>
      )}

      <div className="device-bar" aria-label="The run">
        {sm ? (
          <button type="button" className="device-chip mp-chip" onClick={() => onSelect(sm.id)} title="START: the run starts on this map node, where a person put her (no login, no character)" data-testid="maps-start-chip">
            <span className="device-label">start</span>
            <span className="device-value">{sm.id} (she stands there)</span>
          </button>
        ) : (
          <>
            <button type="button" className="device-chip mp-chip" onClick={() => loginNode && onSelect(loginNode.id)} disabled={!loginNode} title="The login node: a server and a credential by name (simulated)">
              <span className="device-label">login</span>
              <span className="device-value">{lg.credential ? `${lg.credential}${credentialOf(lg.credential) ? "" : " (?)"}` : "not set"}</span>
            </button>
            <button type="button" className="device-chip mp-chip" onClick={() => charNode && onSelect(charNode.id)} disabled={!charNode} title="The choose-character node (simulated)">
              <span className="device-label">character</span>
              <span className="device-value">{charNode ? slotText(characterOf(charNode)) : "not connected"}</span>
            </button>
          </>
        )}
        <label className="device-chip">
          <span className="device-label">static data</span>
          <select value={world} onChange={(e) => setWorld(e.target.value as WorldSource)} data-testid="maps-world">
            <option value="local">lab data/kb</option>
            <option value="sample">sample sheets</option>
          </select>
        </label>
        <div className="device-chip">
          <span className="device-label">maps</span>
          <span className="device-value">{maps.length}</span>
        </div>
        {/* matpilot round 16 #7: the chip counts every finding, the cards a node's: it opens the list of all */}
        <button
          type="button"
          className="device-chip mp-chip"
          data-level={total?.level}
          onClick={onLint}
          disabled={!lintDoc}
          aria-pressed={selection?.kind === "lint" && panelOpen && side === "node"}
          title="Every finding the lint counts, the project's own (on no node) and each node's: open the list"
          data-testid="maps-lint-chip"
        >
          <span className="device-label">lint</span>
          <span className="device-value">{total ? `${total.text}${lint && lint.for !== key ? " (checking…)" : ""}` : "…"}</span>
        </button>
        {!sm && problems.length > 0 && (
          <div className="device-chip" data-level="warning" title={problems.join(" · ")}>
            {problems[0]}
          </div>
        )}
      </div>

      <div className="maps-body" data-panel={panelOpen ? "open" : "closed"}>
        <div className="maps-stage" data-mat={matOpen ? "open" : "closed"} data-graph={folded ? "folded" : "open"} data-bottom={matOpen ? bottom : "none"}>
          <section className="maps-graph" aria-label="The project's nodes and how they link">
            <div className="maps-toolbar">
              {folded ? (
                <>
                  <button type="button" className="block-tab-add" onClick={() => setGraphFolded(false)} aria-expanded={false} data-testid="maps-graph-show">
                    Show the graph
                  </button>
                  <span className="maps-hint">
                    The graph is folded while the run plays{activeNode ? " · now: " : ""}
                    {activeNode && <span className="maps-now">{nodeWords(project, activeNode)}</span>}
                  </span>
                </>
              ) : adding !== null ? (
                <form
                  className="maps-add"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void addMap();
                  }}
                >
                  <label>
                    map id <input value={adding} onChange={(e) => setAdding(e.target.value)} list="maps-known" maxLength={40} autoFocus data-testid="maps-add-id" />
                  </label>
                  <button type="submit" className="button button-small button-primary" disabled={addBusy}>
                    {addBusy ? "Reading…" : "Add"}
                  </button>
                  <button type="button" className="button button-small" onClick={() => setAdding(null)}>
                    Cancel
                  </button>
                </form>
              ) : (
                <button type="button" className="block-tab-add" onClick={() => setAdding("")} title="Place a map node from the static data" data-testid="maps-add">
                  + map
                </button>
              )}
              {!folded && tl && matOpen && (
                <button type="button" className="block-tab-add" onClick={() => setGraphFolded(true)} aria-expanded={true} title="Fold the graph: the map gets the height" data-testid="maps-graph-fold">
                  Fold the graph
                </button>
              )}
              {!folded && adding === null && (
                <span className="maps-hint">Drag from a port to connect (START&apos;s connection onto a map: the run starts there; login → character → a map&apos;s entry; a map&apos;s + port onto another map: an exit); click a node to inspect it; double-click a node to open its tabs on /flows.</span>
              )}
            </div>
            <datalist id="maps-known">
              {[...new Set([...(world === "sample" ? EXAMPLE_MAPS : []), ...(lintDoc?.world.maps ?? []), ...maps.map((b) => b.map)])].sort().map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
            <div className="maps-graph-canvas">
              <MapsCanvas
                project={project}
                lint={lintDoc}
                trace={sim && !simStale ? sim.doc.trace : null}
                selected={selected}
                activeNode={activeNode}
                activeEdge={activeEdge}
                onSelect={onSelect}
                onMove={onMove}
                onConnectSession={onConnectSession}
                onSetStart={onSetStart}
                onDeleteSession={onDeleteSession}
                onConnectExit={onConnectExit}
                onRetargetExit={onRetargetExit}
                onDeleteExit={onDeleteExit}
                onOpen={openFlow}
                onSimulateFrom={simulateFrom}
                onRules={onRules}
              />
            </div>
          </section>
          {matOpen && (
            <section className="maps-mat" aria-label="Under the graph: the links or the map view" ref={matRef} data-bottom={bottom}>
              <div className="maps-bottom-tabs segmented" role="group" aria-label="Under the graph">
                <button type="button" aria-pressed={bottom === "links"} className="segmented-option" onClick={() => setBottom("links")} data-testid="maps-bottom-links">
                  Links
                </button>
                <button type="button" aria-pressed={bottom === "map"} className="segmented-option" onClick={() => setBottom("map")} data-testid="maps-bottom-map">
                  Map view
                </button>
                <span className="maps-hint">{bottom === "links" ? (selectedMap ? `how ${selectedMap.map.map} links: its entries and exits` : "every link of the project; click a map for its own") : "the walk grid and the simulation"}</span>
              </div>
              {bottom === "links" ? (
                <LinksPanel project={project} node={selectedMap?.id ?? null} onSelect={onSelect} onOpen={openFlow} onRules={onRules} />
              ) : (
                <>
                  <div className="maps-mat-bar">
                    <label className="device-chip">
                      <span className="device-label">map</span>
                      <select
                        value={matMap ?? ""}
                        onChange={(e) => {
                          setMatChoice(e.target.value || null);
                          if (tl) setPlaying(false);
                        }}
                        disabled={Boolean(tl && playing)}
                        data-testid="maps-mat-map"
                      >
                        {!matMap && <option value="">no map</option>}
                        {mapNames.map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))}
                      </select>
                    </label>
                    <span className="maps-mat-what">
                      {tl ? (sim?.old ? "approximate (an older backend)" : "a simulation") : "the map before a run: press Simulate"}
                      {matMap && !rows ? " · no walk grid here (positions are estimates)" : ""}
                    </span>
                    <div className="segmented" role="group" aria-label="Zoom">
                      {[1, 2, 4].map((z) => (
                        <button key={z} type="button" className="segmented-option" aria-pressed={zoom === z} onClick={() => setZoom(z)}>
                          {z === 1 ? "fit" : `${z}×`}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="maps-mat-stage">
                    <MatView map={matMap} rows={rows} sheet={sheet} tl={tl} time={time} labels={labels} savePoint={sim?.doc.trace.save_point ?? null} zoom={zoom} decorSeed={decorOn ? (sim?.seed ?? Math.round(num(runForm.seed, 1, 0, 2 ** 31 - 1))) : null}>
                      {tl && beat?.session && (time < tl.offset || beat.kind === "session") && (
                        // the first seconds: the session's steps, before the character is on a map
                        // (round 3: over the map itself, one or two lines on a phone; the step list
                        // has the details)
                        <p className="mat-overlay" role="status" data-testid="mat-session">
                          <strong>{beat.session.step === "start" ? "Starting the client…" : beat.session.step === "login" ? `Logging in…${sim?.mock ? " (a mock)" : " (simulated)"}` : `Entering the game…${sim?.mock ? " (a mock)" : " (simulated)"}`}</strong>{" "}
                          <span>
                            the character appears on {sim?.doc.trace.start.map ?? "the first map"}
                            {sim?.doc.trace.start.cell ? ` (${sim.doc.trace.start.cell[0]}, ${sim.doc.trace.start.cell[1]})` : ""} in {Math.max(0, Math.ceil(arrival(tl) - time))} s
                          </span>{" "}
                          <span className="mat-overlay-detail">{beat.session.text}.</span>
                        </p>
                      )}
                    </MatView>
                    {tl && (
                      <PlaybackBar
                        time={time}
                        end={end}
                        playing={playing}
                        speed={speed}
                        onPlay={() => {
                          if (timeRef.current >= end) setTime(0);
                          setMatChoice(null);
                          setPlaying(true);
                        }}
                        onPause={() => setPlaying(false)}
                        onSeek={seek}
                        onSpeed={(s) => setSpeed(SPEEDS.includes(s as (typeof SPEEDS)[number]) ? s : 4)}
                        onStep={step}
                        onReset={() => {
                          setPlaying(false);
                          setTime(0);
                        }}
                      />
                    )}
                  </div>
                  <ul className="maps-legend" aria-label="What the map shows">
                    <li>
                      <label className="maps-decor-toggle" title="Decoration only: the map's spawns from the static data, wandering from the run's seed. Never engaged, never in the steps, the checks or the Python.">
                        <input
                          type="checkbox"
                          checked={decorOn}
                          onChange={(e) => {
                            setDecorOn(e.target.checked);
                            writeChoice(store, WANDER_KEY, e.target.checked ? "on" : "off");
                          }}
                          data-testid="maps-decor"
                        />
                        {/* matpilot round 5: the dot lives in the label, so the legend's height never
                            changes with the box (a separate key wrapped the phone legend, -6 % map) */}
                        <span className="maps-decor-dot" aria-hidden="true" />
                        Show the map&apos;s other monsters (decoration)
                      </label>
                    </li>
                    <li data-k="bot">the character</li>
                    <li data-k="trail">walked</li>
                    <li data-k="route">walking next</li>
                    <li data-k="monster">a monster met</li>
                    <li data-k="npc">an NPC</li>
                    <li data-k="warp">a warp</li>
                    <li data-k="save">the save point</li>
                  </ul>
                </>
              )}
            </section>
          )}
        </div>

        {panelOpen && (
          <aside className="maps-side" aria-label="The node, the simulation and the Python" ref={sideRef}>
            <div className="maps-side-tabs">
              <div className="segmented" role="group" aria-label="Panel">
                {SIDES.map((s) => (
                  <button key={s} type="button" className="segmented-option" aria-pressed={side === s} onClick={() => openPanel(s)} data-testid={`maps-side-${s}`}>
                    {/* matpilot 4: nothing on this page is named Run (it never runs): the pane is the Simulation */}
                    {s === "node" ? "Node" : s === "run" ? "Simulation" : "Python"}
                  </button>
                ))}
              </div>
              <button type="button" className="icon-button" onClick={() => (setPanelOpen(false), writeChoice(store, MK.panel, "closed"))} title="Close the panel" aria-label="Close the panel">
                <CloseIcon />
              </button>
            </div>
            <div className="maps-side-body">
              {side === "node" && (
                <>
                  {selection === null && <Intro own={projectLint} onLint={onLint} />}
                  {selection?.kind === "rules" && <RulesPanel project={project} onEdit={(r) => edit(r)} onOpen={openFlow} />}
                  {selection?.kind === "lint" && <LintList lint={lintDoc} project={project} stale={Boolean(lint && lint.for !== key)} onSelect={onSelect} />}
                  {selected && (
                    <NodeInspector
                      project={project}
                      nodeId={selected}
                      lint={lintDoc}
                      onStart={onSetStart}
                      onChange={(p) => {
                        // a node deleted in the inspector: said, with Undo (a rename keeps the count)
                        const gone = p.nodes.length < projectRef.current.nodes.length ? selected : null;
                        replace(refreshRule(p), { keepView: true, ...(gone ? { notice: `Deleted the map node ${gone} and its connections.`, undo: true } : {}) });
                      }}
                      onOpen={openFlow}
                      credentials={catalogue?.credentials}
                      onZones={setZonesFor}
                      onSimulate={(id) => void simulate(id)}
                      onRules={onRules}
                      onRenamed={(from, to) => {
                        setSelection({ kind: "node", id: to });
                        if (runForm.from === from) setRunForm({ ...runForm, from: to });
                      }}
                    />
                  )}
                </>
              )}
              {side === "run" && (
                <RunPanel
                  form={runForm}
                  setForm={setRunForm}
                  starts={maps}
                  busy={simBusy}
                  onRun={() => void simulate(maps.some((b) => b.id === runForm.from) ? runForm.from : "")}
                  result={sim ? { tl: sim.tl, checks, endText: END_TEXT[sim.doc.trace.end] ?? sim.doc.trace.end, notes: sim.doc.trace.notes, old: sim.old, stale: simStale } : null}
                  current={current}
                  labels={labels}
                  onSeek={seek}
                />
              )}
              {side === "python" && (
                <div className="maps-python">
                  <div className="python-files" role="tablist" aria-label="Files">
                    {shown.map((f) => (
                      <button key={f.path} type="button" role="tab" className="python-file" aria-selected={file?.path === f.path} onClick={() => setCodeFile(f.path)} title={f.path} data-testid={`maps-file-${f.path}`}>
                        {f.path}
                      </button>
                    ))}
                    <button type="button" role="tab" className="python-file" aria-selected={file === null} onClick={() => setCodeFile(jsonName)} data-testid="maps-file-json">
                      {jsonName}
                    </button>
                    <button type="button" className="button button-small" onClick={copy} disabled={codeText === ""}>
                      {copied === "ok" ? "Copied" : "Copy"}
                    </button>
                  </div>
                  <p className="studio-panel-note">
                    {file
                      ? pythonErr
                        ? `Not up to date: ${pythonErr}`
                        : selected && shown !== files
                          ? `One file per tab: ${selected}'s ${shown.length === 1 ? "tab" : `${shown.length} tabs`} (select nothing for every node's).`
                          : "One file per tab of every node, made by the flow engine from the project."
                      : python || pythonErr
                        ? `The project JSON (the one source of truth): Save downloads it.${pythonErr ? ` The Python view: ${pythonErr}.` : ""}`
                        : "The Python view is made by the flow engine…"}
                  </p>
                  <CodeView ref={codeRef} code={codeText} colour={file !== null} label={file ? "Python" : "the project JSON"} testId={file ? "maps-code-py" : "maps-code-json"} />
                </div>
              )}
            </div>
          </aside>
        )}
      </div>

      <footer className="studio-status">
        <p className="studio-status-text" data-testid="maps-status" aria-live="polite">
          {status}
        </p>
        <div className="studio-toggles" role="group" aria-label="Panels">
          <button type="button" className="toggle-button" aria-pressed={matOpen} onClick={() => (setMatOpen(!matOpen), writeChoice(store, MK.mat, matOpen ? "closed" : "open"))} data-testid="maps-toggle-mat">
            Links &amp; map view
          </button>
          <button type="button" className="toggle-button" aria-pressed={panelOpen} onClick={() => (setPanelOpen(!panelOpen), writeChoice(store, MK.panel, panelOpen ? "closed" : "open"))}>
            Panel
          </button>
        </div>
      </footer>

      {zonesMap && (
        <div className="text-neutral-100">
          <ZonesEditor
            api={api}
            world={world}
            server={project.target.server}
            map={zonesMap.map.map}
            block={zonesMap.id}
            zonesRef={zonesMap.zones ?? null}
            onReference={(ref) => edit(setZones(projectRef.current, zonesMap.id, ref))}
            onClose={() => setZonesFor(null)}
          />
        </div>
      )}
      {/* a phone in a run: room for the fixed playback bar (bar + 16 px + the safe area) */}
      <div className="maps-bar-spacer" aria-hidden="true" />
      <FlowFileDialogs open={dialog} onClose={() => setDialog(null)} meta={fileMeta} onMeta={setFile} getFlow={getProject} pythonCached={pythonCached} pythonFor={pythonFor} onOpened={onOpened} />
    </main>
  );
}

/** How a run ended, in words (the engine's `end`). */
const END_TEXT: Record<string, string> = {
  horizon: "the simulated time ran out (horizon)",
  done: "the project ended",
  single_block_exit: "the map node took an exit (single node run)",
  max_runtime: "max_runtime_s reached",
  stop_when: "stop_when held",
  handler_runaway: "an event fired too often (runaway)",
  death_limit: "dead fired more than max_per_run",
  relocate_no_block: "relocation found no map node for the map",
};

/** When the character is on its first map: after the mock session, else the trace's first map step. */
function arrival(tl: Timeline): number {
  return tl.offset > 0 ? tl.offset : (tl.beats.find((b) => b.kind !== "session")?.t0 ?? 0);
}

/** The graph node the character is in, in words (the folded graph's toolbar). */
function nodeWords(p: Project, id: string): string {
  const n = nodeById(p, id);
  if (!n) return id;
  return n.kind === "map" ? `${n.id} (${n.map.map})` : `${nodeTitle(n)} (simulated)`;
}

/** The panel with nothing selected. `own`: the lint's findings on the project itself (no card
 * shows them; matpilot round 16 #7), said here and in the lint chip's list. */
function Intro({ own, onLint }: { own: LintGroup | null; onLint: () => void }) {
  return (
    <div className="stack">
      {own && (
        <div className="notice notice-warn" data-testid="maps-project-lint">
          <p>
            <strong>On the project itself</strong> (no card shows {own.findings.length === 1 ? "it" : "them"}; the lint chip lists every finding):
          </p>
          <ul className="plain-list">
            {own.findings.map((f, i) => (
              <li key={`${f.rule}-${i}`}>
                {f.severity === "readiness" ? "not ready" : f.severity} · {f.text || f.message}
              </li>
            ))}
          </ul>
          <button type="button" className="button button-small" onClick={onLint} data-testid="maps-project-lint-all">
            Every finding
          </button>
        </div>
      )}
      <p className="strong">The project: its nodes, how they link, and the bot walking them.</p>
      <ul className="plain-list">
        <li>START is where the run begins. On a map node (the ready-made xmas_dun02: ONE box), the run starts where a person put her: drag START&apos;s connection onto another map to start there. Run (amber) plays the project in the game from START, box by box, once every block on the way is live.</li>
        <li>Login → Choose character → the first map are the session (later: login is not live yet): drag from a node&apos;s right port to connect it (one path). A credential is a NAME; no password is ever typed or kept here. Simulate plays them; nothing logs in.</li>
        <li>Each map node is a map with its own tabs (a main, and any you make): double-click it, or “Open flow”, to open them on /flows.</li>
        <li>Left of a map: its ENTRIES, how the character arrives (the session, a warp in, an NPC / Kafra warp, a Butterfly Wing). Right: its EXITS, where each goes and how.</li>
        <li>Drag from a map&apos;s “+” port onto another map to add an exit; one map can link to many. “+ map” places a map from the static data.</li>
        <li>Global holds the functions, events and variables every node shares; a node&apos;s own name overrides Global&apos;s there. Its “World rules”: the save point, and what to do on a map none of the nodes is on.</li>
        <li>Under the graph, “Links” lists the selected map&apos;s entries and exits (or every link); “Map view” shows the walk grid and the run.</li>
        <li>Simulate plays the run on each map&apos;s walk grid: the bot walks, meets monsters (placed from the seed), talks to NPCs and warps on, and the graph follows it.</li>
      </ul>
    </div>
  );
}
