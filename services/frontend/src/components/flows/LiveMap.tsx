"use client";

// The live map (Batt 2026-11-21: "while a Run plays, the Map tab shows a map like the minimap:
// where the bot is as a green dot, the monsters it sees as red dots, the map as on /maps"). The
// map she is on comes from the Run helper's summary; its walk grid from the static data (the same
// request as /maps). One canvas, nothing loaded from outside; drawn by lib/flow/livemap.ts.
import { useEffect, useMemo, useRef, useState } from "react";

import type { FlowsApi, WorldSource } from "@/lib/flow/api";
import { drawLive, MAP_VIEWS, type MapView, SIGHT_STALE_S, sightLine, sightOf, viewWindow } from "@/lib/flow/livemap";
import type { LiveSummary } from "@/lib/flow/liverun";
import { browserStorage, KEYS, readChoice, writeChoice } from "@/lib/flow/prefs";
import { FALLBACK_COLOURS, fitScale } from "@/lib/maps/draw";

type Grid = { rows: string[] | null; size: [number, number] | null; failed?: boolean };

export default function LiveMap({ api, world, server, summary, running }: { api: FlowsApi | null; world: WorldSource; server: string; summary: LiveSummary | null | undefined; running: boolean }) {
  const sight = useMemo(() => sightOf(summary), [summary]);
  const store = useMemo(() => browserStorage(), []);
  const [view, setViewState] = useState<MapView>(() => readChoice(store, KEYS.liveMap, MAP_VIEWS, "whole"));
  const [grids, setGrids] = useState<Record<string, Grid>>({});
  const [box, setBox] = useState<{ w: number; h: number }>({ w: 0, h: 0 });
  const boxRef = useRef<HTMLDivElement | null>(null);
  const ref = useRef<HTMLCanvasElement | null>(null);
  const map = sight.map;
  const grid = map ? grids[map] : undefined;

  // the walk grid of the map she is on, once a map (a failed request is not repeated)
  useEffect(() => {
    if (!api || !map || grids[map]) return;
    let alive = true;
    api
      .world(world, server, [map], true)
      .then((w) => alive && setGrids((g) => ({ ...g, [map]: { rows: w.walk?.[map] ?? null, size: w.maps[map]?.size ?? null } })))
      .catch(() => alive && setGrids((g) => ({ ...g, [map]: { rows: null, size: null, failed: true } })));
    return () => {
      alive = false;
    };
  }, [api, map, grids, world, server]);

  useEffect(() => {
    const el = boxRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => setBox({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    setBox({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  const mapW = grid?.rows?.[0]?.length ?? grid?.size?.[0] ?? 0;
  const mapH = grid?.rows?.length ?? grid?.size?.[1] ?? 0;
  const win = mapW && mapH ? viewWindow(view, sight.pos, mapW, mapH) : null;
  const scale = win ? fitScale(box.w, box.h, win.w, win.h) : 1;

  useEffect(() => {
    const c = ref.current;
    if (!c || !win) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const dpr = typeof window !== "undefined" ? Math.min(2, window.devicePixelRatio || 1) : 1;
    c.width = Math.round(win.w * scale * dpr);
    c.height = Math.round(win.h * scale * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    drawLive(ctx, { rows: grid?.rows ?? null, win, scale, sight, colours: FALLBACK_COLOURS });
  }, [win?.x0, win?.y0, win?.w, win?.h, scale, grid, sight]); // eslint-disable-line react-hooks/exhaustive-deps

  const setView = (v: MapView) => {
    setViewState(v);
    writeChoice(store, KEYS.liveMap, v);
  };

  return (
    <div className="live-map" data-testid="live-map">
      <div className="live-map-head">
        <span className="strong">Live map</span>
        <span className="muted" data-testid="live-map-line">
          {sightLine(sight, running)}
        </span>
        <span className="live-map-views" role="group" aria-label="The map's view">
          {MAP_VIEWS.map((v) => (
            <button key={v} type="button" className="toggle-button" aria-pressed={view === v} onClick={() => setView(v)} data-testid={`live-map-${v}`}>
              {v === "whole" ? "Whole map" : "Close-up"}
            </button>
          ))}
        </span>
      </div>
      <div className="live-map-box" ref={boxRef}>
        {win ? (
          <canvas ref={ref} style={{ width: win.w * scale, height: win.h * scale }} aria-label={`The map ${map}: her cell and the monsters she sees`} />
        ) : (
          <p className="muted live-map-empty">
            {!map
              ? running
                ? "Waiting for her first reading of the screen."
                : "No Run is playing: start one (Run, at the top) to see her here."
              : grid?.failed || (grid && !mapW)
                ? `No walk grid for ${map} in the static data: nothing to draw her on.`
                : `Loading ${map}…`}
          </p>
        )}
      </div>
      <p className="muted live-map-legend">
        <span className="live-dot" style={{ background: "#22c55e" }} /> her cell (the minimap, once a second) and her last cells ·{" "}
        <span className="live-dot" style={{ background: FALLBACK_COLOURS.monster }} /> the monsters of the detector&apos;s last read, placed from her cell
        (may be a cell off; faded after {SIGHT_STALE_S} s without a read). Drag the box&apos;s corner to make it taller.
      </p>
    </div>
  );
}
