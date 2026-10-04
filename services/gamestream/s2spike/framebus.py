"""The S2 frame bus (docs/s2-plan.md section 2): decode ONCE, then every consumer reads the same
frames from shared memory -- the bot as numpy, the console as JPEG -- with one ``frame_id`` and one
``t_mono_ns`` for both.

One writer (the S2 stream client) and any number of readers share a file in a tmpfs volume
(``/framebus/ring``), mmapped. N slots; a seqlock per slot:

    writer:  slot = (latest + 1) % N;  seq += 1 (odd);  header + pixels;  seq += 1 (even);
             latest = slot.  It never waits for a reader.
    reader:  read latest;  seq must be even;  copy header + pixels;  re-read seq -- unchanged means
             the copy is whole. Changed = an OVERRUN (the writer lapped this reader): retry once,
             then count it. DROPS = the frame_ids a reader skipped (latest-wins: a slow consumer
             skips frames and never delays the writer or another consumer).

Memory ordering: the writer's stores are separate memcpy calls into the mmap, and x86-64 keeps
stores in order (TSO), as it keeps loads in order for the reader. This host is x86-64; an ARM
port would need explicit fences around ``seq``.

STDLIB + NUMPY ONLY, and no other poring_env import: services/gamestream/s2spike/framebus.py is a
byte-identical copy (the gamestream image has no pydantic), pinned by a drift test.
"""

import mmap
import os
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray

MAGIC = b"PLFB"
VERSION = 1
FMT_BGRA = 1
PAGE = 4096
# magic, version, slots, slot_header, slot_bytes, latest, writer_pid, heartbeat_ns, frames_written,
# decode_p50_us, decode_p95_us (the writer's own decode timing, for /health)
_GLOBAL = struct.Struct("<4sIIIQqQQQII")
GLOBAL_BYTES = 64
_OFF_LATEST = 24
_OFF_HEARTBEAT = 40
_OFF_WRITTEN = 48
_DECODE = struct.Struct("<II")
_OFF_DECODE = 56
# seq, frame_id, t_mono_ns, t_pts, width, height, stride, fmt
_SLOT = struct.Struct("<QqQqIIII")
SLOT_HEADER_BYTES = 64
_U64 = struct.Struct("<Q")
_I64 = struct.Struct("<q")
assert _GLOBAL.size == GLOBAL_BYTES and _SLOT.size <= SLOT_HEADER_BYTES


class FrameBusError(RuntimeError):
    """The ring is missing, not a frame bus, or a different layout than this reader expects."""


class BusFrame(NamedTuple):
    frame_id: int
    t_mono_ns: int  # the writer's CLOCK_MONOTONIC when decoding completed (shared by the host)
    t_pts: int  # the stream's presentation timestamp (-1 = unknown)
    width: int
    height: int
    bgra: bytes  # tightly packed rows (stride == width * 4)

    def to_numpy(self) -> NDArray[np.uint8]:
        return np.frombuffer(self.bgra, dtype=np.uint8).reshape(self.height, self.width, 4)


