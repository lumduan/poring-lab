"""Process-wide backend state: the mux, the single XTest writer, the input log, the stream hub."""

import asyncio
import contextlib
import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol, TypeVar

from poring_backend.config import Settings
from poring_backend.input_log import InputLog, InputLogRecord, wall_clock_iso
from poring_backend.mux import Decision, InputMux, Routed, Source
from poring_backend.stream import CaptureHub, Outbox
from poring_env.clock import monotonic_ns
from poring_env.env import FrameSource
from poring_env.protocol import InputEvent, ReleaseAll, SetMode, Status

log = logging.getLogger(__name__)

T = TypeVar("T")


class XInput(Protocol):
    """What the injector needs from an input sink (poring_env.x11.X11Input in production)."""

    def send_many(self, events: list[InputEvent]) -> None: ...

    def pointer(self) -> tuple[int, int]: ...

    def has_window_class(self, needle: str) -> bool: ...

    def close(self) -> None: ...


class Injector:
    """Owns the ONE XTest connection. Events are applied on a single thread, in exactly the order
    the mux decided them; the connection is re-opened after any X error (display restart)."""

    def __init__(self, factory: Callable[[], XInput]) -> None:
        self._factory = factory
        self._sink: XInput | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="xtest")

    def _call(self, fn: Callable[[XInput], T]) -> T:
        try:
            if self._sink is None:
                self._sink = self._factory()
            return fn(self._sink)
        except Exception:
            self._reset()
            raise

    def _reset(self) -> None:
        sink, self._sink = self._sink, None
        if sink is not None:
            with contextlib.suppress(Exception):
                sink.close()

    async def _run(self, fn: Callable[[XInput], T]) -> T:
        # run_in_executor is called before the first await, so jobs queue in call order.
        return await asyncio.get_running_loop().run_in_executor(self._executor, self._call, fn)

    async def apply(self, events: list[InputEvent]) -> None:
        await self._run(lambda sink: sink.send_many(events))

    async def pointer(self) -> tuple[int, int] | None:
        try:
            return await self._run(lambda sink: sink.pointer())
        except Exception:
            return None

    async def rdp_window_present(self) -> bool | None:
        try:
            return await self._run(lambda sink: sink.has_window_class("freerdp"))
        except Exception:
            return None

    async def close(self) -> None:
        await asyncio.get_running_loop().run_in_executor(self._executor, self._reset)
        self._executor.shutdown(wait=False, cancel_futures=True)


class AppState:
    def __init__(
        self,
        settings: Settings,
        *,
        capture_factory: Callable[[], FrameSource],
        input_factory: Callable[[], XInput],
    ) -> None:
        self.settings = settings
        self.mux = InputMux(lease_ns=settings.lease_ns)  # always boots in HUMAN
        self.input_log = InputLog(settings.data_dir)
        self.injector = Injector(input_factory)
        self.hub = CaptureHub(
            capture_factory, fps=settings.stream_fps, jpeg_quality=settings.jpeg_quality
        )
        self.agents: set[Outbox] = set()
        self.rdp_window_present: bool | None = None
        self._status_task: asyncio.Task[None] | None = None
        self._background: set[asyncio.Task[Any]] = set()

    # --- lifecycle --------------------------------------------------------------------------------

    async def start(self) -> None:
        self._status_task = asyncio.create_task(self._status_loop(), name="status-loop")

    async def stop(self) -> None:
        if self._status_task is not None:
            self._status_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._status_task
        if self._background:
            await asyncio.wait(self._background, timeout=2.0)
        await self.hub.stop()
        await self.injector.close()
        self.input_log.close()

    async def _status_loop(self) -> None:
        period = 1.0 / self.settings.status_hz
        while True:
            self.rdp_window_present = await self.injector.rdp_window_present()
            self.broadcast_status()
            await asyncio.sleep(period)

    # --- status -----------------------------------------------------------------------------------

    def status(self) -> Status:
        now = monotonic_ns()
        return Status(
            t_mono_ns=now,
            frame_id=self.hub.last_frame_id,
            mode=self.mux.mode,
            lease_until_ns=self.mux.lease_until_ns(now),
            bot_connected=bool(self.agents),
            rdp_window_present=self.rdp_window_present,
            capture_fps=round(self.hub.capture_fps, 2),
            viewers=self.hub.viewer_count,
        )

    def broadcast_status(self) -> None:
        text = self.status().model_dump_json()
        self.hub.broadcast_control(text)
        for outbox in self.agents:
            outbox.offer_control(text)

    # --- input ------------------------------------------------------------------------------------

    async def set_mode(self, msg: SetMode) -> None:
        now = monotonic_ns()
        released = self.mux.set_mode(msg.mode, now)
        self._log(Source.HUMAN, msg.model_dump(mode="json"), msg.frame_id, True, "mode_change", now)
        self._log_synthetic(released, now)
        await self._inject(released)
        self.broadcast_status()

    async def submit_many(self, source: Source, events: Sequence[InputEvent]) -> list[Decision]:
        now = monotonic_ns()
        lease_before = self.mux.lease_active(now)
        decisions: list[Decision] = []
        routed: list[Routed] = []
        for event in events:
            decision = self.mux.submit(source, event, now)
            self._log(
                source,
                event.model_dump(mode="json"),
                event.frame_id,
                decision.accepted,
                decision.reason,
                now,
            )
            self._log_synthetic(decision.inject, now)
            decisions.append(decision)
            routed.extend(decision.inject)
        await self._inject(routed)
        if self.mux.lease_active(now) != lease_before:
            self.broadcast_status()
        return decisions

    async def release_source(self, source: Source) -> None:
        """Release everything ``source`` holds -- a closed tab or a dead agent must never leave a
        key or button down on the one session. Runs as its own shielded task so it completes even
        when the connection handler is being cancelled (server shutdown, test client teardown)."""
        task = asyncio.create_task(
            self.submit_many(source, [ReleaseAll(t_mono_ns=monotonic_ns())]),
            name=f"release-{source}",
        )
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        await asyncio.shield(task)

    async def _inject(self, routed: Sequence[Routed]) -> None:
        if not routed:
            return
        try:
            await self.injector.apply([r.event for r in routed])
        except Exception as exc:
            log.warning("input injection failed (X unavailable?): %s", exc)

    def _log(
        self,
        source: Source,
        event: dict[str, Any],
        frame_id: int,
        accepted: bool,
        reason: str,
        now: int,
        *,
        synthetic: bool = False,
    ) -> None:
        self.input_log.write(
            InputLogRecord(
                t_mono_ns=now,
                t_wall=wall_clock_iso(),
                source=source.value,
                mode=self.mux.mode,
                accepted=accepted,
                reason=reason,
                synthetic=synthetic,
                frame_id=frame_id,
                event=event,
            )
        )

    def _log_synthetic(self, routed: Sequence[Routed], now: int) -> None:
        for r in routed:
            if r.synthetic:
                self._log(
                    r.source,
                    r.event.model_dump(mode="json"),
                    r.event.frame_id,
                    True,
                    r.reason,
                    now,
                    synthetic=True,
                )
