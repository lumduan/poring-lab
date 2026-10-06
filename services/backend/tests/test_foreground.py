"""The TYPING-ONLY foreground gate (Batt, 2026-10-06): bot typing needs the lab client in front on
a fresh frame; clicks are never gated; a refusal lets go of the keys the bot holds (never its
mouse buttons); the console path needs its own template (fail closed until calibrated); a
``desktop`` operator window (ASSIST) exempts the agent's own console. These tests run the REAL
gate (marker ``real_foreground``); the screen it looks at is a fake title-bar crop."""

import asyncio
import io
import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from poring_backend import capture_lock as cl
from poring_backend import state as state_module
from poring_backend.config import Settings
from poring_backend.display import Region
from poring_backend.foreground import ForegroundGate
from poring_backend.main import create_app
from poring_backend.mux import Source
from poring_backend.signature import SIG_MATCH, grey_thumb
from poring_env.clock import monotonic_ns
from poring_env.frame import Frame
from poring_env.protocol import AgentHello, AgentInput, Key, Mode, MouseButton, MouseMove, SetMode

pytestmark = pytest.mark.real_foreground

GAME = "80,77,1280,720"
BOX = [6, -24, 56, 16]  # the client's title bar, relative to GAME_REGION (ro_agent's calibration)
REGION = (86, 53, 56, 16)


def title(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 255, (16, 56, 4), dtype=np.uint8)


ACTIVE, OTHER = title(1), title(2)  # the client's active title bar / another window's


class Screen:
    """What the gate's grab returns: a crop, its path and how old the frame is."""

    def __init__(self) -> None:
        self.crop, self.path, self.age_ms = ACTIVE, "x11", 0.0
        self.regions: list[tuple[int, int, int, int]] = []

    def grab(self, region: tuple[int, int, int, int]) -> tuple[int, np.ndarray, str]:
        self.regions.append(region)
        return monotonic_ns() - int(self.age_ms * 1e6), self.crop, self.path


def install(settings_dir: Path, *, rdp: bool = True, stream: bool = False) -> None:
    """As scripts/foreground_template.py does: atomic writes (the status loop reads them)."""
    d = settings_dir / "foreground"
    d.mkdir(parents=True, exist_ok=True)

    def atomic(name: str, data: bytes) -> None:
        tmp = d / f".{name}.tmp"
        tmp.write_bytes(data)
        tmp.replace(d / name)

    atomic("client_title_active.json", json.dumps({"box": BOX}).encode())
    buf = io.BytesIO()
    np.save(buf, grey_thumb(ACTIVE))
    if rdp:
        atomic("client_title_active.npy", buf.getvalue())
    if stream:
        atomic("client_title_active@stream.npy", buf.getvalue())


def test_a_half_written_template_is_no_template_and_never_a_crash(tmp_path: Path) -> None:
    install(tmp_path)
    (tmp_path / "foreground" / "client_title_active.npy").write_bytes(b"\x93NUMPY")  # cut short
    g = gate(tmp_path, Screen())
    assert g.check().reason == "foreground_uncalibrated"
    assert g.snapshot()["calibrated"]["rdp"] is False


# --- the gate on its own --------------------------------------------------------------------------


def gate(tmp_path: Path, screen: Screen) -> ForegroundGate:
    return ForegroundGate(tmp_path, Region.parse(GAME), lambda: screen.grab)


def test_the_gate_reads_the_title_bar_box_and_matches_it(tmp_path: Path) -> None:
    screen = Screen()
    install(tmp_path)
    g = gate(tmp_path, screen)
    ok = g.check()
    assert (ok.ok, ok.reason, ok.distance, ok.path) == (True, "ok", 0.0, "x11")
    assert screen.regions == [REGION]
    screen.crop = OTHER
    bad = g.check()
    assert (bad.ok, bad.reason) == (False, "client_not_foreground")
    assert bad.distance is not None and bad.distance > SIG_MATCH


def test_a_stale_frame_is_never_judged(tmp_path: Path) -> None:
    screen = Screen()
    install(tmp_path)
    screen.age_ms = 450  # older than CITED_MAX_AGE_MS (400): a frozen or static stream
    assert gate(tmp_path, screen).check().reason == "foreground_stale_frame"


def test_no_template_fails_closed(tmp_path: Path) -> None:
    assert gate(tmp_path, Screen()).check().reason == "foreground_uncalibrated"
    install(tmp_path, rdp=False)  # a box but no picture
    assert gate(tmp_path, Screen()).check().reason == "foreground_uncalibrated"


def test_the_console_path_needs_its_own_template(tmp_path: Path) -> None:
    """Batt's answer 2: S2 typing is refused until the @stream template is calibrated."""
    screen = Screen()
    screen.path = "bus"
    install(tmp_path)
    assert gate(tmp_path, screen).check().reason == "foreground_uncalibrated"
    install(tmp_path, stream=True)
    assert gate(tmp_path, screen).check().ok


