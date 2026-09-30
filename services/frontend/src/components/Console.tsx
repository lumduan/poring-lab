"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import Banner from "@/components/Banner";
import FilesPanel from "@/components/FilesPanel";
import ModeSwitch from "@/components/ModeSwitch";
import OverlayCanvas from "@/components/OverlayCanvas";
import PastePanel from "@/components/PastePanel";
import StatsPanel, { EMPTY_STATS, type Links, type Stats } from "@/components/StatsPanel";
import StreamCanvas from "@/components/StreamCanvas";
import Toolbar from "@/components/Toolbar";
import { HeldKeys, type KeyStep } from "@/lib/keys";
import {
  browserNowNs,
  NO_FRAME,
  parseServerMessage,
  type BrowserToBackend,
  type Detections,
  type ErrorReply,
  type FrameMeta,
  type Mode,
  type PasteResult,
  type Status,
} from "@/lib/protocol";
import type { Size, ViewMode } from "@/lib/view";
import { checkPaste, describePaste } from "@/lib/transfer";
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
  const [detections, setDetections] = useState<Detections | null>(null);
  const [stats, setStats] = useState<Stats>(EMPTY_STATS);
  const [links, setLinks] = useState<Links>({ stream: false, input: false });
  const [frameSize, setFrameSize] = useState<Size>({ width: 1280, height: 720 });
  const [viewMode, setViewMode] = useState<ViewMode>("fit");
  const [focused, setFocused] = useState(false);
  const pasteIdRef = useRef(0);
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

  useEffect(() => {
    const base = backendWsBase(backendUrl);
    let pendingMeta: FrameMeta | null = null;
    let queued: { meta: FrameMeta; blob: Blob } | null = null;
    let decoding = false;
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

    // Latest frame wins: while one JPEG decodes, newer arrivals overwrite `queued`.
    const drawLatest = async () => {
      decoding = true;
      while (queued) {
        const { meta, blob } = queued;
        queued = null;
        try {
          const bitmap = await createImageBitmap(blob);
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
          frameIdRef.current = meta.frame_id;
          frames += 1;
          bytes += meta.nbytes;
          // Both intervals are on the backend's clock, so they are directly meaningful.
          push(captureToEncode, (meta.t_encoded_ns - meta.t_capture_ns) / 1e6);
          push(encodeToSend, (meta.t_mono_ns - meta.t_encoded_ns) / 1e6);
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
        else if (msg?.type === "status") setStatus(msg);
        else if (msg?.type === "detections") setDetections(msg);
        else if (msg?.type === "error") showDropped(msg);
      },
      onBinary: (blob) => {
        if (!pendingMeta) return; // a JPEG always follows its FrameMeta; ignore strays
        queued = { meta: pendingMeta, blob };
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
        if (msg?.type === "pong") rttMs = (browserNowNs() - msg.echo_t_mono_ns) / 1e6;
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
      });
      frames = 0;
      bytes = 0;
      windowStart = now;
    }, 500);

    return () => {
      clearInterval(pinger);
      clearInterval(statsTimer);
      if (droppedTimer) clearTimeout(droppedTimer);
      stream.close();
      input.close();
      inputRef.current = null;
    };
  }, [backendUrl, showToast]);

  const send = useCallback((message: BrowserToBackend) => {
    inputRef.current?.send(message);
  }, []);

  const stamp = () => ({ t_mono_ns: browserNowNs(), frame_id: frameIdRef.current });

  const setMode = (mode: Mode) => send({ type: "set_mode", ...stamp(), mode });

  const sendKeys = (steps: KeyStep[]) => {
    for (const step of steps) {
      if (held.apply(step)) send({ type: "key", ...stamp(), code: step.code, action: step.action });
    }
  };

  const releaseAll = () => {
    held.clear();
    send({ type: "release_all", ...stamp() });
  };

  /** ADR-0004: the backend pastes ``text`` into the focused Windows window (human-only). */
  const sendPaste = useCallback((text: string, source: PasteSource): boolean => {
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
      if (text.length === 0) {
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
      <Banner links={links} status={status} dropped={dropped} />
      <Toolbar
        disabled={!links.input}
        mode={viewMode}
        onKeys={sendKeys}
        onReleaseAll={releaseAll}
        onModeChange={setViewMode}
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
      </StreamCanvas>
      <div className="grid gap-3 lg:grid-cols-2">
        <details className="rounded-md border border-neutral-800 p-3" open>
          <summary className="cursor-pointer text-sm font-medium">Paste to Windows</summary>
          <div className="mt-2">
            <PastePanel
              enabled={status?.clipboard_enabled === true}
              connected={links.input}
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
      <StatsPanel stats={stats} status={status} links={links} />
      <p className="text-xs text-neutral-500">
        {focused
          ? "Keyboard and mouse go to the remote desktop (through the backend's input mux). ⌘V pastes your clipboard into the focused Windows field. Click outside the screen to release."
          : "Click the screen to control it. Leaving it (blur or hiding the tab) releases anything held."}
      </p>
    </main>
  );
}
