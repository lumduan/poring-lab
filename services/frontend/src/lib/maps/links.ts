// HOW THE MAPS LINK (Batt 2026-11-13: "show which map links to which and how; a map's ENTRIES are
// a warp's entrance, a Butterfly Wing's arrival (the town), a Kafra teleport's arrival; its EXITS
// are walking to the next map's warp, a Butterfly Wing, a Kafra teleport -- any number of them").
//
// Pure data over the PROJECT (docs/planning/project-model.md): a map node's exits are its
// take_exit statements in ANY of its tabs (`to_block` = the target map node's id); an entry's kind
// is how the project arrives there (the session path's last edge, each exit that targets it, a
// death's respawn). An exit's address is its engine path "<node>/<tab>/<site>" (project.ts
// nodeSites). Tested in links.test.ts.
import type { AuthoredExit, CellRef, Exit } from "../flow/ir.ts";
import { type MapNode, mapNodes, nodeById, nodeSites, type PNode, type Project, sessionPath } from "../flow/project.ts";

/** How the character arrives at an entry. */
export type ArrivalKind = "start" | AuthoredExit | "death_respawn";

export const ARRIVAL_WORDS: Record<ArrivalKind, string> = {
  start: "the session enters the game here",
  walk_exit: "walks in through a warp",
  npc_warp: "an NPC / Kafra warp lands here",
  item_warp: "a Butterfly Wing lands here",
  death_respawn: "a death respawns here",
};

export const EXIT_WORDS: Record<AuthoredExit, string> = {
  walk_exit: "walk to a warp",
  npc_warp: "NPC / Kafra warp",
  item_warp: "Butterfly Wing",
};

export type Arrival = { kind: ArrivalKind; from: string | null; fromMap: string | null; path: string | null };
export type EntryRow = { name: string; at: CellRef | null; radius: number; arrivals: Arrival[] };
export type ExitRow = {
  path: string; // "<node>/<tab>/<site>"
  tab: string;
  kind: AuthoredExit;
  how: string; // "walk to (12, 40)", "talk to kafra · option warp", "call butterfly_wing()"
  toNode: string;
  toMap: string | null; // null: the target is not a map node of this project
  toEntry: string;
  entryKnown: boolean; // the target node has an entry of that name
};
export type NodeLinks = { node: string; map: string; entries: EntryRow[]; exits: ExitRow[]; respawnTo: { node: string; map: string } | null };

const cellText = (c: CellRef | null) => (c ? `(${c.x}, ${c.y})` : "anywhere");

function itemText(x: Exit): string {
  if (x.proc) return `call ${x.proc}()`;
  const item = x.item;
  if (!item) return "a Butterfly Wing";
  if (item.kind === "var") return `the item ${item.name}`;
  return item.id === 602 ? "a Butterfly Wing" : `item ${item.id}`;
}

/** The exit in a few words: what the character does to leave. */
export function exitHow(x: Exit): string {
  if (x.kind === "walk_exit") return x.warp ? `walk to ${cellText(x.warp)}` : "walk to a warp (cell not set)";
  if (x.kind === "npc_warp") {
    const opts = x.options.map((o) => o.key).join(" › ");
    return `${x.npc ? `talk to ${x.npc.key}` : "an NPC (not set)"}${opts ? ` · ${opts}` : ""}`;
  }
  if (x.kind === "item_warp") return itemText(x);
  return "a death";
}

const mapNode = (p: Project, id: string): MapNode | undefined => {
  const n = nodeById(p, id);
  return n?.kind === "map" ? n : undefined;
};

/** Every take_exit of a node (any tab), with its engine path, in the order the tabs list them. */
export function exitSites(n: PNode): { path: string; tab: string; exit: Exit }[] {
  const out: { path: string; tab: string; exit: Exit }[] = [];
  for (const s of nodeSites(n)) if (s.stmt.kind === "take_exit") out.push({ path: s.path, tab: s.tab, exit: s.stmt.exit });
  return out;
}

/** Every authored exit of a map node, where it goes and how. */
export function exitRows(p: Project, n: PNode): ExitRow[] {
  return exitSites(n)
    .filter(({ exit }) => exit.kind !== "death_respawn")
    .map(({ path, tab, exit }) => {
      const to = mapNode(p, exit.to_block);
      return {
        path,
        tab,
        kind: exit.kind as AuthoredExit,
        how: exitHow(exit),
        toNode: exit.to_block,
        toMap: to ? to.map.map : null,
        toEntry: exit.to_entry,
        entryKnown: !!to?.entries.some((e) => e.name === exit.to_entry),
      };
    });
}

