"""Which frames the backend streams to the console (S2 step 4 wiring; docs/s2-plan.md).

RDP mode, and the console mode of the Moonlight-qt / V3-mirror era: X11 screen grabs, as always.
Console mode WITH a live S2 writer on the frame bus: the bus -- the same decoded frames (and the
same ``frame_id`` / ``t_mono_ns``) the bot reads, never an X mirror. A bus whose writer stops
heart-beating falls back to X11 on the next grab, and comes back by itself.

Inert until compose mounts the ``framebus`` volume: without ``/framebus/ring`` nothing changes.
"""

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from poring_env.bus_source import BusFrameSource
from poring_env.env import FrameSource
from poring_env.frame import Frame
from poring_env.framebus import FrameBusError, FrameBusReader, WriterStatus

STALE_S = 2.0  # a writer heartbeat older than this is not live


class CaptureSelector:
    """The hub's one FrameSource. Called only on the capture thread (grab/close); ``snapshot``
    (for /health) reads values the capture thread cached, never the mmap."""

    def __init__(
        self,
        x11_factory: Callable[[], FrameSource],
        *,
        bus_path: Path,
        console_mode: Callable[[], bool],
        console_fps: float,
        stale_s: float = STALE_S,
    ) -> None:
        self._x11_factory = x11_factory
        self.bus_path = bus_path
        self._console_mode = console_mode
        self.console_fps = console_fps
        self.stale_s = stale_s
        self._x11: FrameSource | None = None
        self._bus: BusFrameSource | None = None
        self._probe: FrameBusReader | None = None
        self._writer: tuple[WriterStatus, float] | None = None
        self.writer_fps = 0.0
        self.active = "x11"
        self.switches = 0
        self.probe_errors = 0

    def _bus_live(self) -> bool:
        """console mode + a ring + a writer that heart-beat within stale_s (cached for /health)."""
        if not self._console_mode() or not os.path.exists(self.bus_path):
            self._writer = None
            return False
        try:
            if self._probe is None:
                self._probe = FrameBusReader(self.bus_path, "probe")
            else:
                self._probe.reopen_if_replaced()
            status = self._probe.writer()
        except FrameBusError:
            self.probe_errors += 1
            self._close_probe()
            return False
        now = time.monotonic()
        if self._writer is not None and now > self._writer[1]:
            before, seen = self._writer
            if status.pid == before.pid and status.frames_written >= before.frames_written:
                instant = (status.frames_written - before.frames_written) / (now - seen)
                old = self.writer_fps
                self.writer_fps = instant if not old else 0.8 * old + 0.2 * instant
        self._writer = (status, now)
        return status.heartbeat_age_s < self.stale_s

    def _close_probe(self) -> None:
        if self._probe is not None:
            self._probe.close()
            self._probe = None
        self._writer = None

    @property
    def self_paced(self) -> bool:
        """The bus paces its own reads (a grab waits for a newer frame, capped at CONSOLE_FPS):
        the hub must not wait for X DAMAGE then -- nothing paints Xvfb on the S2 path, so damage
        mode fell back to its 1 s keepalive (the console's 1 fps, 2026-10-03)."""
        return self.active == "bus"

    def grab(self) -> Frame:
        want = "bus" if self._bus_live() else "x11"
        if want != self.active:
            self.switches += 1
            self.active = want
            self._close_sources()
        if want == "bus":
            if self._bus is None:
                self._bus = BusFrameSource(
                    self.bus_path, "stream", repeat_on_timeout=True, max_fps=self.console_fps
                )
            return self._bus.grab()
        if self._x11 is None:
            self._x11 = self._x11_factory()
        return self._x11.grab()

    def _close_sources(self) -> None:
        for source in (self._x11, self._bus):
            if source is not None:
                source.close()
        self._x11 = None
        self._bus = None

    def close(self) -> None:
        self._close_sources()
        self._close_probe()

    def snapshot(self) -> dict[str, Any]:
        writer: dict[str, Any] | None = None
        if self._writer is not None:
            status, seen = self._writer
            writer = {
                "pid": status.pid,
                "heartbeat_age_s": round(status.heartbeat_age_s + time.monotonic() - seen, 2),
                "frames_written": status.frames_written,
                "latest_frame_id": status.latest_frame_id,
                "fps": round(self.writer_fps, 1),
                "decode_ms_p50": status.decode_p50_us / 1000,
                "decode_ms_p95": status.decode_p95_us / 1000,
            }
        bus = self._bus
        return {
            "path": str(self.bus_path),
            "active": self.active,
            "console_fps": self.console_fps,
            "switches": self.switches,
            "probe_errors": self.probe_errors,
            "writer": writer,
            "consumers": {"stream": bus.snapshot() if bus is not None else {"open": False}},
        }
