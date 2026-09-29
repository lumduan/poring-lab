"""Screen stream: one capture loop, fanned out to every viewer, latest frame wins.

The loop runs only while at least one viewer is connected. Each viewer has one frame *slot*; a
slow viewer skips frames instead of queueing them, so latency never builds up. Control messages
(status, detections, pong) go through a small bounded outbox on the same connection, and a single
pump task per connection does all the sending (Starlette WebSockets are not safe for concurrent
sends).
"""

import asyncio
import contextlib
import logging
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import simplejpeg
from starlette.websockets import WebSocket

from poring_env.clock import monotonic_ns
from poring_env.env import FrameSource
from poring_env.frame import Frame
from poring_env.protocol import FrameMeta

log = logging.getLogger(__name__)


def encode_jpeg(frame: Frame, quality: int) -> bytes:
    """BGRA straight from X -> JPEG via libjpeg-turbo, no colour conversion pass."""
    data: bytes = simplejpeg.encode_jpeg(
        frame.to_numpy(), quality=quality, colorspace="BGRA", colorsubsampling="420", fastdct=True
    )
    return data


class Outbox:
    """Per-connection send queue: bounded control messages + one latest-frame slot."""

    def __init__(self, max_control: int = 64) -> None:
        self._control: deque[str] = deque(maxlen=max_control)
        self._frame: tuple[FrameMeta, bytes] | None = None
        self._wake = asyncio.Event()
        self.frames_skipped = 0

    def offer_control(self, text: str) -> None:
        self._control.append(text)
        self._wake.set()

    def offer_frame(self, meta: FrameMeta, jpeg: bytes) -> None:
        if self._frame is not None:
            self.frames_skipped += 1
        self._frame = (meta, jpeg)
        self._wake.set()

    async def drain(self) -> tuple[list[str], tuple[FrameMeta, bytes] | None]:
        await self._wake.wait()
        self._wake.clear()
        control = list(self._control)
        self._control.clear()
        frame, self._frame = self._frame, None
        return control, frame


async def pump(ws: WebSocket, outbox: Outbox) -> None:
    """The only task that sends on ``ws``. FrameMeta is stamped with the actual send time and is
    immediately followed by its JPEG as one binary message."""
    while True:
        control, frame = await outbox.drain()
        for text in control:
            await ws.send_text(text)
        if frame is not None:
            meta, jpeg = frame
            await ws.send_text(
                meta.model_copy(update={"t_mono_ns": monotonic_ns()}).model_dump_json()
            )
            await ws.send_bytes(jpeg)


class Pacer:
    """Deadline pacing for the capture loop.

    Frame slots sit on a fixed grid (start + k * period). After each frame, ``delay(now)`` returns
    how long to sleep until the next slot. When a frame overruns, the loop starts the next one
    immediately and the missed slots are skipped (counted in ``skipped``): the grid never shifts,
    so drift never accumulates. The clock is passed in, so this is testable without sleeping.
    """

    def __init__(self, period_s: float, now: float) -> None:
        if period_s <= 0:
            raise ValueError("period must be positive")
        self.period = period_s
        self.next_due = now + period_s
        self.skipped = 0

    def delay(self, now: float) -> float:
        if now < self.next_due:
            wait = self.next_due - now
            self.next_due += self.period
            return wait
        late_slots = int((now - self.next_due) // self.period)
        self.skipped += late_slots
        self.next_due += (late_slots + 1) * self.period
        return 0.0


class CaptureHub:
    def __init__(
        self,
        source_factory: Callable[[], FrameSource],
        *,
        fps: float,
        jpeg_quality: int,
    ) -> None:
        self._source_factory = source_factory
        self._source: FrameSource | None = None
        self._period_s = 1.0 / fps
        self._quality = jpeg_quality
        # mss connections are per-thread; one dedicated capture thread keeps a single one.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="capture")
        self._viewers: set[Outbox] = set()
        self._task: asyncio.Task[None] | None = None
        self.capture_fps = 0.0
        self.last_frame_id = -1
        self.frames_skipped_late = 0

    @property
    def target_fps(self) -> float:
        return 1.0 / self._period_s

    @property
    def viewer_count(self) -> int:
        return len(self._viewers)

    def add_viewer(self) -> Outbox:
        outbox = Outbox()
        self._viewers.add(outbox)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="capture-loop")
        return outbox

    def remove_viewer(self, outbox: Outbox) -> None:
        self._viewers.discard(outbox)
        if not self._viewers and self._task is not None:
            self._task.cancel()
            self._task = None
            self.capture_fps = 0.0

    def broadcast_control(self, text: str) -> None:
        for outbox in self._viewers:
            outbox.offer_control(text)

    def _grab_and_encode(self) -> tuple[Frame, bytes, int]:
        if self._source is None:
            self._source = self._source_factory()
        frame = self._source.grab()
        jpeg = encode_jpeg(frame, self._quality)
        return frame, jpeg, monotonic_ns()

    def _reset_source(self) -> None:
        if self._source is not None:
            with contextlib.suppress(Exception):
                self._source.close()
            self._source = None

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        last_ns: int | None = None
        pacer = Pacer(self._period_s, loop.time())
        while True:
            try:
                frame, jpeg, encoded_ns = await loop.run_in_executor(
                    self._executor, self._grab_and_encode
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # X down, display restarting, ...
                log.warning("capture failed (%s); retrying in 1s", exc)
                await loop.run_in_executor(self._executor, self._reset_source)
                self.capture_fps = 0.0
                await asyncio.sleep(1.0)
                pacer = Pacer(self._period_s, loop.time())
                continue
            meta = FrameMeta(
                t_mono_ns=encoded_ns,
                frame_id=frame.frame_id,
                t_capture_ns=frame.t_capture_ns,
                t_encoded_ns=encoded_ns,
                width=frame.width,
                height=frame.height,
                nbytes=len(jpeg),
            )
            for outbox in self._viewers:
                outbox.offer_frame(meta, jpeg)
            self.last_frame_id = frame.frame_id
            if last_ns is not None and frame.t_capture_ns > last_ns:
                instant = 1e9 / (frame.t_capture_ns - last_ns)
                self.capture_fps = (
                    instant if self.capture_fps == 0.0 else (0.9 * self.capture_fps + 0.1 * instant)
                )
            last_ns = frame.t_capture_ns
            wait = pacer.delay(loop.time())
            self.frames_skipped_late = pacer.skipped
            await asyncio.sleep(wait)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await asyncio.get_running_loop().run_in_executor(self._executor, self._reset_source)
        self._executor.shutdown(wait=False, cancel_futures=True)