def test_a_failing_grab_is_a_refusal_never_a_pass(tmp_path: Path) -> None:
    install(tmp_path)

    def broken(region: tuple[int, int, int, int]) -> tuple[int, np.ndarray, str]:
        raise RuntimeError("no display")

    g = ForegroundGate(tmp_path, Region.parse(GAME), lambda: broken)
    result = asyncio.run(g.check_async())
    assert (result.ok, result.reason) == (False, "foreground_check_failed")
    assert g.snapshot()["refused"] == {"foreground_check_failed": 1}


# --- the gate in the backend ----------------------------------------------------------------------


class FakeCapture:
    def grab(self) -> Frame:
        return Frame(frame_id=1, t_capture_ns=monotonic_ns(), width=64, height=36,
                     bgra=bytes(64 * 36 * 4))  # fmt: skip

    def close(self) -> None:
        pass


class FakeInput:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def send_many(self, events: list[Any]) -> None:
        self.events.extend(events)

    def pointer(self) -> tuple[int, int]:
        return (0, 0)

    def has_window_class(self, needle: str) -> bool:
        return False

    def close(self) -> None:
        pass


@pytest.fixture
def lab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        green_interlock: Any) -> Iterator[Callable[..., tuple[TestClient, Screen]]]:  # fmt: skip
    clients: list[TestClient] = []

    def factory(*, green: bool = True, **overrides: Any) -> tuple[TestClient, Screen]:
        screen = Screen()

        class FakeGrabSource:
            def __init__(self, *a: Any, **k: Any) -> None:
                self.grab = screen.grab

        monkeypatch.setattr(state_module, "GrabSource", FakeGrabSource)
        (tmp_path / "lab-state").mkdir(exist_ok=True)
        (tmp_path / "settings").mkdir(exist_ok=True)
        fields: dict[str, Any] = {
            "data_dir": tmp_path / "data", "status_hz": 20.0, "internal_port": 80,
            "public_port": 80, "lab_state_dir": tmp_path / "lab-state",
            "settings_dir": tmp_path / "settings", "game_region": GAME,
        }  # fmt: skip
        fake = FakeInput()
        app = create_app(Settings(**(fields | overrides)), capture_factory=FakeCapture,
                         input_factory=lambda: fake)  # fmt: skip
        client = TestClient(app)
        client.__enter__()
        client.fake = fake  # type: ignore[attr-defined]
        if green:
            green_interlock(client.app.state.poring)
        clients.append(client)
        return client, screen

    yield factory
    for c in clients:
        c.__exit__(None, None, None)


def poring(client: TestClient) -> Any:
    return client.app.state.poring  # type: ignore[attr-defined]


def set_mode(client: TestClient, mode: Mode) -> None:
    with client.websocket_connect("/ws/input") as ws:
        ws.send_text(SetMode(t_mono_ns=1, mode=mode).model_dump_json())
    end = time.monotonic() + 3
    while client.get("/health").json()["mode"] != mode.value:
        assert time.monotonic() < end
        time.sleep(0.02)


def send(ws: Any, *events: Any, sensitive: bool = False) -> dict[str, Any]:
    ws.send_text(AgentInput(t_mono_ns=1, t_capture_ns=1, events=list(events),
                            sensitive=sensitive).model_dump_json())  # fmt: skip
    while True:
        msg = json.loads(ws.receive_text())
        if msg["type"] == "input_ack":
            return msg  # type: ignore[no-any-return]


def bot(client: TestClient, *events: Any, sensitive: bool = False) -> dict[str, Any]:
    """One batch on its own agent connection (a disconnect then releases what the bot holds)."""
    with client.websocket_connect("/internal/agent") as ws:
        ws.send_text(AgentHello(t_mono_ns=1, agent_id="t", version="0").model_dump_json())
        return send(ws, *events, sensitive=sensitive)


def k(code: str, action: str) -> Key:
    return Key(t_mono_ns=1, code=code, action=action)  # type: ignore[arg-type]


