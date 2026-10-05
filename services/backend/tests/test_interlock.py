"""The environment interlock (ADR-0016, rewritten 2026-10-04): the per-failure table, expiry, the
operator windows, the mux gate, and that the agent can neither claim nor see green."""

import json
import time
import typing
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from poring_backend import capture_lock as cl
from poring_backend.config import Settings
from poring_backend.interlock import EnvironmentsConfig, Window, evaluate, load_config
from poring_backend.main import create_app
from poring_backend.mux import InputMux, Source
from poring_env.clock import FrameCounter, monotonic_ns
from poring_env.frame import Frame
from poring_env.protocol import (
    AgentHello,
    AgentInput,
    CaptureBackend,
    Key,
    Mode,
    MouseButton,
    MouseMove,
    Ping,
    ReleaseAll,
    SetMode,
    Wheel,
    parse_agent_to_backend,
)
from poring_packets.events import Attestation

ROOT = Path(__file__).resolve().parents[3]
HOST, AGENT, GM = "192.168.1.169", 2000001, 2000002
STEADY = CaptureBackend(backend="console", seq=7, phase="steady")
CFG = EnvironmentsConfig.model_validate({
    "version": 1, "attestation_max_age_s": 10, "window_max_s": 120,
    "environments": [
        {"id": "lab-rathena", "status": "allowed", "adr": "ADR-0006", "windows_host": HOST,
         "accounts": [AGENT, GM], "signals": ["lab_host", "session"]},
        {"id": "community", "status": "pending", "adr": "ADR-0006", "signals": []},
    ],
})  # fmt: skip


def attest(**over: Any) -> Attestation:
    base: dict[str, Any] = {"t_mono_ns": 1, "client_ip": HOST, "session_live": True, "aid": AGENT,
                            "last_packet_age_ms": 200, "map_conns": 1,
                            "server": "lab-rathena"}  # fmt: skip
    return Attestation(**(base | over))


def verdict(cfg: EnvironmentsConfig | None = CFG, *, mode: Mode = Mode.BOT, lock: Any = STEADY,
            win_host: str = HOST, att: Attestation | None = None, age: float | None = 1.0,
            window: Window | None = None, err: str = "") -> Any:  # fmt: skip
    return evaluate(cfg, err, mode=mode, lock=lock, win_host=win_host,
                    attest=attest() if att is None else att, attest_age_s=age,
                    window=window)  # fmt: skip


# --- the per-failure table ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"cfg": None, "err": "config_missing"}, "config_missing"),
        ({"cfg": None, "err": "config_invalid"}, "config_invalid"),
        ({"lock": CaptureBackend(backend="hold", reason="x")}, "lock_not_steady"),
        ({"lock": CaptureBackend(backend="console", seq=7, phase="switching")}, "lock_not_steady"),
        ({"win_host": "192.168.1.170"}, "host_mismatch"),
        ({"age": None}, "no_attestation"),
        ({"age": 10.5}, "attestation_stale"),
        ({"att": attest(client_ip="192.168.1.50")}, "client_ip_mismatch"),
        ({"att": attest(session_live=False, aid=None)}, "no_session"),
        ({"att": attest(aid=1234567)}, "account_not_lab"),
        ({"att": attest(server="lab-rathena-th")}, "server_mismatch"),  # another server's sniffer
        ({"att": attest(server=None)}, "server_mismatch"),  # an unnamed sniffer: never green
    ],
)  # fmt: skip
def test_every_failure_is_red_for_the_bot(kwargs: dict[str, Any], reason: str) -> None:
    for mode in (Mode.BOT, Mode.ASSIST):
        v = verdict(mode=mode, **kwargs)
        assert (v.green, v.bot_allowed, v.reason) == (False, False, reason)
        assert v.status().state == "red"


def test_an_attested_lab_session_is_green_for_both_lab_accounts() -> None:
    for aid in (AGENT, GM):
        v = verdict(att=attest(aid=aid))
        assert (v.green, v.bot_allowed, v.env_id, v.status().state) == (
            True, True, "lab-rathena", "green")  # fmt: skip


def test_a_pending_or_forbidden_environment_is_never_green() -> None:
    only_pending = EnvironmentsConfig.model_validate(
        CFG.model_dump() | {"environments": [CFG.environments[1].model_dump()]}
    )
    assert verdict(only_pending).reason == "env_pending"
    lab_pending = CFG.model_copy(deep=True)
    lab_pending.environments[0].status = "pending"
    assert not verdict(lab_pending).bot_allowed


