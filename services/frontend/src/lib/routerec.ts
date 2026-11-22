/**
 * The console's "Record route" panel, its PURE logic (docs/planning/waypoints-npc-recording.md
 * Amendment 11): the backend's GET /routes/record (routes_routerec.py: the host helper
 * scripts/route_rec.py's status, with `helper_alive` from its heartbeat) -> the panel's model
 * (ready or which item is missing, the minutes that fit or unknown, the recording's elapsed time and
 * size), and which guide notifications are NEW since the last poll (by id: the toasts and the
 * browser notification). No React, no fetch. Values are rendered as TEXT only.
 *
 * The video is recorded on the bot server's own disk (record_session's local root, shipped to the
 * storage later); the route folder holds a pointer to it. So the disk line is that local disk's.
 */

export type RouteRecNotification = {
  id: string; // "<recording id>-<n>": unique per notification
  kind: string; // started | stopped | map_change | indoors | low_disk
  level: string; // info | action (the person types something) | warn
  text: string;
  at: string; // ISO time with its offset
  recording: string;
};

export type RouteRecDisk = {
  root?: string; // the recorder's local root: the disk the video fills
  free_bytes?: number;
  floor_bytes?: number;
  unshipped_bytes?: number;
  unshipped_cap_bytes?: number | null;
  usable_bytes?: number;
  limit?: "floor" | "unshipped"; // which of the recorder's two local limits leaves less room
  rate_bytes_per_min?: number | null;
  rate_source?: string;
  minutes: number | null;
  max_minutes?: number;
  verdict: "ok" | "warn" | "refuse" | "unknown";
  error?: string;
};

export type RouteRecCheck = {
  id: string | null; // the request it answers (POST /routes/record's id)
  at: string;
  ready: boolean;
  missing: string[];
  missing_words: string | null;
  basic_info: boolean | null;
  chat_window: boolean | null;
  minimap: "present" | "absent" | null;
  xy: [number, number] | null;
  format: string | null;
  recorder: string | null; // why the recorder would refuse, in its own words
  disk: RouteRecDisk;
  busy: string | null;
  can_start: boolean;
  words: string;
};

export type RouteRecRecording = {
  id: string;
  dir: string;
  map: string | null;
  format: string | null;
  fps: number;
  split: string;
  started: string;
  state: "starting" | "recording" | "stopping";
  elapsed_s: number;
  max_s: number;
  disk_used_bytes: number;
  minutes_left: number | null;
  rate_source: string;
  ready: boolean;
  missing: string[];
  missing_words: string | null;
  minimap: "present" | "absent" | null;
  xy: [number, number] | null;
  session: string | null; // record_session's session id, once found
  session_path: string | null;
};

export type RouteRecLast = {
  id: string;
  dir: string;
  ended: string;
  stop_reason: string;
  rc: number | null;
  bytes: number | null; // measured from the local session folder
  session: string | null;
  session_path: string | null;
  split: string;
  refused: boolean;
};

export type RouteRecStatus = {
  state: string; // no_helper | idle | busy | starting | recording | stopping | ended | failed
  helper_alive: boolean;
  detail?: string;
  busy?: string | null;
  check?: RouteRecCheck | null;
  recording?: RouteRecRecording | null;
  last?: RouteRecLast | null;
  notifications?: RouteRecNotification[];
};

export type Level = "ok" | "warn" | "bad" | "unknown";

export type ReadyItem = { key: string; ok: boolean | null; text: string }; // ok null: info only

export type PanelModel = {
  helper: "alive" | "down";
  headline: string;
  recording: boolean; // a recording is starting, going or stopping
  checking: boolean; // a check (or a start's check) was asked and its answer is not in yet
  canCheck: boolean;
  canStart: boolean;
  canStop: boolean;
  ready: boolean | null; // null: never checked
  items: ReadyItem[];
  disk: { level: Level; text: string; minutes: number | null } | null;
  rec: { elapsed: string; size: string; left: string; map: string; split: string; stopping: boolean } | null;
  last: string | null; // the last recording's end, in words
};

