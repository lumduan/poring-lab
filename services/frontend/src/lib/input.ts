// Browser input -> protocol fields. Keys travel as KeyboardEvent.code (a PHYSICAL key position),
// which the backend maps to X keycodes; the Windows side applies its own layout.

import type { MouseButton } from "./protocol.gen";

/** Normalized [0, 1] position of a pointer event over the video canvas. */
export function normalizePointer(event: MouseEvent, rect: DOMRect): { x: number; y: number } {
  const clamp = (v: number) => Math.min(1, Math.max(0, v));
  return {
    x: clamp((event.clientX - rect.left) / rect.width),
    y: clamp((event.clientY - rect.top) / rect.height),
  };
}

export function buttonName(button: number): MouseButton["button"] | null {
  return button === 0 ? "left" : button === 1 ? "middle" : button === 2 ? "right" : null;
}

/** While the game view has focus every key goes to the game, including F1-F12, Tab, Space and
 * the arrows (browser reload, fullscreen, focus moves, scrolling). Cmd/Meta combos stay with the
 * browser so it remains escapable. */
export function shouldPreventDefault(event: KeyboardEvent): boolean {
  return !event.metaKey;
}

const PIXELS_PER_NOTCH = 100;
const LINES_PER_NOTCH = 3;

/** Accumulates wheel deltas (pixels / lines / pages) into whole notches; + = down. */
export class WheelAccumulator {
  private acc = 0;

  push(event: WheelEvent): number {
    const unit =
      event.deltaMode === WheelEvent.DOM_DELTA_PIXEL
        ? PIXELS_PER_NOTCH
        : event.deltaMode === WheelEvent.DOM_DELTA_LINE
          ? LINES_PER_NOTCH
          : 1;
    this.acc += event.deltaY / unit;
    const notches = Math.trunc(this.acc);
    this.acc -= notches;
    return Math.max(-10, Math.min(10, notches));
  }
}
