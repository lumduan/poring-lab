"""End-to-end through FastAPI with fake X capture/input: real WebSockets, real mux, real log."""

import hashlib
import json
import logging
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
    ClipboardPaste,
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
        self.ctrl = False
        self.on_ctrl_v: Callable[[], None] | None = None  # "Windows" reacting to a paste

    def send_many(self, events: list[InputEvent]) -> None:
        for event in events:
            self.events.append(event)
            if isinstance(event, MouseMove):
                self.pos = to_pixels(event.x, event.y, 1280, 720)
            if isinstance(event, Key) and event.code == "ControlLeft":
                self.ctrl = event.action == "down"
            is_v = isinstance(event, Key) and event.code == "KeyV" and event.action == "down"
            if is_v and self.ctrl and self.on_ctrl_v is not None:
                self.on_ctrl_v()

    def pointer(self) -> tuple[int, int]:
        return self.pos

    def has_window_class(self, needle: str) -> bool:
        return False

    def close(self) -> None:
        pass


Factory = Callable[..., tuple[TestClient, FakeInput]]


@pytest.fixture
def make_client(tmp_path: Path, green_interlock: Any) -> Iterator[Factory]:
    clients: list[TestClient] = []

    def factory(
        *, clipboard: Any = None, green: bool = True, **overrides: Any
    ) -> tuple[TestClient, FakeInput]:
        fake = FakeInput()
        if clipboard is not None:
            fake.on_ctrl_v = clipboard.ctrl_v
        lab_state = tmp_path / "lab-state"  # mounted, no lock file: the default `rdp`
        lab_state.mkdir(exist_ok=True)
        overrides.setdefault("lab_state_dir", lab_state)
        settings = Settings(
            data_dir=tmp_path,
            stream_fps=100.0,
            status_hz=20.0,
            frontend_origins=ORIGIN,
            **overrides,
        )
        app = create_app(
            settings,
            capture_factory=FakeCapture,
            input_factory=lambda: fake,
            clipboard_factory=(lambda: clipboard) if clipboard is not None else None,
        )
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        if green:  # ADR-0016: an attested lab session (tests of the gate itself pass green=False)
            green_interlock(client.app.state.poring)
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


def receive_text_until(ws: WebSocketTestSession, type_: str) -> dict[str, Any]:
    """Like receive_until, but skips the stream's binary JPEG frames."""
    while True:
        raw = ws.receive()
        if raw.get("text"):
            msg: dict[str, Any] = json.loads(raw["text"])
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
    assert body["lease_active"] is False and body["last_human_input_age_s"] is None


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


# --- ADR-0004: human-only clipboard paste -------------------------------------------------------

SECRET_TEXT = "PASTE-SECRET-91c4 สวัสดีครับ"


def paste(ws: WebSocketTestSession, text: str = SECRET_TEXT, request_id: int = 7) -> dict[str, Any]:
    ws.send_text(ClipboardPaste(t_mono_ns=1, request_id=request_id, text=text).model_dump_json())
    return receive_until(ws, "paste_result")


def keys(fake: FakeInput) -> list[tuple[str, str]]:
    return [(e.code, e.action) for e in fake.events if isinstance(e, Key)]


CTRL_V = [("ControlLeft", "down"), ("KeyV", "down"), ("KeyV", "up"), ("ControlLeft", "up")]


def clipboard_client(make_client: Factory, make_xfreerdp: Any, **kw: Any) -> tuple[Any, ...]:
    xfreerdp = make_xfreerdp()
    client, fake = make_client(
        clipboard=xfreerdp, rdp_clipboard="text-to-remote", clipboard_settle_s=0.01, **kw
    )
    return client, fake, xfreerdp


def test_paste_goes_through_the_mux_and_never_logs_its_text(
    make_client: Factory, make_xfreerdp: Any, tmp_path: Path
) -> None:
    client, fake, xfreerdp = clipboard_client(make_client, make_xfreerdp)
    with client.websocket_connect("/ws/input", headers={"origin": ORIGIN}) as ws:
        result = paste(ws)
    assert (result["ok"], result["reason"], result["request_id"]) == (True, "ok", 7)
    assert result["chars"] == len(SECRET_TEXT)
    assert keys(fake) == CTRL_V
    assert ("data", SECRET_TEXT.encode()) in xfreerdp.replies

    lines = log_lines(tmp_path)
    summary = next(r for r in lines if r["event"]["type"] == "clipboard_paste")
    # ADR-0004 amendment c: the event and its time only -- no text, no length, no digest.
    assert summary["event"] == {"type": "clipboard_paste"}
    synthetic = [r for r in lines if r["synthetic"]]
    assert [(r["source"], r["reason"]) for r in synthetic] == [("human", "clipboard_paste")] * 4
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert "PASTE-SECRET" not in path.read_text(errors="replace"), path
    audit = (tmp_path / "transfer_log").glob("*.jsonl")
    record = json.loads(next(audit).read_text().splitlines()[-1])
    assert (record["action"], record["ok"], record["name"]) == ("paste", True, None)
    assert (record["size"], record["sha256"]) == (0, None)
    full = hashlib.sha256(SECRET_TEXT.encode()).hexdigest()
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert full[:8] not in path.read_text(errors="replace"), (
                path
            )  # no digest, not even a prefix
    # ...and the paste is followed by a scrub: CLIPBOARD re-owned (empty) and released again.
    assert xfreerdp.history == ["own", "release", "own", "release"]


