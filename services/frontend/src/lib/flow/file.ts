// The flow FILE (docs/planning/flows-save-load.md section 1): what Save keeps, as a download or as
// a file in a GitHub folder, and what Load opens. Shared by /flows and /maps.
//
// Ported from MatPilot (MIT), src/lib/blocks/program-file.ts at 4022c87
// (https://github.com/lumduan/matpilot, Copyright (c) 2026 Sarat Sonsuk; the licence text is in
// components/flowfile/flowfile.css and THIRD_PARTY.md). Ours: the IR inside, the byte cap and NFC
// on names, the hostile-file checks below, the file meta, the shortcuts.
//
// A file on the way IN is HOSTILE (ADR-0020 7.1, as importer.ts): its size is checked before it is
// read (the callers, from File.size or GitHub's size) and again here, its bracket depth before
// JSON.parse, then the wrapper's fields one by one, then the IR goes through importFlow (the same
// checks as a bare IR file). The result is a SCRATCH flow: nothing on the page changes unless all of
// it passes. `python` is never read: it is made again from the flow (a derived field in a file is
// never trusted). The static data the page lints on (prefs KEYS.world: derived from rAthena and the
// client) is never written into a file: it must never reach GitHub (CLAUDE.md rule 4).
import type { Flow } from "./ir.ts";
import { MAX_JSON_DEPTH } from "./ir.ts";
import { importFlow, jsonDepth, sorted } from "./importer.ts";
import { KEYS, type StorageLike } from "./prefs.ts";
import { parseRepository, repositoryLabel, safePath } from "../github/repository.ts";

export const FLOW_FILE_FORMAT = "poring-lab-flow";
/** The newest version this page reads and writes. */
export const FLOW_FILE_VERSION = 1;
export const FLOW_FILE_EXTENSION = ".flow.json";
/** A flow file is a few kilobytes; anything larger is refused before it is read. */
export const FLOW_FILE_MAX_BYTES = 2_000_000;
/** A name: at most 60 characters (code points) AND 180 UTF-8 bytes (Thai is 3 bytes a letter;
 * git and some file systems limit bytes). */
export const NAME_MAX_CHARS = 60;
export const NAME_MAX_BYTES = 180;
export const SAVED_BY_MAX_CHARS = 40;
export const DEFAULT_FLOW_NAME = "My flow";

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);

