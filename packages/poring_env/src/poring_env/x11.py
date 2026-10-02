"""X11 implementation of the Env contract (requires the ``x11`` extra).

Capture: mss 10.2 -- XCB + XShmGetImage with the shared segment passed as a memfd over the X socket,
so it works from another container that only mounts ``/tmp/.X11-unix`` (no IPC-namespace sharing);
mss falls back to XGetImage by itself and reports why in ``performance_status()``.

Input: python-xlib speaking the XTEST extension. The remote RDP pointer is an X cursor, not
framebuffer pixels, so grabs are cursor-free unless ``with_cursor=True`` (XFixes compositing).

The session area (``SESSION_SIZE``, ADR-0009 amendment 2026-10-02): the ONE Windows session is
drawn 1:1 at the X screen's top-left, and the screen may be larger. A 1920x1200 canvas lets
Moonlight open its 1440x900 stream window at native size (it caps a window at 80 % of the screen).
Capture crops to the session and input is normalised over it, so every consumer sees the same
session-sized frame and coordinates whatever the canvas is.
"""

import logging
import threading

import mss
import mss.base
from Xlib import X
from Xlib import display as xdisplay
from Xlib import error as xerror
from Xlib.ext import xtest
from Xlib.xobject.drawable import Window

from poring_env.clock import FrameCounter, monotonic_ns
from poring_env.env import CompositeEnv
from poring_env.frame import Frame
from poring_env.keymap import x11_keycode
from poring_env.protocol import InputEvent, Key, MouseButton, MouseMove, ReleaseAll, Wheel

log = logging.getLogger(__name__)

_BUTTONS = {"left": 1, "middle": 2, "right": 3}
_WHEEL_UP, _WHEEL_DOWN = 4, 5


def parse_session_size(spec: str) -> tuple[int, int] | None:
    """SESSION_SIZE "WxH" -> (w, h); "" -> None (the session fills the whole X screen)."""
    spec = spec.strip()
    if not spec:
        return None
    w, sep, h = spec.partition("x")
    if not (sep and w.isdigit() and h.isdigit() and int(w) > 0 and int(h) > 0):
        raise ValueError(f"SESSION_SIZE must be WxH (e.g. 1440x900), got {spec!r}")
    return int(w), int(h)


def session_extent(
    session: tuple[int, int] | None, screen_w: int, screen_h: int
) -> tuple[int, int]:
    """The session's (w, h) on a screen: the whole screen if unset, clipped to it if larger (an
    .env written before the desktop was recreated -- logged, never fatal)."""
    if session is None:
        return screen_w, screen_h
    w, h = min(session[0], screen_w), min(session[1], screen_h)
    if (w, h) != session:
        log.warning(
            "SESSION_SIZE %dx%d exceeds the %dx%d screen: clipped",
            session[0], session[1], screen_w, screen_h,
        )  # fmt: skip
    return w, h


def to_pixels(x: float, y: float, width: int, height: int) -> tuple[int, int]:
    """Map normalized [0, 1] coordinates to the pixel containing that point (1.0 -> last pixel)."""
    px = min(width - 1, max(0, int(x * width)))
    py = min(height - 1, max(0, int(y * height)))
    return px, py


class X11Capture:
    """FrameSource over mss. Each calling thread gets its own X connection (mss is not
    thread-safe); callers normally dedicate one capture thread anyway. ``session``: grab only the
    session area at the screen's top-left (None = the whole screen)."""

    def __init__(
        self,
        display: str | None = None,
        *,
        with_cursor: bool = False,
        counter: FrameCounter | None = None,
        session: tuple[int, int] | None = None,
    ) -> None:
        self._display = display
        self._with_cursor = with_cursor
        self._session = session
        self._counter = counter or FrameCounter()
        self._local = threading.local()
        self._instances: list[mss.base.MSS] = []
        self._lock = threading.Lock()

    def _sct(self) -> mss.base.MSS:
        sct: mss.base.MSS | None = getattr(self._local, "sct", None)
        if sct is None:
            sct = mss.MSS(display=self._display, with_cursor=self._with_cursor)
            self._local.sct = sct
            with self._lock:
                self._instances.append(sct)
            status = sct.performance_status
            if status:
                log.warning("mss capture is on a slow path: %s", "; ".join(status))
        return sct

    def _area(self, sct: mss.base.MSS) -> dict[str, int]:
        """The grabbed area, once per thread (the screen can't change under a live connection)."""
        area: dict[str, int] | None = getattr(self._local, "area", None)
        if area is None:
            monitors = sct.monitors
            screen = monitors[1] if len(monitors) > 1 else monitors[0]
            w, h = session_extent(self._session, screen["width"], screen["height"])
            area = {"left": screen["left"], "top": screen["top"], "width": w, "height": h}
            self._local.area = area
        return area

    def grab(self) -> Frame:
        sct = self._sct()
        shot = sct.grab(self._area(sct))
        return Frame(
            frame_id=self._counter.next(),
            t_capture_ns=monotonic_ns(),
            width=shot.width,
            height=shot.height,
            bgra=shot.bgra,
        )

    def close(self) -> None:
        with self._lock:
            instances, self._instances = self._instances, []
        for sct in instances:
            sct.close()
        self._local = threading.local()


