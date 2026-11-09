#!/usr/bin/env python3
"""The VIDEO SIDE of an RDP recording: the GPU encoder in the contained sidecar ``media-rec``, fed
raw BGRA by record_session.py. STAGE 3 (ADR-0024, Batt 2026-11-09): the video IS the recording on
rdp by default (``--format vpp-hevc444-10-q20``: no PNG; poring_dataset.frames reads it). STAGE 2
(docs/planning/gpu-recording.md 9.1, its bars PRE-REGISTERED before any run): ONE side-by-side
recording, ``--also-png``: every frame kept as lossless PNG is ALSO fed to round 3's candidate
encoder (``vpp-hevc444-10-q20``, doc 8.4), so the two recordings of ONE session can be compared
frame by frame (``check``; stage 2 PASSED every bar, 9.3).

    media_rec.py prep        create the two directories the sidecar binds (ours, mode 0700)
    media_rec.py status      read-only: the sidecar's state, its control directory, leftovers
    media_rec.py check SESSION --map MAP --out OUT.json [--pilot DIR] [--baseline DIR]
                       [--det-threads 4] [--det-every 1] [--no-detector]

THE MECHANISM (doc 9.1):

    backend (X grab) --docker exec pipe, raw BGRA--> host recorder --PNG--> session/shard-*.tar
                                                        |
                       raw BGRA, ONE named pipe in a RAM directory (/dev/shm/poring-lab-mediarec)
                                                        v
       the sidecar (media-probe image; no network, read-only, the render node only): ffmpeg
       hwupload -> scale_vaapi (BT.709 full, xv30) -> hevc_vaapi Main 4:4:4 10, CQP 20, all-intra
                                                        |
                 sequential, to ~/poring-lab-rec/.media-rec/.<sid>.hevc (dot-named: never shipped)
                                                        v
       at the end the host RENAMES it into the session (the same filesystem, no copy):
       session/video.hevc + video.idx.csv (one row per kept frame: INDEX_FIELDS + EXTRA_FIELDS,
       the PNG record's t_wall / bus_frame_id / source) + video.ffmpeg.log

* The host side (VideoFeed) never blocks the recorder's loop: ``offer`` puts the frame on a bounded
  queue (QUEUE_FRAMES); a full queue DROPS that frame from the video (its row says so); a feeder
  thread writes the queue to the pipe.
* FAIL-SAFE: the encoder closing its pipe (EPIPE), a frame write blocked for STALL_S, or the
  feeder dying ends the VIDEO side, once, with its reason in the manifest's ``video``. Video-only:
  the recorder then STOPS the session cleanly (``video_failed: ...``), the frames already in the
  stream are the session. Stage 2: the PNG frames go on to the end of the session (the PNG is the
  reference). A video side that cannot START refuses the recording (video-only: every part; stage
  2: part 0, a later --resume part records PNG only and says why).
* The alpha byte is set to 255 on the copy that is fed: the bench encoded PNGs, which ffmpeg turns
  into BGRA with alpha 255, and the grab's own alpha is not specified.
* One recorder at a time (an exclusive flock on the control directory); one job at a time in the
  sidecar (services/media-probe/mediarec.sh, its only reader of the pipe).
* ``check`` (offline, host CPU, after the recording): every kept frame's video twin decoded (PyAV,
  software, one thread) and compared with its PNG: gpu_rec_bench's metrics and bars (Q1-Q6, G1,
  P1-P3 with the map's CPU detector, D1, S1), the stage-2 bars (STAGE2_BARS: completeness, the
  video side's CPU per frame with the hop, the detect server's latency against a pilot without
  the recording), and recorder_boxes' own comparison of the two box files.

Pixels in only (rule 1): no client, no input. ``check`` writes boxes and numbers, never pixels.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import csv
import errno
import fcntl
import json
import os
import queue
import re
import stat
import statistics
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

ARM = "vpp-hevc444-10-q20"  # round 3's CANDIDATE (doc 8.4); mediarec.sh's options are its own
SERVICE = "media-rec"
CONTAINER = "poring-lab-media-rec-1"
CTL = Path("/dev/shm/poring-lab-mediarec")  # RAM: the job, the pipe, small status files
REC_NAME = ".media-rec"  # under the local session root: the sidecar's bitstream (disk)
UID = 1000  # compose's user for the sidecar (the host's bot)
FIFO, JOB, RUNNING, LOCK = "frames.fifo", "job", "running", "lock"
QUEUE_FRAMES = 8  # ~30 MB of 1280 x 720 BGRA: the encoder may lag this far before frames drop
OPEN_TIMEOUT_S = 15.0  # the sidecar must open the pipe's other end within this
STALL_S = 20.0  # a frame write blocked this long: the encoder is not reading (the video fails)
DONE_TIMEOUT_S = 60.0  # after the last frame: the sidecar's done file within this
PIPE_BYTES = 1 << 20  # F_SETPIPE_SZ: /proc/sys/fs/pipe-max-size's default
SIZE_EVERY_S = 1.0  # the part file's size is re-read at most this often
NEAR_AFTER_MS = 50.0  # a detect call within a frame write's span + this is "near" an encode
DROPPED_LISTED = 200  # the manifest lists at most this many frame ids per status
# the session id record_session makes (rdp only: the console records Sunshine's H.264): the same
# pattern as mediarec.sh's JOB_RE (test_media_rec pins the two)
SID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}-rdp-[A-Za-z0-9_.-]{1,64}$")
JOB_RE = re.compile(
    r"^start ([0-9]{8}T[0-9]{6}-rdp-[A-Za-z0-9_.-]{1,64}) ([1-9][0-9]{1,4}) ([1-9][0-9]{1,4}) "
    r"([1-9][0-9]{0,12})$"
)
INDEX_FIELDS = ("frame_id", "t_mono_ns", "video_index", "status", "write_start_ns", "write_end_ns")
# stage 3 (ADR-0024): the PNG record's own fields, so a video-only session keeps every field a
# PNG session's json member holds (poring_dataset.frames reads them back; empty when not given)
EXTRA_FIELDS = ("t_wall", "bus_frame_id", "source")


def local_root() -> Path:
    """The recorder's local session root (dataset_ship.LOCAL_ROOT: ~/poring-lab-rec)."""
    return Path.home() / "poring-lab-rec"