// --- names ------------------------------------------------------------------------------------------
// Control characters (C0, DEL, C1), what Windows refuses in a file name (/ \ : * ? " < > |), and the
// bidirectional overrides and isolates (a name that DISPLAYS differently from its bytes).
const NAME_BAD = /[\u0000-\u001f\u007f-\u009f/\\:*?"<>|\u202a-\u202e\u2066-\u2069]+/g;
/** Device names Windows refuses with any extension: a class cloning the folder on Windows would fail. */
const WINDOWS_RESERVED = /^(con|prn|aux|nul|com[0-9]|lpt[0-9])$/i;

/** `text` without lone surrogates (they are not UTF-8; no regex lookbehind: older iOS Safari
 * refuses it when the page loads). */
function wellFormed(text: string): string {
  let out = "";
  for (const ch of text) {
    const cp = ch.codePointAt(0) ?? 0;
    if (cp < 0xd800 || cp > 0xdfff) out += ch;
  }
  return out;
}

/** UTF-8 bytes of a well-formed string. */
export function utf8Bytes(text: string): number {
  let n = 0;
  for (const ch of text) {
    const cp = ch.codePointAt(0) ?? 0;
    n += cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4;
  }
  return n;
}

/** The user-perceived characters (graphemes) of `text`: a Thai letter keeps its vowel and tone
 * marks when a name is cut. Code points where Intl.Segmenter is missing. */
function graphemes(text: string): Iterable<string> {
  if (typeof Intl !== "undefined" && typeof Intl.Segmenter === "function") {
    const seg = new Intl.Segmenter(undefined, { granularity: "grapheme" });
    return (function* () {
      for (const s of seg.segment(text)) yield s.segment;
    })();
  }
  return Array.from(text);
}

/** The longest start of `text`, cut between graphemes, of at most `chars` code points and `bytes`
 * UTF-8 bytes. */
export function fitText(text: string, chars: number, bytes: number): string {
  let out = "";
  let c = 0;
  let b = 0;
  for (const g of graphemes(text)) {
    const gc = Array.from(g).length;
    const gb = utf8Bytes(g);
    if (c + gc > chars || b + gb > bytes) break;
    out += g;
    c += gc;
    b += gb;
  }
  return out;
}

/**
 * A name that is safe as a file name on every system and on GitHub: NFC; no control characters, no
 * `/ \ : * ? " < > |`, no bidi overrides, no leading dots; spaces collapsed; at most 60 characters
 * and 180 UTF-8 bytes; not a Windows device name. Letters in any script (Thai too) and spaces stay.
 * `''` when nothing is left.
 */
export function cleanFlowName(name: string): string {
  const text = wellFormed(name.slice(0, 4 * NAME_MAX_BYTES)) // a hostile 2 MB name costs no more than this
    .normalize("NFC")
    .replace(NAME_BAD, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^\.+/, "")
    .trim();
  let out = fitText(text, NAME_MAX_CHARS, NAME_MAX_BYTES).trim().normalize("NFC");
  if (WINDOWS_RESERVED.test(out)) out = `${out}_`;
  return out;
}

/** "Farm loop" -> "Farm loop.flow.json"; an empty name falls back to `fallback`, then "My flow". */
export function flowFileName(name: string, fallback = ""): string {
  return `${cleanFlowName(name) || cleanFlowName(fallback) || DEFAULT_FLOW_NAME}${FLOW_FILE_EXTENSION}`;
}

export function isFlowFileName(fileName: string): boolean {
  return fileName.toLowerCase().endsWith(FLOW_FILE_EXTENSION) && fileName.length > FLOW_FILE_EXTENSION.length;
}

/** "Farm loop.flow.json" -> "Farm loop"; other names lose their last extension. */
export function flowNameFromFileName(fileName: string): string {
  const base = fileName.split(/[/\\]/).pop() ?? fileName;
  const stem = isFlowFileName(base) ? base.slice(0, -FLOW_FILE_EXTENSION.length) : base.replace(/\.[^.]*$/, "");
  return cleanFlowName(stem) || DEFAULT_FLOW_NAME;
}

/** Who saved a file, as they typed their name: one line, no control characters, 40 characters. */
export function cleanSavedBy(text: string): string {
  const one = wellFormed(text.slice(0, 400))
    .normalize("NFC")
    .replace(/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return fitText(one, SAVED_BY_MAX_CHARS, 4 * SAVED_BY_MAX_CHARS).trim();
}

// --- writing ------------------------------------------------------------------------------------------
export type FlowFileParts = {
  readonly name: string;
  readonly savedBy: string;
  /** ISO 8601, or "" when unknown. */
  readonly savedAt: string;
  /** The Python the flow engine made from the flow ("" when it was not reachable). */
  readonly python: string;
  readonly flow: Flow;
};

const lines = (code: string): string[] => {
  const text = code.replace(/\n$/, "");
  return text === "" ? [] : text.split("\n");
};

/** The file's text: pretty JSON, the flow's keys in canonical order and the Python as lines, so a
 * diff on GitHub reads well. EXACTLY these seven fields: never the static data (the world). */
export function serializeFlowFile(p: FlowFileParts): string {
  const file = {
    format: FLOW_FILE_FORMAT,
    version: FLOW_FILE_VERSION,
    name: cleanFlowName(p.name) || cleanFlowName(p.flow.name) || DEFAULT_FLOW_NAME,
    savedBy: cleanSavedBy(p.savedBy),
    savedAt: p.savedAt,
    python: lines(p.python),
    flow: sorted(p.flow),
  };
  return `${JSON.stringify(file, null, 2)}\n`;
}

// --- reading --------------------------------------------------------------------------------------------
export type ParsedFlowFile =
  | { readonly ok: true; readonly flow: Flow; readonly name: string; readonly savedBy: string; readonly savedAt: string; readonly bare: boolean }
  | { readonly ok: false; readonly errors: string[] };

/**
 * Reads a saved flow file, or a bare IR file (a download from before 2026-11-12). `fallbackName`
 * names it when the file does not (the file's name without its extension). Nothing is evaluated;
 * the flow is checked as importFlow checks an imported file, and MW1's schema checks it again at
 * the next lint.
 */
export function parseFlowFile(text: string, fallbackName: string): ParsedFlowFile {
  const bytes = new TextEncoder().encode(text).length;
  if (bytes > FLOW_FILE_MAX_BYTES) return { ok: false, errors: [`the file is ${bytes} bytes; a flow file is at most ${FLOW_FILE_MAX_BYTES}`] };
  if (jsonDepth(text) > MAX_JSON_DEPTH + 1) return { ok: false, errors: [`nested deeper than ${MAX_JSON_DEPTH}`] };
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return { ok: false, errors: ["this file is not a flow (it is not JSON)"] };
  }
  if (!isObj(data)) return { ok: false, errors: ["this file is not a flow (a flow file is a JSON object)"] };
  const fallback = cleanFlowName(fallbackName);
  if (!("format" in data)) {
    if (!("ir" in data)) return { ok: false, errors: ["this file is not a poring-lab flow"] };
    const r = importFlow(text); // a bare IR file, as Save wrote it before 2026-11-12
    if (!r.ok) return r;
    return { ok: true, flow: r.flow, name: fallback || cleanFlowName(r.flow.name) || DEFAULT_FLOW_NAME, savedBy: "", savedAt: "", bare: true };
  }
  if (data.format !== FLOW_FILE_FORMAT) return { ok: false, errors: ["this file is not a poring-lab flow"] };
  const v = data.version;
  if (typeof v !== "number" || !Number.isInteger(v) || v < 1) return { ok: false, errors: ["version: a whole number from 1"] };
  if (v > FLOW_FILE_VERSION) return { ok: false, errors: ["this flow was saved by a newer poring-lab: pull the update, then open it again"] };
  const errors: string[] = [];
  for (const k of ["name", "savedBy", "savedAt"] as const) {
    if (data[k] !== undefined && typeof data[k] !== "string") errors.push(`${k}: text`);
  }
  if (!isObj(data.flow)) errors.push("flow: missing (a flow file carries its flow)");
  if (errors.length) return { ok: false, errors };
  // `python` is not read: it is made again from the flow
  const r = importFlow(JSON.stringify(data.flow));
  if (!r.ok) return { ok: false, errors: r.errors.map((e) => `flow: ${e}`) };
  const name = typeof data.name === "string" ? cleanFlowName(data.name) : "";
  return {
    ok: true,
    flow: r.flow,
    name: name || fallback || cleanFlowName(r.flow.name) || DEFAULT_FLOW_NAME,
    savedBy: typeof data.savedBy === "string" ? cleanSavedBy(data.savedBy) : "",
    savedAt: savedAtOf(data.savedAt),
    bare: false,
  };
}

/** A saved time that parses, else "". */
function savedAtOf(v: unknown): string {
  if (typeof v !== "string" || v.length > 40) return "";
  return Number.isNaN(new Date(v).getTime()) ? "" : v;
}

// --- the file meta: the name it was saved as, and the GitHub file it came from --------------------------
/** The GitHub file a flow was loaded from or last saved to: a save replaces it only while its sha is
 * this one (flows-save-load.md section 3, compare-and-swap). */
export type GitHubLink = { readonly repository: string; readonly path: string; readonly sha: string };
export type FileMeta = { readonly name: string; readonly link: GitHubLink | null };

const SHA = /^[0-9a-f]{40}(?:[0-9a-f]{24})?$/;

export function newFileMeta(flow: Flow): FileMeta {
  return { name: cleanFlowName(flow.name) || DEFAULT_FLOW_NAME, link: null };
}

function readLink(v: unknown): GitHubLink | null {
  if (!isObj(v) || typeof v.repository !== "string" || typeof v.path !== "string" || typeof v.sha !== "string") return null;
  const repo = parseRepository(v.repository);
  if (!repo || repositoryLabel(repo) !== v.repository || !safePath(v.path) || !SHA.test(v.sha)) return null;
  return { repository: v.repository, path: v.path, sha: v.sha };
}

/** This browser's meta for its last flow (both pages share it), checked like anything stored; a
 * meta written for another flow, or one that does not parse, gives the defaults. */
export function readFileMeta(store: StorageLike | null, flow: Flow): FileMeta {
  try {
    const v: unknown = JSON.parse(store?.getItem(KEYS.file) ?? "null");
    if (!isObj(v) || v.flow !== flow.name || typeof v.name !== "string") return newFileMeta(flow);
    return { name: cleanFlowName(v.name) || newFileMeta(flow).name, link: readLink(v.link) };
  } catch {
    return newFileMeta(flow);
  }
}

/** Store the meta beside the flow it belongs to (the flow's IR name tags it). */
export function writeFileMeta(store: StorageLike | null, meta: FileMeta, flow: Flow): boolean {
  try {
    if (!store) return false;
    store.setItem(KEYS.file, JSON.stringify({ flow: flow.name, name: meta.name, link: meta.link }));
    return true;
  } catch {
    return false;
  }
}

// --- on this computer ------------------------------------------------------------------------------------
type Anchor = { href: string; download: string; rel: string; click(): void; remove(): void };
export type DownloadDeps = {
  readonly make: () => Anchor;
  readonly attach: (a: Anchor) => void;
  readonly urls: { createObjectURL(b: Blob): string; revokeObjectURL(u: string): void };
  readonly later: (fn: () => void, ms: number) => void;
};
export const REVOKE_AFTER_MS = 10_000;

function browserDownload(): DownloadDeps {
  return {
    make: () => document.createElement("a"),
    attach: (a) => document.body.append(a as HTMLAnchorElement),
    urls: URL,
    later: (fn, ms) => void setTimeout(fn, ms),
  };
}

/** Saves `text` through the browser's download, usually into Downloads (ported from MatPilot's
 * src/hooks/downloadFile.ts). The object URL is revoked 10 s later: some browsers read it after
 * click() returns. */
export function downloadText(fileName: string, text: string, deps: DownloadDeps = browserDownload()): void {
  const url = deps.urls.createObjectURL(new Blob([text], { type: "application/json" }));
  const a = deps.make();
  a.href = url;
  a.download = fileName;
  a.rel = "noopener";
  deps.attach(a);
  a.click();
  a.remove();
  deps.later(() => deps.urls.revokeObjectURL(url), REVOKE_AFTER_MS);
}

// --- the keyboard ----------------------------------------------------------------------------------------
export type KeyLike = {
  readonly key: string;
  readonly code?: string;
  readonly ctrlKey: boolean;
  readonly metaKey: boolean;
  readonly altKey: boolean;
  readonly shiftKey: boolean;
  readonly isComposing?: boolean;
  readonly target: unknown;
};

/** Typing into a field: the shortcuts leave it alone. */
function typing(target: unknown): boolean {
  if (!target || typeof target !== "object") return false;
  const el = target as { tagName?: unknown; isContentEditable?: unknown };
  const tag = typeof el.tagName === "string" ? el.tagName.toUpperCase() : "";
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable === true;
}

/** Ctrl/⌘+S opens Save and Ctrl/⌘+O opens Load (as MatPilot's ADR 0011 decision 10), not while
 * typing in a field. On a Thai (or any non-Latin) layout the letter comes from the key's place. */
export function fileShortcut(e: KeyLike): "save" | "load" | null {
  if (e.altKey || e.shiftKey || e.isComposing || !(e.ctrlKey || e.metaKey)) return null;
  // (Chrome's autofill sends keydown events without a key)
  const k = typeof e.key === "string" ? e.key : "";
  const key = k.length === 1 && /[a-z]/i.test(k) ? k.toLowerCase() : e.code === "KeyS" ? "s" : e.code === "KeyO" ? "o" : "";
  const which = key === "s" ? "save" : key === "o" ? "load" : null;
  return which && !typing(e.target) ? which : null;
}
