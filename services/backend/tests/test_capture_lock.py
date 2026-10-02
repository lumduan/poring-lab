"""The capture-backend lock (ADR-0009): one Windows session, one display path at a time.

rdp-loop.sh connects only while the lock says `rdp`, fails closed on anything it cannot read, never
connects while a Moonlight window is on the display, and wakes from every wait when the lock
changes. These tests run the real script (functions and the main loop) with fake X/RDP binaries.
"""

import os
import signal
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RDP_LOOP = ROOT / "services" / "desktop" / "bin" / "rdp-loop.sh"
STREAM_LOOP = ROOT / "services" / "gamestream" / "bin" / "gamestream-loop.sh"


def write_lock(state: Path, text: str) -> None:
    """Atomic, like scripts/capture_backend.py: a new inode every time."""
    tmp = state / ".capture-backend.tmp"
    tmp.write_text(text)
    tmp.replace(state / "capture-backend")


def read_lock(state_dir: Path) -> tuple[str, str, str, str]:
    script = f'source "{RDP_LOOP}"; read_lock; printf "%s|%s|%s|%s" "$LOCK_BACKEND" "$LOCK_SEQ" '
    script += '"$LOCK_PHASE" "$LOCK_WHY"'
    env = {"PATH": "/usr/bin:/bin", "LAB_STATE_DIR": str(state_dir)}
    out = subprocess.run(
        ["bash", "-c", script], env=env, capture_output=True, text=True, check=True
    )
    backend, seq, phase, why = out.stdout.split("|", 3)
    return backend, seq, phase, why


def test_lock_values(tmp_path: Path) -> None:
    write_lock(tmp_path, "BACKEND=console\nSEQ=7\nPHASE=switching\nOWNER=capture_backend\n")
    assert read_lock(tmp_path)[:3] == ("console", "7", "switching")
    write_lock(tmp_path, "# comment\n\nBACKEND=rdp\nSEQ=8\nSINCE=1759370000\nREASON=to-rdp\n")
    assert read_lock(tmp_path)[:3] == ("rdp", "8", "steady")


def test_mounted_directory_without_a_file_is_rdp(tmp_path: Path) -> None:
    assert read_lock(tmp_path)[0] == "rdp"


@pytest.mark.parametrize(
    "content",
    [
        "BACKEND=console $(touch /tmp/lock-pwned)\n",  # not KEY=word
        "BACKEND=both\nSEQ=1\n",
        "BACKEND=rdp\nSEQ=one\n",
        "BACKEND=rdp\nPHASE=whatever\n",
        "BACKEND=rdp\nPATH=/evil\n",  # unknown key
        "SEQ=3\n",  # no backend at all
    ],
)
def test_anything_unreadable_holds(tmp_path: Path, content: str) -> None:
    write_lock(tmp_path, content)
    backend, _, _, why = read_lock(tmp_path)
    assert backend == "hold" and why
    assert not Path("/tmp/lock-pwned").exists()


def test_an_unmounted_lock_directory_holds(tmp_path: Path) -> None:
    backend, _, _, why = read_lock(tmp_path / "not-mounted")
    assert backend == "hold" and "not mounted" in why


def test_nap_wakes_early_when_the_lock_changes(tmp_path: Path) -> None:
    write_lock(tmp_path, "BACKEND=console\nSEQ=1\n")
    env = {"PATH": "/usr/bin:/bin", "LAB_STATE_DIR": str(tmp_path)}
    proc = subprocess.Popen(
        ["bash", "-c", f'source "{RDP_LOOP}"; nap 20'], env=env, stderr=subprocess.PIPE, text=True
    )
    t0 = time.monotonic()
    time.sleep(1.2)
    write_lock(tmp_path, "BACKEND=rdp\nSEQ=2\n")
    _, err = proc.communicate(timeout=10)
    assert time.monotonic() - t0 < 5
    assert "lock changed: waking early" in err


# --- the main loop, with fake binaries -----------------------------------------------------------


