"""scripts/talk1.py (talk@1, demonstrations 3.30): the seeded plan (targets found in L3 by cell,
start and goal cells, the first option) and the dialog logic -- T2 states, T3 reads, the scroll, the
choice by text, the highlight check, OK / Cancel, the clean close -- against a FAKE client (no
pixels, no input). The menu strings are invented; the real ones come from the local L3 at run
time."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from poring_env import menu_text as mt
from poring_env import npc_dialog as nd

SCRIPTS = Path(__file__).resolve().parents[2].parent / "scripts"
S = 1_000_000_000


@pytest.fixture(scope="module")
def talk1() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("talk1", SCRIPTS / "talk1.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["talk1"] = mod
    spec.loader.exec_module(mod)
    return mod


MENU7 = ["Ask about A", "Ask about B", "Ask about C ", "Ask about D", "Ask about E",
         "Ask about F", "Leave now"]  # fmt: skip
MENU8 = [*MENU7[:6], "Ask about G", "Leave, thanks."]
MENU4 = ["Open the map", "Clear the marks", "Read a notice", "Cancel it"]


def l3(**over: Any) -> dict[str, Any]:
    npcs = [
        {"name": "NpcA#x", "map": "prt_church", "x": 103, "y": 76},
        {"name": "NpcB#x", "map": "prt_church", "x": 103, "y": 71},
        {"name": "NpcC#x", "map": "prontera", "x": 154, "y": 187},
    ]
    menus = {"NpcA#x": [{"options": MENU7}], "NpcB#x": [{"options": MENU8}],
             "NpcC#x": [{"options": MENU4}, {"options": ["Yes", "No"]}]}  # fmt: skip
    menus.update(over)
    return {"npc": {"positions": {"npcs": npcs}, "menus": {"by_npc": menus}}}


def test_targets_are_found_in_l3_by_their_cell(talk1: Any) -> None:
    info = talk1.l3_target(l3(), talk1.TARGETS["garnet"])
    assert info["name"] == "NpcA#x" and info["menus"][0] == MENU7 and info["others"] == [(103, 71)]
    assert talk1.l3_target(l3(), talk1.TARGETS["guide"])["menus"][1] == ["Yes", "No"]
    with pytest.raises(SystemExit, match="not 7 options"):
        talk1.l3_target(l3(**{"NpcA#x": [{"options": MENU8}]}), talk1.TARGETS["garnet"])
    coloured = [*MENU7[:2], "^0000FFAsk^000000", *MENU7[3:]]
    with pytest.raises(SystemExit, match="coloured"):
        talk1.l3_target(l3(**{"NpcA#x": [{"options": coloured}]}), talk1.TARGETS["garnet"])
    empty = {"npc": {"positions": {"npcs": []}, "menus": {"by_npc": {}}}}
    with pytest.raises(SystemExit, match="0 NPCs"):
        talk1.l3_target(empty, talk1.TARGETS["garnet"])


def church() -> np.ndarray:
    """A corridor like the church's: x 96-103 walkable, the NPCs on its east edge."""
    w = np.zeros((200, 200), bool)
    w[50:100, 96:104] = True
    return w


def test_the_plan_is_seeded_alternating_and_inside_the_rules(talk1: Any) -> None:
    data = l3()
    info = {k: talk1.l3_target(data, talk1.TARGETS[k]) for k in ("garnet", "henson")}
    plans = talk1.plan_trials("prt_church", 20, 20261130, info, church(), lambda a, b: True)
    assert plans == talk1.plan_trials("prt_church", 20, 20261130, info, church(),
                                      lambda a, b: True)  # fmt: skip
    assert plans != talk1.plan_trials("prt_church", 20, 7, info, church(), lambda a, b: True)
    for p in plans:
        t = talk1.TARGETS[p["target"]]
        assert p["target"] == ("garnet", "henson")[p["k"] % 2] and p["npc_cell"] == list(t.cell)
        other = (103, 71) if p["target"] == "garnet" else (103, 76)
        assert 4 <= talk1.cheb(p["start"], t.cell) <= 8 and talk1.cheb(p["start"], other) >= 3
        assert 2 <= talk1.cheb(p["goal"], t.cell) <= 3 and talk1.cheb(p["goal"], other) > 1
        assert np.hypot(*np.subtract(p["goal"], p["start"])) < np.hypot(
            *np.subtract(t.cell, p["start"]))  # our side  # fmt: skip
        assert church()[p["start"][1], p["start"][0]] and church()[p["goal"][1], p["goal"][0]]
        menu = info[p["target"]]["menus"][0]
        assert p["first_position"] in t.first
        assert p["intended"] == [menu[p["first_position"] - 1], menu[-1]]
        assert p["l3_options"] == menu and p["npc"] == info[p["target"]]["name"]


