"""A ``FrameSource`` over the S2 frame bus (poring_env.framebus): what the bot grabs in console
mode once the S2 client publishes decoded frames, instead of an X screen grab."""

import time
from pathlib import Path
from typing import Any

from poring_env.frame import Frame
from poring_env.framebus import BusFrame, FrameBusError, FrameBusReader


class FrameBusTimeout(TimeoutError):
    """No frame newer than the last one within the timeout."""


class BusFrameSource:
    """``grab()`` returns the newest frame with a ``frame_id`` above the last one it returned,
    waiting up to ``timeout_s`` for it (the Env contract: frame ids strictly increase). The ids
    are the writer's, so the bot, the console and the logs name the same frame.

    ``repeat_on_timeout`` (the backend's human view only, never an Env): a static screen returns
    the last frame again instead of raising -- like the damage loop's keepalive.
    ``max_fps``: never return frames faster than this (the console's CONSOLE_FPS cap); the bus
    still holds every frame for faster readers."""

    def __init__(
        self,
        path: str | Path,
        name: str,
        *,
        timeout_s: float = 1.0,
        poll_s: float = 0.002,
        repeat_on_timeout: bool = False,
        max_fps: float | None = None,
    ) -> None:
        self.path = Path(path)
        self.name = name
        self.timeout_s = timeout_s
        self.poll_s = poll_s
        self.repeat_on_timeout = repeat_on_timeout
        self.min_interval_s = 1.0 / max_fps if max_fps else 0.0
        self.repeats = 0
        self._reader: FrameBusReader | None = None
        self._last: Frame | None = None
        self._last_return = 0.0

    @property
    def reader(self) -> FrameBusReader:
        if self._reader is None:
            self._reader = FrameBusReader(self.path, self.name)
        elif self._reader.replaced():
            self._reader.reopen_if_replaced()  # a new writer: its ids may restart lower
            self._last = None
        return self._reader

    def grab(self) -> Frame:
        reader = self.reader
        wait = self._last_return + self.min_interval_s - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        after = self._last.frame_id if self._last is not None else -1
        deadline = time.monotonic() + self.timeout_s
        while True:
            got = reader.read(after)
            if got is not None:
                frame = _to_frame(got)
                self._last, self._last_return = frame, time.monotonic()
                return frame
            if time.monotonic() >= deadline:
                break
            time.sleep(self.poll_s)
        if self.repeat_on_timeout and self._last is not None:
            self.repeats += 1
            self._last_return = time.monotonic()
            return self._last
        status = reader.writer()
        raise FrameBusTimeout(
            f"{self.path}: no frame after {after} in {self.timeout_s:.1f} s "
            f"(writer pid {status.pid}, heartbeat {status.heartbeat_age_s:.1f} s ago)"
        )

    def snapshot(self) -> dict[str, Any]:
        if self._reader is None:
            return {"name": self.name, "open": False}
        st = self._reader.stats
        return {
            "name": self.name,
            "open": True,
            "frames_read": st.frames_read,
            "drops": st.drops,
            "overruns": st.overruns,
            "retries": st.retries,
            "reopens": st.reopens,
            "repeats": self.repeats,
            "last_frame_id": st.last_frame_id,
        }

    def close(self) -> None:
        if self._reader is not None:
            self._reader.close()
            self._reader = None


def _to_frame(got: BusFrame) -> Frame:
    return Frame(
        frame_id=got.frame_id,
        t_capture_ns=got.t_mono_ns,
        width=got.width,
        height=got.height,
        bgra=got.bgra,
    )


__all__ = ["BusFrameSource", "FrameBusError", "FrameBusTimeout"]
