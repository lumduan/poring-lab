"use client";

import { useState } from "react";

import type { Found } from "@/lib/gamefile/endpoint";
import {
  allowWarning,
  applyFound,
  defaultTarget,
  initialTicks,
  keyOfFound,
  ROLE_TEXT,
  type Target,
  targetOptions,
  targetValue,
  unusable,
} from "@/lib/gamefile/plan";
import { scanInWorker } from "@/lib/gamefile/run";
import type { ScanResult } from "@/lib/gamefile/scan";
import type { EnvInput, SettingsView } from "@/lib/settings";

type Save = (envs: EnvInput[]) => Promise<string | null>;

/** "Find servers from a game file" (Batt, 2026-10-06). The file is read IN THIS BROWSER, by a
 * Web Worker, by slices; nothing is uploaded. Only the endpoints the person ticks are sent, and
 * only when they press the button. Every value from the file is rendered as plain text. */
export default function GameFileFinder({ view, save }: { view: SettingsView; save: Save }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [target, setTarget] = useState<Target>(defaultTarget());
  const [ticks, setTicks] = useState<Set<string>>(new Set());
  const [own, setOwn] = useState(false);
  const [name, setName] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [over, setOver] = useState(false);

  const options = targetOptions(view);
  const current = options.find((o) => o.value === targetValue(target)) ?? options[0];

  const open = async (file: File | undefined) => {
    if (!file) return;
    setBusy(file.name);
    setResult(null);
    setMsg(null);
    const r = await scanInWorker(file);
    setBusy(null);
    setResult(r);
    const t = defaultTarget();
    setTarget(t);
    setOwn(false);
    setTicks(initialTicks(r.found, t, view.forbidden));
    setName(r.display ? `Found in ${r.file}: ${r.display}` : `Found in ${r.file}`);
  };

  const choose = (value: string) => {
    const t = options.find((o) => o.value === value)?.target ?? defaultTarget();
    setTarget(t);
    setOwn(false);
    setMsg(null);
    if (result) setTicks(initialTicks(result.found, t, view.forbidden)); // Allowed: nothing pre-ticked
  };

  const toggle = (key: string) => {
    const next = new Set(ticks);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setTicks(next);
  };

  const chosen: Found[] = (result?.found ?? []).filter((f) => ticks.has(keyOfFound(f)) && !unusable(f, target, view.forbidden));

  const submit = async () => {
    if (chosen.length === 0) return;
    if (target.kind === "allowed") {
      const warning = allowWarning(chosen, target);
      if (!own || (warning && !window.confirm(warning))) return;
    }
    const err = await save(applyFound(view, target, chosen, name));
    setMsg(err ? { ok: false, text: err } : { ok: true, text: target.kind === "allowed" ? `Allowed ${chosen.length}.` : `Blocked ${chosen.length}.` });
    if (!err) setResult(null);
  };

  return (
    <section
      className={`rounded-lg border p-4 text-sm ${over ? "border-sky-500 bg-sky-950/30" : "border-neutral-800"}`}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        void open(e.dataTransfer.files?.[0]);
      }}
    >
      <h2 className="text-sm font-semibold">Find servers from a game file</h2>
      <p className="mt-1 text-xs text-neutral-400">
        Drop a <span className="font-mono">data.grf</span> (or any .grf), a <span className="font-mono">clientinfo.xml</span> /{" "}
        <span className="font-mono">sclientinfo.xml</span>, an <span className="font-mono">externalsettings</span> .lub, or the
        game&apos;s .exe here. It is read in this browser only and never uploaded; only the servers you pick are sent.
      </p>
      <label className="mt-2 inline-block cursor-pointer rounded border border-neutral-600 px-3 py-1">
        Choose a file…
        <input type="file" className="hidden" onChange={(e) => void open(e.target.files?.[0])} />
      </label>
      {busy && <p className="mt-2 text-neutral-300">Reading {busy}…</p>}

      {result && (
        <div className="mt-3 flex flex-col gap-2">
          <p className="text-neutral-300">
            <span className="font-mono">{result.file}</span>
            {result.kind === "grf" && ` — ${result.stats.entries} entries; ${result.stats.read} settings file(s) read`}
          </p>
          {result.error && <p className="rounded border border-amber-800 bg-amber-950/50 px-3 py-1.5 text-amber-100">{result.error}</p>}
          {result.notes.map((n, i) => (
            <p key={i} className="text-xs text-neutral-400">{n}</p>
          ))}

          {result.found.length > 0 && (
            <>
              <label className="flex flex-wrap items-center gap-2 text-xs text-neutral-300">
                What to do with the ticked servers
                <select value={current.value} onChange={(e) => choose(e.target.value)} className="rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm text-neutral-100">
                  {options.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </label>
              {target.kind === "new-forbidden" && (
                <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} className="w-96 max-w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm" />
              )}
              <ul className="flex flex-col gap-1">
                {result.found.map((f) => {
                  const key = keyOfFound(f);
                  const why = unusable(f, target, view.forbidden);
                  return (
                    <li key={key} className="rounded bg-neutral-950 px-3 py-1.5">
                      <label className={`flex flex-wrap items-center gap-3 ${why ? "opacity-50" : ""}`}>
                        <input type="checkbox" disabled={!!why} checked={!why && ticks.has(key)} onChange={() => toggle(key)} />
                        <span className="font-mono">{f.port === null ? `${f.host} : every port` : `${f.host} : ${f.port}`}</span>
                        <span className="text-xs text-neutral-400">{ROLE_TEXT[f.role]}</span>
                        {!f.lan && <span className="rounded bg-amber-900 px-1.5 text-xs text-amber-100">outside your network</span>}
                      </label>
                      <p className="mt-0.5 text-xs text-neutral-500">found in {f.sources.join("; ")}</p>
                      {why && <p className="text-xs text-neutral-500">Can&apos;t: {why}.</p>}
                    </li>
                  );
                })}
              </ul>
              {target.kind === "allowed" && (
                <div className="rounded border border-amber-800 bg-amber-950/40 p-3 text-amber-100">
                  <p className="font-semibold">Allowing lets the bot act on these servers.</p>
                  <p className="mt-1 text-xs">
                    Only for a private server you run, or one whose owner allows bots. A file can be crafted to make
                    you allow someone else&apos;s server: check every address. Nothing is ticked for you.
                  </p>
                  <label className="mt-2 flex items-center gap-2 text-xs">
                    <input type="checkbox" checked={own} onChange={(e) => setOwn(e.target.checked)} />
                    I run this server, or its owner allows bots on it.
                  </label>
                </div>
              )}
              <button
                type="button"
                disabled={chosen.length === 0 || (target.kind === "allowed" && !own)}
                onClick={() => void submit()}
                className={`self-start rounded px-3 py-1 font-semibold text-white disabled:opacity-40 ${target.kind === "allowed" ? "bg-amber-700 hover:bg-amber-600" : "bg-red-800 hover:bg-red-700"}`}
              >
                {target.kind === "allowed" ? `Allow the ${chosen.length} ticked…` : `Block the ${chosen.length} ticked`}
              </button>
            </>
          )}
        </div>
      )}
      {msg && <p className={`mt-2 rounded border px-3 py-2 ${msg.ok ? "border-emerald-700 bg-emerald-950 text-emerald-100" : "border-red-700 bg-red-950 text-red-100"}`}>{msg.text}</p>}
    </section>
  );
}
