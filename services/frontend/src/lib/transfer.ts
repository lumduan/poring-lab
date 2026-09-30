// Human-only clipboard paste and file transfer helpers (ADR-0004).
//
// The pure functions are unit-tested (transfer.test.ts). The network ones call the backend's
// /transfer routes cross-origin: the browser then always sends an Origin header, which the backend
// REQUIRES (it is how a browser is told apart from the agent or a script). That is also why a
// download is fetched as a blob instead of followed as a plain link: a navigation sends no Origin.

/** Mirror of poring_env.protocol.PASTE_MAX_BYTES (UTF-8 bytes). */
export const PASTE_MAX_BYTES = 64 * 1024;

export function utf8Bytes(text: string): number {
  return new TextEncoder().encode(text).length;
}

export function formatBytes(n: number): string {
  if (!Number.isFinite(n) || n < 0) return "?";
  if (n < 1024) return `${n} B`;
  const units = ["KiB", "MiB", "GiB"];
  let value = n / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${Math.round(value * 10) / 10} ${units[unit]}`; // 1 decimal, no trailing ".0"
}

export type PasteCheck = { ok: boolean; bytes: number; message: string | null };

export function checkPaste(text: string): PasteCheck {
  const bytes = utf8Bytes(text);
  if (text.length === 0) return { ok: false, bytes, message: null };
  if (bytes > PASTE_MAX_BYTES) {
    return {
      ok: false,
      bytes,
      message:
        `Too large to paste: ${formatBytes(bytes)} (limit ${formatBytes(PASTE_MAX_BYTES)}). ` +
        "Send it as a file instead.",
    };
  }
  return { ok: true, bytes, message: null };
}

const PASTE_REASONS: Record<string, string> = {
  ok: "Pasted into the focused Windows window.",
  clipboard_disabled:
    "Clipboard paste is not enabled on the backend (RDP_CLIPBOARD=text-to-remote in .env).",
  origin_required: "Refused: this connection did not come from the console page.",
  mode_bot: "Refused: the input mux is in BOT mode. Switch to HUMAN or ASSIST to paste.",
  "mode=BOT": "Refused: the input mux is in BOT mode. Switch to HUMAN or ASSIST to paste.",
  rdp_clipboard_not_listening:
    "The RDP session did not pick up the text (clipboard redirection off, or RDP reconnecting).",
  no_data_request:
    "Ctrl+V was sent, but the focused Windows window did not paste. Click a text field in the " +
    "remote screen first, then send again.",
  x_unavailable: "The backend cannot reach the X display.",
  ownership_taken: "Another program took the clipboard: nothing was pasted.",
  inject_timeout: "The backend timed out before sending Ctrl+V.",
  timeout: "The paste timed out.",
  own_failed: "The backend could not take the X clipboard.",
  cancelled: "The paste was cancelled (connection closed).",
};

export function describePaste(reason: string): string {
  return PASTE_REASONS[reason] ?? `Paste failed: ${reason}.`;
}

export type TransferEntry = { name: string; kind: "file" | "dir"; size: number; mtime_ns: number };
export type TransferListing = {
  files: TransferEntry[];
  free_bytes: number;
  capacity_bytes: number;
  max_file_bytes: number;
};
export type UploadResult = { name: string; size: number; sha256: string };

function field(detail: unknown, key: string): unknown {
  return typeof detail === "object" && detail !== null
    ? (detail as Record<string, unknown>)[key]
    : undefined;
}

/** A human sentence for a /transfer error response (``detail`` is FastAPI's error detail). */
export function describeTransferError(status: number, detail: unknown): string {
  const reason = field(detail, "reason");
  switch (reason) {
    case "too_large":
    case "body_larger_than_declared":
      return (
        `The file is ${formatBytes(Number(field(detail, "size")))}; the transfer area takes at ` +
        `most ${formatBytes(Number(field(detail, "max_bytes")))}. For large files (e.g. a game ` +
        "client) use SMB or a direct download on Windows instead."
      );
    case "not_enough_space":
      return (
        `Not enough room in the transfer area (${formatBytes(Number(field(detail, "free_bytes")))}` +
        " free). Delete files there first."
      );
    case "exists":
      return `"${String(field(detail, "name"))}" already exists in the transfer area.`;
    case "transfer_disabled":
      return "File transfer is not enabled on the backend (RDP_DRIVES=transfer in .env).";
    case "origin_required":
    case "origin_not_allowed":
      return "The backend refused this page's origin (check FRONTEND_ORIGINS).";
    case "bad_name": {
      const why = field(detail, "detail");
      return `Unusable file name${typeof why === "string" ? `: ${why}` : ""}.`;
    }
    case "directory_not_empty":
      return "That folder is not empty: empty it from Windows first.";
    case "not_a_file":
      return "Folders cannot be downloaded: open it from Windows.";
    case "not_found":
      return "It is not there any more (deleted from Windows?).";
    case "length_required":
      return "The browser did not say how large the file is.";
    case "network_error":
      return "The backend could not be reached.";
    default:
      return `Transfer failed (HTTP ${status}${typeof reason === "string" ? `: ${reason}` : ""}).`;
  }
}

export class TransferError extends Error {
  readonly status: number;
  readonly reason: string | null;

  constructor(status: number, detail: unknown) {
    super(describeTransferError(status, detail));
    this.status = status;
    const reason = field(detail, "reason");
    this.reason = typeof reason === "string" ? reason : null;
  }
}

export function fileUrl(base: string, name: string, overwrite = false): string {
  return `${base}/transfer/files/${encodeURIComponent(name)}${overwrite ? "?overwrite=true" : ""}`;
}

async function failure(response: Response): Promise<TransferError> {
  let detail: unknown = null;
  try {
    detail = ((await response.json()) as { detail?: unknown }).detail ?? null;
  } catch {
    // not JSON (a proxy error page, say): the status alone has to do
  }
  return new TransferError(response.status, detail);
}

export async function listFiles(base: string): Promise<TransferListing> {
  const response = await fetch(`${base}/transfer/files`, { cache: "no-store" });
  if (!response.ok) throw await failure(response);
  return (await response.json()) as TransferListing;
}

export async function deleteFile(base: string, name: string): Promise<void> {
  const response = await fetch(fileUrl(base, name), { method: "DELETE" });
  if (!response.ok) throw await failure(response);
}

/** Fetch with Origin (see the top of this file), then hand the blob to the browser's saver. */
export async function downloadFile(base: string, name: string): Promise<void> {
  const response = await fetch(fileUrl(base, name), { cache: "no-store" });
  if (!response.ok) throw await failure(response);
  const url = URL.createObjectURL(await response.blob());
  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.append(link);
    link.click();
    link.remove();
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }
}

/** XMLHttpRequest, because fetch() cannot report upload progress. */
export function uploadFile(
  base: string,
  file: File,
  options: { overwrite?: boolean; onProgress?: (loaded: number, total: number) => void } = {},
): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", fileUrl(base, file.name, options.overwrite ?? false));
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (event) => options.onProgress?.(event.loaded, event.total);
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        // keep null
      }
      if (xhr.status === 200) resolve(body as UploadResult);
      else reject(new TransferError(xhr.status, field(body, "detail") ?? null));
    };
    xhr.onerror = () => reject(new TransferError(0, { reason: "network_error" }));
    xhr.send(file);
  });
}
