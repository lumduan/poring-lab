"use client";

import { type MutableRefObject, useEffect, useRef } from "react";

import type { RoutePreview } from "@/lib/protocol";
import { clipRects, passedPixels, pickForFrame, routePixels } from "@/lib/route";

type Props = {
  /** LIVE previews (newest last) and the capture time of the frame on screen (host clock). */
  liveRef: MutableRefObject<RoutePreview[]>;
  frameNsRef: MutableRefObject<number | null>;
  width: number;
  height: number;
};

/** The agent's route (walk@8+). LIVE (Batt 2026-10-08): anchored to the WORLD like a navigation
 * app -- the message nearest the displayed frame, re-projected by the agent from the character's
 * current position: the line starts at the feet, the stretch just walked over fades, the next click
 * (a box) and the goal (converging arrows) stay, all UNDER the client's UI windows; nothing when no live
 * message is close to the frame. One-shot (screen-pixel) previews are never drawn: they float
 * (lib/route.ts, Batt 2026-10-08). Display only, on its own canvas so neither overlay's redraw
 * clears the other. */
export default function RouteCanvas({ liveRef, frameNsRef, width, height }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);

  // LIVE: redraw every animation frame from the refs (no React state at 20-60 Hz)
  useEffect(() => {
    let raf = 0;
    let drawn = false;
    const tick = () => {
      raf = requestAnimationFrame(tick);
      const ctx = ref.current?.getContext("2d");
      if (!ctx) return;
      if (liveRef.current.length === 0) {
        if (drawn) ctx.clearRect(0, 0, width, height); // the route ended: clear once
        drawn = false;
        return;
      }
      ctx.clearRect(0, 0, width, height);
      drawLive(ctx, pickForFrame(liveRef.current, frameNsRef.current), width, height);
      drawn = true;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [liveRef, frameNsRef, width, height]);

  return (
    <canvas
      ref={ref}
      width={width}
      height={height}
      className="pointer-events-none absolute inset-0 h-full w-full"
    />
  );
}

// The RA2 look (Batt 2026-10-08, from Red Alert 2's move line): a thin solid line from the unit's
// feet, small square nodes at the corners, a box on the next click, and at the goal four arrows
// converging on the ground point, animated. The faint shadow keeps it visible on bright floors.
const RA2_LINE = "rgba(70, 230, 90, 0.95)";
const RA2_SHADOW = "rgba(0, 0, 0, 0.35)";
const RA2_NODE = "#fde68a";
const RA2_PULSE_MS = 700;

function drawLive(ctx: CanvasRenderingContext2D, route: RoutePreview | null, w: number, h: number) {
  if (!route || route.points.length === 0) return;
  ctx.save();
  ctx.beginPath(); // everything outside the client's UI windows
  ctx.rect(0, 0, w, h);
  for (const r of clipRects(route, w, h)) ctx.rect(r.x, r.y, r.w, r.h);
  ctx.clip("evenodd");
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const s of passedPixels(route, w, h)) {
    ctx.strokeStyle = `rgba(70, 230, 90, ${(0.6 * s.alpha).toFixed(3)})`;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(s.a.x, s.a.y);
    ctx.lineTo(s.b.x, s.b.y);
    ctx.stroke();
  }
  const pixels = routePixels(route, w, h);
  const path = pixels.filter((p) => p.kind === "feet" || p.kind === "waypoint");
  if (path.length > 1) {
    for (const [width, style] of [
      [4, RA2_SHADOW],
      [2, RA2_LINE],
    ] as const) {
      ctx.lineWidth = width;
      ctx.strokeStyle = style;
      ctx.beginPath();
      path.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
      ctx.stroke();
    }
    for (const p of path.slice(1)) node(ctx, p.x, p.y, 3, RA2_NODE); // the corners
  }
  const phase = (performance.now() % RA2_PULSE_MS) / RA2_PULSE_MS;
  for (const p of pixels) {
    if (p.kind === "goal") arrowsIn(ctx, p.x, p.y, 14 - 8 * phase);
    else if (p.kind === "click") box(ctx, p.x, p.y, 5);
  }
  ctx.restore();
}

function node(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, fill: string) {
  ctx.fillStyle = "rgba(0, 0, 0, 0.5)";
  ctx.fillRect(x - r - 1, y - r - 1, 2 * r + 2, 2 * r + 2);
  ctx.fillStyle = fill;
  ctx.fillRect(x - r, y - r, 2 * r, 2 * r);
}

function box(ctx: CanvasRenderingContext2D, x: number, y: number, r: number) {
  ctx.lineWidth = 2;
  ctx.strokeStyle = RA2_NODE;
  ctx.strokeRect(x - r, y - r, 2 * r, 2 * r);
}

/** Four arrowheads on the diagonals, pointing in at (x, y) from radius r (RA2's move marker). */
function arrowsIn(ctx: CanvasRenderingContext2D, x: number, y: number, r: number) {
  ctx.fillStyle = "rgba(70, 230, 90, 0.95)";
  ctx.strokeStyle = RA2_SHADOW;
  ctx.lineWidth = 1;
  for (const a of [Math.PI / 4, (3 * Math.PI) / 4, (5 * Math.PI) / 4, (7 * Math.PI) / 4]) {
    const tx = x + Math.cos(a) * r; // the tip, nearest the goal
    const ty = y + Math.sin(a) * r * 0.6; // flattened: the ground is seen at an angle
    const bx = x + Math.cos(a) * (r + 7);
    const by = y + Math.sin(a) * (r + 7) * 0.6;
    const nx = -Math.sin(a) * 4;
    const ny = Math.cos(a) * 4 * 0.6;
    ctx.beginPath();
    ctx.moveTo(tx, ty);
    ctx.lineTo(bx + nx, by + ny);
    ctx.lineTo(bx - nx, by - ny);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  }
}
