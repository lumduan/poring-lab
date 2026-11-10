"use client";

// The Maps page's GRAPH (React Flow, Node-RED / n8n's way of placing blocks; Batt 2026-11-10):
// START -> Login -> Choose character -> the flow's map nodes, joined by their typed exits. The graph
// is DERIVED (lib/maps/graph.ts over lib/flow/canvas.ts); drawing an exit from a map node's port
// onto another map node, or deleting one, edits the IR as /flows' Map tab does. The session nodes
// are the page's MOCK (never IR). During a playback the node the character is in glows and the
// exit it last took is drawn thicker. Ideas from Node-RED (typed ports, status lines); no code from
// it or from n8n.
import "@xyflow/react/dist/style.css";

import {
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  BaseEdge,
  type Connection,
  Controls,
  type Edge,
  type EdgeChange,
  EdgeLabelRenderer,
  type EdgeProps,
  getSmoothStepPath,
  Handle,
  MiniMap,
  type Node,
  type NodeChange,
  type NodeProps,
  Position,
  ReactFlow,
  type ReactFlowInstance,
} from "@xyflow/react";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { EXIT_COLOURS, ExitEdge } from "@/components/flows/FlowCanvas";
import { PlayIcon } from "@/components/maps/icons";
import type { LintDoc, Trace } from "@/lib/flow/api";
import type { GEdge, XY } from "@/lib/flow/canvas";
import type { AuthoredExit, Flow, MapBlock } from "@/lib/flow/ir";
import { blockRunLine, edgeRuns, lintLine, lintOf } from "@/lib/flow/status";
import { fitViewport, followCentre, mapsGraph, type MapsNodeData } from "@/lib/maps/graph";
import { ACCOUNTS, serverOf, type Session, slotText } from "@/lib/maps/session";

const PORTS: { kind: AuthoredExit; label: string }[] = [
  { kind: "walk_exit", label: "walk exit" },
  { kind: "npc_warp", label: "npc warp" },
  { kind: "item_warp", label: "item warp" },
];

type Extra = { selected: boolean; active: boolean; lint: LintDoc | null; trace: Trace | null; onOpenFlow: (block: string) => void; onSimulateFrom: (block: string) => void };
type MNode = Node<MapsNodeData & Extra>;

function Mock() {
  return (
    <span className="mp-mock" title="A mock: simulated only. The bot's real login is scripts/ro_agent.py">
      MOCK
    </span>
  );
}

function StartNode({ data }: NodeProps<MNode>) {
  return (
    <div className="mp-node mp-start" data-selected={data.selected} data-active={data.active}>
      START
      <Handle type="source" position={Position.Right} id="out" className="mp-handle" />
    </div>
  );
}

function LoginNode({ data }: NodeProps<MNode>) {
  if (data.kind !== "login") return null;
  const s: Session = data.session;
  const server = serverOf(s.server);
  const acc = ACCOUNTS.find((a) => a.id === s.account);
  return (
    <div className="mp-node mp-session" data-selected={data.selected} data-active={data.active}>
      <Handle type="target" position={Position.Left} id="in" className="mp-handle" />
      <div className="mp-head">
        <span className="mp-title">Login</span>
        <Mock />
      </div>
      <div className="mp-line">
        <span className="mp-key">server</span> {server ? server.title : s.server}
      </div>
      <div className="mp-line">
        <span className="mp-key">account</span> {acc?.title ?? s.account} (from the server)
      </div>
      <div className="mp-call">to_char_select(…, &quot;{s.account}&quot;)</div>
      <Handle type="source" position={Position.Right} id="out" className="mp-handle" />
    </div>
  );
}

function CharacterNode({ data }: NodeProps<MNode>) {
  if (data.kind !== "character") return null;
  return (
    <div className="mp-node mp-session" data-selected={data.selected} data-active={data.active}>
      <Handle type="target" position={Position.Left} id="in" className="mp-handle" />
      <div className="mp-head">
        <span className="mp-title">Choose character</span>
        <Mock />
      </div>
      <div className="mp-line">
        <span className="mp-key">slot</span> {slotText(data.session)}
      </div>
      <div className="mp-line">
        <span className="mp-key">name</span> {data.session.char || "the account's own (.env)"}
      </div>
      <div className="mp-call">enter_game(…, &quot;{data.session.account}&quot;)</div>
      <Handle type="source" position={Position.Right} id="out" className="mp-handle" />
    </div>
  );
}

