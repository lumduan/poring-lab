import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from poring_env.protocol import (
    NO_FRAME,
    AgentHello,
    AgentInput,
    Box,
    Detections,
    FrameMeta,
    InputAck,
    Key,
    Mode,
    MouseButton,
    MouseMove,
    Ping,
    Pong,
    ReleaseAll,
    SetMode,
    Status,
    Wheel,
    json_schema,
    parse_agent_to_backend,
    parse_backend_to_agent,
    parse_backend_to_browser,
    parse_browser_to_backend,
    parse_input_event,
)

SCHEMA_FILE = Path(__file__).resolve().parents[1] / "schema" / "protocol.schema.json"

T = 1_000_000_000

BROWSER_TO_BACKEND: list[BaseModel] = [
    MouseMove(t_mono_ns=T, frame_id=7, x=0.25, y=0.5),
    MouseButton(t_mono_ns=T, frame_id=7, button="right", action="down", x=0.0, y=1.0),
    Wheel(t_mono_ns=T, frame_id=7, dy=-3),
    Key(t_mono_ns=T, frame_id=7, code="F1", action="down"),
    ReleaseAll(t_mono_ns=T),
    SetMode(t_mono_ns=T, mode=Mode.ASSIST),
    Ping(t_mono_ns=T),
]
BACKEND_TO_BROWSER: list[BaseModel] = [
    FrameMeta(
        t_mono_ns=T,
        frame_id=3,
        t_capture_ns=T - 5,
        t_encoded_ns=T - 1,
        width=1280,
        height=720,
        nbytes=4096,
    ),
    Status(
        t_mono_ns=T,
        mode=Mode.HUMAN,
        lease_until_ns=None,
        bot_connected=False,
        rdp_window_present=None,
        capture_fps=0.0,
        viewers=0,
    ),
    Detections(
        t_mono_ns=T,
        frame_id=3,
        t_capture_ns=T - 9,
        boxes=[Box(x1=0.1, y1=0.2, x2=0.3, y2=0.4, cls="poring", conf=0.9)],
    ),
    Pong(t_mono_ns=T, echo_t_mono_ns=12345),
]
AGENT_TO_BACKEND: list[BaseModel] = [
    AgentHello(t_mono_ns=T, agent_id="vision", version="0.1.0"),
    AgentInput(
        t_mono_ns=T,
        frame_id=9,
        t_capture_ns=T - 3,
        events=[MouseMove(t_mono_ns=T, frame_id=9, x=0.5, y=0.5)],
    ),
    Detections(t_mono_ns=T, frame_id=9, t_capture_ns=T - 3),
    Ping(t_mono_ns=T),
]
BACKEND_TO_AGENT: list[BaseModel] = [
    BACKEND_TO_BROWSER[1],
    InputAck(t_mono_ns=T, frame_id=9, accepted=1, dropped=2, reasons=["human_lease"]),
    Pong(t_mono_ns=T, echo_t_mono_ns=1),
]


@pytest.mark.parametrize(
    ("parse", "msg"),
    [(parse_browser_to_backend, m) for m in BROWSER_TO_BACKEND]
    + [(parse_backend_to_browser, m) for m in BACKEND_TO_BROWSER]
    + [(parse_agent_to_backend, m) for m in AGENT_TO_BACKEND]
    + [(parse_backend_to_agent, m) for m in BACKEND_TO_AGENT],
    ids=lambda v: getattr(v, "type", getattr(v, "__name__", "?")),
)
def test_round_trip_through_channel_union(parse: Any, msg: BaseModel) -> None:
    parsed = parse(msg.model_dump_json())
    assert type(parsed) is type(msg)
    assert parsed == msg


def test_every_message_carries_timestamp_and_frame_id() -> None:
    for msg in BROWSER_TO_BACKEND + BACKEND_TO_BROWSER + AGENT_TO_BACKEND + BACKEND_TO_AGENT:
        wire = json.loads(msg.model_dump_json())
        assert "t_mono_ns" in wire and "frame_id" in wire and "type" in wire, msg


def test_frame_id_defaults_to_no_frame() -> None:
    assert ReleaseAll(t_mono_ns=T).frame_id == NO_FRAME


def test_input_event_union_rejects_control_messages() -> None:
    with pytest.raises(ValidationError):
        parse_input_event(SetMode(t_mono_ns=T, mode=Mode.BOT).model_dump_json())


@pytest.mark.parametrize(
    "raw",
    [
        '{"type": "mouse_move", "t_mono_ns": 1, "frame_id": 0, "x": 1.5, "y": 0.5}',
        '{"type": "mouse_move", "t_mono_ns": -1, "frame_id": 0, "x": 0.5, "y": 0.5}',
        '{"type": "key", "t_mono_ns": 1, "frame_id": 0, "code": "Key A", "action": "down"}',
        '{"type": "key", "t_mono_ns": 1, "frame_id": 0, "code": "KeyA", "action": "hold"}',
        '{"type": "wheel", "t_mono_ns": 1, "frame_id": 0, "dy": 50}',
        '{"type": "teleport", "t_mono_ns": 1, "frame_id": 0}',
        '{"type": "ping", "t_mono_ns": 1, "frame_id": 0, "extra": true}',
    ],
)
def test_invalid_browser_messages_are_rejected(raw: str) -> None:
    with pytest.raises(ValidationError):
        parse_browser_to_backend(raw)


def test_agent_input_needs_at_least_one_event() -> None:
    with pytest.raises(ValidationError):
        AgentInput(t_mono_ns=T, t_capture_ns=T, events=[])


def test_committed_schema_matches_models() -> None:
    committed = json.loads(SCHEMA_FILE.read_text())
    assert committed == json_schema(), (
        "packages/poring_env/schema/protocol.schema.json is stale -- run scripts/gen_protocol.sh "
        "and commit the regenerated schema + services/frontend/src/lib/protocol.gen.ts"
    )


def test_schema_discriminants_are_required() -> None:
    defs = json_schema()["$defs"]
    for name in ("MouseMove", "Key", "FrameMeta", "Status", "AgentInput"):
        assert "type" in defs[name]["required"], name
        assert "frame_id" in defs[name]["required"], name
