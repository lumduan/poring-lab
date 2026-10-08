"""Compose-network-only routes (port 8001, never published): the vision agent's channel."""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from poring_backend.drops import ReplyThrottle
from poring_backend.mux import Source
from poring_backend.routes_public import get_state, offer, read_message, stop_task
from poring_backend.stream import Outbox, pump
from poring_env.clock import monotonic_ns
from poring_env.protocol import (
    AgentHello,
    AgentInput,
    Detections,
    InputAck,
    OperatorHud,
    Ping,
    Pong,
    RoutePreview,
    parse_agent_to_backend,
    parse_display_to_backend,
)

log = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/internal/agent")
async def ws_agent(ws: WebSocket) -> None:
    state = get_state(ws)
    server = ws.scope.get("server")
    if not server or server[1] != state.settings.internal_port:
        await ws.close(code=1008, reason="internal listener only")
        return
    await ws.accept()
    outbox = Outbox()
    state.agents.add(outbox)
    sender = asyncio.create_task(pump(ws, outbox), name="agent-pump")
    state.broadcast_status()  # bot_connected flipped
    throttle = ReplyThrottle()
    reply = offer(outbox.offer_control)
    agent_id = ""
    try:
        while True:
            msg = await read_message(ws, parse_agent_to_backend, "agent", state, throttle, reply)
            match msg:
                case None:
                    continue
                case AgentHello():
                    log.info("agent %s (%s) connected", msg.agent_id, msg.version)
                    agent_id = msg.agent_id
                    state.agent_hello(outbox, msg)
                case AgentInput():
                    decisions = await state.submit_many(
                        Source.BOT, msg.events, sensitive=msg.sensitive
                    )
                    accepted = sum(d.accepted for d in decisions)
                    ack = InputAck(
                        t_mono_ns=monotonic_ns(),
                        frame_id=msg.frame_id,
                        accepted=accepted,
                        dropped=len(decisions) - accepted,
                        reasons=sorted({d.reason for d in decisions if not d.accepted}),
                    )
                    outbox.offer_control(ack.model_dump_json())
                case Detections() | RoutePreview() | OperatorHud():
                    # display only: relayed to viewers, never to the mux, never into the input log
                    state.hub.broadcast_control(msg.model_dump_json())
                    if isinstance(msg, OperatorHud):  # Status says what was relayed, and when
                        state.feed_relayed("hud", agent_id)
                    elif isinstance(msg, RoutePreview):
                        state.feed_relayed("route", agent_id)
                case Ping():
                    pong = Pong(
                        t_mono_ns=monotonic_ns(),
                        frame_id=msg.frame_id,
                        echo_t_mono_ns=msg.t_mono_ns,
                    )
                    outbox.offer_control(pong.model_dump_json())
    except WebSocketDisconnect:
        pass
    finally:
        state.agents.discard(outbox)
        await stop_task(sender)
        state.broadcast_status()
        await state.release_source(Source.BOT)


@router.websocket("/internal/display")
async def ws_display(ws: WebSocket) -> None:
    """The HUD SCENE process (scripts/hud_scene.py, Batt 2026-10-08): keyframes, deltas and the
    global motion, relayed to viewers. DISPLAY ONLY: the internal listener only, never the mux,
    never the input log, not an agent (no "bot connected"; any mux mode, so the HUD stays on while a
    human plays). Drops are never silent (the shared reader)."""
    state = get_state(ws)
    server = ws.scope.get("server")
    if not server or server[1] != state.settings.internal_port:
        await ws.close(code=1008, reason="internal listener only")
        return
    await ws.accept()
    throttle = ReplyThrottle()

    async def reply(text: str) -> None:
        await ws.send_text(text)

    try:
        while True:
            msg = await read_message(
                ws, parse_display_to_backend, "display", state, throttle, reply
            )
            if msg is None:
                continue
            state.hub.broadcast_control(msg.model_dump_json())
            state.feed_relayed("scene", "hud-scene")
    except WebSocketDisconnect:
        pass
