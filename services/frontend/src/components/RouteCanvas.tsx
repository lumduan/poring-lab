"use client";

import { type MutableRefObject, useEffect, useRef } from "react";

import type { RoutePreview } from "@/lib/protocol";
import {
  clipRects,
  passedPixels,
  pickForFrame,
  routePath,
  routePixels,
  routeTtlMs,
} from "@/lib/route";

type Props = {
  route: RoutePreview | null;
  /** LIVE previews (newest last) and the capture time of the frame on screen (host clock). */
  liveRef?: MutableRefObject<RoutePreview[]>;
  frameNsRef?: MutableRefObject<number | null>;
  width: number;
  height: number;
};

/** The agent's route (walk@8+). LIVE (Batt 2026-10-08): anchored to the WORLD like a navigation
 * app -- the message nearest the displayed frame, re-projected by the agent from the character's
 * current position: the line starts at the feet, the stretch just walked over fades, the next click
 * (a crosshair) and the goal (a ring) stay, all UNDER the client's UI windows; nothing when no live
 * message is close to the frame. A one-shot (older) preview keeps its own fade. Display only, on
 * its own canvas so neither overlay's redraw clears the other. */
export default function RouteCanvas({ route, liveRef, frameNsRef, width, height }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);

  // LIVE: redraw every animation frame from the refs (no React state at 20-60 Hz)
  useEffect(() => {
    if (!liveRef || !frameNsRef) return;
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

  // ONE-SHOT (walk@8-11's plan-time preview): drawn once, cleared after its ttl
  useEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (!ctx || (liveRef && liveRef.current.length > 0)) return;
    ctx.clearRect(0, 0, width, height);
    const ttl = routeTtlMs(route);
    if (ttl === 0 || route?.live) return;
    drawPlan(ctx, route, width, height);
    const timer = setTimeout(() => ctx.clearRect(0, 0, width, height), ttl);
    return () => clearTimeout(timer);
  }, [route, liveRef, width, height]);

  return (
    <canvas
      ref={ref}
      width={width}
      height={height}
      className="pointer-events-none absolute inset-0 h-full w-full"
    />
  );
}

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
    ctx.strokeStyle = `rgba(245, 158, 11, ${(0.6 * s.alpha).toFixed(3)})`;
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(s.a.x, s.a.y);
    ctx.lineTo(s.b.x, s.b.y);
    ctx.stroke();
  }
  const pixels = routePixels(route, w, h);
  const path = pixels.filter((p) => p.kind === "feet" || p.kind === "waypoint");
  if (path.length > 1) {
    for (const [width, style] of [
      [7, "rgba(0, 0, 0, 0.55)"],
      [4, "rgba(245, 158, 11, 0.95)"],
    ] as const) {
      ctx.lineWidth = width;
      ctx.strokeStyle = style;
      ctx.beginPath();
      path.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
      ctx.stroke();
    }
  }
  for (const p of pixels) {
    ctx.beginPath();
    if (p.kind === "goal") {
      ctx.lineWidth = 3;
      ctx.strokeStyle = "#f59e0b";
      ctx.arc(p.x, p.y, 10, 0, 2 * Math.PI);
      ctx.stroke();
    } else if (p.kind === "click") {
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#fde68a";
      ctx.moveTo(p.x - 8, p.y);
      ctx.lineTo(p.x + 8, p.y);
      ctx.moveTo(p.x, p.y - 8);
      ctx.lineTo(p.x, p.y + 8);
      ctx.stroke();
    } else if (p.kind === "feet") {
      ctx.fillStyle = "#fbbf24";
      ctx.arc(p.x, p.y, 4, 0, 2 * Math.PI);
      ctx.fill();
    }
  }
  ctx.restore();
}

function drawPlan(ctx: CanvasRenderingContext2D, route: RoutePreview | null, w: number, h: number) {
  const pixels = routePixels(route, w, h);
  const path = routePath(pixels);
  ctx.lineWidth = 3;
  ctx.strokeStyle = "rgba(245, 158, 11, 0.9)";
  ctx.setLineDash([8, 6]);
  ctx.beginPath();
  path.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
  ctx.stroke();
  ctx.setLineDash([]);
  for (const p of pixels) {
    ctx.beginPath();
    if (p.kind === "goal") {
      ctx.strokeStyle = "#f59e0b";
      ctx.arc(p.x, p.y, 9, 0, 2 * Math.PI);
      ctx.stroke();
    } else if (p.kind === "click") {
      ctx.strokeStyle = "#fde68a";
      ctx.moveTo(p.x - 8, p.y);
      ctx.lineTo(p.x + 8, p.y);
      ctx.moveTo(p.x, p.y - 8);
      ctx.lineTo(p.x, p.y + 8);
      ctx.stroke();
    } else {
      ctx.fillStyle = p.kind === "start" ? "#fbbf24" : "#f59e0b";
      ctx.arc(p.x, p.y, 4, 0, 2 * Math.PI);
      ctx.fill();
    }
  }
  if (route?.label && path.length > 0) {
    ctx.font = "12px ui-monospace, monospace";
    ctx.fillStyle = "rgba(0, 0, 0, 0.65)";
    ctx.fillRect(path[0].x + 8, path[0].y - 22, ctx.measureText(route.label).width + 6, 15);
    ctx.fillStyle = "#fef3c7";
    ctx.fillText(route.label, path[0].x + 11, path[0].y - 10);
  }
}