def test_the_guide_never_picks_its_submenu_option(talk1: Any) -> None:
    walk = np.ones((300, 300), bool)
    info = {"guide": talk1.l3_target(l3(), talk1.TARGETS["guide"])}
    plans = talk1.plan_trials("prontera", 40, 20261131, info, walk, lambda a, b: True)
    assert {p["first_position"] for p in plans} == {2, 3}
    assert all(p["intended"][1] == MENU4[3] for p in plans)


def test_no_reachable_goal_stops_the_plan(talk1: Any) -> None:
    info = {k: talk1.l3_target(l3(), talk1.TARGETS[k]) for k in ("garnet", "henson")}
    with pytest.raises(SystemExit, match="no goal"):
        talk1.plan_trials("prt_church", 2, 1, info, church(), lambda a, b: False)


@pytest.mark.parametrize("name", ["walk15", "walk16"])
def test_the_walk_rule_is_reused_unchanged(name: str) -> None:
    sys.path.insert(0, str(SCRIPTS))
    w = importlib.import_module(name)
    assert callable(w.walk_route) and w.WALK == "walk" and callable(w.where_relocalise)
    rule = name.replace("walk", "walk@")
    assert rule == w.WALK8_RULE


# --- the fake client ----------------------------------------------------------------------------

D_RECT = (201, 101, 278, 178)
M_RECT = (201, 301, 278, 118)


class FakeClient:
    """An NPC's dialog: ``pages`` NEXT pages, then the menu; a choice gives ``after`` pages and the
    menu again; the LAST option ends: CLOSE. The menu shows 4 rows and scrolls ``step`` rows per
    arrow click; a row click selects (``follows``) or chooses (``chooses``)."""

    def __init__(self, options: list[str], pages: int = 3, after: int = 2, step: int = 1,
                 follows: bool = True, chooses: bool = False, unread: tuple[int, ...] = (),
                 unread_at: tuple[tuple[int, int], ...] = (), opens: bool = True,
                 button: bool = True) -> None:  # fmt: skip
        self.options, self.n = options, len(options)
        self.phase = "page" if opens else "closed"
        self.left, self.after, self.step = pages, after, step
        self.follows, self.chooses, self.unread, self.button = follows, chooses, unread, button
        self.unread_at = unread_at  # (top, row): unreadable only at that scroll position
        self.top = self.sel = 0
        self.t = 0
        self.page = 0
        self.clicks: list[tuple[str, int, int]] = []
        self.choices: list[int] = []
        self.closed_by: str | None = None

    # the Io
    def observe(self) -> tuple[nd.NpcUiState, Any]:
        self.t += S // 20
        return self.view(), {"lines": self.lines()}

    def now(self) -> int:
        return self.t

    def wait(self, seconds: float) -> None:
        self.t += int(seconds * S)

    def digest(self, frame: Any, state: nd.NpcUiState) -> str:
        return f"page{self.page}" if state.dialog is not None else "-"

    def click(self, x: int, y: int, what: str, inside: nd.Box) -> int:
        bx, by, bw, bh = inside
        assert bx <= x < bx + bw and by <= y < by + bh, (what, x, y, inside)
        st = self.view()
        self.clicks.append((what, x, y))
        self.t += S // 10
        if what == "next" and self.phase == "page":
            self.page += 1
            self.left -= 1
            if self.left == 0:
                self.phase, self.top, self.sel = "menu", 0, 0
        elif what == "close" and self.phase == "close":
            self.phase, self.closed_by = "closed", "close"
        elif what.startswith("scroll_") and self.phase == "menu":
            d = self.step if what == "scroll_down" else -self.step
            self.top = max(0, min(self.n - 4, self.top + d))
        elif what.startswith("row_") and self.phase == "menu":
            assert st.menu is not None and st.menu.rect == inside
            if self.follows:
                self.sel = self.top + int(what[4:])
            if self.chooses:
                self.choose()
        elif what == "ok" and self.phase == "menu":
            self.choose()
        elif what == "cancel" and self.phase == "menu":
            self.phase, self.closed_by = "closed", "cancel"
        return self.t

    def choose(self) -> None:
        self.choices.append(self.sel + 1)
        self.page += 1
        if self.sel + 1 == self.n:
            self.phase = "close"
        else:
            self.phase, self.left = "page", self.after

    # what the client shows
    def lines(self) -> list[str]:
        vis = [o.rstrip(" ") for o in self.options]
        return (vis[self.top : self.top + 4] + [""] * 4)[:4]

    def view(self) -> nd.NpcUiState:
        if self.phase == "closed":
            return nd.NpcUiState(True, "ok", 1.0)
        button = ("next" if self.phase == "page" and self.button else
                  "close" if self.phase == "close" else None)  # fmt: skip
        dialog = nd.DialogView(D_RECT, button, (434, 256, 42, 20), 0.0, {})  # type: ignore[arg-type]
        menu = None
        if self.phase == "menu":
            rows = tuple((212, 326 + 16 * k, 243, 16) for k in range(4))
            hl = self.sel - self.top if 0 <= self.sel - self.top < 4 else None
            bar = self.n > 4
            menu = nd.MenuView(M_RECT, rows, ("plain",) * 4, hl, bar, bar and self.top > 0,
                               bar and self.top + 4 < self.n, (self.top, self.top + 5) if bar
                               else None, (388, 396, 42, 20), (434, 396, 42, 20),
                               (455, 329, 13, 10), (455, 378, 13, 10), 0.0)  # fmt: skip
        return nd.NpcUiState(True, "ok", 1.0, dialog, menu)


