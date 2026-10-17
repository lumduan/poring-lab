"""scripts/ro_agent.py's PACED sends (hunt-flow v34, 2026-10-17): the default drains 50 ms before
every send (unchanged); ``min_send_gap_s`` reads the queued messages without blocking and keeps
only the minimum gap since the previous send -- never two inputs closer than that, and a human
lease is still waited out (never fought)."""

import importlib.util
import json
import time
from collections import deque
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def ro() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ro_agent_pacing", SCRIPTS / "ro_agent.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeWs:
    """Acks every send at once; ``recv(timeout)`` returns a queued message, else waits out the
    timeout and raises TimeoutError (websockets' sync semantics, 0 = no wait)."""

    def __init__(self) -> None:
        self.q: deque[str] = deque()
        self.sent: list[float] = []

    def send(self, data: str) -> None:
        self.sent.append(time.monotonic())
        self.q.append(json.dumps({"type": "input_ack", "accepted": 1, "dropped": 0,
                                  "reasons": []}))  # fmt: skip

    def recv(self, timeout: float | None = None) -> str:
        if self.q:
            return self.q.popleft()
        if timeout and timeout > 0:
            time.sleep(timeout)
        raise TimeoutError


def agent(ro: ModuleType, gap: float | None) -> Any:
    a = ro.Agent.__new__(ro.Agent)
    a.ws = FakeWs()
    a.status = {"mode": "ASSIST"}
    a.min_send_gap_s = gap
    a._last_send = 0.0
    return a


def move(a: Any) -> None:
    a.send([{"type": "mouse_move", "t_mono_ns": 0, "frame_id": -1, "x": 0.5, "y": 0.5}])


def test_the_default_still_drains_50_ms_before_every_send(ro: ModuleType) -> None:
    a = agent(ro, None)
    t0 = time.monotonic()
    move(a)
    time.sleep(0.06)  # work: the default waits anyway
    t1 = time.monotonic()
    move(a)
    assert a.ws.sent[0] - t0 >= 0.049 and a.ws.sent[1] - t1 >= 0.049


def test_paced_sends_keep_the_gap_but_drop_the_dead_wait(ro: ModuleType) -> None:
    a = agent(ro, 0.05)
    move(a)
    move(a)  # back to back: still >= the gap apart
    assert a.ws.sent[1] - a.ws.sent[0] >= 0.049
    time.sleep(0.06)  # work longer than the gap: the next send goes at once
    t2 = time.monotonic()
    move(a)
    assert a.ws.sent[2] - t2 < 0.03


def test_paced_sends_still_wait_out_a_human_lease(ro: ModuleType) -> None:
    a = agent(ro, 0.05)
    until = ro.ns() + int(0.3e9)
    a.ws.q.append(json.dumps({"type": "status", "mode": "ASSIST", "lease_until_ns": until}))
    move(a)
    assert ro.ns() >= until and len(a.ws.sent) == 1  # sent only after the lease ended
    a.ws.q.append(json.dumps({"type": "status", "mode": "HUMAN"}))
    with pytest.raises(ro.Stop, match="left ASSIST"):
        move(a)
    assert len(a.ws.sent) == 1


def test_stop_on_takeover_keeps_the_pacing_and_still_stops_on_a_lease(ro: ModuleType) -> None:
    import sys

    sys.path.insert(0, str(SCRIPTS))
    import farm0

    a = agent(ro, 0.05)
    farm0.stop_on_takeover(a)
    time.sleep(0.06)
    t0 = time.monotonic()
    move(a)
    assert a.ws.sent[0] - t0 < 0.03  # paced: no dead 50 ms wait (the override had one)
    b = agent(ro, None)
    farm0.stop_on_takeover(b)
    t1 = time.monotonic()
    move(b)
    assert b.ws.sent[0] - t1 >= 0.049  # the default still drains 50 ms
    a.ws.q.append(json.dumps({"type": "status", "mode": "ASSIST",
                              "lease_until_ns": ro.ns() + int(5e9)}))  # fmt: skip
    with pytest.raises(farm0.FarmStop, match="took over"):
        move(a)
    assert len(a.ws.sent) == 1  # nothing sent under the lease
