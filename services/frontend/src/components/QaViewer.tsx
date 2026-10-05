"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import OverlayCanvas from "@/components/OverlayCanvas";
import QaEditor from "@/components/QaEditor";
import { handcheckProgress, initialSession, type QaIndex, type QaSession, toDetections } from "@/lib/qa";
import {
  classForKey,
  type Cls,
  type EditBox,
  type FrameEdit,
  frameEdit,
  fromAuto,
  fromHandCheck,
  type HandCheckDoc,
  toHandCheck,
} from "@/lib/qa_edit";
import { backendHttpBase } from "@/lib/ws";

type Props = { backendUrl: string | null };

/** Step through a recorded session's frames with the auto-labels drawn by the console's own overlay
 * canvas (the one vision's detections use), for Batt's visual check of Phase 2 labels.
 *
 * Hand-check mode (B6, Post-S2 round Part D): fix the boxes and save them to the backend
 * (/qa/handcheck/<session>, LAN + allowlisted Origin only). Keys: ←/→ frames (saves first), A accept
 * the frame as shown, Del delete the selected box, 1/2/3 class (player/monster/npc: new boxes, and
 * the selected one), Esc deselect, Ctrl/⌘+S save. Drag a box to move it, a corner to resize, empty
 * space to add. scripts/label_iou.py scores the auto-labels against the saved set. */
