// IR <-> the workflow canvas (MW2 level 1), as PURE data (canvas.test.ts round-trips it in node).
//
// Nodes: one per map block (`block:<name>`), the GLOBAL events (`events:global`) and each map
// block's own events (`events:<name>`, attached to its block). A plain flow (no workflow) shows its
// `main` node instead of map blocks. The global node also lists the ALWAYS-ON safety events the flow
// does not write (ADR-0020 #15: the compiler adds them; locked, read-only, never IR).
// Edges are DERIVED, never stored: one per `take_exit` statement of a block's main flow (typed by
// its exit kind, on the port of that kind), plus the read-only `death_respawn` edges to the save
// point's block (MW1's IR refuses an authored death_respawn: the respawn map follows the save point,
// ADR-0020 13.1). Drawing or deleting an edge EDITS the IR (connectExit / removeExit below), so the
// IR stays the single source of truth; the layout (positions) is the canvas's own and is not part
// of the IR or its hash.
import {
  type AuthoredExit,
  type Exit,
  type ExitKind,
  type Flow,
  type Handler,
  type MapBlock,
  type MapEvent,
  type Stmt,
  type ZonesRef,
  builtInEvents,
  clone,
  exitOf,
  exitsOf,
  newBlock,
  NAME,
  stmtAt,
  walk,
} from "./ir.ts";

export type XY = { x: number; y: number };
export type MapNodeData = { kind: "map"; block: MapBlock; index: number; start: boolean; startEntry: string | null };
export type EventsNodeData =
  | { kind: "events"; scope: "global"; handlers: Handler[]; builtIn: string[] }
  | { kind: "events"; scope: "block"; block: string; events: MapEvent[] };
export type MainNodeData = { kind: "main"; main: Exclude<Flow["main"], null> };
export type NodeData = MapNodeData | EventsNodeData | MainNodeData;
export type GNode = { id: string; type: "map" | "events" | "main"; position: XY; data: NodeData };
export type EdgeKind = ExitKind | "attach";
export type GEdge = {
  id: string;
  source: string;
  target: string;
  sourceHandle: string;
  targetHandle: string;
  data: { kind: EdgeKind; derived: boolean; path?: string; entry?: string };
};
export type Meta = Omit<Flow, "handlers" | "workflow" | "main"> & {
  workflow: Omit<Flow["workflow"] & object, "blocks"> | null;
};
export type Graph = { meta: Meta; nodes: GNode[]; edges: GEdge[]; notes: string[] };

export const blockId = (name: string) => `block:${name}`;

// --- the save point and the derived death_respawn edges ---------------------------------------------
/** The block a death respawns into, when the flow fixes the save point on ONE map (set at a Kafra
 * or asserted); otherwise null with the reason. */
export function savePointBlock(flow: Flow): { block: string | null; why: string } {
  const wf = flow.workflow;
  if (!wf) return { block: null, why: "a plain flow has no map blocks" };
  const maps = new Set<string>();
  for (const b of wf.blocks) {
    for (const [, s] of walk(b.main, b.name)) {
      if (s.kind !== "action") continue;
      if (s.block === "set_save_point") maps.add(b.map.map);
      if (s.block === "assert_save_point") {
        const c = s.params.cell;
        if (c?.kind === "lit" && typeof c.value === "object" && !Array.isArray(c.value) && c.value.kind === "cell") {
          maps.add(c.value.map);
        }
      }
    }
  }
  if (maps.size === 0) return { block: null, why: "nothing sets the save point: a death respawns at an unknown map" };
  if (maps.size > 1) return { block: null, why: `the save point is set on ${[...maps].sort().join(", ")}: it depends on the path` };
  const map = [...maps][0];
  const on = wf.blocks.filter((b) => b.map.map === map);
  const pick = on.length === 1 ? on[0] : on.find((b) => b.resume_here);
  return pick ? { block: pick.name, why: `the save point is on ${map}` } : { block: null, why: `no block is on ${map}` };
}

