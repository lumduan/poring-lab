"use client";

/**
 * Batt 2026-11-19: "add a Logs tab at the bottom of /flows, next to Hunt rules: the bot plays and
 * then stops by itself and I cannot see why; it should also tell the bot's status -- what it
 * thinks, what it will do, is it attacking a monster"; "make the time a UI I can change myself";
 * and a retry option after a code error.
 *
 * - RunOptionsBox: ONE time limit for the Run (the project's, with every hunt block `minutes`
 *   following it; lib/flow/runoptions.ts) and the retry option (this bot server's,
 *   GET/PUT /flows/run/options behind the same human-only gate as Run).
 * - LogsPanel: the Run's state, what she does (the Run helper's story of the session events, in
 *   words) and the Run's whole log tail. Display only: it never decides or sends input.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Live } from "@/components/flows/LiveRun";
import { ACTIVE, liveLabel, monitorTiles, REFUSALS } from "@/lib/flow/liverun";
import { browserStorage, KEYS, readChoice, writeChoice } from "@/lib/flow/prefs";
import type { Project } from "@/lib/flow/project";
import {
  effectiveLimitS,
  huntMinutes,
  parseHoursMinutes,
  RETRY_CHOICES,
  RETRY_WAIT_CHOICES,
  type RetryOptions,
  storyTime,
  TIME_CHOICES,
  timeWords,
  withTimeLimit,
} from "@/lib/flow/runoptions";

const btn = "button button-small";
const OPTIONS_POLL_MS = 15_000;

function useRetryOptions(base: string): { opts: RetryOptions | null; err: string | null; save: (retryMax: number, waitS: number, bagCount?: boolean) => Promise<void>; busy: boolean } {
  const [opts, setOpts] = useState<RetryOptions | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const csrf = useRef<string | null>(null);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await fetch(`${base}/flows/run/options`, { cache: "no-store" });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const doc = (await r.json()) as RetryOptions;
        if (alive) setOpts(doc);
      } catch (e) {
        if (alive) setErr(`the retry option did not load (${e instanceof Error ? e.message : String(e)})`);
      }
    };
    void load();
    const timer = setInterval(() => void load(), OPTIONS_POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [base]);
  const save = useCallback(
    async (retryMax: number, waitS: number, bagCount?: boolean) => {
      setBusy(true);
      setErr(null);
      try {
        for (let attempt = 0; attempt < 2; attempt++) {
          if (csrf.current === null) {
            const t = await fetch(`${base}/settings/csrf`, { cache: "no-store" });
            if (!t.ok) throw new Error(`the security token was refused (HTTP ${t.status})`);
            csrf.current = ((await t.json()) as { token: string }).token;
          }
          const r = await fetch(`${base}/flows/run/options`, {
            method: "PUT",
            cache: "no-store",
            headers: { "content-type": "application/json", "x-csrf-token": csrf.current },
            body: JSON.stringify({ retry_max: retryMax, retry_wait_s: waitS, ...(bagCount === undefined ? {} : { bag_count: bagCount }) }),
          });
          if (r.ok) {
            setOpts((await r.json()) as RetryOptions);
            break;
          }
          const body = (await r.json().catch(() => ({}))) as { detail?: { reason?: string; detail?: string } };
          const reason = body.detail?.reason ?? `HTTP ${r.status}`;
          if (reason === "csrf_invalid" && attempt === 0) {
            csrf.current = null;
            continue;
          }
          setErr(`${REFUSALS[reason] ?? `Refused: ${reason}`}${body.detail?.detail ? `: ${body.detail.detail}` : ""}`);
          break;
        }
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [base],
  );
  return { opts, err, save, busy };
}

/** The Run options strip: the time limit (saved with the project) and the retry (this bot
 * server's). `onProject`: the page's replace (an edit, undoable, like every other). */
