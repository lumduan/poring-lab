"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import GameFileFinder from "@/components/GameFileFinder";
import {
  type AuditRecord,
  auditText,
  badgeText,
  cdnWarning,
  describeServer,
  type EnvInput,
  type EnvType,
  type EnvView,
  groupSuggestions,
  notReadyText,
  parseForbidden,
  reasonText,
  type SettingsView,
  toInputs,
  unblockReady,
  validateEntry,
} from "@/lib/settings";
import { backendHttpBase } from "@/lib/ws";

type Note = { tone: "ok" | "error" | "info"; text: string };
type Extra = { reason?: string; confirm?: string; source?: "page" | "import" };
type Save = (envs: EnvInput[], extra?: Extra) => Promise<string | null>; // the error text, or null

const NOTE_CLASS: Record<Note["tone"], string> = {
  ok: "border-emerald-700 bg-emerald-950 text-emerald-100",
  error: "border-red-700 bg-red-950 text-red-100",
  info: "border-neutral-700 bg-neutral-900 text-neutral-200",
};

const BADGE_CLASS: Record<EnvType, string> = {
  allowed: "bg-emerald-900 text-emerald-100",
  forbidden: "bg-red-900 text-red-100",
  pending: "bg-amber-900 text-amber-100",
};

const TYPE_HELP: Record<EnvType, string> = {
  allowed: "Allowed: the bot may act while the game is connected to one of these servers.",
  forbidden: "Forbidden: the bot never acts here, and these servers can never be allowed anywhere.",
  pending: "Pending: not approved; the bot never acts here.",
};

/** A LAN address (RFC 1918); anything else -- a public IP or a name -- gets the warning. */
function onLan(host: string): boolean {
  const m = /^(\d+)\.(\d+)\.\d+\.\d+$/.exec(host);
  if (!m) return false;
  const [a, b] = [Number(m[1]), Number(m[2])];
  return a === 10 || (a === 192 && b === 168) || (a === 172 && b >= 16 && b <= 31);
}

function Why({ text }: { text: string }) {
  if (!text) return null;
  return (
    <details className="text-xs text-neutral-500">
      <summary className="cursor-pointer select-none">why?</summary>
      <span>{text}</span>
    </details>
  );
}

/** The HARD path (loosening a forbidden list): a typed reason and the subject typed again. */
function HardPanel({
  title,
  subject,
  onConfirm,
  onCancel,
}: {
  title: string;
  subject: string;
  onConfirm: (reason: string, confirm: string) => Promise<string | null>;
  onCancel: () => void;
}) {
  const [reason, setReason] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const ready = unblockReady(subject.toLowerCase(), reason, confirm.toLowerCase());
  return (
    <div className="mt-2 rounded border border-red-800 bg-red-950/40 p-3 text-sm">
      <p className="font-semibold text-red-200">{title}</p>
      <p className="mt-1 text-xs text-red-200/80">
        This loosens a forbidden list, so the bot could act somewhere it never could before. It is
        recorded with your reason.
      </p>
      <label className="mt-2 flex flex-col text-xs text-neutral-300">
        Why? (at least 10 characters)
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="mt-1 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm"
          rows={2}
        />
      </label>
      <label className="mt-2 flex flex-col text-xs text-neutral-300">
        Type <span className="font-mono text-neutral-100">{subject}</span> to confirm
        <input
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          className="mt-1 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-sm"
        />
      </label>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          disabled={!ready}
          onClick={async () => setError(await onConfirm(reason, confirm))}
          className="rounded bg-red-700 px-3 py-1 text-sm font-semibold text-white hover:bg-red-600 disabled:opacity-40"
        >
          Confirm
        </button>
        <button type="button" onClick={onCancel} className="rounded border border-neutral-700 px-3 py-1 text-sm">
          Cancel
        </button>
      </div>
      {error && <p className="mt-2 text-xs text-red-300">{error}</p>}
    </div>
  );
}

type Hard = { title: string; subject: string; envs: EnvInput[] } | null;

