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
  // `short`: the one word the label keeps where its full words do not fit (labelPlace)
  | { kind: "session"; from: string; to: string; entry: string | null; label: string; short: string; derived: false }
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
    const short = to?.kind === "character" ? "log in" : to?.kind === "map" ? "enter" : "";
    edges.push({ id: sessionEdgeId(e.from, e.to), source: e.from, target: e.to, sourceHandle: OUT, targetHandle: onto(e.to, e.entry), data: { kind: "session", from: e.from, to: e.to, entry: e.entry ?? null, label, short, derived: false } });
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
export function fitViewport(box: Box, bounds: Rect, minZoom: number, maxZoom: number, pad: number, left = 0): { viewport: Viewport; overflow: boolean } | null {
  if (!finite(box.width, box.height, bounds.x, bounds.y, bounds.width, bounds.height, minZoom, maxZoom, pad, left)) return null;
  // `left` (round 18 #6): px kept free at the box's left, beside the pad (React Flow's controls)
  const w = box.width - Math.max(0, left);
  if (w <= 2 * pad || box.height <= 2 * pad || bounds.width <= 0 || bounds.height <= 0 || minZoom <= 0 || maxZoom < minZoom) return null;
  const x0 = box.width - w;
  const z = Math.min(maxZoom, (w - 2 * pad) / bounds.width, (box.height - 2 * pad) / bounds.height);
  if (z >= minZoom) {
    return { viewport: { x: x0 + (w - bounds.width * z) / 2 - bounds.x * z, y: (box.height - bounds.height * z) / 2 - bounds.y * z, zoom: z }, overflow: false };
  }
  const zz = minZoom;
  const y = bounds.height * zz <= box.height - 2 * pad ? (box.height - bounds.height * zz) / 2 - bounds.y * zz : pad - bounds.y * zz;
  return { viewport: { x: x0 + pad - bounds.x * zz, y, zoom: zz }, overflow: true };
}

// --- the fit stays clear of React Flow's controls (matpilot round 18 #6) -------------------------
// At 390 in the sample the zoom buttons (bottom left) covered 13 % of the Global card's left edge,
// its "Open flow" button included: the fit's cards started at the 24 px pad, under the 26 px wide
// column that starts 15 px in. The fit now keeps the controls' column free at the LEFT (the cards
// under or over a fitted card, like Global under town, then clear it too).
/** React Flow 12's controls (@xyflow/react/dist/style.css: .react-flow__panel margin 15px,
 * .react-flow__controls-button 26 px wide; pinned in maps.test.ts) and the clearance beside them. */
export const RF_CONTROLS = { margin: 15, button: 26 };
export const CONTROLS_CLEAR_PX = 8;
/** The px the fit keeps free at its box's left, beside its pad, so a fitted card's left edge is
 * CONTROLS_CLEAR_PX right of the controls' column. */
export const fitLeft = (pad: number): number => Math.max(0, RF_CONTROLS.margin + RF_CONTROLS.button + CONTROLS_CLEAR_PX - pad);

// --- which cards the Fit shows (matpilot round 17 N6, N7) ----------------------------------------
// Fit never went below the readable minimum (round 6: 0.86rem node text stays >= 11 px at 0.85), so
// on a phone the one box's START + xmas_dun02 (530 flow px, 450 at 0.85, on a 342 px wide view)
// opened at its LEFT with the card's exits cut, and a map "+ map" put right of it was 0 % in view.
// At 1440 the sample project fitted its two maps only while the button said "Fit the maps", and
// Login, Choose character and Global stayed off screen. Now the fit tries, at the readable minimum,
// EVERY card, then the RUN'S PATH (all but Global), then START + the MAP cards; on a narrow canvas
// where none of them fits, START + the maps are scaled down until they fit (down to FIT_FLOOR);
// the button's title says which (fitTitle).
/** The pages' phone breakpoint (maps.css `@media (max-width: 48rem)`, 16 px a rem): a canvas this
 * wide or narrower is NARROW (inclusive, as max-width is). */
