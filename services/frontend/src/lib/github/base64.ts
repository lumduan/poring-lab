// Base64 for GitHub's contents API, which sends and receives file bytes as Base64
// (docs/planning/flows-save-load.md section 3). Plain btoa throws on Thai: the text goes through
// UTF-8 bytes first.
//
// Ported from MatPilot (MIT), src/lib/github/base64.ts at 4022c87 (https://github.com/lumduan/matpilot,
// Copyright (c) 2026 Sarat Sonsuk; the licence text is in components/flowfile/flowfile.css and
// THIRD_PARTY.md).

const CHUNK = 0x8000; // 32 KB: keeps String.fromCharCode's argument list short

/** UTF-8 bytes of `text`, as Base64. */
export function encodeBase64Utf8(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

/** Base64 (GitHub wraps it in lines) to text, read as UTF-8. Throws on bad Base64 or UTF-8. */
export function decodeBase64Utf8(base64: string): string {
  const binary = atob(base64.replace(/\s+/g, ""));
  const bytes = Uint8Array.from(binary, (ch) => ch.charCodeAt(0));
  return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
}

/** How many bytes a Base64 text decodes to (whitespace ignored), before decoding it. */
export function base64Bytes(base64: string): number {
  let n = 0;
  let pad = 0;
  for (let i = 0; i < base64.length; i++) {
    const c = base64.charCodeAt(i);
    if (c === 0x20 || c === 0x0a || c === 0x0d || c === 0x09) continue;
    n++;
    if (c === 0x3d) pad++; // "="
  }
  return Math.max(0, Math.floor((n * 3) / 4) - pad);
}
