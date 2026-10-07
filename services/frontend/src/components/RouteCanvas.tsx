"use client";

import { useEffect, useRef } from "react";

import type { RoutePreview } from "@/lib/protocol";
import { routePath, routePixels, routeTtlMs } from "@/lib/route";

type Props = { route: RoutePreview | null; width: number; height: number };

/** The agent's PLANNED route (walk@8): the waypoint polyline it will follow (amber, dashed), its
 * waypoints, the goal (a ring) and the point it will click next (a crosshair). Display only, on its
 * own canvas so neither overlay's fade clears the other. */
export default function RouteCanvas({ route, width, height }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);
    const ttl = routeTtlMs(route);
    if (ttl === 0) return;
    const pixels = routePixels(route, width, height);
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
    const timer = setTimeout(() => ctx.clearRect(0, 0, width, height), ttl);
    return () => clearTimeout(timer);
  }, [route, width, height]);

  return (
    <canvas
      ref={ref}
      width={width}
      height={height}
      className="pointer-events-none absolute inset-0 h-full w-full"
    />
  );
}
