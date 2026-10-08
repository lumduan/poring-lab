"use client";

import { useEffect, useRef } from "react";

import {
  arrowHead,
  classColour,
  counterText,
  type HudFrame,
  hudAlive,
  hudBoxes,
  lockRemainingMs,
  lockText,
  type PxRect,
  walkPx,
  zonePx,
} from "@/lib/hud";

type Props = {
  /** The latest HUD message and when this tab received it; null draws nothing. */
  hud: HudFrame | null;
  width: number;
  height: number;
};

const FONT = "12px ui-monospace, monospace";
const LABEL_BG = "rgba(0, 0, 0, 0.65)";
const LABEL_FG = "#f8fafc";
const LOCK = "#f0abfc";
const ZONE = "rgba(56, 189, 248, 0.75)";
const WALK = "rgba(70, 230, 90, 0.95)";
const SHADOW = "rgba(0, 0, 0, 0.45)";

/** The operator HUD (Batt 2026-10-08): the rule's boxes with class, confidence and distance in
 * CELLS, the locked target and its countdown, the work zone, the walk vector and the counters, on
 * its own canvas over the stream. Display only: it draws, it sends nothing. Every string is drawn
 * with fillText (text, never markup). Cleared ttl_ms after the message arrived; while a lock is
 * shown it redraws each animation frame so the countdown runs. */
export default function HudCanvas({ hud, width, height }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);
    if (!hud) return;
    let raf = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const draw = () => {
      const age = performance.now() - hud.at;
      ctx.clearRect(0, 0, width, height);
      if (!hudAlive(hud.msg, age)) return false; // expired: cleared
      drawHud(ctx, hud, age, width, height);
      return true;
    };
    if (hud.msg.lock) {
      const tick = () => {
        if (draw()) raf = requestAnimationFrame(tick);
      };
      tick();
    } else if (draw()) {
      const left = hud.msg.ttl_ms - (performance.now() - hud.at);
      timer = setTimeout(() => ctx.clearRect(0, 0, width, height), Math.max(0, left));
    }
    return () => {
      cancelAnimationFrame(raf);
      if (timer) clearTimeout(timer);
    };
  }, [hud, width, height]);

  return (
    <canvas
      ref={ref}
      width={width}
      height={height}
      className="pointer-events-none absolute inset-0 h-full w-full"
    />
  );
}

function drawHud(ctx: CanvasRenderingContext2D, hud: HudFrame, ageMs: number, w: number, h: number) {
  const msg = hud.msg;
  ctx.save();
  ctx.font = FONT;
  ctx.textBaseline = "bottom";

  // the work zone: the game area (dashed) and the client's UI windows taken out of it (dimmed)
  const zone = zonePx(msg, w, h);
  if (zone) {
    ctx.fillStyle = "rgba(15, 23, 42, 0.35)";
    ctx.strokeStyle = "rgba(148, 163, 184, 0.6)";
    ctx.lineWidth = 1;
    for (const r of zone.exclude) {
      ctx.fillRect(r.x, r.y, r.w, r.h);
      ctx.strokeRect(r.x, r.y, r.w, r.h);
    }
    ctx.strokeStyle = ZONE;
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(zone.area.x, zone.area.y, zone.area.w, zone.area.h);
    ctx.setLineDash([]);
  }

  // the walk vector: from our feet to the destination, with the destination as text
  const walk = walkPx(msg, w, h);
  if (walk?.start && walk.end) {
    for (const [lw, style] of [
      [4, SHADOW],
      [2, WALK],
    ] as const) {
      ctx.lineWidth = lw;
      ctx.strokeStyle = style;
      ctx.beginPath();
      ctx.moveTo(walk.start.x, walk.start.y);
      ctx.lineTo(walk.end.x, walk.end.y);
      ctx.stroke();
    }
    const head = arrowHead(walk.start, walk.end, 12);
    if (head) {
      ctx.fillStyle = WALK;
      ctx.beginPath();
      ctx.moveTo(walk.end.x, walk.end.y);
      ctx.lineTo(head[0].x, head[0].y);
      ctx.lineTo(head[1].x, head[1].y);
      ctx.closePath();
      ctx.fill();
    }
    if (walk.text) label(ctx, walk.text, walk.end.x + 10, walk.end.y - 6, WALK, w);
  }

  // the units: box, feet, "class conf% N cells"; the locked one bracketed with its countdown
  const lockMs = lockRemainingMs(msg, ageMs);
  for (const b of hudBoxes(msg, w, h)) {
    const colour = b.locked ? LOCK : classColour(b.cls);
    ctx.lineWidth = b.locked ? 3 : 2;
    ctx.strokeStyle = colour;
    ctx.strokeRect(b.x, b.y, b.w, b.h);
    ctx.fillStyle = colour;
    ctx.beginPath();
    ctx.arc(b.foot.x, b.foot.y, 2.5, 0, 2 * Math.PI);
    ctx.fill();
    const top = b.y - 15 < 0 ? b.y + b.h + 16 : b.y; // no room above: below the box
    label(ctx, b.label, b.x, top, colour, w);
    if (b.locked) {
      brackets(ctx, b, LOCK);
      label(ctx, lockText(lockMs), b.x, top - 16, LOCK, w);
    }
  }

  // the counters, bottom right (clear of the chat window, bottom left)
  const counters = counterText(msg);
  if (counters) {
    const tw = ctx.measureText(counters).width;
    label(ctx, counters, w - tw - 14, h - 8, LABEL_FG, w);
  }
  ctx.restore();
}

/** One line of text on a dark plate, kept inside the canvas horizontally. */
function label(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, fg: string, w: number) {
  const tw = ctx.measureText(text).width;
  const left = Math.max(0, Math.min(x, w - tw - 6));
  ctx.fillStyle = LABEL_BG;
  ctx.fillRect(left, y - 15, tw + 6, 15);
  ctx.fillStyle = fg;
  ctx.fillText(text, left + 3, y - 2);
}

/** Corner brackets just outside a box: the lock. */
function brackets(ctx: CanvasRenderingContext2D, r: PxRect, colour: string) {
  const pad = 4;
  const len = Math.max(6, Math.min(14, Math.min(r.w, r.h) / 3));
  const x0 = r.x - pad;
  const y0 = r.y - pad;
  const x1 = r.x + r.w + pad;
  const y1 = r.y + r.h + pad;
  ctx.strokeStyle = colour;
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (const [cx, cy, dx, dy] of [
    [x0, y0, 1, 1],
    [x1, y0, -1, 1],
    [x0, y1, 1, -1],
    [x1, y1, -1, -1],
  ] as const) {
    ctx.moveTo(cx + dx * len, cy);
    ctx.lineTo(cx, cy);
    ctx.lineTo(cx, cy + dy * len);
  }
  ctx.stroke();
}
