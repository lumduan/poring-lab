"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import ModeSwitch from "@/components/ModeSwitch";
import OverlayCanvas from "@/components/OverlayCanvas";
import StatsPanel, { EMPTY_STATS, type Links, type Stats } from "@/components/StatsPanel";
import StreamCanvas from "@/components/StreamCanvas";
import {
  browserNowNs,
  NO_FRAME,
  parseServerMessage,
  type BrowserToBackend,
  type Detections,
  type FrameMeta,
  type Mode,
  type Status,
} from "@/lib/protocol";
import { backendWsBase, ReconnectingSocket } from "@/lib/ws";

type Props = { backendUrl: string | null };

/** Owns both sockets. Video frames are drawn imperatively (never through React state); status,
 * detections and stats go through state at their own, much lower rates. */
export default function Console({ backendUrl }: Props) {
  const videoRef = useRef<HTMLCanvasElement>(null);
  const inputRef = useRef<ReconnectingSocket | null>(null);
  const frameIdRef = useRef<number>(NO_FRAME);
  const [status, setStatus] = useState<Status | null>(null);
  const [detections, setDetections] = useState<Detections | null>(null);
  const [stats, setStats] = useState<Stats>(EMPTY_STATS);
  const [links, setLinks] = useState<Links>({ stream: false, input: false });
  const [size, setSize] = useState({ width: 1280, height: 720 });

  useEffect(() => {
    const base = backendWsBase(backendUrl);
    let pendingMeta: FrameMeta | null = null;
    let queued: { meta: FrameMeta; blob: Blob } | null = null;
    let decoding = false;
    let frames = 0;
    let bytes = 0;
    let captureToEncodeMs = 0;
    let encodeToSendMs = 0;
    let rttMs: number | null = null;
    let windowStart = performance.now();

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
              setSize({ width: meta.width, height: meta.height });
            }
            canvas.getContext("2d")?.drawImage(bitmap, 0, 0);
          }
          bitmap.close();
          frameIdRef.current = meta.frame_id;
          frames += 1;
          bytes += meta.nbytes;
          // Both intervals are on the backend's clock, so they are directly meaningful.
          captureToEncodeMs = (meta.t_encoded_ns - meta.t_capture_ns) / 1e6;
          encodeToSendMs = (meta.t_mono_ns - meta.t_encoded_ns) / 1e6;
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
      onClose: () => setLinks((l) => ({ ...l, input: false })),
      onText: (text) => {
        const msg = parseServerMessage(text);
        // Our own clock went out and came back: a same-domain round trip.
        if (msg?.type === "pong") rttMs = (browserNowNs() - msg.echo_t_mono_ns) / 1e6;
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
        captureToEncodeMs,
        encodeToSendMs,
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
      stream.close();
      input.close();
      inputRef.current = null;
    };
  }, [backendUrl]);

  const send = useCallback((message: BrowserToBackend) => {
    inputRef.current?.send(message);
  }, []);

  const setMode = useCallback(
    (mode: Mode) =>
      send({ type: "set_mode", t_mono_ns: browserNowNs(), frame_id: frameIdRef.current, mode }),
    [send],
  );

  return (
    <main className="mx-auto flex max-w-[1320px] flex-col gap-3 p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold tracking-tight">poring-lab</h1>
        <ModeSwitch mode={status?.mode ?? null} onChange={setMode} disabled={!links.input} />
      </header>
      <StreamCanvas videoRef={videoRef} frameIdRef={frameIdRef} send={send}>
        <OverlayCanvas detections={detections} width={size.width} height={size.height} />
      </StreamCanvas>
      <StatsPanel stats={stats} status={status} links={links} />
      <p className="text-xs text-neutral-500">
        Click the screen to control it. Keys and mouse go to the one RDP session through the
        backend&apos;s input mux; leaving the screen (blur) releases anything you hold.
      </p>
    </main>
  );
}