// `dead` is always on (ADR-0020 #15: written by the flow or added by the compiler), so every
// workflow's death respawns: the death_respawn edges follow the save point alone.

// --- layout -------------------------------------------------------------------------------------
export const COL_W = 560;
export const ROW_H = 300;

/** Columns by exit distance from the start block (BFS); event nodes under their block. */
export function autoLayout(flow: Flow): Record<string, XY> {
  const pos: Record<string, XY> = { "events:global": { x: 40, y: 20 } };
  const wf = flow.workflow;
  if (!wf) {
    pos.main = { x: 40, y: 260 };
    return pos;
  }
  const byName = new Map(wf.blocks.map((b) => [b.name, b]));
  const col = new Map<string, number>();
  const queue = byName.has(wf.start_block) ? [wf.start_block] : [];
  if (queue.length) col.set(wf.start_block, 0);
  while (queue.length) {
    const cur = queue.shift()!;
    for (const { exit } of exitsOf(byName.get(cur)!)) {
      if (byName.has(exit.to_block) && !col.has(exit.to_block)) {
        col.set(exit.to_block, col.get(cur)! + 1);
        queue.push(exit.to_block);
      }
    }
  }
  const last = Math.max(-1, ...col.values()) + 1;
  const rows = new Map<number, number>();
  for (const b of wf.blocks) {
    const c = col.get(b.name) ?? last;
    const r = rows.get(c) ?? 0;
    rows.set(c, r + 1);
    pos[blockId(b.name)] = { x: 40 + c * COL_W, y: 240 + r * ROW_H };
    pos[`events:${b.name}`] = { x: 40 + c * COL_W, y: 240 + r * ROW_H + 190 };
  }
  return pos;
}

// --- IR -> graph ------------------------------------------------------------------------------------
function withoutBlocks(wf: NonNullable<Flow["workflow"]>): NonNullable<Meta["workflow"]> {
  const out: Partial<NonNullable<Flow["workflow"]>> = { ...wf };
  delete out.blocks;
  return out as NonNullable<Meta["workflow"]>;
}

export function toGraph(flow: Flow, positions: Record<string, XY> = {}): Graph {
  const auto = autoLayout(flow);
  const at = (id: string): XY => positions[id] ?? auto[id] ?? { x: 0, y: 0 };
  const { handlers, workflow, main, ...rest } = flow;
  const meta: Meta = { ...rest, workflow: workflow ? withoutBlocks(workflow) : null };
  const nodes: GNode[] = [
    {
      id: "events:global",
      type: "events",
      position: at("events:global"),
      data: { kind: "events", scope: "global", handlers, builtIn: builtInEvents(flow) },
    },
  ];
  const edges: GEdge[] = [];
  const notes: string[] = [];
  if (!workflow) {
    nodes.push({ id: "main", type: "main", position: at("main"), data: { kind: "main", main: main ?? [] } });
    return { meta, nodes, edges, notes };
  }
  const names = new Set(workflow.blocks.map((b) => b.name));
  workflow.blocks.forEach((b, index) => {
    const id = blockId(b.name);
    const start = b.name === workflow.start_block;
    nodes.push({
      id,
      type: "map",
      position: at(id),
      data: { kind: "map", block: b, index, start, startEntry: start ? workflow.start_entry : null },
    });
    if (b.events.length) {
      const eid = `events:${b.name}`;
      nodes.push({ id: eid, type: "events", position: at(eid), data: { kind: "events", scope: "block", block: b.name, events: b.events } });
      edges.push({
        id: `attach:${b.name}`,
        source: eid,
        target: id,
        sourceHandle: "attach",
        targetHandle: "events",
        data: { kind: "attach", derived: true },
      });
    }
    for (const { path, exit } of exitsOf(b)) {
      if (!names.has(exit.to_block)) {
        notes.push(`${path}: the exit goes to ${exit.to_block}, which is not a block of this flow`);
        continue;
      }
      edges.push({
        id: `exit:${path}`,
        source: id,
        target: blockId(exit.to_block),
        sourceHandle: exit.kind,
        targetHandle: "in",
        data: { kind: exit.kind, derived: false, path, entry: exit.to_entry },
      });
    }
  });
  const sp = savePointBlock(flow);
  if (sp.block) {
    for (const b of workflow.blocks) {
      if (b.name === sp.block) continue;
      edges.push({
        id: `respawn:${b.name}`,
        source: blockId(b.name),
        target: blockId(sp.block),
        sourceHandle: "death_respawn",
        targetHandle: "in",
        data: { kind: "death_respawn", derived: true },
      });
    }
  } else notes.push(`death_respawn: ${sp.why}`);
  return { meta, nodes, edges, notes };
}

