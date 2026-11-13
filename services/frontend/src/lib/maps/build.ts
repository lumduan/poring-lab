// Placing a MAP NODE from the static data (the Maps page's "+ map"; docs/planning/project-model.md
// section 2): a project map node (project.ts newMapNode) for a map id, with what the backend's
// static data says about that map (its walk grid and its spawns), worked out in the browser at run
// time. Nothing derived from the client or rAthena is stored in the repo: the cells and ids come
// from GET /flows/world each time. Pure functions, tested in maps.test.ts on synthetic data.
//
// The defaults are a GUESS a learner then changes (in the node inspector, or the node's tabs on
// /flows):
// - the entry: the walkable cell nearest the map's centre (no walk grid: "anywhere");
// - targets: the species the map spawns 2 or more of; ignored: boss spawn lines and single spawns
//   (on xmas_dun02 that ignores the Stormy Knight and the Garm Baby, the Rogue's own rule);
// - its main: with targets, attack the nearest target 5 times (within 9 cells), then stop; without,
//   newMapNode's own (stop at once until it is written).
import { MAP_ID, type Stmt } from "../flow/ir.ts";
import { type MapNode, mapNodes, newMapNode, type Project } from "../flow/project.ts";
import { CARD_MAX_PX, LABEL_LANE_PX, POS_SCALE } from "./graph.ts";

export type MapFacts = {
  rows: string[] | null; // rows[y][x], '.' walkable (the backend's walk grid)
  spawns: { mob: number; count: number; boss: boolean }[];
};

export const ATTACKS = 5;
export const WITHIN = 9;
/** Where "+ map" places a new node: right of the rightmost map node, in the project's units. Round
 * 15 #5 made it the ready-made projects' compact 230 (437 px: a 400 px card left a 37 px gap, and
 * the new node's "death respawn (derived)" label was 83 % under the cards, matpilot round 16 #8);
 * now the widest card plus a lane for a two-line label: 300 units, 570 px. */
export const NEW_NODE_DX = Math.ceil((CARD_MAX_PX + LABEL_LANE_PX) / POS_SCALE.x);

/** The walkable cell nearest the grid's centre (ties: the lower y, then the lower x), or null. */
export function centreCell(rows: readonly string[] | null): [number, number] | null {
  if (!rows || !rows.length) return null;
  const h = rows.length;
  const w = rows[0].length;
  const cx = Math.floor(w / 2);
  const cy = Math.floor(h / 2);
  let best: [number, number] | null = null;
  let bestD = Infinity;
  for (let y = 0; y < h; y++) {
    const row = rows[y];
    for (let x = 0; x < row.length; x++) {
      if (row[x] !== ".") continue;
      const d = Math.abs(x - cx) + Math.abs(y - cy);
      if (d < bestD) {
        bestD = d;
        best = [x, y];
      }
    }
  }
  return best;
}

export function targetGuess(spawns: MapFacts["spawns"]): { targets: number[]; ignore: number[] } {
  const total = new Map<number, { count: number; boss: boolean }>();
  for (const s of spawns) {
    const o = total.get(s.mob) ?? { count: 0, boss: false };
    total.set(s.mob, { count: o.count + s.count, boss: o.boss || s.boss });
  }
  const targets: number[] = [];
  const ignore: number[] = [];
  for (const [mob, o] of [...total].sort((a, b) => a[0] - b[0])) (o.boss || o.count < 2 ? ignore : targets).push(mob);
  return { targets, ignore };
}

function attackLoop(): Stmt[] {
  return [
    {
      kind: "repeat",
      times: { kind: "lit", value: ATTACKS },
      body: [
        {
          kind: "action",
          block: "attack_nearest",
          concept: "combat.attack_target",
          timeout_s: 120,
          on_fail: "stop",
          outcome_to: null,
          note: null,
          params: { within: { kind: "lit", value: WITHIN } },
        },
      ],
    },
    { kind: "stop", reason: "done" },
  ];
}

/** Where a new map node goes: right of the rightmost map node, on its row (else right of all). */
export function newNodePos(p: Project): { x: number; y: number } {
  const maps = mapNodes(p);
  const pool = maps.length ? maps : p.nodes;
  if (!pool.length) return { x: 0, y: 0 };
  const right = pool.reduce((a, b) => (b.pos.x > a.pos.x ? b : a));
  return { x: Math.round(right.pos.x + NEW_NODE_DX), y: Math.round(right.pos.y) };
}

/** A map node for `map`, from the static data's facts (null: none known). */
export function mapNodeFor(p: Project, map: string, facts: MapFacts | null, pos = newNodePos(p)): MapNode {
  const n = newMapNode(p, map, pos);
  const c = centreCell(facts?.rows ?? null);
  n.entries = [{ name: "arrival", at: c ? { kind: "cell", map, x: c[0], y: c[1] } : null, radius: 2 }];
  const g = targetGuess(facts?.spawns ?? []);
  n.targets = g.targets.map((id) => ({ kind: "mob", id }));
  n.ignore = g.ignore.map((id) => ({ kind: "mob", id }));
  const main = n.tabs[0];
  if (g.targets.length && main.main) main.main = attackLoop();
  return n;
}

export type AddResult = { ok: true; project: Project; id: string } | { ok: false; error: string };

/** Add a map node for `map` to the project (+ map). */
export function addMapNode(p: Project, map: string, facts: MapFacts | null, pos?: { x: number; y: number }): AddResult {
  if (!MAP_ID.test(map)) return { ok: false, error: `${JSON.stringify(map)} is not a map id` };
  const n = mapNodeFor(p, map, facts, pos ?? newNodePos(p));
  return { ok: true, project: { ...p, nodes: [...p.nodes, n] }, id: n.id };
}