def slot_stride(slot_bytes: int) -> int:
    return -(-(SLOT_HEADER_BYTES + slot_bytes) // PAGE) * PAGE


def ring_size(slots: int, slot_bytes: int) -> int:
    return PAGE + slots * slot_stride(slot_bytes)  # the global header has a page to itself


def _mono_ns() -> int:
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


class FrameBusWriter:
    """The only writer. ``create`` replaces any old ring with a fresh file (a new inode, so readers
    of a previous writer notice and re-open)."""

    def __init__(
        self, path: str | Path, *, max_width: int, max_height: int, slots: int = 4
    ) -> None:
        if slots < 2 or max_width <= 0 or max_height <= 0:
            raise ValueError(f"bad ring: {slots=} {max_width=} {max_height=}")
        self.path = Path(path)
        self.slots = slots
        self.slot_bytes = max_width * max_height * 4
        self._stride = slot_stride(self.slot_bytes)
        size = ring_size(slots, self.slot_bytes)
        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o640)
        try:
            os.ftruncate(fd, size)
            # Reserve every page NOW (2026-10-03): a sparse ring on a full tmpfs SIGBUSes the writer
            # at the first page it cannot get -- mid-stream. The tmpfs fills when a reader still
            # maps the previous writer's (unlinked) ring; it frees once every reader re-opens.
            try:
                os.posix_fallocate(fd, 0, size)
            except OSError as exc:
                free = os.statvfs(self.path.parent)
                os.close(fd)
                fd = -1
                tmp.unlink(missing_ok=True)
                raise FrameBusError(
                    f"no room for a {size >> 20} MiB ring ({free.f_bavail * free.f_frsize >> 20} "
                    f"MiB free in {self.path.parent}): an earlier ring is still mapped ({exc})"
                ) from None
            self._mm = mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
        finally:
            if fd >= 0:
                os.close(fd)
        # Everything but the magic first: a reader that opens the file early refuses it.
        _GLOBAL.pack_into(self._mm, 0, b"\0\0\0\0", VERSION, slots, SLOT_HEADER_BYTES,
                          self.slot_bytes, -1, os.getpid(), _mono_ns(), 0, 0, 0)  # fmt: skip
        self._mm[0:4] = MAGIC
        os.replace(tmp, self.path)
        self._latest = -1
        self._written = 0

    def _slot_offset(self, slot: int) -> int:
        return PAGE + slot * self._stride

    def publish(
        self, bgra: NDArray[np.uint8] | bytes, frame_id: int, t_mono_ns: int, t_pts: int = -1
    ) -> None:
        """One decoded frame (HxWx4 BGRA, C-contiguous, or packed bytes with ``shape``)."""
        if isinstance(bgra, bytes):
            raise TypeError("pass an HxWx4 uint8 array (the shape carries width and height)")
        if bgra.ndim != 3 or bgra.shape[2] != 4 or bgra.dtype != np.uint8:
            raise ValueError(f"expected HxWx4 uint8 BGRA, got {bgra.shape} {bgra.dtype}")
        height, width = int(bgra.shape[0]), int(bgra.shape[1])
        nbytes = width * height * 4
        if nbytes > self.slot_bytes:
            raise ValueError(f"{width}x{height} does not fit a {self.slot_bytes}-byte slot")
        pixels = np.ascontiguousarray(bgra)
        slot = (self._latest + 1) % self.slots
        off = self._slot_offset(slot)
        seq = _U64.unpack_from(self._mm, off)[0]
        _U64.pack_into(self._mm, off, seq + 1)  # odd: being written
        _SLOT.pack_into(self._mm, off, seq + 1, frame_id, t_mono_ns, t_pts, width, height,
                        width * 4, FMT_BGRA)  # fmt: skip
        start = off + SLOT_HEADER_BYTES
        self._mm[start : start + nbytes] = memoryview(pixels).cast("B")
        _U64.pack_into(self._mm, off, seq + 2)  # even: complete
        _I64.pack_into(self._mm, _OFF_LATEST, slot)
        self._latest = slot
        self._written += 1
        _U64.pack_into(self._mm, _OFF_WRITTEN, self._written)
        _U64.pack_into(self._mm, _OFF_HEARTBEAT, _mono_ns())

    def set_decode_stats(self, p50_us: int, p95_us: int) -> None:
        """The writer's decode time percentiles (shown in the backend's /health)."""
        cap = 0xFFFFFFFF
        _DECODE.pack_into(self._mm, _OFF_DECODE, min(max(p50_us, 0), cap), min(max(p95_us, 0), cap))

    def heartbeat(self) -> None:
        """Alive without a new frame (a static screen): readers judge staleness by this."""
        _U64.pack_into(self._mm, _OFF_HEARTBEAT, _mono_ns())

    def close(self, *, unlink: bool = False) -> None:
        self._mm.close()
        if unlink:
            self.path.unlink(missing_ok=True)


@dataclass
class ReaderStats:
    frames_read: int = 0
    drops: int = 0  # frame_ids skipped between two frames this reader consumed
    overruns: int = 0  # a frame lost because the writer lapped this reader twice in a row
    retries: int = 0  # a torn copy that the second attempt recovered
    reopens: int = 0  # a new writer (new ring inode)
    last_frame_id: int = -1


class WriterStatus(NamedTuple):
    pid: int
    heartbeat_age_s: float
    frames_written: int
    latest_frame_id: int
    decode_p50_us: int
    decode_p95_us: int


