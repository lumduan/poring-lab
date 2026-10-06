// Endpoints found in a dropped game file (Batt, 2026-10-06: "Find servers from a game file").
// EVERY dropped file is HOSTILE: anyone can craft a GRF, XML, lub or exe. So:
//   * a strict grammar: an IPv4 literal, a bracketed/bare IPv6 literal, or an RFC 1123 hostname
//     (labels 1-63, total <= 253, at least two labels, a non-numeric TLD), and a port 1-65535;
//     anything else -- "<script>", "javascript:", quotes, spaces, control characters -- is dropped;
//   * LINEAR scanning only: text is cut into bounded tokens by a character loop; no regular
//     expression ever runs on attacker-controlled text of unbounded length (no catastrophic
//     backtracking). The only regexes here run on tokens already capped at MAX_TOKEN characters
//     and have no nested quantifiers.

export type Role = "login" | "assist-web" | "other";

export interface Found {
  host: string;
  port: number | null;
  role: Role;
  sources: string[]; // where it was found: "data.grf: data\clientinfo.xml" (at most MAX_SOURCES)
  lan: boolean; // on the local network (RFC 1918); everything else gets the warning
}

export const MAX_SOURCES = 4;

export const MAX_TOKEN = 260;
export const MAX_FOUND = 200;

function isIpv4(h: string): boolean {
  const parts = h.split(".");
  if (parts.length !== 4) return false;
  for (const p of parts) {
    if (p.length < 1 || p.length > 3) return false;
    for (const c of p) if (c < "0" || c > "9") return false;
    if (Number(p) > 255) return false;
  }
  return true;
}

function isIpv6(h: string): boolean {
  if (h.length < 2 || h.length > 45) return false;
  const halves = h.split("::");
  if (halves.length > 2) return false;
  const groups = halves.flatMap((x) => (x === "" ? [] : x.split(":")));
  if (halves.length === 1 && groups.length !== 8) return false;
  if (halves.length === 2 && groups.length > 7) return false;
  for (const g of groups) {
    if (g.length < 1 || g.length > 4) return false;
    for (const c of g.toLowerCase()) if (!((c >= "0" && c <= "9") || (c >= "a" && c <= "f"))) return false;
  }
  return true;
}

function isHostname(h: string): boolean {
  if (h.length < 3 || h.length > 253) return false;
  const labels = h.split(".");
  if (labels.length < 2) return false;
  for (const l of labels) {
    if (l.length < 1 || l.length > 63 || l.startsWith("-") || l.endsWith("-")) return false;
    for (const c of l) {
      if (!((c >= "a" && c <= "z") || (c >= "0" && c <= "9") || c === "-")) return false;
    }
  }
  const tld = labels[labels.length - 1];
  return [...tld].some((c) => c >= "a" && c <= "z");
}

/** The grammar: a valid host (lower-cased) or null. */
export function validHost(raw: string): string | null {
  const h = raw.trim().toLowerCase();
  if (h.length === 0 || h.length > MAX_TOKEN) return null;
  if (isIpv4(h) || isIpv6(h) || isHostname(h)) return h;
  return null;
}

export function validPort(raw: string | number): number | null {
  const text = String(raw).trim();
  if (text.length < 1 || text.length > 5) return null;
  for (const c of text) if (c < "0" || c > "9") return null;
  const n = Number(text);
  return n >= 1 && n <= 65535 ? n : null;
}

/** "host:port", "[v6]:port" or "host" -> {host, port} under the grammar; null for anything else. */
export function parseEndpoint(raw: string): { host: string; port: number | null } | null {
  const text = raw.trim();
  if (text.length === 0 || text.length > MAX_TOKEN) return null;
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    if (c <= 0x20 || c >= 0x7f) return null; // no space or control character INSIDE an endpoint
  }
  if (text.startsWith("[")) {
    const end = text.indexOf("]");
    if (end < 0) return null;
    const host = isIpv6(text.slice(1, end).toLowerCase()) ? text.slice(1, end).toLowerCase() : null;
    const rest = text.slice(end + 1);
    if (!host) return null;
    if (rest === "") return { host, port: null };
    const port = rest.startsWith(":") ? validPort(rest.slice(1)) : null;
    return port === null ? null : { host, port };
  }
  const colons = [...text].filter((c) => c === ":").length;
  if (colons === 1) {
    const i = text.indexOf(":");
    const host = validHost(text.slice(0, i));
    const port = validPort(text.slice(i + 1));
    return host && port ? { host, port } : null;
  }
  const host = validHost(text);
  return host ? { host, port: null } : null;
}

