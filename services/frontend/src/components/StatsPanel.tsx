import type { Status } from "@/lib/protocol";

export type Stats = {
  fps: number;
  kibps: number;
  captureToEncodeP50: number;
  encodeToSendP50: number;
  rttMs: number | null;
  frameId: number;
  /** Phase 0 (browser side): send->receive via the ping offset, receive->decoded, decoded->painted. */
  netMs: number | null;
  decodeMs: number;
  paintWaitMs: number;
  offsetUncertaintyMs: number | null;
};

export type Links = { stream: boolean; input: boolean };

export const EMPTY_STATS: Stats = {
  fps: 0,
  kibps: 0,
  captureToEncodeP50: 0,
  encodeToSendP50: 0,
  rttMs: null,
  frameId: -1,
  netMs: null,
  decodeMs: 0,
  paintWaitMs: 0,
  offsetUncertaintyMs: null,
};

type Props = { stats: Stats; status: Status | null; links: Links };

/** FPS / latency panel. Frame latencies are backend-clock intervals from the frame metadata
 * (rolling p50); RTT, decode and paint are browser-clock intervals. The one cross-clock number,
 * send→recv, goes through Cristian's offset and shows its uncertainty (half the best RTT). */
export default function StatsPanel({ stats, status, links }: Props) {
  const rdp =
    status?.rdp_window_present == null ? "unknown" : status.rdp_window_present ? "up" : "down";
  const rows: [string, string][] = [
    ["stream", links.stream ? "connected" : "down"],
    ["input", links.input ? "connected" : "down"],
    ["RDP", rdp],
    ["mode", status?.mode ?? "–"],
    ["frame", String(stats.frameId)],
    ["view fps", stats.fps.toFixed(1)],
    ["capture fps", status ? status.capture_fps.toFixed(1) : "–"],
    ["KiB/s", stats.kibps.toFixed(0)],
    ["capture→encode p50", `${stats.captureToEncodeP50.toFixed(1)} ms`],
    ["encode→send p50", `${stats.encodeToSendP50.toFixed(1)} ms`],
    ["input RTT", stats.rttMs == null ? "–" : `${stats.rttMs.toFixed(1)} ms`],
    [
      "send→recv p50",
      stats.netMs == null
        ? "–"
        : `${stats.netMs.toFixed(1)} ±${(stats.offsetUncertaintyMs ?? 0).toFixed(1)} ms`,
    ],
    ["decode p50", `${stats.decodeMs.toFixed(1)} ms`],
    ["→paint p50", `${stats.paintWaitMs.toFixed(1)} ms`],
    ["paint", status?.paint ?? "decode"],
    ["bot", status?.bot_connected ? "connected" : "absent"],
  ];
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-1 rounded-md border border-neutral-800 p-3 font-mono text-xs sm:grid-cols-3 lg:grid-cols-6">
      {rows.map(([label, value]) => (
        <div key={label} className="flex justify-between gap-2">
          <dt className="text-neutral-500">{label}</dt>
          <dd className="tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
