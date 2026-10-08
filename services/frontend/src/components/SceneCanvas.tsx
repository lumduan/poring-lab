"use client";

import { type MutableRefObject, useEffect, useRef } from "react";

import type { SceneStore } from "@/lib/scene";

type Props = {
  store: MutableRefObject<SceneStore>;
  frameNsRef: MutableRefObject<number | null>;
  frameIdRef: { readonly current: number | null };
  width: number;
  height: number;
};

const COLOUR: Record<string, string> = { monster: "#f87171", npc: "#fbbf24", player: "#60a5fa", sign: "#fb923c" };

/** The HUD SCENE (Batt 2026-10-08): the retained overlay, redrawn on every animation frame for the
 * frame on screen. World objects (units, signboards) are shifted by that frame's global motion;
 * screen objects (the UI windows, the work zone) never move. Display only. */
export default function SceneCanvas({ store, frameNsRef, frameIdRef, width, height }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let raf = 0;
    const tick = () => {
      raf = requestAnimationFrame(tick);
      const ctx = ref.current?.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, width, height);
      for (const b of store.current.boxes(frameIdRef.current, frameNsRef.current, width, height)) {
        if (b.kind === "zone" || b.kind === "window") {
          ctx.strokeStyle = "rgba(90, 200, 255, 0.55)";
          ctx.lineWidth = 1;
          ctx.setLineDash(b.kind === "zone" ? [6, 4] : []);
          ctx.strokeRect(b.x, b.y, b.w, b.h);
          ctx.setLineDash([]);
          continue;
        }
        const col = COLOUR[b.cls] ?? "#e5e5e5";
        ctx.strokeStyle = col;
        ctx.lineWidth = 2;
        ctx.strokeRect(b.x, b.y, b.w, b.h);
        if (b.label) {
          ctx.font = "11px ui-monospace, monospace";
          ctx.fillStyle = "rgba(0, 0, 0, 0.7)";
          ctx.fillRect(b.x, b.y - 14, ctx.measureText(b.label).width + 6, 13);
          ctx.fillStyle = col;
          ctx.fillText(b.label, b.x + 3, b.y - 4);
        }
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [store, frameNsRef, frameIdRef, width, height]);

  return (
    <canvas
      ref={ref}
      width={width}
      height={height}
      className="pointer-events-none absolute inset-0 h-full w-full"
    />
  );
}
