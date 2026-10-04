"""The capture-backend lock (ADR-0009): who owns the ONE Windows session, `rdp` or `console`.

The lock is a small KEY=word file, ``<lab-state>/capture-backend``, written only by
``scripts/capture_backend.py`` on the host (atomic rename) and bind-mounted read-only as a
directory into desktop, backend and gamestream. This module is the Python reader and writer-side
formatter; ``services/desktop/bin/rdp-loop.sh`` (``read_lock``) applies the same rules in bash, and
``tests/test_capture_lock.py`` checks that both agree.

Rules (fail closed):
  * lock directory missing (not mounted)          -> hold
  * directory present, file absent                 -> rdp  (the lab before the lock existed)
  * any malformed line, unknown key or bad value   -> hold
"""

import re
from pathlib import Path

from poring_env.protocol import CaptureBackend, CleanRoom

LOCK_NAME = "capture-backend"
KEYS = ("BACKEND", "SEQ", "PHASE", "OWNER", "SINCE", "REASON")
_LINE = re.compile(r"^([A-Z_]+)=([A-Za-z0-9_.:-]*)$")
_WORD = re.compile(r"^[A-Za-z0-9_.:-]*$")


def _hold(reason: str) -> CaptureBackend:
    return CaptureBackend(backend="hold", reason=reason)


def parse_lock(text: str) -> CaptureBackend:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        match = _LINE.match(line)
        if match is None:
            return _hold(f"malformed lock line: {line[:60]}")
        key, value = match.groups()
        if key not in KEYS:
            return _hold(f"unknown lock key {key}")
        values[key] = value
    backend = values.get("BACKEND", "")
    if backend not in ("rdp", "console"):
        return _hold(f"BACKEND={backend!r} is not rdp|console")
    seq = values.get("SEQ", "0")
    if not seq.isdigit():
        return _hold(f"SEQ={seq!r} is not a number")
    phase = values.get("PHASE", "steady")
    if phase not in ("steady", "switching"):
        return _hold(f"PHASE={phase!r} is not steady|switching")
    since = values.get("SINCE", "")
    return CaptureBackend(
        backend="rdp" if backend == "rdp" else "console",
        seq=int(seq),
        phase="steady" if phase == "steady" else "switching",
        since=int(since) if since.isdigit() else None,
        owner=values.get("OWNER") or None,
        reason=values.get("REASON") or None,
    )


def read_lock(directory: Path) -> CaptureBackend:
    if not directory.is_dir():
        return _hold(f"lock directory {directory} is not mounted")
    try:
        text = (directory / LOCK_NAME).read_text(encoding="ascii")
    except FileNotFoundError:
        return CaptureBackend(backend="rdp", phase="steady", reason="no lock file: default rdp")
    except (OSError, UnicodeDecodeError) as exc:
        return _hold(f"lock unreadable: {type(exc).__name__}")
    return parse_lock(text)


def format_lock(backend: str, seq: int, phase: str, *, owner: str, since: int, reason: str) -> str:
    """The file body. Refuses anything rdp-loop.sh's reader would reject (so a writer bug can never
    produce a lock that holds both clients by accident)."""
    if backend not in ("rdp", "console") or phase not in ("steady", "switching") or seq < 0:
        raise ValueError(f"bad lock: {backend=} {seq=} {phase=}")
    for name, value in (("owner", owner), ("reason", reason)):
        if not _WORD.match(value):
            raise ValueError(f"{name} must be a single word of [A-Za-z0-9_.:-]: {value!r}")
    body = (
        f"BACKEND={backend}\nSEQ={seq}\nPHASE={phase}\nOWNER={owner}\nSINCE={since}\n"
        f"REASON={reason}\n"
    )
    assert parse_lock(body).backend == backend
    return body


# --- alarms (2026-10-04): the watchdog is watched -------------------------------------------------
# ``<lab-state>/cleanroom-alarm``: ALARM / SINCE, written only by capture_backend.py `alarm` (called
# by cleanroom.py's guard timer) and removed by `alarm --clear`. The console shows it RED.
ALARM_NAME = "cleanroom-alarm"
ALARMS = ("watchdog_down",)  # the whitelist: anything else in the file is ignored


def format_alarm(name: str, since: int) -> str:
    if name not in ALARMS:
        raise ValueError(f"unknown alarm {name!r} (one of {ALARMS})")
    return f"ALARM={name}\nSINCE={int(since)}\n"


def parse_alarms(text: str) -> list[str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = _LINE.match(line)
        if match is None:
            return []
        values[match.group(1)] = match.group(2)
    name = values.get("ALARM", "")
    return [name] if name in ALARMS else []


def read_alarms(directory: Path) -> list[str]:
    try:
        text = (directory / ALARM_NAME).read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError):
        return []
    return parse_alarms(text)


