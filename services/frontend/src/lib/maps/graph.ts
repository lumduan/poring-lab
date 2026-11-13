// The Maps page's GRAPH over the PROJECT (Batt 2026-11-13, docs/planning/project-model.md: "a login
// node, a choose-character node, a node for each map, all linked into a work flow, and a GLOBAL
// node that shares variables and functions"): n8n / Node-RED's way of placing blocks. Pure data,
// tested in maps.test.ts.
//
// - NODES are the project's own nodes (`project.nodes`), drawn at their saved `pos`.
// - The SESSION connections are `project.edges` (login -> character -> the start map's ENTRY port).
// - MAP -> MAP links are the EXITS (take_exit statements in a map node's tabs): one port per exit
//   on the card's right (`x:<engine path>`), onto the ENTRY it lands on (`e:<entry name>`, the
//   card's left); `in` (the card's head) takes what names no entry (a death's respawn lands on the
//   save point's cell). A death's respawn edge is DERIVED (the save point's map node).
// - GLOBAL has no ports and no edges: its card says it is shared by every node.
// - THE START MARKER (Batt 2026-11-13 ~21:4x, the one box "START > map xmas_dun02"): when `start` is
//   a MAP node, a small "START" pill sits left of it, NOT a project node (its id `START_ID` is no
//   name), with one connection onto the start map's first entry; dragging that connection's end
//   onto another map node sets `start` (edit.ts setStart). A login start keeps its Login card's pill.
import type { AuthoredExit } from "../flow/ir.ts";
import type { Trace } from "../flow/api.ts";
import { type CharacterNode, type GlobalNode, type LoginNode, type MapNode, mapNodes, nodeById, type Project, sessionPath, startMap } from "../flow/project.ts";
import { exitRows, savePointNode } from "./links.ts";
import type { Timeline } from "./play.ts";

export const exitHandle = (path: string) => `x:${path}`;
export const entryHandle = (name: string) => `e:${name}`;
export const OUT = "out"; // a session node's one port out
export const IN = "in"; // a node's head: a connection that names no entry
export const RESPAWN = "death_respawn";
/** The START marker's id and its one connection's (never a node id: ids are names, no "@"). */
export const START_ID = "@start";
export const START_EDGE = "start>";
/** Where the marker sits: this many pixels left of the start map's card, a little lower. */
export const START_DX = 150;
export const START_DY = 40;

/** The project's `pos` is in the graph's UNITS; a card is drawn at pos x POS_SCALE pixels. The
 * ready-made projects place cards 260-300 units apart and 220 rows down, and a map card is 330-400
 * px wide and up to ~400 px tall (a port per entry and exit), so the map columns come out ~570 px
 * apart (the IR 2 graph's 560) and Global under the maps. Dragging saves pixels / scale, rounded. */
export const POS_SCALE = { x: 1.9, y: 2 } as const;
export type XY = { x: number; y: number };
export const toScreen = (p: XY): XY => ({ x: p.x * POS_SCALE.x, y: p.y * POS_SCALE.y });
export const toUnits = (p: XY): XY => ({ x: Math.round(p.x / POS_SCALE.x), y: Math.round(p.y / POS_SCALE.y) });

export type MapsNodeData =
  | { kind: "start"; to: string; entry: string | null }
  | { kind: "login"; node: LoginNode; start: boolean }
  | { kind: "character"; node: CharacterNode }
  | { kind: "map"; node: MapNode; first: boolean }
  | { kind: "global"; node: GlobalNode };
export type MapsNode = { id: string; type: MapsNodeData["kind"]; position: XY; data: MapsNodeData };
export type EdgeData =
  | { kind: "start"; to: string; entry: string | null; label: string; derived: false }
  | { kind: "session"; from: string; to: string; entry: string | null; label: string; derived: false }
  | { kind: AuthoredExit; path: string; entry: string; derived: false; label?: string }
  | { kind: "death_respawn"; derived: true; label?: string };
export type MapsEdge = { id: string; source: string; target: string; sourceHandle: string; targetHandle: string; data: EdgeData };
export type MapsGraph = { nodes: MapsNode[]; edges: MapsEdge[]; notes: string[] };

export const sessionEdgeId = (from: string, to: string) => `edge:${from}>${to}`;
export const exitEdgeId = (path: string) => `exit:${path}`;

const finiteXY = (p: XY | undefined): p is XY => !!p && Number.isFinite(p.x) && Number.isFinite(p.y);

/** Where a node with no usable `pos` goes (a hand-made file): by its kind, in rows. */
function fallbackPos(kind: MapsNodeData["kind"], i: number): XY {
  if (kind === "login") return { x: 0, y: 0 };
  if (kind === "character") return { x: 260, y: 0 };
  if (kind === "global") return { x: 560, y: 260 };
  return { x: 560 + 300 * (i % 4), y: 300 * Math.floor(i / 4) };
}

