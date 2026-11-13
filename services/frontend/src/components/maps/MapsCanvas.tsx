"use client";

// The Maps page's GRAPH over the PROJECT (React Flow, n8n's way; Batt 2026-11-13, docs/planning/
// project-model.md): the project's nodes -- Login, Choose character, one per map, and ONE Global --
// at their saved positions; the SESSION connections (project.edges: login -> character -> the
// start map's entry) drawn, dragged to another node and deleted like n8n's; the map nodes' EXITS
// (take_exit statements in their tabs) as one port per exit onto the entry they land on; Global
// with no ports, "shared by every node". The graph is DERIVED (lib/maps/graph.ts); every drawing
// edits the project (lib/maps/edit.ts). During a playback the node the character is in glows and
// the connection or exit it last took is drawn thicker. Ideas from Node-RED and n8n (typed ports,
// status lines); no code from either.
import "@xyflow/react/dist/style.css";

import {
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  BaseEdge,
  type Connection,
  ControlButton,
  Controls,
  type Edge,
  type EdgeChange,
  EdgeLabelRenderer,
  type EdgeProps,
  getBezierPath,
  getSmoothStepPath,
  Handle,
  MiniMap,
  type Node,
  type NodeChange,
  type NodeProps,
  Position,
  ReactFlow,
  type ReactFlowInstance,
  useUpdateNodeInternals,
} from "@xyflow/react";
import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { EXIT_COLOURS } from "@/components/maps/colours";
import { MapIcon, PlayIcon } from "@/components/maps/icons";
import type { LintDoc, Trace } from "@/lib/flow/api";
import type { AuthoredExit } from "@/lib/flow/ir";
import { type Project } from "@/lib/flow/project";
import { lintLine } from "@/lib/flow/status";
import { sessionLinkProblem } from "@/lib/maps/edit";
import { type EdgeData, entryHandle, exitHandle, exitRuns, fitViewport, followCentre, IN, mapsGraph, type MapsNodeData, OUT, RESPAWN, toUnits, type XY } from "@/lib/maps/graph";
import { entryCaption, EXIT_WORDS, nodeLinks } from "@/lib/maps/links";
import { nodeLint, tabList, tabRows } from "@/lib/maps/nodewords";
import { readRules, wingText } from "@/lib/maps/rules";
import { characterOf, credentialOf, loginOf, serverOf, slotText } from "@/lib/maps/session";

const PORTS: { kind: AuthoredExit; label: string }[] = [
  { kind: "walk_exit", label: "walk to a warp" },
  { kind: "npc_warp", label: "NPC / Kafra warp" },
  { kind: "item_warp", label: "Butterfly Wing" },
];
const isPort = (h: string | null | undefined): h is AuthoredExit => PORTS.some((p) => p.kind === h);
const entryOf = (h: string | null | undefined) => (h && h.startsWith("e:") ? h.slice(2) : undefined);

type Extra = {
  selected: boolean;
  active: boolean;
  project: Project;
  lint: LintDoc | null;
  trace: Trace | null;
  onOpen: (id: string) => void;
  onSimulateFrom: (id: string) => void;
  onRules: () => void;
};
type MNode = Node<MapsNodeData & Extra>;

function Simulated() {
  return (
    <span className="mp-mock" title="Simulate plays it; nothing on this page runs in the game. The bot's real login is scripts/ro_agent.py">
      SIMULATED
    </span>
  );
}

function LintLine({ lint, id }: { lint: LintDoc | null; id: string }) {
  if (!lint) return null;
  const l = lintLine(nodeLint(lint, id).counts);
  return (
    <div className="mp-status" data-level={l.level}>
      ● {l.text}
    </div>
  );
}

function RunLine({ trace, id }: { trace: Trace | null; id: string }) {
  if (!trace) return null;
  const b = trace.blocks[id];
  return <div className="mp-run">sim: {b ? `${b.visits} visit${b.visits === 1 ? "" : "s"} · ${b.time_s.toFixed(0)} s` : "not reached"}</div>;
}