def test_the_attestation_expires() -> None:
    assert verdict(age=9.9).green
    assert verdict(age=10.1).reason == "attestation_stale"


# --- operator windows -----------------------------------------------------------------------------

WIN = Window("login", time.time() + 60, 60.0, "login")


def test_a_window_lets_assist_through_and_never_bot_mode() -> None:
    red = {"age": None}
    v = verdict(mode=Mode.ASSIST, window=WIN, **red)
    assert (v.green, v.bot_allowed, v.reason, v.status().state) == (
        False, True, "window:login", "window")  # fmt: skip
    v = verdict(mode=Mode.BOT, window=WIN, **red)
    assert (v.bot_allowed, v.reason) == (False, "no_attestation")


def test_the_window_file_is_bounded_tied_to_the_lock_and_expires() -> None:
    now = 1_000_000
    good = cl.format_window("login", now, now + 90, 7, "login")
    assert cl.parse_window(good, STEADY, now + 10)[:1] == ("login",)  # type: ignore[index]
    assert cl.parse_window(good, STEADY, now + 91) is None  # expired
    assert cl.parse_window(good, STEADY.model_copy(update={"seq": 8}), now + 10) is None  # handover
    switching = STEADY.model_copy(update={"phase": "switching"})
    assert cl.parse_window(good, switching, now + 10) is None  # a login window: never mid-handover
    desk = cl.format_window("desktop", now, now + 60, 7, "to-console-tscon")
    assert cl.parse_window(desk, switching, now + 10) is not None  # capture_backend's own tscon
    assert cl.parse_window(desk, CaptureBackend(backend="hold", reason="x"), now + 10) is None
    long = good.replace(f"UNTIL={now + 90}", f"UNTIL={now + 121}")
    assert cl.parse_window(long, STEADY, now + 10) is None  # longer than 120 s: refused
    assert cl.parse_window(good, STEADY, now + 10, max_s=60) is None  # the config's bound
    assert cl.parse_window(good.replace("WINDOW=login", "WINDOW=ingame"), STEADY, now) is None
    assert cl.parse_window(good + "EXTRA=$(x)\n", STEADY, now + 1) is None  # malformed: none
    with pytest.raises(ValueError, match="1..120"):
        cl.format_window("desktop", now, now + 121, 7, "x")
    with pytest.raises(ValueError, match="unknown window"):
        cl.format_window("game", now, now + 10, 7, "x")


# --- the mux gate ---------------------------------------------------------------------------------


def test_the_mux_refuses_bot_presses_and_lets_releases_through() -> None:
    mux = InputMux(lease_ns=1, mode=Mode.BOT)
    down = Key(t_mono_ns=1, code="KeyA", action="down")
    assert mux.submit(Source.BOT, down, 1).accepted  # green: held
    presses = [
        Key(t_mono_ns=2, code="KeyB", action="down"),
        MouseMove(t_mono_ns=2, x=0.5, y=0.5),
        MouseButton(t_mono_ns=2, button="left", action="down"),
        Wheel(t_mono_ns=2, dy=1),
    ]
    for press in presses:
        d = mux.submit(Source.BOT, press, 2, bot_allowed=False)
        assert (d.accepted, d.reason) == (False, "environment_unattested")
    up = mux.submit(Source.BOT, Key(t_mono_ns=3, code="KeyA", action="up"), 3, bot_allowed=False)
    assert up.accepted and not mux.holds_anything(Source.BOT)
    release = MouseButton(t_mono_ns=4, button="left", action="up", x=0.9, y=0.9)
    d = mux.submit(Source.BOT, release, 4, bot_allowed=False)
    event = d.inject[0].event
    assert d.accepted and isinstance(event, MouseButton) and (event.x, event.y) == (None, None)
    assert mux.submit(Source.BOT, ReleaseAll(t_mono_ns=5), 5, bot_allowed=False).accepted


def test_release_bot_lets_go_of_everything_and_the_human_is_never_gated() -> None:
    mux = InputMux(lease_ns=1, mode=Mode.ASSIST)
    mux.submit(Source.BOT, Key(t_mono_ns=1, code="KeyW", action="down"), 1)
    mux.submit(Source.BOT, MouseButton(t_mono_ns=1, button="right", action="down"), 1)
    released = mux.release_bot(2)
    assert {r.reason for r in released} == {"interlock_release"} and len(released) == 2
    assert not mux.holds_anything(Source.BOT)
    human = mux.submit(Source.HUMAN, Key(t_mono_ns=3, code="KeyA", action="down"), 3,
                       bot_allowed=False)  # fmt: skip
    assert human.accepted