export const NARROW_PX = 768;
/** The least zoom the narrow fit scales down to: React Flow's own zoom-out limit (MapsCanvas passes
 * it as the `minZoom` prop), so the fit never shows a zoom a person could not pinch back to. */
export const FIT_FLOOR = 0.2;
export type FitWhat = "all" | "path" | "maps";
/** The three card sets' bounds (flow pixels): every card; the run's path (every card but Global);
 * START + the map cards. A set that is missing (none of its cards) is skipped. */
export type FitSets = { all?: Rect | null; path?: Rect | null; maps?: Rect | null };
/** `scaled`: below the readable minimum (a narrow canvas); `overflow`: not even that fitted, and
 * the set starts at its LEFT at the readable minimum (a finger, or the minimap, pans the rest). */
export type FitChoice = { viewport: Viewport; overflow: boolean; what: FitWhat; scaled: boolean };

/** Which cards the Fit shows, and how (see above). Null: no box (folded, not laid out), a bad
 * number in the box, or no usable set. */
export function fitChoice(box: Box, sets: FitSets, minZoom: number, maxZoom: number, pad: number, left = 0): FitChoice | null {
  let last: { what: FitWhat; rect: Rect } | null = null;
  for (const what of ["all", "path", "maps"] as const) {
    const rect = sets[what];
    if (!rect) continue;
    const f = fitViewport(box, rect, minZoom, maxZoom, pad, left);
    if (!f) continue; // an unusable set (no size, a bad number); with a bad box, every set is
    last = { what, rect };
    if (!f.overflow) return { ...f, what, scaled: false };
  }
  if (!last) return null;
  if (box.width <= NARROW_PX && FIT_FLOOR < minZoom) {
    const s = fitViewport(box, last.rect, FIT_FLOOR, maxZoom, pad, left);
    if (s && !s.overflow) return { viewport: s.viewport, overflow: false, what: last.what, scaled: s.viewport.zoom < minZoom };
  }
  const f = fitViewport(box, last.rect, minZoom, maxZoom, pad, left);
  return f ? { ...f, what: last.what, scaled: false } : null;
}

/** The cards a fit of `what` leaves out, by the names their cards show, in the session's order
 * (a project has one Login, one Choose character, one Global). Login says it holds START when the
 * run starts there (`start`). */
export function fitLeftOut(nodes: readonly { type: string; start?: boolean }[], what: FitWhat): string[] {
  const inFit = (t: string) => what === "all" || (what === "path" ? t !== "global" : t === "map" || t === "start");
  const out: string[] = [];
  for (const t of ["login", "character", "global"]) {
    const n = nodes.find((x) => x.type === t);
    if (!n || inFit(t)) continue;
    out.push(t === "login" ? (n.start ? "Login (START)" : "Login") : t === "character" ? "Choose character" : "Global");
  }
  return out;
}

