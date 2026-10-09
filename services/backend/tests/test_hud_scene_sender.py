"""scripts/hud_scene.py's Sender, the display channel (2026-10-09: after a guarded backend recreate
the HUD scene process sat on a dead websocket). A dead link is noticed, re-made with backoff (1 s
doubling to 30 s, forever, one log line per state change), every connection starts with a KEYFRAME,
and the messages that found the link down are dropped and counted. Display only: nothing but the
scene's own messages ever leaves."""

from __future__ import annotations

import importlib.util
import json
import queue
import socket
import sys
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from websockets.exceptions import ConnectionClosedError
from websockets.protocol import State

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
REGION, DESKTOP = (80, 77, 1280, 720), (1440, 900)
WINDOWS = [(0, 0, 220, 326), (1135, 14, 1266, 162)]


@pytest.fixture(scope="module")
def hs() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("hud_scene", SCRIPTS / "hud_scene.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hud_scene"] = mod  # its dataclass resolves its module by name
    spec.loader.exec_module(mod)
    return mod


def unit(cls: str, x: float, y: float) -> dict[str, Any]:
    return {"kind": "unit", "cls": cls, "conf": 0.8, "box": [x - 15, y - 60, x + 15, y]}


class FakeLink:
    """A connection that a backend recreate can kill; it keeps what it received."""

    def __init__(self) -> None:
        self.got: list[dict[str, Any]] = []
        self.state = State.OPEN

    def send(self, text: str) -> None:
        if self.state is not State.OPEN:
            raise ConnectionClosedError(None, None)
        self.got.append(json.loads(text))

    def recv(self, timeout: float | None = None) -> str:
        if self.state is not State.OPEN:
            raise ConnectionClosedError(None, None)
        raise TimeoutError  # the display channel never replies unless a message was refused

    def close(self) -> None:
        self.state = State.CLOSED


class Scene:
    """A tracker plus its producers, as serve() wires them: messages are made AND queued under the
    tracker's lock, and the Sender's keyframe is the tracker's state at that moment."""

    def __init__(self, hs: ModuleType, out_kw: dict[str, Any]) -> None:
        self.t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
        self.out = hs.Sender(keyframe=self.keyframe, lock=self.t.lock, **out_kw)

    def keyframe(self) -> dict[str, Any]:
        return {"type": "hud_scene", "t_mono_ns": 1, "frame_id": 7, **self.t.keyframe()}

    def detect(self, found: list[dict[str, Any]]) -> None:
        with self.t.lock:
            d = self.t.observe(found, self.t.offset.copy())
            if d is not None:
                self.out.put({"type": "hud_delta", "t_mono_ns": 1, "frame_id": 7, **d})

    def pump(self) -> None:
        while not self.out.q.empty():
            self.out.step(self.out.q.get())


def test_a_dead_link_is_dropped_redialled_and_rebuilt_with_a_keyframe_first(
    hs: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    import hud_scene_check as hc

    monkeypatch.setattr(hs, "SCENE_LOG", tmp_path / "scene.jsonl")
    now, links, attempts = [100.0], [], []
    plan = ["up", "refused", "refused", "up"]

    def connect() -> FakeLink:
        attempts.append(now[0])
        if plan.pop(0) == "refused":
            raise ConnectionRefusedError("the new backend is not listening yet")
        links.append(FakeLink())
        return links[-1]

    sc = Scene(hs, {"connect": connect, "clock": lambda: now[0]})
    out = sc.out
    out.step(None)  # the first connection: a keyframe before anything else
    assert links[0].got[0]["type"] == "hud_scene" and out.state == "up"
    sc.detect([unit("npc", 700, 400)])
    sc.detect([unit("npc", 700, 400)])  # seen twice: drawn, seq 1
    sc.pump()
    assert [m["seq"] for m in links[0].got if m["type"] == "hud_delta"] == [1]

    links[0].state = State.CLOSED  # the backend recreate closed it
    sc.detect([unit("npc", 760, 400)])  # seq 2 (the drifted box moves): finds the link down
    sc.pump()
    assert out.state == "down" and out.dropped == 1 and len(links[0].got) == 2  # nothing more
    for dt in (1.0, 1.75, 0.25):  # attempts at +1 s (refused), none at +2.75, +3 s (refused)
        now[0] += dt
        out.step(None)
    assert [a - attempts[1] for a in attempts[1:]] == [0.0, pytest.approx(2.0)]
    sc.detect([unit("npc", 820, 400)])  # seq 3, queued while down, before the reconnect
    now[0] += 4.0
    out.step(None)  # back (+4 s): the keyframe first, and the queued seq 3 it carries is not sent
    link = links[1]
    assert out.state == "up" and out.connects == 2 and out.superseded == 1
    assert link.got[0]["type"] == "hud_scene" and link.got[0]["seq"] == sc.t.seq == 3
    sc.detect([unit("npc", 880, 400)])  # seq 4: right after the keyframe, as a console wants it
    sc.pump()
    assert [m["type"] for m in link.got] == ["hud_scene", "hud_delta"] and link.got[1]["seq"] == 4

    # a console fed by the new link only is current: not stale, the NPC where it was last seen
    rp = hc.Replay([{"logged_ns": i, "msg": m} for i, m in enumerate(link.got)])
    rp.advance(10)
    npc = [o for o in rp.boxes(1, *DESKTOP, 80, 77) if o["kind"] == "unit"]
    assert not rp.stale and len(npc) == 1 and npc[0]["px"][0] == pytest.approx(880 - 15)

    # quiet: one line down, one line back (the first connect has its own)
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "display channel" in ln]
    assert len(lines) == 3 and "DOWN" in lines[1] and "UP again" in lines[2]
    assert "3 attempts, 1 messages dropped" in lines[2]
    # the log keeps every message, tagged when it did not leave; a replay skips those
    logged = [json.loads(ln) for ln in (tmp_path / "scene.jsonl").read_text().splitlines()]
    assert sorted(e.get("link", "sent") for e in logged).count("dropped") == 1
    assert sum(e.get("link") == "superseded" for e in logged) == 1
    assert all("link" not in e for e in hc.load_log(log=tmp_path / "scene.jsonl"))


