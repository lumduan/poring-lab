"use client";

// A map's walk grid with the cells a simulate run walked (static data + the trace; drawn on a
// canvas, nothing loaded from outside). B2 adds the ZONES layer (blocks-from-hunt-flow.md section
// 3): the cells each zone item closes and the search-area preview EXACTLY as the backend's run of
// the loader returned them (the browser computes no cell), the items' points, the line or area
// being drawn, and clicks on cells (x east, y NORTH: y = 0 is the bottom row).
import { useEffect, useRef, useState } from "react";

import type { PathSegment, WorldMap } from "@/lib/flow/api";
import { type Cell, cellOfPixel, type Draft, type ZoneKind } from "@/lib/flow/zones";

const SEG_COLOURS = ["#38bdf8", "#f472b6", "#a3e635", "#fbbf24", "#c084fc", "#fb7185", "#2dd4bf"];
// the search-area preview's classes (flows_zones.area_of): '.' the largest piece, 'z' closed by the
// zones, 'c' sealed off, 'o' walkable elsewhere
const AREA_COLOURS: Record<string, string> = { ".": "#1f4d3a", z: "#7f1d1d", c: "#4c1d95", o: "#3f3f47" };
const ITEM_COLOURS: Record<ZoneKind, string> = { no_cross: "#ef4444", no_enter: "#f97316" };

export type ZonesLayer = {
  area: string[] | null; // the check's rows (rows[y][x]); null: not checked for this text
  closed: { kind: ZoneKind; cells: Cell[] }[]; // the check's cells per item
  items: { kind: ZoneKind; points: Cell[]; selected: boolean }[]; // the model's points
  draft: Draft | null;
};

export default function PathMap({
  name,
  rows,
  sheet,
  paths,
  marks,
  zones,
  zoom,
  onCell,
}: {
  name: string;
  rows: string[] | null;
  sheet: WorldMap | null;
  paths: PathSegment[];
  marks: { x: number; y: number; label: string; colour: string }[];
  zones?: ZonesLayer;
  zoom?: number;
  onCell?: (c: Cell, double: boolean) => void;
}) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const [hover, setHover] = useState<Cell | null>(null);
  const w = rows?.[0]?.length ?? sheet?.size?.[0] ?? 0;
  const h = rows?.length ?? sheet?.size?.[1] ?? 0;
  const auto = w && h ? Math.max(1, Math.min(4, Math.floor(360 / Math.max(w, h)))) : 2;
  const scale = zoom ?? auto;

  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    // RO cells grow northwards: y = 0 is the bottom row of the map.
    const px = (x: number) => x * scale;
    const py = (y: number) => (h - 1 - y) * scale;
    const centre = ([x, y]: Cell): [number, number] => [px(x) + scale / 2, py(y) + scale / 2];
    ctx.fillStyle = "#050506";
    ctx.fillRect(0, 0, c.width, c.height);
    if (rows) {
      ctx.fillStyle = "#3f3f47";
      for (let y = 0; y < rows.length; y++) {
        const row = rows[y];
        for (let x = 0; x < row.length; x++) if (row[x] === ".") ctx.fillRect(px(x), py(y), scale, scale);
      }
    }
    if (zones?.area) {
      for (let y = 0; y < zones.area.length; y++) {
        const row = zones.area[y];
        for (let x = 0; x < row.length; x++) {
          const col = AREA_COLOURS[row[x]];
          if (!col) continue;
          ctx.fillStyle = col;
          ctx.fillRect(px(x), py(y), scale, scale);
        }
      }
    }
    for (const it of zones?.closed ?? []) {
      ctx.fillStyle = ITEM_COLOURS[it.kind];
      ctx.globalAlpha = 0.85;
      for (const [x, y] of it.cells) ctx.fillRect(px(x), py(y), scale, scale);
      ctx.globalAlpha = 1;
    }
    const outline = (points: Cell[], closed: boolean, colour: string, dashed: boolean, width: number) => {
      if (!points.length) return;
      ctx.strokeStyle = colour;
      ctx.lineWidth = width;
      ctx.setLineDash(dashed ? [4, 3] : []);
      ctx.beginPath();
      points.forEach((p, j) => {
        const [X, Y] = centre(p);
        if (j === 0) ctx.moveTo(X, Y);
        else ctx.lineTo(X, Y);
      });
      if (closed) ctx.closePath();
      ctx.stroke();
      ctx.fillStyle = colour;
      for (const p of points) {
        const [X, Y] = centre(p);
        ctx.fillRect(X - 1.5, Y - 1.5, 3, 3);
      }
      ctx.setLineDash([]);
    };
    for (const it of zones?.items ?? []) {
      outline(it.points, it.kind === "no_enter", it.selected ? "#fde047" : "#e5e5e5", false, it.selected ? 2.5 : 1.5);
    }
    if (zones?.draft) outline(zones.draft.points, false, "#22d3ee", true, 2);
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
  }, [rows, paths, marks, scale, h, zones]);

  if (!w || !h) {
    return <div className="text-xs text-neutral-500">{name}: no walk grid in the static data (routes are estimates)</div>;
  }
  const cellAt = (e: React.MouseEvent<HTMLCanvasElement>): Cell | null => {
    // the canvas's CONTENT box: past its border (clientLeft / clientTop), and in canvas pixels
    // should CSS ever scale it (a border-blind version mapped half of each cell to its neighbour)
    const el = e.currentTarget;
    const r = el.getBoundingClientRect();
    const sx = el.clientWidth ? el.width / el.clientWidth : 1;
    const sy = el.clientHeight ? el.height / el.clientHeight : 1;
    return cellOfPixel((e.clientX - r.left - el.clientLeft) * sx, (e.clientY - r.top - el.clientTop) * sy, scale, w, h);
  };
  return (
    <figure className="space-y-1">
      <figcaption className="text-xs">
        {name} · {w}×{h} cells{rows ? "" : " (no walk grid: routes are estimates)"}
        {onCell && <span className="ml-2 text-neutral-400">cell {hover ? `(${hover[0]}, ${hover[1]})` : "-"} · x east, y north</span>}
      </figcaption>
      <canvas
        ref={ref}
        width={w * scale}
        height={h * scale}
        className={`rounded border border-neutral-800 ${onCell ? "cursor-crosshair" : ""}`}
        data-testid={onCell ? "zones-canvas" : undefined}
        onMouseMove={onCell ? (e) => setHover(cellAt(e)) : undefined}
        onMouseLeave={onCell ? () => setHover(null) : undefined}
        onClick={onCell ? (e) => { const c = cellAt(e); if (c) onCell(c, false); } : undefined}
        onDoubleClick={onCell ? (e) => { const c = cellAt(e); if (c) onCell(c, true); } : undefined}
      />
    </figure>
  );
}
