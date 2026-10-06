// GRF (version 0x200) -- only the header and the file table, then only the entries that name
// servers. The layout (public knowledge, e.g. rAthena's grfio.cpp):
//   header, 46 bytes: "Master of Magic\0" (16) | key (14) | table offset u32 | seed u32 |
//                     count u32 | version u32         (offsets are relative to byte 46)
//   table at 46 + offset: compressed size u32 | inflated size u32 | zlib data
//   entry: name (NUL-terminated) | zsize u32 | zsize aligned u32 | size u32 | flags u8 | offset u32
//   flags: 0x01 a file (else a directory), 0x02 / 0x04 encrypted (DES variants).
// Encrypted entries are NOT decrypted (Batt: MIXCRYPT stays study-only and private): they are
// reported as "encrypted, can't read" and skipped. Every number read from the file is checked
// against the file's size and the limits before it is used.

export type Reader = (offset: number, length: number) => Promise<Uint8Array>;

export const GRF_HEADER = 46;
const MAGIC = "Master of Magic";
export const FLAG_FILE = 0x01;
export const FLAG_ENCRYPTED = 0x02 | 0x04;

export type Target = "clientinfo" | "externalsettings";

export interface GrfEntry {
  name: string; // ASCII, lower case, "\" separators; other bytes became "?"
  target: Target;
  zsize: number;
  size: number;
  flags: number;
  offset: number;
}

export function u32(b: Uint8Array, o: number): number {
  return (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)) >>> 0;
}

export function u16(b: Uint8Array, o: number): number {
  return b[o] | (b[o + 1] << 8);
}

export function isGrf(head: Uint8Array): boolean {
  if (head.length < GRF_HEADER) return false;
  for (let i = 0; i < MAGIC.length; i++) if (head[i] !== MAGIC.charCodeAt(i)) return false;
  return true;
}

const LUA_DIR = "data\\luafiles514\\lua files\\service_";

/** The entries worth reading, from their (lower-case, "\") path. Nothing else is ever inflated. */
export function targetOf(name: string): Target | null {
  if (name === "data\\clientinfo.xml" || name === "data\\sclientinfo.xml") return "clientinfo";
  if (name.startsWith(LUA_DIR) && name.endsWith(".lub")) {
    const rest = name.slice(LUA_DIR.length); // "korea\externalsettings_kr.lub"
    const slash = rest.indexOf("\\");
    if (slash > 0 && rest.indexOf("\\", slash + 1) < 0 && rest.startsWith("externalsettings", slash + 1)) {
      return "externalsettings";
    }
  }
  return null;
}

/** Bytes [from, to) as lower-case ASCII with "/" -> "\"; any other byte becomes "?". */
function pathText(b: Uint8Array, from: number, to: number): string {
  let s = "";
  for (let i = from; i < to; i++) {
    let c = b[i];
    if (c >= 0x41 && c <= 0x5a) c += 0x20;
    else if (c === 0x2f) c = 0x5c;
    s += c >= 0x20 && c <= 0x7e ? String.fromCharCode(c) : "?";
  }
  return s;
}

const lower = (c: number): number => (c >= 0x41 && c <= 0x5a ? c + 0x20 : c);

/** ".xml" / ".lub" at the end of a name, checked on the bytes (the cheap filter that keeps a
 * 500 000-entry table from being turned into strings). */
function maybeTarget(b: Uint8Array, from: number, to: number): boolean {
  if (to - from < 12 || b[to - 4] !== 0x2e) return false;
  const [x, y, z] = [lower(b[to - 3]), lower(b[to - 2]), lower(b[to - 1])];
  return (x === 0x78 && y === 0x6d && z === 0x6c) || (x === 0x6c && y === 0x75 && z === 0x62);
}

export interface TableLimits {
  maxEntries: number;
  maxNameLen: number;
  maxTargets: number;
}

export interface Table {
  targets: GrfEntry[];
  entries: number;
  stopped: string | null; // why the walk ended early, in plain words
}

/** Walk an inflated table once, linearly. A bad record ends the walk; what was read is kept. */
export function walkTable(t: Uint8Array, limits: TableLimits): Table {
  const targets: GrfEntry[] = [];
  let entries = 0;
  let pos = 0;
  while (pos < t.length) {
    if (entries >= limits.maxEntries) {
      return { targets, entries, stopped: `the file table has more than ${limits.maxEntries} entries; read the first ${limits.maxEntries} only` };
    }
    const stop = Math.min(t.length, pos + limits.maxNameLen);
    let end = pos;
    while (end < stop && t[end] !== 0) end++;
    if (end >= stop || end + 18 > t.length) {
      return { targets, entries, stopped: "the file table is damaged; read up to the damage only" };
    }
    const rec = end + 1;
    const flags = t[rec + 12];
    entries++;
    if (flags & FLAG_FILE && maybeTarget(t, pos, end)) {
      const name = pathText(t, pos, end);
      const target = targetOf(name);
      if (target) {
        if (targets.length >= limits.maxTargets) {
          return { targets, entries, stopped: `more than ${limits.maxTargets} settings files; read the first ${limits.maxTargets} only` };
        }
        targets.push({ name, target, zsize: u32(t, rec), size: u32(t, rec + 8), flags, offset: u32(t, rec + 13) });
      }
    }
    pos = rec + 17;
  }
  return { targets, entries, stopped: null };
}

export type Header =
  | { ok: true; tableAt: number; zsize: number; size: number }
  | { ok: false; why: string };

/** The header and the table's own 8-byte header, checked against the file size and limits. */
export async function readHeader(
  read: Reader,
  fileSize: number,
  limits: { tableMaxCompressed: number; tableMaxInflated: number },
): Promise<Header> {
  const head = await read(0, GRF_HEADER);
  if (!isGrf(head)) return { ok: false, why: "This is not a GRF file." };
  const version = u32(head, 42);
  if (version !== 0x200) {
    const v = `0x${version.toString(16)}`;
    return { ok: false, why: `This GRF is version ${v}; the finder reads version 0x200 (the usual one) only.` };
  }
  const tableAt = GRF_HEADER + u32(head, 30);
  if (tableAt + 8 > fileSize) return { ok: false, why: "The GRF's file table points outside the file: the file is damaged." };
  const th = await read(tableAt, 8);
  const zsize = u32(th, 0);
  const size = u32(th, 4);
  if (zsize > fileSize - tableAt - 8) return { ok: false, why: "The GRF's file table is cut off: the file is damaged." };
  const mb = (n: number) => `${Math.round(n / 2 ** 20)} MB`;
  if (zsize > limits.tableMaxCompressed || size > limits.tableMaxInflated) {
    return { ok: false, why: `The GRF's file table is too large (${mb(Math.max(zsize, size))}; the limit is ${mb(limits.tableMaxInflated)}).` };
  }
  return { ok: true, tableAt: tableAt + 8, zsize, size };
}
