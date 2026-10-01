"""ADR-0007 routes (/ingest/packets, /ws/packets) and sensitive agent batches, end-to-end."""

import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from poring_backend.config import Settings
from poring_backend.main import create_app
from poring_backend.packets import PacketOutbox
from poring_backend.routes_packets import compose_peer
from poring_env.clock import FrameCounter, monotonic_ns
from poring_env.frame import Frame
from poring_env.protocol import AgentInput, InputEvent, Key, Mode, MouseButton, MouseMove, SetMode
from poring_packets.events import Chat, PacketStats

ORIGIN = "http://lab.test:3000"
T = 1_000


class GreyCapture:
    """Mid-grey frames: the black-screen detector stays 'ok'."""

    def __init__(self) -> None:
        self.counter = FrameCounter()

    def grab(self) -> Frame:
        return Frame(self.counter.next(), monotonic_ns(), 64, 36, bytes([128]) * (64 * 36 * 4))

    def close(self) -> None:
        pass


class RecordingInput:
    def __init__(self) -> None:
        self.events: list[InputEvent] = []

    def send_many(self, events: list[InputEvent]) -> None:
        self.events.extend(events)

    def pointer(self) -> tuple[int, int]:
        return (0, 0)

    def has_window_class(self, needle: str) -> bool:
        return True

    def close(self) -> None:
        pass


Factory = Callable[..., tuple[TestClient, RecordingInput]]


@pytest.fixture
def make_client(tmp_path: Path) -> Iterator[Factory]:
    clients: list[TestClient] = []

    def factory(**overrides: Any) -> tuple[TestClient, RecordingInput]:
        fake = RecordingInput()
        settings = Settings(
            data_dir=tmp_path,
            status_hz=20.0,
            frontend_origins=ORIGIN,
            **{"public_port": 80, "internal_port": 80, "ingest_peer": "testclient", **overrides},
        )
        app = create_app(settings, capture_factory=GreyCapture, input_factory=lambda: fake)
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client, fake

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


def health(client: TestClient) -> dict[str, Any]:
    data: dict[str, Any] = client.get("/health").json()
    return data


def refused(client: TestClient, path: str, **kwargs: Any) -> None:
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(path, **kwargs) as ws:
        ws.receive_text()


def chat(text: str = "hello") -> str:
    return Chat(
        t_mono_ns=monotonic_ns(), server="map", dir="sc", packet_id=0x8D, kind="public",
        gid=1, speaker="A", text=text, raw_hex=text.encode().hex().upper(),
    ).model_dump_json()  # fmt: skip


def stats() -> str:
    return PacketStats(
        t_mono_ns=monotonic_ns(), packets=10, unknown=0, desyncs=0, skipped_bytes=0, tcp_gaps=0,
        clock_steps=0, map="prontera", self_x=150.0, self_y=180.0, entities=3, hp=40, max_hp=40,
        sp=10, max_sp=10, ingest_dropped=7,
    ).model_dump_json()  # fmt: skip


def log_lines(tmp_path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for path in sorted((tmp_path / "input_log").glob("*.jsonl"))
        for line in path.read_text().splitlines()
    ]


