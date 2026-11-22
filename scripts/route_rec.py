#!/usr/bin/env python3
"""ROUTE REC -- the console's "Record route" button, the HOST side (docs/planning/
waypoints-npc-recording.md Amendment 11: phase 2 of Amendment 8 decision 5. The player records her
own play once; the recording serves the walk_to blocks and the future ML page).

    route_rec.py serve     the helper loop (scripts/host/poring-lab-routerec.service)
    route_rec.py status    print the status file
    route_rec.py check     one readiness + disk check on ONE fresh frame, printed as JSON

IT SENDS NO INPUT, EVER. It is not an input writer (ADR-0002): it reads pictures of the game
(``ro_agent.Screen``, a grabber only), the capture lock, the disk and ``ps``, and it starts and
stops ``record_session.py``. A route recording is of the PERSON's play, so a start is refused
while a bot of ours plays (``flow_run.writer_busy`` over this copy's processes,
``flow_run.copy_ps_lines``).

THE CHANNEL (the /flows Run's pattern, scripts/flow_run.py): the backend (routes_routerec.py, behind
routes_settings.write_gate unchanged) writes ONE request, ``settings/routerec/request.json``
({"id", "action": "check" | "start" | "stop", "map"?: start only}); this loop consumes it (once,
valid or not) and rewrites ``status.json`` every STATUS_EVERY_S, its heartbeat. ``settings/`` is the
human-only store, mounted only into the backend (/lab-settings).

A CHECK, and every start first (Amendment 11 / decision 3), on ONE fresh frame of the REAL client:
- the capture lock steady, rdp or console (``capture_lock.read_lock``, the function record_session
  imports as ``read_lock``); it picks record_session's ``--backend``;
- Basic Info on screen (``panelfind.find_basic_info``) and the chat window
  (``chat_window.find_any``, read only, searched outside the windows already found as
  ``ro_agent.find_panels`` searches it), both on the real client's pixels. While recording they are
  RE-CHECKED at the places found (ro_agent's own at-place re-check, < 1 ms) and searched again only
  when a re-check fails (a search is ~2 s at 1080 on bot-server);
- the minimap: present or absent, REPORTED, never required (Amendment 10: indoors has none). The
  readout is read as route_track reads a recording (``route_track.game_view``: a 1280x720 frame as
  it is, any other size through clientview's virtual client, the minimap anchored top-right; then
  ``selfpos.read_minimap(..., light=True)``). ABSENT = no parser saw a glyph (``no_glyph`` from the
  base parser and, when the light fallback ran, from it too); a readout that is there but unread
  (Prontera's paving, ``uncovered_ink``) is present;
- the recorder's own start rules for this lock: ``record_session.resolve_format`` itself (the
  default format, and its refusal in its own words; it is given the recorder's DEFAULT --out, the
  folder it will record into), then the video side's start checks (media_rec: its control and
  bitstream directories, ``dir_problem``; the sidecar running, ``container_state``) or, for h264,
  the S2 recording dir (``record_session.rec_dir``) on the local root's filesystem (it moves the
  files by rename);
- the disk the VIDEO fills: the recorder's local root (``dataset_ship.LOCAL_ROOT``, its default
  --out). Free bytes there (``dataset_ship.free_bytes``, statvfs) minus the recorder's floor
  (``dataset_ship.min_free_bytes()``, its --min-free-gb default), and no more than its unshipped
  cap leaves (``dataset_ship.MAX_UNSHIPPED_BYTES`` minus ``unshipped_bytes``: record_session's other
  local cap, ``local_caps``, refuses and stops on it too), divided by the RATE -> the minutes that
  fit. The rate is the median of this install's own finished recordings of the same format and fps
  (index.json), else the format's default (DEFAULT_RATES): the console's raw H.264 41 MB/min
  (ADR-0010 C3: 40.7 MB/min at IDR 1 s, every frame). The rdp video at 5 fps is NOT measured yet:
  no default, the minutes are then UNKNOWN (Amendment 11: measured on the dev lab before the
  estimate ships). Fewer than ``warn_minutes`` warns; 0 refuses.

A START: ``record_session.py --fps 5 --backend <the lock's> --label route --seconds <max length>
--max-bytes <what fits>``, its default format (no --format) and its DEFAULT --out (no --out: every
recording goes to the root disk as sequential files, CLAUDE.md rule 7; long-term copies reach the
NAS by shipping, ``dataset_ship.py``, never by recording onto NFS). h264 keeps record_session's own
caps (H264_MAX_SECONDS, H264_MAX_MB). The ROUTE FOLDER is Amendment 8's layout under the storage
setting (lab_env.store_dir(); no NAS assumed), and holds a POINTER to the video, not the video:

    <storage>/recordings/<YYYY-MM-DD>/<stamp>-<map or "route">-route/
      manifest.json     this helper's: purpose route, keep false, split (decided at the start),
                        start / end, the stop reason, format, fps, the recorder's argv + rc, and
                        ``session``: record_session's session id and its local path (found under
                        the local root after the start, then as record_session reports it), with
                        ``bytes`` measured from that local session folder at the end
      events.jsonl      the start, every notification shown, the minimap's changes, the readout's
                        jumps, readiness lost / back, the end (t_wall, t_mono_ns: the frames' clock)
      recorder.log      record_session's own output (its last line is its result JSON)
    <storage>/recordings/index.json   {"v", "recordings": [...]}: what the page lists, the rates
    <LOCAL_ROOT>/<stamp>-<backend>-route/   record_session's own session (its manifest, video,
                        packets), shipped later like every other session

A STOP = SIGINT to the recorder's PID (its clean end: the runbooks' ``kill -INT "$rpid"``). Not its
process group: record_session's grab helper is a ``docker exec`` child in it, and a signalled grab
helper ends the recording before its manifest is written. It also stops when the readiness is lost
for ``ready_lost_s`` (a logout, the client closed), with the reason; or by itself (its length, its
size cap, its disk or IO guard).

THE GUIDE NOTIFICATIONS (decision 1; this helper's light watch while it records: a frame every
``watch_every_s``, the minimap reader with light=True; NO input):
- "Recording started" (once the recorder has lived START_SETTLE_S) / "Recording stopped (why)";
- a MAP CHANGE -> "New map: type /where in the chat". The cue (``MapWatch``): the minimap window
  appearing or disappearing for ``confirm_reads`` reads in a row, or the readout jumping farther
  than walking allows (route_track.consistent: cheb <= max_speed * dt + slack) for
  ``confirm_reads`` reads in a row that agree with each other (one misread is no change). Shown
  once per change: ``quiet_s`` after one shown, another cue is logged, not shown;
- INDOORS (the minimap absent): "No minimap here: type /where again when you stop" every
  ``indoor_every_s`` while it stays absent (0: off);
- LOW DISK at each of ``low_disk_minutes`` (10, 2) minutes left (the most urgent one once when a
  read crosses two).
Each one has an id (``<recording id>-<n>``), goes into status.json (the last ``notify_keep``) and
into the recording's events.jsonl. The page shows the NEW ones (services/frontend/src/lib/
routerec.ts).

EVERY NUMBER is a ``RecSettings`` field, its default our value (Batt 2026-11-13: everything a user
would set is a setting); ``settings/routerec/settings.json`` may override any of them (checked;
a bad file keeps the defaults and the status says why).

KNOWN LIMITS (2026-11-22, phase 2; accepted for this phase by the parent's review):
- a helper restart mid-recording does not re-attach to the recorder: the recorder ends at its own
  --seconds, and its route folder's manifest keeps no end (the pointer is written once found);
- no sha256 of the video in the manifest yet (Amendment 8 lists one): dataset_ship's checksums
  cover the session when it is shipped.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import re
import signal
import statistics
import subprocess
import sys
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple, TypeGuard

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dataset_ship  # noqa: E402  (the disk floor and free bytes: record_session's own)
import flow_run  # noqa: E402  (writer_busy, copy_ps_lines, write_json: the Run helper's)
import lab_env  # noqa: E402  (the storage folder)
import route_track as rt  # noqa: E402  (game_view, consistent, TrackSettings, TEMPLATES)

DIR = ROOT / "settings" / "routerec"
STATE_DIR = ROOT / "state"  # the capture lock's directory (record_session: ROOT / "state")
PY = str(ROOT / ".venv" / "bin" / "python")
RECORDER = str(ROOT / "scripts" / "record_session.py")
VERSION = 1
STATUS_EVERY_S = 2.0  # the heartbeat; the backend's HELPER_FRESH_S (10 s) calls it dead after
START_SETTLE_S = 6.0  # the recorder alive this long = started (h264 waits <= 5 s for the client)
LABEL = "route"  # record_session's --label: its session is <stamp>-<backend>-route
SETTINGS_FILE = "settings.json"
INDEX = "index.json"
REQ_ID = re.compile(r"[A-Za-z0-9_-]{8,64}")
MAP_NAME = re.compile(r"[a-z0-9][a-z0-9_]{0,31}")  # a map for the folder's name (lowercase RO maps)
STAMP = "%Y%m%dT%H%M%S"  # record_session's session stamp
MB = 10**6  # record_session's mb_per_min and H264_MAX_MB are decimal
# The format's default rate (bytes a minute) and its source, until this install has its own
# recordings. ➡️ The rdp video (record_session.VIDEO_FORMAT) at 5 fps is not measured yet: it has no
# entry, so its minutes are unknown; the dev lab's measurement goes here with its source.
DEFAULT_RATES: dict[str, tuple[float, str]] = {
    "h264": (41 * MB, "the console's raw H.264, every frame: 41 MB/min (ADR-0010 C3, 40.7 at IDR "
                      "1 s)"),
}  # fmt: skip
MISSING_WORDS = {
    "capture_lock": "the capture lock is not steady on rdp or console",
    "frame": "no picture of the game could be taken",
    "basic_info": "the character's status window is not on screen",
    "chat_window": "the chat window is not on screen",
}
NO_MINIMAP = frozenset({"no_glyph", "rect_outside_frame"})  # selfpos reasons: nothing drawn there


# --- settings (every number a user setting, our value its default) ------------------------------


@dataclass(frozen=True)
class RecSettings:
    fps: float = 5.0  # Amendment 8 decision 2
    max_minutes: float = 60.0  # the max-length setting (record_session's --seconds)
    warn_minutes: float = 10.0  # fewer minutes that fit warn at the check
    watch_every_s: float = 0.5  # the guide's light watch: one frame this often
    ready_every_s: float = 5.0  # the readiness re-read while recording (recheck_ready)
    ready_lost_s: float = 60.0  # readiness lost this long stops the recording
    confirm_reads: int = 2  # a map-change cue holds for this many reads in a row
    quiet_s: float = 10.0  # one map-change notification per change
    indoor_every_s: float = 60.0  # the indoors reminder (0: off)
    low_disk_minutes: tuple[float, ...] = (10.0, 2.0)
    disk_every_s: float = 5.0  # the free bytes re-read while recording
    notify_keep: int = 20  # notifications kept in status.json
    rate_min_s: float = 60.0  # a shorter recording does not set the rate
    # the split, decided at the start (before anyone looks): the first ``held_out_first`` route
    # recordings of this install are held-out (Amendment 9's route-H1..H3), then every
    # ``held_out_every``-th (0: none)
    held_out_first: int = 3
    held_out_every: int = 5
    # route_track's consistency test for the readout's jumps (its TrackSettings' defaults)
    max_speed: float = rt.DEFAULTS.max_speed
    slack: int = rt.DEFAULTS.slack

    def track(self) -> rt.TrackSettings:
        return replace(rt.DEFAULTS, max_speed=self.max_speed, slack=self.slack)


DEFAULTS = RecSettings()


def _num(v: Any) -> TypeGuard[int | float]:
    return isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)


def _int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def settings_problem(s: Any) -> str | None:
    """PURE: why ``s`` is not usable settings (None: it is)."""
    if not isinstance(s, RecSettings):
        return "not route-recording settings"
    for name in ("fps", "max_minutes", "watch_every_s", "ready_every_s", "ready_lost_s",
                 "disk_every_s", "max_speed"):  # fmt: skip
        v = getattr(s, name)
        if not _num(v) or v <= 0:
            return f"{name} must be a number above 0"
    for name in ("warn_minutes", "quiet_s", "indoor_every_s", "rate_min_s"):
        v = getattr(s, name)
        if not _num(v) or v < 0:
            return f"{name} must be a number, 0 or more"
    for name, lo in (("confirm_reads", 1), ("notify_keep", 1), ("slack", 0),
                     ("held_out_first", 0), ("held_out_every", 0)):  # fmt: skip
        v = getattr(s, name)
        if not _int(v) or v < lo:
            return f"{name} must be a whole number, {lo} or more"
    lows = s.low_disk_minutes
    if not isinstance(lows, tuple) or not all(_num(m) and m > 0 for m in lows):
        return "low_disk_minutes must be minutes above 0"
    return None


def settings_json(s: RecSettings) -> dict[str, Any]:
    d = asdict(s)
    d["low_disk_minutes"] = list(s.low_disk_minutes)
    return d


def load_settings(path: Path) -> tuple[RecSettings, str | None]:
    """The settings file's overrides over DEFAULTS; a missing file is the defaults; a bad one is
    the defaults and why (never a half-applied file)."""
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        return DEFAULTS, None
    except (OSError, ValueError) as e:
        return DEFAULTS, f"{path.name} unreadable ({type(e).__name__}): the defaults apply"
    names = {f.name for f in fields(RecSettings)}
    if not isinstance(raw, dict) or set(raw) - names:
        bad = sorted(set(raw) - names) if isinstance(raw, dict) else "not an object"
        return DEFAULTS, f"{path.name} refused (unknown: {bad}): the defaults apply"
    if isinstance(raw.get("low_disk_minutes"), list):
        raw["low_disk_minutes"] = tuple(raw["low_disk_minutes"])
    try:
        s = replace(DEFAULTS, **raw)
    except TypeError as e:
        return DEFAULTS, f"{path.name} refused ({e}): the defaults apply"
    why = settings_problem(s)
    return (DEFAULTS, f"{path.name} refused ({why}): the defaults apply") if why else (s, None)


# --- the request (PURE) ---------------------------------------------------------------------------


def parse_request(text: str) -> dict[str, Any] | str:
    """PURE: a valid request or why it is not one: {"id", "action": "check" | "start" | "stop"},
    and for a start an optional "map" (the folder's name; nothing else in a request reaches a
    path or an argument)."""
    try:
        req = json.loads(text)
    except ValueError:
        return "unparsable request"
    if not isinstance(req, dict):
        return "unparsable request"
    rid, action = req.get("id"), req.get("action")
    if not isinstance(rid, str) or not REQ_ID.fullmatch(rid):
        return "bad request id"
    if action not in ("check", "start", "stop"):
        return f"unknown action {action!r}"
    allowed = {"id", "action", "at"} | ({"map"} if action == "start" else set())
    extra = set(req) - allowed
    if extra:
        return f"a {action} carries nothing else (got {sorted(extra)})"
    out: dict[str, Any] = {"id": rid, "action": action}
    if action == "start":
        m = req.get("map")
        if m is not None and (not isinstance(m, str) or not MAP_NAME.fullmatch(m)):
            return "a map name is lowercase letters, digits and '_' (at most 32)"
        out["map"] = m
    return out


# --- the minimap and the readiness of one frame ---------------------------------------------------


def minimap_present(reason: str, mode: str = "base", light_reason: str | None = None) -> bool:
    """PURE: is a minimap readout drawn there? ABSENT only when no parser saw a glyph: the base
    parser's ``no_glyph`` (or a rect off the frame) and, when the light fallback ran and failed,
    its own reason the same. A readout drawn but unread (Prontera's paving: base ``no_glyph`` or
    ``uncovered_ink``, the fallback ``uncovered_ink``) is present."""
    if reason not in NO_MINIMAP:
        return True
    return mode == "light_failed" and light_reason not in NO_MINIMAP and light_reason is not None


def look_minimap(frame: Any, digits: Any) -> dict[str, Any]:
    """One frame's minimap, read as route_track reads a recording: {"minimap": "present" |
    "absent" | None (no templates), "xy", "reason", "view"}."""
    region, how = rt.game_view(frame, {})
    if digits is None:
        return {"minimap": None, "xy": None, "reason": "no_templates", "view": how}
    from poring_env import selfpos

    rd = selfpos.read_minimap(region, digits, light=True)
    present = minimap_present(rd.reason, rd.mode, rd.light_reason)
    return {"minimap": "present" if present else "absent",
            "xy": None if rd.xy is None else [int(rd.xy[0]), int(rd.xy[1])],
            "reason": rd.reason, "view": how}  # fmt: skip


def look_ready(frame: Any) -> dict[str, Any]:
    """One frame's windows on the REAL client's pixels, SEARCHED as ro_agent.find_panels searches
    them (Basic Info and the hotbar, then the chat window outside the windows already found):
    {"basic_info", "chat_window", "places"}; ``places``: ro_agent.panel_places' entries of the two
    found, for ``recheck_ready``. A search takes ~2 s at 1080 on bot-server (the hotbar's 1.4 s)."""
    import chat_window as cw
    import numpy as np
    import ro_agent

    from poring_env import panelfind as pf

    bgr = np.ascontiguousarray(np.asarray(frame)[..., :3])
    lum = pf.luma(bgr)
    basic, hotbar = pf.find_basic_info(lum), pf.find_hotbar(lum)
    avoid = [(x, y, x + bw, y + bh) for f in ro_agent.panel_places(basic, hotbar, None).values()
             for (x, y), (_, _, bw, bh) in [(f["real_xy"], f["virtual"])]]  # fmt: skip
    chat = cw.find_any(bgr[..., ::-1], avoid)
    if chat is not None and int(chat.get("lines") or 0) < 1:
        chat = None
    places = ro_agent.panel_places(basic, None, chat)
    return {"basic_info": "basic_info" in places, "chat_window": "chat" in places,
            "places": places}  # fmt: skip


def recheck_ready(frame: Any, places: Mapping[str, Any]) -> dict[str, Any] | None:
    """The cheap re-check while recording (< 1 ms a window): both windows still at the places a
    search found (ro_agent's own re-check, ``_panel_still_there``), else None (search again)."""
    if "basic_info" not in places or "chat" not in places:
        return None
    import numpy as np
    import ro_agent

    from poring_env import panelfind as pf

    bgr = np.ascontiguousarray(np.asarray(frame)[..., :3])
    lum, rgb = pf.luma(bgr), bgr[..., ::-1]
    for name in ("basic_info", "chat"):
        if not ro_agent._panel_still_there(name, places[name], lum, rgb):
            return None
    return {"basic_info": True, "chat_window": True, "places": dict(places)}


def lock_ok(lock: Any) -> bool:
    return lock is not None and lock.backend in ("rdp", "console") and lock.phase == "steady"


def readiness(lock: Any, seen: Mapping[str, Any] | None) -> list[str]:
    """PURE: the missing items (MISSING_WORDS' keys), in order; [] = ready. ``seen``: look_ready's
    answer, None when no frame was taken."""
    missing = [] if lock_ok(lock) else ["capture_lock"]
    if seen is None:
        return [*missing, "frame"]
    missing += [k for k in ("basic_info", "chat_window") if not seen.get(k)]
    return missing


def missing_words(missing: Sequence[str]) -> str:
    return "; ".join(MISSING_WORDS.get(k, k) for k in missing)


# --- the guide's rules over a sequence of reads (PURE) --------------------------------------------


Cell = tuple[int, int]


class Mark(NamedTuple):
    """A cue the watch saw: ``kind`` "minimap_appeared" | "minimap_gone" | "jump"; ``shown``
    whether it became a notification (False: inside the quiet time)."""

    kind: str
    shown: bool
    xy: Cell | None = None


@dataclass
class MapWatch:
    """PURE: the map-change and indoors rules over the light watch's reads (t, present, xy)."""

    s: RecSettings = DEFAULTS
    state: bool | None = None  # the minimap's settled state (True present), None: not settled yet
    run: tuple[bool, int] | None = None  # (the other state, its reads in a row)
    anchor: tuple[float, Cell] | None = None  # the last believed cell
    anchor_ok: bool = False  # confirmed by a consistent read after it
    cand: list[tuple[float, Cell]] = field(default_factory=list)  # reads that left the anchor
    last_note: float | None = None  # the last map-change notification
    absent_since: float | None = None
    last_indoor: float | None = None

    def _settle(self, t: float, present: bool) -> bool:
        """The window's state; True when it CHANGED (a settled state flipped)."""
        if self.state is not None and present == self.state:
            self.run = None  # back to the settled state: an odd read is forgotten
            return False
        n = self.run[1] + 1 if self.run is not None and self.run[0] == present else 1
        self.run = (present, n)
        if n < self.s.confirm_reads:
            return False
        first = self.state is None
        self.state, self.run = present, None
        self.anchor, self.anchor_ok, self.cand = None, False, []
        self.absent_since, self.last_indoor = (None if present else t), None
        return not first

    def _jump(self, t: float, xy: Cell) -> bool:
        """The readout's rule: True when ``confirm_reads`` reads in a row left the believed cell
        faster than walking allows and agree with each other (a one-read misread is dropped)."""
        ts = self.s.track()
        if self.anchor is None:
            self.anchor, self.anchor_ok, self.cand = (t, xy), False, []
            return False
        ta, ca = self.anchor
        if rt.consistent(ca, ta, xy, t, ts):
            self.anchor, self.anchor_ok, self.cand = (t, xy), True, []
            return False
        if not self.anchor_ok:  # a lone first read: nothing was believed yet
            self.anchor, self.cand = (t, xy), []
            return False
        if self.cand and not rt.consistent(self.cand[-1][1], self.cand[-1][0], xy, t, ts):
            self.cand = []  # the candidates disagree: start again from this one
        self.cand.append((t, xy))
        if len(self.cand) < self.s.confirm_reads:
            return False
        self.anchor, self.anchor_ok, self.cand = (t, xy), True, []
        return True

    def feed(self, t: float, present: bool | None, xy: Cell | None) -> tuple[list[Mark], list[str]]:
        """One read -> (marks for events.jsonl, notification kinds "map_change" / "indoors").
        ``present`` None: no minimap reading at all (no frame, no templates): nothing changes."""
        marks: list[Mark] = []
        notes: list[str] = []
        if present is None:
            return marks, notes
        kind: str | None = None
        if self._settle(t, present):
            kind = "minimap_appeared" if present else "minimap_gone"
        elif self.state is True and present and xy is not None and self._jump(t, xy):
            kind = "jump"
        if kind is not None:
            shown = self.last_note is None or t - self.last_note >= self.s.quiet_s
            if shown:
                self.last_note = t
                notes.append("map_change")
            marks.append(Mark(kind, shown, xy if kind == "jump" else None))
        if self.state is False and self.s.indoor_every_s > 0 and self.absent_since is not None:
            since = self.last_indoor if self.last_indoor is not None else self.absent_since
            if t - since >= self.s.indoor_every_s:
                self.last_indoor = t
                notes.append("indoors")
        return marks, notes


@dataclass
class ReadyWatch:
    """PURE: readiness lost for ``ready_lost_s`` -> the stop reason (once)."""

    s: RecSettings = DEFAULTS
    lost_since: float | None = None
    fired: bool = False

    def feed(self, t: float, missing: Sequence[str]) -> str | None:
        if not missing:
            self.lost_since, self.fired = None, False
            return None
        if self.lost_since is None:
            self.lost_since = t
        if self.fired or t - self.lost_since < self.s.ready_lost_s:
            return None
        self.fired = True
        return f"the game was not ready for {t - self.lost_since:.0f} s ({missing_words(missing)})"


@dataclass
class DiskWatch:
    """PURE: the low-disk notifications, each threshold once; a read past several fires the most
    urgent one (and the others are spent)."""

    s: RecSettings = DEFAULTS
    fired: set[float] = field(default_factory=set)

    def feed(self, minutes_left: float | None) -> float | None:
        if minutes_left is None:
            return None
        due = [m for m in self.s.low_disk_minutes if minutes_left <= m and m not in self.fired]
        if not due:
            return None
        self.fired.update(due)
        return min(due)


# --- the disk (PURE) ------------------------------------------------------------------------------


def entry_rate(e: Mapping[str, Any]) -> float | None:
    """A finished recording's bytes a minute: record_session's own mb_per_min, else bytes over
    seconds; None when it cannot say."""
    mbm = e.get("mb_per_min")
    if _num(mbm) and mbm > 0:
        return float(mbm) * MB
    b, s = e.get("bytes"), e.get("seconds")
    if _num(b) and _num(s) and b > 0 and s > 0:
        return float(b) / (float(s) / 60.0)
    return None


def rate_of(index: Mapping[str, Any], fmt: str | None, fps: float,
            s: RecSettings = DEFAULTS) -> tuple[float | None, str]:  # fmt: skip
    """PURE: (bytes a minute or None, its source in words): the median of this install's finished
    recordings of the same format and fps (at least ``rate_min_s`` long, not refused), else the
    format's DEFAULT_RATES entry, else None (unknown)."""
    rates = []
    for e in index.get("recordings") or []:
        if not isinstance(e, Mapping) or e.get("format") != fmt or e.get("fps") != fps:
            continue
        if not e.get("end") or e.get("refused") or not _num(e.get("seconds")):
            continue
        r = entry_rate(e)
        if r is not None and float(e["seconds"]) >= s.rate_min_s:
            rates.append(r)
    if rates:
        return statistics.median(rates), (f"the median of this install's {len(rates)} finished "
                                          f"recordings ({fmt}, {fps:g} fps)")  # fmt: skip
    if fmt in DEFAULT_RATES:
        return DEFAULT_RATES[fmt]
    return None, f"not measured yet ({fmt or 'no format'} at {fps:g} fps)"


def estimate(free: int, floor: int, rate: float | None, source: str, s: RecSettings = DEFAULTS,
             *, unshipped: int = 0, cap: int | None = None) -> dict[str, Any]:  # fmt: skip
    """PURE: the minutes that fit on the recorder's local root: above its floor (``free - floor``)
    and, with ``cap``, within its unshipped cap (``cap - unshipped``), the smaller of the two
    (``limit`` says which). verdict "refuse" (nothing fits), "unknown" (room, no rate), "warn"
    (< warn_minutes), "ok"."""
    above = max(0, int(free) - int(floor))
    room = None if cap is None else max(0, int(cap) - int(unshipped))
    usable = above if room is None else min(above, room)
    limit = "unshipped" if room is not None and room < above else "floor"
    minutes = None if rate is None or rate <= 0 else int(usable // rate)
    if usable <= 0 or minutes == 0:
        verdict = "refuse"
    elif minutes is None:
        verdict = "unknown"
    elif minutes < s.warn_minutes:
        verdict = "warn"
    else:
        verdict = "ok"
    return {"free_bytes": int(free), "floor_bytes": int(floor), "unshipped_bytes": int(unshipped),
            "unshipped_cap_bytes": None if cap is None else int(cap), "usable_bytes": usable,
            "limit": limit, "rate_bytes_per_min": None if rate is None else round(rate),
            "rate_source": source, "minutes": minutes, "max_minutes": s.max_minutes,
            "verdict": verdict}  # fmt: skip


def minutes_left(free: int, floor: int, rate: float | None,
                 cap_room: int | None = None) -> float | None:  # fmt: skip
    """PURE: the minutes of recording left: above the floor and, with ``cap_room``, within what
    the unshipped cap still allows."""
    if rate is None or rate <= 0:
        return None
    left = max(0, free - floor)
    if cap_room is not None:
        left = min(left, max(0, cap_room))
    return left / rate


# --- the recording's folder, the recorder's argv, the split, the manifest, the index (PURE) ------


class Limits(NamedTuple):
    """record_session's h264 caps (H264_MAX_SECONDS, H264_MAX_MB): the S2 client's own."""

    h264_max_s: float
    h264_max_mb: int


def route_dir(root: Path, when: datetime, map_name: str | None) -> Path:
    """Amendment 8's layout: <root>/<YYYY-MM-DD>/<stamp>-<map or "route">-route."""
    return root / when.strftime("%Y-%m-%d") / f"{when.strftime(STAMP)}-{map_name or 'route'}-route"


def recorder_seconds(s: RecSettings, fmt: str | None, lim: Limits) -> float:
    secs = s.max_minutes * 60.0
    return min(secs, lim.h264_max_s) if fmt == "h264" else secs


def recorder_max_bytes(usable: int, fmt: str | None, lim: Limits) -> int:
    return min(usable, lim.h264_max_mb * MB) if fmt == "h264" else usable


def recorder_argv(py: str, backend: str, fps: float, seconds: float,
                  max_bytes: int) -> list[str]:  # fmt: skip
    """PURE: record_session's argv: its default format (no --format) and its DEFAULT --out (no
    --out: the local root, dataset_ship.LOCAL_ROOT; CLAUDE.md rule 7), --fps, the lock's backend."""
    return [py, RECORDER, "--backend", backend, "--label", LABEL, "--fps", f"{fps:g}",
            "--seconds", f"{seconds:g}", "--max-bytes", str(int(max_bytes))]  # fmt: skip


SESSION_NAME = re.compile(r"^\.?([0-9]{8}T[0-9]{6})-([a-z]+)-" + LABEL + r"(?:\.h264|\.hevc)?$")


def pick_session(names: Sequence[str], backend: str, since: str) -> str | None:
    """PURE: record_session's session id for a recording started at ``since`` (its stamp, STAMP)
    from the local root's listing and its staging dirs' (h264: ``.<id>.h264`` in the S2 dir until
    the end; the video: ``<id>/`` at once, ``.<id>.hevc`` in .media-rec): the earliest
    ``<stamp>-<backend>-route`` at or after ``since`` (record_session stamps its id a moment
    after it starts), None before it shows."""
    found = set()
    for n in names:
        m = SESSION_NAME.match(n)
        if m is not None and m.group(2) == backend and m.group(1) >= since:
            found.add(f"{m.group(1)}-{backend}-{LABEL}")
    return min(found) if found else None


def decide_split(index: Mapping[str, Any], s: RecSettings = DEFAULTS) -> tuple[str, str]:
    """PURE: (split, the rule's words) for the NEXT route recording, from the earlier ones (a
    refused start does not count): held-out for the first ``held_out_first``, then every
    ``held_out_every``-th; else train."""
    n = sum(
        1
        for e in index.get("recordings") or []
        if isinstance(e, Mapping) and e.get("purpose") == "route" and not e.get("refused")
    )
    k = n + 1  # this one's number
    if k <= s.held_out_first:
        return "held-out", f"route recording {k} of this install: the first {s.held_out_first}"
    if s.held_out_every and (k - s.held_out_first) % s.held_out_every == 0:
        return "held-out", f"route recording {k}: every {s.held_out_every}th after the first"
    return "train", f"route recording {k}"


def session_pointer(local: Path, sid: str | None, how: str | None) -> dict[str, Any]:
    """PURE: where the video is: record_session's session under the recorder's local root."""
    return {"id": sid, "path": None if sid is None else str(local / sid), "root": str(local),
            "found": how}  # fmt: skip


def manifest(rid: str, folder: Path, *, map_name: str | None, backend: str, fmt: str | None,
             fps: float, split: tuple[str, str], start: str, t0_mono_ns: int, argv: Sequence[str],
             max_bytes: int, max_s: float, check: Mapping[str, Any] | None, local: Path,
             s: RecSettings) -> dict[str, Any]:  # fmt: skip
    """PURE: the route recording's manifest at its START: a POINTER to the video (``session``,
    its id unknown until record_session makes it); end, stop reason and bytes None until the end
    (``ended``)."""
    return {"v": VERSION, "id": rid, "purpose": "route", "keep": False, "split": split[0],
            "split_rule": split[1], "dir": folder.name, "map": map_name, "backend": backend,
            "format": fmt, "fps": fps, "start": start, "end": None, "t0_mono_ns": t0_mono_ns,
            "t1_mono_ns": None, "stop_reason": None, "bytes": None, "seconds": None,
            "max_bytes": int(max_bytes), "max_s": max_s,
            "session": session_pointer(local, None, None),
            "recorder": {"argv": list(argv), "rc": None, "result": None},
            "check": dict(check) if check else None, "settings": settings_json(s)}  # fmt: skip


def ended(
    man: Mapping[str, Any],
    *,
    end: str,
    t1_mono_ns: int,
    stop_reason: str,
    rc: int | None,
    result: Mapping[str, Any] | None,
    seconds: float,
    refused: bool,
    session: Mapping[str, Any],
    folder_bytes: int | None,
) -> dict[str, Any]:
    """PURE: the manifest at the END: the stop reason, the video's pointer (``session``), its
    ``bytes`` measured from the local session folder, the recorder's own result."""
    res = dict(result) if result else None
    out = {**man, "end": end, "t1_mono_ns": t1_mono_ns, "stop_reason": stop_reason,
           "bytes": folder_bytes, "session": dict(session),
           "seconds": res.get("seconds", round(seconds, 1)) if res else round(seconds, 1),
           "refused": refused}  # fmt: skip
    out["recorder"] = {**man["recorder"], "rc": rc, "result": res}
    return out


def index_entry(man: Mapping[str, Any], rel: str) -> dict[str, Any]:
    keys = ("id", "purpose", "keep", "split", "map", "backend", "format", "fps", "start", "end",
            "bytes", "seconds", "stop_reason")  # fmt: skip
    e = {k: man.get(k) for k in keys}
    res = (man.get("recorder") or {}).get("result") or {}
    sess = man.get("session") or {}
    e.update(
        {
            "dir": rel,
            "session": sess.get("id"),
            "session_path": sess.get("path"),
            "mb_per_min": res.get("mb_per_min"),
            "refused": bool(man.get("refused")),
        }
    )
    return e


def index_put(index: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any]:
    """PURE: the index with ``entry`` added, or in place of the entry with its dir."""
    recs = [e for e in index.get("recordings") or []
            if isinstance(e, Mapping) and e.get("dir") != entry["dir"]]  # fmt: skip
    return {"v": VERSION, "recordings": [*recs, dict(entry)]}


def load_index(root: Path) -> dict[str, Any]:
    try:
        got = json.loads((root / INDEX).read_text())
    except (OSError, ValueError):
        return {"v": VERSION, "recordings": []}
    return got if isinstance(got, dict) else {"v": VERSION, "recordings": []}


def recorder_result(log: Path) -> dict[str, Any] | None:
    """record_session's result: the last JSON object line of its output with a stop_reason."""
    for ln in reversed(flow_run.tail(log, 40, 100_000)):
        with contextlib.suppress(ValueError):
            got = json.loads(ln)
            if isinstance(got, dict) and "stop_reason" in got:
                return got
    return None


RECORDER_STOPS = {
    "duration": "the maximum length was reached",
    "size_cap": "the disk reached the space kept free",
    "stopped by signal": "it was stopped",
}


def recorder_words(stop_reason: str) -> str:
    """PURE: record_session's own stop reason in plain words (its detail kept)."""
    if stop_reason in RECORDER_STOPS:
        return RECORDER_STOPS[stop_reason]
    head, _, rest = stop_reason.partition(": ")
    words = {"local_cap": "the disk check stopped it", "io_guard": "the disk guard stopped it",
             "video_failed": "the video encoder failed",
             "non_bus_frame": "the console stream went away"}.get(head)  # fmt: skip
    return f"{words}: {rest}" if words and rest else words or stop_reason


# --- notifications --------------------------------------------------------------------------------

TEXTS = {
    "started": "Recording started. Type /where in the chat once, so the route knows its map.",
    "map_change": "New map: type /where in the chat.",
    "indoors": "No minimap here: type /where again when you stop.",
}


def note_text(kind: str, **kw: Any) -> tuple[str, str]:
    """PURE: (level, words) of a notification: "info", "action" (the person types something) or
    "warn"."""
    if kind == "stopped":
        return ("info" if kw.get("by_person") else "warn"), f"Recording stopped: {kw['why']}."
    if kind == "low_disk":
        n = max(1, round(float(kw["minutes"])))
        return "warn", f"Low disk: about {n} minute{'' if n == 1 else 's'} of recording left."
    return ("info" if kind == "started" else "action"), TEXTS[kind]


def iso(t: float) -> str:
    return datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds")


# --- the side effects (thin) ----------------------------------------------------------------------


class LiveHost:
    """What the helper touches on this host: one frame of the REAL client (ro_agent.Screen, a
    grabber: no input), the capture lock, the disk, ps, the recorder."""

    def __init__(self) -> None:
        self._screen: Any = None
        self._digits: Any = None
        self._digits_tried = False

    def grab(self) -> Any:
        import numpy as np
        import ro_agent

        if self._screen is None:
            self._screen = ro_agent.Screen()
        x, y, w, h = ro_agent.real_game_region()
        return np.asarray(self._screen.grab_meta(x, y, w, h)[1])[..., :3]

    def release(self) -> None:
        if self._screen is not None:
            with contextlib.suppress(Exception):
                self._screen.close()
            self._screen = None

    def digits(self) -> Any:
        if not self._digits_tried:
            self._digits_tried = True
            from poring_env import selfpos

            try:
                self._digits = selfpos.load_digit_templates(rt.TEMPLATES)
            except (OSError, ValueError):
                self._digits = None
        return self._digits

    def lock(self) -> Any:
        from poring_backend.capture_lock import read_lock  # record_session.read_lock

        return read_lock(STATE_DIR)

    def free(self, path: Path) -> int:
        return dataset_ship.free_bytes(path)

    def floor(self) -> int:
        return dataset_ship.min_free_bytes()

    def unshipped(self, root: Path) -> int:
        return dataset_ship.unshipped_bytes(root)  # record_session's own measure (a tree walk)

    def unshipped_cap(self) -> int:
        return dataset_ship.MAX_UNSHIPPED_BYTES

    def session_names(self, local: Path) -> list[str]:
        """The local root's names and its two staging dirs' (one listing each, no walk)."""
        import media_rec
        import record_session as rs

        names: list[str] = []
        for d in (local, rs.rec_dir(local), media_rec.rec_dir(local)):
            with contextlib.suppress(OSError):
                names += os.listdir(d)
        return names

    def tree_bytes(self, path: Path) -> int | None:
        return dataset_ship.tree_bytes(path) if path.is_dir() else None

    def ps(self) -> list[str]:
        return flow_run.copy_ps_lines()

    def limits(self) -> Limits:
        import record_session as rs

        return Limits(float(rs.H264_MAX_SECONDS), int(rs.H264_MAX_MB))

    def preflight(self, backend: str, local: Path) -> tuple[str | None, str | None]:
        return preflight(backend, root=local)

    def spawn(self, argv: Sequence[str], log: Path) -> Any:
        with open(log, "ab") as fh:
            return subprocess.Popen(list(argv), cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, start_new_session=True)  # fmt: skip


def preflight(
    backend: str,
    *,
    root: Path | None = None,
    ctl: Path | None = None,
    uid: int | None = None,
    container_state: Callable[[], str] | None = None,
) -> tuple[str | None, str | None]:
    """(the default format, why record_session would refuse to start, or None), by its OWN rules,
    for its DEFAULT --out (the local root: the helper passes no --out):
    - ``record_session.resolve_format`` (it sets the default format before it refuses, so the
      format is known either way);
    - the video format: the video side's start checks, read-only, in media_rec.VideoFeed's order
      (its control and bitstream directories, ``dir_problem``; the sidecar running,
      ``container_state``: a ``docker inspect``) -- record_session refuses then ("the video side
      cannot start");
    - h264: its S2 recording dir (``rec_dir``), which must exist and sit on the local root's
      filesystem (record_h264 renames the files into the session).
    ``root`` / ``ctl`` / ``uid`` / ``container_state``: the tests' own (default: media_rec's and
    dataset_ship.LOCAL_ROOT)."""
    import media_rec
    import record_session as rs

    root = dataset_ship.LOCAL_ROOT if root is None else root
    # record_session's --out default IS dataset_ship.LOCAL_ROOT (the helper passes no --out)
    ns = argparse.Namespace(backend=backend, format=None, out=dataset_ship.LOCAL_ROOT,
                            also_png=False, seconds=0.0, max_bytes=0, idr_every=1.0)  # fmt: skip
    try:
        rs.resolve_format(ns)
    except SystemExit as e:  # ro_agent.Stop: the recorder's refusal, in its words
        return ns.format, str(e)
    if ns.format == rs.VIDEO_FORMAT:
        for d in (media_rec.CTL if ctl is None else ctl, media_rec.rec_dir(root)):
            why = media_rec.dir_problem(d, media_rec.UID if uid is None else uid)
            if why:
                return ns.format, f"the video side cannot start: {why}"
        state = (container_state or media_rec.container_state)()
        if state != "running":
            return ns.format, (f"the video side cannot start: {media_rec.CONTAINER} is {state}: "
                               f"python3 scripts/guarded_build.py start:{media_rec.SERVICE}@60 "
                               "first")  # fmt: skip
    elif ns.format == "h264":
        rec = rs.rec_dir(root)
        if not rec.is_dir():
            return ns.format, (
                f"{rec} does not exist (the S2 recording dir; compose.dev.yaml S2_REC_DIR)"
            )  # record_h264's own first refusal
        probe = root
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        if os.stat(rec).st_dev != os.stat(probe).st_dev:
            return ns.format, (
                f"{rec} is on another filesystem than {root}: record_session "
                "moves the S2 client's files by rename (same filesystem only)"
            )
    return ns.format, None


# --- the helper -----------------------------------------------------------------------------------


@dataclass
class Rec:
    """The recording going on."""

    id: str
    dir: Path
    map: str | None
    backend: str
    fmt: str | None
    split: str
    proc: Any
    log: Path
    t0: float  # the helper's clock
    start: str  # ISO
    max_s: float
    free0: int  # free bytes on the local root at the start
    rate: float | None
    rate_source: str
    unshipped0: int = 0  # unshipped bytes under the local root at the start
    cap: int | None = None  # the recorder's unshipped cap
    session: str | None = None  # record_session's session id, once found
    session_how: str | None = None  # "listing" (found under the local root) | "recorder"
    state: str = "starting"  # starting | recording | stopping
    stop_reason: str | None = None
    by_person: bool = False
    stop_t: float | None = None
    next_frame: float = 0.0
    next_ready: float = 0.0
    next_disk: float = 0.0
    minimap: str | None = None
    xy: list[int] | None = None
    missing: list[str] = field(default_factory=list)
    used: int = 0
    left: float | None = None
    bot_seen: bool = False
    n: int = 0
    places: dict[str, Any] = field(default_factory=dict)  # the windows found (recheck_ready)


class Helper:
    def __init__(self, d: Path = DIR, host: Any = None, root: Path | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 wall: Callable[[], float] = time.time,
                 local: Path | None = None) -> None:  # fmt: skip
        self.dir = d
        self.host = host if host is not None else LiveHost()
        self.root = root if root is not None else lab_env.store_dir() / "recordings"
        # the recorder's local root: its DEFAULT --out, the disk the video fills (tests: their own)
        self.local = local if local is not None else dataset_ship.LOCAL_ROOT
        self.clock, self.wall = clock, wall
        self.s, self.settings_note = load_settings(d / SETTINGS_FILE)
        self.state = "idle"
        self.detail = "waiting for the Record button"
        self.busy: str | None = None
        self.check: dict[str, Any] | None = None
        self.places: dict[str, Any] = {}  # the last check's windows found (look_ready)
        self.rec: Rec | None = None
        self.last: dict[str, Any] | None = None
        self.notes: deque[dict[str, Any]] = deque(maxlen=self.s.notify_keep)
        self.map_watch = MapWatch(self.s)
        self.ready_watch = ReadyWatch(self.s)
        self.disk_watch = DiskWatch(self.s)

    # -- status --
    def rec_status(self) -> dict[str, Any] | None:
        r = self.rec
        if r is None:
            return None
        return {"id": r.id, "dir": str(r.dir), "map": r.map, "backend": r.backend,
                "format": r.fmt, "fps": self.s.fps, "split": r.split, "started": r.start,
                "state": r.state, "elapsed_s": round(self.clock() - r.t0, 1), "max_s": r.max_s,
                "disk_used_bytes": r.used,
                "minutes_left": None if r.left is None else math.floor(r.left),
                "rate_source": r.rate_source, "ready": not r.missing, "missing": list(r.missing),
                "missing_words": missing_words(r.missing) if r.missing else None,
                "minimap": r.minimap, "xy": r.xy, "session": r.session,
                "session_path": None if r.session is None else str(self.local / r.session),
                }  # fmt: skip

    def status(self) -> dict[str, Any]:
        return {"v": VERSION, "state": self.state, "detail": self.detail, "t_wall": self.wall(),
                "busy": self.busy, "check": self.check, "recording": self.rec_status(),
                "last": self.last, "notifications": list(self.notes), "root": str(self.root),
                "local_root": str(self.local),
                "settings": settings_json(self.s), "settings_note": self.settings_note}  # fmt: skip

    def write_status(self) -> None:
        flow_run.write_json(self.dir / "status.json", self.status())

    def log_note(self, **kw: Any) -> None:
        with open(self.dir / "helper.jsonl", "a") as fh:
            fh.write(json.dumps({"t": iso(self.wall()), **kw}) + "\n")

    def busy_tick(self) -> None:
        """Another input writer of ours playing (flow_run.writer_busy): a start is refused while
        it plays; during a recording it is an event (the recording is the person's play)."""
        try:
            self.busy = flow_run.writer_busy(self.host.ps())
        except OSError:
            self.busy = None
        r = self.rec
        if r is not None:
            if self.busy and not r.bot_seen:
                r.bot_seen = True
                self.event(r, "bot_playing", why=self.busy)
            return
        if self.busy and self.state in ("idle", "busy", "ended", "failed"):
            self.state, self.detail = "busy", self.busy
        elif not self.busy and self.state == "busy":
            self.state, self.detail = "idle", "waiting for the Record button"

    # -- requests --
    def take_request(self) -> dict[str, Any] | None:
        f = self.dir / "request.json"
        if not f.exists():
            return None
        try:
            text = f.read_text()
        finally:
            f.unlink(missing_ok=True)  # a request is consumed once, valid or not
        req = parse_request(text)
        if isinstance(req, str):
            self.log_note(event="request_refused", why=req)
            self.detail = f"a request was refused: {req}"
            return None
        return req

    def handle(self, req: Mapping[str, Any]) -> None:
        if req["action"] == "stop":
            if self.rec is not None and self.rec.state in ("starting", "recording"):
                self.stop("you pressed Stop", by_person=True)
            else:
                self.detail = "nothing is recording"
            return
        if self.rec is not None:
            self.detail = (
                "a recording is going: its readiness shows here"
                if req["action"] == "check"
                else "a recording is going already: press Stop first"
            )
            self.log_note(event=f"{req['action']}_refused", why="recording", request=req["id"])
            return
        if req["action"] == "check":
            self.check = self.check_now(req["id"])
            self.detail = self.check["words"]
        else:
            self.start(req)
        if self.rec is None:
            self.host.release()  # the grab helper stays open only while a recording watches

    # -- the check --
    def frame(self) -> tuple[Any, str | None]:
        try:
            return self.host.grab(), None
        except Exception as e:  # noqa: BLE001 -- a failed grab is "no frame", never the loop's end
            return None, f"{type(e).__name__}: {e}"[:200]

    def check_now(self, rid: str | None) -> dict[str, Any]:
        """The readiness and disk check on ONE fresh frame (no input)."""
        lock_err: str | None = None
        try:
            lock = self.host.lock()
        except Exception as e:  # noqa: BLE001
            lock, lock_err = None, f"{type(e).__name__}: {e}"
        img, grab_err = self.frame()
        seen = mm = None
        if img is not None:
            seen = look_ready(img)
            mm = look_minimap(img, self.host.digits())
            self.places = dict(seen["places"])
        missing = readiness(lock, seen)
        backend = lock.backend if lock_ok(lock) else None
        fmt, problem = (None, None)
        if backend is not None:
            fmt, problem = self.host.preflight(backend, self.local)
        rate, source = rate_of(load_index(self.root), fmt, self.s.fps, self.s)
        try:  # the disk the video fills: the recorder's local root (its floor, its unshipped cap)
            disk = estimate(self.host.free(self.local), self.host.floor(), rate, source, self.s,
                            unshipped=self.host.unshipped(self.local),
                            cap=self.host.unshipped_cap())  # fmt: skip
        except OSError as e:
            disk = {"verdict": "refuse", "error": f"{type(e).__name__}: {e}", "minutes": None}
        disk["root"] = str(self.local)
        self.busy_tick()
        can = not missing and disk["verdict"] != "refuse" and problem is None and not self.busy
        if missing:
            words = f"not ready: {missing_words(missing)}"
        elif problem:
            words = f"the recorder would refuse: {problem}"
        elif disk["verdict"] == "refuse" and disk.get("limit") == "unshipped":
            words = (f"no room: recordings waiting to be shipped fill the recorder's cap under "
                     f"{self.local} (run scripts/dataset_ship.py ship)")  # fmt: skip
        elif disk["verdict"] == "refuse":
            words = (f"no room on {self.local}'s disk: nothing fits above the space the recorder "
                     "keeps free")  # fmt: skip
        elif self.busy:
            words = f"a bot of ours is playing: {self.busy}"
        elif disk["minutes"] is None:
            words = "ready; the minutes that fit are unknown (no measured rate for this format)"
        else:
            words = f"ready; about {disk['minutes']} minutes fit"
            if disk["verdict"] == "warn":
                words += f" (less than {self.s.warn_minutes:g})"
        return {"id": rid, "at": iso(self.wall()), "ready": not missing, "missing": missing,
                "missing_words": missing_words(missing) if missing else None,
                "lock": None if lock is None else {"backend": lock.backend, "phase": lock.phase,
                                                   "ok": lock_ok(lock)},
                "lock_error": lock_err, "grab_error": grab_err,
                "basic_info": None if seen is None else seen["basic_info"],
                "chat_window": None if seen is None else seen["chat_window"],
                "minimap": None if mm is None else mm["minimap"],
                "xy": None if mm is None else mm["xy"], "view": None if mm is None else mm["view"],
                "frame": None if img is None else [int(img.shape[1]), int(img.shape[0])],
                "format": fmt, "recorder": problem, "disk": disk, "busy": self.busy,
                "can_start": can, "words": words}  # fmt: skip

    # -- start / stop --
    def start(self, req: Mapping[str, Any]) -> None:
        chk = self.check_now(req["id"])
        self.check = chk
        if not chk["can_start"]:
            self.detail = f"not started: {chk['words']}"
            self.log_note(event="start_refused", why=chk["words"], request=req["id"])
            return
        now = self.wall()
        when = datetime.fromtimestamp(now)
        folder = route_dir(self.root, when, req.get("map"))
        if folder.exists():
            self.detail = f"not started: {folder} exists already"
            return
        lim = self.host.limits()
        backend, fmt = chk["lock"]["backend"], chk["format"]
        seconds = recorder_seconds(self.s, fmt, lim)
        max_bytes = recorder_max_bytes(int(chk["disk"]["usable_bytes"]), fmt, lim)
        argv = recorder_argv(PY, backend, self.s.fps, seconds, max_bytes)  # no --out: LOCAL_ROOT
        index = load_index(self.root)
        split = decide_split(index, self.s)
        rid = when.strftime(STAMP)
        t0 = self.clock()
        man = manifest(rid, folder, map_name=req.get("map"), backend=backend, fmt=fmt,
                       fps=self.s.fps, split=split, start=iso(now), t0_mono_ns=int(t0 * 1e9),
                       argv=argv, max_bytes=max_bytes, max_s=seconds, check=chk,
                       local=self.local, s=self.s)  # fmt: skip
        try:
            folder.mkdir(parents=True)
            flow_run.write_json(folder / "manifest.json", man)
            self.save_index(index_put(index, index_entry(man, self.rel(folder))))
        except OSError as e:  # the storage folder (a NAS mount may be away): refused in words
            self.detail = f"not started: the recordings folder could not be written ({e})"
            self.log_note(event="start_refused", why=self.detail, request=req["id"])
            return
        r = Rec(id=rid, dir=folder, map=req.get("map"), backend=backend, fmt=fmt, split=split[0],
                proc=None, log=folder / "recorder.log", t0=t0, start=iso(now), max_s=seconds,
                free0=int(chk["disk"]["free_bytes"]),
                rate=chk["disk"]["rate_bytes_per_min"], rate_source=chk["disk"]["rate_source"],
                unshipped0=int(chk["disk"].get("unshipped_bytes") or 0),
                cap=chk["disk"].get("unshipped_cap_bytes"), next_frame=t0,
                next_ready=t0 + self.s.ready_every_s, next_disk=t0 + self.s.disk_every_s,
                places=dict(self.places))  # fmt: skip
        self.rec = r
        self.map_watch, self.ready_watch = MapWatch(self.s), ReadyWatch(self.s)
        self.disk_watch = DiskWatch(self.s)
        self.event(r, "start", request=req["id"], argv=argv, split=split[0])
        try:
            r.proc = self.host.spawn(argv, r.log)
        except OSError as e:
            self.finish(None, f"the recorder could not be started ({type(e).__name__}: {e})")
            return
        self.state, self.detail = "starting", "the recorder is starting"
        self.log_note(event="start", id=rid, dir=str(folder), argv=argv)

    def stop(self, why: str, *, by_person: bool = False) -> None:
        r = self.rec
        if r is None or r.proc is None:
            return
        r.stop_reason, r.by_person, r.stop_t = why, by_person, self.clock()
        r.state = "stopping"
        self.state, self.detail = "stopping", f"stopping: {why}"
        self.event(r, "stop", why=why)
        with contextlib.suppress(ProcessLookupError, OSError):
            r.proc.send_signal(signal.SIGINT)  # its PID only: record_session's clean end

    # -- the watch while recording --
    def tick(self) -> None:
        r = self.rec
        if r is None:
            return
        now = self.clock()
        rc = r.proc.poll() if r.proc is not None else None
        if rc is not None:
            self.finish(rc)
            return
        if r.state == "starting" and now - r.t0 >= START_SETTLE_S:
            r.state = "recording"
            self.state, self.detail = "recording", "recording the person's play"
            self.notify(r, "started")
        if r.state == "stopping":
            if r.stop_t is not None and now - r.stop_t > 120:
                self.detail = f"stopping: the recorder has not ended {now - r.stop_t:.0f} s after"
            return
        if now >= r.next_frame:
            r.next_frame = now + self.s.watch_every_s
            self.watch_frame(r, now)
        if now >= r.next_disk:
            r.next_disk = now + self.s.disk_every_s
            self.watch_disk(r)

    def watch_frame(self, r: Rec, now: float) -> None:
        img, grab_err = self.frame()
        if img is None:
            mm: dict[str, Any] = {"minimap": None, "xy": None}
        else:
            mm = look_minimap(img, self.host.digits())
        present = None if mm["minimap"] is None else mm["minimap"] == "present"
        xy = None if mm["xy"] is None else (int(mm["xy"][0]), int(mm["xy"][1]))
        r.minimap, r.xy = mm["minimap"], mm["xy"]
        marks, notes = self.map_watch.feed(now, present, xy)
        for m in marks:
            self.event(r, m.kind, shown=m.shown, xy=None if m.xy is None else list(m.xy))
        for k in notes:
            self.notify(r, k)
        if now < r.next_ready:
            return
        r.next_ready = now + self.s.ready_every_s
        try:
            lock = self.host.lock()
        except Exception:  # noqa: BLE001
            lock = None
        seen = None
        if img is not None:
            seen = recheck_ready(img, r.places) or look_ready(img)
            r.places = dict(seen["places"])
        missing = readiness(lock, seen)
        if lock_ok(lock) and lock.backend != r.backend:
            missing = ["capture_lock", *missing]
        if missing != r.missing:
            self.event(r, "ready_lost" if missing else "ready_back", missing=missing,
                       grab_error=grab_err)  # fmt: skip
        r.missing = missing
        why = self.ready_watch.feed(now, missing)
        if why is not None:
            self.stop(why)

    def watch_disk(self, r: Rec) -> None:
        """The local root's free bytes (the disk the video fills): the minutes left, low disk; and
        the session pointer, until it is found."""
        if r.session is None:
            self.find_session(r)
        try:
            free, floor = self.host.free(self.local), self.host.floor()
        except OSError:
            return
        r.used = max(0, r.free0 - free)
        elapsed_min = (self.clock() - r.t0) / 60.0
        rate = r.rate
        if rate is None and elapsed_min >= 1.0 and r.used > 0:  # unknown: this recording's own
            rate = r.used / elapsed_min
        room = None if r.cap is None else r.cap - r.unshipped0 - r.used
        r.left = minutes_left(free, floor, rate, room)
        hit = self.disk_watch.feed(r.left)
        if hit is not None and r.left is not None:
            self.notify(r, "low_disk", minutes=r.left)

    def find_session(self, r: Rec) -> None:
        """record_session's session under the local root (one listing each of it and its staging
        dirs): written into the manifest at once, so the pointer survives a helper restart."""
        try:
            sid = pick_session(self.host.session_names(self.local), r.backend, r.id)
        except OSError:
            return
        if sid is None:
            return
        r.session, r.session_how = sid, "listing"
        self.event(r, "session_found", session=sid, path=str(self.local / sid))
        try:
            man = json.loads((r.dir / "manifest.json").read_text())
            man["session"] = session_pointer(self.local, sid, "listing")
            flow_run.write_json(r.dir / "manifest.json", man)
        except (OSError, ValueError) as e:
            self.log_note(event="pointer_not_written", id=r.id, why=str(e))

    def finish(self, rc: int | None, why: str | None = None) -> None:
        r = self.rec
        assert r is not None
        res = recorder_result(r.log)
        refused = r.state == "starting" and r.stop_reason is None and rc != 0
        if why is None:
            if r.stop_reason is not None:
                why = r.stop_reason
            elif rc == 0 and res is not None:
                why = recorder_words(str(res.get("stop_reason")))
            else:
                last = next(iter(reversed(flow_run.tail(r.log, 3, 300))), "")
                why = (f"the recorder refused to start ({last})" if refused
                       else f"the recorder ended rc {rc} ({last})")  # fmt: skip
        # the pointer: as record_session reports its session, else as found under the local root
        local, sid, how = self.local, r.session, r.session_how
        if res is not None and isinstance(res.get("dir"), str) and res["dir"]:
            reported = Path(res["dir"])
            local, sid, how = reported.parent, reported.name, "recorder"
        elif sid is None and r.proc is not None:
            self.find_session(r)
            sid, how = r.session, r.session_how
        pointer = session_pointer(local, sid, how)
        folder_bytes = None
        if sid is not None:
            with contextlib.suppress(OSError):
                folder_bytes = self.host.tree_bytes(local / sid)  # the local session folder
        try:
            man = json.loads((r.dir / "manifest.json").read_text())
        except (OSError, ValueError):
            man = None
        t1 = self.clock()
        if man is not None:  # the end's files: never fatal (the recording is the recorder's)
            man = ended(
                man,
                end=iso(self.wall()),
                t1_mono_ns=int(t1 * 1e9),
                stop_reason=why,
                rc=rc,
                result=res,
                seconds=t1 - r.t0,
                refused=refused or r.proc is None,
                session=pointer,
                folder_bytes=folder_bytes,
            )
            try:
                flow_run.write_json(r.dir / "manifest.json", man)
                self.save_index(index_put(load_index(self.root), index_entry(man, self.rel(r.dir))))
            except OSError as e:
                self.log_note(event="end_files_not_written", id=r.id, why=str(e))
        self.notify(r, "stopped", why=why, by_person=r.by_person)
        self.event(r, "end", rc=rc, why=why, bytes=folder_bytes, session=pointer["path"])
        self.last = {"id": r.id, "dir": str(r.dir), "ended": iso(self.wall()), "stop_reason": why,
                     "rc": rc, "bytes": folder_bytes, "session": pointer["id"],
                     "session_path": pointer["path"], "split": r.split,
                     "refused": refused}  # fmt: skip
        ok = rc == 0 and not refused
        self.state, self.detail = ("ended" if ok else "failed"), f"stopped: {why}"
        self.log_note(event="end", id=r.id, rc=rc, why=why)
        self.rec = None
        self.host.release()

    # -- files --
    def rel(self, folder: Path) -> str:
        try:
            return str(folder.relative_to(self.root))
        except ValueError:
            return str(folder)

    def save_index(self, index: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        flow_run.write_json(self.root / INDEX, index)

    def event(self, r: Rec, kind: str, **kw: Any) -> None:
        t = self.clock()
        line = {"t_wall": iso(self.wall()), "t_mono_ns": int(t * 1e9), "kind": kind, **kw}
        try:
            with open(r.dir / "events.jsonl", "a") as fh:
                fh.write(json.dumps(line) + "\n")
        except OSError as e:
            self.log_note(event="events_not_written", why=f"{type(e).__name__}: {e}", kind=kind)

    def notify(self, r: Rec, kind: str, **kw: Any) -> None:
        r.n += 1
        level, text = note_text(kind, **kw)
        n = {"id": f"{r.id}-{r.n}", "kind": kind, "level": level, "text": text,
             "at": iso(self.wall()), "recording": r.id}  # fmt: skip
        self.notes.append(n)
        self.event(r, "notification", id=n["id"], note=kind, level=level, text=text)

    def serve(self) -> int:
        self.dir.mkdir(parents=True, exist_ok=True)
        os.environ.pop("PORING_CONFIRM_READS", None)  # selfpos.CONFIRM_READS_ENV: raw reads here
        stopping = {"flag": False}

        def on_term(*_: object) -> None:
            stopping["flag"] = True

        signal.signal(signal.SIGTERM, on_term)
        signal.signal(signal.SIGINT, on_term)
        last = 0.0
        while True:
            if stopping["flag"]:
                if self.rec is None:
                    self.state, self.detail = "idle", "the helper stopped"
                    self.write_status()
                    return 0
                if self.rec.state != "stopping":
                    self.stop("the helper was stopped")
            else:
                try:
                    req = self.take_request()
                    if req is not None:
                        self.handle(req)
                        self.write_status()
                except Exception as e:  # noqa: BLE001 -- one bad request never ends the helper
                    self.log_note(event="error", where="request", why=f"{type(e).__name__}: {e}")
                    self.detail = f"a request failed: {type(e).__name__}: {e}"
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001 -- the heartbeat and the recorder go on
                self.log_note(event="error", where="tick", why=f"{type(e).__name__}: {e}")
            if time.monotonic() - last >= STATUS_EVERY_S:
                self.busy_tick()
                self.write_status()
                last = time.monotonic()
            time.sleep(self.s.watch_every_s if self.rec is not None else 0.5)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve")
    sub.add_parser("status")
    sub.add_parser("check", help="one readiness + disk check on one fresh frame (no input)")
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        return Helper().serve()
    if a.cmd == "status":
        f = DIR / "status.json"
        print(f.read_text() if f.exists() else '{"state": "no helper"}')
        return 0
    h = Helper()
    try:
        print(json.dumps(h.check_now(None), indent=2))
    finally:
        h.host.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