def rec_dir(root: Path | None = None) -> Path:
    return (root or local_root()) / REC_NAME


class VideoRefused(Exception):
    """The video side cannot start: nothing was fed."""


# --- pure helpers ---------------------------------------------------------------------------------


def job_line(sid: str, w: int, h: int, max_bytes: int) -> str:
    """PURE: the sidecar's job (mediarec.sh's JOB_RE); refuses what the sidecar would refuse."""
    line = f"start {sid} {int(w)} {int(h)} {int(max_bytes)}"
    if not SID_RE.match(sid) or not JOB_RE.match(line):
        raise VideoRefused(f"not a sidecar job: {line!r} (an rdp session id, sizes 10..99999)")
    return line


def parse_done(text: str) -> dict[str, str]:
    """PURE: the sidecar's done file (KEY=value lines: SID, RC, BYTES, ENDED, NOTE)."""
    out = {}
    for ln in text.splitlines():
        k, eq, v = ln.partition("=")
        if eq and re.fullmatch(r"[A-Z]+", k):
            out[k] = v
    return out


def force_alpha(img: Any) -> Any:
    """A BGRA copy of ``img`` with alpha 255 (the bench's PNG input had it; the grab's is not
    specified). The grab's array is read-only, so this is the one copy the video side makes."""
    import numpy as np

    out = np.array(img, dtype=np.uint8, copy=True, order="C")
    out[..., 3] = 255
    return out


def overlaps(a0: int, a1: int, b0: int, b1: int) -> bool:
    return a0 <= b1 and b0 <= a1


def near_encode(calls: Sequence[dict[str, Any]], writes: Sequence[tuple[int, int]],
                after_ms: float = NEAR_AFTER_MS) -> tuple[list[dict[str, Any]],
                                                          list[dict[str, Any]]]:  # fmt: skip
    """PURE: the detect calls (detections.jsonl rows: ``t_ns`` logged after the call, ``ms`` its
    length) split into those whose span meets a frame write's [start, end + after_ms] (the encode
    follows the write within a few ms) and the rest. ``writes`` sorted by start."""
    near, far = [], []
    starts = [w[0] for w in writes]
    import bisect

    pad = int(after_ms * 1e6)
    for c in calls:
        t1 = int(c["t_ns"])
        t0 = t1 - int(float(c.get("ms") or 0.0) * 1e6)
        i = bisect.bisect_right(starts, t1) - 1
        hit = False
        for j in (i, i - 1):
            if 0 <= j < len(writes) and overlaps(t0, t1, writes[j][0], writes[j][1] + pad):
                hit = True
                break
        (near if hit else far).append(c)
    return near, far


def window_rows(rows: Sequence[dict[str, Any]], t0: int, t1: int) -> list[dict[str, Any]]:
    """PURE: the detect calls logged inside [t0, t1] (the recording's own monotonic span)."""
    return [r for r in rows if r.get("t_ns") is not None and t0 <= int(r["t_ns"]) <= t1]


def ms_per_frame(seconds: float | None, frames: int) -> float | None:
    return None if seconds is None or frames <= 0 else round(seconds * 1000 / frames, 3)


# --- the pre-registered stage-2 bars (doc 9.1; a test keeps the doc's table and these equal) ----

STAGE2_BARS: dict[str, float] = {
    "K1_missing": 0,  # kept PNG frames without a decoded video twin, at most
    "C1_video_ms": 20.0,  # the video side's CPU per kept frame (feed thread + sidecar), ms
    "C2_png_ratio": 0.2,  # ... and at most this x the PNG writer's CPU per frame (same session)
    "C3_hop_ms": 5.0,  # the hop's host side (the feed thread: copy + pipe write) per frame, ms
    "L1_p50_ms": 1.0,  # the detect server's GPU call p50 during the recording - the baseline's
    "L2_p95_ms": 3.0,  # ... and its p95 - the baseline's, ms, at most
    "L3_gpu_share": -0.01,  # the share of calls the GPU answered - the baseline's, at least
    "L_min_calls": 500,  # L1-L3 graded only with at least this many calls on each side (else NA)
}
# gpu_rec_bench's bars that are stage 1's own, not stage 2's: the container's encode timing from
# RAM (S2, S3; stage 2 measures the whole video side instead, C1-C3) and the VA-API decode (D2:
# stage 2 runs no container decode; stage 1 proved VA = software = host on this encoder)
STAGE1_ONLY = ("S2", "S3", "D2")


