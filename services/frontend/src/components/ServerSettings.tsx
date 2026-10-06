"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  type AuditRecord,
  auditText,
  type Draft,
  diff,
  type EnvView,
  keyOf,
  reasonText,
  type SettingsView,
  validateEntry,
} from "@/lib/settings";
import { backendHttpBase } from "@/lib/ws";

type Note = { tone: "ok" | "error" | "info"; text: string };

const NOTE_CLASS: Record<Note["tone"], string> = {
  ok: "border-emerald-700 bg-emerald-950 text-emerald-100",
  error: "border-red-700 bg-red-950 text-red-100",
  info: "border-neutral-700 bg-neutral-900 text-neutral-200",
};

const STATUS_TEXT: Record<EnvView["status"], string> = {
  allowed: "Approved",
  pending: "Not approved yet",
  forbidden: "Forbidden (official servers)",
};

function toDrafts(env: EnvView): Draft[] {
  return env.entries.map((e) => ({ host: e.host, port: e.port, source: e.source }));
}

function EnvCard({
  env,
  revision,
  forbidden,
  backendUrl,
  onSaved,
}: {
  env: EnvView;
  revision: number | null;
  forbidden: string[];
  backendUrl: string | null;
  onSaved: (view: SettingsView, note: Note) => void;
}) {
  const [draft, setDraft] = useState<Draft[]>(() => toDrafts(env));
  const [host, setHost] = useState("");
  const [port, setPort] = useState("");
  const [note, setNote] = useState<Note | null>(null);
  const [saving, setSaving] = useState(false);

  const changes = useMemo(() => diff(env.entries, draft), [env.entries, draft]);
  const dirty = changes.added.length > 0 || changes.removed.length > 0;
  const inDraft = new Set(draft.map(keyOf));
  const stored = new Map(env.entries.map((e) => [keyOf(e), e]));

  const add = (h: string, p: string, source: Draft["source"]) => {
    const v = validateEntry(h, p, forbidden);
    if (v.error) {
      setNote({ tone: "error", text: reasonText(v.error) });
      return;
    }
    if (inDraft.has(keyOf(v))) {
      setNote({ tone: "error", text: reasonText("duplicate") });
      return;
    }
    setDraft([...draft, { host: v.host, port: v.port, source }]);
    setNote({ tone: "info", text: `${keyOf(v)} added below. Press Save to keep it.` });
    if (source === "manual") {
      setHost("");
      setPort("");
    }
  };

  const save = async () => {
    setSaving(true);
    setNote({ tone: "info", text: "Saving…" });
    try {
      const r = await fetch(`${backendHttpBase(backendUrl)}/settings/servers/${env.id}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ base_revision: revision ?? 0, entries: draft }),
      });
      const body = await r.json();
      if (!r.ok) {
        const reason: string = body?.detail?.reason ?? `http_${r.status}`;
        const entry = body?.detail?.entry ? ` (${body.detail.entry})` : "";
        setNote({ tone: "error", text: `Not saved${entry}: ${reasonText(reason)}` });
        return;
      }
      const view = body as SettingsView;
      onSaved(view, {
        tone: "ok",
        text: view.saved
          ? `Saved and checked ✓ (revision ${view.revision}): +${changes.added.length} / −${changes.removed.length}.`
          : "Nothing changed.",
      });
      setNote(null);
    } catch {
      setNote({ tone: "error", text: "The backend did not answer: nothing was saved." });
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4">
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-mono text-base font-semibold">{env.id}</h2>
        <span
          className={`rounded px-2 py-0.5 text-xs ${
            env.status === "allowed"
              ? "bg-emerald-900 text-emerald-100"
              : env.status === "pending"
                ? "bg-amber-900 text-amber-100"
                : "bg-red-900 text-red-100"
          }`}
        >
          {STATUS_TEXT[env.status]}
        </span>
      </header>

      {!env.editable ? (
        <p className="text-sm text-neutral-400">
          The bot never acts here, so no servers can be added. ({env.adr})
        </p>
      ) : (
        <div className="flex flex-col gap-4">
          <div>
            <h3 className="mb-1 text-sm font-semibold text-neutral-200">Servers the bot may use</h3>
            {draft.length === 0 ? (
              <p className="text-sm text-neutral-400">
                None yet. Confirm a server the lab found, or add one below.
              </p>
            ) : (
              <ul className="flex flex-col gap-1">
                {draft.map((d) => {
                  const s = stored.get(keyOf(d));
                  return (
                    <li
                      key={keyOf(d)}
                      className="flex flex-wrap items-center gap-3 rounded bg-neutral-950 px-3 py-1.5 text-sm"
                    >
                      <span className="font-mono">{keyOf(d)}</span>
                      {s?.resolved?.length && !/^[\d.]+$/.test(d.host) ? (
                        <span className="text-xs text-neutral-400">= {s.resolved.join(", ")}</span>
                      ) : null}
                      <span className="text-xs text-neutral-500">
                        {s ? `added ${s.added_at.slice(0, 16).replace("T", " ")} from ${s.added_by}` : "not saved yet"}
                      </span>
                      <button
                        type="button"
                        onClick={() => setDraft(draft.filter((x) => keyOf(x) !== keyOf(d)))}
                        className="ml-auto rounded border border-neutral-700 px-2 py-0.5 text-xs hover:bg-neutral-800"
                      >
                        Remove
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {env.discovered.filter((s) => !inDraft.has(keyOf(s))).length > 0 && (
            <div>
              <h3 className="mb-1 text-sm font-semibold text-neutral-200">Found by the lab</h3>
              <p className="mb-1 text-xs text-neutral-400">
                Suggestions only: the bot may not use them until you confirm and save.
              </p>
              <ul className="flex flex-col gap-1">
                {env.discovered
                  .filter((s) => !inDraft.has(keyOf(s)))
                  .map((s) => (
                    <li
                      key={keyOf(s)}
                      className="flex items-center gap-3 rounded border border-dashed border-neutral-700 px-3 py-1.5 text-sm"
                    >
                      <span className="font-mono">{keyOf(s)}</span>
                      <span className="text-xs text-neutral-500">
                        {s.from === "lab_config" ? "from the lab config" : `from ${s.from}`}
                      </span>
                      <button
                        type="button"
                        onClick={() => add(s.host, String(s.port), "discovered")}
                        className="ml-auto rounded bg-sky-700 px-2 py-0.5 text-xs font-semibold text-white hover:bg-sky-600"
                      >
                        Confirm
                      </button>
                    </li>
                  ))}
              </ul>
            </div>
          )}

          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              add(host, port, "manual");
            }}
          >
            <label className="flex flex-col text-xs text-neutral-400">
              Server address
              <input
                value={host}
                onChange={(e) => setHost(e.target.value)}
                placeholder="192.168.1.13 or ro.example.net"
                className="mt-1 w-64 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm text-neutral-100"
              />
            </label>
            <label className="flex flex-col text-xs text-neutral-400">
              Port
              <input
                value={port}
                onChange={(e) => setPort(e.target.value)}
                placeholder="6900"
                inputMode="numeric"
                className="mt-1 w-24 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm text-neutral-100"
              />
            </label>
            <button
              type="submit"
              className="rounded border border-neutral-600 px-3 py-1 text-sm hover:bg-neutral-800"
            >
              Add
            </button>
          </form>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={!dirty || saving}
              onClick={() => void save()}
              className="rounded bg-emerald-700 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-600 disabled:opacity-40"
            >
              Save
            </button>
            <button
              type="button"
              disabled={!dirty || saving}
              onClick={() => {
                setDraft(toDrafts(env));
                setNote(null);
              }}
              className="rounded border border-neutral-700 px-3 py-1.5 text-sm hover:bg-neutral-800 disabled:opacity-40"
            >
              Undo changes
            </button>
            {dirty && (
              <span className="text-xs text-amber-300">
                Unsaved: {changes.added.length ? `+${changes.added.join(", ")} ` : ""}
                {changes.removed.length ? `−${changes.removed.join(", ")}` : ""}
              </span>
            )}
          </div>
        </div>
      )}
      {note && <p className={`mt-3 rounded border px-3 py-2 text-sm ${NOTE_CLASS[note.tone]}`}>{note.text}</p>}
    </section>
  );
}

type Loaded = { view?: SettingsView; audit: AuditRecord[]; error?: string };

/** The page's data: the list and the change history (no React state here). */
async function fetchView(base: string): Promise<Loaded> {
  try {
    const [s, a] = await Promise.all([
      fetch(`${base}/settings/servers`, { cache: "no-store" }),
      fetch(`${base}/settings/audit?days=30`, { cache: "no-store" }),
    ]);
    if (!s.ok) {
      const body = await s.json().catch(() => null);
      return { audit: [], error: reasonText(body?.detail?.reason ?? `http_${s.status}`) };
    }
    const audit = a.ok ? ((await a.json()) as { records: AuditRecord[] }).records : [];
    return { view: (await s.json()) as SettingsView, audit };
  } catch {
    return { audit: [], error: "The backend did not answer." };
  }
}

/** Settings: which game servers the bot may act on. Saving needs a person at this page; the bot
 * can read the list but never change it (the backend enforces both). */
export default function ServerSettings({ backendUrl }: { backendUrl: string | null }) {
  const [view, setView] = useState<SettingsView | null>(null);
  const [audit, setAudit] = useState<AuditRecord[]>([]);
  const [top, setTop] = useState<Note | null>(null);

  const apply = useCallback((r: Loaded) => {
    if (r.error) setTop({ tone: "error", text: r.error });
    if (r.view) setView(r.view);
    setAudit(r.audit);
  }, []);

  useEffect(() => {
    void fetchView(backendHttpBase(backendUrl)).then(apply);
  }, [backendUrl, apply]);

  return (
    <main className="mx-auto flex max-w-[1100px] flex-col gap-4 p-4">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Settings: game servers</h1>
        <p className="mt-1 text-sm text-neutral-400">
          The bot may act only on the servers listed here. The lab suggests the servers your game
          client is set up for; confirm them once and save. Only a person at this page can change
          the list — the bot can read it, never change it. Official game servers can never be added.
        </p>
      </div>
      {top && <p className={`rounded border px-3 py-2 text-sm ${NOTE_CLASS[top.tone]}`}>{top.text}</p>}
      {view && view.store !== "ok" && (
        <p className={`rounded border px-3 py-2 text-sm ${NOTE_CLASS.error}`}>{reasonText(view.store)}</p>
      )}
      {view &&
        view.environments.map((env) => (
          <EnvCard
            key={`${env.id}@${view.revision}`} // a new revision starts a fresh draft
            env={env}
            revision={view.revision}
            forbidden={view.forbidden}
            backendUrl={backendUrl}
            onSaved={(v, n) => {
              setView(v);
              setTop(n);
              void fetchView(backendHttpBase(backendUrl)).then(apply);
            }}
          />
        ))}
      <section className="rounded-lg border border-neutral-800 p-4">
        <h2 className="mb-2 text-sm font-semibold">Change history (last 30 days)</h2>
        {audit.length === 0 ? (
          <p className="text-sm text-neutral-400">No changes yet.</p>
        ) : (
          <ul className="flex flex-col gap-1 text-xs">
            {audit.map((r, i) => (
              <li key={`${r.t_wall}-${i}`} className={r.ok ? "text-neutral-300" : "text-red-300"}>
                <span className="font-mono text-neutral-500">{r.t_wall.slice(0, 19).replace("T", " ")} UTC</span>{" "}
                {auditText(r)}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
