"""The frame-age guard (2026-10-04): poring_env.freshness, MuxedEnv's refusal, the backend's stall
monitor, and the recorder's freeze spans."""

from pathlib import Path

import numpy as np
import pytest

from poring_backend.freshness_monitor import StallMonitor
from poring_env.framebus import FrameBusReader, FrameBusWriter
from poring_env.freshness import StaleFrame, freeze_spans, is_release, presses
from poring_env.protocol import Key, MouseButton, MouseMove, ReleaseAll, Wheel

MS = 1_000_000


def test_releases_are_never_presses() -> None:
    up = [Key(t_mono_ns=1, code="KeyA", action="up"), ReleaseAll(t_mono_ns=1),
          MouseButton(t_mono_ns=1, button="left", action="up")]  # fmt: skip
    assert all(is_release(e) for e in up) and not presses(up)
    for e in (Key(t_mono_ns=1, code="KeyA", action="down"), MouseMove(t_mono_ns=1, x=0.1, y=0.1),
              Wheel(t_mono_ns=1, dy=1)):  # fmt: skip
        assert presses([e])


def test_freeze_spans_are_the_gaps_above_the_threshold() -> None:
    times = [0, 33 * MS, 66 * MS, 300 * MS, 333 * MS]
    assert freeze_spans(times, 150) == [(66 * MS, 300 * MS)]
    assert freeze_spans(times, 300) == []


def test_latest_stamp_reads_the_newest_frame_header(tmp_path: Path) -> None:
    w = FrameBusWriter(tmp_path / "ring", max_width=4, max_height=4)
    r = FrameBusReader(tmp_path / "ring", "t")
    assert r.latest_stamp() is None
    w.publish(np.zeros((4, 4, 4), np.uint8), frame_id=9, t_mono_ns=12345)
    assert r.latest_stamp() == (9, 12345)
    assert r.stats.frames_read == 0  # header only: the reader's counters are untouched


class FakeSource:
    def __init__(self, age: float | None) -> None:
        self.age = age

    def stream_age_ms(self) -> float | None:
        return self.age

    def close(self) -> None: ...


class FakeSink:
    def __init__(self) -> None:
        self.sent: list[object] = []

    def send_batch(self, events, *, frame_id, t_capture_ns):  # type: ignore[no-untyped-def]
        self.sent.append(list(events))
        return True

    def close(self) -> None: ...


def env_with(age: float | None):  # type: ignore[no-untyped-def]
    from poring_env.remote import MuxedEnv

    return MuxedEnv(FakeSource(age), FakeSink())  # type: ignore[arg-type]


def test_a_frozen_stream_refuses_presses_but_never_releases() -> None:
    from poring_env.clock import monotonic_ns
    from poring_env.frame import Frame

    env = env_with(400.0)
    frame = Frame(1, monotonic_ns(), 1, 1, b"\0\0\0\0")
    with pytest.raises(StaleFrame):
        env.act(frame, [Key(t_mono_ns=1, code="KeyA", action="down")])
    assert env.act(frame, [Key(t_mono_ns=1, code="KeyA", action="up")]) is True  # always
    up = Key(t_mono_ns=1, code="KeyA", action="up")
    assert env.stale_refused == 1 and env.sink.sent == [[up]]


def test_a_stale_cited_frame_is_refused_on_a_live_stream() -> None:
    from poring_env.clock import monotonic_ns
    from poring_env.frame import Frame

    env = env_with(20.0)
    old = Frame(1, monotonic_ns() - 900 * MS, 1, 1, b"\0\0\0\0")
    with pytest.raises(StaleFrame):
        env.act(old, [MouseMove(t_mono_ns=1, x=0.5, y=0.5)])
    fresh = Frame(2, monotonic_ns(), 1, 1, b"\0\0\0\0")
    assert env.act(fresh, [MouseMove(t_mono_ns=1, x=0.5, y=0.5)]) is True


def test_the_stall_monitor_counts_a_gap_and_resets_on_a_new_writer(tmp_path: Path) -> None:
    ring = tmp_path / "ring"
    now = {"t": 0}
    mon = StallMonitor(ring, console_mode=lambda: True, threshold_ms=150, clock=lambda: now["t"])
    w = FrameBusWriter(ring, max_width=4, max_height=4)
    px = np.zeros((4, 4, 4), np.uint8)
    for i, t in enumerate((0, 33, 66), start=1):
        w.publish(px, frame_id=i, t_mono_ns=t * MS)
        now["t"] = t * MS + 5 * MS
        mon.sample()
    now["t"] = 300 * MS  # nothing new: stalled
    mon.sample()
    assert mon.snapshot()["stalled_now"] is True
    w.publish(px, frame_id=4, t_mono_ns=320 * MS)
    now["t"] = 325 * MS
    mon.sample()
    snap = mon.snapshot()
    assert (snap["stalls"], snap["max_stall_ms"], snap["stalled_now"]) == (1, 254.0, False)
    w.close(unlink=True)
    mon.sample()  # the ring went away: the mapping is released
    assert mon.snapshot()["frame_age_ms"] is None and mon._reader is None


def test_outside_console_mode_the_monitor_holds_no_mapping(tmp_path: Path) -> None:
    w = FrameBusWriter(tmp_path / "ring", max_width=4, max_height=4)
    w.publish(np.zeros((4, 4, 4), np.uint8), frame_id=1, t_mono_ns=1)
    mon = StallMonitor(tmp_path / "ring", console_mode=lambda: False)
    mon.sample()
    assert mon._reader is None
