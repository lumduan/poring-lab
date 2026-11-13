// The Maps page's EDITS of the project (docs/planning/project-model.md), n8n's way: connections
// drawn and deleted on the graph, nodes added, moved, renamed and deleted, a map node's own fields.
// Every edit is pure (a new project, the old one untouched) and says in words why it is refused.
// Tested in edit.test.ts.
//
// - THE SESSION PATH is `project.edges` (login -> character -> the start map's entry), at most ONE
//   path: a node has at most one connection out, a character node and a map node at most one in;
//   a new connection from a node REPLACES its old one (n8n would add a second: the project model
//   has one path). Global has no connections.
// - MAP -> MAP links stay the EXITS: take_exit statements in a map node's tabs; drawing one adds a
//   take_exit with PLACEHOLDER details (the linter names them) to the source's main, deleting one
//   removes its statement. A rename follows every exit, connection and the start.
import { type AuthoredExit, clone, type Entry, type Exit, exitOf, type MapRef, type MobRef, NAME, type Stmt, stmtAt, type ZonesRef } from "../flow/ir.ts";
import { GLOBAL_ID, MAIN_TAB, type MapNode, nodeById, type PNode, type Project } from "../flow/project.ts";
import { refreshRule } from "./rules.ts";

export type Edit = { ok: true; project: Project } | { ok: false; error: string };

const fail = (error: string): Edit => ({ ok: false, error });
const done = (project: Project): Edit => ({ ok: true, project: refreshRule(project) });

const KIND_WORDS: Record<PNode["kind"], string> = { login: "the login node", character: "the choose-character node", map: "a map node", global: "the Global node" };

// --- the session path (project.edges) --------------------------------------------------------------
/** Whether `from` may connect to `to` (the words when not): login -> character -> map only. */
export function sessionLinkProblem(p: Project, from: string, to: string, entry?: string): string | null {
  const a = nodeById(p, from);
  const b = nodeById(p, to);
  if (!a || !b) return "both ends must be nodes of the project";
  if (a.id === b.id) return "a node cannot connect to itself";
  if (a.kind === "global" || b.kind === "global") return "Global has no connections: it is shared by every node";
  if (a.kind === "login" && b.kind !== "character") return `the login node connects to a choose-character node, not to ${KIND_WORDS[b.kind]}`;
  if (a.kind === "character" && b.kind !== "map") return `the choose-character node connects to a map node (where the session enters the game), not to ${KIND_WORDS[b.kind]}`;
  if (a.kind === "map") return "a map node leaves by its EXITS: drag from one of its + ports (walk to a warp, NPC / Kafra warp, Butterfly Wing)";
  if (b.kind === "map" && entry !== undefined && !b.entries.some((e) => e.name === entry)) return `${b.id} has no entry ${entry}`;
  return null;
}

/** Connect two session nodes (the one connection out of `from`, and the one into `to`, replaced). */
export function connectSession(p: Project, from: string, to: string, entry?: string): Edit {
  const why = sessionLinkProblem(p, from, to, entry);
  if (why) return fail(why);
  const target = nodeById(p, to);
  const out = clone(p);
  const into = target?.kind === "map" ? (entry ?? target.entries[0]?.name) : undefined;
  out.edges = out.edges.filter((e) => e.from !== from && e.to !== to);
  out.edges.push(into !== undefined ? { from, to, entry: into } : { from, to });
  return done(out);
}

/** Where the run starts (Batt 2026-11-13: "START > map xmas_dun02"): a MAP node -- the run starts
 * where she stands on it, at its first entry, no session -- or a login node (the session path).
 * The /maps START marker's connection dragged onto a map, or "Start here" in the inspector. */
export function setStart(p: Project, id: string): Edit {
  const n = nodeById(p, id);
  if (!n) return fail(`there is no node ${id}`);
  if (n.kind !== "map" && n.kind !== "login") return fail(`the run starts on a map node (where she stands) or on a login node, not on ${KIND_WORDS[n.kind]}`);
  if (n.kind === "map" && !n.entries.length) return fail(`${n.id} has no entry: the run starts at a map's first entry`);
  if (p.start === id) return done(p);
  return done({ ...clone(p), start: id });
}

