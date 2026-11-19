/** The capture-backend lock as the console shows it (ADR-0009): who owns the ONE Windows session. */
import type { Status } from "@/lib/protocol";

export type CaptureView = {
  /** Short value for the stats panel, e.g. "rdp", "console (switching)", "HOLD". */
  label: string;
  /** Problems/notices for the banner (empty when all is normal). */
  notices: string[];
  /** Which remote-display window is expected on the display: "rdp" | "stream" | null (none). */
  expect: "rdp" | "stream" | null;
};

export function describeCapture(status: Status | null): CaptureView {
  const lock = status?.capture_backend;
  if (!status || !lock) return { label: "–", notices: [], expect: "rdp" };
  const switching = lock.phase === "switching";
  // The clean room (ADR-0009) parks the lock at console/switching between variants on purpose;
  // the banner's clean-room line says so (lib/banner.ts), so no "handover in progress" here.
  const cleanroom = (lock.reason ?? "").startsWith("cleanroom");
  const label = `${lock.backend === "hold" ? "HOLD" : lock.backend}${switching ? " (switching)" : ""}`;
  const notices: string[] = [];
  if (lock.backend === "hold") {
    notices.push(
      "Capture-backend lock HOLD: neither RDP nor the console stream may connect " +
        `(${lock.reason ?? "unknown reason"}). Recover: python3 scripts/capture_backend.py status.`,
    );
    return { label, notices, expect: null };
  }
  if (switching && !cleanroom) {
    notices.push(`Capture-backend handover to ${lock.backend} in progress (seq ${lock.seq}).`);
  }
  if (lock.backend === "console") {
    // 2026-11-19 (ADR-0004 amendment e): with the S2 client's input socket a paste is TYPED
    notices.push(
      status.clipboard_enabled
        ? "Console mode (Sunshine, ADR-0009): a paste is typed into Windows by Sunshine; \\\\tsclient files are unavailable."
        : "Console mode (Sunshine/Moonlight, ADR-0009): paste and \\\\tsclient files are unavailable.",
    );
    if (!switching && status.stream_window_present === false) {
      notices.push(
        cleanroom
          ? "No stream window on the display: the clean-room variant is starting, or it exited."
          : "The console stream window is missing: gamestream is (re)connecting.",
      );
    }
    return { label, notices, expect: "stream" };
  }
  return { label, notices, expect: "rdp" };
}
