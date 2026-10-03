"""Process-wide backend state: the mux, the single XTest writer, the input log, the stream hub."""

import asyncio
import collections
import contextlib
import logging
import time
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Protocol, TypeVar

from poring_backend.capture_lock import read_cleanroom, read_lock
from poring_backend.capture_select import CaptureSelector
from poring_backend.clipboard import ClipboardService, PasteOutcome, SelectionIO
from poring_backend.config import Settings
from poring_backend.display import DisplayWatch, Region
from poring_backend.drops import DropCounter
from poring_backend.input_log import InputLog, InputLogRecord, wall_clock_iso
from poring_backend.latency import InputRecord, LatencyRecorder
from poring_backend.mode_restore import read_verdict
from poring_backend.mux import Decision, InputMux, Routed, Source
from poring_backend.packets import PacketHub
from poring_backend.stream import CaptureHub, ChangeWatcher, Outbox, StreamTuning
from poring_backend.transfer_log import TransferLog
from poring_env.clock import monotonic_ns
from poring_env.env import FrameSource
from poring_env.protocol import (
    CleanRoom,
    ClipboardPaste,
    InputEvent,
    Key,
    Mode,
    MouseButton,
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


class S2Sink(XInput, Protocol):
    """What the injector needs from the S2 input socket's sink (poring_env.s2input)."""

    leg_ns: "collections.deque[int]"
    refused: int


class Injector:
    """Owns the ONE input writer (ADR-0002). Events are applied on a single thread, in exactly the
    order the mux decided them; a sink is re-opened after any error (display restart, S2 client
    restart).

    Two sinks since S2 step 3 (ADR-0014): XTest on the lab display (RDP, Moonlight-qt, V3b) and the
    S2 input socket (variant S2, no X window takes input). The rule, per batch: console mode AND
    the S2 client's socket exists -> S2, else X. On a switch the old sink first gets a ReleaseAll,
    so nothing stays held where nobody sends any more. Window polls and the pointer stay on X."""

    def __init__(
        self,
        factory: Callable[[], XInput],
        *,
        s2_factory: Callable[[], S2Sink] | None = None,
        s2_socket: Path | None = None,
        console_mode: Callable[[], bool] = lambda: False,
    ) -> None:
        self._factory = factory
        self._sink: XInput | None = None
        self._s2_factory = s2_factory
        self._s2: S2Sink | None = None
        self._s2_socket = s2_socket
        self._console_mode = console_mode
        self.active = "x11"
        self.switches = 0
        self.s2_acks = 0
        self.s2_errors = 0
        self.s2_refused = 0
        self._s2_leg_ns: collections.deque[int] = collections.deque(maxlen=512)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="injector")

    # --- the X sink (input in RDP / Moonlight-qt / V3b, and every window poll) --------------------

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

    # --- the S2 sink ------------------------------------------------------------------------------

    def _reset_s2(self) -> None:
        sink, self._s2 = self._s2, None
        if sink is not None:
            with contextlib.suppress(Exception):
                sink.close()

    def _want_s2(self) -> bool:
        return (
            self._s2_factory is not None
            and self._s2_socket is not None
            and self._console_mode()
            and self._s2_socket.exists()
        )

    def _switch(self, to: str) -> None:
        """Release everything on the sink being left (best effort: it may be gone already)."""
        release: list[InputEvent] = [ReleaseAll(t_mono_ns=monotonic_ns())]
        if self.active == "s2" and self._s2 is not None:
            with contextlib.suppress(Exception):
                self._s2.send_many(release)
            self._reset_s2()  # the S2 client also releases what a closed peer held
        elif self.active == "x11" and self._sink is not None:
            with contextlib.suppress(Exception):
                self._sink.send_many(release)
        log.info("input sink %s -> %s", self.active, to)
        self.active = to
        self.switches += 1

    def _send(self, events: list[InputEvent]) -> None:
        want = "s2" if self._want_s2() else "x11"
        if want != self.active:
            self._switch(want)
        if want == "x11":
            self._call(lambda sink: sink.send_many(events))
            return
        assert self._s2_factory is not None
        try:
            if self._s2 is None:
                self._s2 = self._s2_factory()
            before = self._s2.refused
            self._s2.send_many(events)
        except Exception:
            self.s2_errors += 1
            self._reset_s2()
            raise
        self.s2_acks += 1
        self.s2_refused += self._s2.refused - before
        if self._s2.leg_ns:
            self._s2_leg_ns.append(self._s2.leg_ns[-1])

    # --- the async API ----------------------------------------------------------------------------

    async def _job(self, fn: Callable[[], T]) -> T:
        # run_in_executor is called before the first await, so jobs queue in call order.
        return await asyncio.get_running_loop().run_in_executor(self._executor, fn)

    async def _run(self, fn: Callable[[XInput], T]) -> T:
        return await self._job(lambda: self._call(fn))

    async def apply(self, events: list[InputEvent]) -> None:
        await self._job(lambda: self._send(events))

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

    async def stream_window_present(self) -> bool | None:
        """A Moonlight (console-mode, ADR-0009) window on the display -- or the S2 client's
        unmapped presence marker (same WM_CLASS)."""
        try:
            return await self._run(lambda sink: sink.has_window_class("moonlight"))
        except Exception:
            return None

    def _snapshot(self) -> dict[str, Any]:
        legs = sorted(self._s2_leg_ns)

        def pct(p: float) -> float | None:
            return round(legs[min(len(legs) - 1, int(p * len(legs)))] / 1e6, 2) if legs else None

        return {
            "active": self.active,
            "switches": self.switches,
            "s2_available": self._want_s2(),
            "s2_connected": self._s2 is not None,
            "s2_acks": self.s2_acks,
            "s2_errors": self.s2_errors,
            "s2_refused": self.s2_refused,
            # sent -> the S2 client's LiSend* calls returned (the socket leg; same host clock)
            "s2_leg_ms_p50": pct(0.5),
            "s2_leg_ms_p95": pct(0.95),
            "s2_leg_n": len(legs),
        }

    async def snapshot(self) -> dict[str, Any]:
        """For /health, on the injector's thread: its deque is never read while written."""
        return await self._job(self._snapshot)

    async def close(self) -> None:
        def shut() -> None:
            self._reset()
            self._reset_s2()

        await asyncio.get_running_loop().run_in_executor(self._executor, shut)
        self._executor.shutdown(wait=False, cancel_futures=True)


