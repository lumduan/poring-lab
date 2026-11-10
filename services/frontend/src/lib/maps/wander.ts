// The map's OTHER MONSTERS as decoration (Batt 2026-11-10, world-map-flows.md section 9: "make it an
// option"): the spawns the static data lists for a map, drawn wandering on its walk grid while the
// run plays, deterministically from the run's seed. DECORATION ONLY: they come from the sheet the
// backend already gives (no simulator change), are never engaged, never in the step list, the
// checks or the Python, and are hidden wherever the monster the run meets stands at that time.
// Pure functions, tested in maps.test.ts.
//
// Cheap by construction: at most `cap` (40) wanderers; each one's walk is computed ONCE (a seeded
// random walk of `steps` cells, walked forth and back); a frame only interpolates between two of
// its cells into a list made once (no allocation per frame).

export type Spawn = { mob: number; count: number; boss?: boolean; area?: [number, number, number, number] | null };
export type Wanderer = { mob: number; path: Int32Array; n: number; phase: number };
export type WanderOut = { x: number; y: number; mob: number };
export type Wanderers = { list: Wanderer[]; out: WanderOut[] };

export const WANDER_CAP = 40;
export const WANDER_STEPS = 48;
export const WANDER_STEP_S = 1.6; // a slow walk: one cell every 1.6 s (at 1x)
const HOME_RADIUS = 6; // a wanderer stays this near its first cell
const HOME_TRIES = 200;

/** FNV-1a: a string to 32 bits (the seed of one wanderer). */
function hash(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/** mulberry32: a small seeded generator, [0, 1). */
function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** How many of each species to show: all of them under the cap, else in proportion (each at least
 * one while the cap allows), never more than `cap` in all. */
export function shares(spawns: readonly Spawn[], cap = WANDER_CAP): number[] {
  const total = spawns.reduce((s, x) => s + Math.max(0, x.count), 0);
  if (total <= cap) return spawns.map((x) => Math.max(0, x.count));
  const k = spawns.map((x) => (x.count > 0 ? Math.max(1, Math.floor((x.count * cap) / total)) : 0));
  let sum = k.reduce((s, x) => s + x, 0);
  while (sum > cap) {
    const i = k.indexOf(Math.max(...k));
    k[i]--;
    sum--;
  }
  return k;
}

const walkable = (rows: readonly string[], x: number, y: number) => y >= 0 && y < rows.length && x >= 0 && x < rows[y].length && rows[y][x] === ".";
const inArea = (a: Spawn["area"], x: number, y: number) => !a || (x >= a[0] && x <= a[2] && y >= a[1] && y <= a[3]);

/** The wanderers of one map: none without a walk grid (no walkable cell to stand on). */
export function makeWanderers(rows: readonly string[] | null, spawns: readonly Spawn[], seed: number, map: string, cap = WANDER_CAP, steps = WANDER_STEPS): Wanderers {
  const list: Wanderer[] = [];
  if (!rows || !rows.length || steps < 2) return { list, out: [] };
  const h = rows.length;
  const w = rows[0].length;
  const k = shares(spawns, cap);
  spawns.forEach((sp, si) => {
    for (let j = 0; j < k[si]; j++) {
      const r = rng(hash(`${seed}:${map}:${si}:${j}`));
      const a = sp.area ?? null;
      const [x0, y0, x1, y1] = a ? [Math.max(0, a[0]), Math.max(0, a[1]), Math.min(w - 1, a[2]), Math.min(h - 1, a[3])] : [0, 0, w - 1, h - 1];
      if (x1 < x0 || y1 < y0) continue;
      let hx = -1;
      let hy = -1;
      for (let i = 0; i < HOME_TRIES; i++) {
        const x = x0 + Math.floor(r() * (x1 - x0 + 1));
        const y = y0 + Math.floor(r() * (y1 - y0 + 1));
        if (walkable(rows, x, y)) {
          hx = x;
          hy = y;
          break;
        }
      }
      if (hx < 0) continue; // no walkable cell found in its area: not shown
      const path = new Int32Array(steps * 2);
      let x = hx;
      let y = hy;
      for (let s = 0; s < steps; s++) {
        path[2 * s] = x;
        path[2 * s + 1] = y;
        // the next cell: a random walkable neighbour (RO's 8 ways; a diagonal needs both of its
        // orthogonal neighbours walkable), inside the area and near home; else it stays
        for (let tries = 0; tries < 8; tries++) {
          const dx = Math.floor(r() * 3) - 1;
          const dy = Math.floor(r() * 3) - 1;
          const nx = x + dx;
          const ny = y + dy;
          if ((dx === 0 && dy === 0) || !walkable(rows, nx, ny) || !inArea(a, nx, ny)) continue;
          if (dx !== 0 && dy !== 0 && !(walkable(rows, x + dx, y) && walkable(rows, x, y + dy))) continue;
          if (Math.max(Math.abs(nx - hx), Math.abs(ny - hy)) > HOME_RADIUS) continue;
          x = nx;
          y = ny;
          break;
        }
      }
      list.push({ mob: sp.mob, path, n: steps, phase: r() * (2 * steps - 2) });
    }
  });
  return { list, out: list.map(() => ({ x: 0, y: 0, mob: 0 })) };
}

/** Where each wanderer is at `t` (s), written into `st.out`; returns how many are shown. A wanderer
 * whose cell is within one cell of an `avoid` cell (the monster the run meets, at that time) is
 * not shown then. */
export function wanderersAt(st: Wanderers, t: number, avoid: readonly (readonly [number, number])[] = []): number {
  if (!Number.isFinite(t)) return 0;
  let k = 0;
  for (const wd of st.list) {
    const period = 2 * wd.n - 2;
    let p = (t / WANDER_STEP_S + wd.phase) % period;
    if (p < 0) p += period;
    if (p > wd.n - 1) p = period - p; // forth and back: a continuous walk
    const i = Math.min(wd.n - 2, Math.floor(p));
    const f = p - i;
    const ax = wd.path[2 * i];
    const ay = wd.path[2 * i + 1];
    const x = ax + (wd.path[2 * i + 2] - ax) * f;
    const y = ay + (wd.path[2 * i + 3] - ay) * f;
    const cx = Math.round(x);
    const cy = Math.round(y);
    let hidden = false;
    for (const c of avoid) {
      if (Math.abs(cx - c[0]) <= 1 && Math.abs(cy - c[1]) <= 1) {
        hidden = true;
        break;
      }
    }
    if (hidden) continue;
    const o = st.out[k++];
    o.x = x;
    o.y = y;
    o.mob = wd.mob;
  }
  return k;
}

export const WANDER_KEY = "poring-lab.maps.other-monsters.v1"; // "on" | "off" (default off)
