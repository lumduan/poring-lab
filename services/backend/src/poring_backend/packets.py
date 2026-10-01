"""ADR-0007: the console's packet feed -- a hub with per-viewer bounded queues (drops counted).

Fed by ``/ingest/packets`` and read by ``/ws/packets`` (routes_packets.py). Nothing here is ever
offered to the agent channel or the input mux.
"""

import asyncio
from collections import deque
from typing import Any

from starlette.websockets import WebSocket

from poring_env.clock import monotonic_ns
from poring_packets.events import PacketStats

RECENT_EVENTS = 200  # replayed to a console tab when it connects
VIEWER_QUEUE = 512


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

    def publish(self, msg: Any) -> None:
        now = monotonic_ns()
        text: str = msg.model_dump_json()
        if isinstance(msg, PacketStats):
            self.stats_in += 1
            self.last_stats = text
            self.sniffer_ingest_dropped = msg.ingest_dropped
        else:
            self.events_in += 1
            self.recent.append(text)
            self.ingest_lag_ms = round((now - msg.t_mono_ns) / 1e6, 2)
        self.last_ingest_ns = now
        for viewer in self.viewers:
            viewer.offer(text)

    def add_viewer(self) -> PacketOutbox:
        outbox = PacketOutbox()
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
        return {
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
