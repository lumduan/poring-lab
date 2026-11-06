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
    assert cw.TABS == ("battle", "regular")  # 13:2x: Battle Log | NewTab_2 (the replies)
    # renamed "Chat" at 20:03 (Batt: a name that says what it is for)
    assert cw.TAB_NAMES == {"battle": "Battle Log", "regular": "Chat"}


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


def test_recorded_sessions_keep_the_chat_window_of_their_date() -> None:
    """Offline readers of RECORDED frames (battle_log replay, qa_export / map_labels / item_labels'
    layout checks) take the geometry by the session's date, never this process's."""
    assert cw.for_sid("20261019T135848-human-ui-setup") == cw.LEGACY
    assert cw.for_sid("20261105T091500-x") == cw.LEGACY  # before the cutover (12:xx)
    assert cw.for_sid("20261105T130000-demo") == cw.STANDARD
    assert cw.for_sid("20261019T135848-x", "standard") == cw.STANDARD  # an explicit override
    import client_layout as cl

    img = np.full((720, 1280, 3), 120, np.uint8)
    img[cw.LEGACY.tab_row, 12:72] = 254  # Battle Log's border on the frozen layout's tab row
    tm = {k: np.zeros_like(cl._grey(img, cl.BOX[b])) for k, b in (
        ("arrow_collapsed", "arrow"), ("arrow_expanded", "arrow"), ("row1", "row1"),
        ("row2", "row2"), ("row4", "row4"))}  # fmt: skip
    assert cl.read(img, tm, chat=cw.LEGACY)["tab"] == "battle"
    assert cl.read(img, tm, chat=cw.STANDARD)["tab"] is None  # read at the wrong row: unsure


def test_tabs_verdict_needs_both_tabs_in_order() -> None:
    v = cw.tabs_verdict
    assert v({"slots": ["battle", "regular"]}) == "ok"
    assert v({"slots": ["battle", "empty"]}) == "wrong"  # 11-04: the second tab deleted
    assert v({"slots": ["regular", "battle"]}) == "wrong"  # swapped
    assert v({"slots": ["battle", None]}) == "unread"
    assert v({"slots": [None, None]}) == "unread" and v(None) == "unread"


def test_read_tabs_on_synthetic_labels() -> None:
    rng = np.random.default_rng(5)
    tt = {f"{n}_{s}": rng.random((13, 60 if n == "battle" else 65)) > 0.7
          for n in cw.TABS for s in ("sel", "unsel")}  # fmt: skip
    g = cw.STANDARD
    img = np.full((720, 1280, 3), 60, np.uint8)
    row = g.tab_row
    r0 = cw.TAB_LABEL_ROWS[0]
    for name, (x0, _) in zip(cw.TABS, cw.TAB_SLOT_X, strict=True):
        m = tt[f"{name}_unsel"]
        img[row + r0 : row + r0 + m.shape[0], x0 : x0 + m.shape[1]][m] = 255
    img[row, 80:134] = 255  # the second tab selected
    st = {"left": 0, "text_top": g.text_top}
    got = cw.read_tabs(img, st, tt)
    assert got["slots"] == ["battle", "regular"] and got["selected"] == "regular"
    img2 = img.copy()
    img2[row + r0 : row + r0 + 13, 75:140] = 60  # the second tab gone
    assert cw.read_tabs(img2, st, tt)["slots"] == ["battle", "empty"]


# --- synthetic windows, drawn as the client draws them ----------------------------------------


