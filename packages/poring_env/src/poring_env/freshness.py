"""Frame freshness: never act on a stale picture (the "never trade on a stale price" rule, Batt
2026-10-04; ADR-0014).

The S2 stream drops about one frame per 10 s upstream of the VM. Each drop freezes the picture until
the next IDR (the host has no reference-frame invalidation). Measured over 52.6 min on 2026-10-04:
frame gaps p50 33 ms, p99 49, p99.9 88; gaps above 150 ms 0.23/min, all 186-239 ms, max 239.
Two ages, two budgets:

* STREAM age = now - the newest bus frame's decode time. Above STREAM_MAX_AGE_MS (150: above every
  normal gap, below every observed freeze) the stream is frozen and nobody may act on it.
* CITED age = now - the decode time of the frame a decision was made on. Its budget
  (CITED_MAX_AGE_MS, 400) is larger: it includes the agent's own inference on a GPU shared with
  Frigate and Ollama.

Releases (key/button up, ReleaseAll) are never refused: a refused release leaves something held.
Both budgets are environment knobs; the recorder marks freeze spans with FREEZE_MS.
"""

import os
from collections.abc import Sequence

from poring_env.clock import monotonic_ns
from poring_env.protocol import InputEvent, Key, MouseButton, ReleaseAll


def _env_ms(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


STREAM_MAX_AGE_MS = _env_ms("STREAM_MAX_AGE_MS", 150.0)
CITED_MAX_AGE_MS = _env_ms("CITED_MAX_AGE_MS", 400.0)
FREEZE_MS = _env_ms("FREEZE_MS", 150.0)


class StaleFrame(RuntimeError):
    """The frame (or the stream) is too old to act on: wait for a newer one."""


def age_ms(t_mono_ns: int, now_ns: int | None = None) -> float:
    return ((monotonic_ns() if now_ns is None else now_ns) - t_mono_ns) / 1e6


def is_release(event: InputEvent) -> bool:
    if isinstance(event, ReleaseAll):
        return True
    return isinstance(event, Key | MouseButton) and event.action == "up"


def presses(events: Sequence[InputEvent]) -> bool:
    """Any event that changes the game (a press, a move, a wheel): what the guard may refuse."""
    return any(not is_release(e) for e in events)


def freeze_spans(times_ns: Sequence[int], threshold_ms: float = FREEZE_MS) -> list[tuple[int, int]]:
    """(start, end) ns of every gap above ``threshold_ms`` between consecutive frame times."""
    ordered = sorted(times_ns)
    limit = threshold_ms * 1e6
    return [(a, b) for a, b in zip(ordered, ordered[1:], strict=False) if b - a > limit]