# --- the app: config, /health, Status, the agent's view -------------------------------------------


class FakeCapture:
    def __init__(self) -> None:
        self.counter = FrameCounter()

    def grab(self) -> Frame:
        return Frame(frame_id=self.counter.next(), t_capture_ns=monotonic_ns(), width=64,
                     height=36, bgra=bytes(64 * 36 * 4))  # fmt: skip

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
def app_client(tmp_path: Path) -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def factory(**overrides: Any) -> TestClient:
        lab = tmp_path / "lab-state"
        lab.mkdir(exist_ok=True)
        fields: dict[str, Any] = {"data_dir": tmp_path, "status_hz": 20.0, "lab_state_dir": lab,
                                  "internal_port": 80, "public_port": 80,
                                  "environments_file": tmp_path / "environments.yaml",
                                  "win_host": HOST, "ingest_peer": "testclient"}  # fmt: skip
        settings = Settings(**(fields | overrides))
        fake = FakeInput()
        app = create_app(settings, capture_factory=FakeCapture, input_factory=lambda: fake)
        client = TestClient(app)
        client.__enter__()
        client.fake = fake  # type: ignore[attr-defined]
        clients.append(client)
        return client

    yield factory
    for c in clients:
        c.__exit__(None, None, None)


def write_config(path: Path, cfg: EnvironmentsConfig = CFG) -> None:
    import yaml

    path.write_text(yaml.safe_dump(cfg.model_dump(mode="json", exclude_none=True)))


def state(client: TestClient) -> Any:
    return client.app.state.poring  # type: ignore[attr-defined]


def wait(pred: Callable[[], bool], timeout: float = 3.0) -> None:
    end = time.monotonic() + timeout
    while not pred():
        if time.monotonic() > end:
            raise AssertionError("timed out")
        time.sleep(0.02)


def bot(client: TestClient, *events: Any) -> dict[str, Any]:
    with client.websocket_connect("/internal/agent") as ws:
        ws.send_text(AgentHello(t_mono_ns=1, agent_id="t", version="0").model_dump_json())
        ws.send_text(AgentInput(t_mono_ns=1, t_capture_ns=1, events=list(events)).model_dump_json())
        while True:
            msg = json.loads(ws.receive_text())
            if msg["type"] == "input_ack":
                return msg


def set_mode(client: TestClient, mode: Mode) -> None:
    with client.websocket_connect("/ws/input") as ws:
        ws.send_text(SetMode(t_mono_ns=1, mode=mode).model_dump_json())
    wait(lambda: client.get("/health").json()["mode"] == mode.value)


def test_no_config_file_fails_closed_and_the_committed_one_is_valid(app_client: Any) -> None:
    client = app_client()
    set_mode(client, Mode.BOT)
    ack = bot(client, Key(t_mono_ns=1, code="KeyA", action="down"))
    assert ack["reasons"] == ["environment_unattested"]
    env = client.get("/health").json()["environment"]
    assert (env["state"], env["reason"], env["config"]) == ("red", "config_missing",
                                                            "config_missing")  # fmt: skip
    committed, err = load_config(ROOT / "config" / "environments.yaml")
    assert err == "" and committed is not None
    lab = {e.id: e for e in committed.environments}
    assert lab["lab-rathena"].status == "allowed" and lab["lab-rathena"].windows_host == HOST
    assert set(lab["lab-rathena"].accounts) == {AGENT, GM}
    assert lab["community-bot-testing"].status == "pending"