export default function QaViewer({ backendUrl }: Props) {
  const [index, setIndex] = useState<QaIndex | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [session, setSession] = useState<QaSession | null>(null);
  const [i, setI] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(true);
  const [edits, setEdits] = useState<Record<number, FrameEdit>>({});
  const [selected, setSelected] = useState<number | null>(null);
  const [newClass, setNewClass] = useState<Cls>("monster");
  const [dirty, setDirty] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string>("");
  // Frames the backend HOLDS for this session (not merely looked at): shown in large type.
  const [savedCount, setSavedCount] = useState(0);

  useEffect(() => {
    fetch("/api/qa/index.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`index: ${r.status}`))))
      .then((data: QaIndex) => {
        setIndex(data);
        setSessionId(initialSession(data, window.location.search));
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    // The address bar names the session on screen, so a link always opens what was being checked.
    window.history.replaceState(null, "", `?session=${encodeURIComponent(sessionId)}`);
    fetch(`/api/qa/${sessionId}/labels.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`labels: ${r.status}`))))
      .then((data: QaSession) => {
        setSession(data);
        setI(0);
        setSelected(null);
        setDirty(false);
      })
      .catch((e: Error) => setError(e.message));
    fetch(`${backendHttpBase(backendUrl)}/qa/handcheck/${sessionId}`)
      .then((r) => (r.ok ? r.json() : r.status === 404 ? null : Promise.reject(new Error(`${r.status}`))))
      .then((doc: HandCheckDoc | null) => {
        setEdits(fromHandCheck(doc));
        setSavedCount(doc ? doc.frames.length : 0);
        setSaveMsg(doc ? `loaded ${doc.frames.length} checked frames` : "no hand-check yet");
      })
      .catch((e: Error) => setSaveMsg(`hand-check unavailable: ${e.message}`));
  }, [sessionId, backendUrl]);

  const frame = session?.frames[i] ?? null;
  const boxes: EditBox[] = useMemo(
    () => (frame ? (edits[frame.frame_id]?.boxes ?? fromAuto(frame.boxes)) : []),
    [frame, edits],
  );

  const change = useCallback(
    (next: EditBox[]) => {
      if (!frame) return;
      setEdits((prev) => ({ ...prev, [frame.frame_id]: frameEdit(frame, next) }));
      setDirty(true);
    },
    [frame],
  );

  const save = useCallback(async () => {
    if (!session || !dirty) return;
    const doc = toHandCheck(session.session, session.size, "batt", edits);
    setSaveMsg("saving…");
    try {
      const r = await fetch(`${backendHttpBase(backendUrl)}/qa/handcheck/${session.session}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(doc),
      });
      const body = await r.json();
      if (!r.ok) throw new Error(`${r.status} ${body?.detail?.reason ?? ""}`);
      setDirty(false);
      setSavedCount(body.frames);
      setSaveMsg(`saved ${body.frames} frames (${body.edited} edited)`);
    } catch (e) {
      setSaveMsg(`NOT saved: ${(e as Error).message}`);
    }
  }, [session, dirty, edits, backendUrl]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!session || !frame) return;
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        void save();
        setSelected(null);
        setI((v) => (e.key === "ArrowRight" ? Math.min(session.frames.length - 1, v + 1) : Math.max(0, v - 1)));
        return;
      }
      if (!editing) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        void save();
      } else if (e.key === "a" || e.key === "A") {
        change(boxes); // the frame as shown: accepted if untouched, else edited
      } else if ((e.key === "Delete" || e.key === "Backspace") && selected !== null) {
        change(boxes.filter((_, k) => k !== selected));
        setSelected(null);
      } else if (e.key === "Escape") {
        setSelected(null);
      } else {
        const cls = classForKey(e.key);
        if (!cls) return;
        setNewClass(cls);
        if (selected !== null) change(boxes.map((b, k) => (k === selected ? { ...b, cls } : b)));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [session, frame, boxes, selected, editing, change, save]);

  if (error) return <p className="p-4 text-sm text-amber-300">QA bundle unavailable: {error}</p>;
  if (!index || !session || !frame) return <p className="p-4 text-sm text-neutral-400">Loading…</p>;
  const [w, h] = session.size;
  const checked = Object.keys(edits).length;
  const status: string = edits[frame.frame_id]?.status ?? "unchecked";
  const progress = handcheckProgress(savedCount, session.frames.length, dirty);
  return (
    <main className="flex flex-col gap-3 p-4 text-sm text-neutral-200">
      <div className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-xl font-bold text-white">{session.session}</h1>
        {index.sessions.find((s) => s.id === session.session)?.gold && (
          <span className="rounded bg-yellow-500 px-2 py-0.5 text-xs font-bold text-black">GOLD SET</span>
        )}
        <span
          className={`rounded px-2 py-0.5 text-base font-bold ${
            progress.done ? "bg-emerald-700 text-white" : "bg-red-600 text-white"
          }`}
        >
          {progress.text}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <select
          className="rounded bg-neutral-800 px-2 py-1"
          value={sessionId ?? ""}
          onChange={(e) => {
            void save();
            setSessionId(e.target.value);
          }}
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
          frame {i + 1}/{session.frames.length} · id {frame.frame_id} · {boxes.length} boxes · offset{" "}
          {session.offset_ms} ms
        </span>
        <button
          className="rounded bg-neutral-800 px-2 py-1"
          onClick={() => setI(Math.min(session.frames.length - 1, i + 1))}
        >
          ▶
        </button>
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={editing} onChange={(e) => setEditing(e.target.checked)} />
          hand-check
        </label>
        {editing && (
          <>
            <span className={status === "unchecked" ? "text-neutral-400" : "text-emerald-300"}>{status}</span>
            <span>new: {newClass}</span>
            <span>
              {checked} checked{dirty ? " · unsaved" : ""}
            </span>
            <button className="rounded bg-neutral-700 px-2 py-1" onClick={() => void save()} disabled={!dirty}>
              save
            </button>
            <span className="text-neutral-400">{saveMsg}</span>
          </>
        )}
      </div>
      <div className="relative w-full max-w-[1200px]" style={{ aspectRatio: `${w} / ${h}` }}>
        {/* eslint-disable-next-line @next/next/no-img-element -- a raw lab frame, not a page asset */}
        <img src={`/api/qa/${session.session}/${frame.file}`} alt="" className="absolute inset-0 h-full w-full" />
        {editing ? (
          <QaEditor
            boxes={boxes}
            size={session.size}
            selected={selected}
            newClass={newClass}
            onChange={change}
            onSelect={setSelected}
          />
        ) : (
          <OverlayCanvas detections={toDetections(frame, session.size)} width={w} height={h} staleMs={null} />
        )}
      </div>
      {editing && (
        <p className="text-xs text-neutral-500">
          ←/→ frames (saves) · A accept frame · drag box/corner · drag empty space to add · Del delete · 1/2/3
          player/monster/npc · Esc deselect · Ctrl/⌘+S save
        </p>
      )}
    </main>
  );
}
