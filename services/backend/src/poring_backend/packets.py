"""ADR-0007: the console's packet feed -- a hub with per-viewer bounded queues (drops counted).

Fed by ``/ingest/packets`` and read by ``/ws/packets`` (routes_packets.py). Nothing here is ever
offered to the agent channel or the input mux.

The SOURCE STATE (Batt 2026-10-09): every viewer also gets the backend's own ``PacketSource``
line, at connect and every SOURCE_TICK_S, so the console says "sniffer offline (no packets since
HH:MM:SS)" instead of showing an empty list that looks like "nothing happened".
"""

import asyncio
import time
from collections import deque
from typing import Any, Literal

from starlette.websockets import WebSocket

from poring_env.clock import monotonic_ns
from poring_packets.events import PacketSource, PacketStats

RECENT_EVENTS = 200  # replayed to a console tab when it connects
VIEWER_QUEUE = 512
# The sniffer's heartbeat: poring_packets/sniffer.py run() sends a PacketStats AND an Attestation
# on every 1.0 s tick (`next_tick = now + 1.0`, checked between 0.2 s capture reads), whatever the
# game does -- measured live 2026-10-09 ~14:55: 20 stats and 20 attestations in 20.1 s while the
# idle GM produced 2 game packets. Offline = 5 missed beats. That is under the interlock's
# attestation_max_age_s (10 s, config/environments.yaml), so the panel says so first.
SOURCE_STALE_MS = 5_000
SOURCE_TICK_S = 1.0  # the PacketSource line's own cadence, per viewer


def external_environment_active() -> bool:
    """HOOK, deliberately INERT (Batt 2026-10-09 ~14:40): whether the human now plays on an
    EXTERNAL server, whose packets are not captured by design. No such environment kind exists:
    the ADR that would define it (and how the backend knows) is PROPOSED, not accepted, and Batt
    holds the interlock / allowlist / firewall parts until he accepts it. So nothing that exists
    today can make the backend emit ``external``: no environment-store field, schema key or
    interlock signal is read here. The console already renders the state (PacketTimeline)."""
    return False


class PacketOutbox:
    """Per-viewer bounded queue. Overflow drops the OLDEST line and counts it (never silent)."""

    def __init__(self, max_queue: int = VIEWER_QUEUE) -> None:
        self._queue: deque[str] = deque()
        self._max = max_queue
        self._wake = asyncio.Event()
        self.dropped = 0

    def offer(self, text: str) -> None:
        if len(self._queue) >= self._max:
            self._queue.popleft()
            self.dropped += 1
        self._queue.append(text)
        self._wake.set()

    async def drain(self) -> list[str]:
        await self._wake.wait()
        self._wake.clear()
        out = list(self._queue)
        self._queue.clear()
        return out


async def pump_packets(ws: WebSocket, outbox: PacketOutbox) -> None:
    """The only task that sends on a /ws/packets socket."""
    while True:
        for text in await outbox.drain():
            await ws.send_text(text)