@pytest.fixture
def loop_env(tmp_path: Path) -> Iterator[dict[str, str]]:
    bin_dir, state = tmp_path / "bin", tmp_path / "state"
    bin_dir.mkdir()
    state.mkdir()
    fakes = {
        "xdpyinfo": "#!/bin/sh\nexit 0\n",
        "xwininfo": '#!/bin/sh\ncat "$FAKE_XWININFO" 2>/dev/null\n',
        # A client that connects and stays connected: the mark proves a connect was attempted.
        "xfreerdp3": '#!/bin/sh\ncat >/dev/null\necho connect >>"$FAKE_MARK"\nexec sleep 30\n',
    }
    for name, body in fakes.items():
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    yield {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "DISPLAY": ":99",
        "WIN_HOST": "win.test",
        "RDP_USER": "u",
        "RDP_PASSWORD": "p",
        "RDP_CERT_SHA256": "ab",
        "RDP_OVERRIDE_FILE": str(tmp_path / "no-override"),
        "LAB_STATE_DIR": str(state),
        "FAKE_XWININFO": str(tmp_path / "xwininfo.txt"),
        "FAKE_MARK": str(tmp_path / "connects"),
    }


def run_loop(env: dict[str, str], seconds: float, during: object = None) -> tuple[int, str]:
    """Run rdp-loop's main for `seconds`; return (number of connects, log)."""
    proc = subprocess.Popen(
        ["bash", str(RDP_LOOP)],
        env=env,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )
    try:
        if callable(during):
            during()
        time.sleep(seconds)
    finally:
        os.killpg(proc.pid, signal.SIGTERM)
        _, err = proc.communicate(timeout=10)
    mark = Path(env["FAKE_MARK"])
    return (len(mark.read_text().split()) if mark.exists() else 0), err


def test_console_lock_never_connects(loop_env: dict[str, str]) -> None:
    write_lock(Path(loop_env["LAB_STATE_DIR"]), "BACKEND=console\nSEQ=4\nPHASE=switching\n")
    connects, log = run_loop(loop_env, 2.5)
    assert connects == 0
    assert "capture-backend console seq=4: holding" in log


def test_unmounted_lock_never_connects(loop_env: dict[str, str]) -> None:
    loop_env["LAB_STATE_DIR"] = loop_env["LAB_STATE_DIR"] + "-missing"
    connects, log = run_loop(loop_env, 2.0)
    assert connects == 0 and "not mounted" in log


def test_a_moonlight_window_blocks_rdp_even_if_the_lock_says_rdp(loop_env: dict[str, str]) -> None:
    write_lock(Path(loop_env["LAB_STATE_DIR"]), "BACKEND=rdp\nSEQ=5\n")
    Path(loop_env["FAKE_XWININFO"]).write_text(
        '     0x600002 "Moonlight": ("moonlight" "Moonlight")  1280x800+0+0  +0+0\n'
    )
    connects, log = run_loop(loop_env, 2.5)
    assert connects == 0 and "a Moonlight window is on :99" in log


def test_rdp_lock_connects_once(loop_env: dict[str, str]) -> None:
    write_lock(Path(loop_env["LAB_STATE_DIR"]), "BACKEND=rdp\nSEQ=6\n")
    connects, log = run_loop(loop_env, 2.0)
    assert connects == 1 and "connecting to win.test" in log


def test_flipping_the_lock_to_rdp_reconnects_without_waiting_out_the_hold(
    loop_env: dict[str, str],
) -> None:
    state = Path(loop_env["LAB_STATE_DIR"])
    write_lock(state, "BACKEND=console\nSEQ=9\n")

    def flip_later() -> None:
        time.sleep(1.5)
        write_lock(state, "BACKEND=rdp\nSEQ=10\nPHASE=switching\n")

    connects, log = run_loop(loop_env, 2.5, during=flip_later)
    assert connects == 1  # the 30 s hold nap woke on the lock change
    assert "capture-backend rdp seq=10: resuming" in log


# --- parity: rdp-loop.sh's reader and the backend's must never disagree -------------------------

PARITY_CASES = [
    "BACKEND=console\nSEQ=7\nPHASE=switching\nOWNER=capture_backend\n",
    "# c\n\nBACKEND=rdp\nSEQ=8\nSINCE=1759370000\nREASON=to-rdp\n",
    "BACKEND=console $(touch /tmp/lock-pwned)\n",
    "BACKEND=both\nSEQ=1\n",
    "BACKEND=rdp\nSEQ=one\n",
    "BACKEND=rdp\nPHASE=whatever\n",
    "BACKEND=rdp\nPATH=/evil\n",
    "SEQ=3\n",
    "",
]