# --- the environment interlock's operator window (ADR-0016, 2026-10-04) ---------------------------
# ``<lab-state>/interlock-window``: WINDOW (login|desktop) / OPENED / UNTIL / SEQ / REASON, written
# only by capture_backend.py window (a host tool; the agent channel cannot reach state/). Honoured
# only while it is younger than UNTIL, at most WINDOW_MAX_S long, and for the lock SEQ it was
# opened under -- any handover ends it. Anything malformed is no window (fail closed).

WINDOW_NAME = "interlock-window"
WINDOW_KINDS = ("login", "desktop")
WINDOW_MAX_S = 120


def format_window(kind: str, opened: int, until: int, seq: int, reason: str) -> str:
    if kind not in WINDOW_KINDS:
        raise ValueError(f"unknown window {kind!r} (one of {WINDOW_KINDS})")
    if not 0 < until - opened <= WINDOW_MAX_S:
        raise ValueError(f"a window lasts 1..{WINDOW_MAX_S} s")
    if not _WORD.match(reason) or not reason:
        raise ValueError("reason: one word")
    return f"WINDOW={kind}\nOPENED={opened}\nUNTIL={until}\nSEQ={seq}\nREASON={reason}\n"


def parse_window(
    text: str, lock: CaptureBackend, now: float, max_s: float = WINDOW_MAX_S
) -> tuple[str, float, float, str] | None:
    """(kind, until, seconds left, reason) of a window that is open NOW, else None."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = _LINE.match(line)
        if match is None:
            return None
        values[match.group(1)] = match.group(2)
    kind = values.get("WINDOW", "")
    try:
        opened, until, seq = int(values["OPENED"]), int(values["UNTIL"]), int(values["SEQ"])
    except (KeyError, ValueError):
        return None
    if kind not in WINDOW_KINDS or not 0 < until - opened <= min(max_s, WINDOW_MAX_S):
        return None
    if seq != lock.seq or lock.backend not in ("rdp", "console"):
        return None
    # A desktop window may span capture_backend's OWN handover (it types tscon into its shell
    # after moving the lock to switching, and re-opens the window for the new SEQ); nothing else.
    if lock.phase != "steady" and not (kind == "desktop" and lock.phase == "switching"):
        return None
    if not opened - 5 <= now < until:  # (a little slack for the two clocks' read order)
        return None
    return kind, float(until), until - now, values.get("REASON", "")


def read_window(
    directory: Path, lock: CaptureBackend, now: float, max_s: float = WINDOW_MAX_S
) -> tuple[str, float, float, str] | None:
    try:
        text = (directory / WINDOW_NAME).read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError):
        return None
    return parse_window(text, lock, now, max_s)


# --- the clean room's status (ADR-0009; Batt, 2026-10-03) ----------------------------------------
# ``<lab-state>/cleanroom``: VARIANT / BOX_UNTIL / HARD_CAP, written only by capture_backend.py
# (to-console --cleanroom, stream --variant) and removed by its to-rdp. Shown to the console; it
# never gates anything, so a bad file is simply ignored (None), unlike the lock.

CLEANROOM_NAME = "cleanroom"
CLEANROOM_KEYS = ("VARIANT", "BOX_UNTIL", "HARD_CAP")
VARIANTS = ("V1", "V1gdb", "V2", "V3", "V3b", "S2")


def parse_cleanroom(text: str, lock: CaptureBackend, now: float) -> CleanRoom | None:
    """The clean room's status, or None unless the lock is console + REASON cleanroom*."""
    if lock.backend != "console" or not (lock.reason or "").startswith("cleanroom"):
        return None
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = _LINE.match(line)
        if match is None or match.group(1) not in CLEANROOM_KEYS:
            return None
        values[match.group(1)] = match.group(2)
    variant = values.get("VARIANT", "")
    if variant not in (*VARIANTS, ""):
        return None

    def left(key: str) -> int | None:
        raw = values.get(key, "")
        if not raw.isdigit():
            return None
        return max(0, int(int(raw) - now))

    return CleanRoom(
        variant=variant or None,  # type: ignore[arg-type]  # checked against VARIANTS above
        streaming=lock.phase == "steady",
        box_left_s=left("BOX_UNTIL"),
        hard_cap_left_s=left("HARD_CAP"),
    )


def read_cleanroom(directory: Path, lock: CaptureBackend, now: float) -> CleanRoom | None:
    try:
        text = (directory / CLEANROOM_NAME).read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError):
        return None
    return parse_cleanroom(text, lock, now)


def format_cleanroom(variant: str, box_until: int | None, hard_cap: int | None) -> str:
    if variant not in (*VARIANTS, ""):
        raise ValueError(f"bad clean-room variant {variant!r}")
    box = "" if box_until is None else str(int(box_until))
    cap = "" if hard_cap is None else str(int(hard_cap))
    return f"VARIANT={variant}\nBOX_UNTIL={box}\nHARD_CAP={cap}\n"
