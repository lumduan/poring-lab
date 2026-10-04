"""Record the H.264 bitstream the S2 client decodes (Post-S2 round C1, 2026-10-04): an experiment
against PNG datasets (docs/benchmarks/h264-vs-png.md). The default stays PNG until Batt decides.

Driven by a CONTROL FILE in the recording dir (a host bind mount, compose.dev.yaml: /s2-rec), polled
once a second, so a recording needs no restream:

    start <id> <idr_every_s> <max_s> <max_mb>      begin (idr_every_s 0 = never ask for one)
    stop                                           end now

* Dead-man: the writer of the control file (record_session.py --format h264) re-touches it every
  few seconds; a control file older than STALE_S, the time cap or the size cap ends the recording.
  The stream ending ends it too. The id must match ID_RE (it becomes a file name).
* On start: LiRequestIdrFrame(), and nothing is written before the first IDR access unit (NAL type
  5, with SPS 7 + PPS 8 in it), so the file decodes on its own from byte 0.
* Files, dot-named while open: .<id>.h264 (the Annex-B access units EXACTLY as fed to the decoder),
  .<id>.idx.csv (one row per access unit), .<id>.hash.csv (a 64-bit checksum of every decoded BGRA
  frame, for the determinism check, h264check.py: crc32 + adler32 -- measured 4.7 ms per 1440x900
  frame vs blake2b-128's 20.8 ms, i.e. 0.14 vs 0.62 cores at 30 fps; equality of two decodes is
  not an adversarial question). At the end <id>.done.json is written and the three are
  renamed to their plain names; done.json goes last, so a reader trusts only a finished set.
* The decode thread only enqueues (bounded). A writer thread does the I/O; on a full queue the AU is
  dropped, a gap row is written and the writer skips to the next IDR (asked for at once). A hash
  worker has its own bounded queue; a dropped hash makes the set "incomplete", never a determinism
  failure.
* An IDR timer thread asks for an IDR every idr_every_s seconds while recording (the size cost of
  random access is what the experiment measures). LiRequestIdrFrame only means "one comes soon".
"""

from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}-[a-z0-9][a-z0-9-]{0,47}$")
CONTROL = "control"
STALE_S = 15.0
POLL_S = 1.0
AU_QUEUE = 256  # access units (~80 KB each at 20 Mb/s 30 fps; IDRs larger)
HASH_QUEUE = 16  # decoded frames (5 MB each at 1440x900 BGRA: <= 83 MB of the 1600m)
MAX_S_CAP = 3600
MAX_MB_CAP = 8192
IDX_HEADER = ("au,frame_id,frame_number,frame_type,idr,pts_ms,offset,length,receive_ms,"
              "t_publish_ns\n")  # fmt: skip
NAL_IDR, NAL_SPS, NAL_PPS = 5, 7, 8


def nal_types(au: bytes) -> list[int]:
    """The NAL unit types in an Annex-B access unit (start codes 00 00 01 / 00 00 00 01)."""
    out, i, n = [], 0, len(au)
    while True:
        j = au.find(b"\x00\x00\x01", i)
        if j < 0 or j + 3 >= n:
            return out
        out.append(au[j + 3] & 0x1F)
        i = j + 3


def is_idr(au: bytes) -> bool:
    return NAL_IDR in nal_types(au)


def frame_digest(contiguous: Any) -> str:
    """crc32 + adler32 of a decoded frame's bytes, 16 hex digits (h264check.py hashes the re-decode
    the same way)."""
    return f"{zlib.crc32(contiguous):08x}{zlib.adler32(contiguous):08x}"


def parse_control(text: str) -> dict[str, Any] | None:
    """'start <id> <idr_s> <max_s> <max_mb>' / 'stop' -> a command; anything else -> None."""
    parts = text.split()
    if parts == ["stop"]:
        return {"cmd": "stop"}
    if len(parts) != 5 or parts[0] != "start" or not ID_RE.match(parts[1]):
        return None
    try:
        idr_s, max_s, max_mb = float(parts[2]), float(parts[3]), float(parts[4])
    except ValueError:
        return None
    if not (0 <= idr_s <= 60 and 0 < max_s <= MAX_S_CAP and 0 < max_mb <= MAX_MB_CAP):
        return None
    return {"cmd": "start", "id": parts[1], "idr_s": idr_s, "max_s": max_s, "max_mb": max_mb}


@dataclass
class Unit:
    au: bytes
    frame_ids: list[int]  # the bus frame_ids decoded from it (empty: none, or a decode error)
    frame_number: int
    frame_type: int
    pts_ms: int
    receive_ms: int
    t_publish_ns: int


