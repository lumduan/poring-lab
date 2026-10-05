/** Phase 2 label QA bundles (scripts/qa_export.py): types and the box conversion for the overlay. */
import type { Detections } from "@/lib/protocol";

export type QaBox = { x1: number; y1: number; x2: number; y2: number; cls: string; gid: number };
export type QaFrame = { file: string; frame_id: number; t_mono_ns: number; boxes: QaBox[] };
export type QaSession = { session: string; size: [number, number]; offset_ms: number; frames: QaFrame[] };
export type QaIndex = { sessions: { id: string; title: string; frames: number; gold?: boolean }[] };

/** The session /qa opens on: the one named by `?session=` when the index has it, else the GOLD set
 * (`qa_export.py --mark-gold`), else the newest. (2026-10-04 and again 10-05: the gold set was never
 * opened because /qa started on the newest session, a different indoor run.) */
export function initialSession(index: QaIndex, search: string): string | null {
  const wanted = new URLSearchParams(search).get("session");
  if (wanted && index.sessions.some((s) => s.id === wanted)) return wanted;
  const gold = index.sessions.find((s) => s.gold);
  if (gold) return gold.id;
  return index.sessions.length ? index.sessions[index.sessions.length - 1].id : null;
}

/** The hand-check's progress, as the page shows it in large type: frames SAVED to the backend (not
 * merely looked at; the editor saves only after A or an edit). */
export function handcheckProgress(saved: number, total: number, dirty: boolean): {
  text: string;
  done: boolean;
} {
  const done = saved >= total && total > 0 && !dirty;
  const tail = dirty ? " (UNSAVED changes: press an arrow key or Ctrl/⌘+S)" : "";
  return { text: `hand-check saved: ${saved} / ${total} frames${tail}`, done };
}

/** Pixel boxes of a frame -> the Detections shape OverlayCanvas draws (normalized, conf 1). */
export function toDetections(frame: QaFrame, size: [number, number]): Detections {
  const [w, h] = size;
  const clamp = (v: number) => Math.min(1, Math.max(0, v));
  return {
    type: "detections",
    t_mono_ns: frame.t_mono_ns,
    frame_id: frame.frame_id,
    t_capture_ns: frame.t_mono_ns,
    boxes: frame.boxes.map((b) => ({
      x1: clamp(b.x1 / w),
      y1: clamp(b.y1 / h),
      x2: clamp(b.x2 / w),
      y2: clamp(b.y2 / h),
      cls: `${b.cls} #${b.gid}`,
      conf: 1,
    })),
  };
}
