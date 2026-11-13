// HOW THE MAPS LINK (Batt 2026-11-13: "show which map links to which and how; a map's ENTRIES are
// a warp's entrance, a Butterfly Wing's arrival (the town), a Kafra teleport's arrival; its EXITS
// are walking to the next map's warp, a Butterfly Wing, a Kafra teleport -- any number of them").
//
// Pure data over the IR, shared by the Maps page (the n8n-style ports and the Links panel) and
// /flows (the binding strip above a map's blocks). Nothing here is new IR: an entry's KIND is how
// the flow arrives there (the exits that target it, the start, a death's respawn), an exit's row is
// its take_exit statement. Tested in links.test.ts.
import { savePointBlock } from "../flow/canvas.ts";
import { type AuthoredExit, type CellRef, type Exit, exitsOf, type Flow, type MapBlock } from "../flow/ir.ts";

/** How the character arrives at an entry. */
export type ArrivalKind = "start" | AuthoredExit | "death_respawn";

export const ARRIVAL_WORDS: Record<ArrivalKind, string> = {
  start: "the run starts here",
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
  path: string;
  kind: AuthoredExit;
  how: string; // "walk to (12, 40)", "talk to kafra · option warp", "a Butterfly Wing"
  toBlock: string;
  toMap: string | null; // null: the target block is not in this flow
  toEntry: string;
  entryKnown: boolean; // the target block has an entry of that name
};
export type BlockLinks = { block: string; map: string; entries: EntryRow[]; exits: ExitRow[]; respawnTo: { block: string; map: string } | null };

const cellText = (c: CellRef | null) => (c ? `(${c.x}, ${c.y})` : "anywhere");

function itemText(item: Exit["item"]): string {
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
  if (x.kind === "item_warp") return itemText(x.item);
  return "a death";
}

function blockOf(flow: Flow, name: string): MapBlock | undefined {
  return flow.workflow?.blocks.find((b) => b.name === name);
}

/** Every exit of a block, in the order its statements run. */
export function exitRows(flow: Flow, b: MapBlock): ExitRow[] {
  return exitsOf(b)
    .filter(({ exit }) => exit.kind !== "death_respawn")
    .map(({ path, exit }) => {
      const to = blockOf(flow, exit.to_block);
      return {
        path,
        kind: exit.kind as AuthoredExit,
        how: exitHow(exit),
        toBlock: exit.to_block,
        toMap: to ? to.map.map : null,
        toEntry: exit.to_entry,
        entryKnown: !!to?.entries.some((e) => e.name === exit.to_entry),
      };
    });
}

/** How the flow arrives at each of a block's entries: its exits that target it, the start, and a
 * death's respawn (into the save point's block, at its first entry: the respawn cell is the save
 * point's, which no entry names). */
export function entryRows(flow: Flow, b: MapBlock): EntryRow[] {
  const wf = flow.workflow;
  const rows: EntryRow[] = b.entries.map((e) => ({ name: e.name, at: e.at, radius: e.radius, arrivals: [] }));
  const byName = new Map(rows.map((r) => [r.name, r]));
  if (wf && wf.start_block === b.name) byName.get(wf.start_entry)?.arrivals.push({ kind: "start", from: null, fromMap: null, path: null });
  for (const other of wf?.blocks ?? []) {
    for (const x of exitRows(flow, other)) {
      if (x.toBlock !== b.name) continue;
      byName.get(x.toEntry)?.arrivals.push({ kind: x.kind, from: other.name, fromMap: other.map.map, path: x.path });
    }
  }
  const sp = savePointBlock(flow);
  if (sp.block === b.name && rows.length) rows[0].arrivals.push({ kind: "death_respawn", from: null, fromMap: null, path: null });
  return rows;
}

export function blockLinks(flow: Flow, name: string): BlockLinks | null {
  const b = blockOf(flow, name);
  if (!b) return null;
  const sp = savePointBlock(flow);
  const spb = sp.block ? blockOf(flow, sp.block) : undefined;
  return {
    block: b.name,
    map: b.map.map,
    entries: entryRows(flow, b),
    exits: exitRows(flow, b),
    respawnTo: spb ? { block: spb.name, map: spb.map.map } : null,
  };
}

/** Every link of the flow, map to map, for the Links panel's whole-world table. */
export function worldLinks(flow: Flow): (ExitRow & { fromBlock: string; fromMap: string })[] {
  const out: (ExitRow & { fromBlock: string; fromMap: string })[] = [];
  for (const b of flow.workflow?.blocks ?? []) for (const x of exitRows(flow, b)) out.push({ ...x, fromBlock: b.name, fromMap: b.map.map });
  return out;
}

/** The maps this flow knows (one or more blocks each), sorted: the "known maps" of the unknown-map
 * rule (rules.ts). */
export function knownMaps(flow: Flow): string[] {
  return [...new Set((flow.workflow?.blocks ?? []).map((b) => b.map.map))].sort();
}

/** One line about an arrival, for a port's caption and the tables. */
export function arrivalText(a: Arrival): string {
  if (a.kind === "start") return "start";
  if (a.kind === "death_respawn") return "respawn";
  const how = a.kind === "walk_exit" ? "warp in" : a.kind === "npc_warp" ? "NPC warp in" : "wing arrival";
  return a.fromMap ? `${how} from ${a.fromMap}` : how;
}

/** An entry's caption: its arrivals, or "not used yet". */
export function entryCaption(e: EntryRow): string {
  return e.arrivals.length ? e.arrivals.map(arrivalText).join(" · ") : "nothing arrives here yet";
}

