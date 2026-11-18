"""A Run pauses while the game is off the screen (Batt 2026-11-18: "if a user presses Alt+Tab,
only pause; when the game is back the bot must detect the screen and play on by itself"). The
gate is ro_agent's (every grab and every press passes it); a Run turns it on (PORING_PAUSE_AWAY)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture()
def ro(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("ro_agent_pause", SCRIPTS / "ro_agent.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sig = tmp_path / "signatures"
    sig.mkdir()
    monkeypatch.setattr(module, "signature_path", lambda state: sig / f"{state}.npy")
    monkeypatch.setattr(module, "desktop", lambda: (1280, 720))
    monkeypatch.setattr(module, "real_game_region", lambda: (0, 0, 1280, 720))
    monkeypatch.setattr(module, "AWAY_POLL_S", 0.001)
    monkeypatch.setattr(module, "AWAY_SETTLE_S", 0.02)
    monkeypatch.setenv(module.AWAY_ENV, "1")
    return module


class Looks:
    """A scripted run of looks: each away_now() takes the next verdict (the last one repeats)."""

    def __init__(self, verdicts: list[str | None]) -> None:
        self.verdicts, self.n = verdicts, 0

    def __call__(self, screen: Any) -> str | None:
        v = self.verdicts[min(self.n, len(self.verdicts) - 1)]
        self.n += 1
        return v


def test_the_verdict_fullscreen_is_the_taskbar_a_window_its_lit_title_bar(ro: ModuleType) -> None:
    assert ro.away_verdict(True, 49.9, None) is None  # the taskbar absent: the game in front
    assert "taskbar shows" in ro.away_verdict(True, 0.0, None)  # Alt+Tab: the desktop
    assert ro.away_verdict(True, None, None) is None  # no template: no proof, no pause
    assert ro.away_verdict(False, None, 1.0) is None  # the title bar lit
    assert "not the active window" in ro.away_verdict(False, None, 30.0)  # another window in front


def test_a_look_reads_the_taskbar_box_on_the_raw_path(ro: ModuleType) -> None:
    """away_now's own look never passes the gate (it IS the gate): the raw grab of the taskbar box
    against its template, the backend's bar (TASKBAR_ABSENT_MIN)."""
    path = ro.signature_path("taskbar")
    frame = np.zeros((720, 1280, 4), np.uint8)
    box = (1020, 672, 170, 48)
    np.save(path, ro.grey_thumb(frame[672:720, 1020:1190]))
    path.with_suffix(".json").write_text(json.dumps({"box": list(box), "session": [1280, 720]}))

    class Raw(ro.Screen):  # type: ignore[misc,name-defined]
        def __init__(self) -> None:
            self.frame = frame

        def _grab_raw(self, x: int, y: int, w: int, h: int) -> Any:
            return 7, np.ascontiguousarray(self.frame[y : y + h, x : x + w]), 42, "bus"

        def grab_meta(self, *a: Any) -> Any:
            raise AssertionError("the gate's own look went through the gate")

    s = Raw()
    assert "taskbar shows" in ro.away_now(s)  # the frame IS the taskbar: away
    frame[672:720, 1020:1190] = 200  # the game drawn over it: the taskbar gone
    assert ro.away_now(s) is None


