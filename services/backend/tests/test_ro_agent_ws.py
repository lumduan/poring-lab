"""scripts/ro_agent.py's agent socket survives host work between sends (2026-10-04).

capture_backend's to-console runs docker-exec read-backs and a child command inside one agent
session, reading nothing meanwhile. With the websockets library's default receive flow control
(max_queue 16), the reader thread stops reading once 16 messages queue up -- ~16 s of the backend's
1 Hz status -- so keepalive pings go unanswered and the connection dies. A real server here pushes
the backlog at once and pings every 0.2 s; the client sleeps without reading."""

import importlib.util
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect
from websockets.sync.server import ServerConnection, serve

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
BACKLOG = 60  # status messages queued while the client does host work
KEEPALIVE: dict[str, Any] = {"ping_interval": 0.2, "ping_timeout": 0.3, "close_timeout": 0.5}


@pytest.fixture(scope="module")
def ro() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ro_agent", SCRIPTS / "ro_agent.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def handler(ws: ServerConnection) -> None:
    for i in range(BACKLOG):
        ws.send(f'{{"type": "status", "i": {i}}}')
    try:
        for msg in ws:
            ws.send(f"echo:{msg}")
    except ConnectionClosed:
        pass


def survives_a_stall(client_opts: dict[str, Any], stall_s: float = 1.5) -> bool:
    with serve(handler, "127.0.0.1", 0, **KEEPALIVE) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.socket.getsockname()[1]
        try:
            with connect(f"ws://127.0.0.1:{port}", **KEEPALIVE, **client_opts) as ws:
                time.sleep(stall_s)  # host work: nothing read
                ws.send("still-there")
                got = [ws.recv(timeout=2) for _ in range(BACKLOG + 1)]
                return got[-1] == "echo:still-there"
        except (ConnectionClosed, TimeoutError):
            return False
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_the_library_default_dies_during_a_stall(ro: ModuleType) -> None:
    """The control arm: the failure ro_agent hit, reproduced (so the next test means something)."""
    default = {k: v for k, v in ro.AGENT_WS.items() if k != "max_queue"}
    assert not survives_a_stall(default)


def test_the_agent_socket_survives_a_stall(ro: ModuleType) -> None:
    assert ro.AGENT_WS["max_queue"] is None
    assert survives_a_stall(ro.AGENT_WS)
