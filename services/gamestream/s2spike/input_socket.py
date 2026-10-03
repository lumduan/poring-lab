"""S2 step 3: the input socket. The backend's Injector (the ONE input writer, ADR-0002; every event
has passed the InputMux) sends batches here, and the S2 client turns them into LiSend* calls to
Sunshine. No X window takes part (Batt, 2026-10-03): the path is mux -> socket -> Sunshine.

The socket: a unix stream socket at ``/s2-input/input.sock`` (0660) on the ``s2-input`` tmpfs that
only gamestream and the backend mount (test_guards). ONE peer at a time; a peer that disconnects has
everything it held released, so a dead backend never leaves a key down on the one Windows session.

The wire: one JSON line per batch, ``{"t": sent_ns, "events": [InputEvent dicts]}`` (the
protocol.py models, ``model_dump(mode="json")``), answered once every LiSend* call of the batch has
returned with ``{"t": sent_ns, "recv": ns, "done": ns, "n": applied, "refused": [[i, reason]...]}``.
Times are this host's CLOCK_MONOTONIC (the backend shares it). Every field is whitelisted per type;
anything else is refused per event, never guessed at.

It counts, and never records which keys were pressed (secret typing must stay secret).
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import socket
import stat
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .vk import CODE_TO_VK

SOCKET_PATH = Path("/s2-input/input.sock")
MAX_LINE = 64 * 1024
MAX_EVENTS = 512
WHEEL_DELTA = 120  # per notch, as Moonlight-qt's high-res scroll (and the V3b X path) sends
MODIFIER_BITS = {0xA0: 0x01, 0xA1: 0x01, 0xA2: 0x02, 0xA3: 0x02, 0xA4: 0x04, 0xA5: 0x04,
                 0x5B: 0x08, 0x5C: 0x08}  # fmt: skip  # VK -> MODIFIER_* bit
BUTTONS = {"left": "BUTTON_LEFT", "middle": "BUTTON_MIDDLE", "right": "BUTTON_RIGHT"}
COMMON = {"type", "t_mono_ns", "frame_id"}
FIELDS = {
    "mouse_move": COMMON | {"x", "y"},
    "mouse_button": COMMON | {"button", "action", "x", "y"},
    "wheel": COMMON | {"dy"},
    "key": COMMON | {"code", "action"},
    "release_all": COMMON,
}


class Refused(ValueError):
    """One event that is not on the whitelist; its reason goes back in the ack."""


def _norm(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not 0.0 <= value <= 1.0:
        raise Refused("bad_coordinate")
    return float(value)


def to_pixels(x: float, y: float, width: int, height: int) -> tuple[int, int]:
    """poring_env.x11.to_pixels, the same rule: the pixel containing that point (1.0 -> last)."""
    return min(width - 1, max(0, int(x * width))), min(height - 1, max(0, int(y * height)))


class InputMapper:
    """InputEvent dicts -> LiSend* calls. Tracks what it holds (keys, buttons) and the modifier
    bits, which Moonlight-qt sends INCLUDING a modifier key's own change (SDL's rule)."""

    def __init__(self, lib: Any, const: dict[str, int], width: int, height: int) -> None:
        self.lib, self.const, self.w, self.h = lib, const, width, height
        self.keys: set[int] = set()  # VKs held
        self.buttons: set[str] = set()
        self.counts = {"batches": 0, "keys": 0, "buttons": 0, "moves": 0, "wheel": 0,
                       "release_all": 0, "refused": 0}  # fmt: skip

    def mods(self) -> int:
        out = 0
        for vk in self.keys:
            out |= MODIFIER_BITS.get(vk, 0)
        return out

    def _move(self, x: Any, y: Any) -> None:
        px, py = to_pixels(_norm(x), _norm(y), self.w, self.h)
        self.lib.LiSendMousePositionEvent(px, py, self.w, self.h)
        self.counts["moves"] += 1

    def _key(self, vk: int, down: bool) -> None:
        (self.keys.add if down else self.keys.discard)(vk)
        action = self.const["KEY_ACTION_DOWN" if down else "KEY_ACTION_UP"]
        # `short keyCode` in C: 0x8000 | VK wraps negative, exactly as Moonlight-qt's call
        self.lib.LiSendKeyboardEvent(
            ctypes.c_short(0x8000 | vk).value, bytes([action]), bytes([self.mods()])
        )
        self.counts["keys"] += 1

    def _button(self, name: str, down: bool) -> None:
        (self.buttons.add if down else self.buttons.discard)(name)
        action = self.const["BUTTON_ACTION_PRESS" if down else "BUTTON_ACTION_RELEASE"]
        self.lib.LiSendMouseButtonEvent(bytes([action]), self.const[BUTTONS[name]])
        self.counts["buttons"] += 1

    def check(self, event: Any) -> str:
        """The event's type, or Refused: a whitelist check BEFORE anything of it is sent."""
        if not isinstance(event, dict):
            raise Refused("not_an_object")
        kind = event.get("type")
        if kind not in FIELDS:
            raise Refused("unknown_type")
        if set(event) - FIELDS[kind]:
            raise Refused("unknown_field")
        if kind == "mouse_move":
            _norm(event.get("x")), _norm(event.get("y"))
        elif kind == "mouse_button":
            if event.get("button") not in BUTTONS or event.get("action") not in ("down", "up"):
                raise Refused("bad_button")
            x, y = event.get("x"), event.get("y")
            if (x is None) != (y is None):
                raise Refused("bad_coordinate")
            if x is not None and y is not None:
                _norm(x), _norm(y)
        elif kind == "wheel":
            dy = event.get("dy")
            if isinstance(dy, bool) or not isinstance(dy, int) or not -10 <= dy <= 10:
                raise Refused("bad_wheel")
        elif kind == "key" and (
            event.get("code") not in CODE_TO_VK or event.get("action") not in ("down", "up")
        ):
            raise Refused("unknown_key")
        return str(kind)

    def apply(self, event: Any) -> None:
        kind = self.check(event)
        if kind == "mouse_move":
            self._move(event["x"], event["y"])
        elif kind == "mouse_button":
            if event.get("x") is not None:
                self._move(event["x"], event["y"])
            self._button(event["button"], event["action"] == "down")
        elif kind == "wheel":
            # dy > 0 scrolls down (DOM deltaY sign) = a negative wheel delta (Windows WHEEL_DELTA)
            step = -WHEEL_DELTA if event["dy"] > 0 else WHEEL_DELTA
            for _ in range(abs(event["dy"])):
                self.lib.LiSendHighResScrollEvent(step)
            self.counts["wheel"] += 1
        elif kind == "key":
            self._key(CODE_TO_VK[event["code"]], event["action"] == "down")
        else:
            self.release_all()

    def release_all(self) -> None:
        """Release every key and button this client holds (non-modifiers first, then modifiers,
        so no stray chord is formed on the way out)."""
        for vk in sorted(self.keys, key=lambda v: (v in MODIFIER_BITS, v)):
            self._key(vk, False)
        for name in sorted(self.buttons):
            self._button(name, False)
        self.counts["release_all"] += 1

    def batch(self, events: list[Any]) -> tuple[int, list[list[Any]]]:
        """Apply a batch in order; returns (applied, [[index, reason], ...])."""
        self.counts["batches"] += 1
        applied, refused = 0, []
        for i, event in enumerate(events):
            try:
                self.apply(event)
                applied += 1
            except Refused as exc:
                refused.append([i, str(exc)])
                self.counts["refused"] += 1
        return applied, refused


