"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  identityReasonText,
  MODE_CHOICES,
  nameProblem,
  plateRgba,
  type RememberedCharacter,
  type RunIdentityMode,
  type RunIdentityView,
} from "@/lib/runidentity";
import { backendHttpBase } from "@/lib/ws";

type Note = { tone: "ok" | "error" | "info"; text: string };

const NOTE_CLASS: Record<Note["tone"], string> = {
  ok: "border-emerald-700 bg-emerald-950 text-emerald-100",
  error: "border-red-700 bg-red-950 text-red-100",
  info: "border-neutral-700 bg-neutral-900 text-neutral-200",
};

/** The name line the bot compares, drawn from its own pixels (no image URL: the page's CSP). */
function Plate({ c }: { c: RememberedCharacter }) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  useEffect(() => {
    const px = plateRgba(c.rgb, c.w, c.h);
    const ctx = ref.current?.getContext("2d");
    if (!px || !ctx) return;
    ctx.putImageData(new ImageData(new Uint8ClampedArray(px), c.w, c.h), 0, 0);
  }, [c]);
  return (
    <canvas
      ref={ref}
      width={c.w}
      height={c.h}
      title="The name line the bot compares"
      className="rounded border border-neutral-700"
      style={{ width: c.w * 2, height: c.h * 2, imageRendering: "pixelated" }}
    />
  );
}

type Row = { id: string; name: string };
type Loaded = { view?: RunIdentityView; error?: string };

/** The section's data (no React state here: the page's effect applies it). */
async function fetchIdentity(base: string): Promise<Loaded> {
  try {
    const r = await fetch(`${base}/settings/run-identity`, { cache: "no-store" });
    const body = await r.json().catch(() => null);
    if (!r.ok) return { error: identityReasonText(body?.detail?.reason ?? `http_${r.status}`) };
    return { view: body as RunIdentityView };
  } catch {
    return { error: "The backend did not answer." };
  }
}

/** Settings: who may play a Run -- the mode and the characters remembered here (ADR-0020
 * Amendment R). Only a person at a LAN computer can change it; a Save applies to the next check
 * or Run at once (no restart). */
