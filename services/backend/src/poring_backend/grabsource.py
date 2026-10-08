"""Where the lab's measurement and screenshot helpers grab frames, inside the backend container
(the bench's packet->frame / key->paint / delivery-fps watchers, ro_agent's screen helper).

ONE rule, the backend's own (capture_select.py): the capture-backend lock says ``console`` AND the
S2 frame bus has a live writer (heartbeat < 2 s) -> the bus; it says ``rdp`` AND the RDP frame bus
(rdp_bus.py: the backend's one X grabber, Batt 2026-10-08) has a live writer -> that ring; else X
(:99, ``mss``, imported only then). In V3b (S2, PAINT=bus) nothing is painted into X, so an X
grab there would measure a black window; on the bus each frame carries the writer's
decode-complete time, the moment the lab could first use it (an X grab's time, and an RDP bus
frame's, is the moment of the grab).

``frames()`` yields EVERY new bus frame once (plus ``None`` ticks while none arrives, so per-second
counters keep counting); in X mode it grab-loops. Every item says which source it came from, and a
consumer prints a ``#source=...`` line when it changes, so a run that fell back to X shows it.
"""

import os
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from poring_backend.capture_lock import read_lock
from poring_env.framebus import FrameBusError, FrameBusReader

STALE_S = 2.0
RECHECK_S = 0.5  # how often the source decision is re-read (the lock file, the heartbeat)
Region = tuple[int, int, int, int]  # x, y, w, h in screen pixels (the session is at 0,0)
Grab = tuple[int, NDArray[np.uint8], str]  # (t_mono_ns, BGRA crop, "bus" | "x11")
XGrab = Callable[[Region], tuple[int, NDArray[np.uint8]]]


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))


class GrabSource:
    def __init__(
        self,
        display: str = ":99",
        *,
        lab_state: Path | None = None,
        ring: Path | None = None,
        rdp_ring: Path | None = None,
        stale_s: float = STALE_S,
        x_grab: XGrab | None = None,
    ) -> None:
        self.display = display
        self.lab_state = lab_state or _env_path("GRAB_LAB_STATE", "/lab-state")
        self.ring = ring or _env_path("GRAB_FRAMEBUS", "/framebus/ring")
        self.rdp_ring = rdp_ring or _env_path("GRAB_RDP_RING", "/dev/shm/rdp-ring")
        self._bus_path: Path | None = None  # the ring self._bus is open on
        self.stale_s = stale_s
        self._x_grab = x_grab
        self._sct: object | None = None
        self._bus: FrameBusReader | None = None
        self._live = False
        self._checked = 0.0
        self.last_frame_id = -1  # the bus writer's frame_id of the last grab; -1 = an X grab

    # --- the decision -----------------------------------------------------------------------------

    def _bus_live(self) -> FrameBusReader | None:
        now = time.monotonic()
        if now - self._checked < RECHECK_S:
            return self._bus if self._live else None
        self._checked = now
        self._live = False
        backend = read_lock(self.lab_state).backend
        path = {"console": self.ring, "rdp": self.rdp_ring}.get(backend)
        if path is None or not path.exists():
            return None
        if self._bus is not None and self._bus_path != path:  # the lock flipped: the other ring
            self._bus.close()
            self._bus = None
        try:
            if self._bus is None:
                self._bus, self._bus_path = FrameBusReader(path, "grabsource"), path
            else:
                self._bus.reopen_if_replaced()
            self._live = self._bus.writer().heartbeat_age_s < self.stale_s
        except FrameBusError:
            self._bus = None
        return self._bus if self._live else None

    # --- X ----------------------------------------------------------------------------------------

    def _x(self, region: Region) -> tuple[int, NDArray[np.uint8]]:
        if self._x_grab is not None:
            return self._x_grab(region)
        if self._sct is None:
            import mss  # only when X is the source: the bus path needs no display

            self._sct = mss.MSS(display=self.display)
        x, y, w, h = region
        t = time.monotonic_ns()
        shot = self._sct.grab({"left": x, "top": y, "width": w, "height": h})  # type: ignore[attr-defined]
        img = np.frombuffer(shot.raw, np.uint8).reshape(shot.height, shot.width, 4)
        return t, img

    # --- grabs ------------------------------------------------------------------------------------

    @staticmethod
    def _crop(pixels: NDArray[np.uint8], region: Region) -> NDArray[np.uint8] | None:
        x, y, w, h = region
        if y + h > pixels.shape[0] or x + w > pixels.shape[1]:
            return None
        return pixels[y : y + h, x : x + w]

    def grab(self, region: Region) -> Grab:
        """The newest picture of ``region`` (a bus frame may repeat)."""
        bus = self._bus_live()
        if bus is not None:
            got = bus.read()
            crop = self._crop(got.to_numpy(), region) if got is not None else None
            if got is not None and crop is not None:
                self.last_frame_id = got.frame_id
                return got.t_mono_ns, crop, "bus"
        t, img = self._x(region)
        self.last_frame_id = -1
        return t, img, "x11"

    def frames(
        self,
        region: Region,
        seconds: float,
        *,
        poll_s: float = 0.002,
        tick_s: float = 0.1,
        x_period_s: float = 0.004,
    ) -> Iterator[tuple[int, NDArray[np.uint8] | None, str]]:
        """Bus: every NEW frame once, and a ``None`` image every ``tick_s`` while none arrives.
        X: a grab every ``x_period_s``."""
        end = time.monotonic() + seconds
        last_id, reopens, last_yield = -1, -1, time.monotonic()
        while time.monotonic() < end:
            bus = self._bus_live()
            if bus is None:
                t, img = self._x(region)
                yield t, img, "x11"
                time.sleep(x_period_s)
                continue
            if bus.stats.reopens != reopens:  # a new writer numbers its frames from 1 again
                reopens, last_id = bus.stats.reopens, -1
            got = bus.read(after=last_id)
            crop = self._crop(got.to_numpy(), region) if got is not None else None
            if got is not None and crop is not None:
                last_id = got.frame_id
                last_yield = time.monotonic()
                yield got.t_mono_ns, crop, "bus"
                continue
            if time.monotonic() - last_yield >= tick_s:
                last_yield = time.monotonic()
                yield time.monotonic_ns(), None, "bus"
            time.sleep(poll_s)

    def close(self) -> None:
        if self._bus is not None:
            self._bus.close()
            self._bus = None
