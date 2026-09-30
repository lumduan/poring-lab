"""Event-driven capture: wake the capture loop when anything on the X screen changes (Phase 0).

XDamage on the root window, reported NonEmpty: the server sends one notify when the damage region
goes from empty to non-empty. We subtract it immediately (so the next change notifies again) and
tell the capture loop. The loop grabs right away, subject to a minimum interval (1/max_fps), instead
of waiting for the next slot on a fixed 30 fps grid -- on average that alone removed half a slot
(~17 ms) of capture wait.

Own X connection and thread, like the clipboard service: python-xlib connections are not
thread-safe. Only notifications cross threads.
"""

import contextlib
import logging
import select
import threading
from collections.abc import Callable

from Xlib import display as xdisplay
from Xlib.ext import damage as xdamage

from poring_env.clock import monotonic_ns

log = logging.getLogger(__name__)


class DamageWatcher:
    def __init__(
        self, display: str | None, on_damage: Callable[[int], None], *, reconnect_s: float = 2.0
    ) -> None:
        self._display = display
        self._on_damage = on_damage
        self._reconnect_s = reconnect_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.events = 0
        self.connected = False

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="damage-x", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        warned = False
        while not self._stop.is_set():
            try:
                d = xdisplay.Display(self._display)
            except Exception as exc:
                if not warned:
                    log.warning("damage: X display unavailable (%s); retrying", exc)
                    warned = True
                self._stop.wait(self._reconnect_s)
                continue
            warned = False
            try:
                self._watch(d)
            except Exception as exc:
                log.warning("damage: X connection lost (%s); reconnecting", exc)
            finally:
                self.connected = False
                with contextlib.suppress(Exception):
                    d.close()

    def _watch(self, d: xdisplay.Display) -> None:
        if not d.has_extension("DAMAGE"):
            raise RuntimeError("X display has no DAMAGE extension")
        d.damage_query_version()
        info = d.query_extension("DAMAGE")
        if info is None:
            raise RuntimeError("X display has no DAMAGE extension")
        notify_type = info.first_event + xdamage.DamageNotifyCode
        root = d.screen().root
        damage = root.damage_create(xdamage.DamageReportNonEmpty)
        d.sync()
        self.connected = True
        log.info("damage: watching the X screen for changes")
        while not self._stop.is_set():
            select.select([d], [], [], 0.5)
            fired = False
            while d.pending_events():
                e = d.next_event()
                if e.type == notify_type:
                    fired = True
            if fired:
                d.damage_subtract(damage)  # repair everything: the next change notifies again
                d.flush()
                self.events += 1
                self._on_damage(monotonic_ns())
