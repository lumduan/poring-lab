"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import Banner from "@/components/Banner";
import FilesPanel from "@/components/FilesPanel";
import ModeSwitch from "@/components/ModeSwitch";
import OverlayCanvas from "@/components/OverlayCanvas";
import PacketTimeline from "@/components/PacketTimeline";
import PastePanel from "@/components/PastePanel";
import RouteCanvas from "@/components/RouteCanvas";
import StatsPanel, { EMPTY_STATS, type Links, type Stats } from "@/components/StatsPanel";
import StreamCanvas from "@/components/StreamCanvas";
import Toolbar from "@/components/Toolbar";
import { statusWatch } from "@/lib/banner";
import { HeldKeys, type KeyStep } from "@/lib/keys";
import {
  browserNowNs,
  NO_FRAME,
  parseServerMessage,
  type BrowserToBackend,
  type Detections,
  type ErrorReply,
  type FrameMeta,
  type FrameTiming,
  type Mode,
  type PasteResult,
  type RoutePreview,
  type Status,
} from "@/lib/protocol";
import type { Size, ViewMode } from "@/lib/view";
import { LatestSlot, OffsetEstimator } from "@/lib/timing";
import { checkPaste, describePaste } from "@/lib/transfer";
import { mayForward } from "@/lib/watch";
import { backendWsBase, ReconnectingSocket } from "@/lib/ws";

type Props = { backendUrl: string | null };

type PasteSource = "screen" | "panel";
type Toast = { tone: "pending" | "ok" | "error"; text: string };

const TOAST_TONE: Record<Toast["tone"], string> = {
  pending: "border-sky-700 bg-sky-950/90 text-sky-100",
  ok: "border-emerald-700 bg-emerald-950/90 text-emerald-100",
  error: "border-red-700 bg-red-950/90 text-red-100",
};

const WINDOW = 90; // frames kept for the rolling p50 (~3 s at 30 fps)

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = sorted.length >> 1;
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function push(buffer: number[], value: number): void {
  buffer.push(value);
  if (buffer.length > WINDOW) buffer.shift();
}

/** Owns both sockets. Video frames are drawn imperatively (never through React state); status,
 * detections and stats go through state at their own, much lower rates. */
