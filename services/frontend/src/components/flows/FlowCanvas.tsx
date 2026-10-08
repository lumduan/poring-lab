"use client";

// The workflow canvas (MW2 level 1, React Flow): map blocks joined by typed exits, the global and
// per-map event nodes, a status line under every node (lint, then the last simulate run). The
// graph is DERIVED from the IR (lib/flow/canvas.ts); drawing or deleting an exit edits the IR.
// Ideas from Node-RED (status badges, typed ports); no code from it or from n8n.
import "@xyflow/react/dist/style.css";

import {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  type Edge,
  type EdgeProps,
  getBezierPath,
  Handle,
  MiniMap,
  type Node,
  type NodeProps,
  Position,
  ReactFlow,
  type Connection,
  type NodeChange,
  type ReactFlowInstance,
  applyNodeChanges,
} from "@xyflow/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { CatalogueDoc, LintDoc, Trace } from "@/lib/flow/api";
import { type GEdge, type GNode, type NodeData, toGraph, type XY } from "@/lib/flow/canvas";
import type { AuthoredExit, Flow, MapEvent } from "@/lib/flow/ir";
import { SAFETY_CRITICAL } from "@/lib/flow/ir";
import { blockRunLine, edgeRuns, lintLine, lintOf } from "@/lib/flow/status";

export const EXIT_COLOURS: Record<string, string> = {
  walk_exit: "#4c97ff",
  npc_warp: "#b07cff",
  item_warp: "#f5a623",
  death_respawn: "#ff5d5d",
  attach: "#6b7280",
};
const PORTS: { kind: string; label: string }[] = [
  { kind: "walk_exit", label: "walk exit" },
  { kind: "npc_warp", label: "npc warp" },
  { kind: "item_warp", label: "item warp" },
  { kind: "death_respawn", label: "death respawn" },
];
// Edge labels of different kinds between the same two blocks would sit on one midpoint.
const LABEL_DY: Record<string, number> = { walk_exit: -30, npc_warp: -10, item_warp: 10, death_respawn: 30, attach: 0 };

/** The safety-critical lock (13.6.1: extend only, never override or disable). */
function Lock() {
  return (
    <svg viewBox="0 0 12 14" className="mr-1 inline-block h-3 w-3 align-[-1px]" aria-label="safety-critical: extend only">
      <path d="M3 6V4a3 3 0 0 1 6 0v2" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <rect x="1.5" y="6" width="9" height="7" rx="1.5" fill="currentColor" />
    </svg>
  );
}

const LEVEL_CLASS: Record<string, string> = {
  error: "text-red-300",
  warning: "text-amber-300",
  unsupported: "text-sky-300",
  info: "text-neutral-300",
  ok: "text-emerald-300",
};

type Extra = { lint: LintDoc | null; trace: Trace | null; selected: boolean; stale: boolean };
type MapNodeT = Node<NodeData & Extra, "map">;
type EventsNodeT = Node<NodeData & Extra, "events">;
type MainNodeT = Node<NodeData & Extra, "main">;

function StatusLine({ owner, lint, stale }: { owner: string; lint: LintDoc | null; stale: boolean }) {
  if (!lint) return <div className="text-[11px] text-neutral-500">not linted yet</div>;
  const l = lintLine(lintOf(lint, owner));
  return (
    <div className={`text-[11px] ${LEVEL_CLASS[l.level]} ${stale ? "opacity-50" : ""}`}>
      ● {l.text}
      {stale ? " (stale)" : ""}
    </div>
  );
}

function MapNode({ data }: NodeProps<MapNodeT>) {
  if (data.kind !== "map") return null;
  const b = data.block;
  const run = blockRunLine(data.trace, b.name);
  return (
    <div
      className={`min-w-[230px] rounded-lg border bg-neutral-900 px-3 py-2 shadow-lg ${
        data.selected ? "border-sky-400" : "border-neutral-600"
      }`}
    >
      <Handle type="target" position={Position.Left} id="in" className="!h-3 !w-3 !bg-neutral-300" />
      <div className="flex items-center gap-2">
        {data.start && <span className="rounded bg-emerald-700 px-1.5 text-[10px] font-semibold">START</span>}
        <span className="font-semibold">{b.name}</span>
      </div>
      <div className="text-[11px] text-neutral-400">
        map {b.map.map}
        {data.startEntry ? ` · entry ${data.startEntry}` : ` · ${b.entries.length} entr${b.entries.length === 1 ? "y" : "ies"}`}
      </div>
      {(b.targets.length > 0 || b.ignore.length > 0) && (
        <div className="text-[11px] text-neutral-400">
          targets {b.targets.map((m) => m.id).join(", ") || "-"} · ignore {b.ignore.map((m) => m.id).join(", ") || "-"}
        </div>
      )}
      <StatusLine owner={`block:${b.name}`} lint={data.lint} stale={data.stale} />
      {run && <div className="text-[11px] text-fuchsia-300">sim: {run}</div>}
      <div className="mt-1 flex flex-col items-end gap-0.5">
        {PORTS.map((p) => (
          <div key={p.kind} className="relative pr-2 text-[10px]" style={{ color: EXIT_COLOURS[p.kind] }}>
            {p.label}
            <Handle
              type="source"
              position={Position.Right}
              id={p.kind}
              isConnectable={p.kind !== "death_respawn"}
              className="!h-2.5 !w-2.5"
              style={{ background: EXIT_COLOURS[p.kind], right: -14 }}
            />
          </div>
        ))}
      </div>
      <Handle type="target" position={Position.Bottom} id="events" className="!h-2 !w-2 !bg-neutral-500" />
    </div>
  );
}

