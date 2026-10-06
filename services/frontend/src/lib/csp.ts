// The console's Content-Security-Policy (Batt, 2026-10-06, the game-file finder's threat model):
// no inline script and no eval in production, scripts only by a per-request nonce
// ('strict-dynamic' lets Next's own chunks load), workers only from this origin, no plugins, no
// framing, no <base> tricks. The page may talk to this origin and to the backend (http + ws).
// Styles keep 'unsafe-inline': two components set style attributes, and CSS cannot run script.

/** "http://h:p" + "ws://h:p" of the backend, from BACKEND_PUBLIC_URL, else the request's host on
 * :8000 (as backendHttpBase does in the browser). Anything that does not parse adds nothing. */
export function backendSources(configured: string | null, host: string | null): string[] {
  try {
    if (configured) {
      const u = new URL(configured);
      if (u.protocol !== "http:" && u.protocol !== "https:") return [];
      return [u.origin, u.origin.replace(/^http/, "ws")];
    }
    if (!host || host.length > 300) return [];
    const name = new URL(`http://${host}`).hostname; // throws on anything that is not a host
    if (!/^[a-z0-9.\-[\]:]+$/.test(name)) return [];
    return [`http://${name}:8000`, `ws://${name}:8000`];
  } catch {
    return [];
  }
}

export function cspHeader(o: { nonce: string; dev: boolean; backend: string[]; host: string | null }): string {
  const dev = o.dev && o.host && /^[A-Za-z0-9.\-[\]:]+$/.test(o.host) ? [`ws://${o.host}`] : []; // HMR
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${o.nonce}' 'strict-dynamic'${o.dev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' blob: data:",
    "font-src 'self'",
    ["connect-src 'self'", ...o.backend, ...dev].join(" "),
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}