class FrameBusReader:
    """One consumer's view of the ring (read-only mmap). ``name`` labels its counters."""

    def __init__(self, path: str | Path, name: str) -> None:
        self.path = Path(path)
        self.name = name
        self.stats = ReaderStats()
        self._mm: mmap.mmap | None = None
        self._ino = -1
        self._open()

    def _open(self) -> None:
        try:
            fd = os.open(self.path, os.O_RDONLY)
        except OSError as exc:
            raise FrameBusError(f"{self.path}: {exc.strerror}") from None
        try:
            st = os.fstat(fd)
            if st.st_size < GLOBAL_BYTES:
                raise FrameBusError(f"{self.path}: {st.st_size} bytes is not a frame bus")
            mm = mmap.mmap(fd, st.st_size, mmap.MAP_SHARED, mmap.PROT_READ)
        finally:
            os.close(fd)
        magic, version, slots, slot_header, slot_bytes, *_ = _GLOBAL.unpack_from(mm, 0)
        problem = None
        if magic != MAGIC:
            problem = f"magic {magic!r}"
        elif version != VERSION:
            problem = f"version {version} (this reader speaks {VERSION})"
        elif slot_header != SLOT_HEADER_BYTES or slots < 2:
            problem = f"layout {slots=} {slot_header=}"
        elif st.st_size != ring_size(slots, slot_bytes):
            problem = f"size {st.st_size} != {ring_size(slots, slot_bytes)}"
        if problem:
            mm.close()
            raise FrameBusError(f"{self.path}: not a usable frame bus ({problem})")
        if self._mm is not None:
            self._mm.close()
            self.stats.reopens += 1
        self._mm, self._ino = mm, st.st_ino
        self.slots, self.slot_bytes = slots, slot_bytes
        self._stride = slot_stride(slot_bytes)

    def replaced(self) -> bool:
        """A new writer created a new ring (or removed it)."""
        try:
            return os.stat(self.path).st_ino != self._ino
        except OSError:
            return True

    def reopen_if_replaced(self) -> None:
        if self.replaced():
            self._open()

    def writer(self) -> WriterStatus:
        assert self._mm is not None
        _, _, _, _, _, latest, pid, heartbeat, written, p50, p95 = _GLOBAL.unpack_from(self._mm, 0)
        last = -1
        if 0 <= latest < self.slots:
            last = _SLOT.unpack_from(self._mm, PAGE + latest * self._stride)[1]
        return WriterStatus(pid, (_mono_ns() - heartbeat) / 1e9, written, last, p50, p95)

    def latest_stamp(self) -> tuple[int, int] | None:
        """(frame_id, t_mono_ns) of the newest complete frame, from its slot HEADER only (no pixel
        copy, no stats): the stream-age probe of the frame-age guard (2026-10-04). The same
        seqlock check as read(); None when there is no frame yet or two reads were torn."""
        mm = self._mm
        assert mm is not None
        for _ in range(2):
            latest = _I64.unpack_from(mm, _OFF_LATEST)[0]
            if not 0 <= latest < self.slots:
                return None
            off = PAGE + latest * self._stride
            seq, frame_id, t_mono = _SLOT.unpack_from(mm, off)[:3]
            if seq % 2 or _U64.unpack_from(mm, off)[0] != seq:
                continue
            return frame_id, t_mono
        return None

    def read(self, after: int = -1) -> BusFrame | None:
        """The newest complete frame with ``frame_id > after``, or None (nothing newer, or lost to
        two overruns in a row)."""
        mm = self._mm
        assert mm is not None
        for attempt in range(2):
            latest = _I64.unpack_from(mm, _OFF_LATEST)[0]
            if not 0 <= latest < self.slots:
                return None  # no frame yet
            off = PAGE + latest * self._stride
            seq, frame_id, t_mono, t_pts, width, height, stride, fmt = _SLOT.unpack_from(mm, off)
            if seq % 2:  # being rewritten: the writer lapped us (or a torn `latest`)
                if attempt == 0:
                    self.stats.retries += 1
                continue
            if frame_id <= after:
                return None
            nbytes = height * stride
            if fmt != FMT_BGRA or stride != width * 4 or nbytes > self.slot_bytes:
                raise FrameBusError(f"slot {latest}: bad frame header {width}x{height} {stride=}")
            start = off + SLOT_HEADER_BYTES
            pixels = mm[start : start + nbytes]
            if _U64.unpack_from(mm, off)[0] != seq:
                if attempt == 0:
                    self.stats.retries += 1
                continue
            last = self.stats.last_frame_id
            if last >= 0 and frame_id > last + 1:
                self.stats.drops += frame_id - last - 1
            self.stats.frames_read += 1
            self.stats.last_frame_id = frame_id
            return BusFrame(frame_id, t_mono, t_pts, width, height, pixels)
        self.stats.overruns += 1
        return None

    def close(self) -> None:
        if self._mm is not None:
            self._mm.close()
            self._mm = None