def test_paste_needs_a_browser_connection(make_client: Factory, make_xfreerdp: Any) -> None:
    client, fake, _ = clipboard_client(make_client, make_xfreerdp)
    with client.websocket_connect("/ws/input") as ws:  # no Origin: a script, or the agent
        result = paste(ws)
    assert (result["ok"], result["reason"], result["chars"]) == (False, "origin_required", 0)
    assert keys(fake) == []


def test_paste_is_refused_in_bot_mode(make_client: Factory, make_xfreerdp: Any) -> None:
    client, fake, _ = clipboard_client(make_client, make_xfreerdp)
    with client.websocket_connect("/ws/input", headers={"origin": ORIGIN}) as ws:
        ws.send_text(SetMode(t_mono_ns=1, mode=Mode.BOT).model_dump_json())
        sync(ws)
        result = paste(ws)
    assert (result["ok"], result["reason"]) == (False, "mode_bot")
    assert keys(fake) == []


def test_paste_in_assist_takes_the_human_lease(make_client: Factory, make_xfreerdp: Any) -> None:
    client, fake, _ = clipboard_client(make_client, make_xfreerdp)
    with client.websocket_connect("/ws/input", headers={"origin": ORIGIN}) as ws:
        ws.send_text(SetMode(t_mono_ns=1, mode=Mode.ASSIST).model_dump_json())
        sync(ws)
        assert paste(ws)["ok"]
        sync(ws)  # the input socket is still live
    assert keys(fake) == CTRL_V


def test_paste_is_off_unless_configured(make_client: Factory) -> None:
    client, fake = make_client()
    with client.websocket_connect("/ws/input", headers={"origin": ORIGIN}) as ws:
        result = paste(ws)
    assert (result["ok"], result["reason"]) == (False, "clipboard_disabled")
    with client.websocket_connect("/ws/stream", headers={"origin": ORIGIN}) as ws:
        status = receive_text_until(ws, "status")
    assert (status["clipboard_enabled"], status["transfer_enabled"]) == (False, False)


def test_status_advertises_the_clipboard(make_client: Factory, make_xfreerdp: Any) -> None:
    client, _, _ = clipboard_client(make_client, make_xfreerdp)
    with client.websocket_connect("/ws/stream", headers={"origin": ORIGIN}) as ws:
        assert receive_text_until(ws, "status")["clipboard_enabled"] is True
    health = client.get("/health").json()["clipboard"]
    assert health["enabled"] is True and health["foreign_owner_clears"] == 0
    assert health["rdp_empty_claims"] == 0


# --- no silent drops ---------------------------------------------------------------------------


def test_invalid_input_is_answered_counted_and_logged_once(
    make_client: Factory, caplog: pytest.LogCaptureFixture
) -> None:
    client, fake = make_client()
    missing_ts = '{"type":"key","frame_id":0,"code":"KeyA","action":"down"}'
    with (
        caplog.at_level(logging.WARNING, logger="poring_backend.drops"),
        client.websocket_connect("/ws/input", headers={"origin": ORIGIN}) as ws,
    ):
        ws.send_text(missing_ts)
        error = receive_until(ws, "error")
        for _ in range(4):
            ws.send_text(missing_ts)
        ws.send_text("{not json")
        ws.send_bytes(b"\x00\x01")
        sync(ws)  # still connected after all of it
    assert (error["channel"], error["reason"], error["ref_type"]) == (
        "ws_input",
        "missing:key.t_mono_ns",
        "key",
    )
    dropped = client.get("/health").json()["dropped_messages"]["ws_input"]
    assert dropped == {"binary_frame": 1, "json_invalid": 1, "missing:key.t_mono_ns": 5}
    warnings = [r.getMessage() for r in caplog.records if r.name == "poring_backend.drops"]
    assert len(warnings) == 3  # one per reason, the burst of 5 is rate-limited
    assert not any(isinstance(e, Key) for e in fake.events)


