"""The S2 frame bus (docs/s2-plan.md section 2): one writer, latest-wins readers, never a torn
frame, and a slow reader never slows the writer. Readers in the torture test are separate
PROCESSES (the GIL would serialise threads around every copy and hide a tear)."""

import json
import mmap
import os
import struct
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from poring_env.bus_source import BusFrameSource, FrameBusTimeout
from poring_env.framebus import PAGE, FrameBusError, FrameBusReader, FrameBusWriter


def frame(frame_id: int, w: int = 64, h: int = 48) -> np.ndarray:
    """A uniform frame whose value is derived from its id: any mix of two frames is detectable."""
    return np.full((h, w, 4), (frame_id * 7) % 256, np.uint8)


def test_round_trip_keeps_pixels_ids_and_times(tmp_path: Path) -> None:
    ring = tmp_path / "ring"
    w = FrameBusWriter(ring, max_width=64, max_height=48)
    pixels = np.random.default_rng(3).integers(0, 255, (48, 64, 4), dtype=np.uint8)
    w.publish(pixels, frame_id=10, t_mono_ns=123_456, t_pts=900)
    r = FrameBusReader(ring, "test")
    got = r.read()
    assert got is not None
    assert (got.frame_id, got.t_mono_ns, got.t_pts) == (10, 123_456, 900)
    assert (got.width, got.height) == (64, 48)
    assert np.array_equal(got.to_numpy(), pixels)
    assert r.read(after=10) is None  # nothing newer
    status = r.writer()
    assert (status.pid, status.frames_written, status.latest_frame_id) == (os.getpid(), 1, 10)
    w.set_decode_stats(4200, 9100)
    assert r.writer()[-2:] == (4200, 9100)


def test_smaller_frames_fit_a_slot(tmp_path: Path) -> None:
    w = FrameBusWriter(tmp_path / "ring", max_width=64, max_height=48)
    w.publish(frame(1, 32, 20), 1, 1)
    got = FrameBusReader(tmp_path / "ring", "t").read()
    assert got is not None and (got.width, got.height) == (32, 20)
    with pytest.raises(ValueError, match="does not fit"):
        w.publish(frame(2, 65, 48), 2, 2)
    with pytest.raises(ValueError, match="HxWx4"):
        w.publish(np.zeros((48, 64, 3), np.uint8), 3, 3)


def test_latest_wins_and_drops_count_the_skipped_ids(tmp_path: Path) -> None:
    ring = tmp_path / "ring"
    w = FrameBusWriter(ring, max_width=64, max_height=48, slots=4)
    r = FrameBusReader(ring, "slow")
    assert r.read() is None  # no frame yet
    for i in range(1, 6):
        w.publish(frame(i), i, i)
    got = r.read()
    assert got is not None and got.frame_id == 5 and r.stats.drops == 0  # the first read: no gap
    for i in range(6, 10):
        w.publish(frame(i), i, i)
    got = r.read(after=5)
    assert got is not None and got.frame_id == 9
    assert (r.stats.frames_read, r.stats.drops, r.stats.last_frame_id) == (2, 3, 9)
    fast = FrameBusReader(ring, "fast")  # per consumer: another reader has its own counters
    assert fast.read() is not None and fast.stats.drops == 0


def test_a_slot_being_rewritten_is_retried_then_counted(tmp_path: Path) -> None:
    ring = tmp_path / "ring"
    w = FrameBusWriter(ring, max_width=64, max_height=48, slots=2)
    w.publish(frame(1), 1, 1)
    r = FrameBusReader(ring, "t")
    with open(ring, "r+b") as fh, mmap.mmap(fh.fileno(), 0) as mm:
        latest = struct.unpack_from("<q", mm, 24)[0]
        off = PAGE + latest * r._stride
        seq = struct.unpack_from("<Q", mm, off)[0]
        struct.pack_into("<Q", mm, off, seq + 1)  # odd: as if the writer were mid-frame
        assert r.read() is None
        assert (r.stats.retries, r.stats.overruns, r.stats.frames_read) == (1, 1, 0)
        struct.pack_into("<Q", mm, off, seq)
    assert r.read() is not None


@pytest.mark.parametrize(
    ("mutate", "why"),
    [
        (lambda b: b"XXXX" + b[4:], "magic"),
        (lambda b: b[:4] + struct.pack("<I", 9) + b[8:], "version"),
        (lambda b: b[: len(b) - PAGE], "size"),
        (lambda b: b[:10], "not a frame bus"),
    ],
)
def test_anything_else_is_refused(tmp_path: Path, mutate, why: str) -> None:  # type: ignore[no-untyped-def]
    ring = tmp_path / "ring"
    FrameBusWriter(ring, max_width=8, max_height=8).close()
    ring.write_bytes(mutate(ring.read_bytes()))
    with pytest.raises(FrameBusError, match=why):
        FrameBusReader(ring, "t")
    with pytest.raises(FrameBusError):
        FrameBusReader(tmp_path / "missing", "t")


def test_a_new_writer_is_noticed_and_reopened(tmp_path: Path) -> None:
    ring = tmp_path / "ring"
    FrameBusWriter(ring, max_width=8, max_height=8).publish(frame(50, 8, 8), 50, 1)
    source = BusFrameSource(ring, "vision", timeout_s=0.05)
    assert source.grab().frame_id == 50
    second = FrameBusWriter(ring, max_width=8, max_height=8)  # a restarted client: ids restart
    second.publish(frame(1, 8, 8), 1, 2)
    assert source.grab().frame_id == 1
    assert source.snapshot()["reopens"] == 1


