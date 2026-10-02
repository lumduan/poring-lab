import type { Links } from "@/components/StatsPanel";
import { describeCapture } from "@/lib/capture";
import type { ErrorReply, Status } from "@/lib/protocol";

type Props = {
  links: Links;
  status: Status | null;
  dropped?: ErrorReply | null;
  /** The RDP session came back within the last minute (the game can lose its D3D device). */
  rdpReconnected?: boolean;
};

/** A clear notice when the picture or the controls can't be trusted. */
export default function Banner({ links, status, dropped = null, rdpReconnected = false }: Props) {
  const problems: string[] = [];
  const capture = describeCapture(status);
  if (!links.stream) problems.push("Stream disconnected: reconnecting to the backend…");
  if (!links.input) problems.push("Input channel disconnected: keys and clicks are not being sent.");
  if (links.stream) problems.push(...capture.notices);
  if (links.stream && capture.expect === "rdp" && status?.rdp_window_present === false) {
    problems.push(
      "RDP session is down: the desktop container is reconnecting (docker compose logs desktop).",
    );
  }
  if (links.stream && status && status.rdp_window_present === null) {
    problems.push("The backend cannot reach the X display.");
  }
  if (links.stream && status?.game_black === true) {
    problems.push(
      "The game window has been black for several seconds (a lost Direct3D device after an RDP " +
        "reconnect?). Nothing it shows can be trusted; recover with scripts/ro_agent.py recover.",
    );
  } else if (links.stream && capture.expect === "rdp" && rdpReconnected && status?.rdp_window_present) {
    problems.push(
      "The RDP session reconnected less than a minute ago: check the game window is still drawing.",
    );
  }
  if (dropped) {
    // Never silent (ADR-0004): the backend refused one of this page's messages -- a console bug.
    problems.push(
      `The backend dropped a ${dropped.ref_type ?? "unreadable"} message on ${dropped.channel}: ` +
        `${dropped.reason}.`,
    );
  }
  if (problems.length === 0) return null;
  return (
    <div role="alert" className="rounded-md border border-amber-600 bg-amber-950 px-3 py-2 text-sm text-amber-100">
      {problems.map((p) => (
        <p key={p}>{p}</p>
      ))}
    </div>
  );
}
