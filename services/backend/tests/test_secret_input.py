"""Human secret typing (2026-10-02): a console's SecretInput toggle keeps human key identities --
and a paste's length and digest -- out of every log, while the keys still reach Windows."""

import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from poring_backend.config import Settings
from poring_backend.main import create_app
from poring_env.clock import FrameCounter, monotonic_ns
from poring_env.frame import Frame
from poring_env.protocol import (
    AgentInput,
    ClipboardPaste,
    InputEvent,
    Key,
    Mode,
    Ping,
    SecretInput,
    SetMode,
)

ORIGIN = "http://lab.test:3000"
T = 1_000
LAN = ("192.168.110.55", 50000)


class GreyCapture:
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


@pytest.fixture
def lab(tmp_path: Path) -> Iterator[tuple[TestClient, RecordingInput]]:
    fake = RecordingInput()
    settings = Settings(
        data_dir=tmp_path,
        status_hz=20.0,
        frontend_origins=ORIGIN,
        public_port=80,  # the TestClient arrives on port 80: one listener for both routes
        internal_port=80,
    )
    app = create_app(settings, capture_factory=GreyCapture, input_factory=lambda: fake)
    client = TestClient(app, client=LAN)
    client.__enter__()
    yield client, fake
    client.__exit__(None, None, None)


def wait_health(client: TestClient, pred: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    for _ in range(300):
        h: dict[str, Any] = client.get("/health").json()
        if pred(h):
            return h
        time.sleep(0.01)
    raise AssertionError("health predicate never held")


def lines(tmp_path: Path, sub: str = "input_log") -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for path in sorted((tmp_path / sub).glob("*.jsonl"))
        for line in path.read_text().splitlines()
    ]


def key(code: str, action: str) -> str:
    return Key(t_mono_ns=T, code=code, action=action).model_dump_json()  # type: ignore[arg-type]


def secret(on: bool) -> str:
    return SecretInput(t_mono_ns=T, on=on).model_dump_json()


def test_secret_keys_are_injected_but_logged_without_codes(
    lab: tuple[TestClient, RecordingInput], tmp_path: Path
) -> None:
    client, fake = lab
    with client.websocket_connect("/ws/input", headers={"origin": ORIGIN}) as ws:
        ws.send_text(key("KeyA", "down"))
        ws.send_text(key("KeyA", "up"))
        ws.send_text(secret(True))
        ws.send_text(key("KeyQ", "down"))
        ws.send_text(key("KeyQ", "up"))
        ws.send_text(secret(False))
        ws.send_text(key("KeyB", "down"))
        ws.send_text(key("KeyB", "up"))
        wait_health(client, lambda h: True)
        for _ in range(100):
            if len([e for e in fake.events if isinstance(e, Key)]) == 6:
                break
            time.sleep(0.01)
    assert [e.code for e in fake.events if isinstance(e, Key)] == [
        "KeyA", "KeyA", "KeyQ", "KeyQ", "KeyB", "KeyB"
    ]  # fmt: skip
    client.__exit__(None, None, None)
    keys = [r["event"] for r in lines(tmp_path) if r["event"].get("type") == "key"]
    assert [k.get("code") for k in keys] == ["KeyA", "KeyA", None, None, "KeyB", "KeyB"]
    assert [k.get("secret") for k in keys] == [None, None, True, True, None, None]
    assert all(k.get("action") in ("down", "up") for k in keys)
    assert "KeyQ" not in "".join(p.read_text() for p in tmp_path.rglob("*.jsonl"))