def test_grab_waits_for_a_newer_frame_and_times_out(tmp_path: Path) -> None:
    ring = tmp_path / "ring"
    w = FrameBusWriter(ring, max_width=8, max_height=8)
    w.publish(frame(1, 8, 8), 1, 1)
    source = BusFrameSource(ring, "vision", timeout_s=0.5)
    first = source.grab()
    assert first.frame_id == 1 and first.t_capture_ns == 1
    later = threading.Timer(0.1, lambda: w.publish(frame(2, 8, 8), 2, 2))
    later.start()
    t0 = time.monotonic()
    assert source.grab().frame_id == 2  # waited for it: ids strictly increase (Env contract)
    assert 0.05 < time.monotonic() - t0 < 0.45
    source.timeout_s = 0.05
    with pytest.raises(FrameBusTimeout, match="no frame after 2"):
        source.grab()


def test_the_human_view_repeats_a_static_frame_and_is_capped(tmp_path: Path) -> None:
    ring = tmp_path / "ring"
    w = FrameBusWriter(ring, max_width=8, max_height=8)
    w.publish(frame(1, 8, 8), 1, 1)
    view = BusFrameSource(ring, "stream", timeout_s=0.02, repeat_on_timeout=True, max_fps=20)
    assert view.grab().frame_id == 1
    t0 = time.monotonic()
    assert view.grab().frame_id == 1  # a static screen: the same frame again, no exception
    w.publish(frame(2, 8, 8), 2, 2)
    assert view.grab().frame_id == 2
    assert time.monotonic() - t0 >= 2 * 0.05 - 0.005  # two grabs, each >= 1/20 s apart
    assert view.snapshot()["repeats"] == 1


READER = textwrap.dedent(
    """
    import json, sys, time
    import numpy as np
    from poring_env.framebus import FrameBusReader
    r = FrameBusReader(sys.argv[1], "torture")
    deadline = time.monotonic() + float(sys.argv[2])
    last, torn = -1, 0
    while time.monotonic() < deadline:
        got = r.read(last)
        if got is None:
            continue
        px = got.to_numpy()
        if not (px == (got.frame_id * 7) % 256).all():
            torn += 1
        last = got.frame_id
    s = r.stats
    print(json.dumps({"torn": torn, "read": s.frames_read, "drops": s.drops,
                      "overruns": s.overruns, "retries": s.retries}))
    """
)


def test_torture_readers_in_other_processes_never_see_a_torn_frame(tmp_path: Path) -> None:
    ring = tmp_path / "ring"
    w = FrameBusWriter(ring, max_width=320, max_height=200, slots=2)  # 2 slots: lapping is easy
    w.publish(frame(0, 320, 200), 0, 0)
    readers = [
        subprocess.Popen([sys.executable, "-c", READER, str(ring), "1.5"], stdout=subprocess.PIPE)
        for _ in range(3)
    ]
    frame_id, t0 = 0, time.monotonic()
    while time.monotonic() - t0 < 1.7:
        frame_id += 1
        w.publish(frame(frame_id, 320, 200), frame_id, frame_id)
    results = [json.loads(p.communicate(timeout=30)[0]) for p in readers]
    assert all(r["torn"] == 0 for r in results), results
    # Not vacuous: every reader really raced the writer. Counted as ATTEMPTS (frames read + laps
    # it lost), not frames read: on the shared host a starved reader read 22 frames and lost
    # 2593 laps (2026-10-07, 1 run in ~40), and "read > 50" failed on scheduling, never on a tear.
    assert all(r["read"] + r["overruns"] > 50 for r in results), results
    print(f"writer {frame_id} frames in 1.7 s; readers {results}")


def test_a_slow_reader_never_slows_the_writer(tmp_path: Path) -> None:
    ring = tmp_path / "ring"
    w = FrameBusWriter(ring, max_width=640, max_height=400)
    w.publish(frame(0, 640, 400), 0, 0)

    def rate() -> float:
        t0 = time.perf_counter()
        for i in range(1, 101):
            w.publish(frame(i, 640, 400), i, i)
        return 100 / (time.perf_counter() - t0)

    alone = rate()
    slow_reader = READER.replace("last = got.frame_id", "last = got.frame_id; time.sleep(0.2)")
    slow = subprocess.Popen(
        [sys.executable, "-c", slow_reader, str(ring), "2"], stdout=subprocess.PIPE
    )
    time.sleep(0.3)
    with_reader = rate()
    slow.communicate(timeout=30)
    assert with_reader > 0.5 * alone, (alone, with_reader)  # no waiting on a reader, ever


def test_a_ring_that_cannot_be_reserved_fails_at_once_not_mid_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-10-03: a reader still mapped the previous writer's ring, the 64 MiB tmpfs had no room
    for a second one, and the new writer SIGBUSed at its 5th frame. The pages are reserved up front
    now, so a full tmpfs is a clear error at creation (before Sunshine's app is launched)."""
    import errno
    import os as _os

    from poring_env.framebus import FrameBusError

    def full(fd: int, offset: int, length: int) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(_os, "posix_fallocate", full)
    with pytest.raises(FrameBusError, match="still mapped"):
        FrameBusWriter(tmp_path / "ring", max_width=64, max_height=32)
    assert list(tmp_path.iterdir()) == []  # no half-made temp file left behind


def test_the_default_ring_and_an_old_one_fit_the_tmpfs() -> None:
    """Two 1440x900 rings (a reader's old one + the new) must fit the 64 MiB framebus volume."""
    from poring_env.framebus import ring_size, slot_stride  # noqa: F401

    one = ring_size(4, 1440 * 900 * 4)
    assert 2 * one < 64 * 1024 * 1024 - 4 * 1024 * 1024  # with headroom
