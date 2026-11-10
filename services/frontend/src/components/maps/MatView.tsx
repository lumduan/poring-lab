"use client";

// The Maps page's MAP VIEW, matpilot's mat for a game map (docs/planning/world-map-flows.md section
// 4): the map's walk grid from the backend and, at the playback's time, the character walking its
// routes, the monster it meets, the NPC it talks to (the drawing is lib/maps/draw.ts, tested in
// node). One canvas, nothing loaded from outside; the grid is drawn once per map and scale. Zoomed
// in, the box scrolls and follows the character.
import { useEffect, useMemo, useRef, useState } from "react";

import type { WorldMap } from "@/lib/flow/api";
import { COLOUR_VARS, type Colours, drawGrid, drawScene, FALLBACK_COLOURS, mapSize } from "@/lib/maps/draw";
import { type Labels, poseAt, type Timeline } from "@/lib/maps/play";

function readColours(el: HTMLElement | null): Colours {
  if (!el) return FALLBACK_COLOURS;
  const cs = getComputedStyle(el);
  const out = { ...FALLBACK_COLOURS };
  for (const k of Object.keys(COLOUR_VARS) as (keyof Colours)[]) {
    const v = cs.getPropertyValue(COLOUR_VARS[k]).trim();
    if (v) out[k] = v;
  }
  return out;
}

export type MatViewProps = {
  map: string | null;
  rows: string[] | null;
  sheet: WorldMap | null;
  tl: Timeline | null;
  time: number;
  labels: Labels | null;
  savePoint: { map: string; cell: [number, number] } | null;
  zoom: number; // 1 = fit the box; 2, 4: closer (the box scrolls, following the character)
};

export default function MatView({ map, rows, sheet, tl, time, labels, savePoint, zoom }: MatViewProps) {
  const box = useRef<HTMLDivElement | null>(null);
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const [boxSize, setBoxSize] = useState<{ w: number; h: number }>({ w: 600, h: 360 });
  const [colours, setColours] = useState<Colours>(FALLBACK_COLOURS);
  const { w, h, known } = useMemo(() => mapSize(map, rows, sheet, tl), [map, rows, sheet, tl]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setBoxSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    setBoxSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);
  useEffect(() => {
    const read = () => setColours(readColours(box.current));
    read();
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    mq?.addEventListener("change", read);
    return () => mq?.removeEventListener("change", read);
  }, []);

  const fit = Math.max(1, Math.min(16, Math.floor(Math.min((boxSize.w - 8) / w, (boxSize.h - 8) / h)) || 1));
  const scale = fit * zoom;
  const dpr = typeof window !== "undefined" ? Math.min(2, window.devicePixelRatio || 1) : 1;

  // the grid, drawn once per map and scale
  const base = useMemo(() => {
    if (typeof document === "undefined") return null;
    const c = document.createElement("canvas");
    c.width = w * scale;
    c.height = h * scale;
    const ctx = c.getContext("2d");
    if (!ctx) return null;
    drawGrid(ctx, rows, w, h, scale, colours);
    return c;
  }, [rows, w, h, scale, colours]);

  useEffect(() => {
    const ctx = canvas.current?.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w * scale, h * scale);
    ctx.imageSmoothingEnabled = false; // the grid stays crisp on a high-density screen
    if (base) ctx.drawImage(base, 0, 0);
    drawScene(ctx, { map, w, h, scale, sheet, tl, time, labels, savePoint, colours });
  }, [base, w, h, scale, dpr, tl, time, map, sheet, labels, savePoint, colours]);

  // follow the character when zoomed in
  const pose = tl ? poseAt(tl, time) : null;
  useEffect(() => {
    const el = box.current;
    if (!el || zoom <= 1 || !pose?.known || pose.map !== map) return;
    const px = pose.x * scale;
    const py = (h - 1 - pose.y) * scale;
    const margin = Math.min(el.clientWidth, el.clientHeight) / 4;
    if (px < el.scrollLeft + margin || px > el.scrollLeft + el.clientWidth - margin || py < el.scrollTop + margin || py > el.scrollTop + el.clientHeight - margin) {
      el.scrollTo({ left: px - el.clientWidth / 2, top: py - el.clientHeight / 2 });
    }
  }, [pose, scale, h, zoom, map]);

  const here = pose?.known && pose.map === map ? `; the character at (${Math.round(pose.x)}, ${Math.round(pose.y)})` : "";
  return (
    <div className="mat-box" ref={box} data-testid="mat-view">
      <canvas
        ref={canvas}
        width={w * scale * dpr}
        height={h * scale * dpr}
        style={{ width: w * scale, height: h * scale }}
        className="mat-canvas"
        role="img"
        aria-label={`${map ?? "no map"}: ${w} × ${h} cells${rows ? "" : " (no walk grid: an estimate)"}${here}`}
      />
      {!known && <p className="mat-note">No walk grid for {map ?? "this map"} in the static data: the area is only as large as the run, and walks are estimates.</p>}
    </div>
  );
}
