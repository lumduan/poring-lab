"""End-to-end through FastAPI with fake X capture/input: real WebSockets, real mux, real log."""

import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from poring_backend.config import Settings
from poring_backend.main import create_app
from poring_env.clock import FrameCounter, monotonic_ns
from poring_env.frame import Frame
from poring_env.protocol import (
    AgentHello,
    AgentInput,
    InputEvent,
    Key,
    Mode,
    MouseMove,
    Ping,
    SetMode,
)
from poring_env.x11 import to_pixels

ORIGIN = "http://lab.test:3000"


class FakeCapture:
    def __init__(self) -> None:
        self.counter = FrameCounter()

    def grab(self) -> Frame:
        return Frame(
            frame_id=self.counter.next(),
            t_capture_ns=monotonic_ns(),
            width=64,
            height=36,
            bgra=bytes(64 * 36 * 4),
        )

    def close(self) -> None:
        pass


class FakeInput:
    def __init__(self) -> None:
        self.events: list[InputEvent] = []
        self.pos = (0, 0)

    def send_many(self, events: list[InputEvent]) -> None:
        for event in events:
            self.events.append(event)
            if isinstance(event, MouseMove):
                self.pos = to_pixels(event.x, event.y, 1280, 720)

    def pointer(self) -> tuple[int, int]:
        return self.pos

    def has_window_class(self, needle: str) -> bool:
        return False

    def close(self) -> None:
        pass


Factory = Callable[..., tuple[TestClient, FakeInput]]


@pytest.fixture
def make_client(tmp_path: Path) -> Iterator[Factory]:
    clients: list[TestClient] = []

    def factory(**overrides: Any) -> tuple[TestClient, FakeInput]:
        fake = FakeInput()
        settings = Settings(
            data_dir=tmp_path,
            stream_fps=100.0,
            status_hz=20.0,
            frontend_origins=ORIGIN,
            **overrides,
        )
        app = create_app(settings, capture_factory=FakeCapture, input_factory=lambda: fake)
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client, fake

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


def sync(ws: WebSocketTestSession) -> None:
    """Ping and wait for the pong: every earlier message on this socket has been handled."""
    ws.send_text(Ping(t_mono_ns=1).model_dump_json())
    while json.loads(ws.receive_text())["type"] != "pong":
        pass


def receive_until(ws: WebSocketTestSession, type_: str) -> dict[str, Any]:
    while True:
        msg: dict[str, Any] = json.loads(ws.receive_text())
        if msg["type"] == type_:
            return msg


def wait_for(pred: Callable[[], bool], timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not pred():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.01)


def log_lines(tmp_path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for path in sorted((tmp_path / "input_log").glob("*.jsonl"))
        for line in path.read_text().splitlines()
    ]


def test_health(make_client: Factory) -> None:
    client, _ = make_client()
    body = client.get("/health").json()
    assert (body["status"], body["mode"], body["x11"], body["pointer"]) == (
        "ok",
        "HUMAN",
        True,
        [0, 0],
    )


def test_human_input_reaches_xtest_and_is_logged(make_client: Factory, tmp_path: Path) -> None:
    client, fake = make_client()
    with client.websocket_connect("/ws/input", headers={"origin": ORIGIN}) as ws:
        ws.send_text(MouseMove(t_mono_ns=5, frame_id=42, x=0.25, y=0.5).model_dump_json())
        sync(ws)
    assert fake.pos == (320, 360)
    first = log_lines(tmp_path)[0]
    assert (first["source"], first["accepted"], first["frame_id"]) == ("human", True, 42)
    assert first["event"]["type"] == "mouse_move"


def test_closing_the_input_socket_releases_held_keys(make_client: Factory) -> None:
    client, fake = make_client()
    with client.websocket_connect("/ws/input", headers={"origin": ORIGIN}) as ws:
        ws.send_text(Key(t_mono_ns=1, code="KeyW", action="down").model_dump_json())
        sync(ws)
    wait_for(lambda: any(isinstance(e, Key) and e.action == "up" for e in fake.events))
    assert [(e.code, e.action) for e in fake.events if isinstance(e, Key)] == [
        ("KeyW", "down"),
        ("KeyW", "up"),
    ]


