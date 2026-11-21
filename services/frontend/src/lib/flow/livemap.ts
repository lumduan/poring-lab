/** The live map on /flows (Batt 2026-11-21: "while a Run plays, a map like the minimap: where the
 * bot is as a green dot, the monsters it sees as red dots; the map as on /maps"). The Run helper's
 * summary gives her map (the player's read), her cell (the minimap, once a second), her last cells
 * and the monsters of the detector's last read placed on the map from her cell (scripts/flow_play.py
 * Sight: the runner's flat box projection, within 1 cell of the runner's own placement on 87.5 % of
 * 520 fights). PURE: drawn on a 2D context (the /maps colours), text by the canvas, never HTML. RO
 * cells grow NORTH: y = 0 is the bottom row. */
import type { Colours, Ctx } from "../maps/draw.ts";
import type { LiveSummary } from "./liverun.ts";

export type Cell = [number, number];
export type Mob = { x: number; y: number; name: string };
export type Sight = { map: string | null; pos: Cell | null; trail: Cell[]; mobs: Mob[] | null; ageS: number | null };

export const SIGHT_STALE_S = 3; // the monsters' dots fade when the last read is older
export const HER_COLOUR = "#22c55e"; // Batt: her dot is green
export const NEAR_R = 18; // the close-up: this many cells on each side of her

export const MAP_VIEWS = ["whole", "near"] as const;
export type MapView = (typeof MAP_VIEWS)[number];

function cellOf(v: unknown): Cell | null {
  if (!Array.isArray(v) || v.length < 2) return null;
  const x = Number(v[0]);
  const y = Number(v[1]);
  return Number.isInteger(x) && Number.isInteger(y) ? [x, y] : null;
}

/** What the map shows, from the Run's summary (an older helper: no map, no trail, no monsters). */
export function sightOf(l: LiveSummary | null | undefined): Sight {
  if (!l) return { map: null, pos: null, trail: [], mobs: null, ageS: null };
  const trail = (Array.isArray(l.trail) ? l.trail : []).map(cellOf).filter((c): c is Cell => c !== null);
  let mobs: Mob[] | null = null;
  if (Array.isArray(l.mobs)) {
    mobs = [];
    for (const m of l.mobs) {
      const c = cellOf(m);
      if (c) mobs.push({ x: c[0], y: c[1], name: typeof m[2] === "string" ? m[2].slice(0, 32) : "monster" });
    }
  }
  return { map: typeof l.map === "string" && l.map ? l.map : null, pos: cellOf(l.pos), trail, mobs, ageS: typeof l.mobs_age_s === "number" ? l.mobs_age_s : null };
}

export type Win = { x0: number; y0: number; w: number; h: number }; // x0, y0: the window's bottom-left cell

/** The cells drawn: the whole map, or a close-up around her (kept inside the map). */
export function viewWindow(view: MapView, pos: Cell | null, mapW: number, mapH: number): Win {
  const whole = { x0: 0, y0: 0, w: mapW, h: mapH };
  if (view === "whole" || !pos) return whole;
  const side = 2 * NEAR_R + 1;
  const w = Math.min(side, mapW);
  const h = Math.min(side, mapH);
  const x0 = Math.max(0, Math.min(mapW - w, pos[0] - NEAR_R));
  const y0 = Math.max(0, Math.min(mapH - h, pos[1] - NEAR_R));
  return { x0, y0, w, h };
}

/** A cell's centre in the window's pixels. */
export function cellPx(win: Win, scale: number, x: number, y: number): { x: number; y: number } {
  return { x: (x - win.x0 + 0.5) * scale, y: (win.y0 + win.h - 1 - y + 0.5) * scale };
}

function inside(win: Win, x: number, y: number): boolean {
  return x >= win.x0 && x < win.x0 + win.w && y >= win.y0 && y < win.y0 + win.h;
}

