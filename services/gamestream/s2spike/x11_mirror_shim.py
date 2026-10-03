"""SPIKE-ONLY COMPATIBILITY SHIM -- not part of the S2 design; drop it with the spike.

Batt, 2026-10-03: final S2 decodes ONCE into a frame bus; the bot reads numpy frames from memory,
humans get JPEG from the same bus through the console's WebSocket, NO Xvfb in the GameStream path,
and input goes mux -> S2 client -> Sunshine. This module exists only so that, during the clean-room
experiment, the existing tooling can see and drive V3 without new paths:
  - it blits each decoded frame into a 1440x900 window at 0,0 on the lab's Xvfb :99, so the web
    console, ro_agent's screenshots and the backend's black-screen detector see V3;
  - the window's WM_CLASS is ("moonlight", "S2spike"): rdp-loop's interlock (`\\("moonlight"`) and
    /health.stream_window_present see a stream window, so RDP can't connect over it;
  - it forwards the X input that reaches it -- the mux's XTest events, the ONLY input path (rule 3)
    -- to LiSend* (absolute mouse, buttons, wheel, keys as Windows VK by physical position).
It logs counts only, never which keys were pressed (secret typing must stay secret).
"""

from __future__ import annotations

import ctypes
import ctypes.util
import threading
from collections.abc import Callable
from ctypes import POINTER, Structure, c_char_p, c_int, c_long, c_uint, c_ulong, c_void_p
from typing import Any

from .vk import vk_for_x_keycode

# X protocol constants (X.h)
KEY_PRESS, KEY_RELEASE, BUTTON_PRESS, BUTTON_RELEASE, MOTION_NOTIFY = 2, 3, 4, 5, 6
MAP_NOTIFY = 19
MASKS = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 6) | (1 << 17)  # keys, buttons,
#   pointer motion, StructureNotify
SHIFT, CONTROL, MOD1, MOD4 = 1, 4, 8, 64
ZPIXMAP, REVERT_TO_POINTER_ROOT, CURRENT_TIME = 2, 1, 0
MODIFIER_VKS = {0xA0: 0x01, 0xA1: 0x01, 0xA2: 0x02, 0xA3: 0x02, 0xA4: 0x04, 0xA5: 0x04,
                0x5B: 0x08, 0x5C: 0x08}  # fmt: skip  # VK -> MODIFIER_* bit


class XInputEvent(Structure):
    """The common prefix of XKeyEvent / XButtonEvent / XMotionEvent (x86_64)."""

    _fields_ = [
        ("type", c_int),
        ("serial", c_ulong),
        ("send_event", c_int),
        ("display", c_void_p),
        ("window", c_ulong),
        ("root", c_ulong),
        ("subwindow", c_ulong),
        ("time", c_ulong),
        ("x", c_int),
        ("y", c_int),
        ("x_root", c_int),
        ("y_root", c_int),
        ("state", c_uint),
        ("detail", c_uint),  # keycode (key events) / button (button events)
    ]


class XEvent(ctypes.Union):
    _fields_ = [("type", c_int), ("input", XInputEvent), ("pad", c_long * 24)]


class XClassHint(Structure):
    _fields_ = [("res_name", c_char_p), ("res_class", c_char_p)]


ErrorHandler = ctypes.CFUNCTYPE(c_int, c_void_p, c_void_p)


def modifiers_from_state(state: int) -> int:
    """X modifier state -> moonlight-common-c MODIFIER_* bits (SHIFT 1, CTRL 2, ALT 4, META 8)."""
    out = 0
    out |= 0x01 if state & SHIFT else 0
    out |= 0x02 if state & CONTROL else 0
    out |= 0x04 if state & MOD1 else 0
    out |= 0x08 if state & MOD4 else 0
    return out


def key_modifiers(state: int, vk: int, pressed: bool) -> int:
    """X reports the state BEFORE the event; SDL (Moonlight-qt) reports it including a modifier
    key's own change. Match Moonlight-qt."""
    mods = modifiers_from_state(state)
    bit = MODIFIER_VKS.get(vk, 0)
    return (mods | bit) if pressed else (mods & ~bit)


