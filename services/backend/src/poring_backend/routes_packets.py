"""ADR-0007: the packet ground-truth feed -- sniffer -> backend -> the human console, nowhere else.

``/ingest/packets`` (internal listener :8001 only, and only from rathena's pinned address, where the
sniffer lives in rathena's network namespace) receives the sniffer's events and stats. It is
one-way: drops are counted and logged, never answered.

``/ws/packets`` (public listener :8000 only) fans them out to console tabs, with the backend's own
``PacketSource`` line (the source state: live / sniffer offline / external) at connect and every
second. It accepts only peers
on the LAN viewer networks (VIEWER_NETWORKS) with an allowlisted Origin: compose peers -- vision,
and the lab gateway through which a container reaching the published port is proxied -- are
refused, so the vision agent cannot read it even with a forged Origin. Every refusal is counted in
``/health`` ``dropped_messages.ws_packets``. The channel is receive-only.

Nothing here touches the input mux or the agent channel (tests pin that): packets are offline
ground truth and a human's view, never an input to a decision.
"""

import asyncio
import ipaddress
import logging
from typing import Any, NoReturn

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from pydantic_core import InitErrorDetails, PydanticCustomError

from poring_backend.drops import ReplyThrottle
from poring_backend.packets import pump_packets, tick_source
from poring_backend.routes_public import get_state, offer, read_message, stop_task
from poring_env.clock import monotonic_ns
from poring_packets.events import Attestation, parse_feed

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


def in_networks(host: str | None, networks: tuple[Any, ...]) -> bool:
    if host is None:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(address in net for net in networks)


def viewer_refusal(
    host: str | None, compose_subnet: str, viewer_nets: tuple[Any, ...]
) -> str | None:
    """Why a /ws/packets peer is refused, or None: only LAN viewer networks are accepted."""
    if in_networks(host, (ipaddress.ip_network(compose_subnet),)):
        return "compose_peer"  # vision, the sniffer, the lab gateway (host scripts, hairpin)
    if not in_networks(host, viewer_nets):
        return "not_a_lan_viewer"
    return None


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
            if isinstance(msg, Attestation):
                # ADR-0016: to the interlock ONLY -- never to a viewer, never to an agent.
                state.interlock.attested(msg, monotonic_ns())
                hub.attested()  # its receipt time only: the Packet timeline's source state
            elif msg is not None:
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
    elif (refusal := viewer_refusal(peer, cfg.compose_subnet, cfg.viewer_nets)) is not None:
        reason = refusal
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
    ticker = asyncio.create_task(tick_source(hub, outbox), name="packets-source")
    throttle = ReplyThrottle()
    try:
        while True:
            await read_message(ws, receive_only, "ws_packets", state, throttle, offer(outbox.offer))
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove_viewer(outbox)
        await stop_task(ticker)
        await stop_task(sender)
