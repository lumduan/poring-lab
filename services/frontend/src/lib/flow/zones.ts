// The /flows Zones layer: map zones as MAP-NODE DATA (docs/planning/blocks-from-hunt-flow.md
// section 3 and B2; ADR-0020 Amendment A 4, DRAFT; Batt D6 2026-10-21: EXPORT only, a person
// commits the file and git is the review record). Pure data, tested in node (zones.test.ts).
//
// - The file config/map_zones/<map>.yaml and the runner's own loader (scripts/map_zones.py) stay
//   the source of truth. The browser re-implements NO geometry: the cells an item closes, the
//   pieces the zones seal off and the search area come from the backend (POST /flows/zones/check),
//   which runs that loader. What is here is the drawing (points as a person clicks them) and the
//   editor's YAML.
// - THE EDITOR'S FORM: one fixed layout, so a file a person writes BY HAND in the same form loads
//   with the same sha256 (the loader hashes the bytes). It is config/map_zones/prt_fild08.yaml's own
//   form: the leading comment lines ("# " + text, "#" for an empty one), then map, reviewed_by,
//   reviewed, delegation (when given), no_cross, no_enter; map and ids plain when YAML reads them
//   back as the same string, else double-quoted; reviewed_by, delegation and every note
//   double-quoted; points as [[x, y], ...]; "\n" line ends, one at the end.
// - reviewed_by NAMES A PERSON and the editor NEVER fills it (nor reviewed or delegation): they are
//   typed for the file being exported. The loader refuses an agent-like reviewer, except in Batt's
//   recorded-delegation form; the check route shows its message as it is.
// - Coordinates are map cells, x east, y NORTH (the README's, /where's, the server's).

export type ZoneKind = "no_cross" | "no_enter";
export type Cell = [number, number];
export type ZoneItem = { kind: ZoneKind; id: string; note: string; points: Cell[] };
/** What the editor holds for one map: no review (that is typed at export, `Review`). */
export type ZonesModel = { map: string; comment: string[]; items: ZoneItem[] };
export type Review = { reviewed_by: string; reviewed: string; delegation: string };
export type Draft = { kind: ZoneKind; points: Cell[] };

export const MAP_NAME = /^[A-Za-z0-9_@-]{1,40}$/; // the loader's MAP_NAME
export const MAX_ITEMS = 200;
export const MAX_POINTS = 200;
const DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
// YAML 1.1 words PyYAML reads as a bool or null: never written plain
const SPECIAL = new Set(
  ["y", "yes", "n", "no", "true", "false", "on", "off", "null"].flatMap((w) => [w, w.toUpperCase(), w[0].toUpperCase() + w.slice(1)]),
);
const PLAIN = /^[A-Za-z_][A-Za-z0-9_-]*$/;

export function emptyZones(map: string): ZonesModel {
  return { map, comment: [], items: [] };
}

export function emptyReview(): Review {
  return { reviewed_by: "", reviewed: "", delegation: "" };
}

/** One line of printable text: what PyYAML's reader accepts inside a double-quoted scalar
 * without a line break (no control characters, no NEL / LS / PS, no BOM, no lone surrogate). */
export function printableLine(s: string): boolean {
  for (const ch of s) {
    const c = ch.codePointAt(0)!;
    const ok =
      (c >= 0x20 && c <= 0x7e) ||
      (c >= 0xa0 && c <= 0xd7ff && c !== 0x2028 && c !== 0x2029) ||
      (c >= 0xe000 && c <= 0xfffd && c !== 0xfeff) ||
      c >= 0x10000;
    if (!ok) return false;
  }
  return true;
}

function scalar(s: string): string {
  return PLAIN.test(s) && !SPECIAL.has(s) ? s : dq(s);
}

function dq(s: string): string {
  return JSON.stringify(s); // printable text only (checked): escapes just `"` and `\`
}

const pts = (p: Cell[]) => `[${p.map(([x, y]) => `[${x}, ${y}]`).join(", ")}]`;

function realDate(s: string): boolean {
  const m = DATE.exec(s);
  if (!m) return false;
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  return d.getUTCFullYear() === Number(m[1]) && d.getUTCMonth() === Number(m[2]) - 1 && d.getUTCDate() === Number(m[3]);
}

