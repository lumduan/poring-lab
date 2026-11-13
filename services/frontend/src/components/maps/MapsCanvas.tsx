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
  ControlButton,
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
  useUpdateNodeInternals,
} from "@xyflow/react";
import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { EXIT_COLOURS, ExitEdge } from "@/components/flows/FlowCanvas";
import { MapIcon, PlayIcon } from "@/components/maps/icons";
import type { LintDoc, Trace } from "@/lib/flow/api";
import { type GEdge, savePointBlock, type XY } from "@/lib/flow/canvas";
import type { AuthoredExit, Flow, MapBlock } from "@/lib/flow/ir";
import { blockRunLine, edgeRuns, lintLine, lintOf } from "@/lib/flow/status";
import { entryHandle, exitHandle, fitViewport, followCentre, mapsGraph, type MapsNodeData } from "@/lib/maps/graph";
import { blockLinks, entryCaption, EXIT_WORDS } from "@/lib/maps/links";
import { ACCOUNTS, serverOf, type Session, slotText } from "@/lib/maps/session";

const PORTS: { kind: AuthoredExit; label: string }[] = [
  { kind: "walk_exit", label: "walk to a warp" },
  { kind: "npc_warp", label: "NPC / Kafra warp" },
  { kind: "item_warp", label: "Butterfly Wing" },
];

type Extra = { selected: boolean; active: boolean; flow: Flow; lint: LintDoc | null; trace: Trace | null; onOpenFlow: (block: string) => void; onSimulateFrom: (block: string) => void; onRules: () => void };
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
      <div className="mp-line mp-wrap" title={`server: ${server ? server.title : s.server}`}>
        <span className="mp-key">server</span> {server ? server.title : s.server}
      </div>
      <div className="mp-line mp-wrap" title={`account: ${acc?.title ?? s.account} (from the server)`}>
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

/** React Flow measures a node's handles once; when a node's ports change (an exit's path moves
 * when a step is inserted above it, e.g. the stated save point; an exit is added), it must be told,
 * or the edge on the new handle is dropped (matpilot's round-6 review: "Couldn't create edge for
 * source handle id x:town.3", the town -> field link gone until a reload). */
function useHandles(id: string, sig: string) {
  const update = useUpdateNodeInternals();
  // a LAYOUT effect (matpilot's re-check: with useEffect one error#008 was left after State it):
  // the new handle list is in before the browser paints the edge on it. Client-only (ssr: false)
  useLayoutEffect(() => update(id), [id, sig, update]);
}

function portSig(data: MNode["data"]): string {
  if (data.kind === "map") {
    const b = data.block;
    const l = blockLinks(data.flow, b.name);
    const sp = savePointBlock(data.flow);
    return [...(l?.entries.map((e) => `e:${e.name}`) ?? []), ...(l?.exits.map((x) => `x:${x.path}`) ?? []), sp.block && sp.block !== b.name ? "respawn" : ""].join("|");
  }
  if (data.kind === "unknown") return data.rules.unknownMap;
  return "";
}

function MapNode({ id, data }: NodeProps<MNode>) {
  useHandles(id, portSig(data));
  if (data.kind !== "map") return null;
  const b = data.block;
  const l = data.lint ? lintLine(lintOf(data.lint, `block:${b.name}`)) : null;
  const run = blockRunLine(data.trace, b.name);
  const n = flowSize(b);
  const links = blockLinks(data.flow, b.name);
  const sp = savePointBlock(data.flow);
  const respawnTo = sp.block && sp.block !== b.name ? data.flow.workflow?.blocks.find((x) => x.name === sp.block)?.map.map : null;
  return (
    <div className="mp-node mp-map mp-card" data-selected={data.selected} data-active={data.active} data-testid={`map-node-${b.name}`}>
      <Handle type="target" position={Position.Left} id="in" className="mp-handle mp-handle-head" />
      <div className="mp-head">
        <MapIcon className="mp-map-icon" />
        <span className="mp-title">{b.map.map}</span>
        {data.start && <span className="fc-start">FIRST</span>}
      </div>
      <div className="mp-line mp-muted">
        its flow: <strong>{b.name}</strong> · {n} block{n === 1 ? "" : "s"}
        {b.targets.length ? ` · ${b.targets.length} target${b.targets.length === 1 ? "" : "s"}` : ""}
      </div>
      {l && (
        <div className="fc-status" data-level={l.level}>
          ● {l.text}
        </div>
      )}
      {run && <div className="fc-run">sim: {run}</div>}
      <div className="mp-ports">
        <div className="mp-ports-col" data-side="in">
          <div className="mp-ports-head">entries</div>
          {(links?.entries ?? []).map((e) => (
            <div key={e.name} className="mp-port" data-side="in" title={`${e.name} at ${e.at ? `(${e.at.x}, ${e.at.y})` : "anywhere"}: ${entryCaption(e)}`} data-testid={`map-entry-${b.name}-${e.name}`}>
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
            <div key={x.path} className="mp-port" data-side="out" style={{ color: EXIT_COLOURS[x.kind] }} title={`${EXIT_WORDS[x.kind]}: ${x.how} → ${x.toBlock} (${x.toEntry})`} data-testid={`map-exit-${x.path}`}>
              <span className="mp-port-name">→ {x.toMap ?? `${x.toBlock}?`}</span>
              <span className="mp-port-cap">{x.toMap ? x.how : "not a map of this flow"}</span>
              <Handle type="source" position={Position.Right} id={exitHandle(x.path)} isConnectable={false} className="mp-dot" style={{ background: EXIT_COLOURS[x.kind] }} />
            </div>
          ))}
          {respawnTo && (
            <div className="mp-port" data-side="out" style={{ color: EXIT_COLOURS.death_respawn }} title="Derived: a death respawns at the save point">
              <span className="mp-port-name">→ {respawnTo}</span>
              <span className="mp-port-cap">a death respawns (derived)</span>
              <Handle type="source" position={Position.Right} id="death_respawn" isConnectable={false} className="mp-dot" style={{ background: EXIT_COLOURS.death_respawn }} />
            </div>
          )}
          {!links?.exits.length && !respawnTo && <div className="mp-port-none">no exit: the run ends here</div>}
          <div className="mp-new" title="Drag from a dot onto another map to add an exit of that kind (its details are filled in on the map's flow)">
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
        <button type="button" className="mp-button" onClick={() => data.onOpenFlow(b.name)} title={`Open ${b.map.map}'s flow (${b.name}) on /flows`}>
          Open flow
        </button>
        <button type="button" className="mp-button" onClick={() => data.onSimulateFrom(b.name)} title={`Simulate from ${b.name} (its entry), without the login`}>
          <PlayIcon className="mp-button-icon" />
          here
        </button>
      </div>
    </div>
  );
}

