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

// --- the graph's view (round 4, 2026-11-10) ------------------------------------------------------
// The fit and the follow-the-playback pan, as pure functions that return null for an unusable
// input. A FOLDED graph is display: none, so its box is 0 x 0; a pan animated over a zero-size view
// makes d3-zoom's interpolation divide by zero (log(0 / 0)), and React Flow then drew its
// background dot with cx / cy / r = NaN on every frame of the animation (matpilot's console count,
// round 4). Nothing moves the view unless every number is finite and the box has a size.
export type Box = { width: number; height: number };
export type Rect = { x: number; y: number; width: number; height: number };
export type Viewport = { x: number; y: number; zoom: number };

const finite = (...v: number[]) => v.every((n) => Number.isFinite(n));

/** The viewport that fits `bounds` into `box` between minZoom and maxZoom; a graph too big for
 * minZoom starts at its LEFT (START) and is centred vertically when it fits, else top-aligned.
 * `overflow`: it did not fit at minZoom. Null: no box (folded, not laid out) or a bad number. */
export function fitViewport(box: Box, bounds: Rect, minZoom: number, maxZoom: number, pad: number): { viewport: Viewport; overflow: boolean } | null {
  if (!finite(box.width, box.height, bounds.x, bounds.y, bounds.width, bounds.height, minZoom, maxZoom, pad)) return null;
  if (box.width <= 2 * pad || box.height <= 2 * pad || bounds.width <= 0 || bounds.height <= 0 || minZoom <= 0 || maxZoom < minZoom) return null;
  const z = Math.min(maxZoom, (box.width - 2 * pad) / bounds.width, (box.height - 2 * pad) / bounds.height);
  if (z >= minZoom) {
    return { viewport: { x: (box.width - bounds.width * z) / 2 - bounds.x * z, y: (box.height - bounds.height * z) / 2 - bounds.y * z, zoom: z }, overflow: false };
  }
  const zz = minZoom;
  const y = bounds.height * zz <= box.height - 2 * pad ? (box.height - bounds.height * zz) / 2 - bounds.y * zz : pad - bounds.y * zz;
  return { viewport: { x: pad - bounds.x * zz, y, zoom: zz }, overflow: true };
}

/** Where to centre the view so the playback's node is in it (at the current zoom), or null: the
 * node is already in view, the box has no size (folded), or a number is not finite. */
export function followCentre(box: Box, vp: Viewport, node: Rect): { x: number; y: number; zoom: number } | null {
  if (!finite(box.width, box.height, vp.x, vp.y, vp.zoom, node.x, node.y, node.width, node.height)) return null;
  if (box.width <= 0 || box.height <= 0 || vp.zoom <= 0 || node.width < 0 || node.height < 0) return null;
  const px = node.x * vp.zoom + vp.x;
  const py = node.y * vp.zoom + vp.y;
  const inView = px >= 0 && py >= 0 && px + node.width * vp.zoom <= box.width && py + node.height * vp.zoom <= box.height;
  return inView ? null : { x: node.x + node.width / 2, y: node.y + node.height / 2, zoom: vp.zoom };
}