class X11Input:
    """InputSink over XTEST. Thread-safe. Only the backend's input mux may own one of these
    (single-writer invariant, ADR-0002). Normalised coordinates span the session area at the
    screen's top-left (``session``; None = the whole screen), the same area X11Capture grabs."""

    def __init__(
        self, display: str | None = None, *, session: tuple[int, int] | None = None
    ) -> None:
        self._d = xdisplay.Display(display)
        if not self._d.has_extension("XTEST"):
            self._d.close()
            raise RuntimeError(f"X display {display!r} has no XTEST extension")
        screen = self._d.screen()
        self.width, self.height = session_extent(
            session, screen.width_in_pixels, screen.height_in_pixels
        )
        self._root: Window = screen.root
        self._lock = threading.Lock()
        self._keys_down: set[int] = set()
        self._buttons_down: set[int] = set()

    def send_input(self, event: InputEvent) -> None:
        with self._lock:
            self._apply(event)
            self._d.sync()

    def send_many(self, events: list[InputEvent]) -> None:
        with self._lock:
            for event in events:
                self._apply(event)
            self._d.sync()

    def _move(self, x: float, y: float) -> None:
        px, py = to_pixels(x, y, self.width, self.height)
        xtest.fake_input(self._d, X.MotionNotify, x=px, y=py)

    def _apply(self, event: InputEvent) -> None:
        match event:
            case MouseMove():
                self._move(event.x, event.y)
            case MouseButton():
                if event.x is not None and event.y is not None:
                    self._move(event.x, event.y)
                button = _BUTTONS[event.button]
                if event.action == "down":
                    xtest.fake_input(self._d, X.ButtonPress, button)
                    self._buttons_down.add(button)
                else:
                    xtest.fake_input(self._d, X.ButtonRelease, button)
                    self._buttons_down.discard(button)
            case Wheel():
                button = _WHEEL_DOWN if event.dy > 0 else _WHEEL_UP
                for _ in range(abs(event.dy)):
                    xtest.fake_input(self._d, X.ButtonPress, button)
                    xtest.fake_input(self._d, X.ButtonRelease, button)
            case Key():
                keycode = x11_keycode(event.code)
                if event.action == "down":
                    xtest.fake_input(self._d, X.KeyPress, keycode)
                    self._keys_down.add(keycode)
                else:
                    xtest.fake_input(self._d, X.KeyRelease, keycode)
                    self._keys_down.discard(keycode)
            case ReleaseAll():
                # Panic path: release everything this sink pressed, whoever asked for it.
                for keycode in sorted(self._keys_down):
                    xtest.fake_input(self._d, X.KeyRelease, keycode)
                for button in sorted(self._buttons_down):
                    xtest.fake_input(self._d, X.ButtonRelease, button)
                self._keys_down.clear()
                self._buttons_down.clear()

    def pointer(self) -> tuple[int, int]:
        """Current pointer position in screen pixels."""
        with self._lock:
            reply = self._root.query_pointer()
            return int(reply.root_x), int(reply.root_y)

    def has_window_class(self, needle: str) -> bool:
        """Whether any window's WM_CLASS contains ``needle`` (case-insensitive) -- e.g. "freerdp"
        to tell whether the RDP client window exists."""
        needle = needle.lower()
        with self._lock:
            stack = [self._root]
            while stack:
                window = stack.pop()
                try:
                    wm_class = window.get_wm_class()
                    if wm_class and any(needle in part.lower() for part in wm_class):
                        return True
                    stack.extend(window.query_tree().children)
                except xerror.XError:
                    continue  # window vanished mid-walk
            return False

    def close(self) -> None:
        self._d.close()


class X11Env(CompositeEnv):
    """Grab and act directly on an X display. Reserved for the backend (ADR-0002)."""

    def __init__(
        self,
        display: str | None = None,
        *,
        with_cursor: bool = False,
        session: tuple[int, int] | None = None,
    ) -> None:
        self.capture = X11Capture(display, with_cursor=with_cursor, session=session)
        self.input = X11Input(display, session=session)
        super().__init__(self.capture, self.input)