/** Delete a session connection. */
export function removeSession(p: Project, from: string, to: string): Edit {
  if (!p.edges.some((e) => e.from === from && e.to === to)) return fail(`no connection ${from} → ${to}`);
  return done({ ...clone(p), edges: p.edges.filter((e) => !(e.from === from && e.to === to)).map((e) => ({ ...e })) });
}

// --- exits (take_exit statements in a map node's tabs) ------------------------------------------------
function placeholderExit(kind: AuthoredExit, from: MapNode, to: MapNode): Exit {
  const x = exitOf(kind, to.id, to.entries[0]?.name ?? "arrival");
  if (kind === "walk_exit") x.warp = { kind: "cell", map: from.map.map, x: 0, y: 0 };
  if (kind === "npc_warp") {
    x.npc = { kind: "npc", key: "n_unset" };
    x.options = [{ kind: "option", key: "o_unset" }];
  }
  if (kind === "item_warp") x.item = { kind: "item", id: 1 };
  return x;
}

const asMap = (n: PNode | undefined): MapNode | null => (n?.kind === "map" ? n : null);
const mainOfNode = (n: PNode): Stmt[] | null => n.tabs.find((t) => t.name === MAIN_TAB)?.main ?? null;

/** Draw an exit: a take_exit with PLACEHOLDER details at the end of the source's main, replacing a
 * trailing stop (a new node's "stop at once"; the exit is now how the map ends). */
export function connectExit(p: Project, from: string, kind: AuthoredExit, to: string): Edit {
  const out = clone(p);
  const a = asMap(nodeById(out, from));
  const b = asMap(nodeById(out, to));
  if (!a || !b) return fail("an exit goes from a map node to a map node");
  const main = mainOfNode(a);
  if (!main) return fail(`${a.id} has no main tab`);
  const stmt: Stmt = { kind: "take_exit", exit: placeholderExit(kind, a, b) };
  const last = main[main.length - 1];
  if (last && last.kind === "stop" && (last.reason === "todo" || last.reason === "done")) main[main.length - 1] = stmt;
  else main.push(stmt);
  return done(out);
}

/** The statement list and index of an engine path "<node>/<tab>/<site>" (a main or a def's body). */
function locate(p: Project, path: string): { node: PNode; list: Stmt[]; index: number; root: Stmt[] } | null {
  const [nodeId, tabName, site] = path.split("/");
  const n = nodeById(p, nodeId ?? "");
  const t = n?.tabs.find((x) => x.name === tabName);
  if (!n || !t || !site) return null;
  const [root, ...rest] = site.split(".");
  const body = root === MAIN_TAB && t.main ? t.main : t.defs.find((d) => d.name === root)?.body;
  if (!body) return null;
  const at = stmtAt(body, rest);
  return at ? { node: n, ...at, root: body } : null;
}

/** Delete an exit (its take_exit statement goes; a body keeps at least one statement). */
export function removeExit(p: Project, path: string): Edit {
  const out = clone(p);
  const at = locate(out, path);
  if (!at || at.list[at.index].kind !== "take_exit") return fail(`no exit at ${path}`);
  at.list.splice(at.index, 1);
  if (at.root.length === 0) at.root.push({ kind: "stop", reason: "done" });
  return done(out);
}

/** Move an exit's END onto another map node (its entry, else the node's first): the statement
 * keeps its kind and details, only `to_block` / `to_entry` change. */
export function retargetExit(p: Project, path: string, to: string, entry?: string): Edit {
  const out = clone(p);
  const at = locate(out, path);
  const s = at ? at.list[at.index] : null;
  const t = asMap(nodeById(out, to));
  if (!s || s.kind !== "take_exit") return fail(`no exit at ${path}`);
  if (!t) return fail("an exit goes to a map node");
  const e = entry !== undefined && t.entries.some((x) => x.name === entry) ? entry : t.entries[0]?.name;
  if (!e) return fail(`${t.id} has no entry`);
  s.exit.to_block = t.id;
  s.exit.to_entry = e;
  return done(out);
}