export function mapsGraph(p: Project): MapsGraph {
  const sp = sessionPath(p);
  const nodes: MapsNode[] = [];
  const at = new Map<string, XY>();
  let mi = 0;
  for (const n of p.nodes) {
    const units = finiteXY(n.pos) ? n.pos : fallbackPos(n.kind, n.kind === "map" ? mi : 0);
    if (n.kind === "map") mi++;
    const position = toScreen(units);
    at.set(n.id, position);
    if (n.kind === "login") nodes.push({ id: n.id, type: "login", position, data: { kind: "login", node: n, start: p.start === n.id } });
    else if (n.kind === "character") nodes.push({ id: n.id, type: "character", position, data: { kind: "character", node: n } });
    else if (n.kind === "map") nodes.push({ id: n.id, type: "map", position, data: { kind: "map", node: n, first: sp.map?.id === n.id } });
    else nodes.push({ id: n.id, type: "global", position, data: { kind: "global", node: n } });
  }
  const isMap = (id: string): MapNode | null => {
    const n = nodeById(p, id);
    return n?.kind === "map" ? n : null;
  };
  const onto = (to: string, entry: string | null | undefined) => (entry && isMap(to)?.entries.some((e) => e.name === entry) ? entryHandle(entry) : IN);
  const edges: MapsEdge[] = [];
  const sm = startMap(p);
  const smAt = sm ? at.get(sm.id) : undefined;
  if (sm && smAt) {
    const entry = sm.entries[0]?.name ?? null;
    nodes.unshift({ id: START_ID, type: "start", position: { x: smAt.x - START_DX, y: smAt.y + START_DY }, data: { kind: "start", to: sm.id, entry } });
    edges.push({ id: START_EDGE, source: START_ID, target: sm.id, sourceHandle: OUT, targetHandle: onto(sm.id, entry), data: { kind: "start", to: sm.id, entry, label: "", derived: false } });
  }
  for (const e of p.edges) {
    if (!nodeById(p, e.from) || !nodeById(p, e.to)) continue;
    const to = nodeById(p, e.to);
    const label = to?.kind === "character" ? "log in, then choose" : to?.kind === "map" ? `enter the game${e.entry ? ` → ${e.entry}` : ""}` : "";
    edges.push({ id: sessionEdgeId(e.from, e.to), source: e.from, target: e.to, sourceHandle: OUT, targetHandle: onto(e.to, e.entry), data: { kind: "session", from: e.from, to: e.to, entry: e.entry ?? null, label, derived: false } });
  }
  for (const n of mapNodes(p)) {
    for (const x of exitRows(p, n)) {
      if (!isMap(x.toNode)) continue; // drawn on the card ("not a map of this project"), no edge
      edges.push({ id: exitEdgeId(x.path), source: n.id, target: x.toNode, sourceHandle: exitHandle(x.path), targetHandle: onto(x.toNode, x.toEntry), data: { kind: x.kind, path: x.path, entry: x.toEntry, derived: false } });
    }
  }
  const save = savePointNode(p).node;
  const saveNode = save ? isMap(save) : null;
  if (saveNode) {
    for (const n of mapNodes(p)) {
      if (n.id === saveNode.id) continue;
      edges.push({ id: `respawn:${n.id}`, source: n.id, target: saveNode.id, sourceHandle: RESPAWN, targetHandle: onto(saveNode.id, saveNode.entries[0]?.name), data: { kind: "death_respawn", derived: true } });
    }
  }
  const notes = sp.problems.map((x) => `The session path: ${x}. Simulate starts at the login node and follows login → character → a map's entry: drag from a node's right port to connect it (or start on a map: "Start here" in a map node's inspector).`);
  return { nodes, edges, notes };
}

/** How often the run took each exit edge (matched by source, kind and target). */
export function exitRuns(trace: Trace | null, edges: readonly MapsEdge[]): Map<string, number> {
  const out = new Map<string, number>();
  if (!trace) return out;
  const count = new Map<string, number>();
  for (const t of trace.transitions) count.set(`${t.from}|${t.kind}|${t.to}`, (count.get(`${t.from}|${t.kind}|${t.to}`) ?? 0) + 1);
  for (const e of edges) {
    if (e.data.kind === "session" || e.data.kind === "start") continue;
    const k = `${e.source}|${e.data.kind}|${e.target}`;
    if (count.has(k)) out.set(e.id, count.get(k) as number);
  }
  return out;
}

/** The edge the playback last went along at beat `current`: a session step's connection, the last
 * exit (by its engine path, else by its from / kind / to), or a death's respawn. */
export function activeEdgeAt(tl: Timeline, current: number, edges: readonly MapsEdge[]): string | null {
  if (current < 0 || current >= tl.beats.length) return null;
  const sessionInto = (to: string) => edges.find((e) => e.data.kind === "session" && e.target === to)?.id ?? null;
  const b = tl.beats[current];
  if (b.kind === "session") return b.session?.step === "character" ? sessionInto(b.node) : null;
  for (let i = current; i >= 0; i--) {
    const x = tl.beats[i];
    if (x.kind === "exit" && x.step) {
      const st = x.step;
      if (st.node && edges.some((e) => e.id === exitEdgeId(st.node as string))) return exitEdgeId(st.node);
      const from = st.from_block ?? st.block;
      return edges.find((e) => e.data.kind === st.exit && e.source === from && e.target === st.to_block)?.id ?? null;
    }
    if (x.kind === "arrive" && x.step?.via === "respawn") return x.step.block ? `respawn:${x.step.block}` : null;
    if (x.kind === "session") return x.session?.step === "character" ? (edges.find((e) => e.data.kind === "session" && e.source === x.node)?.id ?? null) : null;
  }
  return null;
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
 * minZoom starts at its LEFT and is centred vertically when it fits, else top-aligned.
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
