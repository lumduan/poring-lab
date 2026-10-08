"""The RDP frame bus (Batt, 2026-10-08): ONE X grabber fans the same frame out to every consumer on
the RDP path. That is the frame-bus pattern S2 already uses (poring_env.framebus): one writer, any
number of readers, each frame carrying its own ``frame_id`` and capture time.

Why: on RDP the console stream, the walk rule's reads, the demo recorder and the route preview each
grabbed X themselves. They contended on the one Xvfb (the preview managed ~8 Hz, 2026-10-08), and
none of them saw the same frame as another. Now:
- this writer grabs the whole session when XDamage says it changed (at most MAX_FPS), plus a
  KEEPALIVE_S frame while it stays still. A reader that waits for "a frame after T" never waits
  long;
- it publishes every grab to a BACKEND-PRIVATE ring (``/dev/shm/rdp-ring`` in the backend
  container), never the shared ``framebus`` volume: vision stays S2-only (ADR-0005);
- it writes only while the capture-backend lock says ``rdp``. On ``console`` it stops
  heart-beating, so every reader falls back (to the S2 ring, or to X) by itself;
- the readers are ``CaptureSelector`` (the console stream) and ``GrabSource`` (ro_agent's screen
  helper, the bench). Both take the ring only while its writer heart-beats, else X, as on S2.

``RDP_FRAMEBUS=off`` disables it (everything is X again, as before).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from poring_backend.capture_lock import read_lock
from poring_env.framebus import FrameBusError, FrameBusWriter

log = logging.getLogger(__name__)

RING_DEFAULT = Path("/dev/shm/rdp-ring")
MAX_FPS = 30.0
KEEPALIVE_S = 0.1  # a still screen: a fresh frame 10 times a second
LOCK_RECHECK_S = 0.5
SLOTS = 4

Grab = Callable[[], tuple[int, NDArray[np.uint8]]]  # (t_mono_ns, HxWx4 BGRA of the session)


def enabled() -> bool:
    return os.environ.get("RDP_FRAMEBUS", "on").strip().lower() not in ("off", "0", "false", "no")


class RdpBusWriter:
    """The one X grabber on the RDP path. Thread-safe start/stop; /health reads ``snapshot``."""

    def __init__(self, grab: Grab, *, ring: Path = RING_DEFAULT, lab_state: Path,
                 damage_factory: Callable[[Callable[[int], None]], Any] | None = None,
                 max_fps: float = MAX_FPS, keepalive_s: float = KEEPALIVE_S,
                 lock_backend: Callable[[], str] | None = None) -> None:  # fmt: skip
        self._grab = grab
        self.ring = ring
        self.lab_state = lab_state
        self._damage_factory = damage_factory
        self._damage: Any = None
        self.max_fps = max_fps
        self.keepalive_s = keepalive_s
        self._lock_backend = lock_backend or (lambda: read_lock(self.lab_state).backend)
        self._changed = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._writer: FrameBusWriter | None = None
        self.frame_id = 0
        self.frames = 0
        self.on_damage = 0
        self.keepalives = 0
        self.errors = 0
        self.writing = False

    # --- lifecycle --------------------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        if self._damage_factory is not None and self._damage is None:
            self._damage = self._damage_factory(lambda _t: self._changed.set())
            self._damage.start()
        self._thread = threading.Thread(target=self._run, name="rdp-bus", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._changed.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._damage is not None:
            self._damage.stop()
        self._close()

    def _close(self) -> None:
        if self._writer is not None:
            self._writer.close(unlink=True)
            self._writer = None
        self.writing = False

    # --- the loop ---------------------------------------------------------------------------------
    def step(self, *, now: float, last_grab: float) -> float:
        """One iteration (testable): grab and publish if it is time; returns the grab time."""
        try:
            t, img = self._grab()
        except Exception as exc:  # X down, display restarting, ...
            self.errors += 1
            log.debug("rdp-bus grab failed (%s)", exc)
            return last_grab
        if self._writer is None:
            h, w = int(img.shape[0]), int(img.shape[1])
            self._writer = FrameBusWriter(self.ring, max_width=w, max_height=h, slots=SLOTS)
        self.frame_id += 1
        self._writer.publish(np.ascontiguousarray(img), self.frame_id, t)
        self.frames += 1
        self.writing = True
        return now

    def _run(self) -> None:
        last_grab = 0.0
        checked, rdp = 0.0, False
        while not self._stop.is_set():
            now = time.monotonic()
            if now - checked >= LOCK_RECHECK_S:
                checked = now
                try:
                    rdp = self._lock_backend() == "rdp"
                except Exception:  # an unreadable lock: fail closed (no RDP frames)
                    rdp = False
                if not rdp and self.writing:
                    self._close()  # readers see no heartbeat and fall back on their own
            if not rdp:
                self._stop.wait(LOCK_RECHECK_S)
                continue
            # a change (XDamage) or the keepalive, never above max_fps
            changed = self._changed.wait(timeout=self.keepalive_s)
            self._changed.clear()
            if self._stop.is_set():
                break
            wait = 1.0 / self.max_fps - (time.monotonic() - last_grab)
            if wait > 0:
                time.sleep(wait)
            if changed:
                self.on_damage += 1
            else:
                self.keepalives += 1
            try:
                last_grab = self.step(now=time.monotonic(), last_grab=last_grab)
            except FrameBusError as exc:
                self.errors += 1
                log.warning("rdp-bus ring unavailable (%s); retrying in 1 s", exc)
                self._close()
                self._stop.wait(1.0)
        self._close()

    def snapshot(self) -> dict[str, Any]:
        return {"enabled": True, "ring": str(self.ring), "writing": self.writing,
                "frames": self.frames, "on_damage": self.on_damage,
                "keepalives": self.keepalives, "errors": self.errors,
                "max_fps": self.max_fps, "keepalive_s": self.keepalive_s}  # fmt: skip


def x_session_grab(display: str) -> Grab:
    """A Grab of the whole Windows session on the X display. mss is bound to the thread that
    creates it, so it is created on the FIRST call (the writer's own thread)."""
    state: dict[str, Any] = {}

    def grab() -> tuple[int, NDArray[np.uint8]]:
        if "sct" not in state:
            import mss

            from poring_env.x11 import parse_session_size, session_extent

            sct = mss.MSS(display=display)
            mon = sct.monitors[0]
            size = parse_session_size(os.environ.get("SESSION_SIZE", ""))
            state["sct"], state["wh"] = sct, session_extent(size, mon["width"], mon["height"])
        w, h = state["wh"]
        t = time.monotonic_ns()
        shot = state["sct"].grab({"left": 0, "top": 0, "width": w, "height": h})
        return t, np.frombuffer(shot.raw, np.uint8).reshape(shot.height, shot.width, 4)

    return grab
