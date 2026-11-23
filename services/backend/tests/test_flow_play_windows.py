"""flow_play's Run log names where the game's windows were found (teaching-prerun.md 4f), BEFORE
it says how the bot sees the client, and the player's own region follows the find (a 1280x720
window with dragged windows becomes virtual)."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import flow_play as fp  # noqa: E402


def fake_r(away: str | None, moved: bool) -> Any:
    state = {"found": False}

    def find_panels(screen: Any) -> dict[str, Any]:
        state["found"] = True
        return {}

    return types.SimpleNamespace(
        desktop=lambda: (1280, 720), real_game_region=lambda: (0, 0, 1280, 720),
        fullscreen=lambda: True, _raw_distance=lambda screen, sig: 44.0,
        away_verdict=lambda full, d1, d2: away, TASKBAR_ABSENT_MIN=20, SIG_MATCH=6,
        find_panels=find_panels,
        panels_words=lambda: ["the hotbar found at (700, 600): moved to the lab's place"],
        virtual_active=lambda: moved and state["found"],
        game_region=lambda: (100_000, 0, 1280, 720) if moved and state["found"]
        else (0, 0, 1280, 720),
        backend_health=lambda: {"mode": "ASSIST"}, input_modes=lambda v: ["ASSIST", "BOT"],
        MODES_ENV="X", pause_away=lambda: True,
    )  # fmt: skip


def pio(r: Any) -> Any:
    p = object.__new__(fp.PixelIO)
    p.r, p.screen, p.region = r, object(), (0, 0, 1280, 720)
    return p


def test_the_windows_are_found_before_the_view_is_told_and_the_region_follows() -> None:
    p = pio(fake_r(None, moved=True))
    lines = p.describe()
    assert "virtual 1280x720 client" in lines[0]
    assert "each window moved to its lab place" in lines[0]
    assert lines[1].startswith("the game is on the screen")
    assert lines[2] == "the hotbar found at (700, 600): moved to the lab's place"
    assert p.region == (100_000, 0, 1280, 720)


def test_the_windows_are_not_looked_for_while_the_game_is_off_the_screen() -> None:
    p = pio(fake_r("the Windows taskbar shows", moved=True))
    lines = p.describe()
    assert "the bot sees it 1:1" in lines[0]
    assert "the windows: not looked for (the game is not on the screen)" in lines
    assert p.region == (0, 0, 1280, 720)


def test_the_bag_line_names_the_rows_and_why_slots_were_unread() -> None:
    """Batt 2026-11-23: live's start count said "0 kinds read, 27 slot(s) unread" and nothing
    more -- the line now names the window's rows and the unread slots' reasons, counted."""
    got = {"rows": 9, "tabs": [
        {"tab": "use", "unread": [{"slot": 0, "why": "no known icon (the nearest Apple at 41.2)"},
                                  {"slot": 1, "why": "no known icon (the nearest Jellopy at 39.0)"},
                                  {"slot": 2, "why": "the count did not read"}]},
        {"tab": "etc", "unread": [{"slot": 0, "why": "no known icon (the nearest Scell at 50.1)"}]},
        {"tab": "eqp", "unread": []}]}  # fmt: skip
    words = fp.bag_words(got)
    assert words == "the window 7 x 9; unread: 3 no known icon, 1 the count did not read"
    assert fp.bag_words({"tabs": []}) == "the window's rows not recorded"
    assert fp.bag_words({"rows": 6, "tabs": [{"unread": [{"slot": 4}]}]}) == (
        "the window 7 x 6; unread: 1 no reason given"
    )
