"use client";

// The Maps page's side panels (docs/planning/world-map-flows.md): "Run on the maps" (matpilot's
// MatRunPanel for maps: the run's form, how it ended, its checks, and what happened, step by step)
// and the playback bar over the map view
// (matpilot's PlaybackBar: play / pause, the time, the speed; plus a step back / forward and back to
// the start). Text only: every value from the backend or the static data is rendered as React text.
//
// The checks list and the playback bar follow MatPilot's src/components/mats/MatRunPanel.tsx
// (https://github.com/lumduan/matpilot at commit d639909; MIT License, Copyright (c) 2026 Sarat
// Sonsuk; the licence text is in studio.css and THIRD_PARTY.md).
import { memo, useEffect, useRef } from "react";

import { PauseIcon, PlayIcon, StepBackIcon, StepIcon, ToStartIcon } from "@/components/maps/icons";
import type { Beat, Check, Labels, Timeline } from "@/lib/maps/play";
import { beatText } from "@/lib/maps/play";

const seconds = (s: number) => `${s.toFixed(1)} s`;

// --- the run --------------------------------------------------------------------------------------
/** `from`: the node Simulate starts at ("" = the project's start, its login node). */
export type RunForm = { from: string; seed: string; horizon: string; deathAt: string };
export const DEFAULT_RUN: RunForm = { from: "", seed: "1", horizon: "120", deathAt: "" };

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

const BeatList = memo(function BeatList({ tl, current, labels, onSeek }: { tl: Timeline; current: number; labels: Labels | null; onSeek: (t: number) => void }) {
  const list = useRef<HTMLOListElement | null>(null);
  // keep the current step in view INSIDE the list only (round 2: scrollIntoView also scrolled the
  // page, so a phone jumped from the map down to this list)
  useEffect(() => {
    const ol = list.current;
    const el = ol?.querySelector<HTMLElement>(`[data-beat="${current}"]`);
    if (!ol || !el) return;
    if (el.offsetTop < ol.scrollTop || el.offsetTop + el.offsetHeight > ol.scrollTop + ol.clientHeight) {
      ol.scrollTop = Math.max(0, el.offsetTop - ol.clientHeight / 3);
    }
  }, [current]);
  const shown = tl.beats.slice(0, 600);
  return (
    <ol className="mp-beats" ref={list} data-testid="run-steps">
      {shown.map((b: Beat) => (
        <li key={b.i} data-beat={b.i} data-current={b.i === current} data-kind={b.kind}>
          <button type="button" className="mp-beat" onClick={() => onSeek(b.t0)} title="Go to this step">
            <span className="run-time">{seconds(b.t0)}</span>
            <span className="mp-mark" data-kind={b.kind} aria-hidden="true" />
            <span>
              {b.node && b.kind !== "session" ? <span className="muted">{b.node}: </span> : null}
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
  starts,
  busy,
  onRun,
  result,
  current,
  labels,
  onSeek,
}: {
  form: RunForm;
  setForm: (f: RunForm) => void;
  starts: { id: string; map: string }[]; // the map nodes Simulate may start at (else the login)
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
            <option value="">the login node (login, character, then the first map)</option>
            {starts.map((b) => (
              <option key={b.id} value={b.id}>
                the map node {b.id} ({b.map})
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
          <PlayIcon />
          {busy ? "Simulating…" : "Simulate"}
        </button>
      </div>
      {result && (
        <div className="run-result" style={result.stale ? { opacity: 0.65 } : undefined} data-testid="run-result">
          {result.stale && <p className="notice notice-warn">The project changed after this run: Simulate again to see the new one.</p>}
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
      <button type="button" className="icon-button" onClick={onReset} title="Back to the start" aria-label="Back to the start" data-testid="playback-reset">
        <ToStartIcon />
      </button>
      <button type="button" className="icon-button" onClick={() => onStep(-1)} title="The step before" aria-label="The step before" data-testid="playback-back">
        <StepBackIcon />
      </button>
      <button type="button" className="button button-small button-file" onClick={playing ? onPause : onPlay} aria-label={playing ? "Pause" : "Play"} data-testid="playback-play">
        {playing ? <PauseIcon /> : <PlayIcon />}
        <span className="mp-play-text">{playing ? "Pause" : "Play"}</span>
      </button>
      <button type="button" className="icon-button" onClick={() => onStep(1)} title="The next step" aria-label="The next step" data-testid="playback-step">
        <StepIcon />
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
