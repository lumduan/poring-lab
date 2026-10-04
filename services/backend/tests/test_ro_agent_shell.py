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
    env = {**os.environ, "GRAB_LAB_STATE": str(lab_state), "GRAB_FRAMEBUS": str(ring)}
    helper = subprocess.run(
        [sys.executable, "-c", ro._HELPER], input=b"2 1 4 3\n", capture_output=True, env=env,
        timeout=30, check=True,
    )  # fmt: skip
    size = struct.calcsize(ro.HELPER_HEADER)
    t, w, h, frame_id, bus = struct.unpack(ro.HELPER_HEADER, helper.stdout[:size])
    assert (t, w, h) == (777, 4, 3)  # the writer's decode time, not a grab time
    assert (frame_id, bus) == (3, 1)  # the writer's frame_id, from the bus (the recorder keeps it)
    got = np.frombuffer(helper.stdout[size:], np.uint8).reshape(3, 4, 4)
    assert np.array_equal(got, pixels[1:4, 2:6])


def test_a_locale_variant_matches_without_replacing_the_english_signature(
    ro: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-10-03: the Thai pack retitles the login dialogs; `<state>@th` is a second template of
    the SAME box, so the English one still matches after switching back."""
    monkeypatch.setattr(ro, "STATE_DIR", tmp_path)
    monkeypatch.setattr(ro, "region_for", lambda state: (0, 0, 64, 32))
    english = np.full((32, 64, 4), 40, np.uint8)
    thai = english.copy()
    thai[4:12, 8:56, :3] = 220  # the dialog's title text, in another script

    class FakeScreen:
        def __init__(self, img: np.ndarray) -> None:
            self.img = img

        def grab(self, x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray]:
            return 0, self.img

    ro.calibrate(FakeScreen(english), "login")
    assert ro.distance(FakeScreen(thai), "login") > ro.SIG_MATCH  # English template only
    ro.calibrate(FakeScreen(thai), "login@th")
    assert ro.is_state(FakeScreen(thai), "login") and ro.is_state(FakeScreen(english), "login")
    assert ro.distance(FakeScreen(english), "login@th") > ro.SIG_MATCH  # explicit = that file
    names = sorted(p.name for p in (tmp_path / "signatures").glob("*.npy"))
    assert names == ["login.npy", "login@th.npy"]


def test_close_extra_shells_closes_only_other_exact_title_windows(ro: ModuleType) -> None:
    cmd = ro.CLOSE_EXTRA_SHELLS
    assert "-ceq 'poring-lab shell'" in cmd  # exact, case-sensitive: never Batt's consoles
    assert "Where-Object { $_ -ne $fg }" in cmd  # never the foreground (this) window
    assert "PostMessage($_, 0x10," in cmd and "Stop-Process" not in cmd  # WM_CLOSE only
    assert cmd.endswith("@(Get-PlShells).Count")  # the count is read back


def test_file_check_and_the_copy_line(ro: ModuleType) -> None:
    path = r"C:\RO-rAthena\client\2021-11-03_Ragexe_1635926200.exe"
    check = ro.file_check_command(path)
    assert f"$p = '{path}'" in check and "Get-FileHash -LiteralPath $p" in check
    assert ro.copy_item_line(path) == (
        f"Copy-Item -LiteralPath '{path}' -Destination '\\\\tsclient\\transfer\\'"
    )
    with pytest.raises(ro.Stop):
        ro.file_check_command("C:\\it's.exe")


def test_a_stream_copy_of_the_shell_template_is_tried_too(
    ro: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ro, "STATE_DIR", tmp_path)
    (tmp_path / "signatures").mkdir()
    seen: list[int] = []

    def match(rgb: np.ndarray, tmpl: np.ndarray) -> tuple[int, int, float] | None:
        seen.append(int(tmpl[0, 0, 0]))
        return (10, 20, 3.0) if int(tmpl[0, 0, 0]) == 2 else None  # only the stream one matches

    monkeypatch.setattr(ro, "_match_console", match)
    np.save(tmp_path / "signatures" / "shell_tab_template.npy", np.full((4, 4, 3), 1, np.uint8))
    np.save(
        tmp_path / "signatures" / "shell_tab_template_stream.npy", np.full((4, 4, 3), 2, np.uint8)
    )

    class FakeScreen:
        def full(self) -> np.ndarray:
            return np.zeros((10, 10, 4), np.uint8)

    assert ro.find_shell(FakeScreen()) == (10, 20, 3.0) and seen == [1, 2]
    assert ro.template_names("ps_tab_template.npy") == (
        "ps_tab_template.npy", "ps_tab_template_stream.npy",
    )  # fmt: skip


def test_an_actions_effect_is_judged_only_on_a_later_frame(ro: ModuleType) -> None:
    """2026-10-04 05:58: a frozen frame (a dropped frame waiting for an IDR) made the chat look
    closed right after Enter. grab_after waits for a frame decoded after the action, and a stream
    that stays frozen is FrozenStream -- unknown, never "closed"."""
    frames = [(100, "old"), (100, "old"), (250, "new")]

    class FakeScreen:
        def grab_meta(self, x: int, y: int, w: int, h: int):  # type: ignore[no-untyped-def]
            t, tag = frames.pop(0) if len(frames) > 1 else frames[0]
            return t, tag, 1, "bus"

    assert ro.grab_after(FakeScreen(), (0, 0, 1, 1), after_ns=200) == "new"
    frames[:] = [(100, "old")]
    with pytest.raises(ro.FrozenStream):
        ro.grab_after(FakeScreen(), (0, 0, 1, 1), after_ns=200)
    assert issubclass(ro.FrozenStream, ro.Stop)  # callers that retry on Stop retry on it too
