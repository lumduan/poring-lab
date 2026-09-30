// Phase 0 latency helpers (docs/phase0-latency.md). Pure, unit tested with `node --test`.

/** Cristian's algorithm over a sliding window: backend_clock = browser_clock + offset.
 * The sample with the smallest round trip wins; its half round trip is the uncertainty. */
export class OffsetEstimator {
  private samples: { atMs: number; rttNs: number; offsetNs: number }[] = [];
  private readonly windowMs: number;

  constructor(windowMs = 30_000) {
    this.windowMs = windowMs; // not a parameter property: node's type stripping rejects those
  }

  /** One ping/pong: sent and received on the browser clock, `backendNs` stamped by the backend. */
  sample(sentNs: number, backendNs: number, receivedNs: number, nowMs: number): void {
    const rttNs = receivedNs - sentNs;
    if (rttNs < 0) return;
    this.samples.push({ atMs: nowMs, rttNs, offsetNs: backendNs - (sentNs + rttNs / 2) });
    this.samples = this.samples.filter((s) => nowMs - s.atMs <= this.windowMs);
  }

  private best(): { rttNs: number; offsetNs: number } | null {
    let best: { rttNs: number; offsetNs: number } | null = null;
    for (const s of this.samples) if (!best || s.rttNs < best.rttNs) best = s;
    return best;
  }

  get offsetNs(): number | null {
    const b = this.best();
    return b ? Math.round(b.offsetNs) : null;
  }

  get uncertaintyNs(): number | null {
    const b = this.best();
    return b ? Math.round(b.rttNs / 2) : null;
  }
}

/** How long a pointer move must still wait so that at most one is sent per `intervalMs`. */
export function moveDelayMs(sinceLastSendMs: number, intervalMs: number): number {
  return Math.max(0, intervalMs - sinceLastSendMs);
}

/** An event's own timestamp on the performance.now() clock, falling back to `nowMs` if the browser
 * reports something else (old engines used epoch milliseconds). */
export function eventTimeMs(timeStamp: number, nowMs: number): number {
  return timeStamp > 0 && Math.abs(nowMs - timeStamp) < 10_000 ? timeStamp : nowMs;
}

/** Holds only the newest item: putting a new one hands back the one it replaced (to be closed). */
export class LatestSlot<T> {
  private item: T | null = null;
  dropped = 0;

  put(next: T): T | null {
    const old = this.item;
    this.item = next;
    if (old !== null) this.dropped += 1;
    return old;
  }

  take(): T | null {
    const item = this.item;
    this.item = null;
    return item;
  }
}

/** p50 of a list (0 for empty); the console's live readouts. */
export function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = sorted.length >> 1;
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}