def draw(g: cw.Geometry | None, *, input_open: bool = True, bar_only: bool = False,
         scrollbar: bool = True, cover_border: bool = False) -> np.ndarray:  # fmt: skip
    """A window as the client draws it (measured 2026-11-05): the message area's white top border
    ending at left + 592, the grey right border at left + 596, the separator 23 rows above the
    bottom, the white input bar while the input is open; the scrollbar only once the log
    overflows (``scrollbar``)."""
    img = np.zeros((720, 1280, 3), np.uint8)
    img[...] = SCENE
    if g is None:
        return img
    x0, b = g.left, g.bottom
    if bar_only:
        img[b - 22 : b - 20, x0 : x0 + 598] = 255
        img[b - 19 : b - 2, x0 : x0 + 598] = 247
        img[b - 2 : b, x0 : x0 + 598] = 255
        img[b, x0 : x0 + 598] = 196
        return img
    top = g.text_top
    img[top + 1 : b + 1, x0 : x0 + 596] = 55  # the darkened message area
    img[top, x0 + 80 : x0 + 593] = 255  # the top border, not under the selected tab
    img[top + 1 : b + 1, x0 + 596] = 140  # the right border, to the bottom (input closed)
    img[b - 23, x0 : x0 + 597] = 139  # the separator
    if input_open:
        img[b - 23, x0 : x0 + 598] = 196
        img[b - 22 : b - 20, x0 : x0 + 598] = 255
        img[b - 19 : b - 2, x0 : x0 + 598] = 247  # the white input bar
        img[b - 2 : b, x0 : x0 + 598] = 255
        img[b, x0 : x0 + 598] = 196
    if scrollbar:
        img[top + 1 : b - 24, x0 + 585 : x0 + 593] = 0
        img[top + 5 : top + 10, x0 + 587 : x0 + 591] = 230
        img[b - 34 : b - 29, x0 + 587 : x0 + 591] = 220
    if cover_border:  # the pointer / the "Change size(F10)" tooltip over the right border
        img[b - 40 : b - 26, x0 + 587 : x0 + 690] = 200
    return img


@pytest.mark.parametrize("lines", cw.SIZES)
@pytest.mark.parametrize("input_open", [True, False])
@pytest.mark.parametrize("scrollbar", [True, False])
def test_find_reads_every_size_open_or_closed_with_or_without_a_scrollbar(
    lines: int, input_open: bool, scrollbar: bool
) -> None:
    g = cw.Geometry(lines, 719)
    st = cw.find(draw(g, input_open=input_open, scrollbar=scrollbar))
    assert st == {"left": 0, "text_top": g.text_top, "bottom": 719, "lines": lines,
                  "input": "open" if input_open else "closed"}  # fmt: skip


def test_find_reads_a_moved_window_and_the_states_without_a_message_area() -> None:
    moved = cw.Geometry(6, 659, 40)
    st = cw.find(draw(moved))
    assert st is not None and (st["left"], st["bottom"], st["lines"]) == (40, 659, 6)
    assert cw.find(draw(None)) is None  # hidden (F10's 6th step)
    bar = cw.find(draw(cw.STANDARD, bar_only=True))
    assert bar is not None and bar["lines"] == 0 and bar["bottom"] == 719
    # a window whose right border something covers is "obscured", never the bar alone (no F10)
    for inp in (True, False):
        ob = cw.find(draw(cw.STANDARD, input_open=inp, cover_border=True))
        assert ob is not None and ob.get("obscured") and ob["lines"] is None, inp
        assert cw.next_step(ob) in ("unknown", "open_input")  # never "f10"


def test_a_moved_closed_window_over_a_grey_scene_opens_the_input_first() -> None:
    """With the input closed the window's bottom is where its right border ends; a grey scene
    below it (in the border's luma band) hides that: "seen in part" -> open the input (behind the
    UI gate), whose bar gives the bottom. Never a size or a drag on a guess."""
    img = draw(cw.Geometry(12, 639, 40), input_open=False)
    img[640:, 40 + 596] = 140  # the scene below continues the border's grey
    st = cw.find(img)
    assert st is not None and st.get("obscured") and st["text_top"] == cw.Geometry(12, 639).text_top
    assert cw.next_step(st) == "open_input"


def test_a_bright_scene_continuing_the_top_border_does_not_move_the_window() -> None:
    """2026-11-05 21:21, xmas_dun02's pink puzzle floor: the scene right of the window continued
    the top border's white run (747 px), so its end no longer gave the window's left."""
    g = cw.STANDARD
    for input_open in (True, False):
        img = draw(g, input_open=input_open)
        img[g.text_top, 593:900] = 240  # the floor beyond the border, as bright (x 596: 230 live)
        assert cw.find(img) == {
            "left": 0,
            "text_top": g.text_top,
            "bottom": g.bottom,
            "lines": 6,
            "input": "open" if input_open else "closed",
        }


def test_white_scene_rows_without_the_window_frame_are_no_window() -> None:
    img = draw(None)
    img[300:303, 0:1280] = 255  # snow, a white wall: a long white row, but no right border
    assert cw.find(img) is None


def test_padlock_decisions_need_a_match_and_a_margin() -> None:
    assert cw.padlock_state({"open": 0.0, "locked": 54.1}) == "open"
    assert cw.padlock_state({"open": 54.4, "locked": 4.2}) == "locked"
    assert cw.padlock_state({"open": 9.1, "locked": 54.3}) == "open"
    assert cw.padlock_state({"open": 30.0, "locked": 60.0}) is None  # the cursor over it
    assert cw.padlock_state({"open": 12.0, "locked": 20.0}) is None  # no margin


