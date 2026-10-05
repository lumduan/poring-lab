"""scripts/ro_agent.py's chords are PACED (Batt, 2026-10-05): the client ignored Alt+E/Q/S and
Alt+F4 sent as one instantaneous batch. Each step is its own batch, CHORD_STEP_S apart, and a
refused step still releases whatever was pressed."""

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def ro() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ro_agent_chord", SCRIPTS / "ro_agent.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Recorder:
    def __init__(self, ro: ModuleType, refuse_at: int | None = None) -> None:
        self.ro, self.refuse_at = ro, refuse_at
        self.log: list[Any] = []

    def send(self, events: list[dict[str, Any]], *, sensitive: bool = False) -> None:
        sent = [x for x in self.log if x != "sleep"]
        if self.refuse_at is not None and len(sent) == self.refuse_at:
            self.log.append("refused")
            raise self.ro.Stop("mux refused")
        self.log.append([(e["code"], e["action"]) for e in events])


def run_chord(ro: ModuleType, monkeypatch: pytest.MonkeyPatch, rec: Recorder, *codes: str) -> None:
    agent = ro.Agent.__new__(ro.Agent)
    monkeypatch.setattr(agent, "send", rec.send)
    sleeps: list[float] = []
    monkeypatch.setattr(ro.time, "sleep", lambda s: (sleeps.append(s), rec.log.append("sleep")))
    try:
        agent.chord(*codes)
    finally:
        assert all(s >= ro.CHORD_STEP_S for s in sleeps)


def test_a_chord_is_one_event_per_batch_paced_and_nested(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    rec = Recorder(ro)
    run_chord(ro, monkeypatch, rec, "AltLeft", "KeyE")
    assert rec.log == [
        [("AltLeft", "down")], "sleep", [("KeyE", "down")], "sleep",
        [("KeyE", "up")], "sleep", [("AltLeft", "up")], "sleep",
    ]  # fmt: skip
    assert ro.CHORD_STEP_S >= 0.05


def test_a_refused_step_still_releases_what_was_pressed(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    rec = Recorder(ro, refuse_at=1)  # Alt goes down, then the key's press is refused
    with pytest.raises(ro.Stop, match="mux refused"):
        run_chord(ro, monkeypatch, rec, "AltLeft", "KeyQ")
    sends = [x for x in rec.log if x != "sleep"]
    assert sends == [[("AltLeft", "down")], "refused", [("AltLeft", "up")]]