export function RunOptionsBox({ project, onProject, live }: { project: Project; onProject: (p: Project) => void; live: Live }) {
  const running = ACTIVE.includes(live.st?.state ?? "");
  const own = project.max_runtime_s;
  const hunt = huntMinutes(project);
  const effective = effectiveLimitS(project);
  const preset = (TIME_CHOICES as readonly number[]).includes(own) && hunt.length === 0;
  const [custom, setCustom] = useState(!preset);
  const [hours, setHours] = useState(String(Math.floor(own / 3_600) || ""));
  const [mins, setMins] = useState(String(Math.round((own % 3_600) / 60) || ""));
  const [timeErr, setTimeErr] = useState("");
  const setTime = (secs: number) => {
    setTimeErr("");
    onProject(withTimeLimit(project, secs));
  };
  const { opts, err, save, busy } = useRetryOptions(live.base);
  // Batt 2026-11-20: "make Run options hideable: we do not look at it all the time" -- folded by
  // default, its one-line summary in the header; this browser remembers it open or folded
  const store = useMemo(() => browserStorage(), []);
  const [open, setOpen] = useState(() => readChoice(store, KEYS.runOptions, ["open", "closed"] as const, "closed") === "open");
  const summary = `${effective ? `at most ${timeWords(effective)}` : "no time limit"} · ${opts ? (opts.retry_max ? `a code error: check and hunt on (${opts.retry_max}×)` : "a code error ends it") : "…"}${opts ? ` · ${opts.bag_count === false ? "no bag count" : "the bag counted"}` : ""}`;
  return (
    <details
      className="box stack run-options"
      data-testid="run-options"
      open={open}
      onToggle={(e) => {
        const now = (e.currentTarget as HTMLDetailsElement).open;
        setOpen(now);
        writeChoice(store, KEYS.runOptions, now ? "open" : "closed");
      }}
    >
      <summary className="strong" data-testid="run-options-summary">
        Run options <span className="muted">· {summary}</span>
      </summary>
      <label>
        Time limit for the Run{" "}
        <select
          className="field"
          data-testid="run-time-limit"
          value={custom ? "custom" : String(own)}
          onChange={(e) => {
            if (e.target.value === "custom") return setCustom(true);
            setCustom(false);
            setTime(Number(e.target.value));
          }}
        >
          {TIME_CHOICES.map((s) => (
            <option key={s} value={String(s)}>
              {s ? timeWords(s) : "No time limit (until Stop, a death, a full bag or the box's own end)"}
            </option>
          ))}
          <option value="custom">Another time…</option>
        </select>
      </label>
      {custom && (
        <div className="row">
          <input className="field" inputMode="numeric" aria-label="hours" placeholder="hours" value={hours} onChange={(e) => setHours(e.target.value)} />
          <input className="field" inputMode="numeric" aria-label="minutes" placeholder="minutes" value={mins} onChange={(e) => setMins(e.target.value)} />
          <button
            className={btn}
            onClick={() => {
              const s = parseHoursMinutes(hours, mins);
              if (s === null) return setTimeErr("whole hours, and minutes 0..59 (both empty = no time limit)");
              setTime(s);
            }}
          >
            Set
          </button>
          {timeErr && <span className="err-text">{timeErr}</span>}
        </div>
      )}
      <p className="muted" data-testid="run-time-words">
        A Run of this project plays {effective ? `at most ${timeWords(effective)}` : "with no time limit"}.
        {hunt.length > 0 ? ` The hunt block “minutes” (${hunt.map((h) => `${h.where}: ${h.minutes} min`).join("; ")}) also stops the hunt: choosing a time here sets it to follow the Run (0).` : ""} Saved with the project (Save keeps it){running ? "; the Run that is playing keeps the time it started with" : ""}.
      </p>
      <label>
        After a code error{" "}
        <select className="field" data-testid="run-retry-max" disabled={!opts || busy} value={String(opts?.retry_max ?? "")} onChange={(e) => opts && void save(Number(e.target.value), opts.retry_wait_s)}>
          {RETRY_CHOICES.map((n) => (
            <option key={n} value={String(n)}>
              {n === 0 ? "end the Run (retry off)" : `check her and hunt on, at most ${n} time${n === 1 ? "" : "s"}`}
            </option>
          ))}
        </select>{" "}
        <select className="field" aria-label="wait before the check" disabled={!opts || busy || opts.retry_max === 0} value={String(opts?.retry_wait_s ?? "")} onChange={(e) => opts && void save(opts.retry_max, Number(e.target.value))}>
          {RETRY_WAIT_CHOICES.map((s) => (
            <option key={s} value={String(s)}>
              {`after ${s} s`}
            </option>
          ))}
        </select>
      </label>
      <p className="muted" data-testid="run-retry-words">
        {opts ? `${opts.words[0].toUpperCase()}${opts.words.slice(1)}. A code error is a program fault or a frozen picture; a death, Stop, the time limit, a full bag, the game leaving the screen or a refusal never retries. This bot server's setting: the Run that is playing reads it at its next retry.` : "The retry option is loading…"}
      </p>
      <label>
        The Economy{" "}
        <select className="field" data-testid="run-bag-count" disabled={!opts || busy} value={opts?.bag_count === false ? "off" : "on"} onChange={(e) => opts && void save(opts.retry_max, opts.retry_wait_s, e.target.value === "on")}>
          <option value="on">count the bag at the start and the end (~17 s each)</option>
          <option value="off">do not count the bag (no economy)</option>
        </select>
      </label>
      <p className="muted" data-testid="run-bag-words">
        {opts?.bag_count === false
          ? "No bag count: a Run writes no economy."
          : "The bot opens the bag (Alt+E), reads every tab and closes it, at the start and at the end -- after Stop too (a second Stop skips it). The change is the Run's economy on the Economy page. This bot server's setting."}
      </p>
      {err && <p className="err-text">{err}</p>}
    </details>
  );
}