// --- the save point's node (where a death respawns) ------------------------------------------------
/** The map node a death respawns into, when the project fixes the save point on ONE map (set at a
 * Kafra, or asserted), else null with the reason. */
export function savePointNode(p: Project): { node: string | null; why: string } {
  const maps = new Set<string>();
  for (const n of mapNodes(p)) {
    for (const { stmt: s } of nodeSites(n)) {
      if (s.kind !== "action") continue;
      if (s.block === "set_save_point") maps.add(n.map.map);
      if (s.block === "assert_save_point") {
        const c = s.params.cell;
        if (c?.kind === "lit" && c.value && typeof c.value === "object" && !Array.isArray(c.value) && c.value.kind === "cell") maps.add(c.value.map);
      }
    }
  }
  if (maps.size === 0) return { node: null, why: "nothing sets the save point: a death respawns at an unknown map" };
  if (maps.size > 1) return { node: null, why: `the save point is set on ${[...maps].sort().join(", ")}: it depends on the path` };
  const map = [...maps][0];
  const on = mapNodes(p).filter((n) => n.map.map === map);
  const pick = on.length === 1 ? on[0] : on.find((n) => n.resume_here);
  return pick ? { node: pick.id, why: `the save point is on ${map}` } : { node: null, why: `no map node is on ${map}` };
}

/** How the project arrives at each of a map node's entries: the session path's last edge, the
 * exits that target it, and a death's respawn (into the save point's node, at its first entry: the
 * respawn cell is the save point's, which no entry names). */
export function entryRows(p: Project, n: MapNode): EntryRow[] {
  const rows: EntryRow[] = n.entries.map((e) => ({ name: e.name, at: e.at, radius: e.radius, arrivals: [] }));
  const byName = new Map(rows.map((r) => [r.name, r]));
  const sp = sessionPath(p);
  if (sp.map?.id === n.id && sp.entry) byName.get(sp.entry)?.arrivals.push({ kind: "start", from: sp.character?.id ?? null, fromMap: null, path: null });
  for (const other of mapNodes(p)) {
    for (const x of exitRows(p, other)) {
      if (x.toNode !== n.id) continue;
      byName.get(x.toEntry)?.arrivals.push({ kind: x.kind, from: other.id, fromMap: other.map.map, path: x.path });
    }
  }
  if (savePointNode(p).node === n.id && rows.length) rows[0].arrivals.push({ kind: "death_respawn", from: null, fromMap: null, path: null });
  return rows;
}

export function nodeLinks(p: Project, id: string): NodeLinks | null {
  const n = mapNode(p, id);
  if (!n) return null;
  const sp = savePointNode(p);
  const spn = sp.node ? mapNode(p, sp.node) : undefined;
  return { node: n.id, map: n.map.map, entries: entryRows(p, n), exits: exitRows(p, n), respawnTo: spn ? { node: spn.id, map: spn.map.map } : null };
}

/** Every link of the project, map to map, for the Links panel's whole-world table. */
export function worldLinks(p: Project): (ExitRow & { fromNode: string; fromMap: string })[] {
  const out: (ExitRow & { fromNode: string; fromMap: string })[] = [];
  for (const n of mapNodes(p)) for (const x of exitRows(p, n)) out.push({ ...x, fromNode: n.id, fromMap: n.map.map });
  return out;
}

/** The maps the project's map nodes are on, sorted: the "known maps" of the unknown-map rule. */
export function knownMaps(p: Project): string[] {
  return [...new Set(mapNodes(p).map((n) => n.map.map))].sort();
}

/** One line about an arrival, for a port's caption and the tables. */
export function arrivalText(a: Arrival): string {
  if (a.kind === "start") return a.from ? "the session enters here" : "START: the run starts here, where she stands";
  if (a.kind === "death_respawn") return "respawn";
  const how = a.kind === "walk_exit" ? "warp in" : a.kind === "npc_warp" ? "NPC warp in" : "wing arrival";
  return a.fromMap ? `${how} from ${a.fromMap}` : how;
}

/** An entry's caption: its arrivals, or "nothing arrives here yet". */
export function entryCaption(e: EntryRow): string {
  return e.arrivals.length ? e.arrivals.map(arrivalText).join(" · ") : "nothing arrives here yet";
}