BUTTONS = {1: "BUTTON_LEFT", 2: "BUTTON_MIDDLE", 3: "BUTTON_RIGHT", 8: "BUTTON_X1", 9: "BUTTON_X2"}
WHEEL = {4: 120, 5: -120}  # WHEEL_DELTA per click, as Moonlight-qt's high-res scroll


class Mirror:
    """One window, two X connections: frames drawn from the decode thread, input read on its own
    thread (python-xlib style rules: never share a Display between threads; XInitThreads anyway)."""

    def __init__(self, width: int, height: int, sender: Any, log: Callable[[str], None]) -> None:
        self.w, self.h, self.sender, self.log = width, height, sender, log
        x11 = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
        self.x11 = x11
        x11.XInitThreads()
        x11.XOpenDisplay.restype = c_void_p
        x11.XOpenDisplay.argtypes = [c_char_p]
        x11.XDefaultRootWindow.restype = c_ulong
        x11.XDefaultRootWindow.argtypes = [c_void_p]
        x11.XCreateSimpleWindow.restype = c_ulong
        x11.XCreateSimpleWindow.argtypes = [c_void_p, c_ulong, c_int, c_int, c_uint, c_uint,
                                            c_uint, c_ulong, c_ulong]  # fmt: skip
        x11.XSetClassHint.argtypes = [c_void_p, c_ulong, POINTER(XClassHint)]
        x11.XStoreName.argtypes = [c_void_p, c_ulong, c_char_p]
        x11.XSelectInput.argtypes = [c_void_p, c_ulong, c_long]
        x11.XMapRaised.argtypes = [c_void_p, c_ulong]
        x11.XMoveWindow.argtypes = [c_void_p, c_ulong, c_int, c_int]
        x11.XSetInputFocus.argtypes = [c_void_p, c_ulong, c_int, c_ulong]
        x11.XNextEvent.argtypes = [c_void_p, POINTER(XEvent)]
        x11.XPending.argtypes = [c_void_p]
        x11.XFlush.argtypes = [c_void_p]
        x11.XSync.argtypes = [c_void_p, c_int]
        x11.XDefaultVisual.restype = c_void_p
        x11.XDefaultVisual.argtypes = [c_void_p, c_int]
        x11.XDefaultDepth.argtypes = [c_void_p, c_int]
        x11.XDefaultGC.restype = c_void_p
        x11.XDefaultGC.argtypes = [c_void_p, c_int]
        x11.XCreateImage.restype = c_void_p
        x11.XCreateImage.argtypes = [c_void_p, c_void_p, c_uint, c_int, c_int, c_void_p, c_uint,
                                     c_uint, c_int, c_int]  # fmt: skip
        x11.XPutImage.argtypes = [c_void_p, c_ulong, c_void_p, c_void_p, c_int, c_int, c_int,
                                  c_int, c_uint, c_uint]  # fmt: skip
        x11.XDestroyWindow.argtypes = [c_void_p, c_ulong]
        x11.XCloseDisplay.argtypes = [c_void_p]
        x11.XSetErrorHandler.argtypes = [ErrorHandler]
        self._on_error = ErrorHandler(lambda _d, _e: 0)  # never exit() on an X error (default)
        x11.XSetErrorHandler(self._on_error)

        self.draw_dpy = x11.XOpenDisplay(None)
        self.event_dpy = x11.XOpenDisplay(None)
        if not self.draw_dpy or not self.event_dpy:
            raise RuntimeError("cannot open the X display")
        root = x11.XDefaultRootWindow(self.draw_dpy)
        self.win = x11.XCreateSimpleWindow(self.draw_dpy, root, 0, 0, width, height, 0, 0, 0)
        hint = XClassHint(b"moonlight", b"S2spike")
        x11.XSetClassHint(self.draw_dpy, self.win, ctypes.byref(hint))
        x11.XStoreName(self.draw_dpy, self.win, b"S2 spike (V3, clean room) - Moonlight")
        x11.XSync(self.draw_dpy, 0)
        x11.XSelectInput(self.event_dpy, self.win, MASKS)
        x11.XSync(self.event_dpy, 0)
        x11.XMapRaised(self.draw_dpy, self.win)
        x11.XMoveWindow(self.draw_dpy, self.win, 0, 0)
        x11.XSync(self.draw_dpy, 0)
        self._buf = ctypes.create_string_buffer(width * height * 4)
        visual = x11.XDefaultVisual(self.draw_dpy, 0)
        depth = x11.XDefaultDepth(self.draw_dpy, 0)
        data = ctypes.cast(self._buf, c_void_p)
        self._image = x11.XCreateImage(
            self.draw_dpy, visual, depth, ZPIXMAP, 0, data, width, height, 32, 0
        )
        self._gc = x11.XDefaultGC(self.draw_dpy, 0)
        self.counts = {"frames_shown": 0, "keys": 0, "buttons": 0, "moves": 0, "wheel": 0,
                       "keys_unmapped": 0}  # fmt: skip
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._events, name="s2spike-x-input", daemon=True)
        self._thread.start()

    def show(self, bgra: Any) -> None:
        """Blit one decoded BGRA frame (h, w, 4) uint8; frames of another size are skipped."""
        if bgra.shape[0] != self.h or bgra.shape[1] != self.w:
            return
        ctypes.memmove(self._buf, bgra.ctypes.data, self.w * self.h * 4)
        self.x11.XPutImage(self.draw_dpy, self.win, self._gc, self._image, 0, 0, 0, 0,
                           self.w, self.h)  # fmt: skip
        self.x11.XFlush(self.draw_dpy)
        self.counts["frames_shown"] += 1

    def _events(self) -> None:
        x11, ev = self.x11, XEvent()
        while not self._stop.is_set():
            if not x11.XPending(self.event_dpy):
                self._stop.wait(0.002)
                continue
            x11.XNextEvent(self.event_dpy, ctypes.byref(ev))
            self.handle(ev.type, ev.input)

    def handle(self, kind: int, e: XInputEvent) -> None:
        s, lib = self.sender, self.sender.lib
        if kind == MAP_NOTIFY:
            # Keys from XTest go to the focus window; take it while V3 streams (the loop puts it
            # back to PointerRoot after the stream, like after Moonlight-qt).
            self.x11.XSetInputFocus(self.event_dpy, self.win, REVERT_TO_POINTER_ROOT, CURRENT_TIME)
            self.x11.XFlush(self.event_dpy)
        elif kind == MOTION_NOTIFY:
            x, y = min(max(e.x, 0), self.w - 1), min(max(e.y, 0), self.h - 1)
            lib.LiSendMousePositionEvent(x, y, self.w, self.h)
            self.counts["moves"] += 1
        elif kind in (BUTTON_PRESS, BUTTON_RELEASE):
            if e.detail in WHEEL:
                if kind == BUTTON_PRESS:
                    lib.LiSendHighResScrollEvent(WHEEL[e.detail])
                    self.counts["wheel"] += 1
            elif e.detail in BUTTONS:
                action = s.const["BUTTON_ACTION_PRESS" if kind == BUTTON_PRESS else
                                 "BUTTON_ACTION_RELEASE"]  # fmt: skip
                lib.LiSendMouseButtonEvent(bytes([action]), s.const[BUTTONS[e.detail]])
                self.counts["buttons"] += 1
        elif kind in (KEY_PRESS, KEY_RELEASE):
            vk = vk_for_x_keycode(e.detail)
            if vk is None:
                self.counts["keys_unmapped"] += 1
                return
            pressed = kind == KEY_PRESS
            action = s.const["KEY_ACTION_DOWN" if pressed else "KEY_ACTION_UP"]
            mods = key_modifiers(e.state, vk, pressed)
            # `short keyCode` in C: 0x8000 | VK wraps negative, exactly as Moonlight-qt's call
            lib.LiSendKeyboardEvent(
                ctypes.c_short(0x8000 | vk).value, bytes([action]), bytes([mods])
            )
            self.counts["keys"] += 1

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self.x11.XDestroyWindow(self.draw_dpy, self.win)
        self.x11.XSync(self.draw_dpy, 0)
        # The XImage points at our buffer: never XDestroyImage it (Xlib would free() our memory).
        self.x11.XCloseDisplay(self.event_dpy)
        self.x11.XCloseDisplay(self.draw_dpy)
