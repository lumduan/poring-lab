"""Process-wide backend state: the mux, the single XTest writer, the input log, the stream hub."""

import asyncio
import contextlib
import hashlib
import logging
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol, TypeVar

from poring_backend.clipboard import ClipboardService, PasteOutcome, SelectionIO
from poring_backend.config import Settings
from poring_backend.drops import DropCounter
from poring_backend.input_log import InputLog, InputLogRecord, wall_clock_iso
from poring_backend.mux import Decision, InputMux, Routed, Source
from poring_backend.stream import CaptureHub, Outbox
from poring_backend.transfer_log import TransferLog
from poring_env.clock import monotonic_ns
from poring_env.env import FrameSource
from poring_env.protocol import (
    ClipboardPaste,
    InputEvent,
    Key,
    Mode,
    PasteResult,
    ReleaseAll,
    SetMode,
    Status,
)

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
        clipboard_factory: Callable[[], SelectionIO] | None = None,
    ) -> None:
        self.settings = settings
        self.mux = InputMux(lease_ns=settings.lease_ns)  # always boots in HUMAN
        self.input_log = InputLog(settings.data_dir)
        self.transfer_log = TransferLog(settings.data_dir)
        # Never silent (ADR-0004 decision 4): unreadable messages and mux refusals are counted.
        self.drops = DropCounter()
        self.refused: Counter[tuple[str, str]] = Counter()
        self.clipboard: ClipboardService | None = None
        if settings.clipboard_enabled and clipboard_factory is not None:
            self.clipboard = ClipboardService(
                clipboard_factory, settle_s=settings.clipboard_settle_s
            )
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
        if self.clipboard is not None:
            self.clipboard.start()
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
        if self.clipboard is not None:
            await asyncio.to_thread(self.clipboard.stop)
        self.input_log.close()
        self.transfer_log.close()

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
            clipboard_enabled=self.clipboard is not None,
            transfer_enabled=self.settings.transfer_enabled,
        )

    def refused_snapshot(self) -> dict[str, dict[str, int]]:
        """``{source: {reason: count}}`` of mux refusals, for /health."""
        out: dict[str, dict[str, int]] = {}
        for (source, reason), count in sorted(self.refused.items()):
            out.setdefault(source, {})[reason] = count
        return out

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

    async def submit_many(
        self,
        source: Source,
        events: Sequence[InputEvent],
        *,
        synthetic_reason: str | None = None,
    ) -> list[Decision]:
        """Run ``events`` through the mux and inject what it allows. ``synthetic_reason`` marks
        events the backend generated on the source's behalf (e.g. the Ctrl+V of a paste)."""
        now = monotonic_ns()
        lease_before = self.mux.lease_active(now)
        decisions: list[Decision] = []
        routed: list[Routed] = []
        for event in events:
            decision = self.mux.submit(source, event, now)
            # Refused housekeeping (a disconnect's ReleaseAll for a source without control) is
            # still in the input log, but it is not a dropped input worth counting.
            if not decision.accepted and not isinstance(event, ReleaseAll):
                self.refused[(source.value, decision.reason)] += 1
            self._log(
                source,
                event.model_dump(mode="json"),
                event.frame_id,
                decision.accepted,
                synthetic_reason if decision.accepted and synthetic_reason else decision.reason,
                now,
                synthetic=synthetic_reason is not None,
            )
            self._log_synthetic(decision.inject, now)
            decisions.append(decision)
            routed.extend(decision.inject)
        await self._inject(routed)
        if self.mux.lease_active(now) != lease_before:
            self.broadcast_status()
        return decisions

    async def paste(self, msg: ClipboardPaste, *, browser: bool, client: str | None) -> PasteResult:
        """Human-only paste (ADR-0004). ``browser``: the connection presented an allowlisted
        Origin. Only the length and sha256 of the text are ever logged."""
        data = msg.text.encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        refusal: str | None = None
        if self.clipboard is None:
            refusal = "clipboard_disabled"
        elif not browser:
            refusal = "origin_required"
        elif self.mux.mode is Mode.BOT:
            refusal = "mode_bot"
        now = monotonic_ns()
        summary = {"type": msg.type, "chars": len(msg.text), "bytes": len(data), "sha256": digest}
        self._log(Source.HUMAN, summary, msg.frame_id, refusal is None, refusal or "ok", now)
        if refusal is not None or self.clipboard is None:
            outcome = PasteOutcome(False, refusal or "clipboard_disabled")
        else:
            outcome = await self.clipboard.paste(msg.text, self._inject_paste_chord)
        if not outcome.ok:
            self.refused[(Source.HUMAN.value, f"paste:{outcome.reason}")] += 1
        self.transfer_log.write(
            "paste",
            name=None,
            size=len(data),
            sha256=digest,
            ok=outcome.ok,
            reason=outcome.reason,
            client=client,
        )
        return PasteResult(
            t_mono_ns=monotonic_ns(),
            frame_id=msg.frame_id,
            request_id=msg.request_id,
            ok=outcome.ok,
            reason=outcome.reason,
            chars=len(msg.text) if outcome.ok else 0,
        )

    async def _inject_paste_chord(self) -> str | None:
        """Ctrl+V as the human, through the mux; returns the refusal reason, if any."""
        now = monotonic_ns()
        chord = [
            Key(t_mono_ns=now, code="ControlLeft", action="down"),
            Key(t_mono_ns=now, code="KeyV", action="down"),
            Key(t_mono_ns=now, code="KeyV", action="up"),
            Key(t_mono_ns=now, code="ControlLeft", action="up"),
        ]
        decisions = await self.submit_many(Source.HUMAN, chord, synthetic_reason="clipboard_paste")
        refused = [d.reason for d in decisions if not d.accepted]
        return refused[0] if refused else None

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
