"""poring_backend.grabsource: the measurement and screenshot helpers' one rule -- the S2 frame bus
in console mode with a live writer, else X. Fake ring + fake lab-state; X is a stub."""

import time
from pathlib import Path

import numpy as np
import pytest

from poring_backend import grabsource
from poring_backend.grabsource import GrabSource
from poring_env.framebus import FrameBusWriter


def lab(tmp_path: Path, backend: str) -> Path:
    d = tmp_path / "lab-state"
    d.mkdir(exist_ok=True)
    (d / "capture-backend").write_text(f"BACKEND={backend}\nSEQ=4\nPHASE=steady\n")
    return d


def x_stub(region: tuple[int, int, int, int]) -> tuple[int, np.ndarray]:
    _, _, w, h = region
    return time.monotonic_ns(), np.full((h, w, 4), 7, np.uint8)


@pytest.fixture(autouse=True)
def no_recheck_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(grabsource, "RECHECK_S", 0.0)


def frame(value: int) -> np.ndarray:
    return np.full((6, 8, 4), value, np.uint8)


def test_console_with_a_live_writer_reads_the_bus_cropped(tmp_path: Path) -> None:
    ring = tmp_path / "ring"
    w = FrameBusWriter(ring, max_width=8, max_height=6)
    px = np.arange(6 * 8 * 4, dtype=np.uint8).reshape(6, 8, 4)
    w.publish(px, frame_id=1, t_mono_ns=555)
    src = GrabSource(lab_state=lab(tmp_path, "console"), ring=ring, x_grab=x_stub)
    t, img, source = src.grab((2, 1, 4, 3))
    assert (t, source) == (555, "bus") and np.array_equal(img, px[1:4, 2:6])


@pytest.mark.parametrize("backend", ["rdp", "hold"])
def test_rdp_or_hold_grabs_x(tmp_path: Path, backend: str) -> None:
    ring = tmp_path / "ring"
    FrameBusWriter(ring, max_width=8, max_height=6).publish(frame(1), 1, 1)
    src = GrabSource(lab_state=lab(tmp_path, backend), ring=ring, x_grab=x_stub)
    assert src.grab((0, 0, 4, 3))[2] == "x11"


def test_frames_yields_each_new_bus_frame_once_and_ticks_between(tmp_path: Path) -> None:
    ring = tmp_path / "ring"
    w = FrameBusWriter(ring, max_width=8, max_height=6)
    w.publish(frame(1), 1, 100)
    src = GrabSource(lab_state=lab(tmp_path, "console"), ring=ring, x_grab=x_stub)
    out = []
    for t, img, source in src.frames((0, 0, 8, 6), 0.5, tick_s=0.05):
        out.append((t if img is not None else None, source))
        if len(out) == 3:
            w.publish(frame(2), 2, 200)
    frames = [t for t, _ in out if t is not None]
    assert frames == [100, 200]  # each once, at the writer's decode time
    assert any(t is None for t, _ in out)  # ticks while no new frame arrives
    assert {s for _, s in out} == {"bus"}


def test_a_stale_writer_falls_back_to_x_and_says_so(tmp_path: Path) -> None:
    ring = tmp_path / "ring"
    FrameBusWriter(ring, max_width=8, max_height=6).publish(frame(1), 1, 1)
    src = GrabSource(lab_state=lab(tmp_path, "console"), ring=ring, stale_s=0.05, x_grab=x_stub)
    time.sleep(0.1)  # the writer stops heart-beating
    assert src.grab((0, 0, 4, 3))[2] == "x11"


def test_the_watch_output_parser_keeps_the_sources(tmp_path: Path) -> None:
    import importlib.util
    import sys

    path = Path(__file__).resolve().parents[3] / "scripts" / "measure_delay.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("measure_delay", path)
    assert spec and spec.loader
    md = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(md)
    import base64

    thumb = base64.b64encode(bytes([1, 2, 3])).decode()
    grabs, sources = md.parse_watch(f"#source=bus\n10,{thumb}\n#source=x11\n20,{thumb}\n")
    assert [t for t, _ in grabs] == [10, 20] and sources == ["bus", "x11"]
