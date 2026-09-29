// Mouse helpers for the console. Keyboard policy lives in keys.ts, geometry in view.ts.

import type { MouseButton } from "./protocol.gen";

export type ButtonName = MouseButton["button"];

export function buttonName(button: number): ButtonName | null {
  return button === 0 ? "left" : button === 1 ? "middle" : button === 2 ? "right" : null;
}

// PointerEvent.buttons bit for each button (a second button pressed while another is held
// arrives as a pointermove with `button` set: a "chord").
export const BUTTON_BITS: Record<ButtonName, number> = { left: 1, middle: 4, right: 2 };

const PIXELS_PER_NOTCH = 100;
const LINES_PER_NOTCH = 3;

/** Accumulates wheel deltas (pixels / lines / pages) into whole notches; + = down. The backend
 * turns notches into X buttons 4/5. */
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
