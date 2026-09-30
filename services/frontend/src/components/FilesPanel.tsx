"use client";

import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";

import {
  deleteFile,
  downloadFile,
  formatBytes,
  listFiles,
  TransferError,
  uploadFile,
  type TransferListing,
} from "@/lib/transfer";
import { backendHttpBase } from "@/lib/ws";

type Props = {
  backendUrl: string | null;
  enabled: boolean; // the backend offers \\tsclient\transfer (Status.transfer_enabled)
};

type Upload = { name: string; loaded: number; total: number; error: string | null };

const button =
  "rounded-md border border-neutral-700 bg-neutral-900 px-2 py-0.5 text-xs hover:bg-neutral-800 disabled:opacity-40";

const REFRESH_MS = 5000;

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Files between this browser and Windows (ADR-0004): uploads land in \\tsclient\transfer, and
 * whatever Windows saves there can be downloaded here. RAM-only area (512 MiB), emptied when the
 * lab stops -- a hand-off point, not storage. */
export default function FilesPanel({ backendUrl, enabled }: Props) {
  const [listing, setListing] = useState<TransferListing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const base = useCallback(() => backendHttpBase(backendUrl), [backendUrl]);

  const refresh = useCallback(async () => {
    try {
      setListing(await listFiles(base()));
      setError(null);
    } catch (e) {
      setError(message(e));
    }
  }, [base]);

  useEffect(() => {
    if (!enabled) return;
    const tick = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    const first = setTimeout(tick, 0);
    const timer = setInterval(tick, REFRESH_MS);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [enabled, refresh]);

  const track = (name: string, patch: Partial<Upload>) =>
    setUploads((list) => list.map((u) => (u.name === name ? { ...u, ...patch } : u)));

  const upload = async (file: File, overwrite = false): Promise<void> => {
    setUploads((list) => [
      ...list.filter((u) => u.name !== file.name),
      { name: file.name, loaded: 0, total: file.size, error: null },
    ]);
    try {
      await uploadFile(base(), file, {
        overwrite,
        onProgress: (loaded, total) => track(file.name, { loaded, total }),
      });
      setUploads((list) => list.filter((u) => u.name !== file.name));
    } catch (e) {
      if (
        e instanceof TransferError &&
        e.reason === "exists" &&
        !overwrite &&
        window.confirm(`"${file.name}" already exists in the transfer area. Replace it?`)
      ) {
        return upload(file, true);
      }
      track(file.name, { error: message(e) });
    }
    await refresh();
  };

  const uploadAll = (files: FileList | null) => {
    for (const file of Array.from(files ?? [])) void upload(file);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    if (enabled) uploadAll(event.dataTransfer.files);
  };

  const download = async (name: string) => {
    try {
      await downloadFile(base(), name);
    } catch (e) {
      setError(message(e));
    }
  };

  const remove = async (name: string, kind: string) => {
    if (!window.confirm(`Delete the ${kind === "dir" ? "folder" : "file"} "${name}"?`)) return;
    try {
      await deleteFile(base(), name);
    } catch (e) {
      setError(message(e));
    }
    await refresh();
  };

  if (!enabled) {
    return (
      <p className="text-xs text-amber-300">
        File transfer is off on the backend (RDP_DRIVES=transfer, then the desktop reconnects).
      </p>
    );
  }

  const used = listing ? listing.capacity_bytes - listing.free_bytes : 0;

  return (
    <div className="flex flex-col gap-2 text-sm">
      <p className="text-xs text-neutral-400">
        In Windows this folder is <span className="font-mono">\\tsclient\transfer</span> (Win+R).
        RAM only, {formatBytes(listing?.capacity_bytes ?? 512 * 1024 * 1024)}, emptied when the lab
        stops. Large files such as a game client: use SMB or a direct download on Windows.
      </p>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`flex items-center gap-3 rounded-md border border-dashed px-3 py-2 text-xs ${
          dragging ? "border-sky-500 bg-sky-950" : "border-neutral-700"
        }`}
      >
        <button type="button" className={button} onClick={() => inputRef.current?.click()}>
          Upload…
        </button>
        <span className="text-neutral-400">or drop files here</span>
        <input
          ref={inputRef}
          type="file"
          multiple
          hidden
          onChange={(e) => {
            uploadAll(e.target.files);
            e.target.value = "";
          }}
        />
        <button type="button" className={`${button} ml-auto`} onClick={() => void refresh()}>
          Refresh
        </button>
      </div>
      {uploads.map((u) => (
        <div key={u.name} className="text-xs">
          <span className="font-mono">{u.name}</span>{" "}
          {u.error ? (
            <span className="text-red-400">{u.error}</span>
          ) : (
            <span className="text-neutral-400">
              {formatBytes(u.loaded)} / {formatBytes(u.total)}
            </span>
          )}
          {u.error && (
            <button
              type="button"
              className={`${button} ml-2`}
              onClick={() => setUploads((list) => list.filter((x) => x.name !== u.name))}
            >
              Dismiss
            </button>
          )}
        </div>
      ))}
      {error && <p className="text-xs text-red-400">{error}</p>}
      {listing && (
        <>
          <table className="w-full text-xs">
            <tbody>
              {listing.files.length === 0 && (
                <tr>
                  <td className="py-1 text-neutral-500">Empty.</td>
                </tr>
              )}
              {listing.files.map((f) => (
                <tr key={f.name} className="border-t border-neutral-800">
                  <td className="py-1 font-mono">
                    {f.kind === "dir" ? "📁 " : ""}
                    {f.name}
                  </td>
                  <td className="py-1 text-right text-neutral-400">
                    {f.kind === "file" ? formatBytes(f.size) : ""}
                  </td>
                  <td className="py-1 pl-3 text-neutral-500">
                    {new Date(f.mtime_ns / 1e6).toLocaleString()}
                  </td>
                  <td className="py-1 pl-3 text-right whitespace-nowrap">
                    {f.kind === "file" && (
                      <button type="button" className={button} onClick={() => void download(f.name)}>
                        Download
                      </button>
                    )}{" "}
                    <button type="button" className={button} onClick={() => void remove(f.name, f.kind)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs text-neutral-500">
            {formatBytes(used)} used of {formatBytes(listing.capacity_bytes)}
          </p>
        </>
      )}
    </div>
  );
}
