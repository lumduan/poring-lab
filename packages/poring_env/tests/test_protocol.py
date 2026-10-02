import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from poring_env.protocol import (
    NO_FRAME,
    PASTE_MAX_BYTES,
    AgentHello,
    AgentInput,
    Box,
    ClipboardPaste,
    Detections,
    ErrorReply,
    FrameMeta,
    InputAck,
    Key,
    Mode,
    MouseButton,
    MouseMove,
    PasteResult,
    Ping,
    Pong,
    ReleaseAll,
    SecretInput,
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
    ClipboardPaste(t_mono_ns=T, request_id=1, text="hello สวัสดี\nline 2"),
    SecretInput(t_mono_ns=T, on=True),
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
    PasteResult(t_mono_ns=T, request_id=1, ok=True, reason="ok", chars=17),
    ErrorReply(t_mono_ns=T, channel="ws_input", reason="missing:key.t_mono_ns", ref_type="key"),
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
    ErrorReply(t_mono_ns=T, channel="agent", reason="json_invalid"),
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


# --- ADR-0004: the clipboard is on the browser channel only ---------------------------------


def _reachable_defs(schema: dict[str, Any], start: dict[str, Any]) -> set[str]:
    """Every $defs name reachable from ``start`` through $ref."""
    defs = schema["$defs"]
    seen: set[str] = set()
    stack: list[Any] = [start]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                name = ref.removeprefix("#/$defs/")
                if name not in seen:
                    seen.add(name)
                    stack.append(defs[name])
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return seen


@pytest.mark.parametrize("channel", ["agent_to_backend", "input_event"])
def test_agent_side_schema_cannot_reach_clipboard_or_transfer(channel: str) -> None:
    schema = json_schema()
    reachable = _reachable_defs(schema, schema["properties"][channel])
    assert "AgentInput" in reachable or channel == "input_event"
    assert not {"ClipboardPaste", "PasteResult", "SecretInput"} & reachable, reachable
    assert not any("clip" in name.lower() or "transfer" in name.lower() for name in reachable)


def test_clipboard_paste_is_refused_on_every_agent_path() -> None:
    raw = ClipboardPaste(t_mono_ns=T, request_id=1, text="x").model_dump_json()
    with pytest.raises(ValidationError):
        parse_agent_to_backend(raw)
    with pytest.raises(ValidationError):
        parse_input_event(raw)
    batch = {"type": "agent_input", "t_mono_ns": T, "frame_id": 1, "t_capture_ns": T}
    with pytest.raises(ValidationError):
        parse_agent_to_backend(json.dumps({**batch, "events": [json.loads(raw)]}))


def test_paste_cap_counts_utf8_bytes_not_characters() -> None:
    thai = "ส"  # 3 bytes in UTF-8
    fits = thai * (PASTE_MAX_BYTES // 3)
    assert len(fits.encode()) <= PASTE_MAX_BYTES
    ClipboardPaste(t_mono_ns=T, request_id=0, text=fits)
    with pytest.raises(ValidationError):
        ClipboardPaste(t_mono_ns=T, request_id=0, text=fits + thai)
    ClipboardPaste(t_mono_ns=T, request_id=0, text="a" * PASTE_MAX_BYTES)
    with pytest.raises(ValidationError):
        ClipboardPaste(t_mono_ns=T, request_id=0, text="a" * (PASTE_MAX_BYTES + 1))


def test_paste_rejects_empty_text_and_lone_surrogates() -> None:
    with pytest.raises(ValidationError):
        ClipboardPaste(t_mono_ns=T, request_id=0, text="")
    with pytest.raises(ValidationError):  # what JSON.stringify emits for a broken JS string
        parse_browser_to_backend(
            '{"type":"clipboard_paste","t_mono_ns":1,"frame_id":-1,"request_id":0,"text":"a\\ud800"}'
        )


# --- ADR-0007: packet ground truth never reaches the agent side --------------------------------


@pytest.mark.parametrize("channel", ["agent_to_backend", "backend_to_agent", "input_event"])
def test_agent_side_schema_cannot_reach_packet_events(channel: str) -> None:
    schema = json_schema()
    reachable = _reachable_defs(schema, schema["properties"][channel])
    packetish = ("packet", "chat", "entity", "world", "sniff", "stat_change", "map_enter")
    assert not any(any(word in name.lower() for word in packetish) for name in reachable), reachable


def test_poring_env_never_imports_poring_packets() -> None:
    src = Path(__file__).resolve().parents[1] / "src"
    offenders = [
        str(path.relative_to(src))
        for path in src.rglob("*.py")
        if "poring_packets" in path.read_text() or "packets" in path.stem
    ]
    assert offenders == []
