"""Phase 0: damage-driven capture, runtime tuning, latency recording, loopback-only debug routes."""

import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from poring_backend.config import Settings
from poring_backend.latency import LatencyRecorder
from poring_backend.main import create_app
from poring_backend.stream import Outbox, damage_wait_s
from poring_env.clock import FrameCounter, monotonic_ns
from poring_env.frame import Frame
from poring_env.protocol import (
    FrameMeta,
    FrameTiming,
    Key,
    Ping,
    ReleaseAll,
    ViewerTiming,
)

ORIGIN = "http://lab.test:3000"


class FakeCapture:
    def __init__(self) -> None:
        self.counter = FrameCounter()

    def grab(self) -> Frame:
        return Frame(
            frame_id=self.counter.next(),
            t_capture_ns=monotonic_ns(),
            width=32,
            height=16,
            bgra=bytes(32 * 16 * 4),
        )

    def close(self) -> None:
        pass


class NullInput:
    def send_many(self, events: list[Any]) -> None:
        pass

    def pointer(self) -> tuple[int, int]:
        return (0, 0)

    def has_window_class(self, needle: str) -> bool:
        return False

    def close(self) -> None:
        pass


class FakeDamage:
    """A ChangeWatcher the test fires by hand."""

    def __init__(self, on_damage: Callable[[int], None]) -> None:
        self.on_damage = on_damage
        self.events = 0
        self.connected = True

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def fire(self) -> None:
        self.events += 1
        self.on_damage(monotonic_ns())


Make = Callable[..., tuple[TestClient, list[FakeDamage]]]


@pytest.fixture
def make(tmp_path: Path) -> Iterator[Make]:
    clients: list[TestClient] = []

    def factory(**overrides: Any) -> tuple[TestClient, list[FakeDamage]]:
        watchers: list[FakeDamage] = []

        def damage(on: Callable[[int], None]) -> FakeDamage:
            watchers.append(FakeDamage(on))
            return watchers[-1]

        fields: dict[str, Any] = {
            "data_dir": tmp_path,
            "frontend_origins": ORIGIN,
            "stream_fps": 100.0,
            "status_hz": 20.0,
        }
        fields.update(overrides)
        app = create_app(
            Settings(**fields),
            capture_factory=FakeCapture,
            input_factory=NullInput,
            damage_factory=damage,
        )
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client, watchers

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


def frames_within(ws: WebSocketTestSession, seconds: float) -> list[dict[str, Any]]:
    """FrameMeta messages that arrive within ``seconds`` (a ping closes the window)."""
    metas: list[dict[str, Any]] = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        time.sleep(0.01)
    ws.send_text(Ping(t_mono_ns=1).model_dump_json())
    while True:
        raw = ws.receive()
        if raw.get("text"):
            msg = json.loads(raw["text"])
            if msg["type"] == "pong":
                return metas
            if msg["type"] == "frame":
                metas.append(msg)


# --- pure helpers -------------------------------------------------------------------------------


def test_damage_wait_respects_the_cap() -> None:
    assert damage_wait_s(0.0, 60.0) == pytest.approx(1 / 60)
    assert damage_wait_s(0.010, 60.0) == pytest.approx(1 / 60 - 0.010)
    assert damage_wait_s(0.5, 60.0) == 0.0


def test_outbox_counts_what_latest_wins_drops() -> None:
    outbox = Outbox()
    meta = FrameMeta(
        t_mono_ns=1, frame_id=1, t_capture_ns=1, t_encoded_ns=1, width=1, height=1, nbytes=1
    )
    outbox.offer_frame(meta, b"a")
    outbox.offer_frame(meta, b"b")
    outbox.offer_frame(meta, b"c")
    assert outbox.frames_skipped == 2


def test_recorder_maps_browser_clock_through_the_offset() -> None:
    rec = LatencyRecorder()
    ms = 1_000_000
    base = 600_000_000 * ms  # host monotonic ~ a week of uptime
    meta = FrameMeta(
        t_mono_ns=0,
        frame_id=7,
        t_capture_ns=base,
        t_encoded_ns=base + 4 * ms,
        width=1,
        height=1,
        nbytes=1,
    )
    rec.frame_encoded(meta)
    rec.frame_sent(7, base + 5 * ms)
    offset = base - 90_000 * ms  # the tab has been open ~90 s: backend = browser + offset
    rec.viewer_timing(
        ViewerTiming(
            t_mono_ns=1,
            offset_ns=offset,
            offset_uncertainty_ns=2 * ms,
            visible=True,
            user_agent="Test/1",
            frames=[
                FrameTiming(
                    frame_id=7,
                    recv_ns=base + 15 * ms - offset,
                    decoded_ns=base + 20 * ms - offset,
                    painted_ns=base + 28 * ms - offset,
                )
            ],
        )
    )
    s = rec.summary(window_ns=10**12, now=base + 30 * ms)
    assert s["encode_ms"]["p50"] == 4.0
    assert s["viewer_net_ms"]["p50"] == 10.0
    assert s["viewer_decode_ms"]["p50"] == 5.0
    assert s["viewer_paint_wait_ms"]["p50"] == 8.0
    assert s["viewer_capture_to_paint_ms"]["p50"] == 28.0
    assert s["viewer_offset_uncertainty_ms"] == 2.0
    assert s["viewer_user_agent"] == "Test/1"


def test_viewer_timing_without_an_offset_is_not_converted() -> None:
    rec = LatencyRecorder()
    rec.viewer_timing(ViewerTiming(t_mono_ns=1, visible=True, frames=[]))
    assert len(rec.viewer) == 0


# --- capture modes ----------------------------------------------------------------------------