def test_invalid_agent_messages_are_answered(make_client: Factory) -> None:
    client, _ = make_client(internal_port=80)
    with client.websocket_connect("/internal/agent") as ws:
        ws.send_text('{"type":"agent_input","t_mono_ns":1,"frame_id":1,"t_capture_ns":1}')
        error = receive_until(ws, "error")
    assert (error["channel"], error["reason"]) == ("agent", "missing:agent_input.events")
    assert client.get("/health").json()["dropped_messages"]["agent"] == {
        "missing:agent_input.events": 1
    }


def test_invalid_stream_messages_are_answered(make_client: Factory) -> None:
    client, _ = make_client()
    with client.websocket_connect("/ws/stream", headers={"origin": ORIGIN}) as ws:
        ws.send_text('{"type":"ping"}')
        error = receive_text_until(ws, "error")
    assert (error["channel"], error["reason"]) == ("ws_stream", "missing:ping.t_mono_ns")


def test_mux_refusals_are_counted_in_health(make_client: Factory) -> None:
    client, _ = make_client(internal_port=80)
    with client.websocket_connect("/internal/agent") as ws:
        send_agent_key(ws, "KeyA")
    assert client.get("/health").json()["input_refused"] == {"bot": {"mode=HUMAN": 1}}


# --- the capture-backend lock (ADR-0009) ---------------------------------------------------------


def write_lock(directory: Path, backend: str, seq: int = 3) -> None:
    directory.mkdir(exist_ok=True)
    (directory / "capture-backend").write_text(f"BACKEND={backend}\nSEQ={seq}\nPHASE=steady\n")


def test_health_reports_the_lock_default_rdp(make_client: Factory) -> None:
    client, _ = make_client()
    lock = client.get("/health").json()["capture_backend"]
    assert (lock["backend"], lock["phase"]) == ("rdp", "steady")


def test_console_mode_refuses_paste_and_hides_paste_and_files(
    make_client: Factory, make_xfreerdp: Any, tmp_path: Path
) -> None:
    write_lock(tmp_path / "lab-state", "console", seq=12)
    client, fake, _ = clipboard_client(make_client, make_xfreerdp)
    with client.websocket_connect("/ws/stream", headers={"origin": ORIGIN}) as ws:
        status = receive_text_until(ws, "status")
    assert (
        status["capture_backend"]["backend"] == "console" and status["capture_backend"]["seq"] == 12
    )
    assert (status["clipboard_enabled"], status["transfer_enabled"]) == (False, False)
    with client.websocket_connect("/ws/input", headers={"origin": ORIGIN}) as ws:
        result = paste(ws)
    assert (result["ok"], result["reason"]) == (False, "console_backend")
    assert keys(fake) == []  # no Ctrl+V reached the (Moonlight) display
    health = client.get("/health").json()
    assert health["clipboard"]["paste_available"] is False
    assert health["input_refused"]["human"]["paste:console_backend"] == 1


def test_an_unmounted_lock_holds_and_refuses_paste(
    make_client: Factory, make_xfreerdp: Any, tmp_path: Path
) -> None:
    client, fake, _ = clipboard_client(
        make_client, make_xfreerdp, lab_state_dir=tmp_path / "not-mounted"
    )
    assert client.get("/health").json()["capture_backend"]["backend"] == "hold"
    with client.websocket_connect("/ws/input", headers={"origin": ORIGIN}) as ws:
        result = paste(ws)
    assert (result["ok"], result["reason"]) == (False, "backend_hold")
    assert keys(fake) == []


def test_health_and_status_show_the_clean_room_only_under_its_lock(
    make_client: Factory, tmp_path: Path
) -> None:
    import time

    lab_state = tmp_path / "lab-state"
    lab_state.mkdir(exist_ok=True)
    cap = int(time.time()) + 3600
    (lab_state / "cleanroom").write_text(f"VARIANT=V3\nBOX_UNTIL=\nHARD_CAP={cap}\n")
    write_lock(lab_state, "console", seq=20)  # REASON missing: not a clean room
    client, _ = make_client()
    assert client.get("/health").json()["cleanroom"] is None
    (lab_state / "capture-backend").write_text(
        "BACKEND=console\nSEQ=21\nPHASE=steady\nREASON=cleanroom\n"
    )
    deadline = time.monotonic() + 5
    while (room := client.get("/health").json()["cleanroom"]) is None:
        assert time.monotonic() < deadline, "the status loop never re-read the lab state"
        time.sleep(0.05)
    assert (room["variant"], room["streaming"], room["box_left_s"]) == ("V3", True, None)
    assert 3500 < room["hard_cap_left_s"] <= 3600
    with client.websocket_connect("/ws/stream", headers={"origin": ORIGIN}) as ws:
        assert receive_text_until(ws, "status")["cleanroom"]["variant"] == "V3"


