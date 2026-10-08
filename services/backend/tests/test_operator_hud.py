"""scripts/operator_hud.py: the operator HUD's sender (Batt, 2026-10-08). Display only: every
message it sends passes the backend's own parser (parse_agent_to_backend), distances are in CELLS,
every field is bounded, and nothing it does can raise into the walk rule."""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from poring_env.protocol import OperatorHud, parse_agent_to_backend

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
REGION = (80, 77, 1280, 720)  # the game region on the desktop (x, y, w, h)
DESKTOP = (1440, 900)


@pytest.fixture(scope="module")
def hud() -> ModuleType:
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))  # route_preview (UI_WINDOWS), unit_gate, as in a rule
    spec = importlib.util.spec_from_file_location("operator_hud", SCRIPTS / "operator_hud.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["operator_hud"] = mod
    spec.loader.exec_module(mod)
    return mod


class Box:  # unit_detector.Box's shape
    def __init__(self, x0: float, y0: float, x1: float, y1: float, score: float, cls: str) -> None:
        self.x0, self.y0, self.x1, self.y1, self.score, self.cls = x0, y0, x1, y1, score, cls


class Ws:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[str] = []
        self.fail = fail

    def send(self, text: str) -> None:
        if self.fail:
            raise ConnectionError("socket closed")
        self.sent.append(text)


class Agent:
    def __init__(self, fail: bool = False) -> None:
        self.ws = Ws(fail)


class Clock:
    def __init__(self) -> None:
        self.t = 1_000_000_000

    def __call__(self) -> int:
        return self.t


def sender(hud: ModuleType, agent: Agent | None = None, **kw: Any) -> Any:
    return hud.HudSender(agent or Agent(), REGION, DESKTOP, label="walk@12", clock=Clock(), **kw)


def test_a_decision_becomes_a_valid_display_only_hud(hud: ModuleType) -> None:
    agent = Agent()
    s = sender(hud, agent)
    boxes = [Box(100, 200, 140, 260, 0.81, "monster"), Box(600, 300, 630, 380, 0.5, "npc")]
    s.note(hud.line_detected(2))
    s.note(hud.line_refused("TALK cell"))
    s.note(hud.line_walking((102, 110)))
    walk = hud.walk_vector((102, 110), REGION, DESKTOP, text=hud.line_walking((102, 110)),
                           start_px=(640, 362), end_px=(760, 300))  # fmt: skip
    assert s.send(boxes=boxes, cells=[(3, -4), None], lock_=hud.lock(0, None, 1800), walk=walk,
                  det_ms=250.0)  # fmt: skip
    assert len(agent.ws.sent) == 1
    msg = parse_agent_to_backend(agent.ws.sent[0])  # the backend's own parser accepts it
    assert isinstance(msg, OperatorHud)
    assert msg.label == "walk@12" and msg.ttl_ms == hud.DEFAULT_TTL_MS
    u0 = msg.units[0]
    assert (u0.cls, u0.conf, u0.dist_cells) == ("monster", 0.81, 4)  # Chebyshev: max(|3|, |-4|)
    assert msg.units[1].dist_cells is None  # no cell: "? cells", never a pixel distance
    assert u0.box.x == pytest.approx((80 + 100) / 1440) and u0.box.y == pytest.approx(277 / 900)
    assert u0.box.w == pytest.approx(40 / 1440) and u0.box.h == pytest.approx(60 / 900)
    assert (u0.foot.x, u0.foot.y) == (pytest.approx(200 / 1440), pytest.approx(337 / 900))
    assert msg.lock is not None and msg.lock.index == 0 and msg.lock.lock_remaining_ms == 1800
    assert msg.walk is not None and msg.walk.dest is not None
    assert (msg.walk.dest.x, msg.walk.dest.y, msg.walk.text) == (102, 110, "walking to (102,110)")
    assert msg.walk.end is not None and msg.walk.end.x == pytest.approx(840 / 1440)
    assert msg.log == ["detected 2 units", "refused: TALK cell", "walking to (102,110)"]
    assert msg.counters.units == 2 and msg.counters.det_fps == 4.0
    assert msg.zone is not None


def test_the_work_zone_is_the_game_area_minus_the_clients_ui_windows(hud: ModuleType) -> None:
    import route_preview

    z = hud.zone(REGION, DESKTOP)
    assert z["area"] == {"x": 80 / 1440, "y": 77 / 900, "w": 1280 / 1440, "h": 720 / 900}
    assert len(z["exclude"]) == len(route_preview.UI_WINDOWS)  # the same mask the clicks use
    x0, y0, x1, y1 = route_preview.UI_WINDOWS[0]
    assert z["exclude"][0]["x"] == pytest.approx((80 + x0) / 1440)
    assert z["exclude"][0]["w"] == pytest.approx((x1 - x0) / 1440)


def test_unit_cells_use_the_pick_else_the_gates_nearest_flat_cell(hud: ModuleType) -> None:
    class Cam:  # a flat camera: our cell at (640, 362), 30 px per cell
        def project(self, cells: Any, alt: Any = None) -> np.ndarray:
            return np.array([640.0, 362.0]) + np.asarray(cells, dtype=float) * 30.0

    feet: list[tuple[float, float]] = []

    def pick(camera: Any, gat: Any, belief: Any, px: np.ndarray) -> np.ndarray:
        feet.append((float(px[0, 0]), float(px[0, 1])))
        if px[0, 0] > 800:
            return np.array([[2 * 10**5, 0]])  # nothing picked under these feet
        if px[0, 0] < 0:
            raise ValueError("off the map")
        return np.array([[2, -5]])

    boxes = [Box(100, 100, 140, 160, 0.9, "monster"), Box(840, 362, 860, 422, 0.9, "player"),
             Box(-50, 0, -10, 40, 0.9, "monster")]  # fmt: skip
    cells = hud.unit_cells(boxes, Cam(), None, (100, 100), pick=pick)
    assert feet[0] == (120.0, 160.0)  # the box's bottom centre: its feet
    assert cells[0] == (2, -5)
    assert cells[1] == (7, 2)  # unit_gate._nearest_cell: ((850-640)/30, (422-362)/30)
    assert cells[2] is None  # an error is an unknown distance, never a stop
    assert [hud.chebyshev(c) for c in cells] == [5, 7, None]


def test_every_field_is_bounded_and_the_message_still_passes(hud: ModuleType) -> None:
    agent = Agent()
    s = sender(hud, agent)
    for i in range(30):
        s.note(f"line {i}\nwith a break\x1b[31m and a very long tail " + "x" * 200)
    boxes = [Box(i, i, i + 10, i + 20, 0.5, "monster" * 10) for i in range(100)]
    boxes.append(Box(math.nan, 0, math.inf, 5, 2.0, "player"))
    walk = hud.walk_vector((99999, -3), REGION, DESKTOP, text="t" * 500,
                           start_px=(math.nan, 0), end_px=(5000, -5000))  # fmt: skip
    assert s.send(boxes=boxes, cells=[(10**6, 0)] * 101, lock_=hud.lock(70, 5, 10**9), walk=walk,
                  det_fps=1e9)  # fmt: skip
    msg = parse_agent_to_backend(agent.ws.sent[0])
    assert isinstance(msg, OperatorHud)
    assert len(msg.units) == 64 and msg.counters.units == 101  # counted, the first 64 drawn
    assert len(msg.log) == 12 and msg.log[-1].startswith("line 29 with a break")
    assert all(len(line) <= 96 and "\n" not in line and "\x1b" not in line for line in msg.log)
    assert all(len(u.cls) <= 32 for u in msg.units) and msg.units[0].dist_cells == 4096
    assert msg.lock is not None and msg.lock.index is None and msg.lock.id == 5  # 70 is no unit
    assert msg.lock.lock_remaining_ms == 60_000
    assert msg.walk is not None and msg.walk.dest is not None
    assert (msg.walk.dest.x, msg.walk.dest.y) == (4096, 0) and len(msg.walk.text) == 96
    assert msg.counters.det_fps == 1000.0


def test_a_message_the_backend_would_refuse_is_never_sent(hud: ModuleType) -> None:
    """The positive case for the validation gate: the backend answers a bad message with an
    ErrorReply on the rule's socket, and ro_agent.Agent stops on one -- so it must never leave."""
    agent = Agent()
    s = sender(hud, agent)
    good = hud.message(t_ns=1, label="x")
    bad = {**good, "log": ["two\nlines"]}  # a raw message that skipped the clamping
    assert s.send_message(good) and len(agent.ws.sent) == 1
    assert not s.send_message(bad)
    assert len(agent.ws.sent) == 1 and s.refused == 1 and "invalid" in (s.last_error or "")
    assert not s.send_message({**good, "units": [{"cls": "x", "conf": math.nan}]})
    assert len(agent.ws.sent) == 1  # NaN never reaches the wire either


def test_a_failing_socket_never_raises_into_the_rule(hud: ModuleType) -> None:
    s = sender(hud, Agent(fail=True))
    assert s.send(boxes=[Box(0, 0, 1, 1, 0.5, "npc")]) is False
    assert "ConnectionError" in (s.last_error or "")
    assert s.clear() is False
    s.agent = None  # no socket at all
    assert s.send(force=True) is False


def test_the_rate_limit_keeps_the_log_for_the_next_message(hud: ModuleType) -> None:
    agent = Agent()
    s = sender(hud, agent)
    clock = s.clock
    assert s.send()
    s.note("refused: TALK cell")
    clock.t += 50_000_000  # 50 ms later: within the 100 ms limit
    assert not s.send() and s.skipped == 1
    clock.t += 60_000_000
    assert s.send()
    assert json.loads(agent.ws.sent[-1])["log"] == ["refused: TALK cell"]
    assert s.send(force=True)  # a forced decision always goes


def test_clear_sends_an_empty_hud_that_clears_at_once(hud: ModuleType) -> None:
    agent = Agent()
    assert sender(hud, agent).clear()
    msg = parse_agent_to_backend(agent.ws.sent[0])
    assert isinstance(msg, OperatorHud) and msg.ttl_ms == 0 and msg.units == []


def test_gate_lines_are_plain_words(hud: ModuleType) -> None:
    assert hud.line_gate(True, {"units": 3}) == "click clear of 3 unit envelope(s)"
    assert hud.line_gate(False, {"why": "no_detector"}) == "refused: no_detector"
    line = hud.line_gate(False, {"nearest": "monster", "min_px": 7.5})
    assert line == "refused: monster 7.5 px from the click"
    assert hud.line_detected(1) == "detected 1 unit"
    assert hud.fps_from_ms(0) is None and hud.fps_from_ms(200.0) == 5.0


# --- the rule side: enable + hooks (Batt 2026-10-08; display only, never blocking a decision) ---
@pytest.fixture
def enabled(hud: ModuleType, monkeypatch: pytest.MonkeyPatch) -> Any:
    import ro_agent

    monkeypatch.setattr(ro_agent, "game_region", lambda: REGION)
    monkeypatch.setattr(ro_agent, "desktop", lambda: DESKTOP)
    agent = Agent()
    token = hud.enable("walk@12 indoor/clean", agent=agent)
    assert token is not None and hud.enable("again", agent=Agent()) is None  # an outer owner wins
    yield agent
    hud.disable(token)
    assert hud.sender() is None


class Det:
    last_ms = 12.0

    def detect(self, frame: Any) -> list[Box]:
        return [Box(600, 300, 640, 340, 0.9, "monster")]


class World:
    def __init__(self) -> None:
        self.position = (100, 100)
        self.camera = None
        self.gat = None


def test_disabled_hooks_are_pass_through(hud: ModuleType) -> None:
    assert hud.sender() is None
    gate = hud.hook_unit_check(lambda pr, w, u, v: (False, {"why": "x"}), {"detector": None})
    step = hud.hook_click_step(lambda pr, w, end: {"clicked": True, "outcome": "confirmed"})
    assert gate(None, World(), 1.0, 2.0) == (False, {"why": "x"})
    assert step(None, World(), (101, 101)) == {"clicked": True, "outcome": "confirmed"}


def test_the_gate_only_records_and_the_step_publishes_after_it_returned(
    hud: ModuleType, enabled: Any
) -> None:
    det, units_ = Det(), {}
    units_["detector"] = det
    sent_during_gate: list[int] = []

    def rule_gate(pr: Any, w: Any, u: float, v: float) -> tuple[bool, dict[str, Any]]:
        boxes = units_["detector"].detect("frame")  # the gate's own detector call
        assert boxes[0].cls == "monster"  # the detector's output is unchanged
        return False, {"units": 1, "min_px": 26.0, "nearest": "monster"}

    gate = hud.hook_unit_check(rule_gate, units_)

    def rule_step(pr: Any, w: Any, end: tuple[int, int]) -> dict[str, Any]:
        res = gate(pr, w, 640.0, 360.0)
        sent_during_gate.append(len(enabled.ws.sent))  # nothing sent between gate and click
        return {"clicked": not res[0], "outcome": "covered_unit_envelope"}

    step = hud.hook_click_step(rule_step)
    before = len(enabled.ws.sent)
    out = step(None, World(), (103, 99))
    assert out == {"clicked": True, "outcome": "covered_unit_envelope"}  # the result untouched
    assert sent_during_gate == [before]
    msg = json.loads(enabled.ws.sent[-1])
    assert msg["type"] == "operator_hud" and msg["counters"]["units"] == 1
    assert any("monster 26.0 px" in line for line in msg["log"])  # the gate's verdict, in words
    assert msg["walk"]["dest"] == {"x": 103, "y": 99}


def test_a_failing_hud_socket_never_reaches_the_rule(
    hud: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ro_agent

    monkeypatch.setattr(ro_agent, "game_region", lambda: REGION)
    monkeypatch.setattr(ro_agent, "desktop", lambda: DESKTOP)
    token = hud.enable("walk@12", agent=Agent(fail=True))
    try:
        step = hud.hook_click_step(
            lambda pr, w, end: {"clicked": False, "outcome": "no_safe_point"}
        )
        route = hud.hook_route(lambda pr, w, goal: {"decline": "unit_stays"})
        assert step(None, World(), (1, 2)) == {"clicked": False, "outcome": "no_safe_point"}
        assert route(None, World(), (5, 5)) == {"decline": "unit_stays"}
    finally:
        hud.disable(token)