function eventRow(ev: MapEvent): { mode: string; key: string; detail: string } {
  if (ev.kind === "disable") return { mode: "DISABLE", key: ev.key, detail: "" };
  if (ev.kind === "extend") return { mode: "EXTEND", key: ev.key, detail: `${ev.steps.length} step(s)` };
  const h = ev.event;
  return { mode: ev.kind === "override" ? "OVERRIDE" : "ADD", key: h.name, detail: `${h.priority} · ${h.mode}` };
}

function EventsNode({ data }: NodeProps<EventsNodeT>) {
  if (data.kind !== "events") return null;
  const rows =
    data.scope === "global"
      ? data.handlers.map((h) => ({ mode: "GLOBAL", key: h.name, detail: `${h.priority} · ${h.mode} · then ${h.then}` }))
      : data.events.map(eventRow);
  const owner = data.scope === "global" ? "global" : `block:${data.block}`;
  return (
    <div
      className={`min-w-[230px] rounded-lg border border-dashed bg-neutral-950 px-3 py-2 ${
        data.selected ? "border-sky-400" : "border-pink-500/70"
      }`}
    >
      {data.scope === "block" && <Handle type="source" position={Position.Top} id="attach" className="!h-2 !w-2 !bg-neutral-500" />}
      <div className="text-xs font-semibold text-pink-300">
        {data.scope === "global" ? "Global events (every map)" : `${data.block} · map events`}
      </div>
      <ul className="mt-1 space-y-0.5">
        {rows.map((r) => (
          <li key={`${r.mode}:${r.key}`} className="flex gap-1.5 text-[11px]">
            <span className="w-16 shrink-0 text-neutral-400">{r.mode}</span>
            <span className="font-medium">
              {SAFETY_CRITICAL.includes(r.key) && <Lock />}
              {r.key}
            </span>
            <span className="text-neutral-500">{r.detail}</span>
          </li>
        ))}
        {rows.length === 0 && <li className="text-[11px] text-neutral-500">none</li>}
      </ul>
      {data.scope === "global" && <StatusLine owner={owner} lint={data.lint} stale={data.stale} />}
    </div>
  );
}

function MainNode({ data }: NodeProps<MainNodeT>) {
  if (data.kind !== "main") return null;
  return (
    <div className={`min-w-[230px] rounded-lg border bg-neutral-900 px-3 py-2 ${data.selected ? "border-sky-400" : "border-neutral-600"}`}>
      <div className="font-semibold">main (a plain flow)</div>
      <div className="text-[11px] text-neutral-400">{data.main.length} statement(s) · no map blocks</div>
      <StatusLine owner="flow" lint={data.lint} stale={data.stale} />
    </div>
  );
}

type ExitEdgeT = Edge<GEdge["data"] & { runs?: number }, "exit">;