// --- graph -> IR ------------------------------------------------------------------------------------
export function fromGraph(g: Graph): Flow {
  const global = g.nodes.find((n) => n.data.kind === "events" && n.data.scope === "global");
  const handlers = global && global.data.kind === "events" && global.data.scope === "global" ? global.data.handlers : [];
  const { workflow: wfMeta, ...rest } = g.meta;
  const flow: Flow = { ...rest, handlers: clone(handlers), main: null, workflow: null };
  if (!wfMeta) {
    const m = g.nodes.find((n) => n.data.kind === "main");
    flow.main = m && m.data.kind === "main" ? clone(m.data.main) : [];
    return flow;
  }
  const blocks = g.nodes
    .map((n) => n.data)
    .filter((d): d is MapNodeData => d.kind === "map")
    .sort((a, b) => a.index - b.index)
    .map((d) => clone(d.block));
  flow.workflow = { ...wfMeta, blocks };
  return flow;
}

// --- edits (IR -> IR) -----------------------------------------------------------------------------
export type EditResult = { ok: true; flow: Flow } | { ok: false, error: string };

function blockOf(flow: Flow, name: string): MapBlock | undefined {
  return flow.workflow?.blocks.find((b) => b.name === name);
}

function placeholderExit(kind: AuthoredExit, from: MapBlock, to: MapBlock): Exit {
  const x = exitOf(kind, to.name, to.entries[0]?.name ?? "arrival");
  if (kind === "walk_exit") x.warp = { kind: "cell", map: from.map.map, x: 0, y: 0 };
  if (kind === "npc_warp") {
    x.npc = { kind: "npc", key: "n_unset" };
    x.options = [{ kind: "option", key: "o_unset" }];
  }
  if (kind === "item_warp") x.item = { kind: "item", id: 1 };
  return x;
}

/** Draw an exit: a take_exit statement with PLACEHOLDER details (the linter names them) at the end
 * of the source block's main, replacing a trailing stop("todo"). */
export function connectExit(flow: Flow, from: string, kind: AuthoredExit, to: string): EditResult {
  const out = clone(flow);
  const a = blockOf(out, from);
  const b = blockOf(out, to);
  if (!a || !b) return { ok: false, error: "both ends must be map blocks" };
  const stmt: Stmt = { kind: "take_exit", exit: placeholderExit(kind, a, b) };
  const last = a.main[a.main.length - 1];
  if (last && last.kind === "stop" && last.reason === "todo") a.main[a.main.length - 1] = stmt;
  else a.main.push(stmt);
  return { ok: true, flow: out };
}

/** Delete an exit edge: its take_exit statement goes (a main flow keeps at least one statement). */
export function removeExit(flow: Flow, path: string): EditResult {
  const out = clone(flow);
  const [root, ...rest] = path.split(".");
  const b = blockOf(out, root);
  const at = b ? stmtAt(b.main, rest) : null;
  if (!b || !at || at.list[at.index].kind !== "take_exit") return { ok: false, error: `no exit at ${path}` };
  at.list.splice(at.index, 1);
  if (b.main.length === 0) b.main.push({ kind: "stop", reason: "todo" });
  return { ok: true, flow: out };
}

