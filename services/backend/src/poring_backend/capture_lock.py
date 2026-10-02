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

from poring_env.protocol import CaptureBackend

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