/** The Run's monitor bar (Batt 2026-11-20: "a small dashboard of the bot, emoji so a look tells"):
 * the state, what she does, HP as a bar, her cell, kills, items gained, potions, Fly Wings, time. */
export function RunMonitor({ live }: { live: Live }) {
  const tiles = monitorTiles(live.st);
  return (
    <div className="run-monitor" role="status" aria-label="the Run at a glance" data-testid="run-monitor">
      {tiles.map((t) => (
        <span key={t.key} className={`run-tile run-tile-${t.key}`} title={t.title} data-testid={`run-tile-${t.key}`}>
          <span className="run-tile-icon" aria-hidden="true">
            {t.icon}
          </span>
          <span className="run-tile-text">{t.text}</span>
          {t.bar !== undefined && (
            <span className="run-tile-bar" aria-hidden="true">
              <span style={{ width: `${t.bar}%` }} data-low={t.bar < 50 ? "true" : "false"} />
            </span>
          )}
        </span>
      ))}
    </div>
  );
}

/** The Logs part of the Run / Log pane: the Run's state line, what she does (newest first), and the
 * Run's log. Its facts are the monitor bar's tiles (RunMonitor). */
/** The Run's state line: playing / ended, its label, when it started or ended, its end words. */
export function RunStateBox({ live }: { live: Live }) {
  const st = live.st;
  const l = st?.live ?? null;
  const active = ACTIVE.includes(st?.state ?? "");
  return (
    <div className="box stack">
      <div className="strong" data-testid="logs-state">
        {st ? `${active ? "Playing" : (st.state ?? "idle")} · ${liveLabel(st)}` : "The Run helper has not answered yet"}
        {st?.label ? ` · ${st.label}` : ""}
        {st?.started ? ` · started ${st.started}` : ""}
        {st?.ended ? ` · ended ${st.ended}` : ""}
      </div>
      {st?.detail && <div className={st.state === "ended" || st.state === "failed" ? "notice-sub" : "muted"}>{st.detail}</div>}
      {l?.end?.words && <div className="notice-sub">The end: {l.end.words}</div>}
    </div>
  );
}

/** What she does (newest first): the Run helper's story of the session's events, in words. */
export function RunStory({ live }: { live: Live }) {
  const story = [...(live.st?.live?.story ?? [])].reverse();
  return (
    <div className="box stack run-story">
      <div className="strong">What she does (newest first)</div>
      {story.length === 0 ? (
        <div className="muted">Nothing yet: the lines come from the Run&apos;s own events while she plays.</div>
      ) : (
        <ol className="logs-story" data-testid="logs-story">
          {story.map((s, i) => (
            <li key={`${story.length - i}-${s.t_s}`}>
              <span className="muted">{storyTime(s.t_s)}</span> {s.words}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

/** The Run's log: its last lines, following the end unless the person turns that off. */
export function RunLogBox({ live }: { live: Live }) {
  const lines = live.st?.log_tail ?? [];
  const pre = useRef<HTMLPreElement | null>(null);
  const [follow, setFollow] = useState(true);
  useEffect(() => {
    if (follow && pre.current) pre.current.scrollTop = pre.current.scrollHeight;
  }, [lines.length, follow]);
  return (
    <div className="box stack">
      <div className="row">
        <span className="strong">The Run&apos;s log ({lines.length} lines)</span>
        <label className="muted">
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> follow the end
        </label>
      </div>
      <pre className="logs-pre" ref={pre} data-testid="logs-pre">
        {lines.length ? lines.join("\n") : "No Run has written a log yet."}
      </pre>
    </div>
  );
}

/** The three in one column (the old Logs tab's order): the state, what she does, the log. */
export function LogsPanel({ live }: { live: Live }) {
  return (
    <div className="stack" data-testid="logs-pane">
      <RunStateBox live={live} />
      <RunStory live={live} />
      <RunLogBox live={live} />
    </div>
  );
}
