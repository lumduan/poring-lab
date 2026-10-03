"""scripts/ro_agent.py: the agent's own terminal (Batt, 2026-10-03) -- found only by its exact
"poring-lab shell" tab, and used only after a pixel-verified NON-elevated check. No Windows here."""

import importlib.util
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def ro() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ro_agent", SCRIPTS / "ro_agent.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def screen_with(colour: tuple[int, int, int] | None, run: int, y: int = 300) -> np.ndarray:
    bgra = np.full((900, 1440, 4), 12, np.uint8)
    if colour is not None:
        bgra[y : y + 18, 100 : 100 + run, :3] = colour[::-1]  # RGB -> BGR
    return bgra


def test_marker_colour(ro: ModuleType) -> None:
    assert ro.marker_colour(screen_with(ro.MARKER_GREEN, 360)) == "green"
    assert ro.marker_colour(screen_with(ro.MARKER_RED, 360)) == "red"
    assert ro.marker_colour(screen_with(ro.MARKER_GREEN, 40)) is None  # a word, not the marker
    assert ro.marker_colour(screen_with(None, 0)) is None
    both = screen_with(ro.MARKER_RED, 360, y=200)
    both[500:518, 100:460, :3] = ro.MARKER_GREEN[::-1]
    assert ro.marker_colour(both) == "green"  # the newest (bottom-most) line wins


def test_the_elevation_check_is_red_for_an_administrator(ro: ModuleType) -> None:
    check = ro.ELEVATION_CHECK
    assert "IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)" in check
    assert check.index("DarkRed") < check.index("else") < check.index("DarkGreen")


def test_the_agents_shell_is_preferred_over_any_powershell_tab(ro: ModuleType) -> None:
    assert ro.CONSOLE_TEMPLATES[False][0] == ro.SHELL_TEMPLATE
    assert ro.SHELL_TEMPLATE not in ro.CONSOLE_TEMPLATES[True]  # never an elevated console's


def test_the_screen_helper_reads_the_frame_bus_only_in_console_mode_with_a_live_writer(
    ro: ModuleType, tmp_path: Path
) -> None:
    """V3b never paints X: ro_agent's screenshots (and the clean room's picture test) must read the
    bus there. In rdp mode, or with no live writer, the helper grabs X as before (it never even
    imports mss until it needs X, so this test needs no display)."""
    import os
    import struct
    import subprocess
    import sys

    from poring_env.framebus import FrameBusWriter

    lab_state, ring = tmp_path / "lab-state", tmp_path / "ring"
    lab_state.mkdir()
    (lab_state / "capture-backend").write_text("BACKEND=console\nSEQ=9\nPHASE=steady\n")
    writer = FrameBusWriter(ring, max_width=8, max_height=6)
    pixels = np.arange(8 * 6 * 4, dtype=np.uint8).reshape(6, 8, 4)
    writer.publish(pixels, frame_id=3, t_mono_ns=777)
    env = {**os.environ, "RO_AGENT_LAB_STATE": str(lab_state), "RO_AGENT_FRAMEBUS": str(ring)}
    helper = subprocess.run(
        [sys.executable, "-c", ro._HELPER], input=b"2 1 4 3\n", capture_output=True, env=env,
        timeout=30, check=True,
    )  # fmt: skip
    t, w, h = struct.unpack("<qII", helper.stdout[:16])
    assert (t, w, h) == (777, 4, 3)  # the writer's decode time, not a grab time
    got = np.frombuffer(helper.stdout[16:], np.uint8).reshape(3, 4, 4)
    assert np.array_equal(got, pixels[1:4, 2:6])