class PacketHub:
    def __init__(self) -> None:
        self.viewers: set[PacketOutbox] = set()
        self.recent: deque[str] = deque(maxlen=RECENT_EVENTS)
        self.last_stats: str | None = None
        self.ingest_connections = 0
        self.events_in = 0
        self.stats_in = 0
        self.last_ingest_ns: int | None = None
        self.ingest_lag_ms: float | None = None  # capture time -> backend receipt, same clock
        self.sniffer_ingest_dropped = 0
        self._dropped_by_gone_viewers = 0
        # the source state's inputs: receipt times only (monotonic for ages, wall for display)
        self.last_stats_ns: int | None = None
        self.last_attest_ns: int | None = None
        self.last_feed_wall_ns: int | None = None
        self.last_event_wall_ns: int | None = None

    def publish(self, msg: Any) -> None:
        now = monotonic_ns()
        wall = time.time_ns()
        text: str = msg.model_dump_json()
        if isinstance(msg, PacketStats):
            self.stats_in += 1
            self.last_stats = text
            self.sniffer_ingest_dropped = msg.ingest_dropped
            self.last_stats_ns = now
        else:
            self.events_in += 1
            self.recent.append(text)
            self.ingest_lag_ms = round((now - msg.t_mono_ns) / 1e6, 2)
            self.last_event_wall_ns = wall
        self.last_ingest_ns = now
        self.last_feed_wall_ns = wall
        for viewer in self.viewers:
            viewer.offer(text)

    def attested(self) -> None:
        """The sniffer's attestation arrived (it went to the interlock). Only its RECEIPT TIME is
        kept here: nothing of its content ever reaches a viewer (ADR-0016)."""
        self.last_attest_ns = monotonic_ns()
        self.last_feed_wall_ns = time.time_ns()

    def source(self, now_ns: int | None = None) -> PacketSource:
        """The Packet timeline's source state, from the sniffer's 1 Hz heartbeat (stats AND
        attestation, both fresh), never from the last game packet (an idle GM sends few)."""
        now = monotonic_ns() if now_ns is None else now_ns

        def age(t: int | None) -> int | None:
            return None if t is None else max(0, (now - t) // 1_000_000)

        stats_age, attest_age = age(self.last_stats_ns), age(self.last_attest_ns)
        beat = None if stats_age is None or attest_age is None else max(stats_age, attest_age)
        state: Literal["live", "sniffer_offline", "external"] = "sniffer_offline"
        if external_environment_active():
            state, reason = "external", "external_environment"
        elif self.last_feed_wall_ns is None:
            reason = "never_heard"
        elif self.ingest_connections <= 0:
            reason = "ingest_disconnected"
        elif stats_age is None or stats_age > SOURCE_STALE_MS:
            reason = "heartbeat_stale"
        elif attest_age is None or attest_age > SOURCE_STALE_MS:
            reason = "not_attesting"
        else:
            state, reason = "live", "ok"
        return PacketSource(
            t_mono_ns=now, state=state, reason=reason,
            ingest_connected=self.ingest_connections > 0, heartbeat_age_ms=beat,
            stale_after_ms=SOURCE_STALE_MS,
            last_feed_unix_ms=None if self.last_feed_wall_ns is None
            else self.last_feed_wall_ns // 1_000_000,
            last_event_unix_ms=None if self.last_event_wall_ns is None
            else self.last_event_wall_ns // 1_000_000,
        )  # fmt: skip

    def add_viewer(self) -> PacketOutbox:
        outbox = PacketOutbox()
        outbox.offer(self.source().model_dump_json())  # the source state first, then the replay
        if self.last_stats is not None:
            outbox.offer(self.last_stats)
        for text in self.recent:
            outbox.offer(text)
        self.viewers.add(outbox)
        return outbox

    def remove_viewer(self, outbox: PacketOutbox) -> None:
        if outbox in self.viewers:
            self._dropped_by_gone_viewers += outbox.dropped
        self.viewers.discard(outbox)

    def snapshot(self) -> dict[str, Any]:
        now = monotonic_ns()
        source = self.source(now)
        return {
            "source": source.state,
            "source_reason": source.reason,
            "ingest_connected": self.ingest_connections > 0,
            "events_in": self.events_in,
            "stats_in": self.stats_in,
            "last_ingest_s_ago": (
                None if self.last_ingest_ns is None else round((now - self.last_ingest_ns) / 1e9, 1)
            ),
            "ingest_lag_ms": self.ingest_lag_ms,
            "sniffer_ingest_dropped": self.sniffer_ingest_dropped,
            "viewers": len(self.viewers),
            "viewer_dropped": self._dropped_by_gone_viewers + sum(v.dropped for v in self.viewers),
        }


async def tick_source(hub: PacketHub, outbox: PacketOutbox) -> None:
    """One viewer's PacketSource line every SOURCE_TICK_S (add_viewer sent the first): the state
    is re-sent even when nothing arrives, which is the point -- an offline sniffer sends nothing."""
    while True:
        await asyncio.sleep(SOURCE_TICK_S)
        outbox.offer(hub.source().model_dump_json())
