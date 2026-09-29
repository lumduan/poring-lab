"use client";

import { TOOLBAR, type KeyStep, type ToolbarKey } from "@/lib/keys";
import type { ViewMode } from "@/lib/view";

type Props = {
  disabled: boolean;
  mode: ViewMode;
  onKeys: (steps: KeyStep[]) => void;
  onReleaseAll: () => void;
  onModeChange: (mode: ViewMode) => void;
};

const button =
  "rounded-md border border-neutral-700 bg-neutral-900 px-2.5 py-1 text-sm hover:bg-neutral-800 disabled:opacity-40";

/** Keys a browser can't send itself (the local OS grabs them), plus view controls. Sequences are
 * defined in lib/keys.ts and never form one of the mux's reserved xfreerdp chords. */
export default function Toolbar({ disabled, mode, onKeys, onReleaseAll, onModeChange }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Remote keys">
      {(Object.keys(TOOLBAR) as ToolbarKey[]).map((key) => (
        <button
          key={key}
          type="button"
          className={button}
          title={TOOLBAR[key].title}
          disabled={disabled}
          onClick={() => onKeys(TOOLBAR[key].steps)}
        >
          {TOOLBAR[key].label}
        </button>
      ))}
      <button
        type="button"
        className={button}
        title="Release every key and button this tab holds on the remote side"
        disabled={disabled}
        onClick={onReleaseAll}
      >
        Release keyboard
      </button>
      <span className="mx-1 h-5 w-px bg-neutral-700" aria-hidden />
      <button
        type="button"
        className={button}
        aria-pressed={mode === "native"}
        title="Fit to window (keeps aspect ratio) / 1:1 pixels"
        onClick={() => onModeChange(mode === "fit" ? "native" : "fit")}
      >
        {mode === "fit" ? "Fit" : "1:1"}
      </button>
    </div>
  );
}
