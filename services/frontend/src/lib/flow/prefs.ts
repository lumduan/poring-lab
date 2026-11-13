// Per-browser conveniences of the /flows studio (which panes are open, the view, the last flow):
// localStorage, every access wrapped, so a private window, blocked site data or a full quota only
// means the defaults. Nothing that decides safety lives here (CLAUDE.md: the human-only settings
// store is the backend's); a stored flow is re-validated like an imported file before it is used.

export type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export const KEYS = {
  view: "poring-lab.flows.view.v1",
  python: "poring-lab.flows.python-panel.v1",
  inspect: "poring-lab.flows.inspect-pane.v1",
  lint: "poring-lab.flows.lint-pane.v1",
  simulate: "poring-lab.flows.simulate-pane.v1",
  paths: "poring-lab.flows.path-pane.v1",
  hunt: "poring-lab.flows.hunt-pane.v1",
  run: "poring-lab.flows.run-pane.v1", // the Run pane (a flow whose map holds the runner's block)
  flow: "poring-lab.flows.flow.v1",
  world: "poring-lab.flows.world.v1", // the static data the last flow is linted and simulated on
  // the last flow's saved name and the GitHub file it came from (file.ts FileMeta); never the world
  file: "poring-lab.flows.file.v1",
} as const;

/** The browser's localStorage, or null where reading it throws (blocked site data). */
export function browserStorage(): StorageLike | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

/** A stored choice among `options`, else `fallback` (missing, unknown, or the storage fails). */
export function readChoice<T extends string>(store: StorageLike | null, key: string, options: readonly T[], fallback: T): T {
  try {
    const v = store?.getItem(key);
    return v !== null && v !== undefined && (options as readonly string[]).includes(v) ? (v as T) : fallback;
  } catch {
    return fallback;
  }
}

/** Store a choice; false when the storage refused it (the page works on, unremembered). */
export function writeChoice(store: StorageLike | null, key: string, value: string): boolean {
  try {
    if (!store) return false;
    store.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

/** Raw text (the last flow's JSON), or null. */
export function readText(store: StorageLike | null, key: string): string | null {
  try {
    return store?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

/** The studio's flow's name as this browser saved it (the flows row shows it on a map flow's page,
 * Batt 2026-11-13); a broken or missing save: "my flow". Display only: the studio checks the saved
 * flow itself when it opens. */
export function savedFlowName(store: StorageLike | null): string {
  try {
    const v = JSON.parse(readText(store, KEYS.flow) ?? "null") as { name?: unknown } | null;
    return typeof v?.name === "string" && v.name.trim() ? v.name : "my flow";
  } catch {
    return "my flow";
  }
}

export function forget(store: StorageLike | null, key: string): void {
  try {
    store?.removeItem(key);
  } catch {
    // nothing to do: the next read falls back anyway
  }
}

/** The Python pane opens by default on screens at least 48rem wide (Batt: side by side is the
 * key), and stays closed on a phone, where it would cover the blocks. */
export function pythonDefault(wide: boolean): "open" | "closed" {
  return wide ? "open" : "closed";
}

/** THE PROJECT this browser has open (format 3, 2026-11-13): /maps and /flows read and write the
 * same one. A bad or old value reads as none (the pages offer the ready-made projects); the old
 * IR 2 flow (`KEYS.flow`) is not opened any more (Batt: "refactor fresh"). */
export const PROJECT_STORE = "poring-lab.flows.project.v3";
export function readProjectText(store: StorageLike | null): string | null {
  return readText(store, PROJECT_STORE);
}
export function writeProjectText(store: StorageLike | null, text: string): boolean {
  return writeChoice(store, PROJECT_STORE, text);
}
/** Whether this browser still holds a flow of the old format (the pages say it was not converted). */
export function hasOldFlow(store: StorageLike | null): boolean {
  return readText(store, KEYS.flow) !== null;
}