@dataclass
class Counts:
    aus: int = 0
    bytes: int = 0
    idrs: int = 0
    frames: int = 0
    skipped_before_idr: int = 0
    queue_overflows: int = 0
    gaps: int = 0
    decode_errors: int = 0
    hashes: int = 0
    hash_dropped: int = 0
    idr_requests: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class Recording:
    """One recording: the files, the writer thread and the hash worker."""

    def __init__(self, root: Path, spec: dict[str, Any], versions: dict[str, str],
                 request_idr: Callable[[], None], log: Callable[[str], None]) -> None:  # fmt: skip
        self.root, self.spec, self.versions, self.log = root, spec, versions, log
        self.request_idr = request_idr
        self.id = str(spec["id"])
        self.counts = Counts()
        self.t_start = time.monotonic()
        self.t_start_wall = time.time()
        self.reason = ""
        self.waiting_idr = True
        self.offset = 0
        self.au_q: queue.Queue[Unit | None] = queue.Queue(AU_QUEUE)
        self.hash_q: queue.Queue[tuple[int, Any] | None] = queue.Queue(HASH_QUEUE)
        self.paths = {k: root / f".{self.id}.{k}" for k in ("h264", "idx.csv", "hash.csv")}
        if any((root / f"{self.id}.{k}").exists() for k in ("h264", "done.json")):
            raise FileExistsError(f"recording {self.id} already exists")
        self.h264 = self.paths["h264"].open("wb")
        self.idx = self.paths["idx.csv"].open("w")
        self.idx.write(IDX_HEADER)
        self.hashes = self.paths["hash.csv"].open("w")
        self.hashes.write("frame_id,crc32_adler32\n")
        self.writer = threading.Thread(target=self._write_loop, name="h264rec-writer", daemon=True)
        self.hasher = threading.Thread(target=self._hash_loop, name="h264rec-hash", daemon=True)
        self.writer.start()
        self.hasher.start()
        self._idr_stop = threading.Event()
        if float(spec["idr_s"]) > 0:
            threading.Thread(target=self._idr_loop, name="h264rec-idr", daemon=True).start()
        self._ask_idr()

    def _ask_idr(self) -> None:
        self.counts.idr_requests += 1
        try:
            self.request_idr()
        except Exception as exc:  # noqa: BLE001 -- a request is advisory
            self.log(f"h264rec: IDR request failed: {exc}")

    def _idr_loop(self) -> None:
        while not self._idr_stop.wait(float(self.spec["idr_s"])):
            self._ask_idr()

    # --- the decode thread ------------------------------------------------------------------------

    def offer(self, unit: Unit, frames: list[Any]) -> None:
        """Never blocks: a full queue drops the unit (the writer then waits for the next IDR)."""
        try:
            self.au_q.put_nowait(unit)
        except queue.Full:
            self.counts.queue_overflows += 1
            self.waiting_idr = True  # read by the writer: everything up to the next IDR is a gap
            self._ask_idr()
            return
        for fid, frame in zip(unit.frame_ids, frames, strict=False):
            try:
                self.hash_q.put_nowait((fid, frame))
            except queue.Full:
                self.counts.hash_dropped += 1

    # --- the writer -------------------------------------------------------------------------------

    def _write_loop(self) -> None:
        while True:
            unit = self.au_q.get()
            if unit is None:
                return
            idr = is_idr(unit.au)
            if self.waiting_idr and not idr:
                if self.counts.aus:  # a gap inside the recording (after an overflow)
                    self.counts.gaps += 1
                    self.idx.write(f"-1,-1,{unit.frame_number},{unit.frame_type},0,"
                                   f"{unit.pts_ms},{self.offset},0,{unit.receive_ms},"
                                   f"{unit.t_publish_ns}\n")  # fmt: skip
                else:
                    self.counts.skipped_before_idr += 1
                continue
            if idr:
                types = nal_types(unit.au)
                if self.counts.idrs == 0 and not (NAL_SPS in types and NAL_PPS in types):
                    self.counts.extra["first_idr_without_sps_pps"] = True
                self.counts.idrs += 1
                self.waiting_idr = False
            self.h264.write(unit.au)
            fid = unit.frame_ids[0] if unit.frame_ids else -1
            if fid < 0:
                self.counts.decode_errors += 1
            self.idx.write(f"{self.counts.aus},{fid},{unit.frame_number},{unit.frame_type},"
                           f"{int(idr)},{unit.pts_ms},{self.offset},{len(unit.au)},"
                           f"{unit.receive_ms},{unit.t_publish_ns}\n")  # fmt: skip
            self.offset += len(unit.au)
            self.counts.aus += 1
            self.counts.bytes += len(unit.au)
            self.counts.frames += len(unit.frame_ids)

    def _hash_loop(self) -> None:
        import numpy as np  # the frames are numpy arrays already (PyAV)

        while True:
            item = self.hash_q.get()
            if item is None:
                return
            fid, frame = item
            digest = frame_digest(np.ascontiguousarray(frame))
            self.hashes.write(f"{fid},{digest}\n")
            self.counts.hashes += 1

    # --- the end ----------------------------------------------------------------------------------

    def over_cap(self) -> str:
        if time.monotonic() - self.t_start > float(self.spec["max_s"]):
            return "time cap"
        if self.counts.bytes > float(self.spec["max_mb"]) * 1e6:
            return "size cap"
        return ""

    def finish(self, reason: str) -> dict[str, Any]:
        self.reason = reason
        self._idr_stop.set()
        self.au_q.put(None)
        self.writer.join(timeout=30)
        self.hash_q.put(None)
        self.hasher.join(timeout=30)
        for f in (self.h264, self.idx, self.hashes):
            f.flush()
            os.fsync(f.fileno())
            f.close()
        for kind, path in self.paths.items():
            path.rename(self.root / f"{self.id}.{kind}")
        c = self.counts
        summary = {
            "id": self.id, "reason": reason, "spec": self.spec, "versions": self.versions,
            "t_start_wall": self.t_start_wall, "seconds": round(time.monotonic() - self.t_start, 2),
            "aus": c.aus, "bytes": c.bytes, "idrs": c.idrs, "frames": c.frames,
            "skipped_before_idr": c.skipped_before_idr, "queue_overflows": c.queue_overflows,
            "gaps": c.gaps, "decode_errors": c.decode_errors, "hashes": c.hashes,
            "hash_dropped": c.hash_dropped, "idr_requests": c.idr_requests,
            # every decoded frame was offered for hashing (those before the first IDR too)
            "hashes_complete": c.hash_dropped == 0 and c.hashes >= c.frames,
            **c.extra,
        }  # fmt: skip
        done = self.root / f"{self.id}.done.json"
        tmp = self.root / f".{self.id}.done.json"
        tmp.write_text(json.dumps(summary, indent=1) + "\n")
        tmp.rename(done)
        self.log(f"h264rec: {self.id} done ({reason}): {c.aus} AUs, {c.bytes / 1e6:.1f} MB, "
                 f"{c.idrs} IDRs, {c.hashes}/{c.frames} hashes")  # fmt: skip
        return summary