export type LiveDraw = { rows: readonly string[] | null; win: Win; scale: number; sight: Sight; colours: Colours };

/** The window's walk grid (as /maps: grey walkable, dark blocked), her trail, the monsters (red;
 * faded when stale) and her (green, over them). Returns what was drawn. */
export function drawLive(ctx: Ctx, d: LiveDraw): { her: boolean; mobs: number; trail: number } {
  const { rows, win, scale, sight, colours } = d;
  ctx.globalAlpha = 1;
  ctx.fillStyle = rows ? colours.wall : colours.empty;
  ctx.fillRect(0, 0, win.w * scale, win.h * scale);
  if (rows) {
    ctx.fillStyle = colours.floor;
    for (let y = win.y0; y < win.y0 + win.h && y < rows.length; y++) {
      const row = rows[y] ?? "";
      const py = (win.y0 + win.h - 1 - y) * scale;
      let x = win.x0;
      const end = Math.min(row.length, win.x0 + win.w);
      while (x < end) {
        if (row[x] !== ".") {
          x++;
          continue;
        }
        const x0 = x;
        while (x < end && row[x] === ".") x++;
        ctx.fillRect((x0 - win.x0) * scale, py, (x - x0) * scale, scale);
      }
    }
  }
  const trail = sight.trail.filter(([x, y]) => inside(win, x, y));
  if (trail.length > 1) {
    ctx.strokeStyle = HER_COLOUR;
    ctx.globalAlpha = 0.45;
    ctx.lineWidth = Math.max(1, scale * 0.35);
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.beginPath();
    trail.forEach(([x, y], i) => {
      const p = cellPx(win, scale, x, y);
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.stroke();
    ctx.globalAlpha = 1;
  }
  let mobs = 0;
  const stale = sight.ageS !== null && sight.ageS > SIGHT_STALE_S;
  for (const m of sight.mobs ?? []) {
    if (!inside(win, m.x, m.y)) continue;
    const p = cellPx(win, scale, m.x, m.y);
    ctx.globalAlpha = stale ? 0.35 : 1;
    ctx.fillStyle = colours.monster;
    ctx.strokeStyle = colours.wall;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(p.x, p.y, Math.max(2.5, scale * 0.55), 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    if (scale >= 10) {
      ctx.font = `${Math.round(Math.min(14, scale * 0.9))}px sans-serif`;
      ctx.fillStyle = colours.text;
      ctx.fillText(m.name, p.x + scale * 0.7, p.y - scale * 0.5);
    }
    mobs++;
  }
  ctx.globalAlpha = 1;
  let her = false;
  if (sight.pos && inside(win, sight.pos[0], sight.pos[1])) {
    const p = cellPx(win, scale, sight.pos[0], sight.pos[1]);
    ctx.fillStyle = HER_COLOUR;
    ctx.strokeStyle = colours.botEdge;
    ctx.lineWidth = Math.max(1.5, scale * 0.2);
    ctx.beginPath();
    ctx.arc(p.x, p.y, Math.max(3.5, scale * 0.8), 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    her = true;
  }
  return { her, mobs, trail: trail.length };
}

/** The line under the map, in words. */
export function sightLine(s: Sight, running: boolean): string {
  if (!s.map) return running ? "Waiting for her first reading of the screen." : "No Run is playing.";
  const parts = [`map ${s.map}`, s.pos ? `her cell (${s.pos[0]}, ${s.pos[1]})` : "her cell not read yet"];
  if (s.mobs === null) parts.push("no hunt core playing: no monsters to show");
  else {
    const n = s.mobs.length;
    const age = s.ageS === null ? "" : `, ${s.ageS.toFixed(1)} s ago${s.ageS > SIGHT_STALE_S ? " (faded: not read since)" : ""}`;
    parts.push(`${n === 1 ? "1 monster" : `${n} monsters`} seen${age}`);
  }
  return parts.join(" · ");
}
