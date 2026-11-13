"use client";

// The MAPS page (Batt 2026-11-10, docs/planning/world-map-flows.md): the flow as a GRAPH of maps
// (n8n / Node-RED: START -> Login -> Choose character -> map nodes joined by their exits; one map
// may link to many), each map node BOUND to its own flow (the map block's blocks on /flows: "Open
// flow"), and matpilot's mat for maps: SIMULATE plays the bot through the session's mock steps and
// the maps' flows on each map's walk grid: walking a -> b -> c, meeting monsters, talking to NPCs,
// warping on, the graph following it.
//
// NOTHING here runs live: the green button is SIMULATE (no game, no input). Login and Choose
// character are MOCKS (lib/maps/session.ts): no credential field anywhere, nothing logs in. The
// backend calls are computation only (lib/flow/api.ts: lint, simulate, the Python view, the static
// data); the page never reaches the executor, the mux, an agent channel or any input path.
//
// The flow is /flows' own (the same browser storage), so "Open flow" opens that map's tab there and
// /flows' map picker comes back here. The layout follows MatPilot's Mats page
// (src/components/mats/MatsApp.tsx at commit d639909; MIT License, Copyright (c) 2026 Sarat Sonsuk;
// the licence text is in studio.css and THIRD_PARTY.md): the stage with the playback bar over it,
// the panel beside it. Save and Load (2026-11-12, docs/planning/flows-save-load.md): on this computer
// and on GitHub, the dialogs shared with /flows (components/flowfile/).
import "@/components/flows/studio.css";
import "./maps.css";

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import FlowFileDialogs, { type FileDialog, type Opened, useFileShortcuts } from "@/components/flowfile/FlowFileDialogs";
import CodeView from "@/components/flows/CodeView";
import { InspectPanel } from "@/components/flows/Panels";
import { CaretIcon, CloseIcon, FolderIcon, PlayIcon, SaveIcon } from "@/components/maps/icons";
import LinksPanel from "@/components/maps/LinksPanel";
import RulesPanel from "@/components/maps/RulesPanel";
import { CharacterPanel, DEFAULT_RUN, LoginPanel, PlaybackBar, RunPanel, type RunForm, SPEEDS, StartPanel } from "@/components/maps/SidePanels";
import { ApiError, type CatalogueDoc, FlowsApi, type LintDoc, type Scenario, type SimDoc, type WorldDoc, type WorldMap, type WorldSource } from "@/lib/flow/api";
import { type BlockProps, connectExit, type EditResult, removeBlock, removeExit, setStart, setZonesRef, updateBlock, type XY } from "@/lib/flow/canvas";
import { type FileMeta, newFileMeta, readFileMeta, writeFileMeta } from "@/lib/flow/file";
import { exportText, importFlow } from "@/lib/flow/importer";
import { type AuthoredExit, canonical, type Flow, MAP_ID } from "@/lib/flow/ir";
import { browserStorage, KEYS, readChoice, readText, writeChoice } from "@/lib/flow/prefs";
import { RUNNERS, runnerForMap, runnerHref } from "@/lib/flow/runners";
import { STARTER_WORLD, starterFlow } from "@/lib/flow/starter";
import { END_TEXT, lintLine } from "@/lib/flow/status";
import { addMapNode, type MapFacts, oneMapFlow } from "@/lib/maps/build";
import { mapsGraph, UNKNOWN_ID } from "@/lib/maps/graph";
import { beatAt, beatText, buildTimeline, type Check, type Labels, poseAt, runChecks, type Timeline } from "@/lib/maps/play";
import { readSession, type Session, serverOf, sessionProblems, sessionPython, sessionSteps, slotText, writeSession } from "@/lib/maps/session";
import { refreshRule } from "@/lib/maps/rules";
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
  layout: "poring-lab.maps.layout.v1",
  run: "poring-lab.maps.run.v1",
  bottom: "poring-lab.maps.bottom.v1",
} as const;
const EXAMPLE_MAPS = ["xmas_dun02", "town_1", "field_1"];
type Notice = { text: string; tone: "ok" | "warn" | "error"; undo: { flow: Flow; world: WorldSource; file: FileMeta } | null };
type Sim = { doc: SimDoc; for: string; tl: Timeline; seed: number | null; old: boolean };

function initialFlow(store: ReturnType<typeof browserStorage>): { flow: Flow; restored: boolean; broken: boolean } {
  const text = readText(store, KEYS.flow);
  if (!text) return { flow: starterFlow(), restored: false, broken: false };
  const r = importFlow(text);
  return r.ok ? { flow: r.flow, restored: true, broken: false } : { flow: starterFlow(), restored: false, broken: true };
}

function readLayout(store: ReturnType<typeof browserStorage>, name: string): Record<string, XY> {
  try {
    const v = JSON.parse(readText(store, MK.layout) ?? "null") as { name?: unknown; positions?: unknown } | null;
    if (!v || v.name !== name || !v.positions || typeof v.positions !== "object") return {};
    const out: Record<string, XY> = {};
    for (const [k, p] of Object.entries(v.positions as Record<string, unknown>)) {
      const q = p as { x?: unknown; y?: unknown };
      if (typeof q?.x === "number" && typeof q?.y === "number" && Number.isFinite(q.x) && Number.isFinite(q.y)) out[k] = { x: q.x, y: q.y };
    }
    return out;
  } catch {
    return {};
  }
}