/** React Flow measures a node's handles once; when a node's ports change (an exit's path moves
 * when a step is inserted above it, e.g. the stated save point; an exit is added), it must be told,
 * or the edge on the new handle is dropped (matpilot's round-6 review: "Couldn't create edge for
 * source handle id x:town.3", the town -> field link gone until a reload). A LAYOUT effect
 * (matpilot's re-check: with useEffect one error#008 was left): the new handle list is in before
 * the browser paints the edge on it. Client-only (ssr: false). */
function useHandles(id: string, sig: string) {
  const update = useUpdateNodeInternals();
  useLayoutEffect(() => update(id), [id, sig, update]);
}

function LoginNode({ id, data }: NodeProps<MNode>) {
  useHandles(id, "out");
  if (data.kind !== "login") return null;
  const l = loginOf(data.node);
  const server = l.server ? serverOf(l.server) : null;
  const cred = l.credential ? credentialOf(l.credential) : null;
  return (
    <div className="mp-node mp-session" data-selected={data.selected} data-active={data.active} data-testid={`map-node-${id}`}>
      <div className="mp-head">
        <span className="mp-title">Login</span>
        {data.start && <span className="mp-pill mp-pill-start">START</span>}
        <Simulated />
      </div>
      <div className="mp-line mp-wrap" title={`server: ${server?.title ?? l.server ?? "not set"}`}>
        <span className="mp-key">server</span> {server?.title ?? l.server ?? "not set"}
      </div>
      <div className="mp-line mp-wrap" title={`credential: ${l.credential ?? "not set"}${cred ? ` (${cred.title}); its id and password stay in the server's .env` : ""}`}>
        <span className="mp-key">credential</span> {l.credential ?? "not set"}
        {cred ? <span className="mp-muted"> · a name, the secret stays in .env</span> : null}
      </div>
      <div className="mp-line mp-muted">tabs: {tabList(data.node)}</div>
      <LintLine lint={data.lint} id={id} />
      <Handle type="source" position={Position.Right} id={OUT} className="mp-handle" />
    </div>
  );
}

function CharacterNode({ id, data }: NodeProps<MNode>) {
  useHandles(id, "in|out");
  if (data.kind !== "character") return null;
  const c = characterOf(data.node);
  return (
    <div className="mp-node mp-session" data-selected={data.selected} data-active={data.active} data-testid={`map-node-${id}`}>
      <Handle type="target" position={Position.Left} id={IN} className="mp-handle" />
      <div className="mp-head">
        <span className="mp-title">Choose character</span>
        <Simulated />
      </div>
      <div className="mp-line">
        <span className="mp-key">slot</span> {slotText(c)}
      </div>
      <div className="mp-line">
        <span className="mp-key">name</span> {c.name || "the account's own"}
      </div>
      <div className="mp-line mp-muted">tabs: {tabList(data.node)}</div>
      <LintLine lint={data.lint} id={id} />
      <Handle type="source" position={Position.Right} id={OUT} className="mp-handle" />
    </div>
  );
}

function portSig(data: MNode["data"]): string {
  if (data.kind !== "map") return "";
  const l = nodeLinks(data.project, data.node.id);
  return [...(l?.entries.map((e) => entryHandle(e.name)) ?? []), ...(l?.exits.map((x) => exitHandle(x.path)) ?? []), l?.respawnTo && l.respawnTo.node !== data.node.id ? RESPAWN : ""].join("|");
}

function MapNodeCard({ id, data }: NodeProps<MNode>) {
  useHandles(id, portSig(data));
  if (data.kind !== "map") return null;
  const n = data.node;
  const links = nodeLinks(data.project, n.id);
  const respawnTo = links?.respawnTo && links.respawnTo.node !== n.id ? links.respawnTo.map : null;
  const overrides = tabRows(data.project, n).flatMap((t) => t.rows.filter((r) => r.overrides).map((r) => r.name));
  return (
    <div className="mp-node mp-map mp-card" data-selected={data.selected} data-active={data.active} data-testid={`map-node-${id}`}>
      <Handle type="target" position={Position.Left} id={IN} className="mp-handle mp-handle-head" />
      <div className="mp-head">
        <MapIcon className="mp-map-icon" />
        <span className="mp-title">{n.map.map}</span>
        {data.first && <span className="mp-pill mp-pill-start">FIRST</span>}
      </div>
      <div className="mp-line mp-muted mp-wrap">
        {/* matpilot 12: no "xmas_dun02 · xmas_dun02": the node's id only when it is not the map's */}
        {n.id !== n.map.map ? (
          <>
            node <strong>{n.id}</strong> ·{" "}
          </>
        ) : null}
        tabs: {tabList(n)}
        {n.targets.length ? ` · ${n.targets.length} target${n.targets.length === 1 ? "" : "s"}` : ""}
      </div>
      {overrides.length > 0 && <div className="mp-line mp-muted mp-wrap">overrides Global: {overrides.join(", ")}</div>}
      <LintLine lint={data.lint} id={id} />
      <RunLine trace={data.trace} id={id} />
      <div className="mp-ports">
        <div className="mp-ports-col" data-side="in">
          <div className="mp-ports-head">entries</div>
          {(links?.entries ?? []).map((e) => (
            <div key={e.name} className="mp-port" data-side="in" title={`${e.name} at ${e.at ? `(${e.at.x}, ${e.at.y})` : "anywhere"}: ${entryCaption(e)}`} data-testid={`map-entry-${n.id}-${e.name}`}>
              <Handle type="target" position={Position.Left} id={entryHandle(e.name)} className="mp-dot" />
              <span className="mp-port-name">{e.name}</span>
              <span className="mp-port-cap">{entryCaption(e)}</span>
            </div>
          ))}
          {!links?.entries.length && <div className="mp-port-none">no entry: the bot cannot arrive</div>}
        </div>
        <div className="mp-ports-col" data-side="out">
          <div className="mp-ports-head">exits</div>
          {(links?.exits ?? []).map((x) => (
            <div key={x.path} className="mp-port" data-side="out" style={{ color: EXIT_COLOURS[x.kind] }} title={`${EXIT_WORDS[x.kind]}: ${x.how} → ${x.toNode} (${x.toEntry}); in the tab ${x.tab}`} data-testid={`map-exit-${x.path}`}>
              <span className="mp-port-name">→ {x.toMap ?? `${x.toNode}?`}</span>
              <span className="mp-port-cap">{x.toMap ? `${x.how}${x.tab !== "main" ? ` (tab ${x.tab})` : ""}` : "not a map of this project"}</span>
              <Handle type="source" position={Position.Right} id={exitHandle(x.path)} isConnectable={false} className="mp-dot" style={{ background: EXIT_COLOURS[x.kind] }} />
            </div>
          ))}
          {respawnTo && (
            <div className="mp-port" data-side="out" style={{ color: EXIT_COLOURS.death_respawn }} title="Derived: a death respawns at the save point">
              <span className="mp-port-name">→ {respawnTo}</span>
              <span className="mp-port-cap">a death respawns (derived)</span>
              <Handle type="source" position={Position.Right} id={RESPAWN} isConnectable={false} className="mp-dot" style={{ background: EXIT_COLOURS.death_respawn }} />
            </div>
          )}
          {!links?.exits.length && !respawnTo && <div className="mp-port-none">no exit: the run ends here</div>}
          <div className="mp-new" title="Drag from a dot onto another map to add an exit of that kind (its details are filled in on the node's tabs on /flows)">
            {PORTS.map((p) => (
              <div key={p.kind} className="mp-port mp-port-new" data-side="out" style={{ color: EXIT_COLOURS[p.kind] }}>
                <span className="mp-port-name">+ {p.label}</span>
                <Handle type="source" position={Position.Right} id={p.kind} className="mp-dot mp-dot-new" style={{ borderColor: EXIT_COLOURS[p.kind] }} />
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="mp-actions nodrag">
        <button type="button" className="mp-button" onClick={() => data.onOpen(n.id)} title={`Open ${n.id}'s tabs on /flows (or double-click the node)`}>
          Open flow
        </button>
        <button type="button" className="mp-button" onClick={() => data.onSimulateFrom(n.id)} title={`Simulate from ${n.id} (its entry), without the login`}>
          <PlayIcon className="mp-button-icon" />
          here
        </button>
      </div>
    </div>
  );
}

/** GLOBAL: the names every node imports (no ports: it is shared, not walked to). */
function GlobalNodeCard({ id, data }: NodeProps<MNode>) {
  if (data.kind !== "global") return null;
  const tabs = tabRows(data.project, data.node);
  const r = readRules(data.project);
  return (
    <div className="mp-node mp-global" data-selected={data.selected} data-testid={`map-node-${id}`}>
      <div className="mp-head">
        <span className="mp-title">Global</span>
        <span className="mp-pill mp-pill-shared" title="Every node imports Global's tabs; a node's own name overrides Global's there">
          shared by every node
        </span>
      </div>
      {tabs.length === 0 && <div className="mp-line mp-muted mp-wrap">no tabs yet: make one on /flows (functions, events, variables every node can use)</div>}
      {tabs.map((t) => (
        <div key={t.tab} className="mp-names">
          <div className="mp-names-tab">{t.tab}</div>
          {t.rows.length === 0 && <div className="mp-line mp-muted">empty</div>}
          {t.rows.map((x) => (
            <div key={x.name} className="mp-line mp-wrap" data-kind={x.kind} title={x.text}>
              <span className="mp-name">{x.kind === "event" ? `event ${x.name}` : x.kind === "var" ? x.text : `${x.name}()`}</span>
              {x.key && <span className="mp-muted"> · {x.key}</span>}
              {x.clash.length > 0 && <span className="mp-override"> · {x.key} also {x.clash.join(", ")}</span>}
              {x.overriddenOn.length > 0 && <span className="mp-override"> · overridden on {x.overriddenOn.join(", ")}</span>}
            </div>
          ))}
        </div>
      ))}
      <div className="mp-line mp-wrap mp-rule-line">
        <span className="mp-key">any other map</span>{" "}
        {r.custom ? "Global's own unexpected_map event" : r.unknownMap === "wing" ? `→ ${wingText(r.wingItem)} to the save point` : "→ the run stops (the built-in)"}
      </div>
      <LintLine lint={data.lint} id={id} />
      <div className="mp-actions nodrag">
        <button type="button" className="mp-button" onClick={() => data.onOpen(id)} title="Open Global's tabs on /flows (or double-click the node)">
          Open flow
        </button>
        <button type="button" className="mp-button" onClick={() => data.onRules()} title="The world rules: the save point and what happens on an unknown map">
          World rules
        </button>
      </div>
    </div>
  );
}

type ExitEdgeT = Edge<EdgeData & { runs?: number; active?: boolean }, "exit">;
// Edge labels of different kinds between the same two nodes would sit on one midpoint.
const LABEL_DY: Record<string, number> = { walk_exit: -30, npc_warp: -10, item_warp: 10, death_respawn: 30 };

function ExitEdge(props: EdgeProps<ExitEdgeT>) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, selected } = props;
  const [path, lx, ly] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition });
  const kind = data?.kind ?? "walk_exit";
  const colour = EXIT_COLOURS[kind] ?? "var(--muted)";
  const derived = data?.derived;
  const dy = (LABEL_DY[kind] ?? 0) + (sourceX > targetX ? 48 : 0); // a loop back: its label lower
  const entry = data && "entry" in data ? data.entry : null;
  const label = data?.label ?? `${kind.replace("_", " ")}${entry ? ` → ${entry}` : ""}${data?.runs ? ` · ${data.runs}×` : ""}${derived ? " (derived)" : ""}`;
  return (
    <>
      <BaseEdge id={id} path={path} style={{ stroke: colour, strokeWidth: selected || data?.active ? 3.5 : 2, strokeDasharray: derived ? "6 5" : undefined }} />
      <EdgeLabelRenderer>
        <div className="nodrag nopan mp-edge-label" style={{ transform: `translate(-50%, -50%) translate(${lx}px, ${ly + dy}px)`, color: colour }}>
          {label}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

type SessionEdgeT = Edge<EdgeData & { active?: boolean }, "session">;

function SessionEdge(props: EdgeProps<SessionEdgeT>) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, selected } = props;
  // round 6: the label sits ABOVE the session row (the cards are wider than the gaps between
  // them; matpilot: the labels read "en the cli", "cter s")
  const [path, lx] = getSmoothStepPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition });
  const label = data && data.kind === "session" ? data.label : "";
  return (
    <>
      <BaseEdge id={id} path={path} style={{ stroke: selected ? "var(--accent)" : "var(--neutral-border)", strokeWidth: selected || data?.active ? 3.5 : 2 }} />
      {label && (
        <EdgeLabelRenderer>
          <div className="nodrag nopan mp-edge-label" style={{ transform: `translate(-50%, -100%) translate(${lx}px, ${Math.min(sourceY, targetY) - 64}px)`, color: "var(--muted)" }}>
            {label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

const MIN_ZOOM = 0.85; // node text (0.86rem and up) stays >= 11 px
const MAX_ZOOM = 1.2;
const PAD = 24;

const nodeTypes = { login: LoginNode, character: CharacterNode, map: MapNodeCard, global: GlobalNodeCard };
const edgeTypes = { exit: ExitEdge, session: SessionEdge };
const MINIMAP: Record<string, string> = { map: "#a21caf", login: "#1d7a43", character: "#8a96a3", global: "#0f766e" };

export type MapsCanvasProps = {
  project: Project;
  lint: LintDoc | null;
  trace: Trace | null;
  selected: string | null;
  activeNode: string | null; // the playback's node
  activeEdge: string | null; // the playback's last connection or exit (an edge id)
  onSelect: (id: string | null) => void;
  onMove: (positions: Record<string, XY>) => void; // in the project's units
  onConnectSession: (from: string, to: string, entry?: string) => void;
  onDeleteSession: (from: string, to: string) => void;
  onConnectExit: (from: string, kind: AuthoredExit, to: string) => void;
  onRetargetExit: (path: string, to: string, entry?: string) => void;
  onDeleteExit: (path: string) => void;
  onOpen: (id: string) => void;
  onSimulateFrom: (id: string) => void;
  onRules: () => void;
};

function MapsCanvas(p: MapsCanvasProps) {
  const { project, lint, trace, selected, activeNode, activeEdge, onSelect, onMove, onConnectSession, onDeleteSession, onConnectExit, onRetargetExit, onDeleteExit, onOpen, onSimulateFrom, onRules } = p;
  const graph = useMemo(() => mapsGraph(project), [project]);
  const rf = useRef<ReactFlowInstance | null>(null);
  const wrap = useRef<HTMLDivElement | null>(null);
  const [overflow, setOverflow] = useState(false);
  const shape = graph.nodes.map((n) => n.id).join("|");
  // round 2: fit, but never below MIN_ZOOM (the text stays >= 11 px); a graph wider than the view
  // starts at its LEFT and pans, and only then a small minimap shows. Round 6: a graph too big for
  // the view opens on its MAP cards (and Global under them), the session row to the left.
  const fit = useCallback(() => {
    const inst = rf.current;
    const el = wrap.current;
    if (!inst || !el || !el.clientWidth || !el.clientHeight) return;
    const ns = inst.getNodes();
    if (!ns.length) return;
    const box = { width: el.clientWidth, height: el.clientHeight };
    // round 4: null while folded (0 x 0) or for any non-finite number: nothing is animated then
    let f = fitViewport(box, inst.getNodesBounds(ns), MIN_ZOOM, MAX_ZOOM, PAD);
    const maps = ns.filter((n) => n.type === "map");
    if (f?.overflow && maps.length && maps.length < ns.length) f = fitViewport(box, inst.getNodesBounds(maps), MIN_ZOOM, MAX_ZOOM, PAD) ?? f;
    if (!f) return;
    setOverflow(f.overflow);
    void inst.setViewport(f.viewport, { duration: 250 });
  }, []);
  useEffect(() => {
    const t = setTimeout(fit, 120);
    return () => clearTimeout(t);
  }, [shape, fit]);
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    let t: ReturnType<typeof setTimeout> | null = null;
    const ro = new ResizeObserver(() => {
      if (t) clearTimeout(t);
      t = setTimeout(fit, 150);
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      if (t) clearTimeout(t);
    };
  }, [fit]);
  // the playback's node out of view (a panned or a wide graph): bring it to the centre
  useEffect(() => {
    const inst = rf.current;
    const el = wrap.current;
    if (!inst || !el || !activeNode) return;
    const n = inst.getInternalNode(activeNode);
    if (!n) return;
    const at = n.internals.positionAbsolute;
    // round 4: a folded graph (0 x 0) is never panned (an animated pan over a zero-size view gave
    // React Flow a NaN zoom on every frame: its background dot's cx / cy / r)
    const c = followCentre({ width: el.clientWidth, height: el.clientHeight }, inst.getViewport(), { x: at.x, y: at.y, width: n.measured.width ?? 220, height: n.measured.height ?? 120 });
    if (c) void inst.setCenter(c.x, c.y, { zoom: c.zoom, duration: 300 });
  }, [activeNode]);
  const runs = useMemo(() => exitRuns(trace, graph.edges), [trace, graph]);
  const initial = useMemo(
    () =>
      graph.nodes.map((n) => ({
        id: n.id,
        type: n.type,
        position: n.position,
        data: { ...n.data, selected: n.id === selected, active: n.id === activeNode, project, lint, trace, onOpen, onSimulateFrom, onRules },
        deletable: false,
      })) as Node[],
    [graph, selected, activeNode, project, lint, trace, onOpen, onSimulateFrom, onRules],
  );
  const [view, setView] = useState<{ base: Node[]; nodes: Node[] }>({ base: initial, nodes: initial });
  if (view.base !== initial) {
    const measured = new Map(view.nodes.map((n) => [n.id, n.measured]));
    setView({ base: initial, nodes: initial.map((n) => ({ ...n, measured: measured.get(n.id) })) });
  }
  const nodes = view.base === initial ? view.nodes : initial;
  const derivedEdges = useMemo(
    () =>
      graph.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle,
        targetHandle: e.targetHandle,
        type: e.data.kind === "session" ? "session" : "exit",
        animated: e.id === activeEdge,
        data: { ...e.data, runs: runs.get(e.id), active: e.id === activeEdge },
        deletable: !e.data.derived,
        selectable: !e.data.derived,
        reconnectable: e.data.derived ? false : "target",
      })) as Edge[],
    [graph, runs, activeEdge],
  );
  const [edgeView, setEdgeView] = useState<{ base: Edge[]; edges: Edge[] }>({ base: derivedEdges, edges: derivedEdges });
  if (edgeView.base !== derivedEdges) setEdgeView({ base: derivedEdges, edges: derivedEdges });
  const edges = edgeView.base === derivedEdges ? edgeView.edges : derivedEdges;
  const onEdgesChange = useCallback((changes: EdgeChange[]) => {
    setEdgeView((v) => ({ ...v, edges: applyEdgeChanges(changes.filter((c) => c.type === "select"), v.edges) }));
  }, []);
  const onNodesChange = useCallback((changes: NodeChange[]) => {
    setView((v) => ({ ...v, nodes: applyNodeChanges(changes, v.nodes) }));
  }, []);
  // n8n's way: only connections the project allows are drawn at all (login -> character -> a map's
  // entry; a map's + port onto another map)
  const isValidConnection = useCallback(
    (c: Connection | Edge) => {
      if (!c.source || !c.target) return false;
      if (c.sourceHandle === OUT) return sessionLinkProblem(project, c.source, c.target, entryOf(c.targetHandle)) === null;
      if (isPort(c.sourceHandle)) return c.source !== c.target && project.nodes.some((n) => n.id === c.target && n.kind === "map");
      // an exit's end dragged onto another map (its own port `x:<path>`: onReconnect retargets it)
      if (c.sourceHandle?.startsWith("x:")) return project.nodes.some((n) => n.id === c.target && n.kind === "map");
      return false;
    },
    [project],
  );
  const onConnect = useCallback(
    (c: Connection) => {
      if (c.sourceHandle === OUT) onConnectSession(c.source, c.target, entryOf(c.targetHandle));
      else if (isPort(c.sourceHandle)) onConnectExit(c.source, c.sourceHandle, c.target);
    },
    [onConnectSession, onConnectExit],
  );
  // dragging a connection's END onto another node moves it (a session connection, or an exit's target)
  const onReconnect = useCallback(
    (old: Edge, c: Connection) => {
      const d = old.data as EdgeData | undefined;
      if (!d || d.derived) return;
      if (d.kind === "session") {
        if (c.source !== old.source || sessionLinkProblem(project, c.source, c.target, entryOf(c.targetHandle)) !== null) return;
        onConnectSession(c.source, c.target, entryOf(c.targetHandle));
      } else if (project.nodes.some((n) => n.id === c.target && n.kind === "map")) onRetargetExit(d.path, c.target, entryOf(c.targetHandle));
    },
    [project, onConnectSession, onRetargetExit],
  );
  const onEdgesDelete = useCallback(
    (es: Edge[]) => {
      for (const e of es) {
        const d = e.data as EdgeData | undefined;
        if (!d || d.derived) continue;
        if (d.kind === "session") onDeleteSession(d.from, d.to);
        else onDeleteExit(d.path);
      }
    },
    [onDeleteSession, onDeleteExit],
  );

  return (
    <div className="h-full w-full" ref={wrap} data-testid="maps-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={(_, __, dragged) => onMove(Object.fromEntries(dragged.map((n) => [n.id, toUnits(n.position)])))}
        isValidConnection={isValidConnection}
        onConnect={onConnect}
        onReconnect={onReconnect}
        onEdgesDelete={onEdgesDelete}
        onNodeClick={(_, n) => onSelect(n.id)}
        onPaneClick={() => onSelect(null)}
        onNodeDoubleClick={(_, n) => onOpen(n.id)}
        zoomOnDoubleClick={false}
        deleteKeyCode={["Delete", "Backspace"]}
        colorMode="system"
        onInit={(inst) => {
          rf.current = inst as unknown as ReactFlowInstance;
        }}
        fitView
        fitViewOptions={{ padding: 0.12, minZoom: MIN_ZOOM, maxZoom: MAX_ZOOM }}
        proOptions={{ hideAttribution: false }}
        attributionPosition="top-right"
        minZoom={0.2}
      >
        <Background gap={24} />
        {/* round 6: Fit is OURS (the maps first, never below MIN_ZOOM: text >= 11 px); React Flow's
            own went to 0.41 (5 px text) */}
        <Controls showInteractive={false} showFitView={false}>
          <ControlButton onClick={fit} title="Fit the maps" aria-label="Fit the maps" data-testid="maps-fit">
            <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" focusable="false">
              <path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4" fill="none" stroke="currentColor" strokeWidth="1.8" />
            </svg>
          </ControlButton>
        </Controls>
        {overflow && (
          <MiniMap position="bottom-right" pannable zoomable style={{ width: 120, height: 80 }} nodeColor={(n) => MINIMAP[n.type ?? ""] ?? "#8a96a3"} data-testid="maps-minimap" />
        )}
      </ReactFlow>
    </div>
  );
}

export default memo(MapsCanvas);
