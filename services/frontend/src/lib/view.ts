// Where the remote frame is drawn, and how pointer positions map onto it. Pure functions, unit
// tested with `node --test` (src/lib/view.test.ts).

export type Size = { width: number; height: number };
export type Rect = { x: number; y: number; width: number; height: number };

/** "fit": scaled to the viewport keeping the aspect ratio, centred (letterbox or pillarbox).
 * "native": 1:1 pixels at the top-left; the viewport scrolls. */
export type ViewMode = "fit" | "native";

export function drawRect(viewport: Size, frame: Size, mode: ViewMode): Rect {
  const native = { x: 0, y: 0, width: frame.width, height: frame.height };
  if (mode === "native" || frame.width <= 0 || frame.height <= 0) return native;
  if (viewport.width <= 0 || viewport.height <= 0) return native;
  const scale = Math.min(viewport.width / frame.width, viewport.height / frame.height);
  const width = frame.width * scale;
  const height = frame.height * scale;
  return { x: (viewport.width - width) / 2, y: (viewport.height - height) / 2, width, height };
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

/** Normalize a point to [0, 1] over the drawn image `rect` (same coordinate space, e.g. client
 * pixels from getBoundingClientRect). Points in the letterbox report `inside: false` and are
 * clamped to the nearest image edge (useful for moves; presses there should be ignored). */
export function normalizePoint(
  px: number,
  py: number,
  rect: Rect,
): { x: number; y: number; inside: boolean } {
  if (rect.width <= 0 || rect.height <= 0) return { x: 0, y: 0, inside: false };
  const u = (px - rect.x) / rect.width;
  const v = (py - rect.y) / rect.height;
  return { x: clamp01(u), y: clamp01(v), inside: u >= 0 && u <= 1 && v >= 0 && v <= 1 };
}