function flowSize(b: MapBlock): number {
  let n = 0;
  const count = (stmts: MapBlock["main"]) => {
    for (const s of stmts) {
      n++;
      if (s.kind === "if") {
        count(s.then);
        count(s.orelse);
      }
      if (s.kind === "while" || s.kind === "repeat" || s.kind === "for") count(s.body);
    }
  };
  count(b.main);
  return n;
}

function MapNode({ data }: NodeProps<MNode>) {
  if (data.kind !== "map") return null;
  const b = data.block;
  const l = data.lint ? lintLine(lintOf(data.lint, `block:${b.name}`)) : null;
  const run = blockRunLine(data.trace, b.name);
  const n = flowSize(b);
  return (
    <div className="mp-node mp-map" data-selected={data.selected} data-active={data.active} data-testid={`map-node-${b.name}`}>
      <Handle type="target" position={Position.Left} id="in" className="mp-handle" />
      <div className="mp-head">
        {data.start && <span className="fc-start">FIRST</span>}
        <span className="mp-title">{b.map.map}</span>
      </div>
      <div className="mp-line mp-muted">
        block {b.name}
        {data.startEntry ? ` · enters at ${data.startEntry}` : ` · ${b.entries.length} entr${b.entries.length === 1 ? "y" : "ies"}`}
      </div>
      <div className="mp-line">
        <span className="mp-key">its flow</span> {n} block{n === 1 ? "" : "s"}
        {b.targets.length ? ` · targets ${b.targets.length}` : ""}
      </div>
      {l && (
        <div className="fc-status" data-level={l.level}>
          ● {l.text}
        </div>
      )}
      {run && <div className="fc-run">sim: {run}</div>}
      <div className="mp-actions nodrag">
        <button type="button" className="mp-button" onClick={() => data.onOpenFlow(b.name)} title={`Open ${b.name}'s flow on /flows`}>
          Open flow
        </button>
        <button type="button" className="mp-button" onClick={() => data.onSimulateFrom(b.name)} title={`Simulate from ${b.name} (its entry), without the login`}>
          <PlayIcon className="mp-button-icon" />
          here
        </button>
      </div>
      <div className="fc-ports">
        {PORTS.map((p) => (
          <div key={p.kind} className="fc-port" style={{ color: EXIT_COLOURS[p.kind] }}>
            {p.label}
            <Handle type="source" position={Position.Right} id={p.kind} className="!h-2.5 !w-2.5" style={{ background: EXIT_COLOURS[p.kind], right: -14 }} />
          </div>
        ))}
        <div className="fc-port" style={{ color: EXIT_COLOURS.death_respawn }}>
          death respawn
          <Handle type="source" position={Position.Right} id="death_respawn" isConnectable={false} className="!h-2.5 !w-2.5" style={{ background: EXIT_COLOURS.death_respawn, right: -14 }} />
        </div>
      </div>
    </div>
  );
}

function MainNode({ data }: NodeProps<MNode>) {
  if (data.kind !== "main") return null;
  return (
    <div className="mp-node mp-map" data-selected={data.selected} data-active={data.active}>
      <Handle type="target" position={Position.Left} id="in" className="mp-handle" />
      <div className="mp-title">main (a plain flow)</div>
      <div className="mp-line mp-muted">{data.statements} statement(s), no map blocks: Load ▸ a workflow to place maps</div>
    </div>
  );
}

type SessionEdgeT = Edge<{ kind: "session"; label: string; active?: boolean }, "session">;

