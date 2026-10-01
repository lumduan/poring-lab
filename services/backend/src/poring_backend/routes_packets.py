"""ADR-0007: the packet ground-truth feed -- sniffer -> backend -> the human console, nowhere else.

``/ingest/packets`` (internal listener :8001 only, and only from rathena's pinned address, where the
sniffer lives in rathena's network namespace) receives the sniffer's events and stats. It is
one-way: drops are counted and logged, never answered.

``/ws/packets`` (public listener :8000 only) fans them out to console tabs. It refuses compose
peers (anything on the lab network except the gateway, through which host scripts arrive) and any
connection without an allowlisted Origin, so the vision agent cannot read it. Every refusal is
counted in ``/health`` ``dropped_messages.ws_packets``. The channel is receive-only.

Nothing here touches the input mux or the agent channel (tests pin that): packets are offline
ground truth and a human's view, never an input to a decision.
"""

import asyncio
import ipaddress
import logging
from typing import NoReturn

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from pydantic_core import InitErrorDetails, PydanticCustomError

from poring_backend.drops import ReplyThrottle
from poring_backend.packets import pump_packets
from poring_backend.routes_public import get_state, offer, read_message, stop_task
from poring_packets.events import parse_feed

log = logging.getLogger(__name__)
router = APIRouter()


def receive_only(_raw: str | bytes) -> NoReturn:
    """Parser for /ws/packets: the console never sends, so every inbound message is a drop."""
    error = InitErrorDetails(
        type=PydanticCustomError("receive_only", "this channel is receive-only"),
        loc=(),
        input=None,
    )
    raise ValidationError.from_exception_data("ws_packets", [error])


def compose_peer(host: str | None, subnet: str, gateway: str) -> bool:
    """A container on the lab network (not the gateway, through which host scripts arrive)."""
    if host is None or host == gateway:
        return False
    try:
        return ipaddress.ip_address(host) in ipaddress.ip_network(subnet)
    except ValueError:
        return False


async def _no_reply(_text: str) -> None:
    """/ingest/packets is one-way: the sniffer never reads, so replies would only back up."""


@router.websocket("/ingest/packets")
async def ingest_packets(ws: WebSocket) -> None:
    state = get_state(ws)
    server = ws.scope.get("server")
    peer = ws.client.host if ws.client else None
    reason = None
    if not server or server[1] != state.settings.internal_port:
        reason = "public_listener"
    elif peer != state.settings.ingest_peer:
        reason = "wrong_peer"
    if reason is not None:
        state.drops.record("ingest", reason, "connect")
        await ws.close(code=1008, reason=reason)
        return
    await ws.accept()
    hub = state.packets
    hub.ingest_connections += 1
    log.info("packet ingest connected")
    throttle = ReplyThrottle()
    try:
        while True:
            msg = await read_message(ws, parse_feed, "ingest", state, throttle, _no_reply)
            if msg is not None:
                hub.publish(msg)
    except WebSocketDisconnect:
        pass
    finally:
        hub.ingest_connections -= 1
        log.info("packet ingest disconnected")


@router.websocket("/ws/packets")
async def ws_packets(ws: WebSocket) -> None:
    state = get_state(ws)
    cfg = state.settings
    server = ws.scope.get("server")
    peer = ws.client.host if ws.client else None
    origin = ws.headers.get("origin")
    reason = None
    if not server or server[1] != cfg.public_port:
        reason = "internal_listener"
    elif compose_peer(peer, cfg.compose_subnet, cfg.compose_gateway):
        reason = "compose_peer"
    elif origin is None:
        reason = "origin_missing"
    elif origin.rstrip("/") not in cfg.origins:
        reason = "origin_not_allowed"
    if reason is not None:
        state.drops.record("ws_packets", reason, "connect")
        await ws.close(code=1008, reason=reason)
        return
    await ws.accept()
    hub = state.packets
    outbox = hub.add_viewer()
    sender = asyncio.create_task(pump_packets(ws, outbox), name="packets-pump")
    throttle = ReplyThrottle()
    try:
        while True:
            await read_message(ws, receive_only, "ws_packets", state, throttle, offer(outbox.offer))
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove_viewer(outbox)
        await stop_task(sender)