/** What the editor refuses before export (the loader decides the rest: the check route). */
export function problems(model: ZonesModel, review: Review): string[] {
  const out: string[] = [];
  if (!MAP_NAME.test(model.map)) out.push(`map ${JSON.stringify(model.map)} is not a file name`);
  if (!review.reviewed_by.trim()) out.push("reviewed_by: type the PERSON who reviewed this file (the editor never fills it)");
  else if (!printableLine(review.reviewed_by)) out.push("reviewed_by: one line of printable text");
  if (!realDate(review.reviewed)) out.push("reviewed: the review date, YYYY-MM-DD");
  if (review.delegation && !printableLine(review.delegation)) out.push("delegation: one line of printable text");
  model.comment.forEach((c, i) => {
    if (!printableLine(c)) out.push(`comment line ${i + 1}: one line of printable text`);
  });
  const ids = new Set<string>();
  model.items.forEach((it, i) => {
    const where = `${it.kind} ${i + 1} (${JSON.stringify(it.id)})`;
    if (!it.id || !printableLine(it.id)) out.push(`${where}: an id of printable text`);
    if (ids.has(it.id)) out.push(`${where}: a duplicate id (ids are unique per file)`);
    ids.add(it.id);
    if (!it.note.trim() || !printableLine(it.note)) out.push(`${where}: a short note, one line`);
    const min = it.kind === "no_cross" ? 2 : 3;
    if (it.points.length < min) out.push(`${where}: at least ${min} points`);
    if (!it.points.every(([x, y]) => Number.isSafeInteger(x) && Number.isSafeInteger(y))) out.push(`${where}: cells are whole numbers`);
  });
  if (model.items.length > MAX_ITEMS) out.push(`at most ${MAX_ITEMS} items`);
  return out;
}

/** The file in the editor's form (header doc), or what stops it. */
export function zonesYaml(model: ZonesModel, review: Review): { ok: true; text: string } | { ok: false; errors: string[] } {
  const errors = problems(model, review);
  if (errors.length) return { ok: false, errors };
  const out: string[] = model.comment.map((c) => (c === "" ? "#" : `# ${c}`));
  out.push(`map: ${scalar(model.map)}`, `reviewed_by: ${dq(review.reviewed_by)}`, `reviewed: ${review.reviewed}`);
  if (review.delegation) out.push(`delegation: ${dq(review.delegation)}`);
  for (const kind of ["no_cross", "no_enter"] as const) {
    const items = model.items.filter((it) => it.kind === kind);
    if (!items.length) continue;
    out.push(`${kind}:`);
    for (const it of items) {
      out.push(`  - id: ${scalar(it.id)}`, `    note: ${dq(it.note)}`, `    ${kind === "no_cross" ? "points" : "polygon"}: ${pts(it.points)}`);
    }
  }
  return { ok: true, text: out.join("\n") + "\n" };
}

/** The cell under a pixel of the map canvas: (dx, dy) from the canvas CONTENT box's top-left, in
 * canvas pixels; y grows NORTH (y = 0 is the bottom row). Null off the map. */
export function cellOfPixel(dx: number, dy: number, scale: number, w: number, h: number): Cell | null {
  const x = Math.floor(dx / scale);
  const y = h - 1 - Math.floor(dy / scale);
  return dx >= 0 && dy >= 0 && x >= 0 && x < w && y >= 0 && y < h ? [x, y] : null;
}

// --- drawing (a person's clicks; the loader's own rules refused early) ---------------------------
export function startDraft(kind: ZoneKind): Draft {
  return { kind, points: [] };
}

const same = (a: Cell, b: Cell) => a[0] === b[0] && a[1] === b[1];

/** A click on a cell. A click on the cell just added adds nothing (a double click's second click;
 * the loader refuses a line's "point k repeats the one before it"); an area refuses another cell
 * it has, except its FIRST, which CLOSES it (3+ points). */
export function addPoint(d: Draft, c: Cell): { draft: Draft; closed: boolean; error: string | null } {
  if (!Number.isSafeInteger(c[0]) || !Number.isSafeInteger(c[1]) || c[0] < 0 || c[1] < 0) {
    return { draft: d, closed: false, error: "a cell on the map" };
  }
  if (d.points.length >= MAX_POINTS) return { draft: d, closed: false, error: `at most ${MAX_POINTS} points` };
  if (d.kind === "no_cross") {
    const last = d.points[d.points.length - 1];
    if (last && same(last, c)) return { draft: d, closed: false, error: null }; // a double click's second click
    return { draft: { ...d, points: [...d.points, c] }, closed: false, error: null };
  }
  const last = d.points[d.points.length - 1];
  if (last && same(last, c) && d.points.length > 1) return { draft: d, closed: false, error: null }; // a double click
  if (d.points.length && same(d.points[0], c)) {
    if (d.points.length >= 3) return { draft: d, closed: true, error: null };
    return { draft: d, closed: false, error: "an area needs 3 corners before it closes" };
  }
  if (d.points.some((p) => same(p, c))) return { draft: d, closed: false, error: "a corner repeats: click the FIRST corner to close" };
  return { draft: { ...d, points: [...d.points, c] }, closed: false, error: null };
}

export function undoPoint(d: Draft): Draft {
  return { ...d, points: d.points.slice(0, -1) };
}

/** Can the draft become an item (a line: 2+ points; an area: 3+)? */
export function finished(d: Draft): boolean {
  return d.points.length >= (d.kind === "no_cross" ? 2 : 3);
}

export function suggestId(model: ZonesModel, kind: ZoneKind): string {
  const prefix = kind === "no_cross" ? "nc" : "ne";
  const used = new Set(model.items.map((it) => it.id));
  for (let i = 1; ; i++) if (!used.has(`${prefix}${i}`)) return `${prefix}${i}`;
}

