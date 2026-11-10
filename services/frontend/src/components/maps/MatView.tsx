"use client";

// The Maps page's MAP VIEW, matpilot's mat for a game map (docs/planning/world-map-flows.md section
// 4): the map's walk grid from the backend and, at the playback's time, the character walking its
// routes, the monster it meets, the NPC it talks to (the drawing is lib/maps/draw.ts, tested in
// node). One canvas, nothing loaded from outside; the grid is drawn once per map and scale. Zoomed
// in, the box scrolls and follows the character.
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import type { WorldMap } from "@/lib/flow/api";
import { COLOUR_VARS, type Colours, drawGrid, drawScene, FALLBACK_COLOURS, fitScale, mapSize } from "@/lib/maps/draw";
import { type Labels, poseAt, type Timeline } from "@/lib/maps/play";
import { makeWanderers, type Spawn } from "@/lib/maps/wander";

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
  children?: ReactNode; // over the map itself (the login overlay), not over the empty stage
  decorSeed?: number | null; // round 5: the map's other monsters (decoration) from this seed; null: off
};

const NO_SPAWNS: Spawn[] = [];

export default function MatView({ map, rows, sheet, tl, time, labels, savePoint, zoom, children, decorSeed = null }: MatViewProps) {
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

  // round 2: "fit" is the LARGEST scale that shows the whole map in the stage, keeping its aspect
  // (matpilot's MatView fills the stage; not a whole number of pixels a cell any more); 2x and 4x
  // zoom from there
  const dpr = typeof window !== "undefined" ? Math.min(3, window.devicePixelRatio || 1) : 1;
  const scale = fitScale(boxSize.w, boxSize.h, w, h) * zoom;

  // the map's other monsters: their walks made once per map, spawns and seed (never per frame)
  const spawns = sheet?.spawns ?? NO_SPAWNS;
  const decor = useMemo(() => (decorSeed === null || !map ? null : makeWanderers(rows, spawns, decorSeed, map)), [decorSeed, rows, spawns, map]);

  // the grid, drawn once per map and size: at whole DEVICE pixels a cell (sharp), then scaled onto
  // the canvas with smoothing off
  const cellPx = Math.max(1, Math.min(16, Math.round(scale * dpr), Math.floor(8192 / Math.max(w, h))));
  const base = useMemo(() => {
    if (typeof document === "undefined") return null;
    const c = document.createElement("canvas");
    c.width = w * cellPx;
    c.height = h * cellPx;
    const ctx = c.getContext("2d");
    if (!ctx) return null;
    drawGrid(ctx, rows, w, h, cellPx, colours);
    return c;
  }, [rows, w, h, cellPx, colours]);

  useEffect(() => {
    const ctx = canvas.current?.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w * scale, h * scale);
    ctx.imageSmoothingEnabled = false; // the grid stays crisp on a high-density screen
    if (base) ctx.drawImage(base, 0, 0, w * scale, h * scale);
    drawScene(ctx, { map, w, h, scale, sheet, tl, time, labels, savePoint, colours, decor });
  }, [base, w, h, scale, dpr, tl, time, map, sheet, labels, savePoint, colours, decor]);

  // follow the character when zoomed in
  const pose = tl ? poseAt(tl, time) : null;
  const poseRef = useRef(pose);
  useEffect(() => {
    poseRef.current = pose;
  });
  // round 3: a zoom (or a new map) opens CENTRED: on the character during a run, else on the
  // middle of the map (it opened at the top-left corner)
  useEffect(() => {
    const el = box.current;
    if (!el || zoom <= 1) return;
    const p = poseRef.current;
    const on = Boolean(p?.known && p.map === map);
    const cx = ((on && p ? p.x : (w - 1) / 2) + 0.5) * scale + 2;
    const cy = (h - 1 - (on && p ? p.y : (h - 1) / 2) + 0.5) * scale + 2;
    el.scrollTo({ left: cx - el.clientWidth / 2, top: cy - el.clientHeight / 2 });
  }, [zoom, map, scale, w, h]);
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
      <div className="mat-frame" style={{ width: w * scale, height: h * scale }}>
        <canvas
          ref={canvas}
          width={Math.round(w * scale * dpr)}
          height={Math.round(h * scale * dpr)}
          style={{ width: w * scale, height: h * scale }}
          className="mat-canvas"
          role="img"
          aria-label={`${map ?? "no map"}: ${w} × ${h} cells${rows ? "" : " (no walk grid: an estimate)"}${here}`}
        />
        {children}
      </div>
      {!known && <p className="mat-note">No walk grid for {map ?? "this map"} in the static data: the area is only as large as the run, and walks are estimates.</p>}
    </div>
  );
}
