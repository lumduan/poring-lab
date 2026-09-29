"""X11 implementation of the Env contract (requires the ``x11`` extra).

Capture: mss 10.2 -- XCB + XShmGetImage with the shared segment passed as a memfd over the X socket,
so it works from another container that only mounts ``/tmp/.X11-unix`` (no IPC-namespace sharing);
mss falls back to XGetImage by itself and reports why in ``performance_status()``.

Input: python-xlib speaking the XTEST extension. The remote RDP pointer is an X cursor, not
framebuffer pixels, so grabs are cursor-free unless ``with_cursor=True`` (XFixes compositing).
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


def to_pixels(x: float, y: float, width: int, height: int) -> tuple[int, int]:
    """Map normalized [0, 1] coordinates to the pixel containing that point (1.0 -> last pixel)."""
    px = min(width - 1, max(0, int(x * width)))
    py = min(height - 1, max(0, int(y * height)))
    return px, py


class X11Capture:
    """FrameSource over mss. Each calling thread gets its own X connection (mss is not
    thread-safe); callers normally dedicate one capture thread anyway."""

    def __init__(
        self,
        display: str | None = None,
        *,
        with_cursor: bool = False,
        counter: FrameCounter | None = None,
    ) -> None:
        self._display = display
        self._with_cursor = with_cursor
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

    def grab(self) -> Frame:
        sct = self._sct()
        monitors = sct.monitors
        shot = sct.grab(monitors[1] if len(monitors) > 1 else monitors[0])
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
    (single-writer invariant, ADR-0002)."""

    def __init__(self, display: str | None = None) -> None:
        self._d = xdisplay.Display(display)
        if not self._d.has_extension("XTEST"):
            self._d.close()
            raise RuntimeError(f"X display {display!r} has no XTEST extension")
        screen = self._d.screen()
        self.width: int = screen.width_in_pixels
        self.height: int = screen.height_in_pixels
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

    def __init__(self, display: str | None = None, *, with_cursor: bool = False) -> None:
        self.capture = X11Capture(display, with_cursor=with_cursor)
        self.input = X11Input(display)
        super().__init__(self.capture, self.input)
