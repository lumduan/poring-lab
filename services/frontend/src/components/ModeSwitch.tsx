"use client";

import { MODE_ACTIVE_CLASS } from "@/lib/mode";
import type { Mode } from "@/lib/protocol";

const MODES: { mode: Mode; hint: string }[] = [
  { mode: "HUMAN", hint: "Only you control the session; bot input is dropped." },
  { mode: "ASSIST", hint: "The bot acts, but any input from you takes over for 3 s." },
  { mode: "BOT", hint: "Only the bot controls the session; your input is dropped." },
];

type Props = { mode: Mode | null; onChange: (mode: Mode) => void; disabled: boolean };

export default function ModeSwitch({ mode, onChange, disabled }: Props) {
  return (
    <div
      role="radiogroup"
      aria-label="Input mode"
      className="inline-flex overflow-hidden rounded-md border border-neutral-700"
    >
      {MODES.map(({ mode: option, hint }) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={mode === option}
          title={hint}
          disabled={disabled}
          onClick={() => onChange(option)}
          className={`px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-40 ${
            mode === option
              ? MODE_ACTIVE_CLASS[option]
              : "bg-neutral-900 text-neutral-300 hover:bg-neutral-800"
          }`}
        >
          {option}
        </button>
      ))}
    </div>
  );
}
