"""Screen stream: one capture loop, fanned out to every viewer, latest frame wins.

The loop runs only while at least one viewer is connected. Each viewer has one frame *slot*; a
slow viewer skips frames instead of queueing them, so latency never builds up (the skips are
counted: ``frames_dropped_slow_viewer``). Control messages (status, detections, pong) go through a
small bounded outbox on the same connection, and a single pump task per connection does all the
sending (Starlette WebSockets are not safe for concurrent sends).

Capture modes (``StreamTuning.capture``, switchable at runtime, docs/phase0-latency.md):
  fixed   grab on a fixed slot grid (``fps``) -- a change waits up to one period for its grab;
  damage  grab when XDamage reports a change, at most ``max_fps`` times a second, plus a 1 s
          keepalive grab.
"""

import asyncio
import contextlib
import logging
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal, Protocol

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


async def pump(
    ws: WebSocket, outbox: Outbox, on_sent: Callable[[int, int], None] | None = None
) -> None:
    """The only task that sends on ``ws``. FrameMeta is stamped with the actual send time and is
    immediately followed by its JPEG as one binary message. ``on_sent(frame_id, t_sent)``."""
    while True:
        control, frame = await outbox.drain()
        for text in control:
            await ws.send_text(text)
        if frame is not None:
            meta, jpeg = frame
            sent = monotonic_ns()
            await ws.send_text(meta.model_copy(update={"t_mono_ns": sent}).model_dump_json())
            await ws.send_bytes(jpeg)
            if on_sent is not None:
                on_sent(meta.frame_id, sent)


@dataclass
class StreamTuning:
    """Runtime-switchable stream and console settings (GET/POST /debug/stream-tuning)."""

    capture: Literal["fixed", "damage"] = "fixed"
    fps: float = 30.0  # fixed mode
    max_fps: float = 60.0  # damage mode cap
    jpeg_quality: int = 80
    move_interval_ms: int | None = None  # console: null = one pointer move per animation frame
    paint: Literal["decode", "raf"] = "decode"  # console: paint on decode or on rAF


class ChangeWatcher(Protocol):
    """What the hub needs from a damage source (damage.DamageWatcher in production)."""

    events: int
    connected: bool

    def start(self) -> None: ...

    def stop(self) -> None: ...


