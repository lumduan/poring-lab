"""The S2 client's PRESENCE marker on the lab display: one X window that is never mapped, selects no
input and is never painted (Batt, 2026-10-03: "unmapped marker window", S2 step 3).

It is not a data path. It only keeps the three existing "a stream client is up" checks true
without changing them:
  - rdp-loop's second interlock (`xwininfo -root -tree | grep '("moonlight"'`: unmapped windows are
    listed too), so RDP never connects over a live stream;
  - /health.stream_window_present (the backend walks the window tree for WM_CLASS "moonlight");
  - capture_backend.py to-console's success gate (that health field).
Input reaches Windows through the input socket (input_socket.py), never through this window, and
the placer (`xdotool search --onlyvisible`) never sees it.
"""

from __future__ import annotations

import ctypes
import ctypes.util
from ctypes import POINTER, Structure, c_char_p, c_int, c_uint, c_ulong, c_void_p

WM_CLASS = (b"moonlight", b"S2client")
TITLE = b"S2 (bus + input socket) - Moonlight presence marker"


class XClassHint(Structure):
    _fields_ = [("res_name", c_char_p), ("res_class", c_char_p)]


ErrorHandler = ctypes.CFUNCTYPE(c_int, c_void_p, c_void_p)


class Presence:
    def __init__(self, width: int, height: int) -> None:
        x11 = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
        self.x11 = x11
        x11.XOpenDisplay.restype = c_void_p
        x11.XOpenDisplay.argtypes = [c_char_p]
        x11.XDefaultRootWindow.restype = c_ulong
        x11.XDefaultRootWindow.argtypes = [c_void_p]
        x11.XCreateSimpleWindow.restype = c_ulong
        x11.XCreateSimpleWindow.argtypes = [c_void_p, c_ulong, c_int, c_int, c_uint, c_uint,
                                            c_uint, c_ulong, c_ulong]  # fmt: skip
        x11.XSetClassHint.argtypes = [c_void_p, c_ulong, POINTER(XClassHint)]
        x11.XStoreName.argtypes = [c_void_p, c_ulong, c_char_p]
        x11.XSync.argtypes = [c_void_p, c_int]
        x11.XDestroyWindow.argtypes = [c_void_p, c_ulong]
        x11.XCloseDisplay.argtypes = [c_void_p]
        x11.XSetErrorHandler.argtypes = [ErrorHandler]
        self._on_error = ErrorHandler(lambda _d, _e: 0)  # never exit() on an X error (default)
        x11.XSetErrorHandler(self._on_error)
        self.dpy = x11.XOpenDisplay(None)
        if not self.dpy:
            raise RuntimeError("cannot open the X display")
        root = x11.XDefaultRootWindow(self.dpy)
        # The stream's size, at 0,0 -- what the old window reported -- but NEVER mapped: it takes
        # no input, draws nothing and covers nothing.
        self.win = x11.XCreateSimpleWindow(self.dpy, root, 0, 0, width, height, 0, 0, 0)
        hint = XClassHint(*WM_CLASS)
        x11.XSetClassHint(self.dpy, self.win, ctypes.byref(hint))
        x11.XStoreName(self.dpy, self.win, TITLE)
        x11.XSync(self.dpy, 0)

    def close(self) -> None:
        self.x11.XDestroyWindow(self.dpy, self.win)
        self.x11.XSync(self.dpy, 0)
        self.x11.XCloseDisplay(self.dpy)