function SessionEdge(props: EdgeProps<SessionEdgeT>) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data } = props;
  const [path, lx, ly] = getSmoothStepPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition });
  return (
    <>
      <BaseEdge id={id} path={path} style={{ stroke: "var(--neutral-border)", strokeWidth: data?.active ? 3.5 : 2 }} />
      {data?.label && (
        <EdgeLabelRenderer>
          <div className="nodrag nopan fc-edge-label" style={{ transform: `translate(-50%, -50%) translate(${lx}px, ${ly - 12}px)`, color: "var(--muted)" }}>
            {data.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

const MIN_ZOOM = 0.85; // node text (0.86rem and up) stays >= 11 px
const MAX_ZOOM = 1.2;
const PAD = 24;

const nodeTypes = { start: StartNode, login: LoginNode, character: CharacterNode, map: MapNode, main: MainNode };
const edgeTypes = { exit: ExitEdge, session: SessionEdge };

export type MapsCanvasProps = {
  flow: Flow;
  session: Session;
  positions: Record<string, XY>;
  lint: LintDoc | null;
  trace: Trace | null;
  selected: string | null;
  activeNode: string | null; // the playback's node
  activeEdge: string | null; // the playback's last exit (an edge id)
  onSelect: (id: string | null) => void;
  onMove: (positions: Record<string, XY>) => void;
  onConnectExit: (from: string, kind: AuthoredExit, to: string) => void;
  onDeleteExit: (path: string) => void;
  onOpenFlow: (block: string) => void;
  onSimulateFrom: (block: string) => void;
};

function MapsCanvas(p: MapsCanvasProps) {
  const { flow, session, positions, lint, trace, selected, activeNode, activeEdge, onSelect, onMove, onConnectExit, onDeleteExit, onOpenFlow, onSimulateFrom } = p;
  const graph = useMemo(() => mapsGraph(flow, session, positions), [flow, session, positions]);
  const rf = useRef<ReactFlowInstance | null>(null);
  const wrap = useRef<HTMLDivElement | null>(null);
  const [overflow, setOverflow] = useState(false);
  const shape = graph.nodes.map((n) => n.id).join("|");
  // round 2: fit, but never below MIN_ZOOM (the text stays >= 11 px); a graph wider than the view
  // starts at its LEFT (START) and pans, and only then a small minimap shows
  const fit = useCallback(() => {
    const inst = rf.current;
    const el = wrap.current;
    if (!inst || !el || !el.clientWidth || !el.clientHeight) return;
    const ns = inst.getNodes();
    if (!ns.length) return;
    // round 4: null while folded (0 x 0) or for any non-finite number: nothing is animated then
    const f = fitViewport({ width: el.clientWidth, height: el.clientHeight }, inst.getNodesBounds(ns), MIN_ZOOM, MAX_ZOOM, PAD);
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
    // round 4: a folded graph (0 x 0) is never panned: an animated pan over a zero-size view gave
    // React Flow a NaN zoom on every frame (its background dot's cx / cy / r)
    const c = followCentre(
      { width: el.clientWidth, height: el.clientHeight },
      inst.getViewport(),
      { x: at.x, y: at.y, width: n.measured.width ?? 220, height: n.measured.height ?? 120 },
    );
    if (c) void inst.setCenter(c.x, c.y, { zoom: c.zoom, duration: 300 });
  }, [activeNode]);
  const runs = useMemo(() => edgeRuns(trace, graph.edges.filter((e) => e.data.kind !== "session") as GEdge[]), [trace, graph]);
  const initial = useMemo(
    () =>
      graph.nodes.map((n) => ({
        id: n.id,
        type: n.type,
        position: n.position,
        data: { ...n.data, selected: n.id === selected, active: n.id === activeNode, lint, trace, onOpenFlow, onSimulateFrom },
        deletable: false,
      })) as Node[],
    [graph, selected, activeNode, lint, trace, onOpenFlow, onSimulateFrom],
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
  const onConnect = useCallback(
    (c: Connection) => {
      const kind = c.sourceHandle as AuthoredExit;
      if (!c.source.startsWith("block:") || !c.target.startsWith("block:")) return;
      if (!PORTS.some((x) => x.kind === kind)) return;
      onConnectExit(c.source.slice(6), kind, c.target.slice(6));
    },
    [onConnectExit],
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
        onNodeDragStop={(_, __, dragged) => onMove(Object.fromEntries(dragged.map((n) => [n.id, n.position])))}
        onConnect={onConnect}
        onEdgesDelete={(es) => es.forEach((e) => e.id.startsWith("exit:") && onDeleteExit(e.id.slice(5)))}
        onNodeClick={(_, n) => onSelect(n.id)}
        onPaneClick={() => onSelect(null)}
        onNodeDoubleClick={(_, n) => n.id.startsWith("block:") && onOpenFlow(n.id.slice(6))}
        zoomOnDoubleClick={false}
        deleteKeyCode={["Delete", "Backspace"]}
        colorMode="system"
        onInit={(inst) => {
          rf.current = inst as unknown as ReactFlowInstance;
        }}
        fitView
        fitViewOptions={{ padding: 0.12, minZoom: MIN_ZOOM, maxZoom: MAX_ZOOM }}
        proOptions={{ hideAttribution: false }}
        minZoom={0.2}
      >
        <Background gap={24} />
        <Controls showInteractive={false} />
        {overflow && (
          <MiniMap
            position="top-right"
            pannable
            zoomable
            style={{ width: 120, height: 80 }}
            nodeColor={(n) => (n.type === "map" ? "#a21caf" : n.type === "start" ? "#1d7a43" : "#8a96a3")}
            data-testid="maps-minimap"
          />
        )}
      </ReactFlow>
    </div>
  );
}

export default memo(MapsCanvas);