def log_lines(tmp_path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted((tmp_path / "data" / "input_log").glob("*.jsonl")):
        out += [json.loads(line) for line in path.read_text().splitlines()]
    return out


def test_the_client_in_front_lets_typing_pass(lab: Any, tmp_path: Path) -> None:
    client, _ = lab()
    install(tmp_path / "settings")
    set_mode(client, Mode.BOT)
    ack = bot(client, k("KeyA", "down"), k("KeyA", "up"))
    assert (ack["accepted"], ack["dropped"]) == (2, 0), ack["reasons"]
    snap = client.get("/health").json()["foreground"]
    assert (snap["state"], snap["passed"], snap["distance"]) == ("ok", 1, 0.0)


def test_another_window_refuses_typing_and_releases_keys_but_never_clicks(
    lab: Any, tmp_path: Path
) -> None:
    client, screen = lab()
    install(tmp_path / "settings")
    set_mode(client, Mode.BOT)
    with client.websocket_connect("/internal/agent") as ws:  # ONE connection: holds survive
        ws.send_text(AgentHello(t_mono_ns=1, agent_id="t", version="0").model_dump_json())
        # the client is in front: the bot holds Shift and the left button (a drag)
        drag = MouseButton(t_mono_ns=1, button="left", action="down", x=0.5, y=0.5)
        first = send(ws, k("ShiftLeft", "down"), drag)
        assert first["accepted"] == 2
        screen.crop = OTHER  # now another window is in front
        ack = send(ws, k("KeyA", "down"), MouseMove(t_mono_ns=1, x=0.6, y=0.6), k("KeyA", "up"))
        assert (ack["accepted"], ack["dropped"]) == (1, 2)  # the move passes, the keys do not
        assert set(ack["reasons"]) == {"client_not_foreground"}
        keys, buttons = poring(client).mux.held(Source.BOT)
        assert keys == frozenset() and buttons == frozenset({"left"})  # Shift let go, drag kept
    lines = log_lines(tmp_path)
    released = [r for r in lines if r["reason"] == "foreground_release"]
    assert [r["event"]["code"] for r in released] == ["ShiftLeft"]
    assert not any(r["event"].get("code") == "KeyA" and r["accepted"] for r in lines)
    health = client.get("/health").json()
    assert health["input_refused"]["bot"]["client_not_foreground"] == 2
    assert health["foreground"]["state"] == "refused"


def test_clicks_moves_and_key_releases_never_ask(lab: Any, tmp_path: Path) -> None:
    client, screen = lab()
    install(tmp_path / "settings")
    screen.crop = OTHER
    set_mode(client, Mode.BOT)
    ack = bot(client, MouseButton(t_mono_ns=1, button="left", action="down", x=0.1, y=0.1),
              MouseButton(t_mono_ns=1, button="left", action="up", x=0.1, y=0.1),
              k("KeyA", "up"))  # fmt: skip
    assert (ack["accepted"], ack["dropped"]) == (3, 0), ack["reasons"]
    assert screen.regions == []  # nothing typed: the gate never looked
    assert client.get("/health").json()["foreground"]["state"] == "unchecked"


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        ({"age_ms": 600}, "foreground_stale_frame"),
        ({"path": "bus"}, "foreground_uncalibrated"),  # no @stream template yet (Batt's answer 2)
    ],
)  # fmt: skip
def test_stale_frames_and_uncalibrated_paths_refuse(
    lab: Any, tmp_path: Path, setup: dict[str, Any], reason: str
) -> None:
    client, screen = lab()
    install(tmp_path / "settings")
    for name, value in setup.items():
        setattr(screen, name, value)
    set_mode(client, Mode.BOT)
    ack = bot(client, k("KeyA", "down"), k("KeyA", "up"))
    assert ack["reasons"] == [reason]


def test_a_sensitive_batch_is_refused_whole_without_key_identities(
    lab: Any, tmp_path: Path
) -> None:
    client, screen = lab()
    install(tmp_path / "settings")
    screen.crop = OTHER
    set_mode(client, Mode.BOT)
    ack = bot(client, k("KeyP", "down"), k("KeyP", "up"), sensitive=True)
    assert (ack["accepted"], ack["dropped"]) == (0, 2)
    assert ack["reasons"] == ["client_not_foreground"]
    text = json.dumps(log_lines(tmp_path))
    assert "KeyP" not in text and "client_not_foreground" in text


def test_a_desktop_operator_window_exempts_the_agents_own_console(lab: Any, tmp_path: Path) -> None:
    """Batt's answer 1: ro_agent's console lines and capture_backend's TSCON type while the
    console, not the client, is in front -- inside a bounded desktop window, ASSIST only."""
    client, screen = lab(assist_lease_s=0.01)
    install(tmp_path / "settings")
    screen.crop = OTHER  # the agent's PowerShell console is in front
    poring(client).interlock.attest = None  # no session: only the window lets the bot act
    now = int(time.time())
    seq = poring(client).capture.seq
    (tmp_path / "lab-state" / cl.WINDOW_NAME).write_text(
        cl.format_window("desktop", now, now + 60, seq, "console"))  # fmt: skip
    set_mode(client, Mode.ASSIST)
    ack = bot(client, k("KeyA", "down"), k("KeyA", "up"))
    assert (ack["accepted"], ack["dropped"]) == (2, 0), ack["reasons"]
    assert screen.regions == []  # exempt: the gate did not look
    assert any(r["reason"] == "foreground_exempt_desktop_window" for r in log_lines(tmp_path))
    assert client.get("/health").json()["foreground"]["exempt"] == 1


def test_the_console_sees_the_gate_and_the_agent_does_not(lab: Any, tmp_path: Path) -> None:
    client, screen = lab()
    install(tmp_path / "settings")
    screen.crop = OTHER
    set_mode(client, Mode.BOT)
    bot(client, k("KeyA", "down"))
    status = poring(client).status()
    assert status.foreground is not None and status.foreground.state == "refused"
    assert status.foreground.refused == 1
    with client.websocket_connect("/internal/agent") as ws:
        while True:
            msg = json.loads(ws.receive_text())
            if msg["type"] == "status":
                assert msg["foreground"] is None and msg["environment"] is None
                break