def test_damage_mode_grabs_on_change_not_on_a_grid(make: Make) -> None:
    client, watchers = make(stream_capture="damage", stream_max_fps=50.0)
    with client.websocket_connect("/ws/stream", headers={"origin": ORIGIN}) as ws:
        first = frames_within(ws, 0.3)
        assert 1 <= len(first) <= 2, "a joining viewer gets one frame, then none while idle"
        watchers[0].fire()
        assert len(frames_within(ws, 0.2)) == 1
        for _ in range(40):  # a burst of changes over ~0.4 s
            watchers[0].fire()
            time.sleep(0.01)
        burst = frames_within(ws, 0.1)
    assert 3 <= len(burst) <= 25, "max_fps caps the grabs (50/s over ~0.5 s)"
    health = client.get("/health").json()["stream"]
    assert health["capture"] == "damage" and health["damage_active"] is True
    assert health["grabs_on_damage"] >= len(burst)


def test_fixed_mode_is_a_grid(make: Make) -> None:
    client, watchers = make(stream_capture="fixed")
    with client.websocket_connect("/ws/stream", headers={"origin": ORIGIN}) as ws:
        assert len(frames_within(ws, 0.3)) >= 10
    assert watchers == []  # no damage watcher in fixed mode
    assert client.get("/health").json()["stream"]["damage_active"] is False


# --- debug routes and runtime tuning --------------------------------------------------------------


def test_damage_capture_is_the_default() -> None:
    assert Settings().stream_capture == "damage" and Settings().stream_max_fps == 60.0


def test_debug_routes_are_loopback_only(make: Make) -> None:
    client, _ = make()  # TestClient's peer is "testclient", not loopback
    assert client.get("/debug/latency").status_code == 404
    assert client.post("/debug/stream-tuning", json={"paint": "raf"}).status_code == 404


def test_tuning_switches_at_runtime_and_reaches_the_console(make: Make) -> None:
    client, _ = make(debug_hosts="testclient", stream_capture="fixed")
    assert client.get("/debug/stream-tuning").json()["capture"] == "fixed"
    tuned = client.post(
        "/debug/stream-tuning",
        json={"capture": "damage", "max_fps": 45, "move_interval_ms": 4, "paint": "raf"},
    ).json()
    assert (tuned["capture"], tuned["max_fps"], tuned["move_interval_ms"]) == ("damage", 45, 4)
    with client.websocket_connect("/ws/stream", headers={"origin": ORIGIN}) as ws:
        status = next(
            json.loads(m["text"])
            for m in iter(ws.receive, None)
            if m.get("text") and json.loads(m["text"])["type"] == "status"
        )
    assert (status["move_interval_ms"], status["paint"]) == (4, "raf")
    back = client.post("/debug/stream-tuning", json={"move_interval_ms": "raf"}).json()
    assert back["move_interval_ms"] is None
    assert client.post("/debug/stream-tuning", json={"jpeg_quality": 5}).status_code == 422
    assert client.post("/debug/stream-tuning", json={"bogus": 1}).status_code == 422


def test_inputs_record_decision_and_injection_times(make: Make) -> None:
    client, _ = make(debug_hosts="testclient")
    sent = monotonic_ns()
    with client.websocket_connect("/ws/input") as ws:  # a script on this host: our clock
        ws.send_text(Key(t_mono_ns=sent, code="KeyA", action="down").model_dump_json())
        ws.send_text(Key(t_mono_ns=sent, code="KeyA", action="up").model_dump_json())
        ws.send_text(ReleaseAll(t_mono_ns=sent).model_dump_json())  # nothing held: no injection
        ws.send_text(Ping(t_mono_ns=1).model_dump_json())
        while json.loads(ws.receive_text())["type"] != "pong":
            pass
    inputs = client.get(f"/debug/latency?since_ns={sent}").json()["inputs"]
    by_kind = {i["kind"]: i for i in inputs}
    down = by_kind["key:KeyA:down"]
    assert down["clock"] == "host" and down["t_sent_host"] == sent
    assert sent <= down["t_arrival"] <= down["t_decided"] <= down["t_injected"]
    assert by_kind["release_all"]["accepted"] is True
    assert by_kind["release_all"]["t_injected"] is None  # nothing was injected


def test_viewer_timing_arrives_on_the_input_socket(make: Make) -> None:
    client, _ = make()
    with client.websocket_connect("/ws/stream", headers={"origin": ORIGIN}) as stream:
        meta = next(
            json.loads(m["text"])
            for m in iter(stream.receive, None)
            if m.get("text") and json.loads(m["text"])["type"] == "frame"
        )
        with client.websocket_connect("/ws/input", headers={"origin": ORIGIN}) as ws:
            now = monotonic_ns()
            timing = ViewerTiming(
                t_mono_ns=1,
                offset_ns=0,
                offset_uncertainty_ns=1_000_000,
                visible=True,
                user_agent="Test/1",
                frames=[
                    FrameTiming(
                        frame_id=meta["frame_id"],
                        recv_ns=now,
                        decoded_ns=now + 2_000_000,
                        painted_ns=now + 5_000_000,
                    )
                ],
            )
            ws.send_text(timing.model_dump_json())
            ws.send_text(Ping(t_mono_ns=1).model_dump_json())
            while json.loads(ws.receive_text())["type"] != "pong":
                pass
    latency = client.get("/health").json()["latency"]
    assert latency["viewer_decode_ms"]["p50"] == 2.0
    assert latency["viewer_paint_wait_ms"]["p50"] == 3.0
    assert latency["viewer_user_agent"] == "Test/1"
    assert "dropped_messages" not in json.dumps(latency)
