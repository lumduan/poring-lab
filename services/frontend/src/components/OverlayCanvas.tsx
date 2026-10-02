"use client";

import { useEffect, useRef } from "react";

import type { Detections } from "@/lib/protocol";

type Props = {
  detections: Detections | null;
  width: number;
  height: number;
  /** Wipe boxes this long after they arrive; null keeps them (the /qa label review). */
  staleMs?: number | null;
};

// Boxes older than this are wiped: the agent stopped publishing, or disconnected.
const STALE_MS = 1000;

/** Detection boxes from the vision agent, drawn on a separate canvas above the video. They come
 * from the agent's own grab (``frame_id`` in its numbering), usually within a frame or two of the
 * frame on screen. */
export default function OverlayCanvas({ detections, width, height, staleMs = STALE_MS }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);
    if (!detections) return;

    ctx.lineWidth = 2;
    ctx.font = "12px ui-monospace, monospace";
    ctx.textBaseline = "bottom";
    for (const box of detections.boxes) {
      const x = box.x1 * width;
      const y = box.y1 * height;
      ctx.strokeStyle = "#38bdf8";
      ctx.strokeRect(x, y, (box.x2 - box.x1) * width, (box.y2 - box.y1) * height);
      const label = `${box.cls} ${Math.round(box.conf * 100)}%`;
      ctx.fillStyle = "rgba(0, 0, 0, 0.65)";
      ctx.fillRect(x, y - 15, ctx.measureText(label).width + 6, 15);
      ctx.fillStyle = "#e0f2fe";
      ctx.fillText(label, x + 3, y - 1);
    }
    if (staleMs === null) return;
    const timer = setTimeout(() => ctx.clearRect(0, 0, width, height), staleMs);
    return () => clearTimeout(timer);
  }, [detections, width, height, staleMs]);

  return (
    <canvas
      ref={ref}
      width={width}
      height={height}
      className="pointer-events-none absolute inset-0 h-full w-full"
    />
  );
}