// --- nodes --------------------------------------------------------------------------------------------
/** Move nodes (n8n saves positions): whole numbers, finite only. */
export function moveNodes(p: Project, positions: Record<string, { x: number; y: number }>): Project {
  let changed = false;
  const nodes = p.nodes.map((n) => {
    const q = positions[n.id];
    if (!q || !Number.isFinite(q.x) || !Number.isFinite(q.y)) return n;
    const pos = { x: Math.round(q.x), y: Math.round(q.y) };
    if (pos.x === n.pos.x && pos.y === n.pos.y) return n;
    changed = true;
    return { ...n, pos };
  });
  return changed ? { ...p, nodes } : p;
}

/** Every exit statement of every node that goes to `id` (for a delete's words). */
export function exitsInto(p: Project, id: string): string[] {
  const out: string[] = [];
  const visit = (stmts: Stmt[], from: string) => {
    for (const s of stmts) {
      if (s.kind === "take_exit" && s.exit.to_block === id) out.push(from);
      if (s.kind === "if") {
        visit(s.then, from);
        visit(s.orelse, from);
      }
      if (s.kind === "while" || s.kind === "repeat" || s.kind === "for") visit(s.body, from);
    }
  };
  for (const n of p.nodes) {
    if (n.id === id) continue;
    for (const t of n.tabs) {
      if (t.main) visit(t.main, n.id);
      for (const d of t.defs) visit(d.body, n.id);
    }
  }
  return out;
}

/** Delete a MAP node (the session's login and character nodes and Global stay: one each), with its
 * connections. Exits of other maps that went to it are KEPT (the Links panel names them "not a map
 * of this project" and the linter flags them): `dangling` counts them for the page's notice. */
export function removeNode(p: Project, id: string): Edit & { dangling?: number } {
  const n = nodeById(p, id);
  if (!n) return fail(`no node ${id}`);
  if (n.kind !== "map") return fail(`${KIND_WORDS[n.kind]} stays: a project has one (it is ${n.kind === "global" ? "shared by every node" : "part of the session path"})`);
  const out = clone(p);
  out.nodes = out.nodes.filter((x) => x.id !== id);
  out.edges = out.edges.filter((e) => e.from !== id && e.to !== id);
  const r = done(out);
  return r.ok ? { ...r, dangling: exitsInto(p, id).length } : r;
}

/** Why a node cannot be renamed to `to`, else null. */
export function renameProblem(p: Project, id: string, to: string): string | null {
  const n = nodeById(p, id);
  if (!n) return `no node ${id}`;
  if (n.kind === "global") return `Global's id is "${GLOBAL_ID}"`;
  if (!NAME.test(to)) return "an id is English letters, digits and _ (a letter first, at most 48)";
  if (to === GLOBAL_ID) return `"${GLOBAL_ID}" is the Global node's id`;
  if (to !== id && p.nodes.some((x) => x.id === to)) return `a node ${to} exists`;
  return null;
}

/** Rename a node: its connections, the start and every exit that names it follow. */
export function renameNode(p: Project, id: string, to: string): Edit {
  const why = renameProblem(p, id, to);
  if (why) return fail(why);
  if (to === id) return { ok: true, project: p };
  const out = clone(p);
  for (const n of out.nodes) if (n.id === id) n.id = to;
  if (out.start === id) out.start = to;
  out.edges = out.edges.map((e) => ({ ...e, from: e.from === id ? to : e.from, to: e.to === id ? to : e.to }));
  const visit = (stmts: Stmt[]) => {
    for (const s of stmts) {
      if (s.kind === "take_exit" && s.exit.to_block === id) s.exit.to_block = to;
      if (s.kind === "if") {
        visit(s.then);
        visit(s.orelse);
      }
      if (s.kind === "while" || s.kind === "repeat" || s.kind === "for") visit(s.body);
    }
  };
  for (const n of out.nodes) {
    for (const t of n.tabs) {
      if (t.main) visit(t.main);
      for (const d of t.defs) visit(d.body);
    }
  }
  return done(out);
}

// --- a map node's own fields ---------------------------------------------------------------------------
export type MapProps = { map: MapRef; entries: Entry[]; targets: MobRef[]; ignore: MobRef[]; resume_here: boolean };
const CELL_MAX = 1000;

