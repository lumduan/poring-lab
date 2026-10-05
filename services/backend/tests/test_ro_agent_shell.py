"""scripts/ro_agent.py: the agent's own terminal (Batt, 2026-10-03) -- found only by its exact
"poring-lab shell" tab, and used only after a pixel-verified NON-elevated check. No Windows here."""

import importlib.util
import re
import time
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from poring_backend.capture_lock import (
    LOCK_NAME,
    WINDOW_NAME,
    format_lock,
    format_window,
)

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
    check = ro.elevation_check(33)
    assert "IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)" in check
    assert check.index("DarkRed") < check.index("else") < check.index("DarkGreen")
    assert check.count("(' ' * 33)") == 2


def test_a_marker_counts_only_at_the_width_this_check_asked_for(ro: ModuleType) -> None:
    """2026-10-04: a green bar left by an earlier check passed three checks that never ran."""
    stale = screen_with(ro.MARKER_GREEN, 40 * ro.CELL_W)
    assert ro.marker_colour(stale) == "green"  # any width: the old reading, fooled
    assert ro.marker_colour(stale, cells=40) == "green"
    assert ro.marker_colour(stale, cells=33) is None
    fresh = stale.copy()
    fresh[400:418, 100 : 100 + 33 * ro.CELL_W, :3] = ro.MARKER_GREEN[::-1]
    assert ro.marker_colour(fresh, cells=33) == "green"


def test_a_fresh_width_is_never_one_already_on_screen(ro: ModuleType) -> None:
    import random

    screen = screen_with(ro.MARKER_GREEN, 40 * ro.CELL_W)
    screen[500:518, 100 : 100 + 50 * ro.CELL_W, :3] = ro.MARKER_RED[::-1]
    rng = random.Random(7)
    picks = {ro.fresh_cells(screen, (ro.MARKER_RED, ro.MARKER_GREEN), rng) for _ in range(300)}
    assert picks and not picks & {39, 40, 41, 49, 50, 51}
    assert picks <= set(ro.MARKER_CELLS)
    assert ro.fresh_cells(screen, (ro.MARKER_PROOF,), random.Random(1)) in ro.MARKER_CELLS


def test_a_proven_line_keeps_its_proof_bar(ro: ModuleType) -> None:
    line = ro.proven_line("cls; Get-Date", 30)
    assert line == "cls; Write-Host (' ' * 30) -BackgroundColor DarkMagenta; Get-Date"
    assert line.count("cls") == 1  # the command's own cls would wipe the bar


class FakeConsole:
    """A console that draws the proof bar only if the typed line reached it whole."""

    def __init__(self, ro: ModuleType, runs: bool) -> None:
        self.ro, self.runs, self.sent = ro, runs, []
        self.frame = np.full((900, 1440, 4), 12, np.uint8)

    def keys(self, *codes: str) -> None:
        self.sent.append(("keys", codes))

    def type_text(self, text: str) -> None:
        self.sent.append(("text", text))
        cells = int(re.search(r"\(' ' \* (\d+)\)", text).group(1))  # type: ignore[union-attr]
        if self.runs:
            self.frame[130:148, 86 : 86 + cells * self.ro.CELL_W, :3] = self.ro.MARKER_PROOF[::-1]

    def full(self) -> np.ndarray:
        return self.frame


