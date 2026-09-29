// Hand-written helpers around the GENERATED protocol types (protocol.gen.ts).

import type { BackendToBrowser } from "./protocol.gen";

export type * from "./protocol.gen";

export const NO_FRAME = -1;

/** The browser's monotonic clock in ns. A separate clock domain from the backend's
 * CLOCK_MONOTONIC: compare the two only through ping/pong round trips. */
export function browserNowNs(): number {
  return Math.round(performance.now() * 1e6);
}

/** Parse a text frame from /ws/stream or /ws/input. The backend validates everything it sends
 * with the same Pydantic models the types are generated from, so no runtime validation here. */
export function parseServerMessage(text: string): BackendToBrowser | null {
  try {
    return JSON.parse(text) as BackendToBrowser;
  } catch {
    return null;
  }
}