def test_the_colour_shape_decides_only_with_greys_ranking() -> None:
    """2026-11-05 xmas_dun02: closed 5.8 / open 20.1 over the north edge's pink wall (20:24) and
    5.8 / 12.0 over the pink puzzle floor (21:21) stopped the check; the icon's blue / white
    shape (IoU 0.51-0.53 vs 0.31) decides them, when grey ranks the same template first."""
    pink = {"open": 20.1, "locked": 5.8, "open_shape": 0.315, "locked_shape": 0.507}
    assert cw.padlock_state(pink) == "locked"
    puzzle = {"open": 12.0, "locked": 5.8, "open_shape": 0.312, "locked_shape": 0.532}
    assert cw.padlock_state(puzzle) == "locked"
    assert cw.padlock_state({**pink, "locked_shape": 0.38}) is None  # the shape not clear (0.065)
    assert cw.padlock_state({**puzzle, "open": 5.0}) is None  # grey ranks the other first
    assert cw.padlock_state({**pink, "open_shape": 0.6, "locked_shape": 0.3}) is None  # disagrees
    assert cw.padlock_state({**pink, "locked": 21.0, "open": 25.0}) is None  # nothing matches
    flip = {"open": 6.0, "locked": 12.5, "open_shape": 0.58, "locked_shape": 0.30}
    assert cw.padlock_state(flip) == "open"
    assert cw.padlock_state({"open": 20.1, "locked": 5.8}) is None  # no shape: grey alone


def test_the_xw3_stand_reads_locked_and_open_frames_stay_open() -> None:
    """2026-11-06 16:00:15 (xw3, stand (37,159)): closed 5.6 / open 19.7, shapes 0.366 / 0.229 --
    shape margin 0.137 under the old 0.15 -- stopped the watch, the same on three re-reads; the
    margin is 0.10 since. The archived OPEN frames of 11-05 (their real readings, scratch-archive
    2026-11-05 chat-1105 / tabs-1105) keep reading open: grey decides them by >= 39.9. A shape
    margin under 0.10 still decides nothing."""
    assert cw.PADLOCK_SHAPE_MARGIN == 0.10
    xw3 = {"open": 19.7, "open_shape": 0.229, "locked": 5.6, "locked_shape": 0.366}
    assert cw.padlock_state(xw3) == "locked"
    opened = [
        {"open": 4.4, "open_shape": 0.602, "locked": 50.4, "locked_shape": 0.302},  # 3 lines
        {"open": 0.0, "open_shape": 0.578, "locked": 47.3, "locked_shape": 0.295},  # 6 lines
        {"open": 3.3, "open_shape": 0.566, "locked": 55.0, "locked_shape": 0.284},  # 12 lines
        {"open": 3.8, "open_shape": 0.59, "locked": 44.2, "locked_shape": 0.292},  # the "+" probe
    ]
    for d in opened:
        assert cw.padlock_state(d) == "open"
    assert cw.padlock_state({**xw3, "locked_shape": 0.32}) is None  # margin 0.091


def test_the_padlock_read_ignores_the_scene_behind_the_icon_row() -> None:
    """2026-11-05 15:25: over xmas_dun02's black void the old union-mask read stopped the pilot;
    each template is now compared on its OWN icon pixels only, so the scene does not matter."""
    x0, dy0, x1, dy1 = cw.PADLOCK_BOX
    h, w = dy1 - dy0, x1 - x0
    locked = np.full((h, w), 130.0, np.float32)  # grass behind
    locked[3:10, 4:12] = 240.0  # the closed padlock's icon
    opened = np.full((h, w), 130.0, np.float32)
    opened[5:10, 2:9] = 240.0  # the open one: its body lower-left ...
    opened[1:4, 10:16] = 240.0  # ... its shackle up-right
    tm = {"open": opened, "locked": locked, "mask": np.ones((h, w), bool)}
    st = {"left": 0, "text_top": 598}
    for bg in (130, 10):  # grass, then the void
        img = np.full((720, 1280, 3), bg, np.uint8)
        img[598 + dy0 : 598 + dy1, x0:x1][3:10, 4:12] = 240
        d = cw.padlock_distances(img, st, tm)
        assert cw.padlock_state(d) == "locked", (bg, d)


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
                 input_open: bool = True, effective: bool = True,
                 tabs: tuple[Any, ...] = ("battle", "regular")) -> None:  # fmt: skip
        self.size, self.left, self.bottom = size, left, bottom
        self.locked, self.input_open, self.effective = locked, input_open, effective
        self.tabs = list(tabs)
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
                "padlock": "locked" if self.locked else "open",
                "tabs": {"slots": list(self.tabs), "selected": "regular"}}  # fmt: skip

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
        monkeypatch.setattr(cw, "read", lambda img, tm, tt=None: img.state())
        monkeypatch.setattr(cw, "load_templates", lambda path=cw.TEMPLATES: {"stub": True})
        monkeypatch.setattr(cw, "load_tab_templates", lambda path=cw.TAB_TEMPLATES: {"stub": True})
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
    assert out["tabs"] == "ok"


