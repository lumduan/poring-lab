"""The black-screen detector (display.py): pixels only, a hold time, RDP reconnects."""

from typing import Any

import pytest

from poring_backend.display import BLACK_FRACTION, DisplayWatch, Region, measure
from poring_env.frame import Frame

S = 1_000_000_000


def frame(t_ns: int, *, value: int = 0, lit: tuple[int, int, int, int] | None = None) -> Frame:
    """A 100x80 frame of grey `value`; `lit` = an (x, y, w, h) white rectangle on top."""
    w, h = 100, 80
    px = bytearray([value, value, value, 255] * (w * h))
    if lit is not None:
        x0, y0, lw, lh = lit
        for y in range(y0, y0 + lh):
            for x in range(x0, x0 + lw):
                i = (y * w + x) * 4
                px[i : i + 3] = b"\xff\xff\xff"
    return Frame(frame_id=t_ns, t_capture_ns=t_ns, width=w, height=h, bgra=bytes(px))


def test_region_parsing() -> None:
    assert Region.parse("") is None
    assert Region.parse(" 10,20,800,664 ") == Region(10, 20, 800, 664)
    assert str(Region(10, 20, 800, 664)) == "10,20,800,664"
    for bad in ("1,2,3", "1,2,0,4", "-1,2,3,4", "a,b,c,d"):
        with pytest.raises(ValueError):
            Region.parse(bad)


def test_measure_only_looks_inside_the_region() -> None:
    f = frame(0, lit=(0, 0, 40, 80))  # left 40 % lit, the rest black
    whole = measure(f, None)
    right = measure(f, Region(50, 0, 50, 80))
    assert whole is not None and right is not None
    assert 0.5 < whole[1] < 0.7
    assert right == (0.0, 1.0)
    assert measure(f, Region(500, 500, 10, 10)) is None  # outside the frame


def test_black_only_after_the_hold_time() -> None:
    clock = [0]
    watch = DisplayWatch(None, hold_s=5.0, clock=lambda: clock[0])
    assert watch.evaluate(0) == "unknown" and watch.black is None
    for t in range(0, 5 * S, S // 2):
        watch.observe(frame(t))
        assert watch.evaluate(t) == "ok"
    watch.observe(frame(5 * S))
    assert watch.evaluate(5 * S) == "black" and watch.black is True
    assert watch.blackouts == 1
    watch.observe(frame(5 * S + S // 2, value=128))  # the client redraws
    assert watch.evaluate(5 * S + S // 2) == "ok"


def test_a_dark_scene_with_lit_ui_is_not_black() -> None:
    watch = DisplayWatch(None, hold_s=1.0)
    for t in range(0, 10 * S, S // 2):
        watch.observe(frame(t, value=3, lit=(0, 70, 100, 10)))  # night map + a lit chat bar
        assert watch.evaluate(t) == "ok"
    assert watch.dark_fraction is not None and watch.dark_fraction < BLACK_FRACTION


def test_no_recent_sample_means_unknown_not_ok() -> None:
    watch = DisplayWatch(None, hold_s=1.0)
    watch.observe(frame(0, value=128))
    assert watch.evaluate(S) == "ok"
    assert watch.evaluate(7 * S) == "unknown"
    assert watch.needs_sample(2 * S)


def test_frames_are_rate_limited_to_two_analyses_a_second() -> None:
    watch = DisplayWatch(None, hold_s=1.0)
    watch.observe(frame(0, value=128))
    watch.observe(frame(S // 10))  # black, but too soon after the last analysis: skipped
    assert watch.dark_fraction == 0.0


def test_rdp_window_gone_and_back_is_one_reconnect() -> None:
    watch = DisplayWatch(None, hold_s=1.0)
    watch.rdp(None, 0)  # X not reachable yet
    watch.rdp(True, 1 * S)  # first sighting: not a reconnect
    assert watch.rdp_reconnects == 0
    watch.rdp(False, 10 * S)
    watch.rdp(False, 11 * S)
    watch.rdp(True, 14 * S)
    snap: dict[str, Any] = watch.snapshot(20 * S)
    assert watch.rdp_reconnects == 1
    assert snap["last_reconnect_gap_s"] == 4.0 and snap["last_reconnect_s_ago"] == 6.0
