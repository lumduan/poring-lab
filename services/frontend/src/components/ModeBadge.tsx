"use client";

import { type InterlockLike, modeBadge } from "@/lib/mode";
import type { Mode } from "@/lib/protocol";

/** The mode LED (Batt, 2026-10-06): BOT red and pulsing, ASSIST amber, HUMAN blue. */
export default function ModeBadge({ mode, env }: { mode: Mode | null; env: InterlockLike | null }) {
  const b = modeBadge(mode, env);
  return (
    <div className="flex items-center gap-3" role="status" aria-live="polite">
      <span
        title={`${b.label}: ${b.detail}`}
        className={`inline-flex items-center gap-2 rounded-full px-2 py-1 text-sm font-bold tracking-wide md:px-3 ${b.className}`}
        data-testid="mode-badge"
      >
        <span
          aria-hidden
          className={`h-2.5 w-2.5 rounded-full bg-current ${b.pulse ? "animate-pulse" : ""}`}
        />
        {/* on a phone the badge is its LED only (colour and pulse); the word stays for screen
            readers and in the tooltip (2026-11-09) */}
        <span className="sr-only md:not-sr-only">{b.label}</span>
      </span>
      <span className="hidden max-w-xl text-xs text-neutral-300 lg:inline">{b.detail}</span>
    </div>
  );
}