/** "Any other map": the world rule for a map none of the map nodes is on (rules.ts). */
function UnknownNode({ id, data }: NodeProps<MNode>) {
  useHandles(id, portSig(data));
  if (data.kind !== "unknown") return null;
  const r = data.rules;
  const wing = r.unknownMap === "wing";
  const save = r.savePoint.cell?.map ?? (data.saveBlock ? data.flow.workflow?.blocks.find((x) => x.name === data.saveBlock)?.map.map : null);
  return (
    <div className="mp-node mp-unknown" data-selected={data.selected} data-rule={wing ? "wing" : "stop"} data-testid="map-node-unknown">
      <div className="mp-head">
        <span className="mp-q" aria-hidden="true">
          ?
        </span>
        <span className="mp-title">Any other map</span>
        <span className="mp-rule-pill">world rule</span>
      </div>
      <div className="mp-line mp-muted mp-wrap">a map none of the {data.maps} map node{data.maps === 1 ? " is" : "s are"} on, e.g. a teleport walked into by accident</div>
      <div className="mp-line">
        {r.custom ? "this flow writes its own unexpected_map event (/flows, events)" : wing ? `→ a Butterfly Wing to the save point${save ? ` (${save})` : ": not known yet, state it"}` : "→ the run stops there (the built-in)"}
      </div>
      {/* always rendered (matpilot round 6): the edge and its handle must not appear in one render */}
      <div className="mp-port" data-side="out" style={{ color: EXIT_COLOURS.item_warp, visibility: wing ? "visible" : "hidden" }}>
        <span className="mp-port-cap">wing home</span>
        <Handle type="source" position={Position.Right} id="out" isConnectable={false} className="mp-dot" style={{ background: EXIT_COLOURS.item_warp }} />
      </div>
      <div className="mp-actions nodrag">
        <button type="button" className="mp-button" onClick={() => data.onRules()} title="The world rules: the save point and what happens on an unknown map">
          World rules
        </button>
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
  // round 6: the label sits ABOVE the session row (the cards are wider than the gaps between
  // them; matpilot: the labels read "en the cli", "cter s")
  const [path, lx] = getSmoothStepPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition });
  return (
    <>
      <BaseEdge id={id} path={path} style={{ stroke: "var(--neutral-border)", strokeWidth: data?.active ? 3.5 : 2 }} />
      {data?.label && (
        <EdgeLabelRenderer>
          <div className="nodrag nopan fc-edge-label" style={{ transform: `translate(-50%, -100%) translate(${lx}px, ${Math.min(sourceY, targetY) - 64}px)`, color: "var(--muted)" }}>
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

const nodeTypes = { start: StartNode, login: LoginNode, character: CharacterNode, map: MapNode, main: MainNode, unknown: UnknownNode };
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
  onRules: () => void;
};

function MapsCanvas(p: MapsCanvasProps) {
  const { flow, session, positions, lint, trace, selected, activeNode, activeEdge, onSelect, onMove, onConnectExit, onDeleteExit, onOpenFlow, onSimulateFrom, onRules } = p;
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
    const box = { width: el.clientWidth, height: el.clientHeight };
    // round 4: null while folded (0 x 0) or for any non-finite number: nothing is animated then
    let f = fitViewport(box, inst.getNodesBounds(ns), MIN_ZOOM, MAX_ZOOM, PAD);
    // round 6 (matpilot: at 1440 x 900 one map in view, the session row took the first 650 px): a
    // graph too big for the view opens on its MAPS (and Any other map), the session row to the left
    // the MAP cards only: Any other map sits left of them (under the session row), and with it the
    // box began at the session row and never reached field_1 (matpilot's re-check, 1440 x 900)
    const maps = ns.filter((n) => n.type === "map" || n.type === "main");
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
        data: { ...n.data, selected: n.id === selected, active: n.id === activeNode, flow, lint, trace, onOpenFlow, onSimulateFrom, onRules },
        deletable: false,
      })) as Node[],
    [graph, selected, activeNode, flow, lint, trace, onOpenFlow, onSimulateFrom, onRules],
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
          <MiniMap
            position="bottom-right"
            pannable
            zoomable
            style={{ width: 120, height: 80 }}
            nodeColor={(n) => (n.type === "map" ? "#a21caf" : n.type === "start" ? "#1d7a43" : n.type === "unknown" ? "#f5a623" : "#8a96a3")}
            data-testid="maps-minimap"
          />
        )}
      </ReactFlow>
    </div>
  );
}

export default memo(MapsCanvas);
