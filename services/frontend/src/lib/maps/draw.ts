// The Maps page's MAP VIEW drawing (components/maps/MatView.tsx), as pure functions over a 2D
// context, so node can test them with a recording context (draw.test.ts): the walk grid (grey
// walkable, dark blocked, as Batt's xmas_dun02 picture), the static data's warps, NPCs and the save
// point, and at a time the routes walked (green), the rest of the walk in progress (dashed), the
// monster met (its HP bar, defeated and fading), its loot, the character, and a speech bubble over
// the NPC talked to. Text is drawn by the canvas, never HTML. RO's cells grow NORTH: y = 0 is the
// bottom row, so screen y = (h - 1 - y) * scale.
import type { WorldMap } from "../flow/api.ts";
import { type Labels, overlayAt, poseAt, type Timeline, trailAt } from "./play.ts";

export type Colours = Record<
  "floor" | "wall" | "trail" | "route" | "bot" | "botEdge" | "monster" | "npc" | "warp" | "save" | "loot" | "text" | "bubble" | "bubbleText" | "empty",
  string
>;
export const COLOUR_VARS: Record<keyof Colours, string> = {
  floor: "--mat-floor",
  wall: "--mat-wall",
  trail: "--mat-trail",
  route: "--mat-route",
  bot: "--mat-bot",
  botEdge: "--mat-bot-edge",
  monster: "--mat-monster",
  npc: "--mat-npc",
  warp: "--mat-warp",
  save: "--mat-save",
  loot: "--mat-loot",
  text: "--mat-text",
  bubble: "--mat-bubble",
  bubbleText: "--mat-bubble-text",
  empty: "--mat-empty",
};
export const FALLBACK_COLOURS: Colours = {
  floor: "#a7aeb6",
  wall: "#1b1f24",
  trail: "#15803d",
  route: "#1f5fbf",
  bot: "#1f5fbf",
  botEdge: "#ffffff",
  monster: "#dc2626",
  npc: "#c2410c",
  warp: "#7c3aed",
  save: "#be123c",
  loot: "#ca8a04",
  text: "#1b1f24",
  bubble: "#ffffff",
  bubbleText: "#1b1f24",
  empty: "#d6dbe1",
};

/** The parts of a CanvasRenderingContext2D the map view uses. */
export type Ctx = Pick<
  CanvasRenderingContext2D,
  | "fillRect"
  | "clearRect"
  | "beginPath"
  | "arc"
  | "fill"
  | "stroke"
  | "moveTo"
  | "lineTo"
  | "closePath"
  | "setLineDash"
  | "fillText"
  | "strokeText"
  | "measureText"
  | "roundRect"
> & {
  fillStyle: CanvasRenderingContext2D["fillStyle"];
  strokeStyle: CanvasRenderingContext2D["strokeStyle"];
  lineWidth: number;
  lineJoin: CanvasLineJoin;
  lineCap: CanvasLineCap;
  globalAlpha: number;
  font: string;
};

/** The map's size: its grid, else its sheet's, else what the run touched on it (an estimate). */
export function mapSize(map: string | null, rows: readonly string[] | null, sheet: WorldMap | null, tl: Timeline | null): { w: number; h: number; known: boolean } {
  if (rows?.length) return { w: rows[0].length, h: rows.length, known: true };
  if (sheet?.size) return { w: sheet.size[0], h: sheet.size[1], known: true };
  let w = 20;
  let h = 20;
  for (const b of tl?.beats ?? []) {
    if (b.map !== map || !b.step) continue;
    for (const c of [...(b.step.cells ?? []), b.step.at, b.step.cell]) {
      if (!c) continue;
      w = Math.max(w, c[0] + 10);
      h = Math.max(h, c[1] + 10);
    }
  }
  return { w, h, known: false };
}

/** The largest CSS pixels a cell at which a w x h map fits a box (its aspect kept; round 2: the map
 * fills the stage instead of a whole number of pixels a cell); at least 0.5, at most 24. */