const andList = (xs: readonly string[]) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs.at(-1)}`);

/** The Fit button's NAME and title before the first fit. Round 18 #6: after a fit its accessible
 * name is its title's first sentence (fitName), so a screen reader hears what the fit showed too;
 * scripts find the button by its data-testid (maps-fit). */
export const FIT_NAME = "Fit the maps";

/** PURE (matpilot round 18 #6): the Fit button's accessible name from its title: the title's first
 * sentence, without its full stop ("Fit the maps: the map cards"); FIT_NAME for no title. */
export function fitName(title: string | null | undefined): string {
  const t = (title ?? "").trim();
  if (!t) return FIT_NAME;
  const end = t.search(/\.(\s|$)/);
  return (end < 0 ? t : t.slice(0, end)).trim() || FIT_NAME;
}

/** The Fit button's title: what its last fit showed (the same fit runs after a load, after
 * "+ map", on a resize and on the button), and which cards it left out. `marker`: the START
 * marker is one of the fit's cards (the run starts on a map). */
export function fitTitle(c: Pick<FitChoice, "what" | "scaled" | "overflow"> | null, out: readonly string[], marker: boolean): string {
  if (!c) return FIT_NAME;
  const all = out.length === 0;
  const one = out.length === 1;
  let s: string;
  if (c.overflow) {
    s = `${all ? "Fit" : "Fit the maps"}: ${marker ? "from START at the left" : "from the left"}, at a readable size (the ${all ? "cards" : "map cards"} do not all fit here: pan right).`;
  } else {
    const what = all ? "Fit: every card" : c.what === "path" ? "Fit: the run's path" : `Fit the maps: ${marker ? "START and " : ""}${c.scaled ? "every map card" : "the map cards"}`;
    s = `${what}${c.scaled ? ", scaled down to fit this narrow view (zoom in to read)" : ""}.`;
  }
  if (all) return s;
  if (c.scaled || c.overflow) return `${s} ${andList(out)} ${one ? "is" : "are"} left out: pan to ${one ? "it" : "them"}.`;
  if (one && out[0] === "Global") return `${s} Global, shared by every node, does not fit beside it at a readable size here: pan to it.`;
  return `${s} ${andList(out)} ${one ? "does" : "do"} not fit beside ${c.what === "path" ? "it" : "them"} at a readable size here: pan to ${one ? "it" : "them"}.`;
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

// --- an exit's label between its two cards (matpilot round 15 #13, round 16 #8) -----------------
// React Flow draws the cards OVER the edge labels, and a label sat at the edge's midpoint: with
// "+ map" 230 units right (round 15 #5's compact spacing) "death respawn (derived)" was 83 % under
// the cards at 1440. The label now sits in the GAP between the two cards, in what fits there: the
// words on one line, else wrapped on words, else one short word, else nothing (each card's port
// row says the exit in full). Flow pixels throughout: the label and the gap scale together.
/** .mp-edge-label's text, measured (round 16: "death respawn (derived)", 23 characters, 208 px
 * wide at 0.85rem / 600 with 0.4rem of padding a side): a little more, to be safe. */
export const LABEL_CH_PX = 8.6;
export const LABEL_PAD_PX = 14;
export const LABEL_CLEAR_PX = 10; // between the label and each card
export const LABEL_MAX_LINES = 3;
/** The widest map card (.mp-card's max-width in maps.css) and the lane "+ map" leaves beside it,
 * room for a two-line label ("death respawn" / "(derived)"). */
export const CARD_MAX_PX = 400;
export const LABEL_LANE_PX = 170;

/** matpilot round 18 #5: a label's text at the view's zoom: .mp-edge-label's 0.85rem (13.6 px, pinned
 * to maps.css in maps.test.ts) times the zoom. Under LABEL_MIN_PX (at 390 after "+ map" both cards
 * fit at 0.31: 4.2 px text) the label is not drawn, as labelLines' "no label" case: each card's
 * port row still names the exit, and the edge's title keeps the words. */
export const LABEL_FONT_PX = 0.85 * 16;
export const LABEL_MIN_PX = 9;
export const labelReadable = (zoom: number): boolean => Number.isFinite(zoom) && LABEL_FONT_PX * zoom >= LABEL_MIN_PX;

export const labelWidth = (text: string): number => Math.ceil(text.length * LABEL_CH_PX + LABEL_PAD_PX);

export type Span = { x: number; width: number };
/** The horizontal gap between two cards (flow pixels): from the left one's right edge to the
 * right one's left edge (negative or 0: they overlap in x, e.g. one under the other), and its
 * centre. Null for a non-finite or a not-yet-measured (width 0) card. */
export function cardGap(a: Span, b: Span): { gap: number; centre: number } | null {
  if (![a.x, a.width, b.x, b.width].every((n) => Number.isFinite(n)) || a.width <= 0 || b.width <= 0) return null;
  const [l, r] = a.x <= b.x ? [a, b] : [b, a];
  const left = l.x + l.width;
  return { gap: r.x - left, centre: left + (r.x - left) / 2 };
}

/** The label's lines in a gap of `gap` flow pixels: `full` on one line when it fits, else `full`
 * wrapped on its words into at most `maxLines` lines (LABEL_MAX_LINES), else `short`, else []
 * (no label). */
export function labelLines(full: string, short: string, gap: number, maxLines = LABEL_MAX_LINES): string[] {
  const room = gap - 2 * LABEL_CLEAR_PX;
  if (!Number.isFinite(room) || room <= 0 || !(maxLines >= 1)) return [];
  if (labelWidth(full) <= room) return [full];
  const lines: string[] = [];
  for (const w of full.split(" ").filter(Boolean)) {
    const last = lines.at(-1);
    if (last !== undefined && labelWidth(`${last} ${w}`) <= room) lines[lines.length - 1] = `${last} ${w}`;
    else lines.push(w);
  }
  if (lines.length <= maxLines && lines.every((l) => labelWidth(l) <= room)) return lines;
  return labelWidth(short) <= room ? [short] : [];
}

// --- one placement rule for every edge label (matpilot round 17, round 16 #8's leftover) ---------
// The session edges' labels sat ABOVE the row (min(source, target) y - 64), never wrapped: with
// Choose character UNDER Login (the sample) "log in, then choose" was 100 % under the Login card,
// and "enter the game → spawn" (204 px) was cut by the cards beside its 158 px gap. Every label now
// takes the same rule: cards SIDE BY SIDE (a horizontal gap): in that gap (labelLines), at the
// edge's own height; cards STACKED (their x spans overlap, a vertical gap between them): in that
// gap, as many lines as its height holds, no wider than the narrower card; OVERLAPPING cards: no
// label (the cards' port rows say it). The full words stay in the label's title.
/** .mp-edge-label's line box: 0.85rem x line-height 1.25 = 17 px a line, and 0.05rem of padding
 * above and below (1.6 px, rounded up). Pinned to maps.css in maps.test.ts. */
export const LABEL_LINE_PX = 17;
export const LABEL_VPAD_PX = 2;
export const labelHeight = (lines: number): number => lines * LABEL_LINE_PX + LABEL_VPAD_PX;

export type LabelPlace = { x: number; y: number; lines: string[]; how: "beside" | "stacked" | "overlap" };
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** Where an edge's label goes between its two cards `a` and `b` (flow pixels), and its lines;
 * `mid` is the edge's own label point (React Flow's getSmoothStepPath / getBezierPath centre).
 * Beside: x = the gap's centre, y = mid's. Stacked: x = mid's (kept over both cards' columns),
 * y = mid's kept inside the gap (so the label stays on its line whenever the gap allows). Null for
 * a card not yet measured (size 0) or a non-finite number. */
export function labelPlace(a: Rect, b: Rect, full: string, short: string, mid: XY): LabelPlace | null {
  if (!finite(a.x, a.y, a.width, a.height, b.x, b.y, b.width, b.height, mid.x, mid.y) || a.width <= 0 || a.height <= 0 || b.width <= 0 || b.height <= 0) return null;
  const h = cardGap(a, b);
  if (h && h.gap > 0) return { x: h.centre, y: mid.y, lines: labelLines(full, short, h.gap), how: "beside" };
  const [top, bottom] = a.y <= b.y ? [a, b] : [b, a];
  const gapTop = top.y + top.height;
  const vgap = bottom.y - gapTop;
  if (vgap <= 0) return { x: mid.x, y: mid.y, lines: [], how: "overlap" };
  const fit = Math.floor((vgap - 2 * LABEL_CLEAR_PX - LABEL_VPAD_PX) / LABEL_LINE_PX);
  const lines = labelLines(full, short, Math.min(a.width, b.width), Math.min(fit, LABEL_MAX_LINES));
  const half = labelHeight(lines.length) / 2;
  const x = clamp(mid.x, Math.max(a.x, b.x), Math.min(a.x + a.width, b.x + b.width));
  const y = lines.length ? clamp(mid.y, gapTop + LABEL_CLEAR_PX + half, bottom.y - LABEL_CLEAR_PX - half) : gapTop + vgap / 2;
  return { x, y, lines, how: "stacked" };
}
