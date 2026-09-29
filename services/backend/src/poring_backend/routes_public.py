"""LAN-facing routes (port 8000): health, the screen stream, human input."""

import asyncio
import contextlib
import logging
from typing import Any, cast

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from starlette.requests import HTTPConnection

from poring_backend.mux import Source
from poring_backend.state import AppState
from poring_backend.stream import pump
from poring_env.clock import monotonic_ns
from poring_env.protocol import Ping, Pong, SetMode, parse_browser_to_backend

log = logging.getLogger(__name__)
router = APIRouter()


def get_state(conn: HTTPConnection) -> AppState:
    return cast(AppState, conn.app.state.poring)


def origin_allowed(ws: WebSocket, state: AppState) -> bool:
    """Browsers always send Origin on WebSocket upgrades; scripts and the agent do not."""
    origin = ws.headers.get("origin")
    return origin is None or origin.rstrip("/") in state.settings.origins


async def stop_task(task: asyncio.Task[Any]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    state = get_state(request)
    pointer = await state.injector.pointer()
    return {
        "status": "ok",
        "mode": state.mux.mode,
        "x11": pointer is not None,
        "pointer": pointer,
        "rdp_window_present": state.rdp_window_present,
        "viewers": state.hub.viewer_count,
        "bot_connected": bool(state.agents),
        "capture_fps": round(state.hub.capture_fps, 2),
        "input_log_dir": str(state.input_log.directory),
    }


@router.websocket("/ws/stream")
async def ws_stream(ws: WebSocket) -> None:
    state = get_state(ws)
    if not origin_allowed(ws, state):
        await ws.close(code=1008, reason="origin not allowed")
        return
    await ws.accept()
    outbox = state.hub.add_viewer()
    outbox.offer_control(state.status().model_dump_json())
    sender = asyncio.create_task(pump(ws, outbox), name="stream-pump")
    try:
        while True:
            try:
                msg = parse_browser_to_backend(await ws.receive_text())
            except ValidationError as exc:
                log.debug("stream: ignoring invalid message: %s", exc)
                continue
            if isinstance(msg, Ping):
                pong = Pong(
                    t_mono_ns=monotonic_ns(), frame_id=msg.frame_id, echo_t_mono_ns=msg.t_mono_ns
                )
                outbox.offer_control(pong.model_dump_json())
    except WebSocketDisconnect:
        pass
    finally:
        state.hub.remove_viewer(outbox)
        await stop_task(sender)


@router.websocket("/ws/input")
async def ws_input(ws: WebSocket) -> None:
    state = get_state(ws)
    if not origin_allowed(ws, state):
        await ws.close(code=1008, reason="origin not allowed")
        return
    await ws.accept()
    try:
        while True:
            try:
                msg = parse_browser_to_backend(await ws.receive_text())
            except ValidationError as exc:
                log.debug("input: ignoring invalid message: %s", exc)
                continue
            match msg:
                case Ping():
                    pong = Pong(
                        t_mono_ns=monotonic_ns(),
                        frame_id=msg.frame_id,
                        echo_t_mono_ns=msg.t_mono_ns,
                    )
                    await ws.send_text(pong.model_dump_json())
                case SetMode():
                    await state.set_mode(msg)
                case _:
                    await state.submit_many(Source.HUMAN, [msg])
    except WebSocketDisconnect:
        pass
    finally:
        await state.release_source(Source.HUMAN)
