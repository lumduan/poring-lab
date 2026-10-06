// "Find servers from a game file" (Batt, 2026-10-06): one dropped file in, endpoints out. Runs in a
// Web Worker (worker.ts) and reads the file BY SLICES through a Reader, so a 3 GB data.grf costs
// its header, its file table and a few small entries. Nothing is uploaded, stored or executed.
// Every number in the file is hostile until checked; every limit below is a hard stop.

import { fromClientinfo, fromExe, fromLub, exeProtection, asciiText } from "./extract.ts";
import { FLAG_ENCRYPTED, isGrf, readHeader, walkTable, type Reader } from "./grf.ts";
import { inflateCapped } from "./inflate.ts";
import { ignorable, isLan, MAX_FOUND, MAX_SOURCES, type Found, type Role } from "./endpoint.ts";

const MB = 2 ** 20;

export const LIMITS = {
  fileMaxBytes: 5 * 2 ** 30, // a GRF's offsets are 32-bit: anything bigger is not one we read
  tableMaxCompressed: 64 * MB,
  tableMaxInflated: 128 * MB,
  maxEntries: 2_000_000,
  maxNameLen: 256,
  maxTargets: 64,
  entryMaxInflated: 1 * MB, // clientinfo.xml / externalsettings_*.lub are a few KB
  totalMaxInflated: 8 * MB,
  textMaxBytes: 1 * MB, // a dropped .xml / .lub
  exeMaxBytes: 128 * MB,
  timeoutMs: 20_000, // the worker is terminated after this (run.ts)
};
export type Limits = typeof LIMITS;

export type Kind = "grf" | "clientinfo" | "lub" | "exe" | "unknown";

export interface ScanResult {
  file: string;
  kind: Kind;
  found: Found[];
  notes: string[]; // plain words: encrypted entries, a protected exe, a limit that was hit
  error: string | null; // nothing could be read, and why
  display: string | null; // the server's display name from clientinfo, made safe
  stats: { entries: number; read: number; encrypted: number; inflated: number; ignored: number };
}

export const NOT_KNOWN =
  "The finder does not know this file. Drop a data.grf (or another .grf), clientinfo.xml / " +
  "sclientinfo.xml, an externalsettings .lub, or the game's .exe.";
export const PROTECTED = "This exe is protected, so its strings can't be read. Drop its data.grf instead.";

/** A file or entry name for display: no control characters, at most `max` characters. */
export function safeName(raw: string, max = 100): string {
  let out = "";
  for (const c of raw) {
    if (out.length >= max) return `${out}…`;
    const code = c.codePointAt(0) ?? 0;
    out += code < 0x20 || (code >= 0x7f && code < 0xa0) || code === 0x2028 || code === 0x2029 ? "?" : c;
  }
  return out;
}

const ROLE_RANK: Record<Role, number> = { login: 0, "assist-web": 1, other: 2 };

class Collector {
  found = new Map<string, Found>();
  ignored = 0;

  add(host: string, port: number | null, role: Role, source: string): void {
    if (ignorable(host)) {
      this.ignored++;
      return;
    }
    const key = port === null ? host : `${host}:${port}`;
    const have = this.found.get(key);
    if (have) {
      if (ROLE_RANK[role] < ROLE_RANK[have.role]) have.role = role;
      if (have.sources.length < MAX_SOURCES && !have.sources.includes(source)) have.sources.push(source);
      return;
    }
    if (this.found.size >= MAX_FOUND) return;
    this.found.set(key, { host, port, role, sources: [source], lan: isLan(host) });
  }

  list(): Found[] {
    return [...this.found.values()].sort((a, b) => ROLE_RANK[a.role] - ROLE_RANK[b.role]);
  }
}

/** A result that read nothing, with the reason. */
export function failed(file: string, error: string): ScanResult {
  return { ...empty(safeName(file), "unknown"), error };
}

function empty(file: string, kind: Kind): ScanResult {
  return {
    file, kind, found: [], notes: [], error: null, display: null,
    stats: { entries: 0, read: 0, encrypted: 0, inflated: 0, ignored: 0 },
  };
}

function ext(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot + 1).toLowerCase();
}