/** Change a map node's map, entries, targets, ignored species and resume_here. An entry RENAMED in
 * place (the same list position) is followed by the exits and the connection that name it. */
export function updateMapNode(p: Project, id: string, v: MapProps): Edit {
  const n = asMap(nodeById(p, id));
  if (!n) return fail(`${id} is not a map node`);
  if (!/^[A-Za-z0-9_@.-]{1,40}$/.test(v.map.map)) return fail(`${JSON.stringify(v.map.map)} is not a map id`);
  if (!v.entries.length) return fail("a map node needs at least one entry (how the character arrives)");
  const names = new Set<string>();
  for (const e of v.entries) {
    if (!NAME.test(e.name)) return fail(`the entry ${JSON.stringify(e.name)}: English letters, digits and _ (a letter first)`);
    if (names.has(e.name)) return fail(`two entries are named ${e.name}`);
    names.add(e.name);
    if (!Number.isInteger(e.radius) || e.radius < 0 || e.radius > 30) return fail(`the entry ${e.name}: a radius of 0 to 30 cells`);
    if (e.at && (!Number.isInteger(e.at.x) || !Number.isInteger(e.at.y) || e.at.x < 0 || e.at.y < 0 || e.at.x > CELL_MAX || e.at.y > CELL_MAX)) return fail(`the entry ${e.name}: a cell (x, y) of 0 to ${CELL_MAX}`);
  }
  for (const m of [...v.targets, ...v.ignore]) if (!Number.isInteger(m.id) || m.id <= 0) return fail(`${m.id} is not a monster id`);
  const out = clone(p);
  const x = asMap(nodeById(out, id)) as MapNode;
  const renamed = new Map<string, string>();
  if (x.entries.length === v.entries.length) {
    x.entries.forEach((e, i) => {
      if (e.name !== v.entries[i].name) renamed.set(e.name, v.entries[i].name);
    });
  }
  x.map = { kind: "map", map: v.map.map };
  x.entries = v.entries.map((e) => ({ name: e.name, at: e.at ? { kind: "cell", map: v.map.map, x: e.at.x, y: e.at.y } : null, radius: e.radius }));
  x.targets = v.targets.map((m) => ({ kind: "mob", id: m.id }));
  x.ignore = v.ignore.map((m) => ({ kind: "mob", id: m.id }));
  x.resume_here = v.resume_here;
  if (x.zones && x.zones.map !== v.map.map) delete x.zones; // a zones file is one map's
  if (renamed.size) {
    out.edges = out.edges.map((e) => (e.to === id && e.entry && renamed.has(e.entry) ? { ...e, entry: renamed.get(e.entry) } : e));
    const visit = (stmts: Stmt[]) => {
      for (const s of stmts) {
        if (s.kind === "take_exit" && s.exit.to_block === id && renamed.has(s.exit.to_entry)) s.exit.to_entry = renamed.get(s.exit.to_entry) as string;
        if (s.kind === "if") {
        visit(s.then);
        visit(s.orelse);
      }
        if (s.kind === "while" || s.kind === "repeat" || s.kind === "for") visit(s.body);
      }
    };
    for (const m of out.nodes) {
      for (const t of m.tabs) {
        if (t.main) visit(t.main);
        for (const d of t.defs) visit(d.body);
      }
    }
  }
  return done(out);
}

/** Name the map node's zones file by its sha256 (B2), or remove the reference (`null`: the key is
 * deleted; an absent reference stays out of the canonical JSON). */
export function setZones(p: Project, id: string, ref: ZonesRef | null): Edit {
  const out = clone(p);
  const n = asMap(nodeById(out, id));
  if (!n) return fail(`${id} is not a map node`);
  if (ref === null) {
    delete n.zones;
    return done(out);
  }
  if (ref.map !== n.map.map) return fail(`the zones of ${ref.map} are not ${n.map.map}'s`);
  if (!/^[0-9a-f]{64}$/.test(ref.sha256)) return fail("a zones reference names the file's sha256");
  n.zones = { map: ref.map, sha256: ref.sha256 };
  return done(out);
}
