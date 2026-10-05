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
  /** Seconds since the last Status arrived (browser clock), or null while it is fresh. */
  statusAgeS?: number | null;
};

/** The backend pushes Status every second. Without one for STATUS_STALE_S the page no longer
 * knows the truth: an alarm on screen may already be over (2026-10-05: the WATCHDOG DOWN box
 * outlived its clear while /health and the push had dropped it within ~2 s; the Safari tab was
 * painting nothing). After STATUS_RECONNECT_S the stream socket reconnects by itself. */
export const STATUS_STALE_S = 3;
export const STATUS_RECONNECT_S = 5;

export function statusStale(ageS: number | null | undefined): boolean {
  return ageS !== null && ageS !== undefined && ageS > STATUS_STALE_S;
}

/** One tick of the console's 1 s status watch: what to show, and whether to reconnect now
 * (once per stale spell; a fresh Status re-arms it). */
export function statusWatch(ageS: number, kicked: boolean): {
  shownAgeS: number | null;
  kick: boolean;
  kicked: boolean;
} {
  if (!statusStale(ageS)) return { shownAgeS: null, kick: false, kicked: false };
  const kick = ageS > STATUS_RECONNECT_S && !kicked;
  return { shownAgeS: Math.round(ageS), kick, kicked: kicked || kick };
}

/** Safety alarms (2026-10-04): shown RED, above every other notice. */
const ALARM_TEXT: Record<string, string> = {
  watchdog_down:
    "WATCHDOG DOWN: a clean-room session is running without its watchdog, so its box and hard " +
    "cap are NOT enforced. End it now (scripts/cleanroom.py end).",
};

/** The alarm box (2026-10-04): Batt missed the first one -- a DARK maroon box (bg-red-950) the
 * shape of the amber notices below it, up ~66 s. Now unmistakable: bright red, white bold text,
 * and sticky at the top so it stays in view while the page is scrolled. */
export const ALARM_BOX_CLASS =
  "sticky top-0 z-50 rounded-md border-2 border-red-200 bg-red-600 px-4 py-3 text-base " +
  "font-bold text-white shadow-lg";

export function bannerAlarms(status: Status | null, statusAgeS: number | null = null): string[] {
  const texts = (status?.alarms ?? []).map((a) => ALARM_TEXT[a] ?? `Safety alarm: ${a}`);
  if (!statusStale(statusAgeS)) return texts;
  return texts.map((t) => `[no status for ${Math.round(statusAgeS ?? 0)} s: this may be stale] ${t}`);
}

/** ADR-0016 (rewritten 2026-10-04): the environment interlock, while the bot could act (BOT or
 * ASSIST). Green says nothing; an operator window and a refusal are shown with their reason. */
export function describeEnvironment(status: Status | null): string | null {
  const env = status?.environment;
  if (!env || !status || status.mode === "HUMAN") return null;
  if (env.state === "window") {
    const left = env.window_left_s === null || env.window_left_s === undefined ? "" : `, ${Math.round(env.window_left_s)} s left`;
    return `Interlock: operator window open (${env.window}${left}) -- bot input allowed in ASSIST only.`;
  }
  if (env.state === "red") {
    return `Interlock: bot input REFUSED (${env.reason}) -- no attested lab session (config/environments.yaml).`;
  }
  return null;
}

export function bannerProblems({
  links,
  status,
  dropped = null,
  rdpReconnected = false,
  nowMs = Date.now(),
  statusAgeS = null,
}: BannerInput): string[] {
  const problems: string[] = [];
  if (links.stream && statusStale(statusAgeS)) {
    problems.push(
      `No status from the backend for ${Math.round(statusAgeS ?? 0)} s: this page may be stale ` +
        "(a hidden or throttled tab?). Reconnecting the stream…",
    );
  }
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
  if (links.stream && status?.bot_agents?.includes("auto_recover")) {
    // Batt 2026-10-04: guarded_build re-logs the GM in by itself after a sniffer restart.
    problems.push("GM auto-recover running (after a sniffer restart): the bot re-logs the GM in, one attempt.");
  }
  if (links.stream && status?.cleanroom) problems.push(describeCleanRoom(status.cleanroom, nowMs));
  const interlock = links.stream ? describeEnvironment(status) : null;
  if (interlock) problems.push(interlock);
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
