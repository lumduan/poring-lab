// The Maps page's GRAPH (Batt 2026-11-10: "the n8n / Node-RED way of placing blocks, like at the
// very start: easy to read, and one map links to many other maps"; docs/planning/world-map-flows.md
// section 2): START -> Login -> Choose character -> the flow's map blocks, joined by their typed
// exits. Pure data, tested in graph.test.ts.
//
// The map nodes and exit edges are /flows' own (lib/flow/canvas.ts toGraph: one node per map
// block, one edge per take_exit, the derived death_respawn edges), so the IR stays the one source
// of truth; the three session nodes and their edges are the page's MOCK (lib/maps/session.ts), never
// IR. Event nodes stay on /flows' Map tab.
import { autoLayout, blockId, type GEdge, type MapNodeData, toGraph, type XY } from "../flow/canvas.ts";
import type { Flow } from "../flow/ir.ts";
import type { Session } from "./session.ts";

export type MapsNodeData =
  | { kind: "start" }
  | { kind: "login"; session: Session }
  | { kind: "character"; session: Session; enters: string | null }
  | MapNodeData
  | { kind: "main"; statements: number };
export type MapsNode = { id: string; type: MapsNodeData["kind"]; position: XY; data: MapsNodeData };
export type MapsEdge = Omit<GEdge, "data"> & { data: GEdge["data"] | { kind: "session"; derived: true; label: string } };
export type MapsGraph = { nodes: MapsNode[]; edges: MapsEdge[]; notes: string[] };

export const SESSION_IDS = ["start", "login", "character"] as const;
const SESSION_AT: Record<(typeof SESSION_IDS)[number], XY> = {
  start: { x: 0, y: 110 },
  login: { x: 150, y: 70 },
  character: { x: 470, y: 70 },
};
const MAPS_X = 800; // the first column of map nodes
const MAPS_Y = 70;

export function mapsGraph(flow: Flow, session: Session, positions: Record<string, XY> = {}): MapsGraph {
  const g = toGraph(flow, {});
  const auto = autoLayout(flow);
  const at = (id: string, fallback: XY): XY => positions[id] ?? fallback;
  const wf = flow.workflow;
  const nodes: MapsNode[] = [
    { id: "start", type: "start", position: at("start", SESSION_AT.start), data: { kind: "start" } },
    { id: "login", type: "login", position: at("login", SESSION_AT.login), data: { kind: "login", session } },
    {
      id: "character",
      type: "character",
      position: at("character", SESSION_AT.character),
      data: { kind: "character", session, enters: wf ? wf.start_block : null },
    },
  ];
  const edges: MapsEdge[] = [
    { id: "session:start", source: "start", target: "login", sourceHandle: "out", targetHandle: "in", data: { kind: "session", derived: true, label: "open the client" } },
    { id: "session:login", source: "login", target: "character", sourceHandle: "out", targetHandle: "in", data: { kind: "session", derived: true, label: "character select" } },
  ];
  if (!wf) {
    nodes.push({ id: "main", type: "main", position: at("main", { x: MAPS_X, y: MAPS_Y }), data: { kind: "main", statements: flow.main?.length ?? 0 } });
    edges.push({ id: "session:enter", source: "character", target: "main", sourceHandle: "out", targetHandle: "in", data: { kind: "session", derived: true, label: "enter the game" } });
    return { nodes, edges, notes: ["a plain flow has no map blocks: its one program runs wherever the character is"] };
  }
  for (const n of g.nodes) {
    if (n.data.kind !== "map") continue;
    const a = auto[n.id] ?? { x: 40, y: 240 };
    nodes.push({ id: n.id, type: "map", position: at(n.id, { x: MAPS_X + (a.x - 40), y: MAPS_Y + (a.y - 240) }), data: n.data });
  }
  edges.push({
    id: "session:enter",
    source: "character",
    target: blockId(wf.start_block),
    sourceHandle: "out",
    targetHandle: "in",
    data: { kind: "session", derived: true, label: `enter the game → ${wf.start_entry}` },
  });
  for (const e of g.edges) if (e.data.kind !== "attach") edges.push(e);
  return { nodes, edges, notes: g.notes.filter((n) => !n.startsWith("death_respawn")) };
}
