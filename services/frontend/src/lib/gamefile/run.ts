// The page's side of the finder: hand the File to a Web Worker (no DOM, no page state), stop it
// after LIMITS.timeoutMs, and re-check everything that comes back before the page shows it.

import { safeLabel } from "./extract.ts";
import { isLan, MAX_FOUND, MAX_SOURCES, parseEndpoint, type Found, type Role } from "./endpoint.ts";
import { failed, LIMITS, safeName, type Kind, type ScanResult } from "./scan.ts";

export { failed };

export interface WorkerLike {
  postMessage(message: unknown): void;
  terminate(): void;
  onmessage: ((event: { data: unknown }) => void) | null;
  onerror: ((event: unknown) => void) | null;
}

const KINDS: Kind[] = ["grf", "clientinfo", "lub", "exe", "unknown"];
const ROLES: Role[] = ["login", "assist-web", "other"];

const text = (v: unknown, max: number): string => safeName(typeof v === "string" ? v : "", max);
const count = (v: unknown): number => (typeof v === "number" && Number.isFinite(v) && v >= 0 ? Math.floor(v) : 0);

/** The worker's reply, re-validated: the grammar again on every endpoint, bounded lists, text
 * made safe. Anything that does not fit is dropped (defence in depth: the worker runs our code
 * on hostile bytes). */
export function checked(data: unknown, file: string): ScanResult {
  if (typeof data !== "object" || data === null) return failed(file, "The finder stopped without an answer.");
  const d = data as Record<string, unknown>;
  const found: Found[] = [];
  for (const raw of Array.isArray(d.found) ? d.found.slice(0, MAX_FOUND) : []) {
    const f = raw as Record<string, unknown>;
    if (typeof f?.host !== "string") continue;
    const port = typeof f.port === "number" ? f.port : null;
    const ep = parseEndpoint(port === null ? f.host : f.host.includes(":") ? `[${f.host}]:${port}` : `${f.host}:${port}`);
    if (!ep || ep.port !== port) continue;
    const role = ROLES.includes(f.role as Role) ? (f.role as Role) : "other";
    const sources = (Array.isArray(f.sources) ? f.sources : []).slice(0, MAX_SOURCES).map((s) => text(s, 200));
    found.push({ host: ep.host, port: ep.port, role, sources, lan: isLan(ep.host) });
  }
  const s = (d.stats ?? {}) as Record<string, unknown>;
  return {
    file: text(d.file, 100) || safeName(file),
    kind: KINDS.includes(d.kind as Kind) ? (d.kind as Kind) : "unknown",
    found,
    notes: (Array.isArray(d.notes) ? d.notes : []).slice(0, 20).map((n) => text(n, 400)),
    error: d.error === null ? null : text(d.error, 400) || "The finder failed.",
    display: typeof d.display === "string" ? safeLabel(d.display) || null : null,
    stats: { entries: count(s.entries), read: count(s.read), encrypted: count(s.encrypted), inflated: count(s.inflated), ignored: count(s.ignored) },
  };
}

function browserWorker(): WorkerLike {
  return new Worker(new URL("./worker.ts", import.meta.url), { type: "module" }) as unknown as WorkerLike;
}

/** Scan one file in a fresh worker; always resolves (an error is a result). */
export function scanInWorker(
  file: { name: string; size: number },
  opts: { timeoutMs?: number; makeWorker?: () => WorkerLike } = {},
): Promise<ScanResult> {
  const timeoutMs = opts.timeoutMs ?? LIMITS.timeoutMs;
  if (file.size > LIMITS.fileMaxBytes) return Promise.resolve(failed(file.name, "This file is too large."));
  return new Promise((resolve) => {
    let worker: WorkerLike;
    try {
      worker = (opts.makeWorker ?? browserWorker)();
    } catch {
      resolve(failed(file.name, "This browser could not start the finder (Web Workers are off)."));
      return;
    }
    const finish = (r: ScanResult) => {
      clearTimeout(timer);
      worker.onmessage = null;
      worker.onerror = null;
      worker.terminate();
      resolve(r);
    };
    const timer = setTimeout(
      () => finish(failed(file.name, `Stopped: reading took longer than ${Math.round(timeoutMs / 1000)} s. The file may be damaged or crafted.`)),
      timeoutMs,
    );
    worker.onmessage = (e) => finish(checked(e.data, file.name));
    worker.onerror = () => finish(failed(file.name, "The finder failed on this file."));
    worker.postMessage(file);
  });
}
