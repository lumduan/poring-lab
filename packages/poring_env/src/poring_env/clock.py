"""Monotonic time and frame numbering shared by every producer in the pipeline."""

import threading
import time


def monotonic_ns() -> int:
    """CLOCK_MONOTONIC in nanoseconds.

    Docker does not put containers in a separate time namespace, so every container on the host
    reads the same clock: a backend timestamp and a vision timestamp are directly comparable.
    """
    return time.monotonic_ns()


class FrameCounter:
    """Thread-safe, strictly increasing frame ids starting at ``start``."""

    def __init__(self, start: int = 0) -> None:
        self._next = start
        self._lock = threading.Lock()

    def next(self) -> int:
        with self._lock:
            value = self._next
            self._next += 1
            return value

    @property
    def last(self) -> int:
        """The most recently issued id, or ``start - 1`` before the first call."""
        with self._lock:
            return self._next - 1