def _restore_marker(lab_state: Path, seq: int, age_s: float) -> None:
    from poring_backend.mode_restore import format_marker

    lab_state.mkdir(exist_ok=True)
    write_lock(lab_state, "rdp", seq=seq)
    (lab_state / "mux-restore").write_text(format_marker(seq, int(time.time() - age_s)))


def test_a_guarded_restart_restores_assist_logged_and_shown(
    make_client: Factory, tmp_path: Path
) -> None:
    _restore_marker(tmp_path / "lab-state", seq=40, age_s=5)
    client, _ = make_client()
    body = client.get("/health").json()
    assert (body["mode"], body["mode_restored"]) == ("ASSIST", True)
    [record] = [r for r in log_lines(tmp_path) if r["reason"] == "mode_restore"]
    assert (record["source"], record["synthetic"], record["mode"]) == ("backend", True, "ASSIST")
    assert record["event"]["by"] == "guarded_build" and "seq 40 unchanged" in record["event"]["why"]
    with client.websocket_connect("/ws/stream", headers={"origin": ORIGIN}) as ws:
        assert receive_text_until(ws, "status")["mode_restored"] is True  # the console's notice
    with client.websocket_connect("/ws/input", headers={"origin": ORIGIN}) as ws:
        ws.send_text(SetMode(t_mono_ns=1, mode=Mode.ASSIST).model_dump_json())
        sync(ws)
    assert client.get("/health").json()["mode_restored"] is False  # a human chose it since


@pytest.mark.parametrize(("seq_now", "age_s"), [(41, 5), (40, 300)])
def test_a_stale_or_post_handover_marker_boots_human(
    make_client: Factory, tmp_path: Path, seq_now: int, age_s: float
) -> None:
    _restore_marker(tmp_path / "lab-state", seq=40, age_s=age_s)
    write_lock(tmp_path / "lab-state", "rdp", seq=seq_now)
    client, _ = make_client()
    body = client.get("/health").json()
    assert (body["mode"], body["mode_restored"]) == ("HUMAN", False)
    assert not [r for r in log_lines(tmp_path) if r["reason"] == "mode_restore"]


def test_health_reports_the_frame_bus_inert_without_a_ring(make_client: Factory) -> None:
    client, _ = make_client()
    bus = client.get("/health").json()["framebus"]
    assert (bus["active"], bus["writer"], bus["path"]) == ("x11", None, "/framebus/ring")


def test_a_safety_alarm_reaches_health_and_status(make_client: Factory, tmp_path: Path) -> None:
    """2026-10-04: state/cleanroom-alarm (capture_backend.py alarm) -> /health.alarms + Status."""
    lab_state = tmp_path / "lab-state"
    lab_state.mkdir(exist_ok=True)
    (lab_state / "cleanroom-alarm").write_text("ALARM=watchdog_down\nSINCE=1791000000\n")
    client, _ = make_client(lab_state_dir=lab_state)
    assert client.get("/health").json()["alarms"] == ["watchdog_down"]


# --- ADR-0005 option c2 (2026-10-04): the agent network reaches only the internal listener -------


def test_the_agent_network_is_refused_on_the_public_listener(tmp_path: Path) -> None:
    from starlette.testclient import TestClient

    from poring_backend.agent_net import AgentNetworkGuard

    lab_state = tmp_path / "lab-state"
    lab_state.mkdir()
    settings = Settings(data_dir=tmp_path, lab_state_dir=lab_state, frontend_origins=ORIGIN)
    app = create_app(settings, capture_factory=FakeCapture, input_factory=FakeInput)
    before = AgentNetworkGuard.refused
    with TestClient(app, client=("10.210.97.7", 40000)) as agent:
        assert agent.get("/health").status_code == 403
        assert agent.get("/transfer/files", headers={"origin": ORIGIN}).status_code == 403
        # closed before accept: a forged Origin changes nothing
        with (
            pytest.raises(WebSocketDisconnect),
            agent.websocket_connect("/ws/input", headers={"origin": ORIGIN}),
        ):
            pass
    with TestClient(app, client=("192.168.1.20", 40000)) as lan:
        assert lan.get("/health").status_code == 200  # LAN viewers unchanged
    assert AgentNetworkGuard.refused >= before + 3


def test_the_agent_network_still_reaches_the_internal_listener(tmp_path: Path) -> None:
    from starlette.testclient import TestClient

    lab_state = tmp_path / "lab-state"
    lab_state.mkdir()
    settings = Settings(data_dir=tmp_path, lab_state_dir=lab_state, frontend_origins=ORIGIN,
                        internal_port=80)  # TestClient arrives on port 80  # fmt: skip
    app = create_app(settings, capture_factory=FakeCapture, input_factory=FakeInput)
    with TestClient(app, client=("10.210.97.7", 40000)) as agent:
        assert agent.get("/health").status_code == 200  # the internal listener is never guarded
