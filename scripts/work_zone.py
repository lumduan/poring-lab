"""The WORK ZONE: the game area minus the client's UI windows, each grown by a margin (Batt,
2026-10-08: walk@12's decision 1; targeting proposal (c) shares it with detection).

Over a UI window the client shows its plain arrow, which the cursor gate reads as WALK, so the gate
cannot protect a click there. walk@11 indoor CROWD route 53 clicked client (52.9, 295.8): the Basic
Information window's icon grid. The click opened the Shortcut Description window, and the chat
input could not open again for the rest of the run.

The windows are route_preview.UI_WINDOWS: the client's always-on windows at the FROZEN 1280x720
layout (client px). A window that is not drawn on a map (the minimap indoors) is still excluded.
Pixels only: nothing here reads the client's state.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from route_preview import UI_WINDOWS  # noqa: E402

MARGIN_PX = 12.0  # around every window (the walk@12 proposal; the unit gate's margin is also 12 px)
GAME_W, GAME_H = 1280, 720  # the frozen client layout (client px)
# UI_WINDOWS, in its order
WINDOW_NAMES = ("basic_info", "hotbar", "top", "minimap", "chat", "notice_left", "notice_right")


def ui_window_at(u: float, v: float, margin: float = MARGIN_PX) -> str | None:
    """The UI window whose rectangle, grown by ``margin``, holds client pixel (u, v); None if none.
    The grown rectangle's edge counts as inside."""
    for name, (x0, y0, x1, y1) in zip(WINDOW_NAMES, UI_WINDOWS, strict=True):
        if x0 - margin <= u <= x1 + margin and y0 - margin <= v <= y1 + margin:
            return name
    return None


def in_work_zone(u: float, v: float, margin: float = MARGIN_PX) -> bool:
    """Inside the game area and outside every UI window grown by ``margin``."""
    if not (0 <= u < GAME_W and 0 <= v < GAME_H):
        return False
    return ui_window_at(u, v, margin) is None