export function fitScale(boxW: number, boxH: number, w: number, h: number): number {
  if (!(boxW > 0 && boxH > 0 && w > 0 && h > 0)) return 1;
  return Math.max(0.5, Math.min(24, Math.min((boxW - 4) / w, (boxH - 4) / h)));
}

/** The walk grid: dark everywhere, walkable runs of each row in grey (no grid: one plain area). */
export function drawGrid(ctx: Ctx, rows: readonly string[] | null, w: number, h: number, scale: number, colours: Colours): void {
  ctx.fillStyle = rows ? colours.wall : colours.empty;
  ctx.fillRect(0, 0, w * scale, h * scale);
  if (!rows) return;
  ctx.fillStyle = colours.floor;
  for (let y = 0; y < rows.length; y++) {
    const row = rows[y];
    const py = (h - 1 - y) * scale;
    let x = 0;
    while (x < row.length) {
      if (row[x] !== ".") {
        x++;
        continue;
      }
      const x0 = x;
      while (x < row.length && row[x] === ".") x++;
      ctx.fillRect(x0 * scale, py, (x - x0) * scale, scale);
    }
  }
}

export type DrawInput = {
  map: string | null;
  w: number;
  h: number;
  scale: number;
  sheet: WorldMap | null;
  tl: Timeline | null;
  time: number;
  labels: Labels | null;
  savePoint: { map: string; cell: [number, number] } | null;
  colours: Colours;
};

