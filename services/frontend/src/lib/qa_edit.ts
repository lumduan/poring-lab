/** B6 hand-check editing (Post-S2 round Part D, 2026-10-04): the pure logic behind the /qa editor.
 * Boxes are in image pixels (the session's game-region size). The editor keeps one FrameEdit per
 * reviewed frame and PUTs them all to the backend (/qa/handcheck/<session>); label_iou.py scores
 * the auto-labels against them. */
import type { QaBox, QaFrame } from "@/lib/qa";

export const CLASSES = ["player", "monster", "npc"] as const;
export type Cls = (typeof CLASSES)[number];
export type EditBox = { x1: number; y1: number; x2: number; y2: number; cls: Cls; gid: number | null };
export type FrameEdit = {
  frame_id: number;
  t_mono_ns: number;
  status: "accepted" | "edited";
  boxes: EditBox[];
};
export type Part = "move" | "nw" | "ne" | "sw" | "se";
export type Hit = { index: number; part: Part };
export type HandCheckDoc = {
  session: string;
  size: [number, number];
  author: string;
  frames: FrameEdit[];
};

export const HANDLE_PX = 7;
export const MIN_BOX_PX = 4;

/** Keys 1/2/3 pick the class of a new (or the selected) box. */
export function classForKey(key: string): Cls | null {
  const i = ["1", "2", "3"].indexOf(key);
  return i < 0 ? null : CLASSES[i];
}

export function normalize(b: EditBox): EditBox {
  return {
    ...b,
    x1: Math.min(b.x1, b.x2),
    x2: Math.max(b.x1, b.x2),
    y1: Math.min(b.y1, b.y2),
    y2: Math.max(b.y1, b.y2),
  };
}

function clampBox(b: EditBox, [w, h]: [number, number]): EditBox {
  const c = (v: number, max: number) => Math.min(max, Math.max(0, v));
  return normalize({ ...b, x1: c(b.x1, w), x2: c(b.x2, w), y1: c(b.y1, h), y2: c(b.y2, h) });
}

/** The auto-labels of a frame as editable boxes (an unknown class becomes "npc"). */
export function fromAuto(boxes: QaBox[]): EditBox[] {
  return boxes.map((b) => ({
    x1: b.x1,
    y1: b.y1,
    x2: b.x2,
    y2: b.y2,
    cls: (CLASSES as readonly string[]).includes(b.cls) ? (b.cls as Cls) : "npc",
    gid: b.gid,
  }));
}

/** The topmost box under (x, y): a corner handle first, then the body (the last drawn wins). */
export function hitTest(boxes: EditBox[], x: number, y: number, handle = HANDLE_PX): Hit | null {
  for (let i = boxes.length - 1; i >= 0; i--) {
    const b = boxes[i];
    const corners: [Part, number, number][] = [
      ["nw", b.x1, b.y1],
      ["ne", b.x2, b.y1],
      ["sw", b.x1, b.y2],
      ["se", b.x2, b.y2],
    ];
    for (const [part, cx, cy] of corners) {
      if (Math.abs(x - cx) <= handle && Math.abs(y - cy) <= handle) return { index: i, part };
    }
  }
  for (let i = boxes.length - 1; i >= 0; i--) {
    const b = boxes[i];
    if (x >= b.x1 && x <= b.x2 && y >= b.y1 && y <= b.y2) return { index: i, part: "move" };
  }
  return null;
}

/** ``start`` dragged by (dx, dy) on ``part``, kept inside the image. */
export function applyDrag(start: EditBox, part: Part, dx: number, dy: number, size: [number, number]): EditBox {
  const [w, h] = size;
  if (part === "move") {
    const bw = start.x2 - start.x1;
    const bh = start.y2 - start.y1;
    const x1 = Math.min(w - bw, Math.max(0, start.x1 + dx));
    const y1 = Math.min(h - bh, Math.max(0, start.y1 + dy));
    return { ...start, x1, y1, x2: x1 + bw, y2: y1 + bh };
  }
  const b = { ...start };
  if (part === "nw" || part === "sw") b.x1 += dx;
  if (part === "ne" || part === "se") b.x2 += dx;
  if (part === "nw" || part === "ne") b.y1 += dy;
  if (part === "sw" || part === "se") b.y2 += dy;
  return clampBox(b, size);
}

/** A new box dragged from (x0, y0) to (x1, y1); null when it is too small to be meant. */
export function newBox(x0: number, y0: number, x1: number, y1: number, cls: Cls, size: [number, number]): EditBox | null {
  const b = clampBox({ x1: x0, y1: y0, x2: x1, y2: y1, cls, gid: null }, size);
  return b.x2 - b.x1 < MIN_BOX_PX || b.y2 - b.y1 < MIN_BOX_PX ? null : b;
}

const same = (a: EditBox, b: EditBox) =>
  a.cls === b.cls &&
  a.gid === b.gid &&
  Math.abs(a.x1 - b.x1) < 0.5 &&
  Math.abs(a.y1 - b.y1) < 0.5 &&
  Math.abs(a.x2 - b.x2) < 0.5 &&
  Math.abs(a.y2 - b.y2) < 0.5;

/** "accepted" when the boxes are the auto-labels untouched, else "edited". */
export function statusOf(auto: EditBox[], boxes: EditBox[]): "accepted" | "edited" {
  return auto.length === boxes.length && auto.every((a, i) => same(a, boxes[i])) ? "accepted" : "edited";
}

/** The reviewed state of a frame after the human's change. */
export function frameEdit(frame: QaFrame, boxes: EditBox[]): FrameEdit {
  return { frame_id: frame.frame_id, t_mono_ns: frame.t_mono_ns, status: statusOf(fromAuto(frame.boxes), boxes), boxes };
}

/** The document the backend stores: reviewed frames only, in frame order, boxes rounded to 0.1 px. */
export function toHandCheck(
  session: string,
  size: [number, number],
  author: string,
  edits: Record<number, FrameEdit>,
): HandCheckDoc {
  const r = (v: number) => Math.round(v * 10) / 10;
  const frames = Object.values(edits)
    .sort((a, b) => a.frame_id - b.frame_id)
    .map((f) => ({ ...f, boxes: f.boxes.map((b) => ({ ...b, x1: r(b.x1), y1: r(b.y1), x2: r(b.x2), y2: r(b.y2) })) }));
  return { session, size, author, frames };
}

export function fromHandCheck(doc: HandCheckDoc | null): Record<number, FrameEdit> {
  const out: Record<number, FrameEdit> = {};
  for (const f of doc?.frames ?? []) out[f.frame_id] = f;
  return out;
}

/** Client pixels on the overlay -> image pixels (the overlay is scaled to the frame). */
export function toImage(
  clientX: number,
  clientY: number,
  rect: { left: number; top: number; width: number; height: number },
  size: [number, number],
): [number, number] {
  return [((clientX - rect.left) / rect.width) * size[0], ((clientY - rect.top) / rect.height) * size[1]];
}
