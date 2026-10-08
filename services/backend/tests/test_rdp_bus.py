"""rdp_bus.py: ONE X grabber on the RDP path publishes every grab to a backend-private ring (Batt
2026-10-08), only while the capture-backend lock says rdp; the readers (GrabSource, the console
stream's CaptureSelector) read it while it heart-beats, else X, as on S2."""

import time
from pathlib import Path

import numpy as np

from poring_backend import grabsource
from poring_backend.capture_select import CaptureSelector
from poring_backend.grabsource import GrabSource
from poring_backend.rdp_bus import RdpBusWriter, enabled
from poring_env.frame import Frame
from poring_env.framebus import FrameBusReader, FrameBusWriter


def session_grab() -> tuple[object, list[int]]:
    """A fake X: each grab returns an 8x6 BGRA picture whose pixels say which grab it was."""
    n = [0]

    def grab() -> tuple[int, np.ndarray]:
        n[0] += 1
        return 1_000 + n[0], np.full((6, 8, 4), n[0], np.uint8)

    return grab, n


def lab(tmp_path: Path, backend: str) -> Path:
    d = tmp_path / "lab-state"
    d.mkdir(exist_ok=True)
    (d / "capture-backend").write_text(f"BACKEND={backend}\nSEQ=4\nPHASE=steady\n")
    return d


def test_each_grab_is_published_with_its_own_id_and_capture_time(tmp_path: Path) -> None:
    grab, _ = session_grab()
    w = RdpBusWriter(grab, ring=tmp_path / "rdp-ring", lab_state=lab(tmp_path, "rdp"))  # type: ignore[arg-type]
    for _ in range(3):
        w.step(now=time.monotonic(), last_grab=0.0)
    r = FrameBusReader(tmp_path / "rdp-ring", "test")
    got = r.read()
    assert got is not None and (got.frame_id, got.t_mono_ns) == (3, 1_003)
    assert int(got.to_numpy()[0, 0, 0]) == 3  # the pixels of that very grab
    assert r.writer().heartbeat_age_s < 1.0 and w.snapshot()["frames"] == 3


def test_the_loop_grabs_on_damage_and_keepalive_and_stops_writing_off_rdp(tmp_path: Path) -> None:
    grab, n = session_grab()
    backend = {"b": "rdp"}
    damages: list[object] = []

    class Damage:
        def __init__(self, cb: object) -> None:
            damages.append(cb)

        def start(self) -> None: ...

        def stop(self) -> None: ...

    ring = tmp_path / "rdp-ring"
    w = RdpBusWriter(grab, ring=ring, lab_state=tmp_path, damage_factory=Damage, max_fps=200.0,
                     keepalive_s=0.05, lock_backend=lambda: backend["b"])  # type: ignore[arg-type]  # fmt: skip
    w.start()
    try:
        time.sleep(0.4)
        assert n[0] >= 4 and w.keepalives >= 4 and ring.exists()  # a still screen: keepalives
        damages[0](0)  # type: ignore[operator]  # X says the screen changed
        time.sleep(0.1)
        assert w.on_damage >= 1
        backend["b"] = "console"  # a handover: the RDP bus stops at once
        time.sleep(0.8)
        assert not ring.exists() and not w.writing
    finally:
        w.stop()


def test_grabsource_reads_the_rdp_ring_in_rdp_and_the_s2_ring_in_console(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setattr(grabsource, "RECHECK_S", 0.0)  # type: ignore[attr-defined]
    s2, rdp = tmp_path / "ring", tmp_path / "rdp-ring"
    FrameBusWriter(s2, max_width=8, max_height=6).publish(np.full((6, 8, 4), 1, np.uint8), 1, 111)
    FrameBusWriter(rdp, max_width=8, max_height=6).publish(np.full((6, 8, 4), 2, np.uint8), 5, 222)
    state = lab(tmp_path, "rdp")
    src = GrabSource(
        lab_state=state, ring=s2, rdp_ring=rdp, x_grab=lambda r: (0, np.zeros((1, 1, 4), np.uint8))
    )
    t, img, source = src.grab((0, 0, 4, 3))
    assert (t, source, src.last_frame_id, int(img[0, 0, 0])) == (222, "bus", 5, 2)
    (state / "capture-backend").write_text("BACKEND=console\nSEQ=5\nPHASE=steady\n")
    t, img, source = src.grab((0, 0, 4, 3))
    assert (t, source, int(img[0, 0, 0])) == (111, "bus", 1)  # the lock flipped: the S2 ring


def test_the_console_stream_shows_the_rdp_bus_frames_in_rdp_mode(tmp_path: Path) -> None:
    class X:
        def grab(self) -> Frame:
            return Frame(10_001, 0, 2, 2, b"\0" * 16)

        def close(self) -> None: ...

    mode = {"rdp": True}
    rdp = tmp_path / "rdp-ring"
    sel = CaptureSelector(lambda: X(), bus_path=tmp_path / "ring", console_mode=lambda: False,
                          console_fps=1000.0, stale_s=0.5, rdp_bus_path=rdp,
                          rdp_mode=lambda: mode["rdp"])  # fmt: skip
    assert sel.grab().frame_id == 10_001  # no RDP writer yet: X
    FrameBusWriter(rdp, max_width=4, max_height=4).publish(np.zeros((4, 4, 4), np.uint8), 9, 77)
    got = sel.grab()
    assert (got.frame_id, got.t_capture_ns, sel.active) == (9, 77, "bus")  # the writer's own ids
    mode["rdp"] = False  # e.g. hold: X again
    assert sel.grab().frame_id == 10_001


def test_rdp_framebus_off_disables_it(monkeypatch: object) -> None:
    monkeypatch.setenv("RDP_FRAMEBUS", "off")  # type: ignore[attr-defined]
    assert not enabled()
    monkeypatch.setenv("RDP_FRAMEBUS", "on")  # type: ignore[attr-defined]
    assert enabled()
