"use client";

import { hudToggle } from "@/lib/hud";
import { TOOLBAR, type KeyStep, type ToolbarKey } from "@/lib/keys";
import type { ViewMode } from "@/lib/view";
import { watchToggle } from "@/lib/watch";

type Props = {
  disabled: boolean;
  mode: ViewMode;
  /** Secret typing, as the backend reports it (Status.human_secret): true while ANY console has it on. */
  secret: boolean;
  /** Watch only: this tab forwards no input (Batt, 2026-10-07). */
  watchOnly: boolean;
  onWatchOnlyChange: (on: boolean) => void;
  /** The operator HUD: shown in this tab only, off on every load (Batt, 2026-10-08). */
  hud: boolean;
  onHudChange: (on: boolean) => void;
  onKeys: (steps: KeyStep[]) => void;
  onReleaseAll: () => void;
  onModeChange: (mode: ViewMode) => void;
  onSecretChange: (on: boolean) => void;
};

const button =
  "rounded-md border border-neutral-700 bg-neutral-900 px-2.5 py-1 text-sm hover:bg-neutral-800 disabled:opacity-40";

/** Keys a browser can't send itself (the local OS grabs them), plus view controls. Sequences are
 * defined in lib/keys.ts and never form one of the mux's reserved xfreerdp chords. */
const secretOn =
  "rounded-md border border-red-500 bg-red-900/60 px-2.5 py-1 text-sm font-semibold text-red-100 hover:bg-red-900 disabled:opacity-40";
const watchOn =
  "rounded-md border border-amber-400 bg-amber-500 px-2.5 py-1 text-sm font-semibold text-neutral-950 hover:bg-amber-400";
const hudOn =
  "rounded-md border border-fuchsia-400 bg-fuchsia-900/60 px-2.5 py-1 text-sm font-semibold text-fuchsia-100 hover:bg-fuchsia-900";

export default function Toolbar({
  disabled,
  mode,
  secret,
  watchOnly,
  onWatchOnlyChange,
  hud,
  onHudChange,
  onKeys,
  onReleaseAll,
  onModeChange,
  onSecretChange,
}: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Remote keys">
      {(Object.keys(TOOLBAR) as ToolbarKey[]).map((key) => (
        <button
          key={key}
          type="button"
          className={button}
          title={TOOLBAR[key].title}
          disabled={disabled || watchOnly}
          onClick={() => onKeys(TOOLBAR[key].steps)}
        >
          {TOOLBAR[key].label}
        </button>
      ))}
      <button
        type="button"
        className={button}
        title="Release every key and button this tab holds on the remote side"
        disabled={disabled || watchOnly}
        onClick={onReleaseAll}
      >
        Release keyboard
      </button>
      <button
        type="button"
        className={secret ? secretOn : button}
        aria-pressed={secret}
        title={
          secret
            ? "Secret typing is ON: keys still reach Windows, but the input log keeps no key identities (and a paste no length or digest). Click to turn it off."
            : "Before typing a password: turn this on. Keys still reach Windows; the input log keeps type and timing only."
        }
        disabled={disabled}
        onClick={() => onSecretChange(!secret)}
      >
        {secret ? "Secret typing ON" : "Secret typing"}
      </button>
      <button
        type="button"
        className={watchOnly ? watchOn : button}
        aria-pressed={watchOnly}
        title={watchToggle(watchOnly).title}
        onClick={() => onWatchOnlyChange(!watchOnly)}
      >
        {watchToggle(watchOnly).label}
      </button>
      <button
        type="button"
        className={hud ? hudOn : button}
        aria-pressed={hud}
        title={hudToggle(hud).title}
        onClick={() => onHudChange(!hud)}
      >
        {hudToggle(hud).label}
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