export default function RunIdentitySettings({ backendUrl }: { backendUrl: string | null }) {
  const [view, setView] = useState<RunIdentityView | null>(null);
  const [mode, setMode] = useState<RunIdentityMode>("any");
  const [rows, setRows] = useState<Row[]>([]);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState<"save" | "remember" | null>(null);
  const [note, setNote] = useState<Note | null>(null);
  const csrf = useRef<string | null>(null);
  const base = backendHttpBase(backendUrl);

  const take = useCallback((v: RunIdentityView) => {
    setView(v);
    setMode(v.mode);
    setRows(v.characters.map((c) => ({ id: c.id, name: c.name })));
  }, []);

  const apply = useCallback(
    (l: Loaded) => {
      if (l.error) setNote({ tone: "error", text: l.error });
      if (l.view) take(l.view);
    },
    [take],
  );

  const reload = useCallback(() => fetchIdentity(base).then(apply), [base, apply]);

  useEffect(() => {
    void fetchIdentity(base).then(apply);
  }, [base, apply]);

  /** One write with the CSRF token (a stale token is fetched again once). */
  const send = useCallback(
    async (method: "PUT" | "POST", path: string, body: unknown): Promise<{ ok: boolean; body: unknown; status: number }> => {
      const once = async (): Promise<Response> => {
        if (!csrf.current) {
          const t = await fetch(`${base}/settings/csrf`, { cache: "no-store" });
          csrf.current = t.ok ? ((await t.json()) as { token: string }).token : "";
        }
        return fetch(`${base}${path}`, {
          method,
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

  const refusal = (body: unknown, status: number): string => {
    const d = (body as { detail?: { reason?: string; detail?: unknown } } | null)?.detail ?? {};
    return identityReasonText(d.reason ?? `http_${status}`, d.detail);
  };

  const save = async () => {
    if (!view) return;
    for (const r of rows) {
      const why = nameProblem(r.name, view.max_name, rows.filter((o) => o.id !== r.id).map((o) => o.name));
      if (why) {
        setNote({ tone: "error", text: `${r.name || "A character"}: ${why}` });
        return;
      }
    }
    setBusy("save");
    try {
      const r = await send("PUT", "/settings/run-identity", { base_revision: view.revision, mode, characters: rows });
      if (!r.ok) {
        setNote({ tone: "error", text: `Not saved: ${refusal(r.body, r.status)}` });
        if (r.status === 409) void reload();
        return;
      }
      const v = r.body as RunIdentityView;
      take(v);
      const what = (v.changes ?? []).map((c) => c.text).join("; ");
      setNote({ tone: "ok", text: v.saved ? `Saved ✓ (revision ${v.revision}): ${what}. The next check or Run uses it.` : "Nothing changed." });
    } catch {
      setNote({ tone: "error", text: "The backend did not answer: nothing was saved." });
    } finally {
      setBusy(null);
    }
  };

  const remember = async () => {
    if (!view) return;
    const why = nameProblem(newName, view.max_name, view.characters.map((c) => c.name));
    if (why) {
      setNote({ tone: "error", text: why });
      return;
    }
    setBusy("remember");
    setNote({ tone: "info", text: "Reading the name line of the character on screen…" });
    try {
      const r = await send("POST", "/settings/run-identity/remember", { base_revision: view.revision, name: newName });
      if (!r.ok) {
        setNote({ tone: "error", text: `Not remembered: ${refusal(r.body, r.status)}` });
        if (r.status === 409) void reload();
        return;
      }
      take(r.body as RunIdentityView);
      setNote({ tone: "ok", text: `Remembered ${newName} ✓ — check the picture below: it must show the character's name.` });
      setNewName("");
    } catch {
      setNote({ tone: "error", text: "The backend did not answer: nothing was remembered." });
    } finally {
      setBusy(null);
    }
  };

  const changed =
    view !== null &&
    (mode !== view.mode ||
      rows.length !== view.characters.length ||
      rows.some((r, i) => r.id !== view.characters[i]?.id || r.name !== view.characters[i]?.name));
  const byId = new Map((view?.characters ?? []).map((c) => [c.id, c]));

  return (
    <section className="mx-auto flex max-w-[1100px] flex-col gap-3 p-4 pb-0" data-testid="run-identity">
      <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4">
        <h1 className="text-lg font-semibold tracking-tight">Settings: who may play a Run</h1>
        <p className="mt-1 text-sm text-neutral-400">
          The first line of a Run&apos;s check asks who is on screen. Choose how strict it is. A Save works at once: the next
          check or Run uses it, with no restart.
        </p>
        {view?.store === "unreadable" && (
          <p className={`mt-2 rounded border px-3 py-2 text-sm ${NOTE_CLASS.error}`}>
            The saved file does not parse ({view.problem}), so every Run&apos;s check fails. Choose a mode and Save to replace it.
          </p>
        )}
        <fieldset className="mt-3 flex flex-col gap-2">
          {MODE_CHOICES.map((m) => (
            <label key={m.mode} className="flex cursor-pointer items-start gap-2 text-sm">
              <input type="radio" name="run-identity-mode" className="mt-1" checked={mode === m.mode} onChange={() => setMode(m.mode)} />
              <span>
                <span className="font-semibold text-neutral-100">{m.title}</span>
                <span className="block text-xs text-neutral-400">{m.help}</span>
              </span>
            </label>
          ))}
        </fieldset>

        <h2 className="mt-4 text-sm font-semibold text-neutral-200">Characters remembered here</h2>
        {rows.length === 0 ? (
          <p className="mt-1 text-sm text-neutral-500">None yet. {mode === "known" && "With this mode every Run is refused until you remember one."}</p>
        ) : (
          <ul className="mt-1 flex flex-col gap-1">
            {rows.map((r) => {
              const c = byId.get(r.id);
              return (
                <li key={r.id} className="flex flex-wrap items-center gap-3 rounded bg-neutral-950 px-3 py-1.5 text-sm">
                  {c && <Plate c={c} />}
                  <input
                    value={r.name}
                    aria-label="The character's name"
                    maxLength={view?.max_name ?? 24}
                    onChange={(e) => setRows(rows.map((o) => (o.id === r.id ? { ...o, name: e.target.value } : o)))}
                    className="w-48 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm text-neutral-100"
                  />
                  {c && <span className="text-xs text-neutral-500">remembered {new Date(c.remembered).toLocaleString()}</span>}
                  <button
                    type="button"
                    onClick={() => setRows(rows.filter((o) => o.id !== r.id))}
                    className="ml-auto rounded border border-neutral-700 px-2 py-0.5 text-xs text-neutral-300 hover:bg-neutral-800"
                  >
                    Forget
                  </button>
                </li>
              );
            })}
          </ul>
        )}

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={!changed || busy !== null}
            onClick={() => void save()}
            className="rounded bg-sky-700 px-3 py-1 text-sm font-semibold text-white hover:bg-sky-600 disabled:opacity-40"
          >
            {busy === "save" ? "Saving…" : "Save"}
          </button>
          {changed && (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => view && take(view)}
              className="rounded border border-neutral-700 px-3 py-1 text-sm text-neutral-200 hover:bg-neutral-800"
            >
              Cancel changes
            </button>
          )}
        </div>

        <div className="mt-4 rounded border border-neutral-800 p-3">
          <h2 className="text-sm font-semibold text-neutral-200">Remember the character on screen</h2>
          <p className="mt-1 text-xs text-neutral-400">
            Put the character in the game, in front, with the Basic Info window (name, level, job) open at the top left.
            Type a name for the list and press Remember: the bot reads only the name line (116 × 14 pixels), once, now.
            Nothing is cut at any other time. The list name is yours to choose (any language); the bot compares the
            picture. Remember again if you change the game&apos;s screen size (window ↔ fullscreen).
          </p>
          {view && !view.helper_alive && (
            <p className="mt-2 text-xs text-amber-200">The Run helper is not running, so the game screen cannot be read now.</p>
          )}
          {changed && <p className="mt-2 text-xs text-amber-200">Save or cancel the changes above first.</p>}
          <div className="mt-2 flex flex-wrap items-end gap-2">
            <label className="flex flex-col text-xs text-neutral-400">
              Name for the list
              <input
                value={newName}
                maxLength={view?.max_name ?? 24}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. the character's name"
                className="mt-1 w-56 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm text-neutral-100"
              />
            </label>
            <button
              type="button"
              disabled={!view || !view.helper_alive || changed || busy !== null || !newName.trim()}
              onClick={() => void remember()}
              className="rounded bg-emerald-700 px-3 py-1 text-sm font-semibold text-white hover:bg-emerald-600 disabled:opacity-40"
            >
              {busy === "remember" ? "Reading…" : "Remember"}
            </button>
          </div>
        </div>
        {note && <p className={`mt-3 rounded border px-3 py-2 text-sm ${NOTE_CLASS[note.tone]}`}>{note.text}</p>}
      </div>
    </section>
  );
}