const ACTIVE = ["starting", "recording", "stopping"];

/** Seconds as m:ss, or h:mm:ss from an hour. */
export function elapsedText(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

/** Bytes in decimal units (the recorder's own MB). */
export function sizeText(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  return `${(bytes / 1e6).toFixed(bytes >= 1e8 ? 0 : 1)} MB`;
}

/** The disk check in words, with its level. */
export function diskLine(disk: RouteRecDisk): { level: Level; text: string; minutes: number | null } {
  const room = disk.usable_bytes == null ? "" : ` (${sizeText(disk.usable_bytes)} free above the space the recorder keeps)`;
  if (disk.verdict === "refuse") {
    if (disk.error) return { level: "bad", minutes: disk.minutes, text: `The disk could not be read: ${disk.error}.` };
    if (disk.limit === "unshipped") {
      return { level: "bad", minutes: disk.minutes, text: "No room: recordings waiting to be shipped fill the recorder's limit on the bot server's disk. Ship them first." };
    }
    return { level: "bad", minutes: disk.minutes, text: "No room: nothing fits above the space the recorder keeps free on the bot server's disk." };
  }
  if (disk.verdict === "unknown" || disk.minutes == null) {
    return { level: "unknown", minutes: null, text: `The minutes that fit are not known yet: this format has no measured rate${room}.` };
  }
  const cap = disk.max_minutes != null && disk.minutes > disk.max_minutes ? ` A recording stops at ${disk.max_minutes} min.` : "";
  if (disk.verdict === "warn") return { level: "warn", minutes: disk.minutes, text: `Only about ${disk.minutes} minutes fit${room}.` };
  return { level: "ok", minutes: disk.minutes, text: `About ${disk.minutes} minutes fit${room}.${cap}` };
}

const ITEM_TEXT: Record<string, [string, string]> = {
  capture_lock: ["The game stream is steady.", "The game stream is not steady (the capture lock is switching or on hold)."],
  frame: ["A picture of the game was taken.", "No picture of the game could be taken."],
  basic_info: ["The character's status window is on screen.", "Open the character's status window: it must be on screen."],
  chat_window: ["The chat window is on screen.", "Show the chat window: it must be on screen."],
};

function minimapItem(minimap: "present" | "absent" | null, xy: [number, number] | null): ReadyItem {
  if (minimap === "present") {
    return { key: "minimap", ok: null, text: xy ? `Minimap on screen, at ${xy[0]} ${xy[1]}.` : "Minimap on screen (its numbers did not read on this picture)." };
  }
  if (minimap === "absent") {
    return { key: "minimap", ok: null, text: "No minimap here (indoors): you will be asked to type /where." };
  }
  return { key: "minimap", ok: null, text: "The minimap was not read." };
}

/** The readiness list: each required item ok or missing, then the minimap (reported, never required). */
export function readyItems(missing: string[], minimap: "present" | "absent" | null, xy: [number, number] | null): ReadyItem[] {
  const keys = ["capture_lock", "basic_info", "chat_window"];
  const items: ReadyItem[] = [];
  if (missing.includes("frame")) items.push({ key: "frame", ok: false, text: ITEM_TEXT.frame[1] });
  for (const k of keys) {
    if (missing.includes("frame") && k !== "capture_lock") continue; // unknown without a picture
    const bad = missing.includes(k);
    items.push({ key: k, ok: !bad, text: ITEM_TEXT[k][bad ? 1 : 0] });
  }
  items.push(minimapItem(minimap, xy));
  return items;
}

/**
 * The panel's model. `pendingId`: the id POST /routes/record answered for a check or a start whose
 * answer is not in the status yet (the helper writes the check with that id).
 */
export function panelModel(st: RouteRecStatus | null, pendingId: string | null = null): PanelModel {
  const alive = !!st && st.helper_alive;
  const state = st?.state ?? "no_helper";
  const rec = st?.recording ?? null;
  const active = alive && (ACTIVE.includes(state) || rec != null);
  const check = st?.check ?? null;
  const checking = alive && pendingId != null && check?.id !== pendingId && !active;
  const busy = st?.busy ?? null;
  let headline: string;
  if (!alive) headline = st?.detail ?? "The Record route helper is not running (poring-lab-routerec.service).";
  else if (rec?.state === "stopping" || state === "stopping") headline = "Stopping the recording…";
  else if (rec?.state === "starting" || state === "starting") headline = "Starting the recorder…";
  else if (rec) headline = `Recording ${elapsedText(rec.elapsed_s)}`;
  else if (checking) headline = "Checking the game screen…";
  else if (busy) headline = `A bot of ours is playing, so a recording cannot start: ${busy}`;
  else headline = check?.words ?? st?.detail ?? "Press Check to see whether a recording can start.";
  let items: ReadyItem[] = [];
  let ready: boolean | null = null;
  if (rec) {
    items = readyItems(rec.missing, rec.minimap, rec.xy);
    ready = rec.missing.length === 0;
  } else if (check) {
    items = readyItems(check.missing, check.minimap, check.xy);
    if (check.recorder) items.push({ key: "recorder", ok: false, text: `The recorder would refuse: ${check.recorder}` });
    ready = check.ready;
  }
  const last = st?.last ? `The last recording stopped: ${st.last.stop_reason}${st.last.bytes != null ? ` (${sizeText(st.last.bytes)})` : ""}.` : null;
  return {
    helper: alive ? "alive" : "down",
    headline,
    recording: active,
    checking,
    canCheck: alive && !active && !checking,
    canStart: alive && !active && !checking && !busy,
    canStop: alive && (rec?.state === "starting" || rec?.state === "recording"),
    ready,
    items,
    disk: rec || !check ? null : diskLine(check.disk),
    rec: rec
      ? {
          elapsed: elapsedText(rec.elapsed_s),
          size: `${sizeText(rec.disk_used_bytes)} used on the disk`,
          left: rec.minutes_left == null ? "the minutes left are not known yet" : `about ${rec.minutes_left} min left on the disk`,
          map: rec.map ?? "map not named (type /where)",
          split: rec.split,
          stopping: rec.state === "stopping",
        }
      : null,
    last,
  };
}

/**
 * The notifications that are NEW since the last poll, and the ids to remember. `seen` null (the
 * first poll after the page loads): nothing is new, so a reload never replays old toasts. The ids
 * to remember are the status's current ones (the helper drops only its oldest, which never return).
 */
export function newNotifications(
  list: RouteRecNotification[] | undefined,
  seen: string[] | null,
): { fresh: RouteRecNotification[]; seen: string[] } {
  const now = list ?? [];
  const ids = now.map((n) => n.id);
  if (seen === null) return { fresh: [], seen: ids };
  const known = new Set(seen);
  return { fresh: now.filter((n) => !known.has(n.id)), seen: ids };
}

/** A notification worth the browser's own notification (when the person allowed it): it asks the
 * person to act, or warns; "started" and a stop the person pressed stay in the page. */
export function wantsBrowserNotification(n: RouteRecNotification): boolean {
  return n.level === "action" || n.level === "warn";
}

const REASONS: Record<string, string> = {
  helper_not_running: "The Record route helper is not running (poring-lab-routerec.service).",
  already_recording: "A recording is going already: press Stop first.",
  nothing_recording: "Nothing is recording.",
  input_writer_busy: "A bot of ours is playing: a route recording is your own play, so it cannot start now.",
  map_goes_with_start: "A map name goes with Start only.",
  csrf_invalid: "The page's token expired: reload the page.",
  lab_host_peer: "Recording cannot be started from the lab computer itself: use another computer on the LAN.",
  windows_host_peer: "Recording cannot be started from the Windows game PC: use another computer on the LAN.",
  rate_limited: "Too many presses in a minute: wait a moment.",
};

/** A refusal of POST /routes/record in words, with the backend's detail where it gave one. */
export function recordReasonText(reason: string, detail?: string): string {
  const base = REASONS[reason] ?? `Refused (${reason}).`;
  return reason === "input_writer_busy" && detail ? `${base} (${detail})` : base;
}