def test_a_missing_or_swapped_tab_stops_before_anything_is_typed(sim: Any) -> None:
    """Batt 2026-11-05: "arrange the tabs correctly". A tab missing (11-04: the second one) or the
    tabs swapped, read with confidence, stops with a frame; nothing is clicked on the tab strip."""
    for tabs in (("battle", "empty"), ("regular", "battle"), ("empty", "regular")):
        c = Client(tabs=tabs)
        with pytest.raises(cw.ChatWindowError, match="tabs: expected Battle Log . Chat"):
            cw.ensure(sim(c), None, why="t")
        assert c.world == [] and c.log == [], tabs


def test_unread_tabs_are_read_again_parked_then_pass_with_a_warning(sim: Any) -> None:
    c = Client(tabs=("battle", None))  # the second label unsure (a bright scene behind it)
    agent = sim(c)
    out = cw.ensure(agent, None, why="t")
    assert out["standard"] and out["tabs"] == "unread" and agent.moves == 2  # one park
    assert c.log == [] and c.world == []


def test_yesterdays_window_is_docked_sized_and_locked(sim: Any) -> None:
    # 11-04: moved up, taller, padlock closed, input closed
    c = Client(size=9, left=0, bottom=640, locked=True, input_open=False)
    agent = sim(c)
    out = cw.ensure(agent, None, why="t")
    assert out["standard"] and {k: v for k, v in c.state().items() if k != "tabs"} == {
        **_st(),
        "input": "open",
    }
    assert out["steps"] == ["unlock", "open_input", "drag", "f10", "f10", "f10", "f10", "f10",
                            "f10", "lock"]  # fmt: skip
    assert c.world == []  # no press ever reached the world
    assert c.gate == ["chat_window:t"]  # Enter only behind the UI gate


def test_no_window_found_is_never_answered_by_a_blind_f10(sim: Any) -> None:
    """2026-11-05 21:21, xmas_dun02: over a bright floor the reader missed a standard window and
    F10 cycled it to 9 lines. A first read without a window now STOPS (hidden, or not read)."""
    c = Client(size="hidden", input_open=True)
    with pytest.raises(cw.ChatWindowError, match="no F10 blind"):
        cw.ensure(sim(c), None, why="t")
    assert c.log == [] and c.size == "hidden"


def test_the_checks_own_cycle_goes_on_through_hidden_and_the_bar_alone(sim: Any) -> None:
    """From the largest size its own F10 hides the window, then shows the bar alone: expected."""
    c = Client(size=15, input_open=True)
    out = cw.ensure(sim(c), None, why="t")
    assert out["steps"] == ["f10"] * 4 and c.size == 6 and c.world == []


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


def test_a_window_seen_in_part_where_it_belongs_is_never_answered_by_a_key() -> None:
    """2026-11-06 09:25 (hunt_flow v56 run 2's setup): the level-up notice icon covered the
    standard window's bottom-left; "seen in part" -> Enter closed the open input, then the check
    stopped. At the standard place a hidden bottom means a cover: stop, no key. A MOVED window
    seen in part keeps its designed step (test_a_moved_closed_window_over_a_grey_scene_...)."""
    g = cw.STANDARD
    covered = {"left": g.left, "text_top": g.text_top, "bottom": None, "lines": None,
               "input": None, "obscured": True}  # fmt: skip
    assert cw.next_step(covered) == "unknown"
    moved = {**covered, "left": 40, "text_top": cw.Geometry(12, 639).text_top}
    assert cw.next_step(moved) == "open_input"
