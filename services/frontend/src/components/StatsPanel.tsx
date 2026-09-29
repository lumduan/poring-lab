import type { Status } from "@/lib/protocol";

export type Stats = {
  fps: number;
  kibps: number;
  captureToEncodeMs: number;
  encodeToSendMs: number;
  rttMs: number | null;
  frameId: number;
};

export type Links = { stream: boolean; input: boolean };

export const EMPTY_STATS: Stats = {
  fps: 0,
  kibps: 0,
  captureToEncodeMs: 0,
  encodeToSendMs: 0,
  rttMs: null,
  frameId: -1,
};

type Props = { stats: Stats; status: Status | null; links: Links };

/** FPS / latency panel. Server-side intervals use the backend clock; RTT is a browser-clock round
 * trip. The two clocks are never subtracted from each other. */
export default function StatsPanel({ stats, status, links }: Props) {
  const lease =
    status?.lease_until_ns != null
      ? Math.max(0, (status.lease_until_ns - status.t_mono_ns) / 1e9)
      : null;
  const rdp =
    status?.rdp_window_present == null ? "unknown" : status.rdp_window_present ? "up" : "down";
  const rows: [string, string][] = [
    ["stream", links.stream ? "connected" : "down"],
    ["input", links.input ? "connected" : "down"],
    ["view fps", stats.fps.toFixed(1)],
    ["capture fps", status ? status.capture_fps.toFixed(1) : "–"],
    ["KiB/s", stats.kibps.toFixed(0)],
    ["frame", String(stats.frameId)],
    ["capture→encode", `${stats.captureToEncodeMs.toFixed(1)} ms`],
    ["encode→send", `${stats.encodeToSendMs.toFixed(1)} ms`],
    ["input RTT", stats.rttMs == null ? "–" : `${stats.rttMs.toFixed(1)} ms`],
    ["human lease", lease == null ? "none" : `${lease.toFixed(1)} s`],
    ["bot", status?.bot_connected ? "connected" : "absent"],
    ["RDP window", rdp],
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
