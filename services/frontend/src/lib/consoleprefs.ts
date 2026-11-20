// The console's toggles, remembered in this browser (Batt 2026-11-20: "the HUD and the buttons I
// pressed are forgotten when I go to /flows and come back; make it remember them"): HUD, Watch
// only, Secret typing and the view (Fit / Native). localStorage through flow/prefs, every access
// wrapped: a private window or blocked site data only means the defaults (all off, Fit). This
// tab's display and its own input only -- nothing that decides safety (the mux mode, the
// interlock, the settings store) is kept here. Pure, unit tested with `node --test`
// (src/lib/consoleprefs.test.ts).
//
// It supersedes "off on every load" for Watch only (2026-10-07) and the HUD (2026-10-08). Both
// remembered ON are the cautious side: Watch only forwards no input (the bot keeps its lease),
// Secret typing logs less.

import { readChoice, type StorageLike, writeChoice } from "./flow/prefs.ts";
import type { ViewMode } from "./view.ts";

export const CONSOLE_KEYS = {
  hud: "poring-lab.console.hud.v1",
  watchOnly: "poring-lab.console.watch-only.v1",
  secret: "poring-lab.console.secret-typing.v1",
  view: "poring-lab.console.view.v1",
} as const;

export type ConsolePrefs = { hud: boolean; watchOnly: boolean; secret: boolean; view: ViewMode };
export type ConsoleToggle = "hud" | "watchOnly" | "secret";

export const CONSOLE_DEFAULTS: ConsolePrefs = { hud: false, watchOnly: false, secret: false, view: "fit" };

const ON_OFF = ["on", "off"] as const;
const VIEWS: readonly ViewMode[] = ["fit", "native"];

/** This browser's remembered toggles; the defaults wherever nothing (valid) is stored. */
export function loadConsolePrefs(store: StorageLike | null): ConsolePrefs {
  const on = (k: ConsoleToggle) => readChoice(store, CONSOLE_KEYS[k], ON_OFF, "off") === "on";
  return {
    hud: on("hud"),
    watchOnly: on("watchOnly"),
    secret: on("secret"),
    view: readChoice(store, CONSOLE_KEYS.view, VIEWS, CONSOLE_DEFAULTS.view),
  };
}

/** Remember one toggle; false when the storage refused it (the console works on, unremembered). */
export function saveToggle(store: StorageLike | null, key: ConsoleToggle, on: boolean): boolean {
  return writeChoice(store, CONSOLE_KEYS[key], on ? "on" : "off");
}

/** Remember the view (Fit / Native). */
export function saveView(store: StorageLike | null, view: ViewMode): boolean {
  return writeChoice(store, CONSOLE_KEYS.view, view);
}
