"""Stream-start preconditions: "one lab client at a time" ENFORCED, not just documented.

V3 shares the lab client's identity (Batt, 2026-10-03), so before it ever sends /launch or /resume:
  - the capture-backend lock says console/steady (the session is on the console, RDP holds);
  - no xfreerdp window is on the display (rdp-loop's own interlock, mirrored);
  - no Moonlight-qt process runs in this container (never two lab clients).
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

LOCK_LINE = re.compile(r"^([A-Z_]+)=([A-Za-z0-9_.:-]*)$")
MOONLIGHT_COMMS = re.compile(r"^(moonlight|Moonlight.*|AppRun.*)$")


def read_lock(state_dir: Path) -> dict[str, str]:
    """KEY=word lines of state_dir/capture-backend; {} when missing or malformed (fail closed)."""
    try:
        text = (state_dir / "capture-backend").read_text()
    except OSError:
        return {}
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        m = LOCK_LINE.match(line)
        if not m:
            return {}
        out[m.group(1)] = m.group(2)
    return out


def moonlight_qt_running(proc: Path = Path("/proc")) -> bool:
    for p in proc.glob("[0-9]*"):
        try:
            comm = (p / "comm").read_text().strip()
        except OSError:
            continue
        if MOONLIGHT_COMMS.match(comm):
            return True
    return False


def xfreerdp_window_present(display: str) -> bool:
    try:
        tree = subprocess.run(
            ["xwininfo", "-root", "-tree", "-display", display],
            capture_output=True, text=True, timeout=10, check=False,
        ).stdout  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return True  # can't tell: fail closed
    return re.search(r'\("xfreerdp"', tree, flags=re.I) is not None


def may_stream(state_dir: Path, display: str) -> tuple[bool, str]:
    lock = read_lock(state_dir)
    if lock.get("BACKEND") != "console" or lock.get("PHASE") != "steady":
        return (
            False,
            f"lock is {lock.get('BACKEND', '?')}/{lock.get('PHASE', '?')}, not console/steady",
        )
    if xfreerdp_window_present(display):
        return False, "an xfreerdp window is on the display"
    if moonlight_qt_running():
        return False, "a Moonlight-qt process runs in this container (never two lab clients)"
    return True, "console/steady, no RDP window, no other lab client"


def state_dir() -> Path:
    return Path(os.environ.get("LAB_STATE_DIR", "/lab-state"))