def _bar(ok: bool | None, value: Any, need: str) -> dict[str, Any]:
    return {"result": "NA" if ok is None else ("PASS" if ok else "FAIL"), "value": value,
            "need": need}  # fmt: skip


def stage2_bars(res: dict[str, Any], bars: dict[str, float] = STAGE2_BARS
                ) -> dict[str, dict[str, Any]]:  # fmt: skip
    """PURE: a check's measures -> the stage-2 bars (K1, F1, C1-C3, L1-L3)."""
    b = bars
    out: dict[str, dict[str, Any]] = {}
    k = res["completeness"]
    missing = k["kept"] - k["matched"]
    out["K1"] = _bar(missing <= b["K1_missing"] and k["undecodable"] == 0
                     and k["decoded"] == k["fed"], [missing, k["undecodable"], k["decoded"],
                                                    k["fed"]],
                     f"kept - matched <= {b['K1_missing']:g}, every fed frame decoded")  # fmt: skip
    vui = res.get("vui") or {}
    out["F1"] = _bar(bool(vui) and vui.get("frames", 0) > 0 and vui.get("frames") == vui.get("ok"),
                     [vui.get("ok"), vui.get("frames"), vui.get("seen")],
                     "every decoded frame signals pc / bt709")  # fmt: skip
    c = res["cpu"]
    v, png = c.get("video_ms_per_frame"), c.get("png_writer_ms_per_frame")
    hop = c.get("feed_ms_per_frame")
    out["C1"] = _bar(None if v is None else v <= b["C1_video_ms"], v, f"<= {b['C1_video_ms']} ms")
    out["C2"] = _bar(None if v is None or png is None else v <= b["C2_png_ratio"] * png,
                     [v, png], f"<= {b['C2_png_ratio']} x the PNG writer's")  # fmt: skip
    out["C3"] = _bar(None if hop is None else hop <= b["C3_hop_ms"], hop, f"<= {b['C3_hop_ms']} ms")
    lat = res.get("latency") or {}
    rec, base = lat.get("recording") or {}, lat.get("baseline") or {}
    n_rec, n_base = rec.get("calls") or 0, base.get("calls") or 0
    powered = n_rec >= b["L_min_calls"] and n_base >= b["L_min_calls"]
    for key, field, lim, sign in (("L1", "gpu_ms_p50", "L1_p50_ms", 1),
                                  ("L2", "gpu_ms_p95", "L2_p95_ms", 1),
                                  ("L3", "gpu_share", "L3_gpu_share", -1)):  # fmt: skip
        a, z = rec.get(field), base.get(field)
        if not powered or a is None or z is None:
            need = f"a pilot and a baseline with >= {b['L_min_calls']:g} calls each"
            out[key] = _bar(None, [n_rec, n_base], need)
            continue
        d = round(a - z, 4)
        ok = d <= b[lim] if sign > 0 else d >= b[lim]
        out[key] = _bar(ok, [a, z, d], f"recording - baseline {'<=' if sign > 0 else '>='} "
                                       f"{b[lim]}")  # fmt: skip
    return out


def stage2_verdict(quality_bars: dict[str, dict[str, Any]],
                   s2: dict[str, dict[str, Any]]) -> dict[str, Any]:  # fmt: skip
    """PURE: doc 9.1's rule. PASS: no bar FAILS, and every bar is MEASURED (not NA) except Q6
    (NA with too few saturated pixels, as in stage 1). The quality bars are gpu_rec_bench's,
    minus STAGE1_ONLY; P must be powered (P1-P3 present)."""
    fails = sorted(k for d in (quality_bars, s2) for k, r in d.items() if r["result"] == "FAIL")
    na = sorted(k for d in (quality_bars, s2) for k, r in d.items()
                if r["result"] == "NA" and k != "Q6")  # fmt: skip
    powered = "P1" in quality_bars
    return {"pass": not fails and not na and powered, "fail": fails, "not_measured": na,
            "detector_powered": powered}  # fmt: skip


# --- the host side of the feed --------------------------------------------------------------------


def container_state(name: str = CONTAINER) -> str:
    """Read-only: the sidecar's state ("running", "exited", ..., or "absent")."""
    res = subprocess.run(["docker", "inspect", "-f", "{{.State.Status}}", name],
                         capture_output=True, text=True, check=False)  # fmt: skip
    return res.stdout.strip() if res.returncode == 0 and res.stdout.strip() else "absent"


def container_image(name: str = CONTAINER) -> str | None:
    """Read-only: the sidecar's image id (provenance in the manifest)."""
    res = subprocess.run(["docker", "inspect", "-f", "{{.Image}}", name], capture_output=True,
                         text=True, check=False)  # fmt: skip
    return (res.stdout.strip() or None) if res.returncode == 0 else None


def dir_problem(path: Path, uid: int = UID) -> str | None:
    """Why ``path`` is not a directory the sidecar may share: ours, a real directory, mode 0700."""
    try:
        st = path.lstat()
    except FileNotFoundError:
        return f"{path} does not exist (python3 scripts/media_rec.py prep)"
    if not stat.S_ISDIR(st.st_mode):
        return f"{path} is not a directory"
    if st.st_uid != uid or os.getuid() != uid:
        return f"{path}: owner {st.st_uid}, this process {os.getuid()}, the sidecar {uid}"
    if stat.S_IMODE(st.st_mode) != 0o700:
        return f"{path}: mode {stat.S_IMODE(st.st_mode):o}, not 700"
    return None