export default function Console({ backendUrl }: Props) {
  const videoRef = useRef<HTMLCanvasElement>(null);
  const inputRef = useRef<ReconnectingSocket | null>(null);
  const frameIdRef = useRef<number>(NO_FRAME);
  const [held] = useState(() => new HeldKeys());
  const [status, setStatus] = useState<Status | null>(null);
  // When the last Status arrived (performance.now(), this tab's clock): the banner's staleness.
  const lastStatusMsRef = useRef<number | null>(null);
  const [statusAgeS, setStatusAgeS] = useState<number | null>(null);
  const [detections, setDetections] = useState<Detections | null>(null);
  const [route, setRoute] = useState<RoutePreview | null>(null);
  const [stats, setStats] = useState<Stats>(EMPTY_STATS);
  const [links, setLinks] = useState<Links>({ stream: false, input: false });
  const [frameSize, setFrameSize] = useState<Size>({ width: 1280, height: 800 });
  const [viewMode, setViewMode] = useState<ViewMode>("fit");
  const [focused, setFocused] = useState(false);
  // Watch only (Batt, 2026-10-07): this tab forwards no input; per tab, off on every load, so a
  // reload always brings instant takeover back.
  const [watchOnly, setWatchOnlyState] = useState(false);
  const watchOnlyRef = useRef(false);
  const pasteIdRef = useRef(0);
  // Phase 0 console knob, pushed by the backend in Status (docs/phase0-latency.md).
  const paintModeRef = useRef<"decode" | "raf">("decode");
  const [pasteResult, setPasteResult] = useState<PasteResult | null>(null);
  const [pastePending, setPastePending] = useState(false);
  // Where the latest paste came from: Cmd+V on the screen answers with a toast, the panel in place.
  const pasteSourceRef = useRef<PasteSource>("panel");
  const [pasteSource, setPasteSource] = useState<PasteSource>("panel");
  const [toast, setToast] = useState<Toast | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((next: Toast) => {
    setToast(next);
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current =
      next.tone === "pending" ? null : setTimeout(() => setToast(null), 4000);
  }, []);
  const [dropped, setDropped] = useState<ErrorReply | null>(null);
  // RDP reconnect notice: when rdp_window_present goes false -> true, remember the backend time
  // (Status.t_mono_ns, its own clock) and show the notice for a minute of backend time.
  const [rdpPrev, setRdpPrev] = useState<boolean | null | undefined>(undefined);
  const [rdpBackAtNs, setRdpBackAtNs] = useState<number | null>(null);
  const rdpNow = status?.rdp_window_present;
  if (rdpNow !== rdpPrev) {
    setRdpPrev(rdpNow);
    if (rdpPrev === false && rdpNow === true && status) setRdpBackAtNs(status.t_mono_ns);
  }
  const rdpReconnected =
    rdpBackAtNs !== null && status !== null && status.t_mono_ns - rdpBackAtNs < 60e9;

  useEffect(() => {
    const base = backendWsBase(backendUrl);
    let pendingMeta: FrameMeta | null = null;
    let queued: { meta: FrameMeta; blob: Blob; recv: number } | null = null;
    let decoding = false;
    // Phase 0 telemetry: per-frame times on this tab's clock, reported once a second.
    const offset = new OffsetEstimator();
    let timings: FrameTiming[] = [];
    const netMs: number[] = [];
    const decodeMs: number[] = [];
    const paintWaitMs: number[] = [];
    type Decoded = { bitmap: ImageBitmap; meta: FrameMeta; recv: number; decoded: number };
    const ready = new LatestSlot<Decoded>(); // paint=raf: only the newest decoded frame waits
    let rafId = 0;
    let frames = 0;
    let bytes = 0;
    const captureToEncode: number[] = [];
    const encodeToSend: number[] = [];
    let rttMs: number | null = null;
    let windowStart = performance.now();
    let droppedTimer: ReturnType<typeof setTimeout> | null = null;

    // The backend dropped one of our messages (never silently): show it for a while.
    const showDropped = (msg: ErrorReply) => {
      setDropped(msg);
      if (droppedTimer) clearTimeout(droppedTimer);
      droppedTimer = setTimeout(() => setDropped(null), 10_000);
    };

    const drawFrame = ({ bitmap, meta, recv, decoded }: Decoded) => {
      const canvas = videoRef.current;
      if (canvas) {
        if (canvas.width !== meta.width || canvas.height !== meta.height) {
          canvas.width = meta.width;
          canvas.height = meta.height;
          setFrameSize({ width: meta.width, height: meta.height });
        }
        canvas.getContext("2d")?.drawImage(bitmap, 0, 0);
      }
      bitmap.close();
      const painted = browserNowNs();
      frameIdRef.current = meta.frame_id;
      frames += 1;
      bytes += meta.nbytes;
      // Both intervals are on the backend's clock, so they are directly meaningful.
      push(captureToEncode, (meta.t_encoded_ns - meta.t_capture_ns) / 1e6);
      push(encodeToSend, (meta.t_mono_ns - meta.t_encoded_ns) / 1e6);
      push(decodeMs, (decoded - recv) / 1e6);
      push(paintWaitMs, (painted - decoded) / 1e6);
      const off = offset.offsetNs;
      if (off != null) push(netMs, (recv + off - meta.t_mono_ns) / 1e6);
      if (timings.length < 240) {
        timings.push({
          frame_id: meta.frame_id,
          recv_ns: recv,
          decoded_ns: decoded,
          painted_ns: painted,
        });
      }
    };
    const paintReady = () => {
      rafId = 0;
      const next = ready.take();
      if (next) drawFrame(next);
    };

    // Latest frame wins: while one JPEG decodes, newer arrivals overwrite `queued`. With
    // paint=raf, a decoded frame waits for the next animation frame, and only the newest waits.
    const drawLatest = async () => {
      decoding = true;
      while (queued) {
        const { meta, blob, recv } = queued;
        queued = null;
        try {
          const bitmap = await createImageBitmap(blob);
          const frame = { bitmap, meta, recv, decoded: browserNowNs() };
          if (paintModeRef.current === "raf") {
            ready.put(frame)?.bitmap.close();
            if (!rafId) rafId = requestAnimationFrame(paintReady);
          } else {
            drawFrame(frame);
          }
        } catch {
          // A corrupt or truncated JPEG: skip it, the next one is ~33 ms away.
        }
      }
      decoding = false;
    };

    const stream = new ReconnectingSocket(`${base}/ws/stream`, {
      onOpen: () => setLinks((l) => ({ ...l, stream: true })),
      onClose: () => setLinks((l) => ({ ...l, stream: false })),
      onText: (text) => {
        const msg = parseServerMessage(text);
        if (msg?.type === "frame") pendingMeta = msg;
        else if (msg?.type === "status") {
          paintModeRef.current = msg.paint ?? "decode";
          lastStatusMsRef.current = performance.now();
          setStatus(msg);
        }
        else if (msg?.type === "detections") setDetections(msg);
        else if (msg?.type === "route_preview") setRoute(msg);
        else if (msg?.type === "error") showDropped(msg);
      },
      onBinary: (blob) => {
        if (!pendingMeta) return; // a JPEG always follows its FrameMeta; ignore strays
        queued = { meta: pendingMeta, blob, recv: browserNowNs() };
        pendingMeta = null;
        if (!decoding) void drawLatest();
      },
    });

    const input = new ReconnectingSocket(`${base}/ws/input`, {
      onOpen: () => setLinks((l) => ({ ...l, input: true })),
      onClose: () => {
        setLinks((l) => ({ ...l, input: false }));
        setPastePending(false); // its answer died with the socket
        setToast((t) => (t?.tone === "pending" ? null : t));
      },
      onText: (text) => {
        const msg = parseServerMessage(text);
        // Our own clock went out and came back: a same-domain round trip.
        if (msg?.type === "pong") {
          const received = browserNowNs();
          rttMs = (received - msg.echo_t_mono_ns) / 1e6;
          offset.sample(msg.echo_t_mono_ns, msg.t_mono_ns, received, performance.now());
        }
        else if (msg?.type === "paste_result" && msg.request_id === pasteIdRef.current) {
          setPasteResult(msg);
          setPastePending(false);
          if (pasteSourceRef.current === "screen") {
            showToast(
              msg.ok
                ? { tone: "ok", text: `Pasted ${msg.chars} characters into Windows.` }
                : { tone: "error", text: describePaste(msg.reason) },
            );
          }
        } else if (msg?.type === "error") showDropped(msg);
      },
    });
    inputRef.current = input;

    const pinger = setInterval(() => {
      const ping: BrowserToBackend = {
        type: "ping",
        t_mono_ns: browserNowNs(),
        frame_id: frameIdRef.current,
      };
      input.send(ping);
      // Phase 0 telemetry (docs/phase0-latency.md): this second's frames, on this tab's clock.
      const report: BrowserToBackend = {
        type: "viewer_timing",
        t_mono_ns: browserNowNs(),
        frame_id: frameIdRef.current,
        offset_ns: offset.offsetNs,
        offset_uncertainty_ns: offset.uncertaintyNs,
        visible: document.visibilityState === "visible",
        user_agent: navigator.userAgent.slice(0, 200),
        frames: timings,
      };
      input.send(report);
      timings = [];
    }, 1000);
    const statsTimer = setInterval(() => {
      const now = performance.now();
      const seconds = Math.max((now - windowStart) / 1000, 1e-3);
      setStats({
        fps: frames / seconds,
        kibps: bytes / 1024 / seconds,
        captureToEncodeP50: median(captureToEncode),
        encodeToSendP50: median(encodeToSend),
        rttMs,
        frameId: frameIdRef.current,
        netMs: netMs.length ? median(netMs) : null,
        decodeMs: median(decodeMs),
        paintWaitMs: median(paintWaitMs),
        offsetUncertaintyMs: offset.uncertaintyNs == null ? null : offset.uncertaintyNs / 1e6,
      });
      frames = 0;
      bytes = 0;
      windowStart = now;
    }, 500);

    // A Status every second, or the banner says it may be stale and the stream reconnects.
    let kicked = false;
    const statusTimer = setInterval(() => {
      const last = lastStatusMsRef.current;
      if (last === null) return;
      const tick = statusWatch((performance.now() - last) / 1000, kicked);
      kicked = tick.kicked;
      setStatusAgeS((prev) => (prev === tick.shownAgeS ? prev : tick.shownAgeS));
      if (tick.kick) stream.kick();
    }, 1000);

    return () => {
      clearInterval(statusTimer);
      clearInterval(pinger);
      clearInterval(statsTimer);
      if (droppedTimer) clearTimeout(droppedTimer);
      if (rafId) cancelAnimationFrame(rafId);
      ready.take()?.bitmap.close();
      stream.close();
      input.close();
      inputRef.current = null;
    };
  }, [backendUrl, showToast]);

  // The backstop under every handler: in watch-only mode no input leaves the tab (lib/watch.ts).
  const send = useCallback((message: BrowserToBackend) => {
    if (!mayForward(message.type, watchOnlyRef.current)) return;
    inputRef.current?.send(message);
  }, []);

  const setWatchOnly = (on: boolean) => {
    watchOnlyRef.current = on; // StreamCanvas lets go of what it holds first (release_all passes)
    setWatchOnlyState(on);
  };

  const stamp = () => ({ t_mono_ns: browserNowNs(), frame_id: frameIdRef.current });

  const setMode = (mode: Mode) => send({ type: "set_mode", ...stamp(), mode });

  // Secret typing (passwords): the backend keeps no human key identities in its logs while on.
  const setSecret = (on: boolean) => send({ type: "secret_input", ...stamp(), on });

  const sendKeys = (steps: KeyStep[]) => {
    if (watchOnlyRef.current) return;
    for (const step of steps) {
      if (held.apply(step)) send({ type: "key", ...stamp(), code: step.code, action: step.action });
    }
  };

  const releaseAll = () => {
    if (watchOnlyRef.current) return;
    held.clear();
    send({ type: "release_all", ...stamp() });
  };

  /** ADR-0004: the backend pastes ``text`` into the focused Windows window (human-only). */
  const sendPaste = useCallback((text: string, source: PasteSource): boolean => {
    if (watchOnlyRef.current) return false;
    pasteIdRef.current += 1;
    pasteSourceRef.current = source;
    setPasteSource(source);
    setPasteResult(null);
    const sent =
      inputRef.current?.send({
        type: "clipboard_paste",
        t_mono_ns: browserNowNs(),
        frame_id: frameIdRef.current,
        request_id: pasteIdRef.current,
        text,
      } satisfies BrowserToBackend) ?? false;
    setPastePending(sent);
    return sent;
  }, []);

  /** Cmd+V (Ctrl+V, Shift+Insert) on the remote screen: the viewer's clipboard text. */
  const pasteFromScreen = useCallback(
    (text: string) => {
      const check = checkPaste(text);
      if (watchOnlyRef.current) {
        showToast({ tone: "error", text: "Watch only is on: nothing was pasted." });
      } else if (text.length === 0) {
        showToast({ tone: "error", text: "The clipboard holds no text to paste." });
      } else if (!check.ok) {
        showToast({ tone: "error", text: check.message ?? "Cannot paste this." });
      } else if (!sendPaste(text, "screen")) {
        showToast({ tone: "error", text: "Input channel disconnected: nothing was pasted." });
      } else {
        showToast({ tone: "pending", text: `Pasting ${text.length} characters…` });
      }
    },
    [sendPaste, showToast],
  );

  const lease =
    status?.lease_until_ns != null
      ? Math.max(0, (status.lease_until_ns - status.t_mono_ns) / 1e9)
      : null;

  return (
    <main className="mx-auto flex max-w-[1600px] flex-col gap-3 p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold tracking-tight">poring-lab console</h1>
        <div className="flex items-center gap-3">
          {watchOnly && (
            <span className="rounded-md bg-amber-500 px-2 py-0.5 text-xs font-semibold text-neutral-950">
              WATCH ONLY
            </span>
          )}
          <span className="font-mono text-xs text-neutral-400">
            {status?.mode === "ASSIST"
              ? lease == null
                ? "lease: none (bot may act)"
                : `human lease ${lease.toFixed(1)} s`
              : ""}
          </span>
          <ModeSwitch mode={status?.mode ?? null} onChange={setMode} disabled={!links.input} />
        </div>
      </header>
      <Banner
        links={links}
        status={status}
        dropped={dropped}
        rdpReconnected={rdpReconnected}
        statusAgeS={statusAgeS}
      />
      <Toolbar
        disabled={!links.input}
        mode={viewMode}
        secret={status?.human_secret ?? false}
        watchOnly={watchOnly}
        onWatchOnlyChange={setWatchOnly}
        onKeys={sendKeys}
        onReleaseAll={releaseAll}
        onModeChange={setViewMode}
        onSecretChange={setSecret}
      />
      <StreamCanvas
        videoRef={videoRef}
        frameIdRef={frameIdRef}
        frameSize={frameSize}
        mode={viewMode}
        held={held}
        send={send}
        onFocusChange={setFocused}
        onPaste={pasteFromScreen}
        moveIntervalMs={status?.move_interval_ms ?? null}
        watchOnly={watchOnly}
        overlay={
          toast && (
            <div
              role="status"
              className={`rounded-md border px-3 py-1.5 text-sm shadow-lg ${TOAST_TONE[toast.tone]}`}
            >
              {toast.text}
            </div>
          )
        }
      >
        <OverlayCanvas detections={detections} width={frameSize.width} height={frameSize.height} />
        <RouteCanvas route={route} width={frameSize.width} height={frameSize.height} />
      </StreamCanvas>
      <div className="grid gap-3 lg:grid-cols-2">
        <details className="rounded-md border border-neutral-800 p-3" open>
          <summary className="cursor-pointer text-sm font-medium">Paste to Windows</summary>
          <div className="mt-2">
            <PastePanel
              enabled={status?.clipboard_enabled === true}
              connected={links.input}
              watchOnly={watchOnly}
              mode={status?.mode ?? null}
              pending={pastePending && pasteSource === "panel"}
              result={pasteSource === "panel" ? pasteResult : null}
              onSend={(text) => sendPaste(text, "panel")}
            />
          </div>
        </details>
        <details className="rounded-md border border-neutral-800 p-3">
          <summary className="cursor-pointer text-sm font-medium">
            Files ⇄ Windows (<span className="font-mono">\\tsclient\transfer</span>)
          </summary>
          <div className="mt-2">
            <FilesPanel backendUrl={backendUrl} enabled={status?.transfer_enabled === true} />
          </div>
        </details>
      </div>
      <PacketTimeline backendUrl={backendUrl} />
      <StatsPanel stats={stats} status={status} links={links} />
      <p className="text-xs text-neutral-500">
        {watchOnly
          ? "Watch only: nothing you do on the screen is sent, so the bot keeps control in ASSIST. Switching to HUMAN still works. Turn Watch only off to take over instantly."
          : focused
          ? "Keyboard and mouse go to the remote desktop (through the backend's input mux). ⌘V pastes your clipboard into the focused Windows field. Click outside the screen to release."
          : "Click the screen to control it. Leaving it (blur or hiding the tab) releases anything held."}
      </p>
    </main>
  );
}
