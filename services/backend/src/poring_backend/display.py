"""Black-screen detector for the game window: pixels only, never packets.

After an RDP reconnect the RO client can lose its Direct3D device and keep presenting black frames
while Windows, the taskbar and the RDP session all look healthy (seen 2026-09-30). Nothing else in
the lab notices, so a long run would record hours of black.

The detector samples the frames the capture loop already grabs (on the capture thread). While no
console is watching, the capture loop is stopped, so ``AppState`` grabs one frame a second for it:
it is never blind. ``black`` means at least ``BLACK_FRACTION`` of the sampled pixels inside
``GAME_REGION`` have a luminance below ``DARK_LUMA``, continuously for ``BLACK_HOLD_S``. A scene
that is merely dark (night maps, a loading screen) keeps some UI pixels lit and stays ``ok``.

RDP reconnects come from the ``rdp_window_present`` poll: the xfreerdp window disappearing and
coming back is one reconnect (``rdp-loop.sh`` restarted the session).
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from poring_env.clock import monotonic_ns
from poring_env.frame import Frame

DARK_LUMA = 10
BLACK_FRACTION = 0.98
STRIDE = 4  # every 4th pixel in each direction: 1/16 of the region is plenty for "all black"
ANALYZE_EVERY_NS = 500_000_000  # the stream may grab at 60 fps; two samples a second suffice
STALE_NS = 5_000_000_000  # no sample this recent -> "unknown"

DisplayState = Literal["unknown", "ok", "black"]


@dataclass(frozen=True)
class Region:
    """The game's client area in desktop pixels (GAME_REGION="x,y,w,h")."""

    x: int
    y: int
    w: int
    h: int

    @classmethod
    def parse(cls, text: str) -> "Region | None":
        """``""`` -> None (the whole frame). Raises ValueError on anything malformed."""
        text = text.strip()
        if not text:
            return None
        parts = [int(p) for p in text.split(",")]
        if len(parts) != 4 or parts[0] < 0 or parts[1] < 0 or parts[2] <= 0 or parts[3] <= 0:
            raise ValueError(f"GAME_REGION must be x,y,w,h with w,h > 0, got {text!r}")
        return cls(*parts)

    def __str__(self) -> str:
        return f"{self.x},{self.y},{self.w},{self.h}"


def measure(frame: Frame, region: Region | None) -> tuple[float, float] | None:
    """(mean luminance, dark-pixel fraction) of the sampled region, or None if the region lies
    outside the frame. Luminance is BT.601 in integer form, on BGRA."""
    pixels = frame.to_numpy()
    if region is not None:
        pixels = pixels[region.y : region.y + region.h, region.x : region.x + region.w]
    sample = pixels[::STRIDE, ::STRIDE, :3].astype(np.uint16)
    if sample.size == 0:
        return None
    luma = (sample[..., 0] * 29 + sample[..., 1] * 150 + sample[..., 2] * 77) >> 8
    return float(luma.mean()), float((luma < DARK_LUMA).mean())


class DisplayWatch:
    """``observe`` runs on the capture thread; everything else on the event loop."""

    def __init__(
        self,
        region: Region | None,
        *,
        hold_s: float,
        clock: Callable[[], int] = monotonic_ns,
    ) -> None:
        self.region = region
        self.hold_ns = int(hold_s * 1e9)
        self._clock = clock
        self._lock = threading.Lock()
        self._last_analyzed_ns: int | None = None
        self._last_sample_ns: int | None = None
        self._dark_since_ns: int | None = None
        self.luminance: float | None = None
        self.dark_fraction: float | None = None
        self.region_outside_frame = False
        self.state: DisplayState = "unknown"
        self.state_since_ns = clock()
        self.blackouts = 0
        self._rdp_seen = False
        self._rdp_present: bool | None = None
        self._rdp_lost_ns: int | None = None
        self.rdp_reconnects = 0
        self.last_reconnect_ns: int | None = None
        self.last_reconnect_gap_s: float | None = None

    # --- capture thread ---------------------------------------------------------------------------

    def observe(self, frame: Frame) -> None:
        t = frame.t_capture_ns
        with self._lock:
            last = self._last_analyzed_ns
            if last is not None and t - last < ANALYZE_EVERY_NS:
                return
            self._last_analyzed_ns = t
        got = measure(frame, self.region)
        with self._lock:
            if got is None:
                self.region_outside_frame = True
                return
            self.region_outside_frame = False
            self.luminance, self.dark_fraction = got
            self._last_sample_ns = t
            if got[1] >= BLACK_FRACTION:
                if self._dark_since_ns is None:
                    self._dark_since_ns = t
            else:
                self._dark_since_ns = None

    # --- event loop -------------------------------------------------------------------------------

    def needs_sample(self, now: int) -> bool:
        """True when no frame was analyzed in the last second (no console: grab one ourselves)."""
        with self._lock:
            last = self._last_analyzed_ns
        return last is None or now - last >= 1_000_000_000

    def evaluate(self, now: int | None = None) -> DisplayState:
        now = self._clock() if now is None else now
        with self._lock:
            sample, dark_since = self._last_sample_ns, self._dark_since_ns
        state: DisplayState
        if sample is None or now - sample > STALE_NS:
            state = "unknown"
        elif dark_since is not None and sample - dark_since >= self.hold_ns:
            state = "black"
        else:
            state = "ok"
        if state != self.state:
            if state == "black":
                self.blackouts += 1
            self.state, self.state_since_ns = state, now
        return state

    def rdp(self, present: bool | None, now: int | None = None) -> None:
        """Feed the xfreerdp-window poll: gone then back = one reconnect."""
        now = self._clock() if now is None else now
        if present is True:
            if self._rdp_seen and self._rdp_present is not True:
                self.rdp_reconnects += 1
                self.last_reconnect_ns = now
                lost = self._rdp_lost_ns
                self.last_reconnect_gap_s = None if lost is None else round((now - lost) / 1e9, 1)
            self._rdp_seen = True
        elif present is False and self._rdp_present is True:
            self._rdp_lost_ns = now
        self._rdp_present = present

    @property
    def black(self) -> bool | None:
        return None if self.state == "unknown" else self.state == "black"

    def snapshot(self, now: int | None = None) -> dict[str, Any]:
        now = self._clock() if now is None else now
        return {
            "state": self.state,
            "since_s": round((now - self.state_since_ns) / 1e9, 1),
            "luminance": None if self.luminance is None else round(self.luminance, 1),
            "dark_fraction": None if self.dark_fraction is None else round(self.dark_fraction, 3),
            "region": str(self.region) if self.region else "full_frame",
            "region_outside_frame": self.region_outside_frame,
            "hold_s": self.hold_ns / 1e9,
            "blackouts": self.blackouts,
            "rdp_reconnects": self.rdp_reconnects,
            "last_reconnect_s_ago": (
                None
                if self.last_reconnect_ns is None
                else round((now - self.last_reconnect_ns) / 1e9, 1)
            ),
            "last_reconnect_gap_s": self.last_reconnect_gap_s,
        }
