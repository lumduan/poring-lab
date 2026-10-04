/** What the console's banner says (pure; Banner.tsx only renders it). */
import { describeCapture } from "./capture.ts";
import type { CleanRoom, ErrorReply, Status } from "./protocol.ts";

export type BannerInput = {
  links: { stream: boolean; input: boolean };
  status: Status | null;
  dropped?: ErrorReply | null;
  /** The RDP session came back within the last minute (the game can lose its D3D device). */
  rdpReconnected?: boolean;
  /** Browser wall clock, for the hard cap's time of day (tests pass a fixed one). */
  nowMs?: number;
};

export function bannerProblems({
  links,
  status,
  dropped = null,
  rdpReconnected = false,
  nowMs = Date.now(),
}: BannerInput): string[] {
  const problems: string[] = [];
  const capture = describeCapture(status);
  if (!links.stream) problems.push("Stream disconnected: reconnecting to the backend…");
  if (!links.input) problems.push("Input channel disconnected: keys and clicks are not being sent.");
  if (links.stream && status?.mode_restored) {
    // ADR-0002 amendment (2026-10-03; recreate 2026-10-04): only a guarded restart's or recreate's
    // marker can do this; never BOT.
    problems.push(
      "ASSIST restored automatically after a guarded restart (scripts/guarded_build.py " +
        "restart:backend or recreate:backend). Choosing a mode clears this notice.",
    );
  }
  if (links.stream && status?.cleanroom) problems.push(describeCleanRoom(status.cleanroom, nowMs));
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
    const black = describeBlack(status, capture.expect);
    if (black) problems.push(black);
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
  return problems;
}

/** A black game region means different things per capture backend. The D3D-device advice (and
 * `ro_agent recover`, which reconnects RDP) applies to RDP mode only. */
function describeBlack(status: Status, expect: "rdp" | "stream" | null): string | null {
  if (expect === "rdp") {
    return (
      "The game window has been black for several seconds (a lost Direct3D device after an RDP " +
      "reconnect?). Nothing it shows can be trusted; recover with scripts/ro_agent.py recover."
    );
  }
  if (expect === "stream" && status.capture_backend?.phase === "steady") {
    return (
      "The game region has been black for several seconds: the console stream shows no game " +
      "picture (the stream client is starting, or the game window is not where GAME_REGION " +
      "expects it). Nothing it shows can be trusted."
    );
  }
  return null; // hold, or a handover/clean-room hold: no stream is expected, black is normal
}

export function describeCleanRoom(room: CleanRoom, nowMs: number): string {
  const parts: string[] = [];
  if (room.streaming && room.variant) {
    parts.push(`${room.variant} streaming`);
    if (room.box_left_s !== null && room.box_left_s > 0) {
      parts.push(`its box ends in ${duration(room.box_left_s)}`);
    }
  } else if (room.variant) {
    parts.push(`between variants (last ${room.variant}): no stream, as expected`);
  } else {
    parts.push("entered, no variant streaming yet");
  }
  if (room.hard_cap_left_s !== null) {
    const at = new Date(nowMs + room.hard_cap_left_s * 1000).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    parts.push(`hard cap in ${duration(room.hard_cap_left_s)} (${at})`);
  }
  return `Clean room (ADR-0009): ${parts.join("; ")}. RDP holds until scripts/cleanroom.py end.`;
}

function duration(seconds: number): string {
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}