/** Everything over the grid at `time`; returns where the character was drawn (px), or null. */
export function drawScene(ctx: Ctx, d: DrawInput): { bot: { x: number; y: number } | null; monsters: number; bubble: string | null } {
  const { map, w, h, scale, sheet, tl, time, labels, savePoint, colours } = d;
  const X = (x: number) => x * scale + scale / 2;
  const Y = (y: number) => (h - 1 - y) * scale + scale / 2;
  const dot = (x: number, y: number, r: number, fill: string, edge?: string) => {
    ctx.beginPath();
    ctx.arc(X(x), Y(y), r, 0, Math.PI * 2);
    ctx.fillStyle = fill;
    ctx.fill();
    if (edge) {
      ctx.lineWidth = Math.max(1.5, scale * 0.25);
      ctx.strokeStyle = edge;
      ctx.stroke();
    }
  };
  const label = (text: string, x: number, y: number, colour: string) => {
    ctx.font = "600 11px system-ui, sans-serif";
    ctx.lineWidth = 3;
    ctx.strokeStyle = colours.bubble;
    ctx.strokeText(text, X(x) + scale, Y(y) - scale);
    ctx.fillStyle = colour;
    ctx.fillText(text, X(x) + scale, Y(y) - scale);
  };
  const line = (cells: readonly (readonly [number, number])[], colour: string, width: number, dash: number[] = [], alpha = 1) => {
    if (cells.length < 2) return;
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = colour;
    ctx.lineWidth = width;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.setLineDash(dash);
    ctx.beginPath();
    cells.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(X(x), Y(y)) : ctx.lineTo(X(x), Y(y))));
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;
  };
  const big = scale >= 4;
  // the static data: warps, NPCs, the save point
  for (const wp of sheet?.warps ?? []) {
    ctx.beginPath();
    ctx.arc(X(wp.x), Y(wp.y), Math.max(4, scale * 1.4), 0, Math.PI * 2);
    ctx.lineWidth = 2;
    ctx.strokeStyle = colours.warp;
    ctx.stroke();
    if (big) label(`warp → ${wp.to_map}`, wp.x, wp.y, colours.warp);
  }
  const over = tl ? overlayAt(tl, time, map, labels) : null;
  for (const n of sheet?.npcs ?? []) {
    const s = Math.max(5, scale * 1.4);
    ctx.fillStyle = colours.npc;
    ctx.fillRect(X(n.x) - s / 2, Y(n.y) - s / 2, s, s);
    if (big || over?.talking === n.key) label(labels?.npcs[n.key] ?? n.key, n.x, n.y, colours.npc);
  }
  if (savePoint && savePoint.map === map) {
    const [sx, sy] = savePoint.cell;
    const s = Math.max(4, scale * 1.3);
    ctx.strokeStyle = colours.save;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(X(sx) - s, Y(sy) - s);
    ctx.lineTo(X(sx) + s, Y(sy) + s);
    ctx.moveTo(X(sx) + s, Y(sy) - s);
    ctx.lineTo(X(sx) - s, Y(sy) + s);
    ctx.stroke();
    if (big) label("save point", sx, sy, colours.save);
  }
  if (!tl || !over) return { bot: null, monsters: 0, bubble: null };
  // the trails: walked (green), the rest of the walk in progress (dashed)
  const tr = trailAt(tl, time, map);
  const tw = Math.max(1.5, scale * 0.55);
  for (const c of tr.done) line(c, colours.trail, tw, [], 0.55);
  if (tr.ahead) line(tr.ahead, colours.route, Math.max(1.2, scale * 0.35), [Math.max(3, scale), Math.max(3, scale)], 0.9);
  if (tr.walking) line(tr.walking, colours.trail, tw);
  // the monster met (near; its fight with an HP bar; defeated and fading) and its loot
  for (const m of over.monsters) {
    ctx.globalAlpha = m.alpha;
    const r = Math.max(4, scale * 1.1);
    dot(m.x, m.y, r, colours.monster, m.state === "fight" ? colours.botEdge : undefined);
    if (m.state !== "down") {
      const bw = Math.max(14, scale * 3);
      ctx.fillStyle = colours.wall;
      ctx.fillRect(X(m.x) - bw / 2, Y(m.y) - r - 7, bw, 4);
      ctx.fillStyle = colours.monster;
      ctx.fillRect(X(m.x) - bw / 2, Y(m.y) - r - 7, bw * m.hp, 4);
      label(m.mob === null ? "a monster" : (labels?.mobs[String(m.mob)] ?? `mob ${m.mob}`), m.x, m.y + 1, colours.monster);
    }
    ctx.globalAlpha = 1;
  }
  for (const l of over.loot) {
    ctx.globalAlpha = Math.max(0, l.alpha);
    const s = Math.max(3, scale * 0.9);
    ctx.fillStyle = colours.loot;
    ctx.beginPath();
    ctx.moveTo(X(l.x), Y(l.y) - s);
    ctx.lineTo(X(l.x) + s, Y(l.y));
    ctx.lineTo(X(l.x), Y(l.y) + s);
    ctx.lineTo(X(l.x) - s, Y(l.y));
    ctx.closePath();
    ctx.fill();
    ctx.globalAlpha = 1;
  }
  // the character
  const pose = poseAt(tl, time);
  let bot: { x: number; y: number } | null = null;
  if (pose && pose.known && pose.map === map) {
    dot(pose.x, pose.y, Math.max(5, scale * 1.3), colours.bot, colours.botEdge);
    bot = { x: X(pose.x), y: Y(pose.y) };
  }
  // a speech bubble over the NPC talked to
  const bub = over.bubble;
  if (bub) {
    ctx.font = "600 12px system-ui, sans-serif";
    const text = bub.text.length > 70 ? `${bub.text.slice(0, 69)}…` : bub.text;
    const bw = ctx.measureText(text).width + 14;
    const bx = Math.min(Math.max(4, X(bub.x) - bw / 2), w * scale - bw - 4);
    const by = Math.max(4, Y(bub.y) - scale * 2 - 28);
    ctx.fillStyle = colours.bubble;
    ctx.strokeStyle = colours.npc;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.roundRect(bx, by, bw, 22, 6);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = colours.bubbleText;
    ctx.fillText(text, bx + 7, by + 15);
  }
  return { bot, monsters: over.monsters.length, bubble: bub?.text ?? null };
}
