"use client";

// A map's walk grid with the cells a simulate run walked (static data + the trace; drawn on a
// canvas, nothing loaded from outside).
import { useEffect, useRef } from "react";

import type { PathSegment, WorldMap } from "@/lib/flow/api";

const SEG_COLOURS = ["#38bdf8", "#f472b6", "#a3e635", "#fbbf24", "#c084fc", "#fb7185", "#2dd4bf"];

export default function PathMap({
  name,
  rows,
  sheet,
  paths,
  marks,
}: {
  name: string;
  rows: string[] | null;
  sheet: WorldMap | null;
  paths: PathSegment[];
  marks: { x: number; y: number; label: string; colour: string }[];
}) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const w = rows?.[0]?.length ?? sheet?.size?.[0] ?? 0;
  const h = rows?.length ?? sheet?.size?.[1] ?? 0;
  const scale = w && h ? Math.max(1, Math.min(4, Math.floor(360 / Math.max(w, h)))) : 2;

  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    // RO cells grow northwards: y = 0 is the bottom row of the map.
    const px = (x: number) => x * scale;
    const py = (y: number) => (h - 1 - y) * scale;
    ctx.fillStyle = "#050506";
    ctx.fillRect(0, 0, c.width, c.height);
    if (rows) {
      ctx.fillStyle = "#3f3f47";
      for (let y = 0; y < rows.length; y++) {
        const row = rows[y];
        for (let x = 0; x < row.length; x++) if (row[x] === ".") ctx.fillRect(px(x), py(y), scale, scale);
      }
    }
    paths.forEach((p, i) => {
      ctx.strokeStyle = SEG_COLOURS[i % SEG_COLOURS.length];
      ctx.lineWidth = Math.max(1.5, scale * 0.8);
      ctx.setLineDash(p.estimated ? [4, 3] : []);
      ctx.beginPath();
      p.cells.forEach(([x, y], j) => {
        const X = px(x) + scale / 2;
        const Y = py(y) + scale / 2;
        if (j === 0) ctx.moveTo(X, Y);
        else ctx.lineTo(X, Y);
      });
      ctx.stroke();
    });
    ctx.setLineDash([]);
    for (const m of marks) {
      ctx.fillStyle = m.colour;
      ctx.beginPath();
      ctx.arc(px(m.x) + scale / 2, py(m.y) + scale / 2, Math.max(3, scale * 1.5), 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "#e5e5e5";
      ctx.font = "10px sans-serif";
      ctx.fillText(m.label, px(m.x) + scale + 4, py(m.y) + 3);
    }
  }, [rows, paths, marks, scale, h]);

  if (!w || !h) {
    return <div className="text-xs text-neutral-500">{name}: no walk grid in the static data (routes are estimates)</div>;
  }
  return (
    <figure className="space-y-1">
      <figcaption className="text-xs text-neutral-300">
        {name} · {w}×{h} cells{rows ? "" : " (no walk grid: routes are estimates)"}
      </figcaption>
      <canvas ref={ref} width={w * scale} height={h * scale} className="rounded border border-neutral-800" />
    </figure>
  );
}
