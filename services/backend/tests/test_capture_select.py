"""capture_select.py: the console stream reads the S2 frame bus only in console mode with a LIVE
writer; RDP mode, no ring, or a writer that stopped heart-beating -> X11, as before."""

import time
from pathlib import Path

import numpy as np
import pytest

from poring_backend.capture_select import CaptureSelector
from poring_env.frame import Frame
from poring_env.framebus import FrameBusWriter


class FakeX11:
    def __init__(self) -> None:
        self.n = 0
        self.closed = 0

    def grab(self) -> Frame:
        self.n += 1
        return Frame(self.n + 10_000, 0, 2, 2, b"\0" * 16)

    def close(self) -> None:
        self.closed += 1


@pytest.fixture
def world(tmp_path: Path) -> dict[str, object]:
    x11 = FakeX11()
    state = {"console": False}
    sel = CaptureSelector(
        lambda: x11, bus_path=tmp_path / "ring", console_mode=lambda: state["console"],
        console_fps=1000.0, stale_s=0.5,
    )  # fmt: skip
    return {"x11": x11, "state": state, "sel": sel, "ring": tmp_path / "ring"}


def test_rdp_mode_and_a_missing_ring_stay_on_x11(world: dict[str, object]) -> None:
    sel, state = world["sel"], world["state"]
    assert isinstance(sel, CaptureSelector) and isinstance(state, dict)
    assert sel.grab().frame_id == 10_001 and sel.active == "x11"
    state["console"] = True  # console mode, but no S2 writer (Moonlight-qt / the V3 mirror era)
    assert sel.grab().frame_id == 10_002 and sel.active == "x11"
    assert sel.snapshot()["writer"] is None


def test_console_mode_with_a_live_writer_streams_the_bus_and_falls_back_when_it_stops(
    world: dict[str, object],
) -> None:
    sel, state, ring = world["sel"], world["state"], world["ring"]
    assert isinstance(sel, CaptureSelector) and isinstance(state, dict) and isinstance(ring, Path)
    w = FrameBusWriter(ring, max_width=4, max_height=4)
    w.publish(np.zeros((4, 4, 4), np.uint8), frame_id=7, t_mono_ns=99)
    w.set_decode_stats(3_000, 8_000)
    sel.grab()  # still rdp: x11
    state["console"] = True
    got = sel.grab()
    assert (got.frame_id, got.t_capture_ns, sel.active) == (7, 99, "bus")  # the writer's own ids
    snap = sel.snapshot()
    assert snap["writer"]["latest_frame_id"] == 7 and snap["writer"]["decode_ms_p95"] == 8.0
    assert snap["consumers"]["stream"]["frames_read"] == 1
    time.sleep(0.6)  # the writer stops heart-beating
    assert sel.grab().frame_id > 10_000 and sel.active == "x11"
    w.heartbeat()
    w.publish(np.zeros((4, 4, 4), np.uint8), frame_id=8, t_mono_ns=100)
    assert sel.grab().frame_id == 8 and sel.switches == 3  # back by itself
    state["console"] = False
    assert sel.grab().frame_id > 10_000  # a handover to rdp: X11 at once


def test_close_keeps_the_counters(world: dict[str, object]) -> None:
    sel = world["sel"]
    assert isinstance(sel, CaptureSelector)
    sel.grab()
    sel.close()  # the hub closes and re-uses it after a capture error
    assert sel.grab().frame_id == 10_002


def test_the_bus_is_self_paced_so_the_hub_stops_waiting_for_x_damage(
    world: dict[str, object],
) -> None:
    """2026-10-03: on S2 nothing paints Xvfb, so damage mode only ever fired its 1 s keepalive and
    the console showed ~1 fps of a 30 fps bus. A self-paced source turns damage waiting off."""
    from poring_backend.stream import CaptureHub, StreamTuning

    sel, state, ring = world["sel"], world["state"], world["ring"]
    assert isinstance(sel, CaptureSelector) and isinstance(state, dict) and isinstance(ring, Path)

    class Damage:
        connected, events = True, 0

        def start(self) -> None: ...

        def stop(self) -> None: ...

    hub = CaptureHub(lambda: sel, tuning=StreamTuning(capture="damage"),
                     damage_factory=lambda _cb: Damage())  # type: ignore[arg-type,return-value]  # fmt: skip
    hub._ensure_damage()
    hub._source = sel
    assert sel.self_paced is False and hub.damage_active is True  # X: damage-driven, as before
    w = FrameBusWriter(ring, max_width=4, max_height=4)
    w.publish(np.zeros((4, 4, 4), np.uint8), frame_id=1, t_mono_ns=1)
    state["console"] = True
    sel.grab()
    assert sel.self_paced is True and hub.damage_active is False  # the bus paces the console
    assert hub.target_fps == hub.tuning.fps
