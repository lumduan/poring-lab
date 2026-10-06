"use client";

import { type InterlockLike, modeBadge } from "@/lib/mode";
import type { Mode } from "@/lib/protocol";

/** The mode LED (Batt, 2026-10-06): BOT red and pulsing, ASSIST amber, HUMAN blue. */
export default function ModeBadge({ mode, env }: { mode: Mode | null; env: InterlockLike | null }) {
  const b = modeBadge(mode, env);
  return (
    <div className="flex items-center gap-3" role="status" aria-live="polite">
      <span
        title={b.detail}
        className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-bold tracking-wide ${b.className}`}
      >
        <span
          aria-hidden
          className={`h-2.5 w-2.5 rounded-full bg-current ${b.pulse ? "animate-pulse" : ""}`}
        />
        {b.label}
      </span>
      <span className="hidden max-w-xl text-xs text-neutral-300 lg:inline">{b.detail}</span>
    </div>
  );
}