class VideoFeed:
    """The video side of one session (see the module doc). ``start`` (refuses with VideoRefused),
    then ``offer`` per kept frame from the PNG loop (never blocks), ``check`` for a failure to
    report, ``bytes`` for the size caps, ``finish(session_dir)`` -> the manifest's ``video``."""

    def __init__(self, sid: str, w: int, h: int, max_bytes: int, *, ctl: Path = CTL,
                 rec: Path | None = None, queue_frames: int = QUEUE_FRAMES,
                 open_timeout_s: float = OPEN_TIMEOUT_S, stall_s: float = STALL_S,
                 done_timeout_s: float = DONE_TIMEOUT_S, pipe_bytes: int | None = PIPE_BYTES,
                 uid: int = UID, require_container: bool = True,
                 clock: Callable[[], float] = time.monotonic,
                 ns: Callable[[], int] = time.monotonic_ns) -> None:  # fmt: skip
        self.sid, self.w, self.h, self.max_bytes = sid, int(w), int(h), int(max_bytes)
        self.ctl, self.rec = ctl, rec or rec_dir()
        self.line = job_line(sid, w, h, max_bytes)
        self.part = self.rec / f".{sid}.hevc"
        self.log = self.rec / f".{sid}.ffmpeg.log"
        self.done = self.ctl / f"done-{sid}"
        self.fifo = self.ctl / FIFO
        self.open_timeout_s, self.stall_s, self.done_timeout_s = (open_timeout_s, stall_s,
                                                                  done_timeout_s)  # fmt: skip
        self.pipe_bytes, self.uid, self.require_container = pipe_bytes, uid, require_container
        self.clock, self.ns = clock, ns
        self.status = "new"  # new -> feeding -> ok | failed | refused
        self.reason: str | None = None
        self.failed_at: int | None = None  # ns
        self.rows: list[dict[str, Any]] = []
        self.feed_cpu_s = 0.0
        self.write_ms: list[float] = []
        self.fed = 0
        self.max_queue = 0
        self._q: queue.Queue[tuple[dict[str, Any], Any] | None] = queue.Queue(queue_frames)
        self._fd: int | None = None
        self._lock_fd: int | None = None
        self._thread: threading.Thread | None = None
        self._writing_since: float | None = None
        self._size, self._size_at = 0, -1e9
        self._made_fifo = False  # only a FIFO this feed made is ever removed by it
        self.started_ns: int | None = None
        self.image: str | None = None
        self.pipe_size: int | None = None

    # -- start ----------------------------------------------------------------------------------
    def start(self) -> None:
        try:
            self._start()
        except VideoRefused as exc:
            self.status, self.reason = "refused", str(exc)
            self._release()
            raise

    def _start(self) -> None:
        for d in (self.ctl, self.rec):
            why = dir_problem(d, self.uid)
            if why:
                raise VideoRefused(why)
        if self.require_container:
            state = container_state()
            if state != "running":
                raise VideoRefused(f"{CONTAINER} is {state}: python3 scripts/guarded_build.py "
                                   f"start:{SERVICE}@60 first")  # fmt: skip
            self.image = container_image()
        self._lock_fd = os.open(self.ctl / LOCK, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise VideoRefused("another recorder holds the sidecar (its lock)") from exc
        for busy in (JOB, RUNNING):
            if (self.ctl / busy).exists():
                raise VideoRefused(f"{self.ctl / busy} exists: the sidecar has a job (status)")
        for p in (self.part, self.log, self.done):
            if p.exists():
                raise VideoRefused(f"{p} already exists")
        if self.fifo.exists() or self.fifo.is_symlink():
            self.fifo.unlink()
        os.mkfifo(self.fifo, 0o600)
        self._made_fifo = True
        tmp = self.ctl / f".{JOB}.tmp"
        tmp.write_text(self.line + "\n")
        tmp.replace(self.ctl / JOB)
        deadline = self.clock() + self.open_timeout_s
        while True:
            try:
                fd = os.open(self.fifo, os.O_WRONLY | os.O_NONBLOCK)
                break
            except OSError as exc:
                if exc.errno != errno.ENXIO:
                    raise VideoRefused(f"the frame pipe: {exc}") from exc
            if self.done.exists():  # the sidecar refused or its ffmpeg ended at once
                d = parse_done(self.done.read_text())
                raise VideoRefused(f"the sidecar ended the job at its start: rc {d.get('RC')}, "
                                   f"{d.get('NOTE')} (see {self.log})")  # fmt: skip
            if self.clock() > deadline:
                self._abandon_job()
                raise VideoRefused(f"the sidecar did not open the frame pipe in "
                                   f"{self.open_timeout_s:g} s (is {CONTAINER} up and idle? "
                                   "media_rec.py status)")  # fmt: skip
            time.sleep(0.05)
        os.set_blocking(fd, True)
        if self.pipe_bytes:
            try:
                self.pipe_size = fcntl.fcntl(fd, fcntl.F_SETPIPE_SZ, self.pipe_bytes)
            except OSError:
                self.pipe_size = None
        self._fd = fd
        self.status, self.started_ns = "feeding", self.ns()
        self._thread = threading.Thread(target=self._feed, name="video-feed", daemon=True)
        self._thread.start()

    def _abandon_job(self) -> None:
        """A start that timed out: take the job back, or, if the sidecar took it, give its ffmpeg
        end-of-file (open and close our end) so the job ends instead of waiting for us."""
        try:
            (self.ctl / JOB).unlink()
            return
        except FileNotFoundError:
            pass  # taken: end the sidecar's wait below
        with contextlib.suppress(OSError):
            os.close(os.open(self.fifo, os.O_WRONLY | os.O_NONBLOCK))

    # -- the PNG loop's side --------------------------------------------------------------------
    def offer(self, frame_id: int, t_mono_ns: int, img: Any,
              meta: dict[str, Any] | None = None) -> bool:  # fmt: skip
        """Queue one kept frame for the video (never blocks). False when it will not be in it.
        ``meta``: the PNG record's other fields (EXTRA_FIELDS) for the index row."""
        row: dict[str, Any] = {"frame_id": int(frame_id), "t_mono_ns": int(t_mono_ns),
                               "video_index": -1, "status": "queued",
                               "write_start_ns": "", "write_end_ns": "",
                               **{k: (meta or {}).get(k, "") for k in EXTRA_FIELDS}}  # fmt: skip
        self.rows.append(row)
        self.check()
        if self.status != "feeding":
            row["status"] = f"not_fed_{self.status}"
            return False
        try:
            self._q.put_nowait((row, img))
        except queue.Full:
            row["status"] = "dropped_queue_full"
            return False
        self.max_queue = max(self.max_queue, self._q.qsize())
        return True

    def check(self) -> str | None:
        """The failure, once the video side has failed (a stalled write is found here)."""
        since = self._writing_since
        if self.status == "feeding" and since is not None and self.clock() - since > self.stall_s:
            self._fail(f"stalled: a frame write blocked for more than {self.stall_s:g} s (the "
                       "encoder is not reading)")  # fmt: skip
        if self.status == "feeding" and self._thread is not None and not self._thread.is_alive():
            self._fail("the feed thread ended")
        return self.reason if self.status == "failed" else None

    def _fail(self, why: str) -> None:
        if self.status == "feeding":
            self.status, self.reason, self.failed_at = "failed", why, self.ns()

    def bytes(self) -> int:
        """The bitstream's size on disk so far (re-read at most every SIZE_EVERY_S)."""
        now = self.clock()
        if now - self._size_at >= SIZE_EVERY_S:
            self._size_at = now
            with contextlib.suppress(FileNotFoundError):
                self._size = self.part.stat().st_size
        return self._size

    # -- the feed thread ------------------------------------------------------------------------
    def _feed(self) -> None:
        t_cpu = time.thread_time()
        try:
            while True:
                item = self._q.get()
                if item is None or self.status != "feeding":
                    break
                row, img = item
                buf = memoryview(force_alpha(img)).cast("B")
                row["write_start_ns"] = self.ns()
                self._writing_since = self.clock()
                try:
                    assert self._fd is not None
                    while buf:
                        buf = buf[os.write(self._fd, buf) :]
                except BrokenPipeError:
                    self._fail("the encoder closed its pipe (EPIPE)")
                    row["status"] = "write_failed"
                    break
                except OSError as exc:
                    self._fail(f"the frame pipe: {exc}")
                    row["status"] = "write_failed"
                    break
                finally:
                    self._writing_since = None
                row["write_end_ns"] = self.ns()
                self.write_ms.append((row["write_end_ns"] - row["write_start_ns"]) / 1e6)
                # written whole: the encoder may have it, so it keeps its place in the stream
                row["video_index"], row["status"] = self.fed, "fed"
                self.fed += 1
                if self.status != "feeding":  # failed (a stall) while this write blocked
                    break
        except Exception as exc:  # noqa: BLE001 -- reported, never raised into the PNG loop
            self._fail(f"the feed thread: {type(exc).__name__}: {exc}")
        finally:
            self.feed_cpu_s += time.thread_time() - t_cpu

    # -- the end --------------------------------------------------------------------------------
    def finish(self, session: Path) -> dict[str, Any]:
        """End the feed (end-of-file to the encoder), wait for the sidecar, move its stream and log
        into ``session``, write video.idx.csv; -> the manifest's ``video`` block."""
        stuck = False
        if self._thread is not None:
            with contextlib.suppress(queue.Full):
                self._q.put(None, timeout=self.stall_s if self.status == "feeding" else 1.0)
            self._thread.join(timeout=self.stall_s + 5)
            stuck = self._thread.is_alive()
            if stuck:
                self._fail("the feed thread did not end (a blocked write)")
        if self._fd is not None and not stuck:
            os.close(self._fd)  # never while the feeder may still write to it
            self._fd = None
        done: dict[str, str] = {}
        if self.started_ns is not None:
            deadline = self.clock() + (self.done_timeout_s if not stuck else 1.0)
            while not self.done.exists() and self.clock() < deadline:
                time.sleep(0.2)
            if self.done.exists():
                done = parse_done(self.done.read_text())
                self.done.unlink()
            elif self.status in ("feeding", "failed"):
                self._fail(f"no done file from the sidecar in {self.done_timeout_s:g} s")
        if self.status == "feeding":
            if done.get("RC") == "0":
                self.status = "ok"
            else:
                self.status, self.reason = "failed", f"the encoder ended with rc {done.get('RC')}"
        files = {}
        for src, name in ((self.part, "video.hevc"), (self.log, "video.ffmpeg.log")):
            if src.exists():
                src.rename(session / name)  # the same filesystem: a rename, no copy
                files[name] = (session / name).stat().st_size
        for row in self.rows:
            if row["status"] == "queued":
                row["status"] = "not_fed_" + self.status
        self._write_index(session / "video.idx.csv")
        self._release()
        return self.summary(done, files)

    def _write_index(self, path: Path) -> None:
        with path.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow((*INDEX_FIELDS, *EXTRA_FIELDS))
            for row in self.rows:
                w.writerow([row[k] for k in (*INDEX_FIELDS, *EXTRA_FIELDS)])

    def _release(self) -> None:
        if self._made_fifo and self.status != "feeding" and self._fd is None:
            self._made_fifo = False
            with contextlib.suppress(OSError):
                self.fifo.unlink()
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

    def summary(self, done: dict[str, str] | None = None,
                files: dict[str, int] | None = None) -> dict[str, Any]:  # fmt: skip
        by: dict[str, list[int]] = collections.defaultdict(list)
        for row in self.rows:
            by[row["status"]].append(row["frame_id"])
        wm = sorted(self.write_ms)
        return {
            "arm": ARM, "status": self.status, "reason": self.reason,
            "failed_at_ns": self.failed_at, "file": "video.hevc", "index": "video.idx.csv",
            "log": "video.ffmpeg.log", "files": files or {},
            "codec": "hevc", "encoder": "hevc_vaapi rext (Main 4:4:4 10) CQP 20 all-intra",
            "surface": "xv30", "color": "bt709 pc", "alpha_forced": True,
            "offered": len(self.rows), "fed": self.fed,
            "by_status": {k: len(v) for k, v in sorted(by.items())},
            "not_fed_ids": {k: v[:DROPPED_LISTED] for k, v in sorted(by.items()) if k != "fed"},
            "feed_cpu_s": round(self.feed_cpu_s, 3),
            "write_ms": {"p50": round(statistics.median(wm), 2) if wm else None,
                         "p95": round(wm[min(len(wm) - 1, int(0.95 * len(wm)))], 2) if wm else None,
                         "max": round(wm[-1], 2) if wm else None},
            "max_queue": self.max_queue, "pipe_size": self.pipe_size,
            "sidecar": {"container": CONTAINER, "image": self.image, "done": done or None},
        }  # fmt: skip


# --- prep / status --------------------------------------------------------------------------------


def cmd_prep(a: argparse.Namespace) -> int:
    """Create CTL and the local root's .media-rec, ours, 0700 (the sidecar's binds never create a
    missing source: a start without them is refused)."""
    if os.getuid() != UID:
        print(f"refused: this user is {os.getuid()}, the sidecar runs as {UID}", file=sys.stderr)
        return 2
    root = a.root
    root.mkdir(parents=True, exist_ok=True)
    for d in (a.ctl, rec_dir(root)):
        if d.exists() and (d.is_symlink() or not d.is_dir()):
            print(f"refused: {d} exists and is not a directory", file=sys.stderr)
            return 2
        d.mkdir(mode=0o700, exist_ok=True)
        d.chmod(0o700)
        why = dir_problem(d)
        if why:
            print(f"refused: {why}", file=sys.stderr)
            return 2
        print(json.dumps({"ready": str(d)}))
    return 0


def cmd_status(a: argparse.Namespace) -> int:
    """Read-only: the sidecar, the control directory and the bitstream directory's leftovers."""
    rec = rec_dir(a.root)
    out: dict[str, Any] = {"container": CONTAINER, "state": container_state()}
    for name, d in (("ctl", a.ctl), ("rec", rec)):
        out[name] = {"path": str(d), "problem": dir_problem(d),
                     "entries": sorted(os.listdir(d)) if d.is_dir() else None}  # fmt: skip
    print(json.dumps(out, indent=1))
    return 0


# --- check (offline) ------------------------------------------------------------------------------


def read_index(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k in ("frame_id", "t_mono_ns", "video_index"):
            r[k] = int(r[k])
        for k in ("write_start_ns", "write_end_ns"):
            r[k] = int(r[k]) if r[k] else None
    return rows


def video_frames(path: Path, plane_fmt: str = "yuv444p10le") -> Iterator[tuple[Any, bool | None]]:
    """The stream's frames in order, decoded by the host's pinned PyAV (software, one thread), each
    with D1: did its access unit, decoded ALONE by a fresh decoder, give the same planes?"""
    import av
    import gpu_rec_bench as gb

    pending: collections.deque[str | None] = collections.deque()
    ctx = av.CodecContext.create("hevc", "r")
    ctx.thread_count = 1

    def md5(f: Any) -> str:
        g = f if f.format.name == plane_fmt else f.reformat(format=plane_fmt)
        return gb.md5_hex(gb.planar_bytes(gb.frame_planes(g)))

    with av.open(str(path), format="hevc") as cont:
        for pkt in cont.demux(cont.streams.video[0]):
            if not pkt.size:
                continue
            data = bytes(pkt)
            alone: str | None = None
            c = av.CodecContext.create("hevc", "r")
            try:
                got = list(c.decode(av.Packet(data))) + list(c.decode(None))
                alone = md5(got[0]) if len(got) == 1 else None
            except av.error.FFmpegError:
                alone = None
            pending.append(alone)
            try:
                frames = list(ctx.decode(av.Packet(data)))
            except av.error.FFmpegError:
                frames = []
                pending.pop()
                yield None, None  # an undecodable access unit
            for f in frames:
                want = pending.popleft() if pending else None
                yield f, (want is not None and md5(f) == want)
    for f in ctx.decode(None):
        want = pending.popleft() if pending else None
        yield f, (want is not None and md5(f) == want)


def latency(pilot: Path | None, baseline: Path | None, t0: int, t1: int,
            writes: Sequence[tuple[int, int]]) -> dict[str, Any]:  # fmt: skip
    """The detect server's calls (detect_speed's measure) during the recording against a pilot
    without one; reported beside: the same pilot outside the recording, and, inside it, the calls
    near a frame's encode against the rest."""
    import detect_speed as ds

    out: dict[str, Any] = {}
    if pilot is not None:
        rows = ds.read_jsonl(pilot / "detections.jsonl")
        inside = window_rows(rows, t0, t1)
        outside = [r for r in rows if r.get("t_ns") is not None
                   and not t0 <= int(r["t_ns"]) <= t1]  # fmt: skip
        near, far = near_encode(inside, sorted(writes))
        out.update({"pilot": pilot.name, "recording": ds.detections(inside),
                    "pilot_outside": ds.detections(outside), "near_encode": ds.detections(near),
                    "far_from_encode": ds.detections(far)})  # fmt: skip
    if baseline is not None:
        out["baseline_session"] = baseline.name
        out["baseline"] = ds.detections(ds.read_jsonl(baseline / "detections.jsonl"))
    return out


def cmd_check(a: argparse.Namespace) -> int:
    import gpu_rec_bench as gb
    import recorder_boxes as rb

    session: Path = a.session
    manifest = json.loads((session / "manifest.json").read_text())
    video = manifest.get("video")
    if not video:
        raise SystemExit(f"{session}: no video side in its manifest (not a stage-2 session)")
    if (manifest.get("format") or "png") != "png":
        raise SystemExit(f"{session}: format {manifest.get('format')}: check grades a video "
                         "against its PNG twin, and a video-only session has none "
                         "(dataset_check.py verifies its stream)")  # fmt: skip
    rows = read_index(session / "video.idx.csv")
    by_fid = {r["frame_id"]: r for r in rows}
    det = None
    if not a.no_detector:
        import unit_detector as ud

        det = ud.for_map(a.map, threads=a.det_threads)
    from gpu_live_parity import rows as det_rows

    per, jper = [], []
    pairs, jpairs = [], []
    png_rows, vid_rows = [], []
    k = {"kept": int(manifest["frames"]), "index_rows": len(rows),
         "fed": sum(r["status"] == "fed" for r in rows), "decoded": 0, "matched": 0,
         "undecodable": 0, "missing_in_stream": 0, "png_without_row": 0, "d1_frames": 0,
         "d1_alone_identical": 0, "t_mismatch": 0, "shard_cuts": []}  # fmt: skip
    end = (None, None)
    vui = {"frames": 0, "ok": 0, "seen": []}
    stream = session / "video.hevc"
    vframes = video_frames(stream) if stream.exists() else iter(())
    t_start = time.time()
    try:
        for meta, data in rb.iter_session(session, manifest, k["shard_cuts"]):
            fid = int(meta["frame_id"])
            row = by_fid.get(fid)
            if row is None:
                k["png_without_row"] += 1
                continue
            if row["status"] != "fed":
                continue
            got = next(vframes, end)
            if got is end:  # the stream ended before this fed frame
                k["missing_in_stream"] += 1
                continue
            frame, alone = got
            if frame is None:
                k["undecodable"] += 1
                continue
            k["decoded"] += 1
            k["d1_frames"] += 1
            k["d1_alone_identical"] += bool(alone)
            seen = gb.vui_of(frame)
            vui["frames"] += 1
            vui["ok"] += seen == {"range": "pc", "matrix": "bt709"}
            if seen not in vui["seen"]:
                vui["seen"].append(seen)
            if int(row["t_mono_ns"]) != int(meta["t_mono_ns"]):
                k["t_mismatch"] += 1
            ref = rb.decode_bgr(data)
            dec = gb.to_bgr(frame, gb.COLOR)
            if dec.shape != ref.shape:
                k["undecodable"] += 1
                continue
            k["matched"] += 1
            m = gb.frame_metrics(ref, dec)
            m["gen2"] = gb.psnr(ref, gb.decode_png_bgr(gb.jpeg95(dec)))
            per.append(m)
            jdec = gb.decode_png_bgr(gb.jpeg95(ref))
            jper.append(gb.frame_metrics(ref, jdec))
            if det is not None and (k["matched"] - 1) % a.det_every == 0:
                bp = det.detect(ref)
                png_rows.append(rb.box_row(meta["t_mono_ns"], fid, det.last_ms, bp))
                bv = det.detect(dec)
                vid_rows.append(rb.box_row(meta["t_mono_ns"], fid, det.last_ms, bv))
                pairs.append((det_rows(bp), det_rows(bv)))
                jpairs.append((det_rows(bp), det_rows(det.detect(jdec))))
            if k["matched"] % 100 == 0:
                print(json.dumps({"checked": k["matched"], "s": round(time.time() - t_start)}),
                      file=sys.stderr, flush=True)  # fmt: skip
        k["decoded_extra"] = sum(1 for f, _ in vframes if f is not None)  # frames past the index
        k["decoded"] += k["decoded_extra"]
    finally:
        if det is not None:
            det.close()
    vbytes = (session / "video.hevc").stat().st_size if (session / "video.hevc").exists() else 0
    arm = {"quality": gb.summarise(per), "parity": gb.parity_stats(pairs) if pairs else None,
           "bytes_per_frame": round(vbytes / max(1, k["decoded"]), 1),
           "d1": {"frames": k["d1_frames"],
                  "alone_identical": k["d1_alone_identical"]}}  # fmt: skip
    jpeg = {"quality": gb.summarise(jper), "parity": gb.parity_stats(jpairs) if jpairs else None}
    png = {"bytes_per_frame": round(int(manifest["bytes"]) / max(1, k["kept"]), 1)}
    qb = {key: v for key, v in gb.bars_for(arm, jpeg, png, None, "vpp").items()
          if key not in STAGE1_ONLY}  # fmt: skip
    seconds = float(manifest.get("cpu_wall_s") or manifest["seconds"])  # cores were averaged so
    cores = manifest.get("cpu_cores") or {}
    side = cores.get(SERVICE)
    feed = video.get("feed_cpu_s")
    fed = int(video.get("fed") or 0)
    video_s = None if side is None or feed is None else feed + side * seconds
    proc = cores.get("recorder_process")
    cpu = {"seconds": seconds, "kept": k["kept"], "fed": fed,
           "recorder_ms_per_frame": ms_per_frame(None if proc is None else proc * seconds,
                                                 k["kept"]),
           "recorder_without_feed_ms_per_frame": ms_per_frame(
               None if proc is None or feed is None else proc * seconds - feed, k["kept"]),
           "png_writer_ms_per_frame": ms_per_frame(manifest.get("png_writer_cpu_s"), k["kept"]),
           "feed_ms_per_frame": ms_per_frame(feed, fed),
           "sidecar_ms_per_frame": ms_per_frame(None if side is None else side * seconds, fed),
           "video_ms_per_frame": ms_per_frame(video_s, fed),
           "backend_cores": cores.get("backend")}  # fmt: skip
    writes = [(r["write_start_ns"], r["write_end_ns"]) for r in rows
              if r["write_start_ns"] is not None and r["write_end_ns"] is not None]  # fmt: skip
    res: dict[str, Any] = {
        "session": manifest["session_id"], "map": a.map, "arm": video.get("arm"),
        "video_status": video.get("status"), "video_reason": video.get("reason"),
        "detector": None if det is None else getattr(det.model, "name", str(det.model)),
        "completeness": k, "vui": vui, "cpu": cpu,
        "sizes": {"png_bytes_per_frame": png["bytes_per_frame"],
                  "video_bytes_per_frame": arm["bytes_per_frame"],
                  "ratio": round(arm["bytes_per_frame"] / png["bytes_per_frame"], 4)
                  if png["bytes_per_frame"] else None,
                  "png_gb_per_hour_1fps": gb.gb_per_hour(png["bytes_per_frame"], 1),
                  "video_gb_per_hour_1fps": gb.gb_per_hour(arm["bytes_per_frame"], 1)},
        "video": arm, "jpeg95": jpeg,
        "latency": latency(a.pilot, a.baseline, int(manifest["t0_mono_ns"]),
                           int(manifest["t1_mono_ns"]), writes),
        "recorder_boxes": rb.compare_rows(png_rows, vid_rows, 0.5) if png_rows else None,
    }  # fmt: skip
    s2 = stage2_bars(res)
    res["bars"] = {"quality": qb, "stage2": s2}
    res["verdict"] = stage2_verdict(qb, s2)
    res["checked_seconds"] = round(time.time() - t_start, 1)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=1) + "\n")
    if png_rows:  # boxes only (no pixels): recorder_boxes' row format, for detector_vs_packets
        for name, rws in (("png", png_rows), ("video", vid_rows)):
            p = a.out.with_name(a.out.stem + f".{name}-boxes.jsonl")
            p.write_text("".join(json.dumps(r) + "\n" for r in rws))
    print(json.dumps({"verdict": res["verdict"], "completeness": k, "sizes": res["sizes"],
                      "cpu": cpu}, indent=1))  # fmt: skip
    for group, bars in res["bars"].items():
        for key, r in bars.items():
            print(f"{group:8s} {key:3s} {r['result']:4s} {r['value']} ({r['need']})")
    return 0 if res["verdict"]["pass"] else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("prep", "status"):
        p = sub.add_parser(name)
        p.add_argument("--root", type=Path, default=local_root())
        p.add_argument("--ctl", type=Path, default=CTL)
    c = sub.add_parser("check")
    c.add_argument("session", type=Path)
    c.add_argument("--map", required=True, help="the map, for unit_detector.for_map")
    c.add_argument("--out", type=Path, required=True)
    c.add_argument("--pilot", type=Path, default=None, help="the pilot session beside it")
    c.add_argument("--baseline", type=Path, default=None, help="a pilot without a recording")
    c.add_argument("--det-threads", type=int, default=4)
    c.add_argument("--det-every", type=int, default=1)
    c.add_argument("--no-detector", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "prep":
        return cmd_prep(a)
    if a.cmd == "status":
        return cmd_status(a)
    if a.det_every < 1:
        raise SystemExit("--det-every: 1 or more")
    return cmd_check(a)


if __name__ == "__main__":
    raise SystemExit(main())