/** The finished draft as an item with the id and note a person gave it. */
export function addItem(model: ZonesModel, d: Draft, id: string, note: string): { ok: true; model: ZonesModel } | { ok: false; error: string } {
  if (!finished(d)) return { ok: false, error: d.kind === "no_cross" ? "a line needs 2 points" : "an area needs 3 corners" };
  const iid = id.trim();
  if (!iid || !printableLine(iid)) return { ok: false, error: "an id: one line of text" };
  if (model.items.some((it) => it.id === iid)) return { ok: false, error: `the id ${iid} is taken (ids are unique per file)` };
  if (!note.trim() || !printableLine(note)) return { ok: false, error: "a short note, one line, is required" };
  if (model.items.length >= MAX_ITEMS) return { ok: false, error: `at most ${MAX_ITEMS} items` };
  const item: ZoneItem = { kind: d.kind, id: iid, note, points: d.points.map(([x, y]) => [x, y] as Cell) };
  return { ok: true, model: { ...model, items: [...model.items, item] } };
}

export function removeItem(model: ZonesModel, index: number): ZonesModel {
  return { ...model, items: model.items.filter((_, i) => i !== index) };
}

/** The comment lines from a textarea ("" = none). */
export function commentLines(text: string): string[] {
  return text === "" ? [] : text.replace(/\r\n?/g, "\n").replace(/\n$/, "").split("\n");
}

/** The model the backend read from a file (GET /flows/zones/file), checked before use. */
export function modelFrom(data: unknown, map: string): ZonesModel | null {
  if (!data || typeof data !== "object") return null;
  const d = data as Record<string, unknown>;
  if (d.map !== map || !Array.isArray(d.comment) || !Array.isArray(d.items)) return null;
  const comment = d.comment.filter((c): c is string => typeof c === "string");
  const items: ZoneItem[] = [];
  for (const it of d.items) {
    if (!it || typeof it !== "object") return null;
    const r = it as Record<string, unknown>;
    if ((r.kind !== "no_cross" && r.kind !== "no_enter") || typeof r.id !== "string" || typeof r.note !== "string" || !Array.isArray(r.points)) return null;
    const p = r.points.filter((c): c is Cell => Array.isArray(c) && c.length === 2 && c.every((v) => Number.isSafeInteger(v)));
    if (p.length !== r.points.length) return null;
    items.push({ kind: r.kind, id: r.id, note: r.note, points: p });
  }
  return { map, comment, items };
}

// --- the check route's reply (POST /flows/zones/check), as the panel shows it -------------------
export type ZonesItemCells = { kind: ZoneKind; id: string; note: string; points: Cell[]; cells: Cell[]; cell_count: number; truncated: boolean };
export type ZonesArea = { rows: string[]; walkable: number; zone_cells: number; cut_cells: number; main_cells: number; other_cells: number; grid: string };
export type ZonesCheck = {
  map: string;
  ok: boolean;
  error: string | null;
  sha256?: string;
  bytes?: number;
  shape: [number, number] | null;
  items?: ZonesItemCells[];
  area?: ZonesArea | null;
  review?: { reviewed_by: string; reviewed: string; delegation: string | null };
  committed?: { exists: boolean; path: string; ok: boolean; error: string | null; sha256?: string; same: boolean; review?: { reviewed_by: string; reviewed: string; delegation: string | null } };
  diff?: string;
  notes?: string[];
};
export type ZonesFile = {
  map: string;
  file: { exists: boolean; path: string; ok: boolean; error: string | null; sha256?: string; text?: string; review?: { reviewed_by: string; reviewed: string; delegation: string | null } };
  model: unknown;
  notes: string[];
};

/** The panel's lines for a check (text only; the loader's message exactly as it came). */
export function checkLines(c: ZonesCheck): { tone: "ok" | "error" | "info"; text: string }[] {
  const out: { tone: "ok" | "error" | "info"; text: string }[] = [];
  if (!c.ok) out.push({ tone: "error", text: c.error ?? "refused" });
  else {
    out.push({ tone: "ok", text: `the loader accepts it · sha256 ${c.sha256}` });
    for (const it of c.items ?? []) out.push({ tone: "info", text: `${it.kind} ${it.id}: closes ${it.cell_count} cell(s)` });
    if (c.area) {
      out.push({
        tone: "info",
        text: `search area (largest piece): ${c.area.main_cells} of ${c.area.walkable} walkable cells · closed by the zones ${c.area.zone_cells} · sealed off ${c.area.cut_cells} · other pieces ${c.area.other_cells}`,
      });
    }
  }
  if (c.committed) {
    const f = c.committed;
    out.push({
      tone: f.exists && !f.ok ? "error" : "info",
      text: !f.exists
        ? `${f.path}: no file yet (no zones: nothing changes in the runner)`
        : f.same
          ? `${f.path}: the same bytes (sha256 ${f.sha256?.slice(0, 12)})`
          : `${f.path}: differs (its sha256 ${f.sha256?.slice(0, 12)})${f.ok ? "" : ` · its loader verdict: ${f.error}`}`,
    });
  }
  for (const n of c.notes ?? []) out.push({ tone: "info", text: n });
  return out;
}
