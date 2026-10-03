"""ASSIST across a GUARDED backend restart (ADR-0002 amendment, Batt 2026-10-03).

The mux boots in HUMAN (ADR-0002 decision 2). One narrow exception: ``scripts/guarded_build.py
restart:backend`` (the dev-mode way to apply backend code) reads ``/health`` first and, ONLY if the
mode is ASSIST, writes ``<lab-state>/mux-restore``:

    MODE=ASSIST
    SEQ=<the capture-backend lock's SEQ>
    WRITTEN=<unix time>
    OWNER=guarded_build

The backend honours it at boot only if ALL of these hold, and otherwise boots HUMAN:
  * every key present, nothing else, KEY=word lines;
  * MODE is exactly ASSIST (BOT is never restored -- the parser has no other value);
  * OWNER is guarded_build;
  * written at most MAX_AGE_S ago (and not in the future beyond a little clock slack);
  * SEQ equals the lock's SEQ now (no handover since), and the lock is not hold.
guarded_build removes the file as soon as the restarted backend answers /health, so a crash or an
unplanned restart afterwards finds no marker and boots HUMAN. The backend's mount is read-only: it
never writes or removes the marker itself.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from poring_env.protocol import CaptureBackend

RESTORE_NAME = "mux-restore"
KEYS = ("MODE", "SEQ", "WRITTEN", "OWNER")
OWNER = "guarded_build"
MAX_AGE_S = 120
FUTURE_SLACK_S = 5
_LINE = re.compile(r"^([A-Z_]+)=([A-Za-z0-9_.:-]*)$")


@dataclass(frozen=True)
class Verdict:
    restore: bool
    why: str


def judge(text: str | None, lock: CaptureBackend, now: float) -> Verdict:
    if text is None:
        return Verdict(False, "no marker")
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = _LINE.match(line)
        if match is None or match.group(1) not in KEYS or match.group(1) in values:
            return Verdict(False, "malformed marker")
        values[match.group(1)] = match.group(2)
    if set(values) != set(KEYS):
        return Verdict(False, "incomplete marker")
    if values["MODE"] != "ASSIST":
        return Verdict(False, f"MODE={values['MODE']} is never restored")
    if values["OWNER"] != OWNER:
        return Verdict(False, f"OWNER={values['OWNER']} is not {OWNER}")
    if not values["WRITTEN"].isdigit() or not values["SEQ"].isdigit():
        return Verdict(False, "malformed marker")
    age = now - int(values["WRITTEN"])
    if not -FUTURE_SLACK_S <= age <= MAX_AGE_S:
        return Verdict(False, f"marker is {age:.0f} s old (limit {MAX_AGE_S} s)")
    if lock.backend == "hold":
        return Verdict(False, "the capture-backend lock is hold")
    if int(values["SEQ"]) != lock.seq:
        return Verdict(False, f"lock seq {lock.seq} != marker seq {values['SEQ']} (a handover)")
    return Verdict(True, f"guarded restart {age:.0f} s ago, lock seq {lock.seq} unchanged")


def read_verdict(directory: Path, lock: CaptureBackend, now: float) -> Verdict:
    try:
        text: str | None = (directory / RESTORE_NAME).read_text(encoding="ascii")
    except FileNotFoundError:
        text = None
    except (OSError, UnicodeDecodeError):
        return Verdict(False, "marker unreadable")
    return judge(text, lock, now)


def format_marker(seq: int, written: int) -> str:
    """The marker guarded_build writes (ASSIST only: there is no parameter for the mode)."""
    if seq < 0 or written <= 0:
        raise ValueError(f"bad marker: {seq=} {written=}")
    return f"MODE=ASSIST\nSEQ={seq}\nWRITTEN={written}\nOWNER={OWNER}\n"