def reader(client: FakeClient) -> Any:
    def read(frame: Any, menu: nd.MenuView) -> mt.MenuSnapshot:
        lines = []
        for k, text in enumerate(frame["lines"]):
            if client.top + k in client.unread or (client.top, k) in client.unread_at:
                lines.append(mt.RowRead(None, "unknown_glyph"))
            else:
                lines.append(mt.RowRead(text, "ok" if text else "empty", 1.0))
        return mt.MenuSnapshot(tuple(lines), menu.can_scroll_up, menu.can_scroll_down)

    return read


def run_dialog(talk1: Any, client: FakeClient, options: list[str], first: int,
               menus: list[list[str]] | None = None, budget: float = 120.0) -> Any:  # fmt: skip
    plan = talk1.DialogPlan((options[first - 1], options[-1]), menus or [options])
    log = talk1.dialog_loop(client, reader(client), plan, client.now(), budget)
    return log, talk1.runtime_gone(client, reader(client))


@pytest.mark.parametrize("first", [1, 3, 6])
def test_a_clean_dialog_chooses_by_text_and_closes(talk1: Any, first: int) -> None:
    c = FakeClient(MENU7)
    log, gone = run_dialog(talk1, c, MENU7, first)
    assert log.outcome is None and log.declined is None, log.as_dict()
    assert c.choices == [first, 7] and c.closed_by == "close" and log.close_click is not None
    assert [ch["packet_index"] for ch in log.choices] == [first, 7]
    assert all(ch["t_ok"] is not None for ch in log.choices)
    assert gone["closed"] and [r["list"] for r in log.reads] == ["ok", "ok"]
    whats = [w for w, _, _ in c.clicks]
    assert whats.count("next") == 3 + 2 and whats.count("ok") == 2 and "cancel" not in whats


def test_scroll_steps_and_short_menus(talk1: Any) -> None:
    c = FakeClient(MENU8, step=2)
    log, gone = run_dialog(talk1, c, MENU8, 7)
    assert log.outcome is None and c.choices == [7, 8] and gone["closed"]
    c = FakeClient(MENU4, pages=1, after=1)
    log, gone = run_dialog(talk1, c, MENU4, 2, menus=[MENU4, ["Yes", "No"]])
    assert log.outcome is None and c.choices == [2, 4]
    assert not any(w.startswith("scroll") for w, _, _ in c.clicks)


def test_a_menu_that_differs_from_l3_is_declined_by_cancel(talk1: Any) -> None:
    c = FakeClient(MENU7)
    other = [*MENU7[:3], "Ask about Q", *MENU7[4:]]
    log, gone = run_dialog(talk1, c, other, 2, menus=[other])
    assert log.outcome == "menu unread" and log.declined["why"] == "menu differs from L3"
    assert c.closed_by == "cancel" and c.choices == [] and gone["closed"]


def test_a_line_read_nowhere_is_a_decline(talk1: Any) -> None:
    c = FakeClient(MENU7, unread=(0,))
    log, _ = run_dialog(talk1, c, MENU7, 2)
    assert log.outcome == "menu unread" and log.declined["why"] == "menu unread"
    assert c.closed_by == "cancel"
    c = FakeClient(MENU7, unread_at=((0, 3),))  # read at another scroll position: fine
    log, _ = run_dialog(talk1, c, MENU7, 4)
    assert log.outcome is None and c.choices == [4, 7]