def wait_health(client: TestClient, pred: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    for _ in range(200):
        h = health(client)
        if pred(h):
            return h
        time.sleep(0.01)
    raise AssertionError(health(client))


# --- /ingest/packets -> /ws/packets ---------------------------------------------------------------


def test_ingested_events_reach_the_console_with_a_replay_for_late_viewers(
    make_client: Factory,
) -> None:
    client, _ = make_client()
    with client.websocket_connect("/ingest/packets") as ingest:
        ingest.send_text(stats())
        ingest.send_text(chat("first"))
        wait_health(client, lambda h: h["packets"]["events_in"] == 1)
        with client.websocket_connect("/ws/packets", headers={"origin": ORIGIN}) as viewer:
            # Replay: the last stats, then the recent events.
            assert json.loads(viewer.receive_text())["type"] == "packet_stats"
            assert json.loads(viewer.receive_text())["text"] == "first"
            ingest.send_text(chat("live"))
            assert json.loads(viewer.receive_text())["text"] == "live"
    h = health(client)["packets"]
    assert h["events_in"] == 2 and h["stats_in"] == 1
    assert h["sniffer_ingest_dropped"] == 7  # the sniffer's own queue drops surface here
    assert h["ingest_lag_ms"] is not None


def test_ingest_drops_are_counted_and_never_answered(make_client: Factory) -> None:
    client, _ = make_client()
    with client.websocket_connect("/ingest/packets") as ingest:
        ingest.send_text('{"type": "chat"}')
        ingest.send_text("not json")
        ingest.send_text(chat())  # still alive after the drops
        h = wait_health(client, lambda h: h["packets"]["events_in"] == 1)
    assert h["dropped_messages"]["ingest"] == {"json_invalid": 1, "missing:chat.t_mono_ns": 1}


def test_ingest_refuses_the_public_listener(make_client: Factory) -> None:
    client, _ = make_client(internal_port=8001)  # TestClient arrives on port 80
    refused(client, "/ingest/packets")
    assert health(client)["dropped_messages"]["ingest"] == {"public_listener": 1}


def test_ingest_refuses_any_peer_but_rathena(make_client: Factory) -> None:
    client, _ = make_client(ingest_peer="10.210.96.6")  # TestClient is "testclient"
    refused(client, "/ingest/packets")
    assert health(client)["dropped_messages"]["ingest"] == {"wrong_peer": 1}


@pytest.mark.parametrize(
    ("overrides", "headers", "reason"),
    [
        ({"public_port": 8000}, {"origin": ORIGIN}, "internal_listener"),
        ({}, {}, "origin_missing"),
        ({}, {"origin": "http://evil.test:3000"}, "origin_not_allowed"),
    ],
)
def test_ws_packets_refusals_are_counted(
    make_client: Factory, overrides: dict[str, Any], headers: dict[str, str], reason: str
) -> None:
    client, _ = make_client(**overrides)
    refused(client, "/ws/packets", headers=headers)
    assert health(client)["dropped_messages"]["ws_packets"] == {reason: 1}


def test_ws_packets_refuses_compose_peers(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path, frontend_origins=ORIGIN, public_port=80, internal_port=80
    )
    app = create_app(settings, capture_factory=GreyCapture, input_factory=RecordingInput)
    with TestClient(app, client=("10.210.96.7", 40000)) as client:  # e.g. vision
        refused(client, "/ws/packets", headers={"origin": ORIGIN})
        assert health(client)["dropped_messages"]["ws_packets"] == {"compose_peer": 1}
    gateway = TestClient(app, client=("10.210.96.1", 40000))  # host scripts arrive via the gateway
    with gateway, gateway.websocket_connect("/ws/packets", headers={"origin": ORIGIN}):
        pass


def test_compose_peer_rule() -> None:
    subnet, gw = "10.210.96.0/24", "10.210.96.1"
    assert compose_peer("10.210.96.6", subnet, gw)
    assert not compose_peer("10.210.96.1", subnet, gw)  # gateway: host scripts
    assert not compose_peer("192.168.110.55", subnet, gw)  # a LAN browser
    assert not compose_peer(None, subnet, gw)
    assert not compose_peer("testclient", subnet, gw)


def test_ws_packets_is_receive_only(make_client: Factory) -> None:
    client, _ = make_client()
    with client.websocket_connect("/ws/packets", headers={"origin": ORIGIN}) as viewer:
        viewer.send_text('{"type": "ping", "t_mono_ns": 1}')
        reply = json.loads(viewer.receive_text())
    assert (reply["type"], reply["channel"], reply["reason"]) == (
        "error",
        "ws_packets",
        "receive_only",
    )
    assert health(client)["dropped_messages"]["ws_packets"] == {"receive_only": 1}


def test_a_slow_viewer_drops_the_oldest_lines_and_counts_them() -> None:
    outbox = PacketOutbox(max_queue=3)
    for i in range(5):
        outbox.offer(str(i))
    assert outbox.dropped == 2
    assert list(outbox._queue) == ["2", "3", "4"]


def test_packet_events_never_reach_the_agent_channel(make_client: Factory) -> None:
    client, _ = make_client()
    with (
        client.websocket_connect("/internal/agent") as agent,
        client.websocket_connect("/ingest/packets") as ingest,
    ):
        ingest.send_text(chat("secret-ground-truth"))
        wait_health(client, lambda h: h["packets"]["events_in"] == 1)
        agent.send_text('{"type": "ping", "t_mono_ns": 1}')
        seen = []
        while True:
            msg = json.loads(agent.receive_text())
            seen.append(msg["type"])
            if msg["type"] == "pong":
                break
    assert set(seen) <= {"status", "pong"}, seen


# --- sensitive agent batches ----------------------------------------------------------------------


def typed(text: str) -> list[InputEvent]:
    out: list[InputEvent] = []
    for ch in text:
        code = f"Key{ch.upper()}"
        out += [
            Key(t_mono_ns=T, code=code, action="down"),
            Key(t_mono_ns=T, code=code, action="up"),
        ]
    return out


def bot_mode(client: TestClient) -> None:
    with client.websocket_connect("/ws/input") as ws:
        ws.send_text(SetMode(t_mono_ns=T, mode=Mode.BOT).model_dump_json())
    wait_health(client, lambda h: h["mode"] == "BOT")


def send_agent(client: TestClient, events: list[InputEvent], sensitive: bool) -> dict[str, Any]:
    with client.websocket_connect("/internal/agent") as agent:
        msg = AgentInput(t_mono_ns=T, t_capture_ns=T, events=events, sensitive=sensitive)
        agent.send_text(msg.model_dump_json())
        while True:
            reply: dict[str, Any] = json.loads(agent.receive_text())
            if reply["type"] == "input_ack":
                return reply


def test_a_sensitive_batch_is_injected_but_logged_without_key_identities(
    make_client: Factory, tmp_path: Path
) -> None:
    client, fake = make_client()
    bot_mode(client)
    ack = send_agent(client, typed("qzx"), sensitive=True)
    assert ack["accepted"] == 6
    assert [e.code for e in fake.events if isinstance(e, Key)] == [
        "KeyQ", "KeyQ", "KeyZ", "KeyZ", "KeyX", "KeyX"
    ]  # fmt: skip
    client.__exit__(None, None, None)  # flush and close the log
    lines = log_lines(tmp_path)
    summaries = [line for line in lines if line["event"].get("type") == "sensitive_batch"]
    assert len(summaries) == 1
    assert summaries[0]["event"]["events"] == 6 and summaries[0]["event"]["accepted"] == 6
    on_disk = "".join(p.read_text() for p in tmp_path.rglob("*") if p.is_file())
    for needle in ("KeyQ", "KeyZ", "KeyX", '"code"'):
        assert needle not in on_disk


def test_an_unbalanced_sensitive_batch_is_refused_whole(make_client: Factory) -> None:
    client, fake = make_client()
    bot_mode(client)
    events: list[InputEvent] = [
        Key(t_mono_ns=T, code="KeyA", action="down"),
        MouseButton(t_mono_ns=T, button="left", action="down"),
        MouseButton(t_mono_ns=T, button="left", action="up"),
    ]
    ack = send_agent(client, events, sensitive=True)
    assert (ack["accepted"], ack["reasons"]) == (0, ["sensitive_unbalanced"])
    assert fake.events == []
    assert health(client)["input_refused"]["bot"] == {"sensitive_unbalanced": 3}


def test_a_sensitive_batch_still_yields_to_the_human_lease(make_client: Factory) -> None:
    client, fake = make_client(assist_lease_s=30.0)
    with client.websocket_connect("/ws/input") as human:
        human.send_text(SetMode(t_mono_ns=T, mode=Mode.ASSIST).model_dump_json())
        human.send_text(MouseMove(t_mono_ns=T, x=0.5, y=0.5).model_dump_json())  # takes the lease
        wait_health(client, lambda h: h["mode"] == "ASSIST")
        ack = send_agent(client, typed("ab"), sensitive=True)
    assert (ack["accepted"], ack["reasons"]) == (0, ["human_lease"])
    assert not [e for e in fake.events if isinstance(e, Key)]