function EnvCard({ env, view, save }: { env: EnvView; view: SettingsView; save: Save }) {
  const [host, setHost] = useState("");
  const [port, setPort] = useState("");
  const [note, setNote] = useState<Note | null>(null);
  const [hard, setHard] = useState<Hard>(null);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(env.name);
  const [summary, setSummary] = useState(env.summary);

  const all = toInputs(view);
  const mine = (f: (e: EnvInput) => EnvInput | null): EnvInput[] =>
    all.flatMap((e) => {
      if (e.id !== env.id) return [e];
      const changed = f(e);
      return changed ? [changed] : [];
    });
  const run = async (envs: EnvInput[], extra?: Extra) => {
    const error = await save(envs, extra);
    setNote(error ? { tone: "error", text: error } : null);
    return error;
  };

  const removeServer = (key: string) => {
    const envs = mine((e) => ({ ...e, servers: e.servers.filter((s) => (s.port === null ? s.host : `${s.host}:${s.port}`) !== key) }));
    if (env.type === "forbidden") {
      setHard({ title: `Unblock ${key} in “${env.name}”`, subject: key, envs });
    } else {
      void run(envs);
    }
  };

  const addAllowed = (h: string, ports: number[], source: "manual" | "discovered") => {
    const outside = !onLan(h);
    if (outside && !window.confirm(`${h} is outside your network. The bot will act on this server. Are you sure?`)) return;
    void run(mine((e) => ({ ...e, servers: [...e.servers, ...ports.map((p) => ({ host: h, port: p, note: "", source }))] })));
  };

  const addFromForm = () => {
    if (env.type === "allowed") {
      const v = validateEntry(host, port, view.forbidden);
      if (v.error) return setNote({ tone: "error", text: reasonText(v.error) });
      addAllowed(v.host, [v.port], "manual");
    } else {
      const entry = parseForbidden(port.trim() ? `${host.trim()}:${port.trim()}` : host);
      if (!entry) return setNote({ tone: "error", text: reasonText("bad_forbidden_entry") });
      const [h, p] = entry.startsWith(".") || !entry.includes(":") ? [entry, null] : [entry.slice(0, entry.lastIndexOf(":")), Number(entry.slice(entry.lastIndexOf(":") + 1))];
      void run(mine((e) => ({ ...e, servers: [...e.servers, { host: h, port: p, note: "" }] })));
    }
    setHost("");
    setPort("");
  };

  const changeType = (to: EnvType) => {
    if (to === env.type) return;
    const envs = mine((e) => ({ ...e, type: to }));
    if (env.type === "forbidden") {
      setHard({ title: `Change “${env.name}” from Forbidden to ${to}`, subject: env.name, envs });
    } else if (to === "allowed") {
      if (window.confirm(`Allow “${env.name}”? The bot may then act on its servers.`)) void run(envs);
    } else {
      void run(envs);
    }
  };

  const remove = () => {
    const envs = mine(() => null);
    if (env.type === "forbidden") {
      setHard({ title: `Delete the forbidden environment “${env.name}”`, subject: env.name, envs });
    } else if (window.confirm(`Delete “${env.name}”?`)) {
      void run(envs);
    }
  };

  const notReady = notReadyText(env);
  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4">
      <header className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold">{env.name}</h2>
          {env.summary && <p className="text-sm text-neutral-300">{env.summary}</p>}
          <Why text={env.why} />
        </div>
        <span className={`rounded px-2 py-0.5 text-xs font-semibold ${BADGE_CLASS[env.type]}`} title={TYPE_HELP[env.type]}>
          {badgeText(env)}
        </span>
      </header>
      {notReady && <p className="mb-2 rounded border border-amber-800 bg-amber-950/50 px-3 py-1.5 text-sm text-amber-100">{notReady}</p>}

      <h3 className="mb-1 text-sm font-semibold text-neutral-200">
        {env.type === "forbidden" ? "Blocked servers" : env.type === "allowed" ? "Servers the bot may use" : "Servers (not approved)"}
      </h3>
      {env.servers.length === 0 ? (
        <p className="text-sm text-neutral-500">None.</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {env.servers.map((s) => {
            const cdn = cdnWarning(s);
            return (
              <li key={s.key} className="rounded bg-neutral-950 px-3 py-1.5 text-sm">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="font-mono">{describeServer(s)}</span>
                  {s.resolved.length > 0 && (
                    <span className="text-xs text-neutral-400">= {s.resolved.map((r) => r.ip).join(", ")}</span>
                  )}
                  <span className="text-xs text-neutral-500">
                    {s.source === "default" ? "from the shipped settings" : s.added_by ? `added ${s.added_at.slice(0, 10)} from ${s.added_by}${s.source === "file" && s.note ? ` (${s.note})` : ""}` : ""}
                  </span>
                  <button
                    type="button"
                    onClick={() => removeServer(s.key)}
                    className={`ml-auto rounded border px-2 py-0.5 text-xs ${env.type === "forbidden" ? "border-red-800 text-red-200 hover:bg-red-950" : "border-neutral-700 hover:bg-neutral-800"}`}
                  >
                    {env.type === "forbidden" ? "Unblock…" : "Remove"}
                  </button>
                </div>
                {s.forbidden && <p className="mt-1 text-xs text-red-300">This server is on a forbidden list: the bot ignores it.</p>}
                {cdn && <p className="mt-1 text-xs text-amber-300">{cdn}</p>}
              </li>
            );
          })}
        </ul>
      )}

      {env.type === "allowed" && env.suggestions.length > 0 && (
        <div className="mt-3">
          <h3 className="mb-1 text-sm font-semibold text-neutral-200">Found by the lab</h3>
          <p className="mb-1 text-xs text-neutral-400">Suggestions only: nothing is allowed until you confirm it.</p>
          {groupSuggestions(env.suggestions).map((g) => (
            <div key={g.host} className="flex flex-wrap items-center gap-2 rounded border border-dashed border-neutral-700 px-3 py-1.5 text-sm">
              <span className="font-mono">{g.host}</span>
              <span className="text-xs text-neutral-400">ports {g.ports.join(", ")}</span>
              {g.ports.map((p) => (
                <button key={p} type="button" onClick={() => addAllowed(g.host, [p], "discovered")} className="rounded border border-sky-800 px-2 py-0.5 text-xs text-sky-200">
                  Confirm {p}
                </button>
              ))}
              {g.ports.length > 1 && (
                <button type="button" onClick={() => addAllowed(g.host, g.ports, "discovered")} className="ml-auto rounded bg-sky-700 px-2 py-0.5 text-xs font-semibold text-white">
                  Confirm all
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <form
        className="mt-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          addFromForm();
        }}
      >
        <label className="flex flex-col text-xs text-neutral-400">
          {env.type === "allowed" ? "Server address" : "Server, or .domain for a whole domain"}
          <input value={host} onChange={(e) => setHost(e.target.value)} className="mt-1 w-64 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm text-neutral-100" />
        </label>
        <label className="flex flex-col text-xs text-neutral-400">
          {env.type === "allowed" ? "Port" : "Port (empty = every port)"}
          <input value={port} onChange={(e) => setPort(e.target.value)} inputMode="numeric" className="mt-1 w-24 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm text-neutral-100" />
        </label>
        <button type="submit" className="rounded border border-neutral-600 px-3 py-1 text-sm hover:bg-neutral-800">
          {env.type === "forbidden" ? "Block" : "Add"}
        </button>
      </form>

      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-neutral-800 pt-3 text-xs">
        <label className="flex items-center gap-1 text-neutral-400">
          Type
          <select value={env.type} onChange={(e) => changeType(e.target.value as EnvType)} className="rounded border border-neutral-700 bg-neutral-950 px-1 py-0.5 text-neutral-100">
            <option value="allowed">Allowed</option>
            <option value="forbidden">Forbidden</option>
            <option value="pending">Pending</option>
          </select>
        </label>
        <button type="button" onClick={() => setEditing(!editing)} className="rounded border border-neutral-700 px-2 py-0.5">
          Rename / describe
        </button>
        <button type="button" onClick={remove} className="ml-auto rounded border border-neutral-700 px-2 py-0.5 text-neutral-300 hover:bg-neutral-800">
          Delete environment
        </button>
      </div>
      {editing && (
        <form
          className="mt-2 flex flex-col gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!(await run(mine((x) => ({ ...x, name, summary }))))) setEditing(false);
          }}
        >
          <input value={name} onChange={(e) => setName(e.target.value)} className="rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm" />
          <input value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="One sentence, plain words" className="rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm" />
          <button type="submit" className="self-start rounded border border-neutral-600 px-3 py-1 text-sm">Save name</button>
        </form>
      )}
      {hard && (
        <HardPanel
          title={hard.title}
          subject={hard.subject}
          onCancel={() => setHard(null)}
          onConfirm={async (reason, confirm) => {
            const error = await run(hard.envs, { reason, confirm });
            if (!error) setHard(null);
            return error;
          }}
        />
      )}
      {note && <p className={`mt-3 rounded border px-3 py-2 text-sm ${NOTE_CLASS[note.tone]}`}>{note.text}</p>}
    </section>
  );
}

function NewEnvironment({ view, save }: { view: SettingsView; save: Save }) {
  const [name, setName] = useState("");
  const [type, setType] = useState<EnvType>("forbidden"); // the safe default
  const [summary, setSummary] = useState("");
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="flex flex-wrap items-end gap-2 rounded-lg border border-neutral-800 p-4"
      onSubmit={async (e) => {
        e.preventDefault();
        const env: EnvInput = { id: null, name: name.trim(), type, summary: summary.trim(), why: "", servers: [] };
        const err = await save([...toInputs(view), env]);
        setError(err);
        if (!err) {
          setName("");
          setSummary("");
        }
      }}
    >
      <h2 className="w-full text-sm font-semibold">New environment</h2>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name, e.g. Old Asiasoft Thai RO" className="w-72 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm" />
      <select value={type} onChange={(e) => setType(e.target.value as EnvType)} className="rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm">
        <option value="forbidden">Forbidden</option>
        <option value="allowed">Allowed</option>
        <option value="pending">Pending</option>
      </select>
      <input value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="One sentence: what is it?" className="min-w-64 flex-1 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm" />
      <button type="submit" disabled={!name.trim()} className="rounded border border-neutral-600 px-3 py-1 text-sm disabled:opacity-40">Create</button>
      <p className="w-full text-xs text-neutral-500">{TYPE_HELP[type]}</p>
      {error && <p className="w-full text-sm text-red-300">{error}</p>}
    </form>
  );
}

function ImportExport({ save, backendUrl }: { save: Save; backendUrl: string | null }) {
  const [pending, setPending] = useState<EnvInput[] | null>(null);
  const [msg, setMsg] = useState<Note | null>(null);
  const exportSet = async () => {
    const r = await fetch(`${backendHttpBase(backendUrl)}/settings/environments/export`, { cache: "no-store" });
    if (!r.ok) return setMsg({ tone: "error", text: "Export failed." });
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = "poring-lab-environments.json";
    a.click();
    URL.revokeObjectURL(url);
  };
  const readImport = async (file: File) => {
    try {
      if (file.size > 60_000) throw new Error("too large");
      const doc = JSON.parse(await file.text());
      if (doc?.format !== "poring-lab-environments/1" || !Array.isArray(doc.environments)) throw new Error("format");
      const envs: EnvInput[] = doc.environments.map((e: EnvInput) => ({
        id: typeof e.id === "string" ? e.id : null, name: String(e.name ?? ""), type: e.type,
        summary: String(e.summary ?? ""), why: String(e.why ?? ""),
        servers: Array.isArray(e.servers) ? e.servers.map((s) => ({ host: String(s.host ?? ""), port: typeof s.port === "number" ? s.port : null, note: String(s.note ?? "") })) : [],
      }));
      setPending(envs);
      setMsg({ tone: "info", text: `${file.name}: ${envs.length} environments. Applying it replaces the whole current set (same rules as editing).` });
    } catch {
      setPending(null);
      setMsg({ tone: "error", text: "That is not an environments file exported from a poring-lab console." });
    }
  };
  return (
    <section className="flex flex-wrap items-center gap-2 rounded-lg border border-neutral-800 p-4 text-sm">
      <h2 className="w-full text-sm font-semibold">Share a setup</h2>
      <button type="button" onClick={() => void exportSet()} className="rounded border border-neutral-600 px-3 py-1">Export all (one file)</button>
      <label className="rounded border border-neutral-600 px-3 py-1">
        Import…
        <input type="file" accept=".json,application/json" className="hidden" onChange={(e) => e.target.files?.[0] && void readImport(e.target.files[0])} />
      </label>
      {pending && (
        <button
          type="button"
          onClick={async () => {
            const err = await save(pending, { source: "import" });
            setMsg(err ? { tone: "error", text: `${err} An import that loosens a forbidden list must be done by hand, one change at a time.` } : { tone: "ok", text: "Imported." });
            if (!err) setPending(null);
          }}
          className="rounded bg-sky-700 px-3 py-1 font-semibold text-white"
        >
          Apply import
        </button>
      )}
      {msg && <p className={`w-full rounded border px-3 py-2 ${NOTE_CLASS[msg.tone]}`}>{msg.text}</p>}
    </section>
  );
}

type Loaded = { view?: SettingsView; audit: AuditRecord[]; error?: string };

/** The page's data: the set and the change history (no React state here). */
async function fetchView(base: string): Promise<Loaded> {
  try {
    const [s, a] = await Promise.all([
      fetch(`${base}/settings/environments`, { cache: "no-store" }),
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

/** Settings: the environments -- where the bot may act, and where it never may. People manage
 * them here; the bot can read them but never change them (the backend enforces both). */
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

  const csrf = useRef<string | null>(null);

  const save: Save = useCallback(
    async (envs, extra = {}) => {
      const base = backendHttpBase(backendUrl);
      // Every write carries the CSRF token only this page can read (CORS); a backend restart
      // invalidates it, so one refusal fetches a fresh token and tries once more.
      const put = async (): Promise<Response> => {
        if (!csrf.current) {
          const t = await fetch(`${base}/settings/csrf`, { cache: "no-store" });
          csrf.current = t.ok ? ((await t.json()) as { token: string }).token : "";
        }
        return fetch(`${base}/settings/environments`, {
          method: "PUT",
          headers: { "content-type": "application/json", "x-csrf-token": csrf.current ?? "" },
          body: JSON.stringify({
            base_revision: view?.revision ?? 0, environments: envs, reason: extra.reason ?? "",
            confirm: extra.confirm ?? "", source: extra.source ?? "page",
          }),
        });
      };
      try {
        let r = await put();
        if (r.status === 403) {
          const peek = await r.clone().json().catch(() => null);
          if (peek?.detail?.reason === "csrf_invalid") {
            csrf.current = null;
            r = await put();
          }
        }
        const body = await r.json().catch(() => null);
        if (!r.ok) {
          const d = body?.detail ?? {};
          const what = d.entry ? ` (${d.entry})` : d.subject && d.reason === "confirm_mismatch" ? ` Type “${d.subject}”.` : "";
          return `Not saved: ${reasonText(d.reason ?? `http_${r.status}`)}${what}`;
        }
        const v = body as SettingsView;
        setView(v);
        const changes = (v.changes ?? []).map((c) => c.text).join("; ");
        setTop({ tone: "ok", text: v.saved ? `Saved and checked ✓ (revision ${v.revision}): ${changes}` : "Nothing changed." });
        void fetchView(base).then((x) => setAudit(x.audit));
        return null;
      } catch {
        return "The backend did not answer: nothing was saved.";
      }
    },
    [backendUrl, view],
  );

  return (
    <main className="mx-auto flex max-w-[1100px] flex-col gap-4 p-4">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Settings: environments</h1>
        <p className="mt-1 text-sm text-neutral-400">
          An environment is a game service: <b>Allowed</b> (the bot may act there), <b>Forbidden</b>{" "}
          (never; its servers can never be allowed anywhere) or <b>Pending</b> (not approved). Only a
          person at their own computer can change them; the bot can only read them. Blocking is
          always easy; unblocking needs a reason.
        </p>
      </div>
      {top && <p className={`rounded border px-3 py-2 text-sm ${NOTE_CLASS[top.tone]}`}>{top.text}</p>}
      {view && view.store !== "ok" && (
        <p className={`rounded border px-3 py-2 text-sm ${NOTE_CLASS.error}`}>{reasonText(view.store)}</p>
      )}
      {view?.environments.map((env) => (
        <EnvCard key={`${env.id}@${view.revision}`} env={env} view={view} save={save} />
      ))}
      {view && view.store === "ok" && <NewEnvironment key={`new@${view.revision}`} view={view} save={save} />}
      {view && view.store === "ok" && <GameFileFinder key={`finder@${view.revision}`} view={view} save={save} />}
      {view && view.store === "ok" && <ImportExport save={save} backendUrl={backendUrl} />}
      <section className="rounded-lg border border-neutral-800 p-4">
        <h2 className="mb-2 text-sm font-semibold">Change history (last 30 days)</h2>
        {audit.length === 0 ? (
          <p className="text-sm text-neutral-400">No changes yet.</p>
        ) : (
          <ul className="flex flex-col gap-1 text-xs">
            {audit.map((r, i) => (
              <li key={`${r.t_wall}-${i}`} className={!r.ok ? "text-red-300" : r.kind === "hard" ? "text-amber-300" : "text-neutral-300"}>
                <span className="font-mono text-neutral-500">{r.t_wall.slice(0, 19).replace("T", " ")} UTC</span> {auditText(r)}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
