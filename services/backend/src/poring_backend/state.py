"""Process-wide backend state: the mux, the single XTest writer, the input log, the stream hub."""

import asyncio
import collections
import contextlib
import logging
import os
import time
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Protocol, TypeVar

from poring_backend import allowlist, envstore
from poring_backend.capture_lock import read_alarms, read_cleanroom, read_lock, read_window
from poring_backend.capture_select import CaptureSelector
from poring_backend.clipboard import ClipboardService, PasteOutcome, SelectionIO
from poring_backend.config import Settings
from poring_backend.display import DisplayWatch, Region
from poring_backend.drops import DropCounter
from poring_backend.foreground import ForegroundGate
from poring_backend.freshness_monitor import StallMonitor
from poring_backend.grabsource import GrabSource
from poring_backend.input_log import InputLog, InputLogRecord, wall_clock_iso
from poring_backend.interlock import Interlock, Verdict, Window, load_config
from poring_backend.latency import InputRecord, LatencyRecorder
from poring_backend.mode_restore import read_verdict
from poring_backend.mux import Decision, InputMux, Routed, Source
from poring_backend.packets import PacketHub
from poring_backend.rdp_bus import RdpBusWriter
from poring_backend.rdp_bus import enabled as rdp_bus_enabled
from poring_backend.stream import CaptureHub, ChangeWatcher, Outbox, StreamTuning
from poring_backend.transfer_log import TransferLog
from poring_env.clock import monotonic_ns
from poring_env.env import FrameSource
from poring_env.protocol import (
    AgentHello,
    CleanRoom,
    ClipboardPaste,
    DisplayFeed,
    ForegroundStatus,
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


class RateLimit:
    """At most ``limit`` events per client in a sliding ``window_s`` (Settings writes)."""

    def __init__(self, *, limit: int, window_s: float) -> None:
        self.limit, self.window_s = limit, window_s
        self._seen: dict[str, collections.deque[float]] = {}

    def allow(self, client: str, now: float) -> bool:
        q = self._seen.setdefault(client, collections.deque())
        while q and now - q[0] > self.window_s:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


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
        rdp_grab_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.settings = settings
        # The RDP frame bus (rdp_bus.py, Batt 2026-10-08): ONE X grabber for every consumer on the
        # RDP path. Production passes the grab factory (main.py); without it, X as before.
        self.rdp_bus: RdpBusWriter | None = None
        if rdp_grab_factory is not None and rdp_bus_enabled():
            self.rdp_bus = RdpBusWriter(
                rdp_grab_factory(),
                ring=settings.rdp_ring_path,
                lab_state=settings.lab_state_dir,
                damage_factory=damage_factory,
                lock_backend=lambda: self.capture.backend,
            )
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
            rdp_bus_path=settings.rdp_ring_path if self.rdp_bus is not None else None,
            rdp_mode=lambda: self.capture.backend == "rdp",
        )
        self.hub = CaptureHub(
            lambda: self.capture_source,
            tuning=self.tuning,
            damage_factory=damage_factory,
            on_frame=self.latency.frame_encoded,
            on_grab=self.display.observe,
        )
        # The frame-age guard's /health side: stalls of the S2 bus (2026-10-04).
        self.stalls = StallMonitor(
            settings.framebus_path, console_mode=lambda: self.capture.backend == "console"
        )
        # ADR-0007: the packet feed for the console (never the agent, never the mux).
        self.packets = PacketHub()
        self.agents: set[Outbox] = set()
        self.rdp_window_present: bool | None = None
        self.stream_window_present: bool | None = None
        # The capture-backend lock (ADR-0009) and the clean room's status, re-read every tick.
        self.capture = read_lock(settings.lab_state_dir)
        self.alarms: list[str] = read_alarms(settings.lab_state_dir)
        self.cleanroom: CleanRoom | None = read_cleanroom(
            settings.lab_state_dir, self.capture, time.time()
        )
        # True from an automatic ASSIST restore until a human next sets the mode (Status).
        self.mode_restored = False
        # Display overlays relayed to viewers (HUD, live route preview): count, last time, sender
        self.feeds: dict[str, tuple[int, int | None, str]] = {}
        # The USER-MANAGED environment set (Settings page; human-only writes; envstore.py). Its
        # audit log is opened first: the interlock's first read may seed the store (audited).
        self.allowlist_audit = allowlist.AuditLog(settings.settings_dir)
        self.envset_lock = asyncio.Lock()
        self.allowlist_resolved: dict[str, list[str]] = {}  # allowed names -> current IPs
        self.forbidden_resolved: dict[str, list[str]] = {}  # forbidden NAMES -> current IPs
        self.allowlist_resolved_at_ns: int | None = None
        self._env_cache: tuple[Any, Any] | None = None  # (store key, its interlock config)
        # Settings writes: a per-process CSRF secret and a per-client rate limit (2026-10-06).
        self.csrf_secret = os.urandom(32)
        self.settings_rate = RateLimit(limit=20, window_s=60.0)
        # ADR-0016: the environment interlock (the user-managed set + attestation + window).
        self.interlock = Interlock(settings.environments_file, settings.win_host,
                                   source=self._envset_source)  # fmt: skip
        # The typing-only foreground gate (2026-10-06): bot TYPING needs the client in front.
        self.foreground = ForegroundGate(
            settings.settings_dir,
            Region.parse(settings.game_region),
            lambda: (
                GrabSource(
                    settings.display,
                    lab_state=settings.lab_state_dir,
                    ring=settings.framebus_path,
                    rdp_ring=settings.rdp_ring_path,
                ).grab
            ),
        )
        self._restore_mode()
        self.verdict: Verdict = self.env_verdict(monotonic_ns())
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
        log.warning("mux mode ASSIST restored automatically after a guarded restart/recreate (%s)",
                    verdict.why)  # fmt: skip

    async def start(self) -> None:
        self.stalls.start()
        if self.rdp_bus is not None:
            self.rdp_bus.start()
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
        if self.rdp_bus is not None:
            await asyncio.to_thread(self.rdp_bus.stop)
        await asyncio.to_thread(self.stalls.stop)
        await self.injector.close()
        if self.clipboard is not None:
            await asyncio.to_thread(self.clipboard.stop)
        self.input_log.close()
        self.transfer_log.close()
        self.allowlist_audit.close()
        self.foreground.close()

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
            await self._interlock_tick(now)
            self._maybe_resolve(now)
            self.broadcast_status()
            await asyncio.sleep(period)

    # --- the server allowlist (Settings page) ----------------------------------------------------

    STORE_ERRORS = {
        "no_dir": "settings_store_missing",
        "missing": "environments_store_missing",
        "invalid": "environments_store_invalid",
    }

    def _envset_source(self) -> tuple[Any, Any, str]:
        """The interlock's config: the user-managed set ONLY. An empty store is seeded ONCE from
        the shipped defaults (audited); after that a missing or invalid store fails closed."""
        directory = self.settings.settings_dir
        state = envstore.state_of(directory)
        if state == "unseeded":
            defaults, error = load_config(self.settings.environments_file)
            if defaults is None:
                return ("no_defaults", error), None, error or "config_missing"
            sha = envstore.file_sha(self.settings.environments_file)
            es = envstore.seed(directory, defaults, sha)
            self.allowlist_audit.write(
                action="seed", kind=None, env_id=None, entry=None, revision_before=None,
                revision_after=es.revision, before=None, after=[e.id for e in es.environments],
                ok=True, reason="seeded", client=None, origin=None, listener=None,
                note=f"the shipped defaults (environments.yaml sha256 {sha[:12]})",
            )  # fmt: skip
            log.warning("environment set seeded from the shipped defaults (sha256 %s)", sha[:12])
            state = "ok"
        if state != "ok":
            return (state,), None, self.STORE_ERRORS[state]
        path = directory / envstore.STORE_NAME
        st = path.stat()
        key = ("ok", st.st_mtime_ns, st.st_size)
        if self._env_cache is None or self._env_cache[0] != key:
            self._env_cache = (key, envstore.to_config(envstore.load(directory)))
        return key, self._env_cache[1], ""

    def envset(self) -> tuple[envstore.EnvSet | None, str]:
        """(the set, "") or (None, why): a missing or invalid store refuses every change."""
        state = envstore.state_of(self.settings.settings_dir)
        if state != "ok":
            return None, self.STORE_ERRORS.get(state, "environments_store_unseeded")
        return envstore.load(self.settings.settings_dir), ""

    def forbidden(self) -> allowlist.Forbidden:
        es, _ = self.envset()
        if es is None:
            return allowlist.Forbidden(frozenset(), frozenset())
        return envstore.forbidden(es, self.forbidden_resolved)

    def _maybe_resolve(self, now_ns: int) -> None:
        """Re-resolve the set's DNS names every ALLOWLIST_RESOLVE_S, in the background."""
        last = self.allowlist_resolved_at_ns
        if last is not None and now_ns - last < self.settings.allowlist_resolve_s * 1e9:
            return
        self.allowlist_resolved_at_ns = now_ns
        task = asyncio.create_task(self.resolve_allowlist(), name="allowlist-resolve")
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def resolve_allowlist(self) -> None:
        """Re-resolve the allowed DNS names AND the forbidden names (Batt, 2026-10-06: the page
        shows their current IPs and warns when a forbidden one sits in a CDN range)."""
        from poring_backend.routes_settings import resolve

        es, _ = self.envset()
        if es is None:
            return
        for env in es.environments:
            for s in env.servers:
                if s.host.startswith(".") or s.host.replace(".", "").isdigit():
                    continue
                forbidden = env.type == "forbidden"
                cache = self.forbidden_resolved if forbidden else self.allowlist_resolved
                cache[s.host] = await resolve(s.host)

    def allowlist_snapshot(self) -> dict[str, Any]:
        """/health: the user-managed set's state, revision and counts (no addresses)."""
        es, error = self.envset()
        last = self.allowlist_resolved_at_ns
        return {
            "store": error or "ok",
            "revision": es.revision if es is not None else None,
            "environments": {e.id: f"{e.type}:{len(e.servers)}" for e in es.environments}
            if es is not None
            else {},
            "resolved_age_s": None if last is None else round((monotonic_ns() - last) / 1e9, 1),
        }

    def env_verdict(self, now_ns: int) -> Verdict:
        """The interlock, read FRESH (the lock and the window file, not the last tick's copy): the
        mux must never act on a stale green."""
        directory = self.settings.lab_state_dir
        lock = read_lock(directory)
        cfg = self.interlock.config
        max_s = cfg.window_max_s if cfg is not None else 0.0
        raw = read_window(directory, lock, time.time(), max_s) if max_s else None
        window = None if raw is None else Window(raw[0], raw[1], raw[2], raw[3])
        return self.interlock.verdict(self.mux.mode, lock, window, now_ns)

    def agent_hello(self, outbox: Outbox, msg: AgentHello) -> None:
        """Name the connection (Status.bot_agents, the console notice) and put WHO acts as the bot
        into the input log: the bot's events carry only source=bot (2026-10-04, the auto GM
        recover after a sniffer restart logs as agent `auto_recover`)."""
        outbox.agent_id = msg.agent_id
        now = monotonic_ns()
        event = {"type": "agent_hello", "agent_id": msg.agent_id, "version": msg.version}
        self._log(Source.BOT, event, msg.frame_id, True, "agent_hello", now)
        self.broadcast_status()

    @property
    def bot_agents(self) -> list[str]:
        return sorted({o.agent_id for o in self.agents if o.agent_id})

    async def _interlock_tick(self, now_ns: int) -> None:
        """Re-read the allowlist when it changed; when bot presses stop being allowed, the bot
        lets go of everything it holds (the set_mode pattern)."""
        self.interlock.reload()
        before, after = self.verdict, self.env_verdict(now_ns)
        self.verdict = after
        if before.status().state != after.status().state or before.reason != after.reason:
            log.info("interlock: %s (%s) -> %s (%s)", before.status().state, before.reason,
                     after.status().state, after.reason)  # fmt: skip
        if not after.bot_allowed and self.mux.holds_anything(Source.BOT):
            released = self.mux.release_bot(now_ns)
            self._log_synthetic(released, now_ns)
            await self._inject(released)

    def _read_lab_state(self) -> None:
        directory = self.settings.lab_state_dir
        self.capture = read_lock(directory)
        self.alarms = read_alarms(directory)
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
            alarms=self.alarms,
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
            environment=self.verdict.status(),
            foreground=self.foreground_status(),
            bot_agents=self.bot_agents,
            hud_feed=self.feed_status("hud", now),
            route_feed=self.feed_status("route", now),
            scene_feed=self.feed_status("scene", now),
        )

    def feed_relayed(self, kind: str, source: str) -> None:
        """A display message (``hud`` / ``route``) was relayed to viewers (Status shows it)."""
        n, _, _ = self.feeds.get(kind, (0, None, ""))
        self.feeds[kind] = (n + 1, monotonic_ns(), source[:64])

    def feed_status(self, kind: str, now: int) -> DisplayFeed:
        n, last, source = self.feeds.get(kind, (0, None, ""))
        age = None if last is None else max(0, (now - last) // 1_000_000)
        return DisplayFeed(relayed=n, age_ms=age, source=source)

    def foreground_status(self) -> ForegroundStatus:
        snap = self.foreground.snapshot()
        return ForegroundStatus(
            state=snap["state"], reason=snap["reason"], distance=snap["distance"],
            age_ms=snap["age_ms"], path=snap["path"], since_s=snap["since_s"],
            refused=sum(snap["refused"].values()),
        )  # fmt: skip

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
        status = self.status()
        self.hub.broadcast_control(status.model_dump_json())
        if self.agents:
            # ADR-0016: the agent sees only its refusals, never the interlock's state.
            agent_text = status.model_copy(
                update={"environment": None, "foreground": None}
            ).model_dump_json()
            for outbox in self.agents:
                outbox.offer_control(agent_text)

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
        # ADR-0016: decided ONCE per batch, fresh; human input is never gated.
        bot_allowed = True
        if source is Source.BOT:
            self.verdict = self.env_verdict(now)
            bot_allowed = self.verdict.bot_allowed
        if sensitive and not bot_allowed and not self.mux.lease_active(now):
            self.refused[(source.value, "environment_unattested")] += len(events)
            self._log_sensitive(source, events, 0, ["environment_unattested"], now)
            return [Decision(False, "environment_unattested") for _ in events]
        # The TYPING-ONLY foreground gate (2026-10-06): a bot batch that presses a key needs the
        # client in front on a fresh frame. Clicks, moves, the wheel and releases never ask.
        gate = await self._foreground_gate(source, events, bot_allowed, now)
        if gate is not None and sensitive:
            self.refused[(source.value, gate)] += len(events)
            self._log_sensitive(source, events, 0, [gate], now)
            released = self.mux.release_bot_keys(now)
            self._log_synthetic(released, now)
            await self._inject(released)
            return [Decision(False, gate) for _ in events]
        lease_before = self.mux.lease_active(now)
        decisions: list[Decision] = []
        routed: list[Routed] = []
        if gate is not None:  # let go of the keys the bot already holds, before anything else
            released = self.mux.release_bot_keys(now)
            self._log_synthetic(released, now)
            routed.extend(released)
        for event in events:
            if gate is not None and isinstance(event, Key):
                decision = Decision(False, gate)
            else:
                decision = self.mux.submit(source, event, now, bot_allowed=bot_allowed)
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

    async def _foreground_gate(
        self, source: Source, events: Sequence[InputEvent], bot_allowed: bool, now: int
    ) -> str | None:
        """None: the batch may type (or does not type); else the refusal reason for its keys.
        Looked at only when the interlock lets the batch through anyway."""
        if source is not Source.BOT or not bot_allowed or self.mux.mode is Mode.HUMAN:
            return None  # the mux refuses this batch anyway (mode, interlock): nothing to look at
        if not any(isinstance(e, Key) and e.action == "down" for e in events):
            return None
        window = self.verdict.window
        if window is not None and window.kind == "desktop" and self.mux.mode is Mode.ASSIST:
            # Batt's answer 1: the agent's own console (ro_agent lines, capture_backend's TSCON).
            self.foreground.note_exempt()
            self._log(Source.BOT, {"type": "foreground", "result": "exempt", "window": "desktop"},
                      -1, True, "foreground_exempt_desktop_window", now)  # fmt: skip
            return None
        check = await self.foreground.check_async()
        if check.ok:
            return None
        log.warning("bot typing refused: %s (distance %s, frame %s ms, %s)", check.reason,
                    check.distance, check.age_ms, check.path)  # fmt: skip
        return check.reason

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
        when the connection handler is being cancelled (server shutdown, test client teardown).

        Holding nothing, there is nothing to release and nothing is submitted (Batt, 2026-10-07,
        console A): in ASSIST a human ReleaseAll takes the lease and makes the bot let go, so a
        console tab that merely closed or reconnected used to interrupt the bot."""
        if not self.mux.holds_anything(source):
            return
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