def test_status_shows_secret_typing_and_a_disconnect_clears_it(
    lab: tuple[TestClient, RecordingInput],
) -> None:
    client, _ = lab
    with client.websocket_connect("/ws/input", headers={"origin": ORIGIN}) as ws:
        ws.send_text(secret(True))
        with client.websocket_connect("/ws/stream", headers={"origin": ORIGIN}) as viewer:
            for _ in range(200):
                msg = json.loads(viewer.receive_text())
                if msg.get("type") == "status" and msg.get("human_secret") is True:
                    break
            else:
                raise AssertionError("status never showed human_secret")
    # the input connection closed: secret typing is off again (the disconnect's cleanup is a task
    # of its own, so the very first status may still predate it: wait for it, bounded)
    with client.websocket_connect("/ws/stream", headers={"origin": ORIGIN}) as viewer:
        for _ in range(200):
            msg = json.loads(viewer.receive_text())
            if msg.get("type") == "status" and msg["human_secret"] is False:
                break
        else:
            raise AssertionError("secret typing stayed on after the disconnect")


def test_a_held_key_released_at_disconnect_stays_redacted(
    lab: tuple[TestClient, RecordingInput], tmp_path: Path
) -> None:
    client, fake = lab
    with client.websocket_connect("/ws/input", headers={"origin": ORIGIN}) as ws:
        ws.send_text(secret(True))
        ws.send_text(key("KeyZ", "down"))  # still held when the tab goes away
        for _ in range(100):
            if any(isinstance(e, Key) for e in fake.events):
                break
            time.sleep(0.01)
    for _ in range(100):  # the disconnect cleanup releases it
        if sum(isinstance(e, Key) for e in fake.events) >= 2:
            break
        time.sleep(0.01)
    client.__exit__(None, None, None)
    on_disk = "".join(p.read_text() for p in tmp_path.rglob("*.jsonl"))
    assert "KeyZ" not in on_disk
    assert [e.code for e in fake.events if isinstance(e, Key)][-1] == "KeyZ"  # it was released


def test_a_secret_paste_logs_neither_length_nor_digest(
    lab: tuple[TestClient, RecordingInput], tmp_path: Path
) -> None:
    client, _ = lab
    paste = ClipboardPaste(t_mono_ns=T, request_id=1, text="hunter2-secret")
    with client.websocket_connect("/ws/input", headers={"origin": ORIGIN}) as ws:
        ws.send_text(secret(True))
        ws.send_text(paste.model_dump_json())
        reply = json.loads(ws.receive_text())
        assert reply["type"] == "paste_result"
    client.__exit__(None, None, None)
    pastes = [r["event"] for r in lines(tmp_path) if r["event"].get("type") == "clipboard_paste"]
    assert pastes == [{"type": "clipboard_paste", "secret": True}]
    audits = lines(tmp_path, "transfer_log")
    assert audits and all(a["sha256"] is None and a["size"] == 0 for a in audits)
    assert "hunter2" not in "".join(p.read_text() for p in tmp_path.rglob("*.jsonl"))


def test_bot_keys_are_never_redacted_by_a_human_toggle(
    lab: tuple[TestClient, RecordingInput], tmp_path: Path
) -> None:
    client, _ = lab
    with client.websocket_connect("/ws/input", headers={"origin": ORIGIN}) as ws:
        ws.send_text(SetMode(t_mono_ns=T, mode=Mode.BOT).model_dump_json())
        ws.send_text(secret(True))
        wait_health(client, lambda h: h["mode"] == "BOT")
        with client.websocket_connect("/internal/agent") as agent:
            batch = AgentInput(
                t_mono_ns=T,
                t_capture_ns=T,
                events=[
                    Key(t_mono_ns=T, code="KeyW", action="down"),
                    Key(t_mono_ns=T, code="KeyW", action="up"),
                ],
            )
            agent.send_text(batch.model_dump_json())
            while json.loads(agent.receive_text())["type"] != "input_ack":
                pass
    client.__exit__(None, None, None)
    records = lines(tmp_path)
    bot = [r["event"] for r in records if r["source"] == "bot" and r["event"]["type"] == "key"]
    assert [k["code"] for k in bot] == ["KeyW", "KeyW"]