def handle_line(mapper: InputMapper, line: bytes, now: Callable[[], int]) -> dict[str, Any]:
    recv = now()
    try:
        msg = json.loads(line)
        sent, events = msg["t"], msg["events"]
        if not isinstance(sent, int) or not isinstance(events, list) or set(msg) != {"t", "events"}:
            raise ValueError("shape")
    except (ValueError, KeyError, TypeError):
        mapper.counts["refused"] += 1
        return {"t": None, "recv": recv, "done": now(), "n": 0, "refused": [[-1, "bad_batch"]]}
    if len(events) > MAX_EVENTS:
        mapper.counts["refused"] += len(events)
        return {"t": sent, "recv": recv, "done": now(), "n": 0, "refused": [[-1, "too_many"]]}
    applied, refused = mapper.batch(events)
    return {"t": sent, "recv": recv, "done": now(), "n": applied, "refused": refused}


class InputServer:
    """The socket, served on its own thread; one peer at a time."""

    def __init__(
        self,
        path: Path,
        mapper: InputMapper,
        log: Callable[[str], None],
        *,
        now: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self.path, self.mapper, self.log, self.now = path, mapper, log, now
        self.peers = 0
        self._stop = threading.Event()
        self._lock = threading.Lock()  # the mapper is used by one peer, and by close()
        with contextlib.suppress(FileNotFoundError):
            if not stat.S_ISSOCK(self.path.lstat().st_mode):
                raise RuntimeError(f"{self.path} exists and is not a socket: refusing")
            self.path.unlink()  # a stale socket from a previous stream
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        old = os.umask(0o117)  # 0660 from the start: never a moment world-connectable
        try:
            self.sock.bind(str(self.path))
        finally:
            os.umask(old)
        os.chmod(self.path, 0o660)
        self.sock.listen(1)
        self.sock.settimeout(0.5)
        self._thread = threading.Thread(target=self._serve, name="s2-input", daemon=True)
        self._thread.start()
        log(f"input socket: {self.path} (0660), one peer at a time")

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            self.peers += 1
            try:
                self._peer(conn)
            finally:
                with self._lock:
                    if self.mapper.keys or self.mapper.buttons:
                        self.mapper.release_all()  # a gone peer never leaves anything held
                conn.close()

    def _peer(self, conn: socket.socket) -> None:
        conn.settimeout(0.5)
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = conn.recv(65536)
            except TimeoutError:
                continue
            except OSError:
                return
            if not chunk:
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                with self._lock:
                    ack = handle_line(self.mapper, line, self.now)
                try:
                    conn.sendall(json.dumps(ack, separators=(",", ":")).encode() + b"\n")
                except OSError:
                    return
            if len(buf) > MAX_LINE:
                self.log("input socket: a line over 64 KiB; peer dropped")
                return

    def close(self) -> None:
        self._stop.set()
        with contextlib.suppress(OSError):
            self.sock.close()
        self._thread.join(timeout=2)
        with self._lock:
            if self.mapper.keys or self.mapper.buttons:
                self.mapper.release_all()
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()