/** Not a server anyone should allow or block: this computer, "any address", link-local. */
export function ignorable(host: string): boolean {
  if (isIpv4(host)) {
    const [a, b] = host.split(".").map(Number);
    return a === 0 || a === 127 || (a === 169 && b === 254) || a >= 224;
  }
  return host === "localhost" || host.endsWith(".localhost") || host === "::1" || host === "::";
}

/** RFC 1918 private IPv4 (the LAN). A public address or a NAME is "outside": the bot would act on
 * a server the person may not control. */
export function isLan(host: string): boolean {
  if (!isIpv4(host)) return false;
  const [a, b] = host.split(".").map(Number);
  return a === 10 || (a === 192 && b === 168) || (a === 172 && b >= 16 && b <= 31);
}

const TOKEN_CHAR = (c: number): boolean =>
  (c >= 0x30 && c <= 0x39) || (c >= 0x41 && c <= 0x5a) || (c >= 0x61 && c <= 0x7a) ||
  c === 0x2e || c === 0x2d || c === 0x3a || c === 0x5b || c === 0x5d; // 0-9 A-Z a-z . - : [ ]

/** Endpoints with a PORT ("host:port") in a text, in one linear pass. A URL's "//host:port/" is a
 * token too ("http:" and "//" split it off). Bare names without a port are not reported here:
 * in exe/lub strings they are mostly file names ("msvcrt.dll"). Ignorable hosts (127.0.0.1...)
 * ARE returned: the caller counts them ("points to this computer"). */
export function scanText(text: string, limit = MAX_FOUND): { host: string; port: number }[] {
  const out: { host: string; port: number }[] = [];
  const seen = new Set<string>();
  let start = -1;
  const flush = (end: number) => {
    if (start < 0) return;
    const len = end - start;
    if (len >= 5 && len <= MAX_TOKEN) {
      const ep = parseEndpoint(text.slice(start, end));
      if (ep && ep.port !== null) {
        const key = `${ep.host}:${ep.port}`;
        if (!seen.has(key)) {
          seen.add(key);
          out.push({ host: ep.host, port: ep.port });
        }
      }
    }
    start = -1;
  };
  let overlong = false; // inside a token longer than MAX_TOKEN: skipped whole, never a fragment
  for (let i = 0; i < text.length && out.length < limit; i++) {
    if (TOKEN_CHAR(text.charCodeAt(i))) {
      if (overlong) continue;
      if (start < 0) start = i;
      else if (i - start >= MAX_TOKEN) {
        overlong = true;
        start = -1;
      }
    } else {
      overlong = false;
      flush(i);
    }
  }
  if (!overlong) flush(text.length);
  return out;
}

/** Printable ASCII runs of a binary (>= minLen characters), in one linear pass. A run longer than
 * maxLen is dropped whole: cutting it would make fragments ("evil.example.com:69" of ":6900"). */
export function* printableRuns(bytes: Uint8Array, minLen = 4, maxLen = 512): Generator<string> {
  let run: number[] = [];
  let over = false;
  for (let i = 0; i <= bytes.length; i++) {
    const c = i < bytes.length ? bytes[i] : 0;
    if (c >= 0x20 && c <= 0x7e) {
      if (run.length < maxLen) run.push(c);
      else over = true;
    } else {
      if (!over && run.length >= minLen) yield String.fromCharCode(...run);
      run = [];
      over = false;
    }
  }
}
