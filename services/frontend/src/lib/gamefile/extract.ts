// What each kind of game file says about servers. All linear scans over bounded input; no regex on
// file text, nothing executed, nothing decrypted.

import { u16, u32 } from "./grf.ts";
import { parseEndpoint, printableRuns, scanText, validHost, type Role } from "./endpoint.ts";

export type Add = (host: string, port: number | null, role: Role) => void;

/** Bytes as ASCII text: tab/newline/CR and printable ASCII kept, every other byte -> "?". The
 * settings files are EUC-KR/TIS-620; the server names in them are ASCII. */
export function asciiText(b: Uint8Array): string {
  const parts: string[] = [];
  const CHUNK = 8192;
  for (let at = 0; at < b.length; at += CHUNK) {
    const codes = Array.from(b.subarray(at, at + CHUNK), (c) =>
      (c >= 0x20 && c <= 0x7e) || c === 0x09 || c === 0x0a || c === 0x0d ? c : 0x3f);
    parts.push(String.fromCharCode(...codes));
  }
  return parts.join("");
}

/** A label from the file (a server's display name), safe and short: letters, digits, space and
 * . _ - ( ) only, CUT at the first other character -- so a crafted name keeps only its harmless
 * head ("Test server <img onerror=...>" -> "Test server"). It is rendered as text anyway. */
export function safeLabel(raw: string, max = 60): string {
  let out = "";
  for (const c of raw) {
    if (out.length >= max) break;
    const ok = (c >= "a" && c <= "z") || (c >= "A" && c <= "Z") || (c >= "0" && c <= "9") || " ._-()".includes(c);
    if (!ok) break;
    out += c;
  }
  return out.replace(/ {2,}/g, " ").trim(); // runs only on <= max characters
}

const MAX_BLOCKS = 64;
const MAX_VALUE = 300;

/** The text between <tag> and </tag> inside one (lower-cased) block, or null. */
function tagValue(low: string, orig: string, tag: string): string | null {
  const open = `<${tag}>`;
  const start = low.indexOf(open);
  if (start < 0) return null;
  const from = start + open.length;
  const end = low.indexOf(`</${tag}>`, from);
  if (end < 0 || end - from > MAX_VALUE) return null;
  return orig.slice(from, end).trim();
}

/** A URL-ish value ("http://www.example.com/x") -> its host and port, under the grammar. */
function hostOfUrl(value: string): { host: string; port: number | null } | null {
  let v = value.trim();
  const scheme = v.indexOf("://");
  if (scheme >= 0 && scheme <= 10) v = v.slice(scheme + 3);
  let cut = v.length;
  for (const c of ["/", "?", "#"]) {
    const i = v.indexOf(c);
    if (i >= 0 && i < cut) cut = i;
  }
  return parseEndpoint(v.slice(0, cut));
}

/** clientinfo.xml / sclientinfo.xml: every <connection>'s <address> + <port> (the login server),
 * and its <registrationweb> (a web page). Returns the first <display> name, made safe. */
export function fromClientinfo(text: string, add: Add): { display: string | null; blocks: number } {
  const low = text.toLowerCase();
  const blocks: [number, number][] = [];
  let at = 0;
  while (blocks.length < MAX_BLOCKS) {
    const s = low.indexOf("<connection>", at);
    if (s < 0) break;
    const e = low.indexOf("</connection>", s);
    if (e < 0) break;
    blocks.push([s, e]);
    at = e + 13;
  }
  if (blocks.length === 0) blocks.push([0, text.length]); // a file without <connection> blocks
  let display: string | null = null;
  for (const [s, e] of blocks) {
    const low1 = low.slice(s, e);
    const orig1 = text.slice(s, e);
    const address = tagValue(low1, orig1, "address");
    const port = tagValue(low1, orig1, "port");
    if (address !== null) {
      const ep = parseEndpoint(port !== null && !address.includes(":") ? `${address}:${port}` : address);
      if (ep) add(ep.host, ep.port, "login");
    }
    const web = tagValue(low1, orig1, "registrationweb");
    if (web) {
      const ep = hostOfUrl(web);
      if (ep) add(ep.host, ep.port, "other");
    }
    const name = tagValue(low1, orig1, "display");
    if (display === null && name) display = safeLabel(name) || null;
  }
  return { display, blocks: blocks.length };
}

/** A .lub (compiled Lua 5.1, or plain Lua text): printable strings in order. A value right after
 * a key containing "assist" is the assist/web service (AssistAddr); a bare host is taken only
 * right after a key that names an address ("...Addr"). */