function ExitEdge(props: EdgeProps<ExitEdgeT>) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, selected } = props;
  const [path, lx, ly] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition });
  const kind = data?.kind ?? "walk_exit";
  const colour = EXIT_COLOURS[kind];
  const derived = data?.derived;
  // a backward edge (a loop back to an earlier block) gets its label lower than the forward one
  const dy = (LABEL_DY[kind] ?? 0) + (sourceX > targetX ? 48 : 0);
  const label = kind === "attach" ? "" : `${kind.replace("_", " ")}${data?.entry ? ` → ${data.entry}` : ""}${data?.runs ? ` · ${data.runs}×` : ""}`;
  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={{ stroke: colour, strokeWidth: selected ? 3 : 2, strokeDasharray: derived ? "6 5" : undefined, opacity: kind === "attach" ? 0.6 : 1 }}
      />
      {label && (
        <EdgeLabelRenderer>
          <div
            className="nodrag nopan pointer-events-auto absolute rounded bg-neutral-950/90 px-1.5 py-0.5 text-[10px]"
            style={{ transform: `translate(-50%, -50%) translate(${lx}px, ${ly + dy}px)`, color: colour }}
          >
            {label}
            {derived && kind === "death_respawn" ? " (derived)" : ""}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

const nodeTypes = { map: MapNode, events: EventsNode, main: MainNode };
const edgeTypes = { exit: ExitEdge };

export type CanvasProps = {
  flow: Flow;
  positions: Record<string, XY>;
  lint: LintDoc | null;
  lintStale: boolean;
  trace: Trace | null;
  catalogue: CatalogueDoc | null;
  selected: string | null;
  onSelect: (id: string | null) => void;
  onOpen: (id: string) => void;
  onMove: (positions: Record<string, XY>) => void;
  onConnectExit: (from: string, kind: AuthoredExit, to: string) => void;
  onDeleteExit: (path: string) => void;
  onNotes: (notes: string[]) => void;
};

export default function FlowCanvas(p: CanvasProps) {
  const { flow, positions, lint, lintStale, trace, selected, onSelect, onOpen, onMove, onConnectExit, onDeleteExit, onNotes } = p;
  const graph = useMemo(() => toGraph(flow, positions), [flow, positions]);
  // fit the view when the set of nodes changes (a new or imported flow, a block added or removed)
  const rf = useRef<ReactFlowInstance | null>(null);
  const shape = graph.nodes.map((n) => n.id).join("|");
  useEffect(() => {
    const t = setTimeout(() => void rf.current?.fitView({ padding: 0.12, duration: 250 }), 80);
    return () => clearTimeout(t);
  }, [shape]);
  useEffect(() => onNotes(graph.notes), [graph, onNotes]);
  const runs = useMemo(() => edgeRuns(trace, graph.edges), [trace, graph]);
  const initial = useMemo(
    () =>
      graph.nodes.map((n: GNode) => ({
        id: n.id,
        type: n.type,
        position: n.position,
        data: { ...n.data, lint, trace, selected: n.id === selected, stale: lintStale },
        deletable: false,
      })) as Node[],
    [graph, lint, trace, selected, lintStale],
  );
  // React Flow's own node state (drags, measured sizes), rebuilt whenever the IR-derived graph
  // changes; the rebuild keeps the sizes React Flow measured (derived state, set during render).
  const [view, setView] = useState<{ base: Node[]; nodes: Node[] }>({ base: initial, nodes: initial });
  if (view.base !== initial) {
    const measured = new Map(view.nodes.map((n) => [n.id, n.measured]));
    setView({ base: initial, nodes: initial.map((n) => ({ ...n, measured: measured.get(n.id) })) });
  }
  const nodes = view.base === initial ? view.nodes : initial;
  const edges = useMemo(
    () =>
      graph.edges.map((e: GEdge) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle,
        targetHandle: e.targetHandle,
        type: "exit",
        data: { ...e.data, runs: runs.get(e.id) },
        deletable: !e.data.derived,
        selectable: !e.data.derived,
      })) as Edge[],
    [graph, runs],
  );

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    setView((v) => ({ ...v, nodes: applyNodeChanges(changes, v.nodes) }));
  }, []);

  const onConnect = useCallback(
    (c: Connection) => {
      const kind = c.sourceHandle as AuthoredExit;
      if (!c.source.startsWith("block:") || !c.target.startsWith("block:")) return;
      if (!["walk_exit", "npc_warp", "item_warp"].includes(kind)) return;
      onConnectExit(c.source.slice(6), kind, c.target.slice(6));
    },
    [onConnectExit],
  );

  return (
    <div className="h-full w-full" data-testid="flow-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onNodeDragStop={(_, __, dragged) => onMove(Object.fromEntries(dragged.map((n) => [n.id, n.position])))}
        onConnect={onConnect}
        onEdgesDelete={(es) => es.forEach((e) => e.id.startsWith("exit:") && onDeleteExit(e.id.slice(5)))}
        onNodeClick={(_, n) => onSelect(n.id)}
        onPaneClick={() => onSelect(null)}
        onNodeDoubleClick={(_, n) => onOpen(n.id)}
        zoomOnDoubleClick={false}
        deleteKeyCode={["Delete", "Backspace"]}
        colorMode="dark"
        onInit={(inst) => {
          rf.current = inst as unknown as ReactFlowInstance;
        }}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        proOptions={{ hideAttribution: false }}
        minZoom={0.2}
      >
        <Background gap={24} />
        <Controls showInteractive={false} />
        <MiniMap pannable zoomable nodeColor={(n) => (n.type === "events" ? "#9d4b6b" : "#3b5b8f")} />
      </ReactFlow>
    </div>
  );
}
