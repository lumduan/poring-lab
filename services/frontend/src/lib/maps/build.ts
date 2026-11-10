// Placing a MAP NODE from the static data (the Maps page's "+ Map"; docs/planning/world-map-flows.md
// section 2): a map block for a map id, with what the backend's static data says about that map
// (its walk grid and its spawns), worked out in the browser at run time. Nothing derived from the
// client or rAthena is stored in the repo: the cells and ids come from GET /flows/world each time.
// Pure functions, tested in build.test.ts on synthetic data.
//
// The defaults are a GUESS a learner then changes (in Inspect, or in the map's flow on /flows):
// - the entry: the walkable cell nearest the map's centre (no walk grid: "anywhere");
// - targets: the species the map spawns 2 or more of; ignored: boss spawn lines and single spawns
//   (on xmas_dun02 that ignores the Stormy Knight and the Garm Baby, the Rogue's own rule);
// - the flow: with targets, attack the nearest target 5 times (within 9 cells), then stop; without,
//   stop("todo") as /flows' "+ map block" does.
import type { EditResult } from "../flow/canvas.ts";
import { clone, emptyFlow, type Flow, MAP_ID, type MapBlock, NAME, newBlock, type Stmt } from "../flow/ir.ts";

export type MapFacts = {
  rows: string[] | null; // rows[y][x], '.' walkable (the backend's walk grid)
  spawns: { mob: number; count: number; boss: boolean }[];
};

export const ATTACKS = 5;
export const WITHIN = 9;

/** A block name for a map id: [A-Za-z][A-Za-z0-9_]*, unused in the flow. */
export function blockName(map: string, taken: ReadonlySet<string>): string {
  let base = map.replace(/[^A-Za-z0-9_]/g, "_").replace(/^[^A-Za-z]+/, "");
  if (!base) base = "map";
  base = base.slice(0, 40);
  let name = base;
  for (let i = 2; taken.has(name) || !NAME.test(name); i++) name = `${base}_${i}`;
  return name;
}

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

export function mapBlockFor(name: string, map: string, facts: MapFacts | null): MapBlock {
  const b = newBlock(name, map);
  const c = centreCell(facts?.rows ?? null);
  b.entries = [{ name: "arrival", at: c ? { kind: "cell", map, x: c[0], y: c[1] } : null, radius: 2 }];
  const g = targetGuess(facts?.spawns ?? []);
  b.targets = g.targets.map((id) => ({ kind: "mob", id }));
  b.ignore = g.ignore.map((id) => ({ kind: "mob", id }));
  if (g.targets.length) b.main = attackLoop();
  return b;
}

/** Add a map node for `map` to a workflow flow (a plain flow has no map blocks). */
export function addMapNode(flow: Flow, map: string, facts: MapFacts | null): EditResult & { name?: string } {
  if (!MAP_ID.test(map)) return { ok: false, error: `${JSON.stringify(map)} is not a map id` };
  const out = clone(flow);
  if (!out.workflow) return { ok: false, error: "a plain flow has no map blocks: Load a workflow first" };
  const name = blockName(map, new Set(out.workflow.blocks.map((b) => b.name)));
  out.workflow.blocks.push(mapBlockFor(name, map, facts));
  return { ok: true, flow: out, name };
}

/** A new workflow of ONE map node on `map` (Load ▸ "One map from the lab data"). */
export function oneMapFlow(map: string, facts: MapFacts | null, maxRuntimeS?: number): EditResult {
  if (!MAP_ID.test(map)) return { ok: false, error: `${JSON.stringify(map)} is not a map id` };
  const f = emptyFlow(`${blockName(map, new Set()).toLowerCase().replace(/^[^a-z]+/, "") || "map"}_flow`.slice(0, 48), maxRuntimeS);
  const name = blockName(map, new Set());
  const b = mapBlockFor(name, map, facts);
  f.description = `One map, ${map}: its entry, targets and ignored species are a first guess from the lab's static data (change them in Inspect).`;
  f.workflow = { start_block: name, start_entry: b.entries[0].name, blocks: [b], run_until_stopped: false };
  return { ok: true, flow: f };
}
