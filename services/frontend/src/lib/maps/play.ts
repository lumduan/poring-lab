// The Maps page's PLAYBACK (matpilot's mat page, for maps; docs/planning/world-map-flows.md
// section 4): the simulator's run in order as a TIMELINE of beats, where the character is at any
// time, what the map shows then (the monster met, the loot, the NPC talked to), and the run's words
// and checks. Pure functions over the backend's trace (poring_flow.trace `play`), tested in
// play.test.ts.
//
// It invents nothing about the run: positions are the trace's cells (a walk is interpolated between
// its cells at RO's 150 ms a cell, 212 ms a diagonal, scaled to the step's own duration), monsters
// are the cells and species the simulator placed from its seed. An older backend gives no `play`:
// the timeline is then APPROXIMATE (the walked segments once each, at the time the trace records,
// and the exits), and says so.
import type { PathSegment, PlayStep, Trace } from "../flow/api.ts";
import type { SessionStep } from "./session.ts";

export type Cell = [number, number];
export type Where = { map: string | null; cell: Cell | null };
export type Beat = {
  i: number;
  t0: number; // absolute: the session's mock steps come first
  t1: number;
  kind: PlayStep["kind"] | "session";
  node: string; // the graph node it belongs to: start | login | character | block:<name> | main
  map: string | null;
  step: PlayStep | null;
  session: SessionStep | null;
  before: Where;
  after: Where;
};
export type Timeline = {
  beats: Beat[];
  end: number;
  offset: number; // where the map flow starts (after the session)
  approximate: boolean; // no `play` from the backend: built from the walked segments
  capped: boolean;
  maps: string[]; // every map the run is on, in order of first visit
};

const ORTH_S = 0.15;
const DIAG_S = 0.212;
export const FADE_S = 0.8; // a defeated monster fades out
export const LOOT_S = 1.5; // its loot stays this long

function stepCost(a: Cell, b: Cell): number {
  return a[0] !== b[0] && a[1] !== b[1] ? DIAG_S : ORTH_S;
}

export function walkSeconds(cells: readonly Cell[]): number {
  let s = 0;
  for (let i = 1; i < cells.length; i++) s += stepCost(cells[i - 1], cells[i]);
  return s;
}

function nodeOf(block: string | null | undefined): string {
  return block ? `block:${block}` : "main";
}

/** The block a trace path names: "town.1" / "town.0.body.0" / "town: exit npc_warp" -> town. */
export function blockOfPath(path: string): string | null {
  const m = /^([A-Za-z][A-Za-z0-9_]*)/.exec(path);
  return m && m[1] !== "main" ? m[1] : null;
}

/** An older backend (no `play`): the walked segments once each, then the exits, by time. */
export function approximatePlay(paths: readonly PathSegment[], transitions: Trace["transitions"]): PlayStep[] {
  const out: PlayStep[] = [];
  for (const p of paths) {
    const block = blockOfPath(p.node);
    const s = walkSeconds(p.cells);
    out.push({ kind: "walk", t0: Math.max(0, p.t - s), t1: p.t, block, map: p.map, cells: p.cells, estimated: p.estimated, node: p.node });
  }
  for (const x of transitions) {
    if (x.kind === "death_respawn") {
      out.push({ kind: "arrive", t0: x.t, t1: x.t, block: x.to, map: x.map, via: "respawn", cell: null });
      continue;
    }
    out.push({ kind: "exit", t0: x.t, t1: x.t, block: x.from, map: null, exit: x.kind, from_block: x.from, to_block: x.to, to_entry: x.entry ?? undefined, to_map: x.map, cell: null, arrived: x.arrived });
  }
  out.sort((a, b) => a.t0 - b.t0 || (a.kind === "exit" ? 1 : 0) - (b.kind === "exit" ? 1 : 0));
  // a segment re-walked later would overlap the next one: keep the order, never go back in time
  let t = 0;
  for (const s of out) {
    if (s.t0 < t) {
      const d = s.t1 - s.t0;
      s.t0 = t;
      s.t1 = Math.max(s.t1, t + d);
    }
    t = s.t1;
  }
  return out;
}