async function scanGrf(read: Reader, size: number, r: ScanResult, c: Collector, L: Limits): Promise<void> {
  const head = await readHeader(read, size, L);
  if (!head.ok) {
    r.error = head.why;
    return;
  }
  const table = await inflateCapped(await read(head.tableAt, head.zsize), head.size);
  if (!table.ok) {
    r.error = table.why === "too_big"
      ? "The GRF's file table unpacks to more than it says: refused (it may be a decompression bomb)."
      : "The GRF's file table is damaged.";
    return;
  }
  const walk = walkTable(table.bytes, L);
  r.stats.entries = walk.entries;
  if (walk.stopped) r.notes.push(`Stopped early: ${walk.stopped}.`);
  if (walk.targets.length === 0) {
    r.notes.push("No clientinfo.xml, sclientinfo.xml or externalsettings .lub in this GRF.");
    return;
  }
  const encrypted: string[] = [];
  for (const e of walk.targets) {
    const source = `${r.file}: ${e.name}`;
    if (e.flags & FLAG_ENCRYPTED) {
      encrypted.push(e.name);
      continue;
    }
    if (e.size === 0 || e.zsize === 0) continue;
    if (e.size > L.entryMaxInflated || e.zsize > 2 * L.entryMaxInflated) {
      r.notes.push(`${e.name}: larger than ${L.entryMaxInflated / MB} MB; a real settings file is a few KB. Skipped.`);
      continue;
    }
    if (r.stats.inflated + e.size > L.totalMaxInflated) {
      r.notes.push(`Stopped early: more than ${L.totalMaxInflated / MB} MB of settings files.`);
      break;
    }
    const at = 46 + e.offset;
    if (at + e.zsize > size) {
      r.notes.push(`${e.name}: points outside the file (damaged). Skipped.`);
      continue;
    }
    const data = await inflateCapped(await read(at, e.zsize), e.size);
    if (!data.ok) {
      r.notes.push(data.why === "too_big"
        ? `${e.name}: unpacks to more than it says; refused (it may be a decompression bomb).`
        : `${e.name}: damaged, can't read. Skipped.`);
      continue;
    }
    r.stats.read++;
    r.stats.inflated += data.bytes.length;
    const add = (h: string, p: number | null, role: Role) => c.add(h, p, role, source);
    if (e.target === "clientinfo") {
      const info = fromClientinfo(asciiText(data.bytes), add);
      r.display ??= info.display;
    } else {
      fromLub(data.bytes, add);
    }
  }
  r.stats.encrypted = encrypted.length;
  if (encrypted.length > 0) {
    const shown = encrypted.slice(0, 3).join(", ");
    const more = encrypted.length > 3 ? ` and ${encrypted.length - 3} more` : "";
    r.notes.push(`Encrypted, can't read (skipped): ${shown}${more}.`);
  }
}

/** Scan one file. Never throws: a failure is a result with `error` set. */
export async function scanSource(read: Reader, rawName: string, size: number, L: Limits = LIMITS): Promise<ScanResult> {
  const file = safeName(rawName);
  const r = empty(file, "unknown");
  const c = new Collector();
  try {
    if (size > L.fileMaxBytes) {
      r.error = `This file is too large (${Math.round(size / 2 ** 30)} GB).`;
      return r;
    }
    const head = await read(0, Math.min(size, 64));
    const add = (h: string, p: number | null, role: Role) => c.add(h, p, role, file);
    if (isGrf(head)) {
      r.kind = "grf";
      await scanGrf(read, size, r, c, L);
    } else if (head[0] === 0x4d && head[1] === 0x5a) {
      r.kind = "exe";
      if (size > L.exeMaxBytes) {
        r.error = `This exe is larger than ${L.exeMaxBytes / MB} MB. Drop its data.grf instead.`;
      } else {
        const bytes = await read(0, size);
        const pe = exeProtection(bytes);
        if (!pe.pe) r.error = "This looks like an exe but is not a valid Windows program.";
        else if (pe.protectedBy) r.error = `${PROTECTED} (Found: ${pe.protectedBy}.)`;
        else fromExe(bytes, add);
      }
    } else {
      const e = ext(rawName);
      const lua = head[0] === 0x1b && head[1] === 0x4c && head[2] === 0x75 && head[3] === 0x61; // "\x1bLua"
      if (!lua && e !== "xml" && e !== "lub") {
        r.error = NOT_KNOWN;
      } else if (size > L.textMaxBytes) {
        r.error = `This file is larger than ${L.textMaxBytes / MB} MB; a real settings file is a few KB.`;
      } else if (lua || e === "lub") {
        r.kind = "lub";
        fromLub(await read(0, size), add);
      } else {
        r.kind = "clientinfo";
        r.display = fromClientinfo(asciiText(await read(0, size)), add).display;
      }
    }
  } catch {
    r.error = r.error ?? "The file could not be read (damaged, or the browser refused to read it).";
  }
  r.found = c.list();
  r.stats.ignored = c.ignored;
  if (c.ignored > 0) {
    r.notes.push(`${c.ignored} address(es) point to this computer (e.g. 127.0.0.1): nothing to allow or block.`);
  }
  if (!r.error && r.found.length === 0 && r.notes.length === 0) r.notes.push("No server addresses found.");
  return r;
}

/** A Reader over a browser File: slices only, never the whole file unless asked for it. */
export function fileReader(file: Blob): Reader {
  return async (offset, length) => new Uint8Array(await file.slice(offset, offset + length).arrayBuffer());
}

/** A Reader over bytes in memory (tests). */
export function bytesReader(bytes: Uint8Array): Reader {
  return async (offset, length) => bytes.subarray(offset, offset + length);
}