@pytest.mark.parametrize("content", PARITY_CASES)
def test_bash_and_python_readers_agree(tmp_path: Path, content: str) -> None:
    from poring_backend.capture_lock import read_lock as py_read_lock

    write_lock(tmp_path, content)
    bash_backend, bash_seq, bash_phase, _ = read_lock(tmp_path)
    py = py_read_lock(tmp_path)
    assert bash_backend == py.backend
    if py.backend != "hold":
        assert (int(bash_seq), bash_phase) == (py.seq, py.phase)


def test_python_reader_missing_file_and_unmounted_dir(tmp_path: Path) -> None:
    from poring_backend.capture_lock import read_lock as py_read_lock

    assert py_read_lock(tmp_path).backend == "rdp"
    assert py_read_lock(tmp_path / "nope").backend == "hold"


def test_format_lock_round_trips_and_refuses_what_bash_would_reject(tmp_path: Path) -> None:
    from poring_backend.capture_lock import format_lock

    body = format_lock(
        "console", 4, "switching", owner="capture_backend", since=1, reason="to-console"
    )
    write_lock(tmp_path, body)
    assert read_lock(tmp_path)[:3] == ("console", "4", "switching")
    for bad in (
        {"backend": "both", "seq": 1, "phase": "steady"},
        {"backend": "rdp", "seq": -1, "phase": "steady"},
        {"backend": "rdp", "seq": 1, "phase": "later"},
    ):
        with pytest.raises(ValueError):
            format_lock(owner="t", since=1, reason="r", **bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        format_lock("rdp", 1, "steady", owner="t", since=1, reason="two words")


# --- gamestream-loop.sh: the mirror image -------------------------------------------------------


def lock_functions(script: Path) -> str:
    text = script.read_text()
    start = text.index("# --- capture-backend lock ---")
    end = text.index("# The second interlock")
    return text[start:end].strip()


def test_both_loops_share_one_lock_reader() -> None:
    """The gamestream copy of read_lock/lock_stamp/nap must stay byte-identical to rdp-loop's."""
    assert lock_functions(STREAM_LOOP) == lock_functions(RDP_LOOP)


@pytest.fixture
def stream_env(tmp_path: Path) -> dict[str, str]:
    bin_dir, state, moon = tmp_path / "bin", tmp_path / "state", tmp_path / "moonlight"
    for d in (bin_dir, state, moon):
        d.mkdir()
    fakes = {
        bin_dir / "xdpyinfo": "#!/bin/sh\nexit 0\n",
        bin_dir / "xwininfo": '#!/bin/sh\ncat "$FAKE_XWININFO" 2>/dev/null\n',
        bin_dir / "gamestream-unpack": "#!/bin/sh\nexit 0\n",
        moon / "AppRun": '#!/bin/sh\necho "$*" >>"$FAKE_MARK"\nexec sleep 30\n',
    }
    for path, body in fakes.items():
        path.write_text(body)
        path.chmod(0o755)
    return {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "DISPLAY": ":99",
        "WIN_HOST": "win.test",
        "LAB_STATE_DIR": str(state),
        "MOONLIGHT_DIR": str(moon),
        "FAKE_XWININFO": str(tmp_path / "xwininfo.txt"),
        "FAKE_MARK": str(tmp_path / "streams"),
    }


def run_stream(env: dict[str, str], seconds: float) -> tuple[list[str], str]:
    proc = subprocess.Popen(
        ["bash", str(STREAM_LOOP)],
        env=env,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )
    try:
        time.sleep(seconds)
    finally:
        os.killpg(proc.pid, signal.SIGTERM)
        _, err = proc.communicate(timeout=10)
    mark = Path(env["FAKE_MARK"])
    return (mark.read_text().splitlines() if mark.exists() else []), err


def test_stream_only_under_a_console_lock(stream_env: dict[str, str]) -> None:
    write_lock(Path(stream_env["LAB_STATE_DIR"]), "BACKEND=rdp\nSEQ=3\n")
    streams, log = run_stream(stream_env, 2.0)
    assert streams == [] and "capture-backend rdp seq=3: holding (no stream)" in log


def test_no_lock_file_means_rdp_so_no_stream(stream_env: dict[str, str]) -> None:
    streams, _ = run_stream(stream_env, 1.5)
    assert streams == []


def test_console_lock_streams_once_with_absolute_mouse(stream_env: dict[str, str]) -> None:
    write_lock(Path(stream_env["LAB_STATE_DIR"]), "BACKEND=console\nSEQ=4\nPHASE=steady\n")
    streams, log = run_stream(stream_env, 2.0)
    assert len(streams) == 1
    args = streams[0].split()
    assert args[:3] == ["stream", "win.test", "Desktop"]
    for flag in ("--absolute-mouse", "--game-optimization", "--audio-on-host"):
        assert flag in args
    assert args[args.index("--resolution") + 1] == "1440x900"
    # windowed at the stream's own size (the canvas is larger), then only MOVED to 0,0
    assert args[args.index("--display-mode") + 1] == "windowed"
    assert args[args.index("--video-codec") + 1] == "H.264"
    assert "capture-backend console seq=4: streaming win.test" in log


def test_the_stream_is_the_session_size(stream_env: dict[str, str]) -> None:
    """1:1 means the stream IS the session area: it follows SESSION_SIZE (GAMESTREAM_RESOLUTION
    overrides, for size experiments only)."""
    write_lock(Path(stream_env["LAB_STATE_DIR"]), "BACKEND=console\nSEQ=4\nPHASE=steady\n")
    streams, _ = run_stream({**stream_env, "SESSION_SIZE": "1600x900"}, 1.5)
    args = streams[0].split()
    assert args[args.index("--resolution") + 1] == "1600x900"


def test_the_stream_window_is_moved_to_the_session_origin_never_resized(
    stream_env: dict[str, str], tmp_path: Path
) -> None:
    """ADR-0009 amendment (2026-10-02): Moonlight opens its window at the stream's own size, centred
    on the larger canvas, and the loop MOVES it to 0,0. A resize during Moonlight's renderer set-up
    left it black, so the loop never resizes, and leaves other Moonlight windows where they are."""
    calls, geo = tmp_path / "xdotool.calls", tmp_path / "geo"
    geo.write_text("240 150\n")
    fake = Path(stream_env["PATH"].split(":")[0]) / "xdotool"
    fake.write_text(
        "#!/bin/bash\n"
        f'echo "$*" >>"{calls}"\n'
        'case "$1" in\n'
        "  search) printf '42\\n7\\n' ;;\n"
        "  getwindowgeometry)\n"
        f'    if [[ "$3" == 42 ]]; then read -r x y <"{geo}"; w=1440 h=900;\n'
        "    else x=320 y=300 w=1280 h=600; fi\n"
        "    printf 'WINDOW=%s\\nX=%s\\nY=%s\\nWIDTH=%s\\nHEIGHT=%s\\nSCREEN=0\\n' "
        '"$3" "$x" "$y" "$w" "$h" ;;\n'
        f'  windowmove) echo "$3 $4" >"{geo}" ;;\n'
        "esac\n"
    )
    fake.chmod(0o755)
    write_lock(Path(stream_env["LAB_STATE_DIR"]), "BACKEND=console\nSEQ=4\nPHASE=steady\n")
    streams, log = run_stream(stream_env, 2.0)
    assert len(streams) == 1
    lines = calls.read_text().splitlines()
    assert {line.split()[0] for line in lines} == {"search", "getwindowgeometry", "windowmove"}
    assert [line for line in lines if line.startswith("windowmove")] == ["windowmove 42 0 0"]
    assert "Moonlight window 42: 1440x900+240+150 (stream 1440x900)" in log
    assert "moved the stream window 42 to 0,0" in log
    assert "Moonlight window 42: 1440x900+0+0" in log
    assert "Moonlight window 7: 1280x600+320+300" in log


def test_console_switching_holds_the_stream(stream_env: dict[str, str]) -> None:
    """The session isn't on the console yet during the switch: Sunshine couldn't apply its display
    settings and captured an empty display when the stream started early (2026-10-02)."""
    write_lock(Path(stream_env["LAB_STATE_DIR"]), "BACKEND=console\nSEQ=6\nPHASE=switching\n")
    streams, log = run_stream(stream_env, 2.0)
    assert streams == []
    assert "seq=6: holding (no stream) -- phase switching: the session is not on the console" in log


def test_an_xfreerdp_window_blocks_the_stream(stream_env: dict[str, str]) -> None:
    write_lock(Path(stream_env["LAB_STATE_DIR"]), "BACKEND=console\nSEQ=5\nPHASE=steady\n")
    Path(stream_env["FAKE_XWININFO"]).write_text(
        '     0xc00002 "FreeRDP: 192.168.1.169": ("xfreerdp" "xfreerdp")  1280x800+0+0\n'
    )
    streams, log = run_stream(stream_env, 2.0)
    assert streams == [] and "an xfreerdp window is on :99" in log
