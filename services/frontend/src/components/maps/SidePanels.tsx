"use client";

// The Maps page's side panels (docs/planning/world-map-flows.md): the session's two MOCK nodes
// (Login, Choose character), "Run on the maps" (matpilot's MatRunPanel for maps: the run's form,
// how it ended, its checks, and what happened, step by step) and the playback bar over the map view
// (matpilot's PlaybackBar: play / pause, the time, the speed; plus a step back / forward and back to
// the start). Text only: every value from the backend or the static data is rendered as React text.
//
// The checks list and the playback bar follow MatPilot's src/components/mats/MatRunPanel.tsx
// (https://github.com/lumduan/matpilot at commit d639909; MIT License, Copyright (c) 2026 Sarat
// Sonsuk; the licence text is in studio.css and THIRD_PARTY.md).
import { memo, useEffect, useRef } from "react";

import type { Beat, Check, Labels, Timeline } from "@/lib/maps/play";
import { beatText } from "@/lib/maps/play";
import { ACCOUNTS, CHAR_NAME, MAX_SLOT, type Session, SERVERS, sessionSteps } from "@/lib/maps/session";

const seconds = (s: number) => `${s.toFixed(1)} s`;

export function LoginPanel({ session, onSession }: { session: Session; onSession: (s: Session) => void }) {
  return (
    <div className="stack">
      <p className="notice notice-warn">
        <strong>A mock.</strong> This page never logs in: Simulate plays these steps. The bot&apos;s real login is <code>scripts/ro_agent.py</code>{" "}
        <code>to_char_select(agent, screen, which)</code>.
      </p>
      <fieldset className="mp-fieldset">
        <legend>Server</legend>
        {SERVERS.map((s) => (
          <label key={s.id} className="mp-choice" data-disabled={!s.automatable}>
            <input type="radio" name="server" value={s.id} checked={session.server === s.id} disabled={!s.automatable} onChange={() => onSession({ ...session, server: s.id })} />
            <span>
              <span className="strong">{s.title}</span> <span className="muted">· {s.status}</span>
              <span className="mp-why">{s.automatable ? s.why : `Not selectable: ${s.why}.`}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <label className="mp-field">
        <span className="strong">Account</span>
        <select value={session.account} onChange={(e) => onSession({ ...session, account: e.target.value === "player" ? "player" : "gm" })} data-testid="login-account">
          {ACCOUNTS.map((a) => (
            <option key={a.id} value={a.id}>
              {a.title} ({a.id})
            </option>
          ))}
        </select>
        <span className="muted">
          The lab account from the server: its id and password are in {ACCOUNTS.find((a) => a.id === session.account)?.env}. This page never asks for them, stores them or
          shows them.
        </span>
      </label>
    </div>
  );
}

export function CharacterPanel({ session, onSession }: { session: Session; onSession: (s: Session) => void }) {
  const bad = session.char !== "" && !CHAR_NAME.test(session.char);
  return (
    <div className="stack">
      <p className="notice notice-warn">
        <strong>A mock.</strong> The bot&apos;s real step is <code>enter_game(agent, screen, which, char=None)</code>: Enter on the slot the client remembers, then it waits until the
        database says the character is online and checks the chat window.
      </p>
      <label className="mp-field">
        <span className="strong">Slot</span>
        <select
          value={session.slot === null ? "" : String(session.slot)}
          onChange={(e) => onSession({ ...session, slot: e.target.value === "" ? null : Number(e.target.value) })}
          data-testid="character-slot"
        >
          <option value="">the remembered slot (as the bot does)</option>
          {Array.from({ length: MAX_SLOT }, (_, i) => i + 1).map((n) => (
            <option key={n} value={n}>
              slot {n} (selected first, by hand)
            </option>
          ))}
        </select>
      </label>
      <label className="mp-field">
        <span className="strong">Character name (optional)</span>
        <input value={session.char} maxLength={23} placeholder="the account's own character (.env)" onChange={(e) => onSession({ ...session, char: e.target.value })} aria-invalid={bad} />
        <span className={bad ? "err-text" : "muted"}>
          {bad ? "Letters, digits, spaces and _ only, at most 23." : "The character that slot holds, when it is not the account's own: enter_game checks it is one of the account's characters."}
        </span>
      </label>
    </div>
  );
}

export function StartPanel({ session }: { session: Session }) {
  const steps = sessionSteps(session);
  return (
    <div className="stack">
      <p>START is where every run begins: the Ragnarok client open on its login screen. Then the two MOCK steps, then the first map.</p>
      <ol className="mp-steps">
        {steps.map((s) => (
          <li key={s.node}>
            <span className="muted">{seconds(s.t0)}</span> {s.text} <code>{s.call}</code>
          </li>
        ))}
      </ol>
      <p className="muted">The times are illustrative (a mock); the real login waits on the client and the database.</p>
    </div>
  );
}

// --- the run --------------------------------------------------------------------------------------
export type RunForm = { from: string; seed: string; horizon: string; deathAt: string };
export const DEFAULT_RUN: RunForm = { from: "login", seed: "1", horizon: "120", deathAt: "" };

const Checks = memo(function Checks({ checks }: { checks: Check[] }) {
  return (
    <ul className="robot-checks" data-testid="run-checks">
      {checks.map((c) => (
        <li key={c.text} data-ok={c.ok === null ? "unknown" : String(c.ok)}>
          <span className="robot-check-mark" aria-hidden="true">
            {c.ok === null ? "?" : c.ok ? "✓" : "✗"}
          </span>
          <span>{c.text}</span>
        </li>
      ))}
    </ul>
  );
});

const KIND_MARK: Record<string, string> = {
  session: "◆",
  walk: "→",
  talk: "❝",
  menu: "≡",
  fight: "✕",
  item: "◇",
  loot: "✦",
  respawn: "✝",
  act: "•",
  wait: "…",
  exit: "⇒",
  arrive: "⇒",
};

const BeatList = memo(function BeatList({ tl, current, labels, onSeek }: { tl: Timeline; current: number; labels: Labels | null; onSeek: (t: number) => void }) {
  const list = useRef<HTMLOListElement | null>(null);
  useEffect(() => {
    const el = list.current?.querySelector<HTMLElement>(`[data-beat="${current}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [current]);
  const shown = tl.beats.slice(0, 600);
  return (
    <ol className="mp-beats" ref={list} data-testid="run-steps">
      {shown.map((b: Beat) => (
        <li key={b.i} data-beat={b.i} data-current={b.i === current} data-kind={b.kind}>
          <button type="button" className="mp-beat" onClick={() => onSeek(b.t0)} title="Go to this step">
            <span className="run-time">{seconds(b.t0)}</span>
            <span className="mp-mark" aria-hidden="true">
              {KIND_MARK[b.kind] ?? "•"}
            </span>
            <span>
              {b.node.startsWith("block:") ? <span className="muted">{b.node.slice(6)}: </span> : null}
              {beatText(b, labels)}
            </span>
          </button>
        </li>
      ))}
      {tl.beats.length > shown.length && <li className="muted">…and {tl.beats.length - shown.length} more steps (the playback shows them all)</li>}
    </ol>
  );
});

export function RunPanel({
  form,
  setForm,
  blocks,
  busy,
  onRun,
  result,
  current,
  labels,
  onSeek,
}: {
  form: RunForm;
  setForm: (f: RunForm) => void;
  blocks: { name: string; map: string }[];
  busy: boolean;
  onRun: () => void;
  result: { tl: Timeline; checks: Check[]; endText: string; notes: string[]; old: boolean; stale: boolean } | null;
  current: number;
  labels: Labels | null;
  onSeek: (t: number) => void;
}) {
  return (
    <div className="stack" data-testid="run-panel">
      <p className="notice">
        <strong>A simulation:</strong> no game, no input. The bot walks the static data&apos;s walk grid; monsters are placed from the seed (not seen); NPCs stand where the static
        data puts them.
      </p>
      <div className="grid2">
        <label>
          start at
          <select className="field" value={form.from} onChange={(e) => setForm({ ...form, from: e.target.value })} data-testid="run-from">
            <option value="login">START (login, character, then the first map)</option>
            {blocks.map((b) => (
              <option key={b.name} value={b.name}>
                the map node {b.name} ({b.map})
              </option>
            ))}
          </select>
        </label>
        <label>
          monsters&apos; seed
          <input className="field" value={form.seed} inputMode="numeric" onChange={(e) => setForm({ ...form, seed: e.target.value })} title="The same seed places the same monsters" />
        </label>
        <label>
          time limit (s)
          <input className="field" value={form.horizon} inputMode="numeric" onChange={(e) => setForm({ ...form, horizon: e.target.value })} />
        </label>
        <label>
          a death at (s, empty: none)
          <input className="field" value={form.deathAt} inputMode="numeric" onChange={(e) => setForm({ ...form, deathAt: e.target.value })} />
        </label>
      </div>
      <div className="button-row">
        <button type="button" className="button button-primary button-run" onClick={onRun} disabled={busy} data-testid="run-start">
          {busy ? "Simulating…" : "▶ Simulate"}
        </button>
      </div>
      {result && (
        <div className="run-result" style={result.stale ? { opacity: 0.65 } : undefined} data-testid="run-result">
          {result.stale && <p className="notice notice-warn">The flow changed after this run: Simulate again to see the new one.</p>}
          {result.old && (
            <p className="notice notice-warn">
              The backend is older than this page: it placed no monsters and gave no step list. The playback shows each walked route once, in order. (A backend restart brings the
              rest.)
            </p>
          )}
          <p className={result.checks.some((c) => c.ok === false) ? "notice notice-warn" : "notice notice-ok"} data-testid="run-end">
            {result.endText} after {seconds(result.tl.end)} (simulated).
          </p>
          <Checks checks={result.checks} />
          {result.notes.length > 0 && (
            <div className="notice notice-warn">
              <ul>
                {result.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </div>
          )}
          <details className="run-output" open>
            <summary>What happens ({result.tl.beats.length} steps)</summary>
            <BeatList tl={result.tl} current={current} labels={labels} onSeek={onSeek} />
          </details>
        </div>
      )}
    </div>
  );
}

// --- the playback bar --------------------------------------------------------------------------------
export const SPEEDS = [1, 2, 4, 8, 16] as const;

export function PlaybackBar({
  time,
  end,
  playing,
  speed,
  onPlay,
  onPause,
  onSeek,
  onSpeed,
  onStep,
  onReset,
}: {
  time: number;
  end: number;
  playing: boolean;
  speed: number;
  onPlay: () => void;
  onPause: () => void;
  onSeek: (t: number) => void;
  onSpeed: (s: number) => void;
  onStep: (dir: -1 | 1) => void;
  onReset: () => void;
}) {
  return (
    <div className="mat-playback" role="group" aria-label="Play back the run" data-testid="playback">
      <button type="button" className="icon-button" onClick={onReset} title="Back to the start">
        ⏮<span className="visually-hidden">Back to the start</span>
      </button>
      <button type="button" className="icon-button" onClick={() => onStep(-1)} title="The step before">
        ◀<span className="visually-hidden">The step before</span>
      </button>
      <button type="button" className="button button-small" onClick={playing ? onPause : onPlay} data-testid="playback-play">
        {playing ? "⏸ Pause" : "▶ Play"}
      </button>
      <button type="button" className="icon-button" onClick={() => onStep(1)} title="The next step" data-testid="playback-step">
        ▶<span className="visually-hidden">The next step</span>
      </button>
      <input type="range" min={0} max={Math.max(0.1, end)} step={0.1} value={Math.min(time, end)} onChange={(e) => onSeek(Number(e.target.value))} aria-label="Time" data-testid="playback-time" />
      <span className="mat-playback-time" data-testid="playback-text">
        {seconds(time)} / {seconds(end)}
      </span>
      <select className="mat-playback-speed" value={speed} onChange={(e) => onSpeed(Number(e.target.value))} aria-label="Speed">
        {SPEEDS.map((s) => (
          <option key={s} value={s}>
            {s}×
          </option>
        ))}
      </select>
    </div>
  );
}