def test_attested_green_then_expiry_releases_what_the_bot_holds(
    app_client: Any, tmp_path: Path
) -> None:
    write_config(tmp_path / "environments.yaml")
    client = app_client()
    set_mode(client, Mode.BOT)
    with client.websocket_connect("/ingest/packets") as ingest:  # the sniffer's channel
        ingest.send_text(attest().model_dump_json())
    wait(lambda: client.get("/health").json()["environment"]["state"] == "green")
    with client.websocket_connect("/internal/agent") as ws:  # held open: a disconnect releases too
        ws.send_text(AgentHello(t_mono_ns=1, agent_id="t", version="0").model_dump_json())
        down = Key(t_mono_ns=1, code="KeyW", action="down")
        ws.send_text(AgentInput(t_mono_ns=1, t_capture_ns=1, events=[down]).model_dump_json())
        while (ack := json.loads(ws.receive_text()))["type"] != "input_ack":
            pass
        assert (ack["accepted"], ack["dropped"]) == (1, 0)
        assert state(client).mux.holds_anything(Source.BOT)
        state(client).interlock.attest_at_ns -= 11_000_000_000  # 11 s without a refresh
        wait(lambda: not state(client).mux.holds_anything(Source.BOT))
    released = [r for r in client.get("/health").json()["environment"].items()]
    assert released
    ups = [e for e in client.fake.events if isinstance(e, Key) and e.code == "KeyW"]  # type: ignore[attr-defined]
    assert [e.action for e in ups] == ["down", "up"]
    health = client.get("/health").json()
    assert (health["environment"]["state"], health["environment"]["reason"]) == (
        "red", "attestation_stale")  # fmt: skip
    ack = bot(client, Key(t_mono_ns=1, code="KeyW", action="down"))
    assert ack["reasons"] == ["environment_unattested"]


def test_an_operator_window_opens_assist_only(app_client: Any, tmp_path: Path) -> None:
    write_config(tmp_path / "environments.yaml")
    client = app_client(assist_lease_s=0.01)  # the mode switch's own release takes no lease
    lab = tmp_path / "lab-state"
    now = int(time.time())
    lock = state(client).capture
    (lab / cl.WINDOW_NAME).write_text(cl.format_window("login", now, now + 60, lock.seq, "login"))
    set_mode(client, Mode.ASSIST)
    ack = bot(client, Key(t_mono_ns=1, code="KeyA", action="down"),
              Key(t_mono_ns=1, code="KeyA", action="up"))  # fmt: skip
    assert (ack["accepted"], ack["dropped"]) == (2, 0), ack["reasons"]
    assert client.get("/health").json()["environment"]["window"] == "login"
    set_mode(client, Mode.BOT)
    ack = bot(client, Key(t_mono_ns=1, code="KeyA", action="down"))
    assert ack["reasons"] == ["environment_unattested"]  # never in BOT mode


def test_the_agent_can_neither_claim_nor_see_green(app_client: Any, tmp_path: Path) -> None:
    write_config(tmp_path / "environments.yaml")
    client = app_client(ingest_peer="10.210.96.6")  # the pinned sniffer peer: NOT this client
    # 1. no agent message type can carry an attestation or an environment
    hints = typing.get_type_hints(AgentInput) | typing.get_type_hints(AgentHello)
    assert "environment" not in hints and "attest" not in json.dumps(
        [str(t) for t in hints.values()])  # fmt: skip
    with pytest.raises(ValueError):
        parse_agent_to_backend(attest().model_dump_json())
    # 2. an attestation over the agent channel is dropped, not obeyed
    with client.websocket_connect("/internal/agent") as ws:
        ws.send_text(attest().model_dump_json())
        assert json.loads(ws.receive_text())["type"] in ("status", "error")
    # 3. the ingest channel refuses any peer but the sniffer's pinned address
    with pytest.raises(Exception), client.websocket_connect("/ingest/packets") as ws:  # noqa: B017
        ws.send_text(attest().model_dump_json())
        ws.receive_text()
    assert state(client).interlock.attestations == 0
    # 4. the agent's Status never shows the interlock; a human's does
    with client.websocket_connect("/internal/agent") as ws:
        ws.send_text(AgentHello(t_mono_ns=1, agent_id="t", version="0").model_dump_json())
        while (msg := json.loads(ws.receive_text()))["type"] != "status":
            pass
        assert msg["environment"] is None
    with client.websocket_connect("/ws/stream") as ws:  # the console's status channel
        while True:
            raw = ws.receive()
            if raw.get("text") and (msg := json.loads(raw["text"]))["type"] == "status":
                break
        assert msg["environment"]["state"] == "red"


def test_human_input_passes_while_red(app_client: Any) -> None:
    client = app_client()
    with client.websocket_connect("/ws/input") as ws:
        ws.send_text(Key(t_mono_ns=1, code="KeyH", action="down").model_dump_json())
        ws.send_text(Key(t_mono_ns=1, code="KeyH", action="up").model_dump_json())
        ws.send_text(Ping(t_mono_ns=1).model_dump_json())
        while json.loads(ws.receive_text())["type"] != "pong":
            pass
    keys = [e.code for e in client.fake.events if isinstance(e, Key)]  # type: ignore[attr-defined]
    assert keys[:2] == ["KeyH", "KeyH"]
    assert client.get("/health").json()["environment"]["state"] == "red"
