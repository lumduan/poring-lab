import type { Links } from "@/components/StatsPanel";
import { bannerAlarms, bannerProblems } from "@/lib/banner";
import type { ErrorReply, Status } from "@/lib/protocol";

type Props = {
  links: Links;
  status: Status | null;
  dropped?: ErrorReply | null;
  /** The RDP session came back within the last minute (the game can lose its D3D device). */
  rdpReconnected?: boolean;
};

/** A clear notice when the picture or the controls can't be trusted (logic: lib/banner.ts). */
export default function Banner({ links, status, dropped = null, rdpReconnected = false }: Props) {
  const alarms = bannerAlarms(status);
  const problems = bannerProblems({ links, status, dropped, rdpReconnected });
  if (alarms.length === 0 && problems.length === 0) return null;
  return (
    <div className="flex flex-col gap-2">
      {alarms.length > 0 && (
        <div role="alert" className="rounded-md border border-red-600 bg-red-950 px-3 py-2 text-sm font-semibold text-red-100">
          {alarms.map((a) => (
            <p key={a}>{a}</p>
          ))}
        </div>
      )}
      {problems.length > 0 && (
        <div role="alert" className="rounded-md border border-amber-600 bg-amber-950 px-3 py-2 text-sm text-amber-100">
          {problems.map((p) => (
            <p key={p}>{p}</p>
          ))}
        </div>
      )}
    </div>
  );
}
