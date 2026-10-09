// The operator HUD (Batt 2026-10-08, docs/phase4-ui.md): what the rule saw and decided, over the
// stream. Display only: an agent -> backend -> viewer message (OperatorHud) that carries no input
// and never reaches the mux. A per-tab toggle, off on every load, like "Watch only". Pure, unit
// tested with `node --test` (src/lib/hud.test.ts). Every string it returns is drawn as TEXT
// (canvas fillText or a React text node), never as markup.

import type { HudUnit, OperatorHud } from "./protocol.ts";

export type PxPoint = { x: number; y: number };
export type PxRect = { x: number; y: number; w: number; h: number };

/** A HUD message and when this tab received it (performance.now(), this tab's clock). The agent's
 * t_mono_ns is the host clock, a different domain: ages are measured from the receipt. */
export type HudFrame = { msg: OperatorHud; at: number };

export const HUD_LOG_LINES = 12;
export const HUD_LINE_CHARS = 96;

export function pointPx(p: { x: number; y: number }, width: number, height: number): PxPoint {
  return { x: p.x * width, y: p.y * height };
}

export function rectPx(r: { x: number; y: number; w: number; h: number }, width: number, height: number): PxRect {
  return { x: r.x * width, y: r.y * height, w: r.w * width, h: r.h * height };
}

/** Whether the message is still shown: ttl_ms after its receipt (0 clears at once). */
export function hudAlive(hud: OperatorHud | null, ageMs: number): boolean {
  return hud != null && hud.ttl_ms > 0 && ageMs < hud.ttl_ms;
}

/** "1 cell", "4 cells", "? cells" -- the rules reason in cells (Chebyshev, from our cell). */
export function cellsText(dist: number | null | undefined): string {
  if (dist == null) return "? cells";
  return dist === 1 ? "1 cell" : `${dist} cells`;
}

/** A box's label: class, confidence and distance in cells, e.g. "monster 81% 4 cells". */
export function unitLabel(u: HudUnit): string {
  return `${plain(u.cls, 32)} ${Math.round(u.conf * 100)}% ${cellsText(u.dist_cells)}`;
}

/** The locked unit's index in this message: by index first, else by track id; -1 when the lock
 * names no unit in view (the countdown is then shown in the panel only). */
export function lockedIndex(hud: OperatorHud | null): number {
  const lock = hud?.lock;
  if (!hud || !lock) return -1;
  if (lock.index != null && lock.index < hud.units.length) return lock.index;
  if (lock.id != null) return hud.units.findIndex((u) => u.id === lock.id);
  return -1;
}

/** The lock's countdown now: its remaining time minus the time since the message arrived. */
export function lockRemainingMs(hud: OperatorHud | null, ageMs: number): number | null {
  if (!hud?.lock) return null;
  return Math.max(0, hud.lock.lock_remaining_ms - Math.max(0, ageMs));
}

export function lockText(ms: number | null): string {
  return ms == null ? "" : `LOCK ${(ms / 1000).toFixed(1)} s`;
}

export type HudBox = PxRect & { cls: string; label: string; foot: PxPoint; locked: boolean };

/** Every unit's box in canvas pixels, with its label; the locked one flagged. */
export function hudBoxes(hud: OperatorHud | null, width: number, height: number): HudBox[] {
  if (!hud) return [];
  const locked = lockedIndex(hud);
  return hud.units.map((u, i) => ({
    ...rectPx(u.box, width, height),
    cls: u.cls,
    label: unitLabel(u),
    foot: pointPx(u.foot, width, height),
    locked: i === locked,
  }));
}

/** The work zone in canvas pixels: the game area and the client's UI windows taken out of it. */
export function zonePx(
  hud: OperatorHud | null,
  width: number,
  height: number,
): { area: PxRect; exclude: PxRect[] } | null {
  if (!hud?.zone) return null;
  return {
    area: rectPx(hud.zone.area, width, height),
    exclude: hud.zone.exclude.map((r) => rectPx(r, width, height)),
  };
}

/** "(102,110)" for a map cell. */
export function cellText(c: { x: number; y: number } | null | undefined): string {
  return c ? `(${c.x},${c.y})` : "";
}

/** The walk vector in canvas pixels (start/end only when the agent put them on screen) and its
 * text: the agent's own words, else the destination cell. */
export function walkPx(
  hud: OperatorHud | null,
  width: number,
  height: number,
): { start: PxPoint | null; end: PxPoint | null; text: string; dest: string } | null {
  const walk = hud?.walk;
  if (!walk) return null;
  const dest = cellText(walk.dest);
  return {
    start: walk.start ? pointPx(walk.start, width, height) : null,
    end: walk.end ? pointPx(walk.end, width, height) : null,
    text: plain(walk.text, HUD_LINE_CHARS) || (dest ? `to ${dest}` : ""),
    dest,
  };
}

/** The arrowhead at the end of a vector: two barbs of length `size`. */
export function arrowHead(start: PxPoint, end: PxPoint, size = 10): [PxPoint, PxPoint] | null {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const len = Math.hypot(dx, dy);
  if (len < 1e-6) return null;
  const ux = dx / len;
  const uy = dy / len;
  const back = { x: end.x - ux * size, y: end.y - uy * size };
  const nx = -uy * size * 0.5;
  const ny = ux * size * 0.5;
  return [
    { x: back.x + nx, y: back.y + ny },
    { x: back.x - nx, y: back.y - ny },
  ];
}

/** "3 units · det 4.2 fps" (det "–" when the agent does not know its rate). */
export function counterText(hud: OperatorHud | null): string {
  if (!hud) return "";
  const n = hud.counters.units;
  const fps = hud.counters.det_fps;
  return `${n} ${n === 1 ? "unit" : "units"} · det ${fps == null ? "–" : fps.toFixed(1)} fps`;
}

/** The log's lines, oldest first, bounded again here (defence in depth: the protocol already
 * refuses control characters and long lines). */
export function logLines(hud: OperatorHud | null, max = HUD_LOG_LINES): string[] {
  if (!hud) return [];
  return hud.log.slice(-max).map((line) => plain(line, HUD_LINE_CHARS));
}

/** Control characters out, length bounded: one plain line of text. */
export function plain(text: string, max: number): string {
  let out = "";
  for (const ch of text) {
    const code = ch.codePointAt(0) ?? 0;
    out += code < 0x20 || code === 0x7f ? " " : ch;
    if (out.length >= max) break;
  }
  return out.slice(0, max);
}

/** The colour of a unit's box, by class. */
export function classColour(cls: string): string {
  switch (cls) {
    case "monster":
      return "#f87171";
    case "player":
      return "#60a5fa";
    case "npc":
      return "#facc15";
    default:
      return "#a3e635";
  }
}

/** The toggle's button text and its tooltip. */
export function hudToggle(on: boolean): { label: string; title: string } {
  return on
    ? {
        label: "HUD ON",
        title:
          "The operator HUD is ON in this tab: the rule's boxes (class, confidence, distance in " +
          "cells), its locked target, the work zone, the walk vector, counters and a short log. " +
          "Display only: it sends nothing. Click to hide it.",
      }
    : {
        label: "HUD",
        title:
          "Show the operator HUD in this tab: what the rule sees and decides, over the stream. " +
          "Display only, off on every load.",
      };
}

// WHY an overlay is empty (its feed lines) lives in ./feeds.ts since 2026-10-09.