def balanced(events: Sequence[InputEvent]) -> bool:
    """True if every key/button pressed in ``events`` is released within them."""
    held: set[str] = set()
    for e in events:
        if isinstance(e, ReleaseAll):
            held.clear()
        elif isinstance(e, Key):
            (held.add if e.action == "down" else held.discard)(f"k:{e.code}")
        elif isinstance(e, MouseButton):
            (held.add if e.action == "down" else held.discard)(f"b:{e.button}")
    return not held


class AppState:
    def __init__(
        self,
        settings: Settings,
        *,
        capture_factory: Callable[[], FrameSource],
        input_factory: Callable[[], XInput],
        s2_input_factory: Callable[[], S2Sink] | None = None,
        clipboard_factory: Callable[[], SelectionIO] | None = None,
        damage_factory: Callable[[Callable[[int], None]], ChangeWatcher] | None = None,
    ) -> None:
        self.settings = settings
        # Boots in HUMAN (ADR-0002); only a guarded restart's marker can restore ASSIST (below).
        self.mux = InputMux(lease_ns=settings.lease_ns)
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
        # XTest, or the S2 input socket in console mode with a live S2 client (ADR-0014).
        self.injector = Injector(
            input_factory,
            s2_factory=s2_input_factory,
            s2_socket=settings.s2_input_socket,
            console_mode=lambda: self.capture.backend == "console",
        )
        # Phase 0: runtime-switchable stream/console tuning, and latency instrumentation (memory).
        self.tuning = StreamTuning(
            capture=settings.stream_capture,
            fps=settings.stream_fps,
            max_fps=settings.stream_max_fps,
            jpeg_quality=settings.jpeg_quality,
            move_interval_ms=settings.console_move_interval_ms,
            paint=settings.console_paint,
        )
        self.latency = LatencyRecorder()
        self.display = DisplayWatch(
            Region.parse(settings.game_region), hold_s=settings.black_hold_s
        )
        # X11 grabs, or the S2 frame bus in console mode with a live writer (capture_select.py).
        self.capture_source = CaptureSelector(
            capture_factory,
            bus_path=settings.framebus_path,
            console_mode=lambda: self.capture.backend == "console",
            console_fps=settings.console_fps,
        )
        self.hub = CaptureHub(
            lambda: self.capture_source,
            tuning=self.tuning,
            damage_factory=damage_factory,
            on_frame=self.latency.frame_encoded,
            on_grab=self.display.observe,
        )
        # ADR-0007: the packet feed for the console (never the agent, never the mux).
        self.packets = PacketHub()
        self.agents: set[Outbox] = set()
        self.rdp_window_present: bool | None = None
        self.stream_window_present: bool | None = None
        # The capture-backend lock (ADR-0009) and the clean room's status, re-read every tick.
        self.capture = read_lock(settings.lab_state_dir)
        self.cleanroom: CleanRoom | None = read_cleanroom(
            settings.lab_state_dir, self.capture, time.time()
        )
        # True from an automatic ASSIST restore until a human next sets the mode (Status).
        self.mode_restored = False
        self._restore_mode()
        self._status_task: asyncio.Task[None] | None = None
        self._background: set[asyncio.Task[Any]] = set()
        # Console connections with secret typing on (SecretInput). While any is on, human key
        # identities never reach the input log (redact_human).
        self._secret_connections: set[int] = set()
        self._inject_warned = 0.0
        self._inject_failures = 0

    # --- lifecycle --------------------------------------------------------------------------------

    def _restore_mode(self) -> None:
        """ADR-0002 amendment (2026-10-03): ASSIST, and only ASSIST, survives a GUARDED restart
        (scripts/guarded_build.py restart:backend wrote a fresh marker for an unchanged lock). Any
        other boot -- a crash, a host reboot, a plain restart -- stays HUMAN."""
        verdict = read_verdict(self.settings.lab_state_dir, self.capture, time.time())
        if not verdict.restore:
            if verdict.why != "no marker":
                log.warning("mux restore marker ignored (%s): booting HUMAN", verdict.why)
            return
        now = monotonic_ns()
        released = self.mux.set_mode(Mode.ASSIST, now)
        assert not released  # at boot nothing is held
        self.mode_restored = True
        self.input_log.write(
            InputLogRecord(
                t_mono_ns=now,
                t_wall=wall_clock_iso(),
                source="backend",
                mode=self.mux.mode,
                accepted=True,
                reason="mode_restore",
                synthetic=True,
                frame_id=-1,
                event={"type": "mode_restore", "mode": "ASSIST", "by": "guarded_build",
                       "why": verdict.why},
            )
        )  # fmt: skip
        log.warning("mux mode ASSIST restored automatically after a guarded restart (%s)",
                    verdict.why)  # fmt: skip

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
            self._read_lab_state()
            self.rdp_window_present = await self.injector.rdp_window_present()
            self.stream_window_present = await self.injector.stream_window_present()
            now = monotonic_ns()
            if self.capture.backend == "rdp":
                # Only RDP mode feeds the reconnect detector: a handover to the console (no
                # xfreerdp window, by design) must not read as an RDP reconnect.
                self.display.rdp(self.rdp_window_present, now)
            if self.display.needs_sample(now):
                await self.hub.sample_once()  # no console watching: keep the detector fed
            before = self.display.state
            after = self.display.evaluate()
            if after != before:
                level = logging.WARNING if "black" in (before, after) else logging.INFO
                log.log(level, "game display %s -> %s (%s)", before, after, self.display.snapshot())
            self.broadcast_status()
            await asyncio.sleep(period)

    def _read_lab_state(self) -> None:
        directory = self.settings.lab_state_dir
        self.capture = read_lock(directory)
        # Display only (the console's clean-room line): wall clock, like the file's unix times.
        self.cleanroom = read_cleanroom(directory, self.capture, time.time())

    # --- status -----------------------------------------------------------------------------------

    @property
    def rdp_mode(self) -> bool:
        """The RDP client owns the Windows session (ADR-0009 lock says `rdp`)."""
        return self.capture.backend == "rdp"

    def status(self) -> Status:
        now = monotonic_ns()
        return Status(
            t_mono_ns=now,
            frame_id=self.hub.last_frame_id,
            mode=self.mux.mode,
            lease_until_ns=self.mux.lease_until_ns(now),
            bot_connected=bool(self.agents),
            rdp_window_present=self.rdp_window_present,
            stream_window_present=self.stream_window_present,
            capture_backend=self.capture,
            cleanroom=self.cleanroom,
            capture_fps=round(self.hub.capture_fps, 2),
            viewers=self.hub.viewer_count,
            # Paste and \\tsclient ride the RDP session's channels: RDP mode only (ADR-0009).
            clipboard_enabled=self.clipboard is not None and self.rdp_mode,
            transfer_enabled=self.settings.transfer_enabled and self.rdp_mode,
            move_interval_ms=self.tuning.move_interval_ms,
            paint=self.tuning.paint,
            game_black=self.display.black,
            human_secret=self.human_secret,
            mode_restored=self.mode_restored,
        )

    def refused_snapshot(self) -> dict[str, dict[str, int]]:
        """``{source: {reason: count}}`` of mux refusals, for /health."""
        out: dict[str, dict[str, int]] = {}
        for (source, reason), count in sorted(self.refused.items()):
            out.setdefault(source, {})[reason] = count
        return out

    @property
    def human_secret(self) -> bool:
        return bool(self._secret_connections)

    def set_human_secret(self, connection: int, on: bool) -> None:
        """A console's secret-typing toggle (SecretInput). Status shows it to every viewer."""
        before = self.human_secret
        if on:
            self._secret_connections.add(connection)
        else:
            self._secret_connections.discard(connection)
        if self.human_secret != before:
            log.info("human secret typing %s", "ON" if self.human_secret else "off")
            self.broadcast_status()

    def redact_human(self, source: Source, event: dict[str, Any]) -> dict[str, Any]:
        """A human key while secret typing is on: type, action and timing only, never the code."""
        if source is not Source.HUMAN or not self.human_secret or event.get("type") != "key":
            return event
        return {
            "type": "key",
            "action": event.get("action"),
            "t_mono_ns": event.get("t_mono_ns"),
            "frame_id": event.get("frame_id"),
            "secret": True,
        }

    def broadcast_status(self) -> None:
        text = self.status().model_dump_json()
        self.hub.broadcast_control(text)
        for outbox in self.agents:
            outbox.offer_control(text)

    # --- input ------------------------------------------------------------------------------------

    async def set_mode(self, msg: SetMode) -> None:
        now = monotonic_ns()
        released = self.mux.set_mode(msg.mode, now)
        self.mode_restored = False  # a human has chosen the mode since
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
        records: Sequence[InputRecord] | None = None,
        sensitive: bool = False,
    ) -> list[Decision]:
        """Run ``events`` through the mux and inject what it allows. ``synthetic_reason`` marks
        events the backend generated on the source's behalf (e.g. the Ctrl+V of a paste).
        ``records`` (one per event) receive the decision and XTest-injection times (Phase 0).
        ``sensitive`` (credentials): one summary line in the input log, no key identities; the
        batch is refused unless it releases everything it presses."""
        now = monotonic_ns()
        if sensitive and not balanced(events):
            self.refused[(source.value, "sensitive_unbalanced")] += len(events)
            self._log_sensitive(source, events, 0, ["sensitive_unbalanced"], now)
            return [Decision(False, "sensitive_unbalanced") for _ in events]
        lease_before = self.mux.lease_active(now)
        decisions: list[Decision] = []
        routed: list[Routed] = []
        for event in events:
            decision = self.mux.submit(source, event, now)
            # Refused housekeeping (a disconnect's ReleaseAll for a source without control) is
            # still in the input log, but it is not a dropped input worth counting.
            if not decision.accepted and not isinstance(event, ReleaseAll):
                self.refused[(source.value, decision.reason)] += 1
            if not sensitive:
                self._log(
                    source,
                    self.redact_human(source, event.model_dump(mode="json")),
                    event.frame_id,
                    decision.accepted,
                    synthetic_reason if decision.accepted and synthetic_reason else decision.reason,
                    now,
                    synthetic=synthetic_reason is not None,
                )
                self._log_synthetic(decision.inject, now)
            decisions.append(decision)
            routed.extend(decision.inject)
        if sensitive:
            reasons = sorted({d.reason for d in decisions if not d.accepted})
            self._log_sensitive(source, events, sum(d.accepted for d in decisions), reasons, now)
        if records is not None:
            for record, decision in zip(records, decisions, strict=True):
                record.t_decided = now
                record.accepted = decision.accepted
        await self._inject(routed)
        if records is not None and routed:
            # X has processed the XTest requests (the injector syncs), or the S2 client's LiSend*
            # calls returned (the injector waits for its ack).
            injected = monotonic_ns()
            for record in records:
                if record.accepted:
                    record.t_injected = injected
        if self.mux.lease_active(now) != lease_before:
            self.broadcast_status()
        return decisions

    async def paste(self, msg: ClipboardPaste, *, browser: bool, client: str | None) -> PasteResult:
        """Human-only paste (ADR-0004). ``browser``: the connection presented an allowlisted
        Origin. Logged: the event and its time only -- no text, no length, no digest. Even a 12-hex
        sha256 prefix confirms a guessed password offline (ADR-0004 amendment c, decided by Batt
        2026-10-02)."""
        refusal: str | None = None
        if self.clipboard is None:
            refusal = "clipboard_disabled"
        elif not self.rdp_mode:
            # Console mode (ADR-0009): the Ctrl+V would reach Windows through Moonlight and paste
            # Windows' OWN clipboard, never this text. Hold: no session at all.
            refusal = "console_backend" if self.capture.backend == "console" else "backend_hold"
        elif not browser:
            refusal = "origin_required"
        elif self.mux.mode is Mode.BOT:
            refusal = "mode_bot"
        now = monotonic_ns()
        summary: dict[str, Any] = {"type": msg.type}
        if self.human_secret:
            summary["secret"] = True
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
            size=0,  # no length for a paste (amendment c): the event and its time only
            sha256=None,
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
            # Rate-limited (a dead sink fails every pointer move): the count is in /health.
            now = time.monotonic()
            self._inject_failures += 1
            if now - self._inject_warned >= 5.0:
                log.warning("input injection failed on the %s sink (%d since the last warning): %s",
                            self.injector.active, self._inject_failures, exc)  # fmt: skip
                self._inject_warned, self._inject_failures = now, 0

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

    def _log_sensitive(
        self,
        source: Source,
        events: Sequence[InputEvent],
        accepted: int,
        reasons: list[str],
        now: int,
    ) -> None:
        """One line for a whole sensitive batch: count and timing only, never key identities."""
        summary = {
            "type": "sensitive_batch",
            "events": len(events),
            "accepted": accepted,
            "t_first_ns": events[0].t_mono_ns,
            "t_last_ns": events[-1].t_mono_ns,
            "refused": reasons,
        }
        self._log(source, summary, events[0].frame_id, accepted > 0, "sensitive", now)

    def _log_synthetic(self, routed: Sequence[Routed], now: int) -> None:
        for r in routed:
            if r.synthetic:
                self._log(
                    r.source,
                    self.redact_human(r.source, r.event.model_dump(mode="json")),
                    r.event.frame_id,
                    True,
                    r.reason,
                    now,
                    synthetic=True,
                )
