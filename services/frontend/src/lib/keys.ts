// Keyboard policy for the console. Pure, unit tested with `node --test` (src/lib/keys.test.ts).
//
// Keys travel as KeyboardEvent.code (a physical key position); the backend maps them to X keycodes
// (packages/poring_env/src/poring_env/keymap.py, mirrored in keycodes.gen.ts). Codes the backend
// can't inject are dropped here instead of being sent and rejected.

import { KNOWN_CODES } from "./keycodes.gen.ts";

const KNOWN = new Set<string>(KNOWN_CODES);
const CONTROL = new Set(["ControlLeft", "ControlRight"]);
const ALT = new Set(["AltLeft", "AltRight"]);
// Mirror of the mux's reserved chords (services/backend/src/poring_backend/mux.py): xfreerdp
// client hotkeys that would act on the ONE RDP session itself (disconnect / fullscreen).
const RESERVED_WITH_CTRL_ALT = new Set(["KeyD", "Enter", "NumpadEnter"]);
// A physical Win/Cmd press belongs to the viewer's own OS; the toolbar sends Win explicitly.
const LOCAL_ONLY = new Set(["MetaLeft", "MetaRight"]);

export type KeyAction = "down" | "up";
export type KeyStep = { code: string; action: KeyAction };

export function isKnownCode(code: string): boolean {
  return KNOWN.has(code);
}

/** Whether a physical key event from the browser should be forwarded to the session. */
export function shouldForwardPhysical(code: string): boolean {
  return KNOWN.has(code) && !LOCAL_ONLY.has(code);
}

/** True if pressing `code` while `held` is down would form a reserved xfreerdp chord. */
export function isReservedChord(held: ReadonlySet<string>, code: string): boolean {
  if (!RESERVED_WITH_CTRL_ALT.has(code)) return false;
  const ctrl = [...held].some((c) => CONTROL.has(c));
  const alt = [...held].some((c) => ALT.has(c));
  return ctrl && alt;
}

/** Press `codes` in order, release them in reverse (a chord). */
export function chord(codes: string[]): KeyStep[] {
  return [
    ...codes.map((code) => ({ code, action: "down" as const })),
    ...[...codes].reverse().map((code) => ({ code, action: "up" as const })),
  ];
}

export type ToolbarKey = "ctrlAltDel" | "win" | "altTab" | "esc";

export const TOOLBAR: Record<ToolbarKey, { label: string; title: string; steps: KeyStep[] }> = {
  ctrlAltDel: {
    label: "Ctrl+Alt+Del",
    title: "Sent as Ctrl+Alt+End, the RDP mapping of the secure-attention sequence",
    steps: chord(["ControlLeft", "AltLeft", "End"]),
  },
  win: { label: "Win", title: "Windows key (Start menu)", steps: chord(["MetaLeft"]) },
  altTab: { label: "Alt+Tab", title: "Switch window", steps: chord(["AltLeft", "Tab"]) },
  esc: { label: "Esc", title: "Escape", steps: chord(["Escape"]) },
};

/** Keys this browser tab currently holds down on the remote side. */
export class HeldKeys {
  private readonly held = new Set<string>();

  get codes(): ReadonlySet<string> {
    return this.held;
  }

  /** Record a step; returns false if it must not be sent (unknown, reserved, or a stray up). */
  apply(step: KeyStep): boolean {
    if (!isKnownCode(step.code)) return false;
    if (step.action === "down") {
      if (isReservedChord(this.held, step.code)) return false;
      this.held.add(step.code);
      return true;
    }
    return this.held.delete(step.code);
  }

  clear(): void {
    this.held.clear();
  }
}
