"""ro_agent.open_chat's RECOVERY (2026-10-09; three held-out runs stopped on "the chat input did not
open"): after the two Enters it re-judges on fresh frames, sends NO further key, and a real failure
stops with the distances and a saved frame."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def load() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("ro_agent", SCRIPTS / "ro_agent.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ro_agent"] = mod
    spec.loader.exec_module(mod)
    return mod


class Gate:
    """A stand-in for scripts/ui_gate.py (its own tests: test_ui_gate.py): records each check."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.stop: Exception | None = None

    def ensure_clear(self, agent: Any, screen: Any, *, why: str) -> dict[str, Any]:
        self.calls.append(why)
        if self.stop is not None:
            raise self.stop
        return {"clear": True}


@pytest.fixture
def gate(monkeypatch: pytest.MonkeyPatch) -> Gate:
    g = Gate()
    monkeypatch.setitem(sys.modules, "ui_gate", g)
    return g


@pytest.fixture
def r(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, gate: Gate) -> Any:
    mod = load()
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(mod, "is_state", lambda screen, st, after_ns=None: False)  # never at first
    monkeypatch.setattr(mod, "layout", lambda name: (10, 10))
    monkeypatch.setattr(mod, "to_png", lambda img, path: tmp_path / "fail.png")
    return mod


class Agent:
    def __init__(self) -> None:
        self.keys_sent: list[str] = []
        self.clicks: list[tuple[int, int]] = []

    def keys(self, *k: str) -> None:
        self.keys_sent += list(k)

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))


class Screen:
    def full(self) -> Any:
        return np.zeros((4, 4, 4), np.uint8)


def test_a_recheck_recognises_the_input_without_another_key(r: Any, monkeypatch: pytest.MonkeyPatch
                                                            ) -> None:  # fmt: skip
    seq = iter([9.0, 8.0, 1.3])
    monkeypatch.setattr(r, "distance", lambda screen, st, after_ns=None: next(seq))
    a = Agent()
    r.open_chat(a, Screen())
    assert a.keys_sent == ["Enter", "Enter"] and a.clicks == [(10, 10)]


def test_a_real_failure_stops_with_its_distances_and_frame(r: Any, monkeypatch: pytest.MonkeyPatch
                                                           ) -> None:  # fmt: skip
    clock = iter(range(0, 1000))
    monkeypatch.setattr(r.time, "monotonic", lambda: float(next(clock)) * 0.3)
    monkeypatch.setattr(r, "distance", lambda screen, st, after_ns=None: 9.5)
    a = Agent()
    with pytest.raises(r.Stop, match=r"distances \[9\.5.*fail\.png"):
        r.open_chat(a, Screen())
    assert a.keys_sent == ["Enter", "Enter"] and a.clicks == []


def test_the_ui_gate_runs_before_any_key_and_its_stop_sends_none(r: Any, gate: Gate) -> None:
    """Batt 2026-10-09 (walk@17 item 6): never press Enter into an unknown state."""
    a = Agent()
    gate.stop = r.Stop("ui gate (open_chat): npc_dialog_open:next")
    with pytest.raises(r.Stop, match="npc_dialog_open"):
        r.open_chat(a, Screen())
    assert gate.calls == ["open_chat"] and a.keys_sent == [] and a.clicks == []
