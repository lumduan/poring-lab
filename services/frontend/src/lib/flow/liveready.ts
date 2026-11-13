// Can the LIVE BLOCK PLAYER play this map node? (Batt 2026-11-13 ~21:4x, docs/planning/live-blocks.md
// stage 1: the player plays a project's blocks in the game; it refuses, before any input, a block
// that has no live binding.) The page asks the same question first, so Run is greyed with the
// reason instead of sending a run the backend refuses (`not_live`).
//
// A block is live when the catalogue says so: GET /flows/catalogue `blocks[name].spec.live === true`
// (a missing flag is NOT live). "Reachable" is what a run from that node can play: the node's main,
// the functions it calls (resolved ON THAT NODE, its own first, then Global's: the virtual dispatch
// of project-model.md section 3), the runner block's role functions, an item warp's function, the
// events that run on the node (its own, then Global's it does not replace), and -- following its
// exits -- the same for every map node the run goes on to. Control statements (if, while, repeat,
// for, wait until, set, call, return, stop, break, continue) are the player's own. An EXIT is live
// only as the item warp by a function (stage 1: "the item warp by a function, its arrival read on
// the minimap"); a walk exit, an NPC warp and an item warp by an item are not live yet. Pure, tested.
import type { Exit, Expr, Stmt } from "./ir.ts";
import { HOME_ROLE, globalOf, mainOf, namesOf, nodeById, type PNode, type Project, RESPAWN_ROLES, resolve, RUNNER_ROLE_KEYS } from "./project.ts";

/** GET /flows/catalogue's `blocks`, as far as this reads it. */
export type LiveCatalogue = Record<string, { spec?: { live?: boolean } } | undefined>;

export type Reach = {
  /** every catalogue block a run can play, sorted */
  blocks: string[];
  /** every exit kind a run can take that the player cannot play yet ("walk_exit", ...), sorted */
  exits: string[];
  /** the map nodes the run can be on (the start first, then in the order the exits reach them) */
  nodes: string[];
};

// stage 3 (live-blocks.md 3.3): the respawn roles' functions play too (their click_at, live there)
const ROLE_PARAMS: readonly string[] = [...RUNNER_ROLE_KEYS.map((r) => r.param), HOME_ROLE, ...RESPAWN_ROLES];

/** The exit's name when the player cannot play it yet, else null (an item warp by a function). */
export function exitNotLive(x: Exit): string | null {
  if (x.kind === "item_warp" && x.proc) return null;
  return x.kind;
}

/** What a run from this map node can play (see the top of the file). */
export function reachable(p: Project, nodeId: string): Reach {
  const blocks = new Set<string>();
  const exits = new Set<string>();
  const nodes: string[] = [];
  const seen = new Set<string>(); // "<node>|<function>": each function once per node
  const queue: string[] = [nodeId];

  const fn = (node: string, name: string) => {
    const key = `${node}|${name}`;
    if (seen.has(key)) return;
    seen.add(key);
    const r = resolve(p, node, name);
    if (r?.def) stmts(node, r.def.body);
  };
  const expr = (node: string, e: Expr | null | undefined) => {
    if (!e) return;
    switch (e.kind) {
      case "callv":
        fn(node, e.proc);
        e.args.forEach((a) => expr(node, a));
        Object.values(e.kwargs).forEach((a) => expr(node, a));
        return;
      case "do":
        action(node, e.action.block, e.action.params);
        return;
      case "list":
        e.items.forEach((a) => expr(node, a));
        return;
      case "and":
      case "or":
        e.terms.forEach((a) => expr(node, a));
        return;
      case "not":
        expr(node, e.term);
        return;
      case "cmp":
      case "arith":
        expr(node, e.left);
        expr(node, e.right);
        return;
      case "sense":
        Object.values(e.args).forEach((a) => expr(node, a));
        return;
      default:
        return;
    }
  };
  const action = (node: string, block: string, params: Record<string, Expr>) => {
    blocks.add(block);
    for (const [k, v] of Object.entries(params)) {
      // the runner's roles name FUNCTIONS (each one press_key): the player presses them too
      if (block === "dungeon_hunt" && ROLE_PARAMS.includes(k) && v.kind === "lit" && typeof v.value === "string") fn(node, v.value);
      else expr(node, v);
    }
  };
  const stmts = (node: string, body: readonly Stmt[]) => {
    for (const s of body) {
      switch (s.kind) {
        case "action":
          action(node, s.block, s.params);
          break;
        case "call":
          fn(node, s.proc);
          s.args.forEach((a) => expr(node, a));
          Object.values(s.kwargs).forEach((a) => expr(node, a));
          break;
        case "if":
          expr(node, s.cond);
          stmts(node, s.then);
          stmts(node, s.orelse);
          break;
        case "while":
          expr(node, s.cond);
          stmts(node, s.body);
          break;
        case "repeat":
          expr(node, s.times);
          stmts(node, s.body);
          break;
        case "for":
          if (s.items.kind === "range") [s.items.start, s.items.stop, s.items.step].forEach((a) => expr(node, a));
          stmts(node, s.body);
          break;
        case "wait_until":
          expr(node, s.cond);
          break;
        case "set":
          expr(node, s.value);
          break;
        case "return":
          expr(node, s.value);
          break;
        case "take_exit": {
          const bad = exitNotLive(s.exit);
          if (bad) exits.add(bad);
          if (s.exit.proc) fn(node, s.exit.proc);
          const to = nodeById(p, s.exit.to_block);
          if (to?.kind === "map" && !nodes.includes(to.id) && !queue.includes(to.id)) queue.push(to.id);
          break;
        }
        default:
          break;
      }
    }
  };
  /** The events that run on a node: its own, then Global's it does not define (a plain function of
   * the same name turns Global's off there). */
  const events = (n: PNode) => {
    const own = namesOf(n);
    for (const [, x] of own) if (x.kind === "event" && x.def) stmts(n.id, x.def.body);
    const g = globalOf(p);
    for (const [name, x] of g ? namesOf(g) : []) if (x.kind === "event" && x.def && !own.has(name)) stmts(n.id, x.def.body);
  };

  while (queue.length) {
    const id = queue.shift() as string;
    const n = nodeById(p, id);
    if (!n || n.kind !== "map" || nodes.includes(id)) continue;
    nodes.push(id);
    stmts(id, mainOf(n)?.main ?? []);
    events(n);
  }
  return { blocks: [...blocks].sort(), exits: [...exits].sort(), nodes };
}

export type LiveReady = { ready: true; reach: Reach } | { ready: false; why: string; notLive: string[]; reach: Reach | null };

/** Whether Run may play this node now, and why not in words: "walk_to, talk_npc: not live yet". */
export function liveReady(p: Project, nodeId: string, catalogue: LiveCatalogue | null | undefined): LiveReady {
  const n = nodeById(p, nodeId);
  if (!n || n.kind !== "map") return { ready: false, why: "Run plays a map node: the run starts where she stands on it", notLive: [], reach: null };
  const reach = reachable(p, nodeId);
  if (!catalogue) return { ready: false, why: "reading the block catalogue from the flow engine…", notLive: [], reach };
  const notLive = [...reach.blocks.filter((b) => catalogue[b]?.spec?.live !== true), ...reach.exits];
  if (notLive.length === 0) return { ready: true, reach };
  return { ready: false, why: `${notLive.join(", ")}: not live yet`, notLive, reach };
}
