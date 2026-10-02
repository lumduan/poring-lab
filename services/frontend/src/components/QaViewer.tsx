"use client";

import { useEffect, useState } from "react";

import OverlayCanvas from "@/components/OverlayCanvas";
import { type QaIndex, type QaSession, toDetections } from "@/lib/qa";

/** Step through a recorded session's frames with the auto-labels drawn by the console's own overlay
 * canvas (the one vision's detections use), for Batt's visual check of Phase 2 labels. */
export default function QaViewer() {
  const [index, setIndex] = useState<QaIndex | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [session, setSession] = useState<QaSession | null>(null);
  const [i, setI] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/qa/index.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`index: ${r.status}`))))
      .then((data: QaIndex) => {
        setIndex(data);
        if (data.sessions.length) setSessionId(data.sessions[data.sessions.length - 1].id);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    fetch(`/api/qa/${sessionId}/labels.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`labels: ${r.status}`))))
      .then((data: QaSession) => {
        setSession(data);
        setI(0);
      })
      .catch((e: Error) => setError(e.message));
  }, [sessionId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!session) return;
      if (e.key === "ArrowRight") setI((v) => Math.min(session.frames.length - 1, v + 1));
      if (e.key === "ArrowLeft") setI((v) => Math.max(0, v - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [session]);

  if (error) return <p className="p-4 text-sm text-amber-300">QA bundle unavailable: {error}</p>;
  if (!index || !session) return <p className="p-4 text-sm text-neutral-400">Loading…</p>;
  const frame = session.frames[i];
  const [w, h] = session.size;
  return (
    <main className="flex flex-col gap-3 p-4 text-sm text-neutral-200">
      <div className="flex flex-wrap items-center gap-3">
        <select
          className="rounded bg-neutral-800 px-2 py-1"
          value={sessionId ?? ""}
          onChange={(e) => setSessionId(e.target.value)}
        >
          {index.sessions.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title} ({s.frames} frames)
            </option>
          ))}
        </select>
        <button className="rounded bg-neutral-800 px-2 py-1" onClick={() => setI(Math.max(0, i - 1))}>
          ◀
        </button>
        <span>
          frame {i + 1}/{session.frames.length} · id {frame.frame_id} · {frame.boxes.length} boxes ·
          offset {session.offset_ms} ms
        </span>
        <button
          className="rounded bg-neutral-800 px-2 py-1"
          onClick={() => setI(Math.min(session.frames.length - 1, i + 1))}
        >
          ▶
        </button>
      </div>
      <div className="relative w-full max-w-[1200px]" style={{ aspectRatio: `${w} / ${h}` }}>
        {/* eslint-disable-next-line @next/next/no-img-element -- a raw lab frame, not a page asset */}
        <img src={`/api/qa/${session.session}/${frame.file}`} alt="" className="absolute inset-0 h-full w-full" />
        <OverlayCanvas detections={toDetections(frame, session.size)} width={w} height={h} staleMs={null} />
      </div>
    </main>
  );
}
