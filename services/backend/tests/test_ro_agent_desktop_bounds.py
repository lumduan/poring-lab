"""ro_agent's pointer input never leaves the desktop (2026-10-19, hunt-flow@43 run 4: a mouse_move
with y < 0 was dropped by the backend's validation, never acknowledged, and the run stopped on the
missing ack). Moves are CLAMPED (logged with their caller); presses outside are a clear Stop."""

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def ro() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ro_agent_bounds", SCRIPTS / "ro_agent.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def agent_of(ro: ModuleType, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, list[Any]]:
    sent: list[Any] = []
    agent = ro.Agent.__new__(ro.Agent)
    monkeypatch.setattr(agent, "send", lambda events, **_k: sent.extend(events))
    monkeypatch.setattr(ro, "desktop", lambda: (1440, 900))
    monkeypatch.setattr(ro.time, "sleep", lambda _s: None)
    monkeypatch.setattr(ro, "log", lambda _m: None)
    return agent, sent


def test_a_move_above_the_desktop_is_clamped_into_it(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent, sent = agent_of(ro, monkeypatch)
    agent.move(700, -40)  # the run-4 case: y < 0
    agent.move(1500, 950)
    agent.move(720, 450)
    xs = [(e["x"], e["y"]) for e in sent]
    assert all(0 <= x <= 1 and 0 <= y <= 1 for x, y in xs)
    assert xs[0] == (700 / 1440, 0.0) and xs[1] == (1439 / 1440, 899 / 900)
    assert xs[2] == (720 / 1440, 450 / 900)  # inside: unchanged


def test_a_press_outside_the_desktop_is_never_sent(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent, sent = agent_of(ro, monkeypatch)
    with pytest.raises(ro.Stop, match="click outside the desktop"):
        agent.click(700, -1)
    with pytest.raises(ro.Stop, match="drag end outside the desktop"):
        agent.drag(100, 100, 100, 901)
    assert sent == []  # nothing at all went out
    agent.click(700, 450)
    assert [e["type"] for e in sent] == ["mouse_move", "mouse_button", "mouse_button"]