def test_an_agent_route_preview_reaches_viewers_and_never_the_mux(
    lab: tuple[TestClient, RecordingInput],
) -> None:
    """walk@8's route preview (Batt, 2026-10-07): display only, relayed like detections."""
    from poring_env.protocol import AgentHello, RoutePoint, RoutePreview

    client, fake = lab
    points = [RoutePoint(x=0.5, y=0.5, kind="start"), RoutePoint(x=0.6, y=0.4, kind="goal")]
    preview = RoutePreview(t_mono_ns=T, label="walk@8 route 0", ttl_ms=4000, points=points)
    hello = AgentHello(t_mono_ns=T, agent_id="t", version="0")
    with (
        client.websocket_connect("/ws/stream", headers={"origin": ORIGIN}) as viewer,
        client.websocket_connect("/internal/agent") as ws,
    ):
        ws.send_text(hello.model_dump_json())
        ws.send_text(preview.model_dump_json())
        for _ in range(400):
            raw = viewer.receive()  # the stream also carries binary video frames
            msg = json.loads(raw["text"]) if raw.get("text") else {}
            if msg.get("type") == "route_preview":
                break
        else:
            raise AssertionError("the viewer never got the route preview")
    assert msg["points"][1] == {"x": 0.6, "y": 0.4, "kind": "goal"} and msg["ttl_ms"] == 4000
    assert fake.events == []  # nothing reached the injector


def test_an_agent_operator_hud_reaches_viewers_and_never_the_mux_or_the_input_log(
    lab: tuple[TestClient, RecordingInput], tmp_path: Path
) -> None:
    """The operator HUD (Batt, 2026-10-08): display only, relayed like route_preview; the agent
    gets no reply, the injector nothing, and the input log never records it."""
    from poring_env.protocol import (
        AgentHello,
        HudCounters,
        HudLock,
        HudPoint,
        HudRect,
        HudUnit,
        OperatorHud,
    )

    client, fake = lab
    unit = HudUnit(
        cls="monster",
        conf=0.8,
        box=HudRect(x=0.4, y=0.3, w=0.03, h=0.05),
        foot=HudPoint(x=0.415, y=0.35),
        dist_cells=3,
    )
    hud = OperatorHud(
        t_mono_ns=T,
        label="walk@12",
        ttl_ms=1500,
        units=[unit],
        lock=HudLock(index=0, lock_remaining_ms=900),
        log=["detected 1 unit", "walking to (102,110)"],
        counters=HudCounters(units=1, det_fps=4.0),
    )
    hello = AgentHello(t_mono_ns=T, agent_id="t", version="0")
    # the positive case: a human key goes through the same input log in this test
    with client.websocket_connect("/ws/input", headers={"origin": ORIGIN}) as human:
        human.send_text(key("KeyA", "down"))
        human.send_text(key("KeyA", "up"))
        for _ in range(200):
            if len(fake.events) == 2:
                break
            time.sleep(0.01)
    injected = list(fake.events)
    with (
        client.websocket_connect("/ws/stream", headers={"origin": ORIGIN}) as viewer,
        client.websocket_connect("/internal/agent") as ws,
    ):
        ws.send_text(hello.model_dump_json())
        ws.send_text(hud.model_dump_json())
        for _ in range(400):
            raw = viewer.receive()  # the stream also carries binary video frames
            msg = json.loads(raw["text"]) if raw.get("text") else {}
            if msg.get("type") == "operator_hud":
                break
        else:
            raise AssertionError("the viewer never got the operator HUD")
        ws.send_text(Ping(t_mono_ns=T + 1).model_dump_json())
        replies = []
        while (reply := json.loads(ws.receive_text()))["type"] != "pong":
            replies.append(reply["type"])
    assert OperatorHud.model_validate(msg) == hud  # relayed unchanged
    assert "error" not in replies and "input_ack" not in replies  # no reply to a display message
    assert [e.code for e in injected if isinstance(e, Key)] == ["KeyA", "KeyA"]
    assert fake.events == injected  # the HUD added nothing at the injector
    client.__exit__(None, None, None)
    on_disk = "".join(p.read_text() for p in tmp_path.rglob("*.jsonl"))
    assert "KeyA" in on_disk  # the log was live and written ...
    assert "operator_hud" not in on_disk and "walking to" not in on_disk  # ... and has no HUD