class Recorder:
    """The control-file poller. One recording at a time; the stream's decode thread calls
    ``offer`` (cheap when idle)."""

    def __init__(self, root: Path, request_idr: Callable[[], None], log: Callable[[str], None],
                 versions: dict[str, str] | None = None) -> None:  # fmt: skip
        if not root.is_dir() or not os.access(root, os.W_OK):
            raise OSError(f"{root} is missing or not writable (compose.dev.yaml S2_REC_DIR)")
        self.root, self.request_idr, self.log = root, request_idr, log
        self.versions = versions or {}
        self.active: Recording | None = None
        self._started: set[str] = set()  # ids already recorded: a new recording needs a new id
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._poll_loop, name="h264rec-control",
                                        daemon=True)  # fmt: skip
        self._thread.start()

    def offer(self, unit: Unit, frames: list[Any]) -> None:
        rec = self.active
        if rec is not None:
            rec.offer(unit, frames)

    def poll(self, now: float | None = None) -> None:
        """One look at the control file (tests call it directly)."""
        path = self.root / CONTROL
        now = time.time() if now is None else now
        try:
            text, mtime = path.read_text(), path.stat().st_mtime
        except OSError:
            text, mtime = "", 0.0
        cmd = parse_control(text) if text else None
        with self._lock:
            rec = self.active
            if rec is not None:
                reason = rec.over_cap()
                if not reason and now - mtime > STALE_S:
                    reason = "control file stale (dead-man)"
                if not reason and (cmd is None or cmd["cmd"] == "stop" or cmd.get("id") != rec.id):
                    reason = "stop"
                if reason:
                    self.active = None
                    rec.finish(reason)
                return
            if cmd is None or cmd["cmd"] != "start" or now - mtime > STALE_S:
                return
            if cmd["id"] in self._started:
                return
            self._started.add(cmd["id"])
            try:
                self.active = Recording(self.root, cmd, self.versions, self.request_idr, self.log)
                self.log(f"h264rec: {cmd['id']} started (IDR every {cmd['idr_s']} s, "
                         f"cap {cmd['max_s']} s / {cmd['max_mb']} MB)")  # fmt: skip
            except (OSError, FileExistsError) as exc:
                self.log(f"h264rec: REFUSED {cmd['id']}: {exc}")

    def _poll_loop(self) -> None:
        while not self._stop.wait(POLL_S):
            try:
                self.poll()
            except Exception as exc:  # noqa: BLE001 -- a recorder never takes the stream down
                self.log(f"h264rec: poll failed: {exc}")

    def close(self, reason: str = "stream ended") -> None:
        self._stop.set()
        self._thread.join(timeout=3)
        with self._lock:
            rec, self.active = self.active, None
        if rec is not None:
            rec.finish(reason)