def test_type_line_reverts_pending_input_then_proves_the_line_ran(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(ro, "SHOTS", tmp_path)
    monkeypatch.setattr(ro, "PROOF_TIMEOUT_S", 1.0)
    windows: list[float] = []  # never the real host tool from a test
    monkeypatch.setattr(
        ro, "ensure_window", lambda kind, phase, s=90, min_left=25: windows.append(min_left)
    )
    ok = FakeConsole(ro, runs=True)
    ro.type_line(ok, ok, "Start-Sleep 10; schtasks /run /tn x")
    assert ok.sent[0] == ("keys", ("Escape",))  # before anything is typed
    assert windows and windows[0] > 15  # a window sized for the line comes first
    assert ok.sent[1][1].endswith("Start-Sleep 10; schtasks /run /tn x\n")
    stuck = FakeConsole(ro, runs=False)  # a `>>` prompt: the line never runs
    stuck.frame[130:148, 86 : 86 + 40 * ro.CELL_W, :3] = ro.MARKER_PROOF[::-1]  # an OLD proof
    with pytest.raises(ro.Stop, match="did not run"):
        ro.type_line(stuck, stuck, "Get-Date")


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
    monkeypatch.setattr(ro, "SHOTS", tmp_path / "shots")  # never the lab's real screenshot dir
    (tmp_path / "shots").mkdir()
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


def test_ensure_window_opens_one_only_when_needed(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ADR-0016: login/desktop phases open a bounded operator window through the HOST tool, and
    never when the interlock is already green or a long-enough window of that kind is open. The
    window is read from the host's state/ files (fresh), never from /health (a tick behind)."""
    calls: list[list[str]] = []

    class Done:
        returncode, stderr = 0, ""

    now = int(time.time())
    (tmp_path / LOCK_NAME).write_text(
        format_lock("rdp", 7, "steady", owner="t", since=now - 60, reason="t"))  # fmt: skip
    monkeypatch.setattr(ro, "LAB_STATE", tmp_path)
    monkeypatch.setattr(ro.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or Done())
    for window, health, opens in [
        (None, {"environment": {"state": "green"}}, False),
        (("login", 80, 7), {"environment": {"state": "red"}}, False),
        (("login", 10, 7), {"environment": {"state": "red"}}, True),  # too short
        (("desktop", 80, 7), {"environment": {"state": "red"}}, True),  # the other kind
        (("login", 80, 6), {"environment": {"state": "red"}}, True),  # an older SEQ's window
        (None, {"environment": {"state": "red"}}, True),
        (None, {}, True),  # backend unreachable: try, and let the backend decide
    ]:
        calls.clear()
        path = tmp_path / WINDOW_NAME
        path.unlink(missing_ok=True)
        if window:
            kind, left, seq = window
            path.write_text(format_window(kind, now - 5, now + left, seq, "t"))
        monkeypatch.setattr(ro, "backend_health", lambda h=health: h)
        ro.ensure_window("login", "login")
        assert bool(calls) is opens, (window, health)
        if opens:
            assert calls[0][-6:] == ["window", "login", "--seconds", "90", "--reason", "login"]
            assert calls[0][1].endswith("scripts/capture_backend.py")


def test_a_window_just_opened_counts_although_health_is_a_tick_behind(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """2026-10-04, to-console failed 3 of 4 times: capture_backend moved the lock to switching
    (SEQ+1), re-opened its desktop window for the new SEQ, and typed tscon. /health still showed
    the previous tick (the SEQ+0 window, now void), so ro_agent ran `capture_backend.py window`,
    which waited 30 s for the flock its own parent held, then failed."""
    now = int(time.time())
    lock = format_lock("console", 8, "switching", owner="t", since=now, reason="to-console")
    (tmp_path / LOCK_NAME).write_text(lock)
    (tmp_path / WINDOW_NAME).write_text(format_window("desktop", now, now + 60, 8, "tscon"))
    stale = {"environment": {"state": "window", "window": "desktop", "window_left_s": 0.4}}
    monkeypatch.setattr(ro, "LAB_STATE", tmp_path)
    monkeypatch.setattr(ro, "backend_health", lambda: stale)

    def no_child(cmd: list[str], **kw: object) -> None:
        raise AssertionError(f"no window command may run here: {cmd}")

    monkeypatch.setattr(ro.subprocess, "run", no_child)
    ro.ensure_window("desktop", "console")


def test_an_interlock_refusal_is_its_own_stop(ro: ModuleType) -> None:
    assert issubclass(ro.Unattested, ro.Stop)


def test_recover_launches_without_closing_when_no_client_is_open(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-10-04: the auto recover's Alt+F4 closed the client, its launch failed (a drifted
    shortcut signature), and a later recover then failed at closing a client that was gone."""
    calls: list[str] = []

    class Session:
        def __enter__(self) -> tuple[object, object]:
            agent = type("A", (), {"wait_for_human": lambda self: None})()
            return agent, object()

        def __exit__(self, *a: object) -> None:
            return None

    monkeypatch.setattr(ro, "session", lambda name: Session())
    monkeypatch.setattr(ro, "close_client", lambda a, s: calls.append("close"))
    monkeypatch.setattr(ro, "launch_client", lambda a, s: calls.append("launch"))
    monkeypatch.setattr(ro, "login", lambda a, s, w: calls.append(f"login {w}"))
    monkeypatch.setattr(ro, "client_absent", lambda s: True)
    ro.recover("gm", retries=0)
    assert calls == ["launch", "login gm"]
    calls.clear()
    monkeypatch.setattr(ro, "client_absent", lambda s: False)
    ro.recover("gm", retries=0)
    assert calls == ["close", "launch", "login gm"]


def test_recover_with_no_retries_is_one_attempt(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """guarded_build's auto recover after a sniffer restart: `recover gm --retries 0` -- one try."""
    names: list[str] = []

    class Boom:
        def __init__(self, name: str) -> None:
            names.append(name)

        def __enter__(self) -> None:
            raise ro.Stop("the client did not launch")

        def __exit__(self, *a: object) -> None:
            return None

    monkeypatch.setattr(ro, "session", lambda name: Boom(name))
    monkeypatch.setattr(ro.time, "sleep", lambda s: None)
    with pytest.raises(ro.Stop):
        ro.recover("gm", retries=0, agent_id="auto_recover")
    assert names == ["auto_recover"]
    names.clear()
    with pytest.raises(ro.Stop):
        ro.recover("gm")  # the default keeps its two retries
    assert names == ["ro_agent-recover"] * 3


def test_the_th_profile_switches_client_accounts_shortcut_and_database(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-10-05, the Thai-data experiment: kro stays the default; th is the separate client copy,
    its RATHENA_TH_* accounts, its own shortcut position and db-th."""
    monkeypatch.delenv("RO_PROFILE", raising=False)
    env = {"RATHENA_TH_GM_USER": "thv_x", "RATHENA_TH_GM_PASSWORD": "p", "RATHENA_TH_GM_CHAR": "c",
           "RO_SHORTCUT": "37,543", "RO_SHORTCUT_TH": "37,450"}  # fmt: skip
    monkeypatch.setattr(ro, "env", lambda: env)
    try:
        assert ro.use_profile(None).name == "kro" and ro.DB == "poring-lab-db-1"
        assert ro.shortcut_xy() == (37, 543)
        with pytest.raises(ro.Stop):
            ro.account("gm")  # kro's RATHENA_GM_* are absent here
        th = ro.use_profile("th")
        assert th.client == r"C:\RO-rAthena-th\client" and ro.DB == "poring-lab-db-th-1"
        assert ro.account("gm") == ("thv_x", "p", "c")
        assert ro.shortcut_xy() == (37, 450)
        with pytest.raises(ro.Stop, match="unknown client profile"):
            ro.use_profile("official")
    finally:
        ro.use_profile("kro")
