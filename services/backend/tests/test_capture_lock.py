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