def damage_wait_s(since_last_grab_s: float, max_fps: float) -> float:
    """How long a damage-triggered grab must still wait to respect the ``max_fps`` cap."""
    return max(0.0, 1.0 / max_fps - since_last_grab_s)


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
        tuning: StreamTuning,
        damage_factory: Callable[[Callable[[int], None]], ChangeWatcher] | None = None,
        on_frame: Callable[[FrameMeta], None] | None = None,
    ) -> None:
        self._source_factory = source_factory
        self._source: FrameSource | None = None
        self.tuning = tuning
        self._damage_factory = damage_factory
        self._damage: ChangeWatcher | None = None
        self._damaged: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._on_frame = on_frame
        # mss connections are per-thread; one dedicated capture thread keeps a single one.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="capture")
        self._viewers: set[Outbox] = set()
        self._task: asyncio.Task[None] | None = None
        self.capture_fps = 0.0
        self.last_frame_id = -1
        self.frames_skipped_late = 0
        self._dropped_by_gone_viewers = 0
        self.grabs_on_damage = 0
        self.grabs_keepalive = 0

    @property
    def target_fps(self) -> float:
        return self.tuning.max_fps if self.damage_active else self.tuning.fps

    @property
    def damage_active(self) -> bool:
        # Falls back to fixed pacing while the damage watcher is not connected to X.
        return (
            self.tuning.capture == "damage" and self._damage is not None and self._damage.connected
        )

    @property
    def damage_events(self) -> int:
        return self._damage.events if self._damage is not None else 0

    @property
    def frames_dropped_slow_viewer(self) -> int:
        """Frames a viewer never received because a newer one replaced it (latest wins)."""
        return self._dropped_by_gone_viewers + sum(o.frames_skipped for o in self._viewers)

    @property
    def viewer_count(self) -> int:
        return len(self._viewers)

    def add_viewer(self) -> Outbox:
        outbox = Outbox()
        self._viewers.add(outbox)
        if self._damaged is not None:
            self._damaged.set()  # damage mode: a newcomer gets a frame now, not at the keepalive
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="capture-loop")
        return outbox

    def remove_viewer(self, outbox: Outbox) -> None:
        if outbox in self._viewers:
            self._dropped_by_gone_viewers += outbox.frames_skipped
        self._viewers.discard(outbox)
        if not self._viewers and self._task is not None:
            self._task.cancel()
            self._task = None
            self.capture_fps = 0.0

    def broadcast_control(self, text: str) -> None:
        for outbox in self._viewers:
            outbox.offer_control(text)

    def _grab_and_encode(self, quality: int) -> tuple[Frame, bytes, int]:
        if self._source is None:
            self._source = self._source_factory()
        frame = self._source.grab()
        jpeg = encode_jpeg(frame, quality)
        return frame, jpeg, monotonic_ns()

    def _notify_damage(self, _t_ns: int) -> None:
        """Called on the damage thread."""
        loop, event = self._loop, self._damaged
        if loop is not None and event is not None:
            with contextlib.suppress(RuntimeError):  # loop closed during shutdown
                loop.call_soon_threadsafe(event.set)

    def _ensure_damage(self) -> None:
        if self.tuning.capture != "damage" or self._damage_factory is None:
            return
        if self._damage is None:
            self._damage = self._damage_factory(self._notify_damage)
        self._damage.start()

    async def _wait_for_change(self, loop: asyncio.AbstractEventLoop, last_grab: float) -> None:
        """Damage mode: sleep until the screen changes (or the 1 s keepalive), then respect
        max_fps. A change that arrives during the grab re-arms the event for the next round."""
        assert self._damaged is not None
        try:
            await asyncio.wait_for(self._damaged.wait(), timeout=1.0)
            self.grabs_on_damage += 1
        except TimeoutError:
            self.grabs_keepalive += 1
        self._damaged.clear()
        await asyncio.sleep(damage_wait_s(loop.time() - last_grab, self.tuning.max_fps))

    def _reset_source(self) -> None:
        if self._source is not None:
            with contextlib.suppress(Exception):
                self._source.close()
            self._source = None

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        self._loop = loop
        self._damaged = asyncio.Event()
        last_ns: int | None = None
        pacer = Pacer(1.0 / self.tuning.fps, loop.time())
        pacer_fps = self.tuning.fps
        last_grab = loop.time()
        first = True
        was_damage = False
        while True:
            self._ensure_damage()
            if self.damage_active and not first:
                await self._wait_for_change(loop, last_grab)
            elif was_damage:  # back to fixed pacing: start a fresh slot grid
                pacer, pacer_fps = Pacer(1.0 / self.tuning.fps, loop.time()), self.tuning.fps
            was_damage = self.damage_active
            first = False
            last_grab = loop.time()
            try:
                frame, jpeg, encoded_ns = await loop.run_in_executor(
                    self._executor, self._grab_and_encode, self.tuning.jpeg_quality
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # X down, display restarting, ...
                log.warning("capture failed (%s); retrying in 1s", exc)
                await loop.run_in_executor(self._executor, self._reset_source)
                self.capture_fps = 0.0
                await asyncio.sleep(1.0)
                pacer = Pacer(1.0 / self.tuning.fps, loop.time())
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
            if self._on_frame is not None:
                self._on_frame(meta)
            for outbox in self._viewers:
                outbox.offer_frame(meta, jpeg)
            self.last_frame_id = frame.frame_id
            if last_ns is not None and frame.t_capture_ns > last_ns:
                instant = 1e9 / (frame.t_capture_ns - last_ns)
                self.capture_fps = (
                    instant if self.capture_fps == 0.0 else (0.9 * self.capture_fps + 0.1 * instant)
                )
            last_ns = frame.t_capture_ns
            if self.damage_active:
                continue  # the next round waits for a change instead of a slot
            if pacer_fps != self.tuning.fps:  # fps changed at runtime: a new grid
                pacer, pacer_fps = Pacer(1.0 / self.tuning.fps, loop.time()), self.tuning.fps
            wait = pacer.delay(loop.time())
            self.frames_skipped_late = pacer.skipped
            await asyncio.sleep(wait)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._damage is not None:
            await asyncio.to_thread(self._damage.stop)
        await asyncio.get_running_loop().run_in_executor(self._executor, self._reset_source)
        self._executor.shutdown(wait=False, cancel_futures=True)