def test_the_highlight_must_follow_the_click(talk1: Any) -> None:
    c = FakeClient(MENU7, follows=False)
    log, _ = run_dialog(talk1, c, MENU7, 3)
    assert log.declined["why"] == "the highlight is not on the line"
    whats = [w for w, _, _ in c.clicks]
    assert sum(w.startswith("row_") for w in whats) == 2 and "ok" not in whats
    assert c.closed_by == "cancel"


def test_a_row_click_that_chooses_by_itself_is_logged(talk1: Any) -> None:
    c = FakeClient(MENU7, chooses=True)
    log, _ = run_dialog(talk1, c, MENU7, 2)
    assert log.outcome is None and c.choices == [2, 7]
    assert all(ch.get("by_row_click") for ch in log.choices)


def test_no_dialog_a_stuck_dialog_and_the_budget(talk1: Any) -> None:
    log, _ = run_dialog(talk1, FakeClient(MENU7, opens=False), MENU7, 2)
    assert log.outcome == "no dialog" and log.steps == []
    log, _ = run_dialog(talk1, FakeClient(MENU7, button=False), MENU7, 2)
    assert log.outcome == "dialog stuck"
    log, _ = run_dialog(talk1, FakeClient(MENU7, pages=10_000), MENU7, 2, budget=20.0)
    assert log.outcome == "timeout"


def test_a_next_that_changes_nothing_is_not_clicked_forever(talk1: Any) -> None:
    class Deaf(FakeClient):
        def click(self, x: int, y: int, what: str, inside: nd.Box) -> int:
            if what == "next":
                self.clicks.append((what, x, y))
                return self.t
            return super().click(x, y, what, inside)

    c = Deaf(MENU7)
    log, _ = run_dialog(talk1, c, MENU7, 2)
    assert log.outcome == "dialog stuck" and len(c.clicks) == talk1.MAX_IDLE_NEXT


def test_the_intended_option_must_be_in_the_menu(talk1: Any) -> None:
    c = FakeClient(MENU7)
    plan = talk1.DialogPlan(("Not offered", MENU7[-1]), [MENU7])
    log = talk1.dialog_loop(c, reader(c), plan, c.now())
    assert log.declined["why"] == "the intended option is not in this menu"


def test_the_runtime_check_needs_two_gone_observations(talk1: Any) -> None:
    c = FakeClient(MENU7)
    assert not talk1.runtime_gone(c, reader(c), timeout=1.0)["closed"]
    c.phase = "closed"
    got = talk1.runtime_gone(c, reader(c))
    assert got["closed"] and got["observations"][-2:] == ["gone", "gone"]


def test_an_unstable_state_is_never_acted_on(talk1: Any) -> None:
    class Flicker(FakeClient):
        def observe(self) -> tuple[nd.NpcUiState, Any]:
            st, fr = super().observe()
            self.page += 1  # the text never settles
            return st, fr

    c = Flicker(MENU7)
    log, _ = run_dialog(talk1, c, MENU7, 2, budget=30.0)
    assert log.outcome == "dialog unread" or log.outcome == "no dialog"
    assert c.clicks == []


def test_decline_all_pages_cancels_and_never_chooses(talk1: Any) -> None:
    """Batt 2026-10-09 ~19:30 (walk@17 item 5): an unintended dialog is declined by talk@1's safe
    path -- NEXT by image, any menu CANCELLED unread, CLOSE clicked -- never a choice."""
    c = FakeClient(MENU7, pages=2)
    log = talk1.decline_all(c, reader(c))
    assert log.outcome is None and c.closed_by == "cancel" and c.choices == []
    whats = [w for w, _, _ in c.clicks]
    assert whats.count("next") == 2 and whats.count("cancel") == 1
    assert not any(w.startswith(("row_", "scroll")) or w == "ok" for w in whats)
    assert log.declined["why"] == "an unintended dialog (decline all)"
    assert talk1.runtime_gone(c, reader(c))["closed"]


def test_decline_all_cancels_an_unread_menu_and_ignores_no_dialog(talk1: Any) -> None:
    c = FakeClient(MENU7, unread=tuple(range(7)))  # every menu row unreadable: still a menu
    assert talk1.decline_all(c, reader(c)).outcome is None
    assert c.closed_by == "cancel"  # a menu is cancelled without reading its rows
    c2 = FakeClient(MENU7, opens=False)
    assert talk1.decline_all(c2, reader(c2)).outcome is None and c2.clicks == []  # nothing open
