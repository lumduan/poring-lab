"""LAN-facing routes (port 8000): health, the screen stream, human input."""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Any, Literal, cast

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from starlette.requests import HTTPConnection

from poring_backend.drops import Channel, ReplyThrottle, drop_reason, message_type
from poring_backend.mux import Source
from poring_backend.state import AppState
from poring_backend.stream import pump
from poring_env.clock import monotonic_ns
from poring_env.protocol import (
    ClipboardPaste,
    ErrorReply,
    InputEvent,
    Key,
    MouseButton,
    Ping,
    Pong,
    SecretInput,
    SetMode,
    ViewerTiming,
    parse_browser_to_backend,
)

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


async def read_message[M](
    ws: WebSocket,
    parse: Callable[[str | bytes], M],
    channel: Channel,
    state: AppState,
    throttle: ReplyThrottle,
    reply: Callable[[str], Awaitable[None]],
) -> M | None:
    """The next message, or None for a drop -- which is never silent: counted (/health), logged
    (rate-limited WARNING) and answered with an ErrorReply (throttled per connection)."""
    message = await ws.receive()
    if message["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(message.get("code", 1000))
    text = message.get("text")
    if text is None:
        reason, ref_type = "binary_frame", None
    else:
        try:
            return parse(text)
        except ValidationError as exc:
            reason, ref_type = drop_reason(exc), message_type(text)
    state.drops.record(channel, reason, ref_type)
    if throttle.allow():
        error = ErrorReply(
            t_mono_ns=monotonic_ns(), channel=channel, reason=reason, ref_type=ref_type
        )
        await reply(error.model_dump_json())
    return None


def input_kind(event: InputEvent) -> str:
    if isinstance(event, Key):
        return f"key:{event.code}:{event.action}"
    if isinstance(event, MouseButton):
        return f"button:{event.button}:{event.action}"
    return event.type


def offer(outbox_offer: Callable[[str], None]) -> Callable[[str], Awaitable[None]]:
    """Adapt a sync Outbox.offer_control to read_message's async reply."""

    async def send(text: str) -> None:
        outbox_offer(text)

    return send


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    state = get_state(request)
    pointer = await state.injector.pointer()
    now = monotonic_ns()
    last_human = state.mux.last_human_input_ns()
    return {
        "status": "ok",
        "mode": state.mux.mode,
        # Is a human at the console right now? (the clean-room watchdog defers to it, 2026-10-03)
        "lease_active": state.mux.lease_active(now),
        "last_human_input_age_s": (
            None if last_human is None else round((now - last_human) / 1e9, 1)
        ),
        "x11": pointer is not None,
        "pointer": pointer,
        # The Windows session's area at the screen's top-left ("" = the whole screen): frames are
        # cropped to it and input is normalised over it (ADR-0009 amendment, 2026-10-02).
        "session_size": state.settings.session_size,
        "rdp_window_present": state.rdp_window_present,
        "stream_window_present": state.stream_window_present,
        # ADR-0009: who owns the ONE Windows session (scripts/capture_backend.py status).
        "capture_backend": state.capture.model_dump(),
        "viewers": state.hub.viewer_count,
        "bot_connected": bool(state.agents),
        "capture_fps": round(state.hub.capture_fps, 2),
        "stream_fps_target": round(state.hub.target_fps, 2),
        "frames_skipped_late": state.hub.frames_skipped_late,
        "input_log_dir": str(state.input_log.directory),
        "dropped_messages": state.drops.snapshot(),
        "input_refused": state.refused_snapshot(),
        "clipboard": {
            "enabled": state.clipboard is not None,
            # Paste needs the RDP session's clipboard channel: not in console mode (ADR-0009).
            "paste_available": state.clipboard is not None and state.rdp_mode,
            "x_connected": state.clipboard.connected if state.clipboard else False,
            "foreign_owner_clears": state.clipboard.foreign_owner_clears if state.clipboard else 0,
            "rdp_empty_claims": state.clipboard.rdp_empty_claims if state.clipboard else 0,
            "scrub_incomplete": state.clipboard.scrub_incomplete if state.clipboard else 0,
        },
        "transfer_enabled": state.settings.transfer_enabled and state.rdp_mode,
        "stream": {
            **asdict(state.tuning),
            "damage_active": state.hub.damage_active,
            "damage_events": state.hub.damage_events,
            "grabs_on_damage": state.hub.grabs_on_damage,
            "grabs_keepalive": state.hub.grabs_keepalive,
            "frames_dropped_slow_viewer": state.hub.frames_dropped_slow_viewer,
        },
        "latency": state.latency.summary(window_ns=30_000_000_000, now=monotonic_ns()),
        "game_display": state.display.snapshot(),
        "packets": state.packets.snapshot(),
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
    sender = asyncio.create_task(pump(ws, outbox, state.latency.frame_sent), name="stream-pump")
    throttle = ReplyThrottle()
    reply = offer(outbox.offer_control)
    try:
        while True:
            msg = await read_message(
                ws, parse_browser_to_backend, "ws_stream", state, throttle, reply
            )
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
    # A browser always sends Origin (checked against the allowlist above); scripts and the agent do
    # not. The human-only clipboard requires a browser connection (ADR-0004).
    browser = ws.headers.get("origin") is not None
    client = ws.client.host if ws.client else None
    # Phase 0: a browser tab's clock maps onto ours by the offset in its ViewerTiming reports.
    # Script clients (no Origin) are assumed to run on this host, i.e. on our clock already.
    clock: Literal["host", "browser"] = "browser" if browser else "host"
    offset_ns: int | None = None
    await ws.accept()
    throttle = ReplyThrottle()
    pastes: set[asyncio.Task[None]] = set()

    async def paste(msg: ClipboardPaste) -> None:
        result = await state.paste(msg, browser=browser, client=client)
        with contextlib.suppress(Exception):  # the socket may have closed meanwhile
            await ws.send_text(result.model_dump_json())

    try:
        while True:
            msg = await read_message(
                ws, parse_browser_to_backend, "ws_input", state, throttle, ws.send_text
            )
            match msg:
                case None:
                    continue
                case ClipboardPaste():
                    # A paste takes up to a few seconds: never stall the input stream behind it.
                    task = asyncio.create_task(paste(msg), name="clipboard-paste")
                    pastes.add(task)
                    task.add_done_callback(pastes.discard)
                case Ping():
                    pong = Pong(
                        t_mono_ns=monotonic_ns(),
                        frame_id=msg.frame_id,
                        echo_t_mono_ns=msg.t_mono_ns,
                    )
                    await ws.send_text(pong.model_dump_json())
                case SetMode():
                    await state.set_mode(msg)
                case ViewerTiming():
                    if msg.offset_ns is not None:
                        offset_ns = msg.offset_ns
                    state.latency.viewer_timing(msg)
                case SecretInput():
                    state.set_human_secret(id(ws), msg.on)
                case _:
                    kind = input_kind(msg)
                    if state.human_secret and isinstance(msg, Key):
                        kind = f"key:secret:{msg.action}"  # the latency ring never keeps the code
                    record = state.latency.input_received(
                        kind, msg.t_mono_ns, monotonic_ns(), clock, offset_ns
                    )
                    await state.submit_many(Source.HUMAN, [msg], records=[record])
    except WebSocketDisconnect:
        pass
    finally:
        for task in list(pastes):
            await stop_task(task)
        await state.release_source(Source.HUMAN)
        # Only after the release: its synthetic key releases are still logged redacted.
        state.set_human_secret(id(ws), False)