export function buildTimeline(trace: Trace, session: readonly SessionStep[] | null): Timeline {
  const beats: Beat[] = [];
  const offset = session && session.length ? session[session.length - 1].t1 : 0;
  const start: Where = { map: trace.start.map, cell: trace.start.cell };
  for (const s of session ?? []) {
    beats.push({ i: beats.length, t0: s.t0, t1: s.t1, kind: "session", node: s.node, map: null, step: null, session: s, before: { map: null, cell: null }, after: s.node === "character" ? start : { map: null, cell: null } });
  }
  const approximate = !Array.isArray(trace.play);
  const steps = approximate ? approximatePlay(trace.paths, trace.transitions) : (trace.play ?? []);
  let cur: Where = start;
  const maps: string[] = [];
  const seen = (m: string | null) => {
    if (m && !maps.includes(m)) maps.push(m);
  };
  seen(start.map);
  for (const st of steps) {
    const map = st.map ?? cur.map;
    let before: Where = cur;
    let after: Where = cur;
    if (st.kind === "walk" && st.cells && st.cells.length) {
      before = { map, cell: st.cells[0] };
      after = { map, cell: st.cells[st.cells.length - 1] };
    } else if (st.kind === "exit") {
      after = { map: st.to_map ?? cur.map, cell: st.cell ?? (st.to_map && st.to_map !== cur.map ? null : cur.cell) };
    } else if (st.kind === "arrive") {
      after = { map: st.map ?? cur.map, cell: st.cell ?? null };
    }
    seen(map);
    if (st.kind === "exit") seen(after.map);
    beats.push({ i: beats.length, t0: st.t0 + offset, t1: st.t1 + offset, kind: st.kind, node: nodeOf(st.kind === "exit" ? (st.from_block ?? st.block) : st.block), map, step: st, session: null, before, after });
    cur = after;
  }
  const last = beats.length ? beats[beats.length - 1].t1 : 0;
  return { beats, end: Math.max(last, offset + trace.t_end_s), offset, approximate, capped: Boolean(trace.play_capped), maps };
}