def send_agent_key(ws: WebSocketTestSession, code: str) -> dict[str, Any]:
    ws.send_text(AgentHello(t_mono_ns=1, agent_id="test", version="0").model_dump_json())
    batch = AgentInput(
        t_mono_ns=1,
        frame_id=7,
        t_capture_ns=1,
        events=[Key(t_mono_ns=1, frame_id=7, code=code, action="down")],
    )
    ws.send_text(batch.model_dump_json())
    return receive_until(ws, "input_ack")


def test_bot_input_is_dropped_in_human_mode(make_client: Factory, tmp_path: Path) -> None:
    client, fake = make_client(internal_port=80)  # TestClient connections arrive on port 80
    with client.websocket_connect("/internal/agent") as ws:
        ack = send_agent_key(ws, "KeyA")
    assert (ack["accepted"], ack["dropped"], ack["reasons"]) == (0, 1, ["mode=HUMAN"])
    assert not any(isinstance(e, Key) and e.code == "KeyA" for e in fake.events)
    assert any(r["source"] == "bot" and not r["accepted"] for r in log_lines(tmp_path))


def test_bot_mode_lets_the_agent_act(make_client: Factory) -> None:
    client, fake = make_client(internal_port=80)
    with client.websocket_connect("/ws/input", headers={"origin": ORIGIN}) as human:
        human.send_text(SetMode(t_mono_ns=1, mode=Mode.BOT).model_dump_json())
        sync(human)
        with client.websocket_connect("/internal/agent") as ws:
            ack = send_agent_key(ws, "KeyA")
    assert (ack["accepted"], ack["dropped"]) == (1, 0)
    assert any(isinstance(e, Key) and e.code == "KeyA" for e in fake.events)


def test_stream_sends_status_then_frame_meta_then_jpeg(make_client: Factory) -> None:
    client, _ = make_client()
    with client.websocket_connect("/ws/stream", headers={"origin": ORIGIN}) as ws:
        assert json.loads(ws.receive_text())["type"] == "status"
        meta = receive_until(ws, "frame")
        jpeg = ws.receive_bytes()
    assert jpeg[:2] == b"\xff\xd8"
    assert (meta["width"], meta["height"], meta["nbytes"]) == (64, 36, len(jpeg))
    assert meta["t_capture_ns"] <= meta["t_encoded_ns"] <= meta["t_mono_ns"]


def test_frame_ids_increase_on_the_stream(make_client: Factory) -> None:
    client, _ = make_client()
    ids = []
    with client.websocket_connect("/ws/stream", headers={"origin": ORIGIN}) as ws:
        while len(ids) < 5:
            msg = ws.receive()
            if msg.get("text") and json.loads(msg["text"])["type"] == "frame":
                ids.append(json.loads(msg["text"])["frame_id"])
    assert ids == sorted(ids) and len(set(ids)) == len(ids)


def test_foreign_origin_is_refused(make_client: Factory) -> None:
    client, _ = make_client()
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws/input", headers={"origin": "http://evil.example"}),
    ):
        pass


def test_configured_origin_is_accepted_and_missing_origin_too(make_client: Factory) -> None:
    client, _ = make_client()
    for headers in ({"origin": ORIGIN}, {"origin": ORIGIN + "/"}, {}):
        with client.websocket_connect("/ws/stream", headers=headers) as ws:
            assert json.loads(ws.receive_text())["type"] == "status"


def test_foreign_origin_is_refused_on_the_stream_too(make_client: Factory) -> None:
    client, _ = make_client()
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws/stream", headers={"origin": "http://192.168.1.99:3000"}),
    ):
        pass


def test_health_reports_pacing(make_client: Factory) -> None:
    client, _ = make_client()
    body = client.get("/health").json()
    assert body["stream_fps_target"] == 100.0 and body["frames_skipped_late"] == 0


def test_internal_route_refuses_the_public_listener(make_client: Factory) -> None:
    client, _ = make_client()  # internal_port stays 8001; TestClient arrives on 80
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/internal/agent"):
        pass