def test_away_pauses_then_goes_on_by_itself_once_the_game_is_back(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    notes: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(ro, "AWAY_HOOK", lambda kind, info: notes.append((kind, info)))
    looks = Looks(["Alt+Tab", "Alt+Tab", None, "Alt+Tab", None])
    monkeypatch.setattr(ro, "away_now", looks)
    drawn = iter([False, True])  # the first return still black (a mode switch): not yet
    monkeypatch.setattr(ro, "client_drawn", lambda s: next(drawn, True))
    ro.away_gate(object())
    assert [k for k, _ in notes] == ["pause", "resume"]  # one of each, however many looks
    assert notes[0][1]["why"] == "Alt+Tab" and notes[1][1]["after_s"] >= 0
    assert looks.n >= 5  # it waited out the flicker back to away before going on
    assert ro.away_state()["paused"] is False


def test_on_the_screen_the_gate_costs_one_look_per_interval(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    looks = Looks([None])
    monkeypatch.setattr(ro, "away_now", looks)
    monkeypatch.setattr(ro, "AWAY_CHECK_S", 60.0)
    for _ in range(5):
        ro.away_gate(object())
    assert looks.n == 1  # the verdict "on the screen" is reused
    ro.away_gate(object(), fresh=True)  # a key press always looks again
    assert looks.n == 2


def test_the_gate_is_off_outside_a_run(ro: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ro.AWAY_ENV)
    monkeypatch.setattr(ro, "away_now", lambda s: pytest.fail("looked outside a Run"))
    ro.away_gate(object())  # the login, the desktop steps: never paused


def test_stop_while_paused_ends_the_wait(ro: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ro, "away_now", Looks(["Alt+Tab"]))
    monkeypatch.setattr(ro, "client_drawn", lambda s: True)
    calls = iter([None, None, "Stop was pressed while the run was paused"])
    monkeypatch.setattr(ro, "AWAY_STOP", lambda: next(calls))
    with pytest.raises(SystemExit, match="Stop was pressed"):
        ro.away_gate(object())


def test_every_grab_passes_the_gate(ro: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []
    monkeypatch.setattr(ro, "away_gate", lambda s, **k: order.append("gate"))

    class Raw(ro.Screen):  # type: ignore[misc,name-defined]
        def __init__(self) -> None:
            pass

        def _grab_raw(self, x: int, y: int, w: int, h: int) -> Any:
            order.append("grab")
            return 7, np.zeros((h, w, 4), np.uint8), 42, "bus"

    Raw().grab(0, 0, 4, 4)
    assert order == ["gate", "grab"]


def test_events_that_only_let_go_never_wait(ro: ModuleType) -> None:
    assert ro.is_release({"type": "release_all"})
    assert ro.is_release({"type": "key", "code": "F1", "action": "up"})
    assert ro.is_release({"type": "mouse_button", "button": "left", "action": "up"})
    assert not ro.is_release({"type": "key", "code": "F1", "action": "down"})
    assert not ro.is_release({"type": "mouse_move", "x": 0.5, "y": 0.5})


def test_only_an_all_key_batch_refused_for_the_foreground_is_sent_again(ro: ModuleType) -> None:
    keys = [{"type": "key", "code": "F1", "action": "down"}]
    fg = {"dropped": 1, "reasons": ["client_not_foreground"]}
    assert ro.refused_for_foreground(keys, fg)
    assert not ro.refused_for_foreground(keys, {"dropped": 1, "reasons": ["mode=HUMAN"]})
    mixed = [{"type": "mouse_move", "x": 0.1, "y": 0.1}, *keys]  # the move went through
    assert not ro.refused_for_foreground(mixed, fg)


class FakeWS:
    def __init__(self, acks: list[dict[str, Any]]) -> None:
        self.acks, self.sent = acks, []

    def send(self, text: str) -> None:
        self.sent.append(json.loads(text))

    def recv(self, timeout: float = 0) -> str:
        if self.sent and self.acks and len(self.sent) > self._acked():
            return json.dumps({"type": "input_ack", **self.acks.pop(0)})
        raise TimeoutError

    def _acked(self) -> int:
        return self.total - len(self.acks)

    def close(self) -> None:
        pass


def test_a_key_refused_because_the_game_left_mid_press_waits_and_goes_again(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The look said "on the screen", the user's Alt+Tab came between it and the key: the backend
    refused the key (client_not_foreground). The Agent pauses and sends the same key again, once
    the game is back -- the run does not end on it."""
    gates: list[bool] = []
    monkeypatch.setattr(ro, "away_gate", lambda s, *, fresh=False: gates.append(fresh))
    a = object.__new__(ro.Agent)
    ws = FakeWS(
        [{"dropped": 1, "reasons": ["client_not_foreground"]}, {"dropped": 0, "reasons": []}]
    )
    ws.total = 2
    a.ws, a.status, a.modes = ws, {"mode": "BOT"}, ("ASSIST", "BOT")
    a.min_send_gap_s, a._last_send, a._gate_screen = None, 0.0, object()
    a.send([ro.key("F1", "down")])
    assert len(ws.sent) == 2 and ws.sent[0]["events"] == ws.sent[1]["events"]
    assert gates == [True, True]  # the look before (a key: fresh) and the pause after the refusal