function readRun(store: ReturnType<typeof browserStorage>): RunForm {
  try {
    const v = JSON.parse(readText(store, MK.run) ?? "null") as Partial<RunForm> | null;
    if (!v) return DEFAULT_RUN;
    const s = (x: unknown, d: string) => (typeof x === "string" && x.length < 20 ? x : d);
    return { from: s(v.from, DEFAULT_RUN.from), seed: s(v.seed, DEFAULT_RUN.seed), horizon: s(v.horizon, DEFAULT_RUN.horizon), deathAt: s(v.deathAt, DEFAULT_RUN.deathAt) };
  } catch {
    return DEFAULT_RUN;
  }
}

const num = (s: string, d: number, lo: number, hi: number) => {
  const n = Number(s);
  return s.trim() !== "" && Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : d;
};

export default function MapsApp({ backendUrl, initialNode }: { backendUrl: string | null; initialNode: string | null }) {
  const router = useRouter();
  const [api] = useState<FlowsApi>(() => new FlowsApi(backendHttpBase(backendUrl)));
  const store = useMemo(() => browserStorage(), []);
  const [start] = useState(() => initialFlow(store));
  const [flow, setFlowState] = useState<Flow>(start.flow);
  const flowRef = useRef<Flow>(start.flow);
  // the name it was saved as and the GitHub file it came from (shared with /flows through storage)
  const [file, setFileState] = useState<FileMeta>(() => (start.restored ? readFileMeta(store, start.flow) : newFileMeta(start.flow)));
  const fileRef = useRef<FileMeta>(file);
  const [dialog, setDialog] = useState<FileDialog>(null);
  const [world, setWorld] = useState<WorldSource>(() => (start.restored ? readChoice(store, KEYS.world, WORLDS, "local") : STARTER_WORLD));
  const worldRef = useRef(world);
  useEffect(() => {
    worldRef.current = world;
  }, [world]);
  const [session, setSessionState] = useState<Session>(() => readSession(store));
  const [positions, setPositions] = useState<Record<string, XY>>(() => readLayout(store, start.flow.name));
  const [catalogue, setCatalogue] = useState<CatalogueDoc | null>(null);
  const [engineErr, setEngineErr] = useState<string | null>(null);
  const [lint, setLint] = useState<{ doc: LintDoc; for: string } | null>(null);
  const [python, setPython] = useState<{ text: string; for: string } | null>(null);
  const [pythonErr, setPythonErr] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(() => {
    const ids = new Set(["start", "login", "character", "main", UNKNOWN_ID, ...(start.flow.workflow?.blocks.map((b) => `block:${b.name}`) ?? [])]);
    return initialNode && ids.has(initialNode) ? initialNode : null;
  });
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
    start.broken ? { text: "Your saved flow could not be opened, so the two-map starter is shown instead.", tone: "warn", undo: null } : null,
  );
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
  const [adding, setAdding] = useState<{ map: string; mode: "node" | "flow" } | null>(null);
  const [addBusy, setAddBusy] = useState(false);
  const [codeFile, setCodeFile] = useState<"session" | "py" | "json">("py");
  const [copied, setCopied] = useState<"idle" | "ok" | "failed">("idle");
  const [zonesFor, setZonesFor] = useState<string | null>(null);
  // round 5 (Batt: "make it an option"): the map's other monsters as decoration; off by default
  const [decorOn, setDecorOn] = useState(() => readChoice(store, WANDER_KEY, ["on", "off"] as const, "off") === "on");
  const [graphFolded, setGraphFolded] = useState(false); // round 3: the map gets the height in a run
  const menuRef = useRef<HTMLDivElement | null>(null);
  const codeRef = useRef<HTMLPreElement | null>(null);
  const matRef = useRef<HTMLElement | null>(null);
  const scrollToMat = useRef(false); // a phone: after Simulate, the map (not the panel) comes into view
  const key = useMemo(() => canonical(flow), [flow]);
  const blocks = useMemo(() => flow.workflow?.blocks.map((b) => ({ name: b.name, map: b.map.map })) ?? [], [flow]);

  const setTime = useCallback((t: number) => {
    timeRef.current = t;
    setTimeState(t);
  }, []);
  const setSide = (s: Side) => {
    setSideState(s);
    writeChoice(store, MK.side, s);
    if (!panelOpen) {
      setPanelOpen(true);
      writeChoice(store, MK.panel, "open");
    }
  };
  const setSession = (s: Session) => {
    setSessionState(s);
    writeSession(store, s);
  };
  const setRunForm = (f: RunForm) => {
    setRunFormState(f);
    writeChoice(store, MK.run, JSON.stringify(f));
  };

  // --- the flow (shared with /flows through this browser's storage) ------------------------------
  const flush = useCallback(() => {
    writeChoice(store, KEYS.flow, exportText(flowRef.current));
    writeChoice(store, KEYS.world, worldRef.current);
    writeFileMeta(store, fileRef.current, flowRef.current);
  }, [store]);
  const setFile = useCallback((m: FileMeta) => {
    fileRef.current = m;
    setFileState(m);
  }, []);
  const replace = useCallback(
    (f: Flow, opts: { notice?: string; undo?: boolean; world?: WorldSource; keepView?: boolean; file?: FileMeta } = {}) => {
      const prev = { flow: flowRef.current, world: worldRef.current, file: fileRef.current };
      flowRef.current = f;
      setFlowState(f);
      // an edit keeps the file it came from; any other new flow starts unsaved (Undo puts it back)
      setFile(opts.file ?? (opts.keepView ? fileRef.current : newFileMeta(f)));
      if (!opts.keepView) {
        setPositions(readLayout(store, f.name));
        setSim(null);
        setSelected(null);
        setPlaying(false);
        setTime(0);
        setMatChoice(null);
      }
      if (opts.world) setWorld(opts.world);
      if (opts.notice) setNotice({ text: opts.notice, tone: "ok", undo: opts.undo ? prev : null });
    },
    [store, setTime, setFile],
  );
  const edit = useCallback(
    (r: EditResult) => {
      // round 6: the unknown-map rule's list of known maps follows the map nodes (rules.ts)
      if (r.ok) replace(refreshRule(r.flow), { keepView: true });
      else setNotice({ text: r.error, tone: "error", undo: null });
    },
    [replace],
  );
  useEffect(() => {
    const t = setTimeout(flush, SAVE_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [flow, world, file, flush]);
  useEffect(() => flush, [flush]); // leaving the page: the latest flow is kept for /flows
  useEffect(() => {
    try {
      store?.setItem(MK.layout, JSON.stringify({ name: flow.name, positions }));
    } catch {
      // unremembered
    }
  }, [positions, flow.name, store]);
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
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menu]);

  // --- the engine: catalogue (the run limits), lint, the Python, the static data ---------------------
  useEffect(() => {
    api
      .catalogue(flow.target.client)
      .then((c) => (setCatalogue(c), setEngineErr(null)))
      .catch((e) => setEngineErr(e instanceof ApiError ? e.reason : String(e)));
  }, [api, flow.target.client]);
  useEffect(() => {
    const t = setTimeout(() => {
      const f = flowRef.current;
      api
        .lint(f, world)
        .then((doc) => setLint({ doc, for: canonical(f) }))
        .catch(() => undefined); // the context bar keeps "…"; /flows shows lint in full
    }, LINT_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [key, world, api]);
  useEffect(() => {
    let alive = true;
    const t = setTimeout(() => {
      const f = flowRef.current;
      api
        .python(f)
        .then((r) => alive && (setPython({ text: r.python, for: canonical(f) }), setPythonErr(null)))
        .catch((e) => alive && setPythonErr(e instanceof ApiError ? e.reason : "the Python view is unavailable"));
    }, PYTHON_DEBOUNCE_MS);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [key, api]);
  // every map of the flow and of the last run, with their walk grids (one request a change)
  const mapNames = useMemo(() => [...new Set([...blocks.map((b) => b.map), ...(sim?.tl.maps ?? []), ...(matChoice ? [matChoice] : [])])].filter((m) => MAP_ID.test(m)).sort().slice(0, 20), [blocks, sim, matChoice]);
  const mapsKey = mapNames.join(",");
  useEffect(() => {
    if (!mapsKey) return;
    let alive = true;
    api
      .world(world, flow.target.server, mapsKey.split(","), true)
      .then((w) => alive && setWorldDoc(w))
      .catch(() => alive && setWorldDoc(null));
    return () => {
      alive = false;
    };
  }, [api, world, flow.target.server, mapsKey]);
  const labels: Labels | null = useMemo(() => {
    if (!worldDoc) return null;
    const pick = <T,>(o: Record<string, T>, f: (v: T) => string | null) => Object.fromEntries(Object.entries(o).flatMap(([k, v]) => (f(v) ? [[k, f(v) as string]] : [])));
    return { mobs: pick(worldDoc.mobs, (m) => m.label), items: pick(worldDoc.items, (i) => i.label), npcs: worldDoc.labels?.npcs ?? {}, options: worldDoc.labels?.options ?? {} };
  }, [worldDoc]);

  // --- simulate and play back ---------------------------------------------------------------------
  const simulate = async (from: string) => {
    const f = flowRef.current;
    const form = { ...runForm, from };
    setRunForm(form);
    const seed = Math.round(num(form.seed, 1, 0, 2 ** 31 - 1));
    const death = form.deathAt.trim() === "" ? null : num(form.deathAt, 200, 0, 3600);
    const base: Scenario = {
      horizon_s: num(form.horizon, 120, 1, 3600),
      start_block: from === "login" ? null : from,
      single_block: false,
      timeline: death === null ? [] : [{ t: death, set: { is_dead: true, hp_percent: 0 } }],
    };
    setSimBusy(true);
    setPlaying(false);
    try {
      let old = false;
      let doc: SimDoc;
      try {
        doc = await api.simulate(f, world, { ...base, encounters: true, seed });
      } catch (e) {
        // an older backend (before 2026-11-10) refuses the two new scenario fields: run without
        if (!(e instanceof ApiError && e.reason === "invalid_scenario" && e.errors.some((x) => /encounters|seed/.test(x)))) throw e;
        old = true;
        doc = await api.simulate(f, world, base);
      }
      const tl = buildTimeline(doc.trace, from === "login" ? sessionSteps(session) : null);
      setSim({ doc, for: canonical(f), tl, seed: old ? null : seed, old: old || !Array.isArray(doc.trace.play) });
      setLint({ doc: doc.lint, for: canonical(f) });
      setMatChoice(null);
      setTime(0);
      setPlaying(true);
      setBottom("map"); // the run plays on the map view
      if (!matOpen) {
        setMatOpen(true);
        writeChoice(store, MK.mat, "open");
      }
      setSide("run");
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
  const activeNode = playing || time > 0 ? (pose?.node ?? null) : null;
  const activeEdge = useMemo(() => {
    if (!tl || current < 0 || !(playing || time > 0)) return null;
    const b = tl.beats[current];
    if (b.kind === "session") return b.node === "login" ? "session:start" : b.node === "character" ? "session:login" : null;
    for (let i = current; i >= 0; i--) {
      const x = tl.beats[i];
      if (x.kind === "exit" && x.step?.node) return `exit:${x.step.node}`;
      if (x.kind === "arrive" && x.step?.via === "respawn") return x.step.block ? `respawn:${x.step.block}` : null;
      if (x.kind === "session") return "session:enter";
    }
    return null;
  }, [tl, current, playing, time]);
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
  const selectedBlock = selected?.startsWith("block:") ? flow.workflow?.blocks.find((b) => `block:${b.name}` === selected) : undefined;
  const matMap =
    (playing ? pose?.map : null) ||
    matChoice ||
    (tl ? pose?.map : null) ||
    selectedBlock?.map.map ||
    tl?.maps[0] ||
    blocks.find((b) => b.name === flow.workflow?.start_block)?.map ||
    null;
  const sheet: WorldMap | null = matMap ? (worldDoc?.maps[matMap] ?? null) : null;
  const rows = matMap ? (worldDoc?.walk?.[matMap] ?? null) : null;
  const simStale = sim !== null && sim.for !== key;
  const folded = matOpen && graphFolded && tl !== null; // the graph folds only while a run is shown

  // --- load, save, add a map ---------------------------------------------------------------------
  const loadSample = async () => {
    setMenu(false);
    try {
      const s = await api.sample();
      replace(s.flow, { world: s.world, undo: true, notice: "Opened Batt's sample: town → NPC warp → farm loop (synthetic maps, the sample sheets)." });
    } catch (e) {
      setNotice({ text: `No sample: ${e instanceof ApiError ? e.reason : String(e)}`, tone: "error", undo: null });
    }
  };
  // Save and Load (components/flowfile/): a loaded file is already checked into a scratch flow
  const onOpened = (o: Opened) => {
    setDialog(null);
    replace(o.flow, { undo: true, file: o.meta, notice: o.notice });
  };
  const pythonCached = useCallback((f: Flow) => (python && python.for === canonical(f) ? python.text : null), [python]);
  const pythonFor = useCallback(
    (f: Flow): Promise<string> => {
      const have = pythonCached(f);
      return have !== null ? Promise.resolve(have) : api.python(f).then((r) => r.python, () => "");
    },
    [api, pythonCached],
  );
  const getFlow = useCallback(() => flowRef.current, []);
  const facts = async (map: string, source: WorldSource): Promise<{ facts: MapFacts | null; why: string }> => {
    try {
      const w = await api.world(source, flowRef.current.target.server, [map], true);
      const m = w.maps[map];
      if (!m) return { facts: null, why: `the ${source === "local" ? "lab data" : "sample sheets"} have no sheet for ${map}` };
      const r = w.walk?.[map] ?? null;
      return { facts: { rows: r, spawns: m.spawns }, why: r ? "" : `no walk grid for ${map} in the static data (the backend's GAT mount): the entry is "anywhere"` };
    } catch (e) {
      return { facts: null, why: `the static data could not be read (${e instanceof ApiError ? e.reason : String(e)})` };
    }
  };
  const addMap = async () => {
    if (!adding) return;
    const map = adding.map.trim();
    if (!MAP_ID.test(map)) return setNotice({ text: `${JSON.stringify(map)} is not a map id`, tone: "error", undo: null });
    setAddBusy(true);
    const source: WorldSource = adding.mode === "flow" ? "local" : world;
    const got = await facts(map, source);
    setAddBusy(false);
    if (adding.mode === "flow") {
      const r = oneMapFlow(map, got.facts, catalogue?.runtime_limits?.default_s);
      if (!r.ok) return setNotice({ text: r.error, tone: "error", undo: null });
      replace(r.flow, { world: source, undo: true, notice: `A new flow on ${map}: ${describeGuess(r.flow, got.why)}` });
    } else {
      const r = addMapNode(flowRef.current, map, got.facts);
      if (!r.ok) return setNotice({ text: r.error, tone: "error", undo: null });
      replace(r.flow, { keepView: true });
      setSelected(`block:${r.name}`);
      setNotice({ text: `Added the map node ${r.name}: ${describeGuess(r.flow, got.why, r.name)} Draw an exit from a map's port onto it.`, tone: "ok", undo: null });
    }
    setAdding(null);
  };
  const openFlow = useCallback(
    (block: string) => {
      flush();
      router.push(`/flows?block=${encodeURIComponent(block)}`);
    },
    [flush, router],
  );
  const simulateRef = useRef<((from: string) => Promise<void>) | null>(null);
  useEffect(() => {
    simulateRef.current = simulate;
  });
  const simulateFrom = useCallback((block: string) => void simulateRef.current?.(block), []);
  const onConnectExit = useCallback((from: string, kind: AuthoredExit, to: string) => edit(connectExit(flowRef.current, from, kind, to)), [edit]);
  const onDeleteExit = useCallback((path: string) => edit(removeExit(flowRef.current, path)), [edit]);
  const onMove = useCallback((p: Record<string, XY>) => setPositions((old) => ({ ...old, ...p })), []);
  const onSelect = useCallback(
    (id: string | null) => {
      setSelected(id);
      if (id) {
        setSideState("node");
        writeChoice(store, MK.side, "node");
        setPanelOpen(true);
      }
      // a map node clicked while nothing plays: the view shows its map
      const b = id?.startsWith("block:") ? flowRef.current.workflow?.blocks.find((x) => `block:${x.name}` === id) : undefined;
      if (b && !playing) setMatChoice(b.map.map);
    },
    [store, playing],
  );
  const onRules = useCallback(() => onSelect(UNKNOWN_ID), [onSelect]); // "Any other map": the world rules
  const copy = () => {
    const text = codeFile === "session" ? sessionPython(session) : codeFile === "py" ? (python?.text ?? "") : exportText(flowRef.current);
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
  // the selected map node's own part of the Python: scroll to its def
  useEffect(() => {
    if (side !== "python" || codeFile !== "py" || !selectedBlock || !python) return;
    const line = python.text.split("\n").findIndex((l) => l.startsWith(`def ${selectedBlock.name}(`));
    const pre = codeRef.current;
    const scroller = pre?.closest(".code-view") as HTMLElement | null;
    if (line < 0 || !pre || !scroller) return;
    const lh = parseFloat(getComputedStyle(pre).lineHeight) || 18;
    scroller.scrollTop = Math.max(0, (line - 3) * lh);
  }, [side, codeFile, selectedBlock, python]);

  // --- words --------------------------------------------------------------------------------------
  const lintDoc = lint?.doc ?? null;
  const canvasNotes = useMemo(() => mapsGraph(flow, session).notes.filter((n) => !n.startsWith("a plain flow")), [flow, session]);
  const total = lintDoc ? lintLine(lintDoc.counts) : null;
  const problems = sessionProblems(session, flow.target.server);
  const checks: Check[] = useMemo(
    () => (sim ? runChecks(sim.tl, sim.doc.trace, blocks, END_TEXT[sim.doc.trace.end] ?? sim.doc.trace.end, sim.seed) : []),
    [sim, blocks],
  );
  const status = engineErr
    ? `The flow engine is not reachable (${engineErr}): the graph works, Simulate does not.`
    : simBusy
      ? "Simulating…"
      : tl && beat
        ? `${playing ? "Playing" : "Paused"} at ${time.toFixed(1)} s of ${end.toFixed(1)} s · ${beat.node.startsWith("block:") ? `${beat.node.slice(6)}: ` : ""}${beatText(beat, labels)}`
        : "Ready. Press Simulate to watch the bot log in (a mock) and walk its maps.";
  const codeText = codeFile === "session" ? sessionPython(session) : codeFile === "py" ? (python?.text ?? "") : exportText(flow);
  const zonesBlock = zonesFor ? flow.workflow?.blocks.find((x) => x.name === zonesFor) : undefined;
  useFileShortcuts(
    (d) => {
      setMenu(false);
      setDialog(d);
    },
    dialog,
    !zonesBlock,
  );

  return (
    <main className="studio maps-page" data-run={tl ? "true" : "false"} data-testid="maps-app">
      <header className="studio-bar">
        <div className="studio-brand">
          <span className="studio-home">Maps</span>
          <span className="status-pill" title="Nothing on this page runs in the game">
            SIMULATE only
          </span>
          <h1 className="studio-title" title={flow.name}>
            {flow.name}
          </h1>
        </div>
        <div className="studio-actions">
          <div className="studio-menu" ref={menuRef}>
            <button type="button" className="button button-small button-file" onClick={() => setMenu(!menu)} aria-expanded={menu} aria-label="Load a flow" title="Open a flow" data-testid="maps-load">
              <FolderIcon />
              <span className="button-text">Load</span>
              <CaretIcon />
            </button>
            {menu && (
              <div className="studio-menu-list" role="menu">
                {/* the map flows first, under their map's name (Batt 2026-11-13) */}
                {RUNNERS.map((r) => (
                  <button key={r.id} type="button" role="menuitem" className="studio-menu-item studio-menu-item-map" onClick={() => (setMenu(false), flush(), router.push(runnerHref(r)))} data-testid={`maps-load-runner-${r.id}`}>
                    {r.title}
                    <small>on /flows: the {r.char}&apos;s real flow on {r.map}, each part on its tab; Simulate, or Run in the game</small>
                  </button>
                ))}
                <button type="button" role="menuitem" className="studio-menu-item" onClick={() => (setMenu(false), replace(starterFlow(), { world: STARTER_WORLD, undo: true, notice: "Opened the starter: two maps." }))}>
                  Starter: two maps<small>town → NPC warp → field, a wing back (synthetic maps)</small>
                </button>
                <button type="button" role="menuitem" className="studio-menu-item" onClick={() => void loadSample()}>
                  Batt&apos;s sample<small>town → NPC warp → farm loop, on synthetic map sheets</small>
                </button>
                <button type="button" role="menuitem" className="studio-menu-item" onClick={() => (setMenu(false), setAdding({ map: "xmas_dun02", mode: "flow" }))} data-testid="maps-load-one-map">
                  One map from the lab data…<small>e.g. xmas_dun02, the Rogue&apos;s map: its walk grid and spawns</small>
                </button>
                <button type="button" role="menuitem" className="studio-menu-item" onClick={() => (setMenu(false), setDialog("load"))} data-testid="maps-load-saved">
                  Open a saved flow…<small>from this computer or from GitHub (checked before it opens; Ctrl+O)</small>
                </button>
              </div>
            )}
          </div>
          <button type="button" className="button button-small button-file" onClick={() => (setMenu(false), setDialog("save"))} aria-label="Save the flow" title="Save the flow: on this computer or on GitHub (Ctrl+S)" data-testid="maps-save">
            <SaveIcon />
            <span className="button-text">Save</span>
          </button>
          <button type="button" className="button button-primary button-run" onClick={() => void simulate(runForm.from === "login" || blocks.some((b) => b.name === runForm.from) ? runForm.from : "login")} disabled={simBusy} title="Run it in the simulator: no game, no input" data-testid="maps-simulate">
            <PlayIcon />
            <span className="button-text">{simBusy ? "Simulating…" : "Simulate"}</span>
          </button>
        </div>
      </header>

      {(notice || canvasNotes.length > 0 || copied === "failed") && (
        <div className="studio-notices">
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
                    if (u) replace(u.flow, { world: u.world, file: u.file });
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
          {canvasNotes.map((n) => (
            <p key={n} className="notice notice-warn">
              {n}
            </p>
          ))}
        </div>
      )}

      <div className="device-bar" aria-label="The run">
        <button type="button" className="device-chip mp-chip" onClick={() => onSelect("login")} title="Login: a mock">
          <span className="device-label">login (mock)</span>
          <span className="device-value">{serverOf(session.server)?.id ?? session.server}</span>
        </button>
        <button type="button" className="device-chip mp-chip" onClick={() => onSelect("character")} title="Choose character: a mock">
          <span className="device-label">character (mock)</span>
          <span className="device-value">{slotText(session)}</span>
        </button>
        <label className="device-chip">
          <span className="device-label">static data</span>
          <select value={world} onChange={(e) => setWorld(e.target.value as WorldSource)} data-testid="maps-world">
            <option value="local">lab data/kb</option>
            <option value="sample">sample sheets</option>
          </select>
        </label>
        <div className="device-chip">
          <span className="device-label">maps</span>
          <span className="device-value">{blocks.length}</span>
        </div>
        <div className="device-chip" data-level={total?.level}>
          <span className="device-label">lint</span>
          <span className="device-value">{total ? `${total.text}${lint && lint.for !== key ? " (checking…)" : ""}` : "…"}</span>
        </div>
        {problems.length > 0 && (
          <div className="device-chip" data-level="warning" title={problems.join(" · ")}>
            {problems[0]}
          </div>
        )}
      </div>

      <div className="maps-body" data-panel={panelOpen ? "open" : "closed"}>
        <div className="maps-stage" data-mat={matOpen ? "open" : "closed"} data-graph={folded ? "folded" : "open"} data-bottom={matOpen ? bottom : "none"}>
          <section className="maps-graph" aria-label="The maps and how they link">
            <div className="maps-toolbar">
              {folded ? (
                <>
                  <button type="button" className="block-tab-add" onClick={() => setGraphFolded(false)} aria-expanded={false} data-testid="maps-graph-show">
                    Show the graph
                  </button>
                  <span className="maps-hint">
                    The graph is folded while the run plays{activeNode ? " · now: " : ""}
                    {activeNode && <span className="maps-now">{nodeWords(activeNode, flow)}</span>}
                  </span>
                </>
              ) : adding?.mode === "node" ? (
                <form
                  className="maps-add"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void addMap();
                  }}
                >
                  <label>
                    map id{" "}
                    <input value={adding.map} onChange={(e) => setAdding({ ...adding, map: e.target.value })} list="maps-known" maxLength={40} autoFocus data-testid="maps-add-id" />
                  </label>
                  <button type="submit" className="button button-small button-primary" disabled={addBusy}>
                    {addBusy ? "Reading…" : "Add"}
                  </button>
                  <button type="button" className="button button-small" onClick={() => setAdding(null)}>
                    Cancel
                  </button>
                </form>
              ) : (
                <button type="button" className="block-tab-add" onClick={() => setAdding({ map: "", mode: "node" })} disabled={!flow.workflow} title={flow.workflow ? "Place a map node from the static data" : "A plain flow has no map blocks"} data-testid="maps-add">
                  + map
                </button>
              )}
              {!folded && tl && matOpen && (
                <button type="button" className="block-tab-add" onClick={() => setGraphFolded(true)} aria-expanded={true} title="Fold the graph: the map gets the height" data-testid="maps-graph-fold">
                  Fold the graph
                </button>
              )}
              {!folded && (
                <span className="maps-hint">Drag from a port (walk exit, npc warp, item warp) onto another map to link them; click a node to inspect it; double-click a map to open its flow.</span>
              )}
            </div>
            <datalist id="maps-known">
              {[...new Set([...EXAMPLE_MAPS, ...blocks.map((b) => b.map)])].map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
            <div className="maps-graph-canvas">
              <MapsCanvas
                flow={flow}
                session={session}
                positions={positions}
                lint={lintDoc}
                trace={sim && !simStale ? sim.doc.trace : null}
                selected={selected}
                activeNode={activeNode}
                activeEdge={activeEdge}
                onSelect={onSelect}
                onMove={onMove}
                onConnectExit={onConnectExit}
                onDeleteExit={onDeleteExit}
                onOpenFlow={openFlow}
                onSimulateFrom={simulateFrom}
                onRules={onRules}
              />
            </div>
          </section>
          {adding?.mode === "flow" && (
            <div className="maps-dialog" role="dialog" aria-label="A new flow on one map">
              <form
                className="maps-add"
                onSubmit={(e) => {
                  e.preventDefault();
                  void addMap();
                }}
              >
                <strong>A new flow on one map, from the lab data</strong>
                <label>
                  map id <input value={adding.map} onChange={(e) => setAdding({ ...adding, map: e.target.value })} list="maps-known" maxLength={40} autoFocus data-testid="maps-one-map-id" />
                </label>
                <span className="muted">Its walk grid, entry and targets come from the backend&apos;s lab data at run time (never stored in the repo). The flow here is replaced (Undo brings it back).</span>
                <div className="button-row">
                  <button type="submit" className="button button-small button-primary" disabled={addBusy}>
                    {addBusy ? "Reading…" : "Make the flow"}
                  </button>
                  <button type="button" className="button button-small" onClick={() => setAdding(null)}>
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          )}
          {matOpen && (
            <section className="maps-mat" aria-label="Under the graph: the links or the map view" ref={matRef} data-bottom={bottom}>
              <div className="maps-bottom-tabs segmented" role="group" aria-label="Under the graph">
                <button type="button" aria-pressed={bottom === "links"} className="segmented-option" onClick={() => setBottom("links")} data-testid="maps-bottom-links">
                  Links
                </button>
                <button type="button" aria-pressed={bottom === "map"} className="segmented-option" onClick={() => setBottom("map")} data-testid="maps-bottom-map">
                  Map view
                </button>
                <span className="maps-hint">{bottom === "links" ? (selectedBlock ? `how ${selectedBlock.map.map} links: its entries and exits` : "every link of the flow; click a map for its own") : "the walk grid and the simulation"}</span>
              </div>
              {bottom === "links" ? (
                <LinksPanel flow={flow} block={selectedBlock?.name ?? null} onSelect={onSelect} onOpenFlow={openFlow} onRules={onRules} />
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
                  {tl && time < tl.offset && beat?.session && (
                    // the first seconds: the session's mock steps, before the character is on a map
                    // (round 3: over the map itself, one or two lines on a phone; the step list
                    // has the details)
                    <p className="mat-overlay" role="status" data-testid="mat-session">
                      <strong>{beat.session.node === "start" ? "Starting the client…" : beat.session.node === "login" ? "Logging in… (a mock)" : "Entering the game… (a mock)"}</strong>{" "}
                      <span>
                        the character appears on {sim?.doc.trace.start.map ?? "the first map"}
                        {sim?.doc.trace.start.cell ? ` (${sim.doc.trace.start.cell[0]}, ${sim.doc.trace.start.cell[1]})` : ""} in {Math.ceil(tl.offset - time)} s
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
          <aside className="maps-side" aria-label="The node, the run and the Python">
            <div className="maps-side-tabs">
              <div className="segmented" role="group" aria-label="Panel">
                {SIDES.map((s) => (
                  <button key={s} type="button" className="segmented-option" aria-pressed={side === s} onClick={() => setSide(s)} data-testid={`maps-side-${s}`}>
                    {s === "node" ? "Node" : s === "run" ? "Run" : "Python"}
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
                  {selected === null && <Intro />}
                  {selected === "start" && <StartPanel session={session} />}
                  {selected === "login" && <LoginPanel session={session} onSession={setSession} />}
                  {selected === "character" && <CharacterPanel session={session} onSession={setSession} />}
                  {selected === UNKNOWN_ID && <RulesPanel flow={flow} onEdit={edit} />}
                  {selected === "main" && (
                    <div className="stack">
                      <p>A plain flow: one program (the tab “main” on /flows), no map blocks. Load ▸ the two-map starter, or One map from the lab data, to place maps.</p>
                      <button type="button" className="button button-small" onClick={() => (flush(), router.push("/flows"))}>
                        Open the flow
                      </button>
                    </div>
                  )}
                  {selectedBlock && (
                    <div className="stack">
                      <div className="mp-bound">
                        <span className="muted">map</span> <strong>{selectedBlock.map.map}</strong> <span className="muted">· its flow: the map block</span> <strong>{selectedBlock.name}</strong>
                      </div>
                      <div className="button-row">
                        <button type="button" className="button button-small button-primary" onClick={() => openFlow(selectedBlock.name)} data-testid="maps-open-flow">
                          Open its flow ↗
                        </button>
                        <button type="button" className="button button-small" onClick={() => void simulate(selectedBlock.name)} disabled={simBusy}>
                          <PlayIcon />
                          Simulate from here
                        </button>
                        <button type="button" className="button button-small" onClick={() => (setMatChoice(selectedBlock.map.map), setPlaying(false), setBottom("map"), matOpen || (setMatOpen(true), writeChoice(store, MK.mat, "open")))}>
                          Show its map
                        </button>
                        {runnerForMap(selectedBlock.map.map) && (
                          <button
                            type="button"
                            className="button button-small"
                            onClick={() => {
                              const r = runnerForMap(selectedBlock.map.map);
                              if (!r) return;
                              flush();
                              router.push(runnerHref(r));
                            }}
                            title="On /flows: the real flow of this map (the live runner as blocks, made from its code), with Run"
                            data-testid="maps-runner-flow"
                          >
                            The {selectedBlock.map.map} flow ↗
                          </button>
                        )}
                      </div>
                      <InspectPanel
                        flow={flow}
                        selected={selected}
                        lint={lintDoc}
                        sim={sim && !simStale ? sim.doc : null}
                        api={api}
                        world={world}
                        onUpdate={(name: string, props: BlockProps) => {
                          edit(updateBlock(flowRef.current, name, props));
                          if (props.name !== name) setSelected(`block:${props.name}`);
                        }}
                        onDelete={(name) => {
                          edit(removeBlock(flowRef.current, name));
                          setSelected(null);
                        }}
                        onStart={(name, entry) => edit(setStart(flowRef.current, name, entry))}
                        onOpen={(id) => id.startsWith("block:") && openFlow(id.slice(6))}
                        onSimulateHere={(b) => void simulate(b)}
                        limits={catalogue?.runtime_limits ?? null}
                        onFlow={(f) => replace(f, { keepView: true })}
                        onZones={setZonesFor}
                      />
                    </div>
                  )}
                </>
              )}
              {side === "run" && (
                <RunPanel
                  form={runForm}
                  setForm={setRunForm}
                  blocks={blocks}
                  busy={simBusy}
                  onRun={() => void simulate(runForm.from === "login" || blocks.some((b) => b.name === runForm.from) ? runForm.from : "login")}
                  result={sim ? { tl: sim.tl, checks, endText: END_TEXT[sim.doc.trace.end] ?? sim.doc.trace.end, notes: sim.doc.trace.notes, old: sim.old, stale: simStale } : null}
                  current={current}
                  labels={labels}
                  onSeek={seek}
                />
              )}
              {side === "python" && (
                <div className="maps-python">
                  <div className="python-files" role="tablist" aria-label="Files">
                    {(["session", "py", "json"] as const).map((k) => (
                      <button key={k} type="button" role="tab" className="python-file" aria-selected={codeFile === k} onClick={() => setCodeFile(k)} data-testid={`maps-file-${k}`}>
                        {k === "session" ? "session.py (mock)" : k === "py" ? `${flow.name}.py` : `${flow.name}.flow.json`}
                      </button>
                    ))}
                    <button type="button" className="button button-small" onClick={copy} disabled={codeText === ""}>
                      {copied === "ok" ? "Copied" : "Copy"}
                    </button>
                  </div>
                  <p className="studio-panel-note">
                    {codeFile === "session"
                      ? "A MOCK: the bot's real login calls (scripts/ro_agent.py) that the Login and Choose character nodes stand for. Nothing here runs from this page."
                      : codeFile === "py"
                        ? pythonErr
                          ? `Not up to date: ${pythonErr}`
                          : selectedBlock
                            ? `Every map's flow is a def under @map_block: ${selectedBlock.name}'s is def ${selectedBlock.name}().`
                            : "Every map's flow is a def under @map_block, made by the flow engine from the blocks."
                        : "The flow IR (the one source of truth): Save keeps it with the Python, on this computer or on GitHub."}
                  </p>
                  {codeFile === "py" && !python ? (
                    <p className="studio-panel-note">The Python view is made by the flow engine…</p>
                  ) : (
                    <CodeView ref={codeRef} code={codeText} colour={codeFile !== "json"} label={codeFile === "json" ? "the flow JSON" : "Python"} testId={`maps-code-${codeFile}`} />
                  )}
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
      {/* a phone in a run: room for the fixed playback bar (bar + 16 px + the safe area) */}
      <div className="maps-bar-spacer" aria-hidden="true" />
    </main>
  );
}

/** The graph node the character is in, in words (the folded graph's toolbar). */
function nodeWords(node: string, flow: Flow): string {
  if (node === "start") return "START";
  if (node === "login") return "Login (a mock)";
  if (node === "character") return "Choose character (a mock)";
  if (node === "main") return "main (a plain flow)";
  const b = flow.workflow?.blocks.find((x) => `block:${x.name}` === node);
  return b ? `${b.name} (${b.map.map})` : node;
}

function describeGuess(f: Flow, why: string, name?: string): string {
  const b = name ? f.workflow?.blocks.find((x) => x.name === name) : f.workflow?.blocks[0];
  if (!b) return why;
  const at = b.entries[0].at;
  const parts = [
    at ? `the entry (${at.x}, ${at.y}) is the walkable cell nearest the centre` : "the entry is anywhere (no walk grid)",
    b.targets.length ? `targets ${b.targets.map((m) => m.id).join(", ")}` : "no targets (no spawns in the static data)",
    b.ignore.length ? `ignored ${b.ignore.map((m) => m.id).join(", ")} (boss lines and single spawns)` : "",
  ].filter(Boolean);
  return `${parts.join("; ")}: a first guess, change it in Inspect.${why ? ` Note: ${why}.` : ""}`;
}

function Intro() {
  return (
    <div className="stack">
      <p className="strong">The maps of your flow, and the bot walking them.</p>
      <ul className="plain-list">
        <li>START → Login → Choose character are a MOCK of the bot&apos;s login (scripts/ro_agent.py): click one to see its choices. No password is ever typed here.</li>
        <li>Each map node is a map, BOUND to its own flow: what to do on this map. “Open flow” opens its blocks on /flows.</li>
        <li>Left of a map: its ENTRIES, how the character arrives (the start, a warp in, an NPC / Kafra warp, a Butterfly Wing). Right: its EXITS, where each goes and how.</li>
        <li>Drag from a map&apos;s “+” port onto another map to add an exit; one map can link to many. “+ map” places a map from the static data.</li>
        <li>“Any other map” holds the WORLD RULES: the save point, and what to do on a map none of the nodes is on (stop, or a Butterfly Wing home).</li>
        <li>Under the graph, “Links” lists the selected map&apos;s entries and exits (or every link); “Map view” shows the walk grid and the run.</li>
        <li>▶ Simulate plays the run on each map&apos;s walk grid: the bot walks, meets monsters (placed from the seed), talks to NPCs and warps on, and the graph follows it.</li>
      </ul>
    </div>
  );
}
