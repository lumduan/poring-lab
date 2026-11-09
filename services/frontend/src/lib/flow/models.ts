// The TRAINED MODELS as sensor devices in the block editor (Batt 2026-11-09: "design the trained
// model files as blocks"; ADR-0020 Amendment B). Pure data, no Blockly: the two blocks' dropdown
// menus, tested in models.test.ts. The catalogue comes from the backend (GET /flows/catalogue
// `models`, packages/poring_flow models.yaml): ids, kinds, statuses, class names.
//
// "[eye] detector <model> sees <class>" is the IR's `detector_sees(model, label)` sensor, a Boolean;
// "[eye] detector <model> count of <class>" is `detector_count(model, label)`, a number. A model
// that is NOT adopted (the Stormy Knight recognizer: round 1 failed its held-out bar) is never
// offered as a working sensor: it is listed apart, with why, and the linter refuses it.

export type ModelDoc = {
  kind: "detector" | "boss_recognizer";
  status: "live" | "not_adopted";
  file: string;
  sha256: string;
  maps: string[];
  classes: string[];
  untrained: string[];
  mobs: Record<string, number[]>;
  why: string;
  available: boolean;
  counts: boolean;
};
export type Models = Record<string, ModelDoc>;
export type Option = [string, string];

/** The block type -> the catalogue sensor it is. */
export const DETECT_SENSOR: Record<string, "detector_sees" | "detector_count"> = {
  pl_detect_sees: "detector_sees",
  pl_detect_count: "detector_count",
};
export const SENSOR_BLOCK: Record<string, string> = { detector_sees: "pl_detect_sees", detector_count: "pl_detect_count" };
export const MODEL_KEY = /^[a-z][a-z0-9_-]{0,31}$/;
export const CLASS_KEY = /^[a-z][a-z0-9_]{0,47}$/;

/** The models a block may pick: the LIVE ones (only detectors for a count), plus the block's own
 * value when it is another (an imported flow keeps it; the linter names the problem). */
export function modelOptions(models: Models | null, current: string | null, counting: boolean): Option[] {
  const out: Option[] = [];
  for (const [id, m] of Object.entries(models ?? {})) {
    if (m.available && (!counting || m.counts)) out.push([m.maps.length ? `${id} (${m.maps.join(", ")})` : id, id]);
  }
  if (current && !out.some(([, v]) => v === current)) {
    const m = models?.[current];
    out.push([`${current} (${m ? (m.available ? "does not count" : "not adopted") : "unknown model"})`, current]);
  }
  if (!out.length) out.push(["v1", "v1"]);
  return out;
}

/** The classes of a model (its trained ones), plus the block's own value when it is not one. */
export function classOptions(models: Models | null, model: string, current: string | null): Option[] {
  const m = models?.[model];
  const out: Option[] = (m?.classes ?? []).map((c) => [c.replaceAll("_", " "), c]);
  if (current && !out.some(([, v]) => v === current)) out.push([`${current.replaceAll("_", " ")} (not a class of ${model})`, current]);
  if (!out.length) out.push(["monster", "monster"]);
  return out;
}

/** The class a new model choice starts with (its first), or the current one if it still fits. */
export function classFor(models: Models | null, model: string, current: string): string {
  const m = models?.[model];
  if (!m || m.classes.includes(current)) return current;
  return m.classes[0] ?? current;
}

/** The first live detector and its first class: what a new block starts with. */
export function firstDetector(models: Models | null): { model: string; label: string } {
  for (const [id, m] of Object.entries(models ?? {})) {
    if (m.available && m.counts && !m.maps.length) return { model: id, label: m.classes.includes("monster") ? "monster" : m.classes[0] };
  }
  return { model: "v1", label: "monster" };
}

/** The not-adopted models, each with why: shown in the Sensors category as text, never as a block. */
export function notAdopted(models: Models | null): string[] {
  return Object.entries(models ?? {})
    .filter(([, m]) => !m.available)
    .map(([id, m]) => `${id}: not adopted, so not offered (${m.kind === "boss_recognizer" ? "a boss recognizer" : "a detector"})`);
}
