"""Stream stalls for /health (the frame-age guard, 2026-10-04; poring_env.freshness).

A thread samples the S2 frame bus's newest frame stamp at 20 Hz (header only: no pixels, no
reader stats) while the console is the backend, and records every STALL: no new frame for longer
than FREEZE_MS. In game the world always animates, so a stall there is a freeze (a dropped frame
waiting for an IDR). A static desktop sends no frames either, hence the neutral name.

It resets when a new writer appears and closes its mapping when the ring goes away, so it never
pins an unlinked ring in the 64 MiB tmpfs (the 2026-10-03 SIGBUS lesson).
"""

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from poring_env.clock import monotonic_ns
from poring_env.framebus import FrameBusError, FrameBusReader
from poring_env.freshness import FREEZE_MS

POLL_S = 0.05


class StallMonitor:
    def __init__(
        self,
        ring: Path,
        console_mode: Callable[[], bool],
        *,
        threshold_ms: float = FREEZE_MS,
        clock: Callable[[], int] = monotonic_ns,
    ) -> None:
        self.ring, self.console_mode, self.threshold_ms, self.clock = (
            ring, console_mode, threshold_ms, clock,
        )  # fmt: skip
        self._reader: FrameBusReader | None = None
        self._lock = threading.Lock()
        self._last: tuple[int, int] | None = None  # (frame_id, t) of the newest frame seen
        self._in_stall = False
        self.stalls = 0
        self.max_stall_ms = 0.0
        self.last_stall_ms = 0.0
        self.last_stall_wall: float | None = None
        self.age_ms: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # --- one sample (tests call it directly) -----------------------------------------------------

    def _close(self) -> None:
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        self._last, self._in_stall, self.age_ms = None, False, None

    def sample(self) -> None:
        if not self.console_mode() or not self.ring.exists():
            with self._lock:
                self._close()
            return
        with self._lock:
            try:
                if self._reader is None:
                    self._reader = FrameBusReader(self.ring, "stall-monitor")
                elif self._reader.replaced():
                    self._close()  # a new writer numbers frames anew: start over
                    self._reader = FrameBusReader(self.ring, "stall-monitor")
                stamp = self._reader.latest_stamp()
            except FrameBusError:
                self._close()
                return
            if stamp is None:
                return
            now = self.clock()
            if self._last is not None and stamp[0] != self._last[0]:
                if self._in_stall:  # the stall ended with this frame: its gap is the stall
                    gap = (stamp[1] - self._last[1]) / 1e6
                    self.stalls += 1
                    self.last_stall_ms = gap
                    self.max_stall_ms = max(self.max_stall_ms, gap)
                    self.last_stall_wall = time.time()
                self._in_stall = False
            self._last = stamp
            self.age_ms = (now - stamp[1]) / 1e6
            if self.age_ms > self.threshold_ms:
                self._in_stall = True

    # --- the thread ------------------------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.wait(POLL_S):
            try:
                self.sample()
            except Exception:  # noqa: BLE001 -- a monitor never takes the backend down
                with self._lock:
                    self._close()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="stall-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        with self._lock:
            self._close()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "frame_age_ms": None if self.age_ms is None else round(self.age_ms, 1),
                "stalled_now": self._in_stall,
                "threshold_ms": self.threshold_ms,
                "stalls": self.stalls,
                "max_stall_ms": round(self.max_stall_ms, 1),
                "last_stall_ms": round(self.last_stall_ms, 1),
                "last_stall_at": self.last_stall_wall,
            }