export function retargetExit(flow: Flow, path: string, to: string): EditResult {
  const out = clone(flow);
  const [root, ...rest] = path.split(".");
  const b = blockOf(out, root);
  const t = blockOf(out, to);
  const at = b ? stmtAt(b.main, rest) : null;
  const s = at ? at.list[at.index] : null;
  if (!s || s.kind !== "take_exit" || !t) return { ok: false, error: `no exit at ${path}` };
  s.exit.to_block = t.name;
  s.exit.to_entry = t.entries[0]?.name ?? s.exit.to_entry;
  return { ok: true, flow: out };
}

export function addBlock(flow: Flow, map = "map_1"): EditResult {
  const out = clone(flow);
  if (!out.workflow) return { ok: false, error: "a plain flow has no map blocks" };
  const names = new Set(out.workflow.blocks.map((b) => b.name));
  let i = out.workflow.blocks.length + 1;
  while (names.has(`block_${i}`)) i++;
  out.workflow.blocks.push(newBlock(`block_${i}`, map));
  return { ok: true, flow: out };
}

export function removeBlock(flow: Flow, name: string): EditResult {
  const out = clone(flow);
  const wf = out.workflow;
  if (!wf) return { ok: false, error: "a plain flow has no map blocks" };
  if (wf.blocks.length === 1) return { ok: false, error: "a workflow keeps at least one map block" };
  if (wf.start_block === name) return { ok: false, error: "the start block cannot be removed: start elsewhere first" };
  wf.blocks = wf.blocks.filter((b) => b.name !== name);
  return { ok: true, flow: out };
}

export type BlockProps = Pick<MapBlock, "map" | "entries" | "targets" | "ignore" | "resume_here"> & { name: string };

/** Change a block's own properties; a rename follows every exit to it and the start. */
export function updateBlock(flow: Flow, name: string, props: BlockProps): EditResult {
  const out = clone(flow);
  const wf = out.workflow;
  const b = blockOf(out, name);
  if (!wf || !b) return { ok: false, error: `no map block ${name}` };
  if (!NAME.test(props.name)) return { ok: false, error: `${JSON.stringify(props.name)} is not a valid name` };
  if (props.name !== name && wf.blocks.some((x) => x.name === props.name)) {
    return { ok: false, error: `a block named ${props.name} exists` };
  }
  if (!props.entries.length) return { ok: false, error: "a block needs at least one entry" };
  Object.assign(b, clone({ ...props }));
  if (props.name !== name) {
    for (const x of wf.blocks) for (const { exit } of exitsOf(x)) if (exit.to_block === name) exit.to_block = props.name;
    if (wf.start_block === name) wf.start_block = props.name;
  }
  return { ok: true, flow: out };
}

/** Name the map node's zones file by its sha256 (B2), or remove the reference (`null`: the key is
 * deleted, as MW1's canonical JSON leaves an absent reference out). The linter checks it is the
 * block's own map and the file's current bytes; approval binds it. */
export function setZonesRef(flow: Flow, name: string, ref: ZonesRef | null): EditResult {
  const out = clone(flow);
  const b = blockOf(out, name);
  if (!b) return { ok: false, error: `no map block ${name}` };
  if (ref === null) {
    delete b.zones;
    return { ok: true, flow: out };
  }
  if (ref.map !== b.map.map) return { ok: false, error: `the zones of ${ref.map} are not ${b.map.map}'s` };
  if (!/^[0-9a-f]{64}$/.test(ref.sha256)) return { ok: false, error: "a zones reference names the file's sha256" };
  b.zones = { map: ref.map, sha256: ref.sha256 };
  return { ok: true, flow: out };
}

export function setStart(flow: Flow, name: string, entry: string): EditResult {
  const out = clone(flow);
  const b = blockOf(out, name);
  if (!out.workflow || !b || !b.entries.some((e) => e.name === entry)) return { ok: false, error: "no such block / entry" };
  out.workflow.start_block = name;
  out.workflow.start_entry = entry;
  return { ok: true, flow: out };
}
