"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { exampleRunFolder, folderProblem, maxProblem, runLogReasonText, type RunLogView } from "@/lib/runlog";
import { backendHttpBase } from "@/lib/ws";

type Note = { tone: "ok" | "error" | "info"; text: string };

const NOTE_CLASS: Record<Note["tone"], string> = {
  ok: "border-emerald-700 bg-emerald-950 text-emerald-100",
  error: "border-red-700 bg-red-950 text-red-100",
  info: "border-neutral-700 bg-neutral-900 text-neutral-200",
};

type Loaded = { view?: RunLogView; error?: string };

async function fetchRunLog(base: string): Promise<Loaded> {
  try {
    const r = await fetch(`${base}/settings/run-log`, { cache: "no-store" });
    const body = await r.json().catch(() => null);
    if (!r.ok) return { error: runLogReasonText(body?.detail?.reason ?? `http_${r.status}`) };
    return { view: body as RunLogView };
  } catch {
    return { error: "The backend did not answer." };
  }
}

/** Settings: the Run log (Batt 2026-11-21) -- "What she does" kept as history: record or not (the
 * default: not), the folder (the default logs/bot, a Run's own folder in it by its start time; a
 * NAS folder if wanted) and the total size kept (the oldest Run deleted first, like a CCTV
 * recorder). Only a person at a LAN computer can change it; a Save applies to the next Run. */
export default function RunLogSettings({ backendUrl }: { backendUrl: string | null }) {
  const [view, setView] = useState<RunLogView | null>(null);
  const [record, setRecord] = useState(false);
  const [folder, setFolder] = useState("");
  const [mb, setMb] = useState("100");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<Note | null>(null);
  const csrf = useRef<string | null>(null);
  const base = backendHttpBase(backendUrl);

  const take = useCallback((v: RunLogView) => {
    setView(v);
    setRecord(v.record);
    setFolder(v.folder);
    setMb(String(v.max_total_mb));
  }, []);

  const apply = useCallback(
    (l: Loaded) => {
      if (l.error) setNote({ tone: "error", text: l.error });
      if (l.view) take(l.view);
    },
    [take],
  );

  useEffect(() => {
    void fetchRunLog(base).then(apply);
  }, [base, apply]);

  /** One write with the CSRF token (a stale token is fetched again once). */
  const send = useCallback(
    async (body: unknown): Promise<{ ok: boolean; body: unknown; status: number }> => {
      const once = async (): Promise<Response> => {
        if (!csrf.current) {
          const t = await fetch(`${base}/settings/csrf`, { cache: "no-store" });
          csrf.current = t.ok ? ((await t.json()) as { token: string }).token : "";
        }
        return fetch(`${base}/settings/run-log`, {
          method: "PUT",
          headers: { "content-type": "application/json", "x-csrf-token": csrf.current ?? "" },
          body: JSON.stringify(body),
        });
      };
      let r = await once();
      if (r.status === 403) {
        const peek = await r.clone().json().catch(() => null);
        if (peek?.detail?.reason === "csrf_invalid") {
          csrf.current = null;
          r = await once();
        }
      }
      return { ok: r.ok, body: await r.json().catch(() => null), status: r.status };
    },
    [base],
  );

  const mbNum = Number(mb);
  const problem = view
    ? folderProblem(folder, view.max_folder) ?? maxProblem(mbNum, view.max_total_mb_range)
    : null;
  const changed = view !== null && (record !== view.record || folder.trim() !== view.folder || mbNum !== view.max_total_mb);

  const save = async () => {
    if (!view || problem) return;
    setBusy(true);
    setNote(null);
    try {
      const r = await send({ base_revision: view.revision, record, folder: folder.trim(), max_total_mb: mbNum });
      if (!r.ok) {
        const reason = (r.body as { detail?: { reason?: string } } | null)?.detail?.reason ?? `http_${r.status}`;
        setNote({ tone: "error", text: runLogReasonText(reason) });
        if (reason === "revision_conflict") void fetchRunLog(base).then(apply);
        return;
      }
      take(r.body as RunLogView);
      setNote({ tone: "ok", text: "Saved. The next Run uses it." });
    } catch {
      setNote({ tone: "error", text: "The backend did not answer: not saved." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mx-auto flex max-w-[1100px] flex-col gap-3 p-4 pb-0" data-testid="run-log">
      <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4">
        <h1 className="text-lg font-semibold tracking-tight">Settings: the Run log</h1>
        <p className="mt-1 text-sm text-neutral-400">
          Keep what the Run panel&apos;s <em>What she does</em> says, for every Run, to read or analyse later. Each Run gets its
          own folder, named by its start time, with two files: <code>story.jsonl</code> (one JSON line each: the clock time, the
          Run&apos;s seconds, the words) and <code>story.log</code> (the same as plain text). When the folder&apos;s Runs pass the
          size below, the oldest Run is deleted first, like a CCTV recorder. A Save applies to the next Run.
        </p>
        {view?.store === "unreadable" && (
          <p className={`mt-2 rounded border px-3 py-2 text-sm ${NOTE_CLASS.error}`}>
            The saved file does not parse ({view.problem}), so nothing is recorded. Save to replace it.
          </p>
        )}
        <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-neutral-100">
          <input type="checkbox" checked={record} onChange={(e) => setRecord(e.target.checked)} />
          Record every Run&apos;s log <span className="text-xs text-neutral-500">(default: off)</span>
        </label>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="flex flex-col text-xs text-neutral-400">
            Folder (on this server; absolute, e.g. a NAS mount, or inside the install)
            <input
              value={folder}
              maxLength={view?.max_folder ?? 512}
              onChange={(e) => setFolder(e.target.value)}
              placeholder={view?.default.folder ?? "logs/bot"}
              className="mt-1 w-96 max-w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-sm text-neutral-100"
            />
          </label>
          <label className="flex flex-col text-xs text-neutral-400">
            Keep at most (MB, all Runs together)
            <input
              value={mb}
              inputMode="numeric"
              onChange={(e) => setMb(e.target.value.replace(/[^0-9]/g, ""))}
              className="mt-1 w-28 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm text-neutral-100"
            />
          </label>
        </div>
        <p className="mt-2 text-xs text-neutral-500">
          A Run would be kept in <code>{exampleRunFolder(folder.trim() || view?.default.folder || "logs/bot")}</code>
          {view && view.store !== "ok" && " (the defaults are shown until you save)"}.
        </p>
        {problem && changed && <p className="mt-2 text-xs text-amber-200">{runLogReasonText(problem)}</p>}
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={!changed || busy || problem !== null}
            onClick={() => void save()}
            className="rounded bg-sky-700 px-3 py-1 text-sm font-semibold text-white hover:bg-sky-600 disabled:opacity-40"
          >
            {busy ? "Saving…" : "Save"}
          </button>
          {changed && (
            <button
              type="button"
              disabled={busy}
              onClick={() => view && take(view)}
              className="rounded border border-neutral-700 px-3 py-1 text-sm text-neutral-200 hover:bg-neutral-800"
            >
              Cancel changes
            </button>
          )}
        </div>
        {note && <p className={`mt-3 rounded border px-3 py-2 text-sm ${NOTE_CLASS[note.tone]}`}>{note.text}</p>}
      </div>
    </section>
  );
}