export function fromLub(bytes: Uint8Array, add: Add): void {
  let prev = "";
  for (const run of printableRuns(bytes)) {
    const low = run.toLowerCase();
    const role: Role = low.includes("assist") || prev.includes("assist") ? "assist-web" : "other";
    const eps = scanText(run);
    for (const ep of eps) add(ep.host, ep.port, role);
    if (eps.length === 0 && prev.includes("addr")) {
      const host = validHost(run);
      if (host) add(host, null, role);
    }
    prev = low.length <= 64 ? low : "";
  }
}

const PACKER_SECTIONS = new Set([
  ".themida", ".winlice", ".vmp0", ".vmp1", ".vmp2", "upx0", "upx1", "upx2", ".enigma1",
  ".enigma2", ".aspack", ".adata", ".mpress1", ".mpress2", ".petite", ".nsp0", ".nsp1", ".perplex",
]);
const ENTROPY_PACKED = 7.2; // bits per byte; compiled code is ~6-6.7, packed or encrypted ~7.5-8
const ENTROPY_MIN_BYTES = 64 * 1024;
const MAX_SECTIONS = 96;

export function entropy(b: Uint8Array): number {
  if (b.length === 0) return 0;
  const counts = new Uint32Array(256);
  for (let i = 0; i < b.length; i++) counts[b[i]]++;
  let h = 0;
  for (const n of counts) {
    if (n === 0) continue;
    const p = n / b.length;
    h -= p * Math.log2(p);
  }
  return h;
}

/** Why a Windows exe is protected (packed/encrypted code), or null; also whether it IS one. */
export function exeProtection(b: Uint8Array): { pe: boolean; protectedBy: string | null } {
  if (b.length < 0x40 || b[0] !== 0x4d || b[1] !== 0x5a) return { pe: false, protectedBy: null };
  const pe = u32(b, 0x3c);
  if (pe + 24 > b.length || b[pe] !== 0x50 || b[pe + 1] !== 0x45 || b[pe + 2] !== 0 || b[pe + 3] !== 0) {
    return { pe: false, protectedBy: null };
  }
  const count = Math.min(u16(b, pe + 6), MAX_SECTIONS);
  let at = pe + 24 + u16(b, pe + 20);
  for (let i = 0; i < count && at + 40 <= b.length; i++, at += 40) {
    let name = "";
    for (let j = 0; j < 8 && b[at + j] !== 0; j++) name += String.fromCharCode(b[at + j]);
    const rawSize = u32(b, at + 16);
    const rawAt = u32(b, at + 20);
    const exec = (u32(b, at + 36) & 0x20000000) !== 0;
    const shown = safeLabel(name, 8);
    if (PACKER_SECTIONS.has(name.toLowerCase())) return { pe: true, protectedBy: `a "${shown}" section` };
    if (name.trim() === "" && rawSize > 0) return { pe: true, protectedBy: "sections with blank names (Themida-style)" };
    if (exec && rawSize >= ENTROPY_MIN_BYTES && rawAt < b.length) {
      const h = entropy(b.subarray(rawAt, Math.min(b.length, rawAt + rawSize)));
      if (h >= ENTROPY_PACKED) return { pe: true, protectedBy: `packed code (${h.toFixed(1)} bits per byte)` };
    }
  }
  return { pe: true, protectedBy: null };
}

/** UTF-16LE printable runs (Windows "wide" strings), linear; overlong runs dropped whole. */
export function* wideRuns(b: Uint8Array, minLen = 6, maxLen = 512): Generator<string> {
  let run: number[] = [];
  let over = false;
  for (let i = 0; i < b.length; i += 2) {
    const c = b[i];
    const hi = i + 1 < b.length ? b[i + 1] : 1;
    if (hi === 0 && c >= 0x20 && c <= 0x7e) {
      if (run.length < maxLen) run.push(c);
      else over = true;
    } else {
      if (!over && run.length >= minLen) yield String.fromCharCode(...run);
      run = [];
      over = false;
    }
  }
  if (!over && run.length >= minLen) yield String.fromCharCode(...run);
}

/** Visible strings of an UNPROTECTED exe: "host:port" only (bare names are mostly file names). */
export function fromExe(b: Uint8Array, add: Add): void {
  for (const runs of [printableRuns(b), wideRuns(b)]) {
    let prev = "";
    for (const run of runs) {
      const low = run.toLowerCase();
      const role: Role = low.includes("assist") || prev.includes("assist") ? "assist-web" : "other";
      for (const ep of scanText(run)) add(ep.host, ep.port, role);
      prev = low.length <= 64 ? low : "";
    }
  }
}
