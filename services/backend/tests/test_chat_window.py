"""The chat window's standard (Batt 2026-11-05): one geometry for every reader, the pixel reader on
synthetic windows drawn like the client's (measured 2026-11-05 11:4x), the step logic, and
``ensure`` driving a simulated client to the standard with the client's own controls only."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import chat_window as cw  # noqa: E402

SCENE = (90, 110, 60)


def test_the_legacy_geometry_gives_back_every_frozen_layout_number() -> None:
    g = cw.LEGACY
    assert g.chat_open_box == (0, 604, 570, 12)  # data/ro_agent/signatures/chat_open.json
    assert g.input_px == (300, 613)  # ro_agent LAYOUTS (1280, 720) "chat_input"
    assert g.tab_row == 529  # client_layout's TAB_ROW
    assert g.text_top == 545  # battle_log's TAB_EDGE_Y
    assert g.rect == (0, 532, 600, 626)  # client_layout.RECTS' chat entry
    assert g.message_area == (0, 545, 640, 600)  # where_fix's CHAT_AREA
    assert g.cue_area == (0, 545, 570, 593)  # chat_cue's CHAT_AREA
    assert g.battle_crop == (0, 528, 600, 600)  # battle_log's CROP
    assert g.line_y0(3) == 551  # battle_log's LINE_Y0


def test_the_standard_is_docked_bottom_left_with_six_lines() -> None:
    g = cw.STANDARD
    assert (g.left, g.bottom, g.lines) == (0, 719, 6)
    assert g.text_top == 598 and g.tab_row == 582  # measured on Batt's setup, 11:32
    assert g.chat_open_box == (0, 699, 570, 12)  # the signature matched there at 1.26 (11:4x)
    assert g.input_px == (300, 708)
    assert g.padlock_px == (585, 591)
    assert g.rect == (0, 585, 600, 720)
    assert g.line_y0(3) == 646  # the NEWEST three of the six lines
    assert cw.TABS == ("battle",)


def test_the_process_geometry_is_the_standard_unless_a_replay_selects_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(cw.ENV, "standard")  # recorded: restored (unset) after the test
    monkeypatch.delenv(cw.ENV)
    assert cw.active() == cw.STANDARD
    cw.select("legacy")
    assert cw.active() == cw.LEGACY
    with pytest.raises(ValueError):
        cw.select("nope")


# --- synthetic windows, drawn as the client draws them ----------------------------------------


def draw(g: cw.Geometry | None, *, input_open: bool = True, bar_only: bool = False,
         cover_down_arrow: bool = False, cover_up_arrow: bool = False) -> np.ndarray:  # fmt: skip
    img = np.zeros((720, 1280, 3), np.uint8)
    img[...] = SCENE
    if g is None:
        return img
    x0, b = g.left, g.bottom
    if bar_only or input_open:
        img[b - 22 : b - 20, x0 : x0 + 597] = 255
        img[b - 19 : b - 2, x0 : x0 + 597] = 247  # the white input bar
        img[b - 2 : b, x0 : x0 + 597] = 255
    if bar_only:
        return img
    top = g.text_top
    img[top + 1 : b - 23, x0 : x0 + 597] = 55  # the darkened message area
    img[top, x0 + 80 : x0 + 593] = 255  # the top border, not under the selected tab
    img[top + 1 : b - 24, x0 + 585 : x0 + 593] = 0  # the scrollbar's black track
    for dy, a, z in cw.UP_ARROW:
        img[top + dy, x0 + a : x0 + z + 1] = 230
    d = b - cw.DOWN_TO_BOTTOM
    for dy, a, z in cw.DOWN_ARROW:
        img[d + dy, x0 + a : x0 + z + 1] = 220
    if cover_down_arrow:  # the "Change size(F10)" tooltip over the down arrow
        img[d - 2 : d + 18, x0 + 587 : x0 + 690] = 200
    if cover_up_arrow:  # the pointer at the padlock: its arrow reaches down over the up arrow
        img[top - 7 : top + 11, x0 + 585 : x0 + 598] = 230
    return img


@pytest.mark.parametrize("lines", cw.SIZES)
@pytest.mark.parametrize("input_open", [True, False])
def test_find_reads_every_size_open_or_closed(lines: int, input_open: bool) -> None:
    g = cw.Geometry(lines, 719)
    st = cw.find(draw(g, input_open=input_open))
    assert st == {"left": 0, "text_top": g.text_top, "bottom": 719, "lines": lines,
                  "input": "open" if input_open else "closed"}  # fmt: skip


def test_find_reads_a_moved_window_and_the_states_without_a_message_area() -> None:
    moved = cw.Geometry(6, 659, 40)
    st = cw.find(draw(moved))
    assert st is not None and (st["left"], st["bottom"], st["lines"]) == (40, 659, 6)
    assert cw.find(draw(None)) is None  # hidden (F10's 6th step)
    bar = cw.find(draw(cw.STANDARD, bar_only=True))
    assert bar is not None and bar["lines"] == 0 and bar["bottom"] == 719
    # a message area whose arrow is covered is "obscured", never the bar alone (no F10 on it)
    for cover in ({"cover_down_arrow": True}, {"cover_up_arrow": True}):
        ob = cw.find(draw(cw.STANDARD, **cover))
        assert ob is not None and ob.get("obscured") and ob["lines"] is None, cover
        assert cw.next_step(ob) == "unknown"  # read again after parking, never F10


def test_white_scene_rows_without_the_scrollbar_are_no_window() -> None:
    img = draw(None)
    img[300:303, 0:1280] = 255  # snow, a white wall: a long white row, but no arrows
    assert cw.find(img) is None


def test_padlock_decisions_need_a_match_and_a_margin() -> None:
    assert cw.padlock_state({"open": 0.0, "locked": 54.1}) == "open"
    assert cw.padlock_state({"open": 54.4, "locked": 4.2}) == "locked"
    assert cw.padlock_state({"open": 9.1, "locked": 54.3}) == "open"
    assert cw.padlock_state({"open": 30.0, "locked": 60.0}) is None  # the cursor over it
    assert cw.padlock_state({"open": 12.0, "locked": 20.0}) is None  # no margin


def _st(**over: Any) -> dict[str, Any]:
    base = {"left": 0, "text_top": 598, "bottom": 719, "lines": 6, "input": "open",
            "padlock": "locked"}  # fmt: skip
    return {**base, **over}


def test_next_step_places_then_sizes_then_locks_and_never_acts_blind() -> None:
    assert cw.next_step(_st()) is None and cw.is_standard(_st())
    assert cw.next_step(None) == "f10"  # hidden: F10 shows it again
    assert cw.next_step({"lines": 0, "bottom": 719}) == "f10"  # the bar alone
    assert cw.next_step({"lines": None, "obscured": True}) == "unknown"
    moved = _st(left=40, bottom=659)
    assert cw.next_step(moved) == "unlock"
    assert cw.next_step({**moved, "padlock": "open", "input": "closed"}) == "open_input"
    assert cw.next_step({**moved, "padlock": "open"}) == "drag"
    assert cw.next_step({**moved, "padlock": None}) == "unknown"
    assert cw.next_step(_st(lines=3, text_top=640)) == "f10"
    assert cw.next_step(_st(lines=15, text_top=472, padlock="open")) == "f10"
    assert cw.next_step(_st(padlock="open")) == "lock"
    assert cw.next_step(_st(padlock=None)) == "unknown"
    assert cw.next_step(_st(padlock="open"), lock=False) is None


# --- ensure on a simulated client ----------------------------------------------------------------


class Client:
    """The client's chat window as seen live: F10 cycles 3-6-9-12-15-hidden-bar, the padlock
    toggles on a click at its body, a drag on the white bar moves the window only while the
    padlock is open, Enter toggles the input. Anything else pressed is a WORLD click (recorded)."""

    CYCLE = (3, 6, 9, 12, 15, "hidden", "bar")

    def __init__(self, size: Any = 6, left: int = 0, bottom: int = 719, locked: bool = True,
                 input_open: bool = True, effective: bool = True) -> None:  # fmt: skip
        self.size, self.left, self.bottom = size, left, bottom
        self.locked, self.input_open, self.effective = locked, input_open, effective
        self.world: list[tuple[int, int]] = []
        self.log: list[str] = []

    def state(self) -> dict[str, Any] | None:
        if self.size == "hidden" or (self.size == "bar" and not self.input_open):
            return None
        if self.size == "bar":
            return {"left": self.left, "text_top": None, "bottom": self.bottom, "lines": 0,
                    "input": "open"}  # fmt: skip
        g = cw.Geometry(self.size, self.bottom, self.left)
        return {"left": self.left, "text_top": g.text_top, "bottom": self.bottom,
                "lines": self.size, "input": "open" if self.input_open else "closed",
                "padlock": "locked" if self.locked else "open"}  # fmt: skip

    def _geom(self) -> cw.Geometry | None:
        return (
            cw.Geometry(self.size, self.bottom, self.left) if isinstance(self.size, int) else None
        )

    def f10(self) -> None:
        self.log.append("F10")
        if self.effective:
            self.size = self.CYCLE[(self.CYCLE.index(self.size) + 1) % len(self.CYCLE)]

    def enter(self) -> None:
        self.log.append("Enter")
        self.input_open = not self.input_open

    def click(self, u: int, v: int) -> None:
        g = self._geom()
        if g is not None and (u, v) == g.padlock_px:
            self.log.append("padlock")
            if self.effective:
                self.locked = not self.locked
        else:
            self.world.append((u, v))

    def drag(self, u: int, v: int, u2: int, v2: int) -> None:
        g = self._geom()
        on_bar = self.input_open and self.size != "hidden" and \
            (g is None or (u, v) == g.input_px)  # fmt: skip
        if not on_bar:
            self.world.append((u, v))
            return
        self.log.append("drag")
        if not self.locked and self.effective:
            self.left, self.bottom = self.left + u2 - u, self.bottom + v2 - v


class Agent:
    def __init__(self, client: Client) -> None:
        self.c = client
        self.moves = 0

    def move(self, x: int, y: int) -> None:
        self.moves += 1

    def click(self, x: int, y: int) -> None:
        self.c.click(x - 80, y - 77)

    def drag(self, x: int, y: int, x2: int, y2: int, steps: int = 10) -> None:
        self.c.drag(x - 80, y - 77, x2 - 80, y2 - 77)

    def keys(self, *codes: str) -> None:
        for code in codes:
            {"F10": self.c.f10, "Enter": self.c.enter}[code]()


@pytest.fixture
def sim(monkeypatch: pytest.MonkeyPatch) -> Any:
    import ro_agent as r
    import ui_gate

    def make(client: Client) -> Agent:
        monkeypatch.setattr(cw, "_grab_rgb", lambda screen: client)
        monkeypatch.setattr(cw, "read", lambda img, tm: img.state())
        monkeypatch.setattr(cw, "load_templates", lambda path=cw.TEMPLATES: {"stub": True})
        monkeypatch.setattr(cw, "_backend", lambda: "rdp")
        monkeypatch.setattr(cw, "_shot", lambda screen, tag: f"<{tag}>")
        monkeypatch.setattr(cw.time, "sleep", lambda s: None)
        monkeypatch.setattr(r, "game_region", lambda: (80, 77, 1280, 720))
        monkeypatch.setattr(r, "activate_client", lambda agent, screen: None)
        monkeypatch.setattr(r, "log", lambda msg: None)
        gate: list[str] = []

        def clear(agent: Any, screen: Any, why: str) -> dict[str, Any]:
            gate.append(why)
            return {"clear": True}

        monkeypatch.setattr(ui_gate, "ensure_clear", clear)
        client.gate = gate  # type: ignore[attr-defined]
        return Agent(client)

    monkeypatch.setenv(cw.ENV, "standard")
    return make


def test_a_standard_window_costs_one_read_and_no_input(sim: Any) -> None:
    c = Client()
    agent = sim(c)
    out = cw.ensure(agent, None, why="t")
    assert out["standard"] and out["steps"] == [] and agent.moves == 0 and c.log == []


def test_yesterdays_window_is_docked_sized_and_locked(sim: Any) -> None:
    # 11-04: moved up, taller, padlock closed, input closed
    c = Client(size=9, left=0, bottom=640, locked=True, input_open=False)
    agent = sim(c)
    out = cw.ensure(agent, None, why="t")
    assert out["standard"] and c.state() == {**_st(), "input": "open"}
    assert out["steps"] == ["unlock", "open_input", "drag", "f10", "f10", "f10", "f10", "f10",
                            "f10", "lock"]  # fmt: skip
    assert c.world == []  # no press ever reached the world
    assert c.gate == ["chat_window:t"]  # Enter only behind the UI gate


def test_a_hidden_window_is_shown_by_f10_through_the_bar_alone(sim: Any) -> None:
    c = Client(size="hidden", input_open=True)
    out = cw.ensure(sim(c), None, why="t")
    assert out["steps"] == ["f10", "f10", "f10"] and c.size == 6 and c.world == []


def test_a_step_without_effect_stops_with_a_frame(sim: Any) -> None:
    c = Client(left=40, bottom=659, locked=True, effective=False)
    with pytest.raises(cw.ChatWindowError, match="no-effect"):
        cw.ensure(sim(c), None, why="t")
    assert c.log == ["padlock"]  # tried once, saw no change, stopped


def test_f10_without_effect_stops_after_one_cycle(sim: Any) -> None:
    c = Client(size=3, effective=False)
    with pytest.raises(cw.ChatWindowError, match="F10"):
        cw.ensure(sim(c), None, why="t")
    assert c.log.count("F10") == len(cw.SIZES) + 3


def test_an_unproven_display_path_gets_no_fixing_input(sim: Any, monkeypatch: Any) -> None:
    c = Client(size=3)
    agent = sim(c)
    monkeypatch.setattr(cw, "_backend", lambda: "console")
    with pytest.raises(cw.ChatWindowError, match="rdp only"):
        cw.ensure(agent, None, why="t")
    assert c.log == [] and agent.moves == 0
    c2 = Client()  # but a standard window passes on any path (one read, no input)
    assert cw.ensure(sim(c2), None, why="t")["standard"]


def test_ro_agent_types_into_the_standard_place() -> None:
    import ro_agent as r

    src = (ROOT / "scripts" / "ro_agent.py").read_text()
    assert 'ensure_chat_window(agent, screen, "open_chat")' in src  # before every typed line
    assert 'ensure_chat_window(agent, screen, f"enter_game:{which}")' in src  # every entry
    assert r.LAYOUTS[(1280, 720)].get("chat_input") is None  # derived, never a stale constant