/** The last beat that has started at `t` (-1: none yet). Beats are in time order. */
export function beatAt(tl: Timeline, t: number): number {
  let lo = 0;
  let hi = tl.beats.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (tl.beats[mid].t0 <= t) {
      found = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return found;
}

/** Where a walk is after `frac` of its time: between two cells, by RO's step costs. */
export function along(cells: readonly Cell[], frac: number): { x: number; y: number; index: number } {
  if (cells.length === 0) return { x: 0, y: 0, index: 0 };
  if (cells.length === 1 || frac <= 0) return { x: cells[0][0], y: cells[0][1], index: 0 };
  if (frac >= 1) {
    const c = cells[cells.length - 1];
    return { x: c[0], y: c[1], index: cells.length - 1 };
  }
  const total = walkSeconds(cells);
  let want = total * frac;
  for (let i = 1; i < cells.length; i++) {
    const c = stepCost(cells[i - 1], cells[i]);
    if (want <= c) {
      const k = want / c;
      return { x: cells[i - 1][0] + (cells[i][0] - cells[i - 1][0]) * k, y: cells[i - 1][1] + (cells[i][1] - cells[i - 1][1]) * k, index: i - 1 };
    }
    want -= c;
  }
  const c = cells[cells.length - 1];
  return { x: c[0], y: c[1], index: cells.length - 1 };
}

export type Pose = { map: string | null; x: number; y: number; known: boolean; beat: number; node: string };

/** Where the character is at `t`, and the beat that holds it (null: an empty timeline). */
export function poseAt(tl: Timeline, t: number): Pose | null {
  if (!tl.beats.length) return null;
  const i = Math.max(0, beatAt(tl, t));
  const b = tl.beats[i];
  let where: Where = t < b.t0 ? b.before : t >= b.t1 ? b.after : b.before;
  if (b.kind === "walk" && b.step?.cells && t >= b.t0 && t < b.t1) {
    const p = along(b.step.cells, (t - b.t0) / Math.max(1e-6, b.t1 - b.t0));
    return { map: b.map, x: p.x, y: p.y, known: true, beat: i, node: b.node };
  }
  if (b.kind === "session" && t >= b.t1 && b.session?.node === "character") where = b.after;
  const c = where.cell;
  return { map: where.map, x: c ? c[0] : 0, y: c ? c[1] : 0, known: c !== null, beat: i, node: b.node };
}

// --- what the map shows at a time ------------------------------------------------------------------
export type Monster = { x: number; y: number; mob: number | null; state: "near" | "fight" | "down"; hp: number; alpha: number; beat: number };
export type Loot = { x: number; y: number; alpha: number };
export type Bubble = { x: number; y: number; text: string; npc: string | null };
export type Overlay = { monsters: Monster[]; loot: Loot[]; bubble: Bubble | null; talking: string | null };

export function overlayAt(tl: Timeline, t: number, map: string | null, labels: Labels | null = null): Overlay {
  const monsters: Monster[] = [];
  const loot: Loot[] = [];
  let bubble: Bubble | null = null;
  let talking: string | null = null;
  for (const b of tl.beats) {
    if (b.map !== map || !b.step) continue;
    const st = b.step;
    if (st.kind === "fight" && st.at) {
      const seen = (st.seen_t ?? st.t0) + tl.offset;
      if (t >= seen && t <= b.t1 + FADE_S) {
        const state = t < b.t0 ? "near" : t < b.t1 ? "fight" : "down";
        const hp = state === "near" ? 1 : state === "fight" ? 1 - (t - b.t0) / Math.max(1e-6, b.t1 - b.t0) : 0;
        monsters.push({ x: st.at[0], y: st.at[1], mob: st.mob ?? null, state, hp, alpha: state === "down" ? Math.max(0, 1 - (t - b.t1) / FADE_S) : 1, beat: b.i });
      }
      if (st.loot && t >= b.t1 && t <= b.t1 + LOOT_S) loot.push({ x: st.at[0], y: st.at[1], alpha: 1 - (t - b.t1) / LOOT_S });
    }
    if ((st.kind === "talk" || st.kind === "menu") && t >= b.t0 && t < Math.max(b.t1, b.t0 + 0.6)) {
      const at = st.at ?? b.after.cell;
      if (at) bubble = { x: at[0], y: at[1], text: beatText(b, labels), npc: st.npc ?? null };
      talking = st.npc ?? null;
    }
  }
  return { monsters, loot, bubble, talking };
}

/** The walked part of every walk on `map` up to `t`, and the rest of the walk in progress. */
export function trailAt(tl: Timeline, t: number, map: string | null): { done: Cell[][]; walking: Cell[] | null; ahead: Cell[] | null; estimated: boolean } {
  const done: Cell[][] = [];
  let walking: Cell[] | null = null;
  let ahead: Cell[] | null = null;
  let estimated = false;
  for (const b of tl.beats) {
    if (b.t0 > t) break;
    if (b.kind !== "walk" || b.map !== map || !b.step?.cells?.length) continue;
    const cells = b.step.cells;
    estimated ||= Boolean(b.step.estimated);
    if (t >= b.t1) {
      done.push(cells);
      continue;
    }
    const p = along(cells, (t - b.t0) / Math.max(1e-6, b.t1 - b.t0));
    walking = [...cells.slice(0, p.index + 1), [p.x, p.y]];
    ahead = [[p.x, p.y], ...cells.slice(p.index + 1)];
  }
  return { done, walking, ahead, estimated };
}

// --- words ------------------------------------------------------------------------------------------
export type Labels = { mobs: Record<string, string>; npcs: Record<string, string>; items: Record<string, string>; options: Record<string, string> };

const cellText = (c: Cell | null | undefined) => (c ? `(${c[0]}, ${c[1]})` : "an unknown cell");

function named(map: Record<string, string> | undefined, key: string | number | null | undefined, kind: string): string {
  if (key === null || key === undefined) return `a ${kind}`;
  const label = map?.[String(key)];
  return label ? `${label} (${key})` : `${kind} ${key}`;
}

const EXIT_WORDS: Record<string, string> = { walk_exit: "walk exit", npc_warp: "NPC warp", item_warp: "item warp" };

/** One beat in words, as the "What happens" list says it. */
export function beatText(b: Beat, labels: Labels | null): string {
  if (b.session) return b.session.text;
  const st = b.step;
  if (!st) return "";
  const L = labels ?? undefined;
  const bad = st.outcome && st.outcome !== "ok" ? ` (${st.outcome})` : "";
  switch (st.kind) {
    case "walk": {
      const n = (st.cells?.length ?? 1) - 1;
      const to = cellText(st.cells?.[st.cells.length - 1]);
      const why = st.purpose === "engage" ? "walk up to the monster" : st.purpose === "npc" ? "walk to the NPC" : st.purpose === "exit" ? "walk to the exit" : "walk";
      return `${why}: to ${to}, ${n} cell${n === 1 ? "" : "s"}${st.estimated ? " (an estimate: no walk grid)" : ""}${st.trimmed ? " (the route is shortened in the list)" : ""}`;
    }
    case "talk": {
      const who = named(L?.npcs, st.npc ?? null, "NPC");
      const what = st.action === "set_save_point" ? "set the save point with" : st.action?.startsWith("take_exit") ? "warp with" : "talk to";
      const opts = st.options?.length ? `, choose ${st.options.map((o) => named(L?.options, o, "option")).join(" → ")}` : "";
      return `${what} ${who} at ${cellText(st.at)}${opts}${bad}`;
    }
    case "menu":
      return st.action === "close_dialog" ? `close the dialog${bad}` : `choose ${named(L?.options, st.option ?? null, "option")}${bad}`;
    case "fight": {
      if (st.at === null || st.at === undefined) return `fight in place: no monster placed (the simulator only spends ${(b.t1 - b.t0).toFixed(1)} s)${bad}`;
      return `meet ${named(L?.mobs, st.mob ?? null, "monster")} at ${cellText(st.at)}: fight, defeat${st.loot ? ", loot" : ""}${bad}`;
    }
    case "item":
      // an item warp by a function: the function and its key (the wing is whatever is on that slot)
      if (st.proc) return `call ${st.proc}()${st.key ? `: press ${st.key}` : ""} (the Butterfly Wing: back to the save point)${bad}`;
      return `use ${named(L?.items, st.item ?? null, "item")}${st.item_kind === "butterfly_wing" ? " (back to the save point)" : st.item_kind === "heal" ? " (heal)" : ""}${bad}`;
    case "loot":
      return `pick up the loot${bad}`;
    case "respawn":
      return `dead: respawn${bad}`;
    case "wait":
      return `wait ${(b.t1 - b.t0).toFixed(1)} s`;
    case "exit":
      return `${EXIT_WORDS[st.exit ?? ""] ?? st.exit} → ${st.to_block}${st.to_map ? ` (${st.to_map}${st.cell ? ` ${st.cell[0]}, ${st.cell[1]}` : ""})` : ""}${st.arrived === false ? ": did NOT arrive" : ""}`;
    case "arrive":
      return `arrive on ${st.map ?? "?"} at ${cellText(st.cell)}${st.via ? ` (${st.via.replaceAll("_", " ")})` : ""}`;
    default:
      return `${(st.action ?? "a block").replaceAll("_", " ")}${bad}`;
  }
}

export type Check = { ok: boolean | null; text: string }; // null: not known

/** matpilot's run checks, for maps: the session, every map block reached, the exits, the end. */
export function runChecks(tl: Timeline, trace: Trace, blocks: readonly { name: string; map: string }[], endText: string, seed: number | null): Check[] {
  const out: Check[] = [];
  if (tl.offset > 0) out.push({ ok: true, text: "Logged in and entered the game (a mock: simulated, nothing ran)" });
  for (const b of blocks) {
    const v = trace.blocks[b.name]?.visits ?? 0;
    out.push(v > 0 ? { ok: true, text: `Reached ${b.name} (${b.map}): ${v} visit${v === 1 ? "" : "s"}` } : { ok: false, text: `Never reached ${b.name} (${b.map})` });
  }
  const missed = trace.transitions.filter((x) => !x.arrived);
  if (trace.transitions.length) out.push(missed.length ? { ok: false, text: `${missed.length} exit${missed.length === 1 ? "" : "s"} did not arrive (${missed[0].from} → ${missed[0].to})` } : { ok: true, text: `Every exit arrived (${trace.transitions.length})` });
  const ended = ["done", "horizon", "single_block_exit"].includes(trace.end);
  out.push({ ok: ended, text: `Ended: ${endText}` });
  const fights = tl.beats.filter((b) => b.kind === "fight");
  const placed = fights.filter((b) => b.step?.at);
  if (fights.length) {
    out.push(
      placed.length
        ? { ok: true, text: `Met ${placed.length} monster${placed.length === 1 ? "" : "s"}${seed === null ? "" : ` (placed from seed ${seed})`}` }
        : { ok: null, text: `${fights.length} fight${fights.length === 1 ? "" : "s"} with no monster placed (the backend placed none)` },
    );
  }
  if (tl.beats.some((b) => b.step?.estimated)) out.push({ ok: null, text: "Some walks are estimates: a map has no walk grid in the static data" });
  if (tl.approximate) out.push({ ok: null, text: "Approximate: the backend gave no step list (an older backend), so each walked route is shown once" });
  if (tl.capped) out.push({ ok: null, text: "The step list was capped: the end of the run is not shown step by step" });
  return out;
}