def test_the_backoff_doubles_to_30_s_and_logs_once(
    hs: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(hs, "SCENE_LOG", tmp_path / "scene.jsonl")
    now, attempts = [0.0], []

    def connect() -> None:
        attempts.append(now[0])
        raise OSError("no route to host")

    out = hs.Sender(connect=connect, clock=lambda: now[0])
    while now[0] < 200:
        out.step({"type": "hud_motion", "t_mono_ns": 1, "frame_id": 1,
                  "offset": {"x": 0.0, "y": 0.0}})  # fmt: skip
        now[0] += 0.25
    gaps = [round(b - a, 2) for a, b in zip(attempts, attempts[1:], strict=False)]
    assert gaps[:7] == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]
    assert out.dropped == 800 and out.sent == 0 and out.state == "down"
    assert sum("display channel" in ln for ln in capsys.readouterr().out.splitlines()) == 1


def test_a_real_server_that_goes_away_and_comes_back(
    hs: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The library end to end: a websockets server on loopback shuts down (closing its connections,
    as a stopping backend does) and a new one starts on the same port. The Sender's thread keeps
    running, drops while down, and the new server's first message is a keyframe."""
    from websockets.sync.server import serve

    monkeypatch.setattr(hs, "SCENE_LOG", tmp_path / "scene.jsonl")
    got: queue.Queue[tuple[int, dict[str, Any]]] = queue.Queue()

    def start(port: int, gen: int) -> Any:
        def handler(ws: Any) -> None:
            for m in ws:
                got.put((gen, json.loads(m)))

        srv = serve(handler, "127.0.0.1", port)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv

    srv = start(0, 1)
    port = srv.socket.getsockname()[1]
    sc = Scene(hs, {"backoff": (0.05, 0.2)})
    out = sc.out
    out.TICK_S = 0.05
    monkeypatch.setattr(out, "_url", lambda: f"ws://127.0.0.1:{port}/internal/display")
    sender = threading.Thread(target=out.run, daemon=True)
    sender.start()
    try:
        gen, first = got.get(timeout=5)
        assert gen == 1 and first["type"] == "hud_scene"
        ws = out.ws  # the link carries WebSocket pings and a bounded send
        assert ws.ping_interval == hs.PING_S and ws.ping_timeout == hs.PING_S
        user_timeout = ws.socket.getsockopt(socket.IPPROTO_TCP, socket.TCP_USER_TIMEOUT)
        assert user_timeout == hs.DEAD_SEND_MS
        srv.shutdown()  # the backend goes away
        deadline = time.monotonic() + 5
        while out.state != "down" and time.monotonic() < deadline:
            sc.detect([unit("npc", 700, 400)])
            time.sleep(0.02)
        assert out.state == "down"
        for _ in range(5):
            out.put({"type": "hud_motion", "t_mono_ns": 1, "frame_id": 1,
                     "offset": {"x": 0.0, "y": 0.0}})  # fmt: skip
        time.sleep(0.1)
        assert out.dropped >= 1
        srv = start(port, 2)  # the new backend on the same address
        gen, msg = got.get(timeout=5)
        while gen == 1:  # anything the old server still read
            gen, msg = got.get(timeout=5)
        assert msg["type"] == "hud_scene"
        deadline = time.monotonic() + 2  # the server can read the keyframe before the count
        while out.connects < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert out.connects == 2 and out.state == "up" and sender.is_alive()
    finally:
        out.put(None)
        sender.join(timeout=5)
        srv.shutdown()
