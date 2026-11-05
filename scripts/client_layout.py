#!/usr/bin/env python3
"""The client's UI LAYOUTS: the STANDARD one and Batt's HUNTING one (2026-10-19: "players do
this; it uncovers play area"), read from pixels and reached through the client's OWN UI only.

    client_layout.py read                  the layout the screen shows (no input)
    client_layout.py ensure hunt|standard  reach it (F12 / the Basic Info arrow / a chat tab)

The hunting layout (docs/client/rathena-client.md "The hunting layout"):
- the hotkey bar shows ONE row (row 1 keeps the Fly Wing in slot 1): F12 cycles the bar
  4 rows -> hidden -> 1 -> 2 -> 3 -> 4 (seen live 2026-10-19);
- the menu ICON PANEL under Basic Information is collapsed by the window's own arrow (about
  (109, 138)); HP / SP / levels / the weight line stay (gm_state and the weight reader re-proven);
- the chat window stays where it is (neither Batt nor the agent could move it by its tabs; its
  message area is click-through), with two tabs, "Battle Log | Regular Chat" (Batt's
  arrangement, recorded as human-ui-setup 20261019T135848). The hunting layout SHOWS Battle Log
  (battle, EXP, item get/drop... lines; Batt's category set) so the combat log can be read;
  Regular Chat keeps the typed commands, and the /where fallback switches to it and back.
The standard layout: 4 rows, the panel expanded, Regular Chat shown.
➡️ SUPERSEDED FOR THE CHAT WINDOW on 2026-11-05 (Batt): the chat window has its own standard,
docked at the bottom-left with 6 lines and two tabs, Battle Log | Chat (scripts/chat_window.py,
checked at every game entry and before every typed line; the client's NewTab_2, renamed "Chat" at
20:03, replaced the Regular Chat tab lost on 11-04 and keeps its role and key "regular"). A tab
that is not in chat_window.TABS is REFUSED, never clicked (the empty tab strip is click-through:
a click there walks). The tab row, the tab click points and the chat rectangle of ``ui_windows``
follow chat_window.active(); RECTS keeps the RECORDED (frozen-layout) values for the offline
tools that read older sessions.

The run-time UI rectangles (route_preview.UI_WINDOWS and everything built on it) follow the
SELECTED layout of this process (``select`` before the mask modules are imported; the runner does
it from PARAMS["ui_layout"]); the default is the standard set, unchanged.
Templates: data/ui_anchors/layout/*.npy (client pixels: local only, never committed).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "data/ui_anchors/layout"
ENV = "PORING_CLIENT_LAYOUT"
LAYOUTS = ("standard", "hunt")
# x0, y0, x1, y1 client px, in work_zone.WINDOW_NAMES order: basic_info, hotbar, top, minimap,
# chat, notice_left, notice_right
RECTS: dict[str, tuple[tuple[int, int, int, int], ...]] = {
    "standard": ((0, 0, 220, 326), (230, 0, 520, 132), (750, 0, 828, 36), (1135, 14, 1266, 162),
                 (0, 532, 600, 626), (0, 668, 50, 720), (1228, 668, 1280, 720)),
    # measured on the live client 2026-10-19 14:3x (the last light row of each window on a clean
    # frame): Basic Info collapsed ends at y 142 (its arrow and notice badge on the bottom edge),
    # the 1-row bar at y 32
    "hunt": ((0, 0, 220, 143), (230, 0, 520, 33), (750, 0, 828, 36), (1135, 14, 1266, 162),
             (0, 532, 600, 626), (0, 668, 50, 720), (1228, 668, 1280, 720)),
}  # fmt: skip
# the tab: the standard layout shows the replies' tab ("regular": Regular Chat until 11-04, the
# client's NewTab_2 since 2026-11-05 13:2x, named "Chat" since 20:03), the hunting layout Battle Log
TARGET = {"standard": {"rows": 4, "panel": "expanded", "tab": "regular"},
          "hunt": {"rows": 1, "panel": "collapsed", "tab": "battle"}}  # fmt: skip
# template crops (x0, y0, x1, y1) and the click points of the client's own controls
# the arrow's crop leaves out the red notice badge drawn right of it (x >= 117: v43 run 2's start)
BOX = {"arrow": (102, 133, 114, 144), "row1": (231, 3, 247, 22), "row2": (232, 44, 246, 64),
       "row4": (232, 107, 246, 127)}  # fmt: skip
ARROW_PX = (109, 138)
# The chat TABS are translucent (the ground shows through: a whole-strip template failed on v43
# run 2's start); the SELECTED tab alone draws a white top border on the tab row over its span:
# 253-255 grey vs 77-159 for the other, on every background seen. Its "distance" is 255 - that.
# The row is chat_window.active().tab_row (529 in the frozen layout, 582 in the 2026-11-05
# standard); a tab's click point is 9 px below it
# spans inside the selected tab's border for both tab sets: Battle Log 5-70; Regular Chat (until
# 11-04) 74-~155; NewTab_2 / Chat (since 2026-11-05) 74-139. Clicks at a tab's middle in both
TAB_SPAN = {"battle": (12, 66), "regular": (88, 134)}
TAB_X = {"battle": 42, "regular": 106}
CHAT_INDEX = 4  # the chat window's entry in a RECTS tuple (work_zone.WINDOW_NAMES order)


def _chat() -> Any:
    sys.path.insert(0, str(ROOT / "scripts"))
    import chat_window

    return chat_window


def tab_row() -> int:
    return int(_chat().active().tab_row)


def tab_px(which: str) -> tuple[int, int]:
    return (TAB_X[which], tab_row() + 9)


MATCH = {"tabs": 25.0, "arrow": 15.0, "row": 10.0}
OTHER_MIN = 25.0  # the arrow's other state must be at least this far


def select(name: str) -> None:
    """This process's layout for the UI rectangles; call BEFORE the mask modules are imported."""
    if name not in LAYOUTS:
        raise ValueError(f"unknown layout {name!r}")
    os.environ[ENV] = name


def active() -> str:
    name = os.environ.get(ENV, "standard")
    return name if name in LAYOUTS else "standard"


def ui_windows(name: str | None = None) -> tuple[tuple[int, int, int, int], ...]:
    """The LIVE windows of layout ``name``: RECTS with the chat window where
    chat_window.active() puts it (the 2026-11-05 standard unless a replay selected "legacy")."""
    rects = list(RECTS[name or active()])
    rects[CHAT_INDEX] = _chat().active().rect
    return tuple(rects)


def _grey(img: Any, box: tuple[int, int, int, int]) -> Any:
    x0, y0, x1, y1 = box
    c = np.asarray(img)[y0:y1, x0:x1, :3].astype(np.float32)
    return c[..., 0] * 0.299 + c[..., 1] * 0.587 + c[..., 2] * 0.114  # RGB


def load_templates(root: Path = TEMPLATES) -> dict[str, Any]:
    names = ("arrow_collapsed", "arrow_expanded", "row1", "row2", "row4")
    return {n: np.load(root / f"{n}.npy") for n in names}


def decide(d: Mapping[str, float]) -> dict[str, Any]:
    """PURE: the layout from template distances (mean abs grey difference). Unknown -> None."""
    tab = None
    if d["tabs_battle"] <= MATCH["tabs"] < d["tabs_regular"]:
        tab = "battle"
    elif d["tabs_regular"] <= MATCH["tabs"] < d["tabs_battle"]:
        tab = "regular"
    panel = None
    if d["arrow_collapsed"] <= MATCH["arrow"] and d["arrow_expanded"] >= OTHER_MIN:
        panel = "collapsed"
    elif d["arrow_expanded"] <= MATCH["arrow"] and d["arrow_collapsed"] >= OTHER_MIN:
        panel = "expanded"
    r1, r2, r4 = (d[k] <= MATCH["row"] for k in ("row1", "row2", "row4"))
    # rows: 4; 2 = "2 or 3" (a step of the F12 cycle, seen live); 1; 0 = hidden; None = no sense
    rows: int | None
    if r1 and r2:
        rows = 4 if r4 else 2
    elif r1:
        rows = None if r4 else 1
    else:
        rows = None if (r2 or r4) else 0
    return {"rows": rows, "panel": panel, "tab": tab}


def read(img_rgb: Any, tm: Mapping[str, Any], chat: Any = None) -> dict[str, Any]:
    """The layout a game-region RGB frame shows (``decide`` on its template distances). ``chat``:
    the chat window's geometry (chat_window.Geometry) of a RECORDED frame (chat_window.for_sid);
    default this process's (chat_window.active())."""
    box = {"arrow_collapsed": "arrow", "arrow_expanded": "arrow", "row1": "row1", "row2": "row2",
           "row4": "row4"}  # fmt: skip
    d = {k: float(np.abs(_grey(img_rgb, BOX[b]) - tm[k]).mean()) for k, b in box.items()}
    row = int(chat.tab_row) if chat is not None else tab_row()
    for tab, (x0, x1) in TAB_SPAN.items():
        d[f"tabs_{tab}"] = 255.0 - float(_grey(img_rgb, (x0, row, x1, row + 1)).mean())
    return {**decide(d), "dist": {k: round(v, 1) for k, v in d.items()}}


def matches(state: Mapping[str, Any], name: str) -> bool:
    """PURE: the read state IS layout ``name``."""
    return all(state.get(k) == v for k, v in TARGET[name].items())


def next_step(state: Mapping[str, Any], name: str) -> str | None:
    """PURE: the next UI step towards layout ``name`` ("f12" / "arrow" / "tab:<which>"), None
    when there; "unknown" when the state cannot be read (the caller stops: never act blind)."""
    if any(state.get(k) is None for k in ("panel", "tab")) or state.get("rows") is None:
        return "unknown"
    t = TARGET[name]
    if state["rows"] != t["rows"]:
        return "f12"
    if state["panel"] != t["panel"]:
        return "arrow"
    if state["tab"] != t["tab"]:
        # a tab the chat window does not have is never clicked (click-through strip: a walk)
        return f"tab:{t['tab']}" if t["tab"] in _chat().TABS else "unknown"
    return None


class LayoutError(RuntimeError):
    pass


def _grab_rgb(screen: Any) -> Any:
    sys.path.insert(0, str(ROOT / "scripts"))
    import ro_agent as r

    x0, y0, w, h = r.game_region()
    return np.asarray(screen.grab(x0, y0, w, h)[1])[..., :3][..., ::-1]


def _park(agent: Any) -> None:
    import ro_agent as r

    x0, y0, _, _ = r.game_region()
    agent.move(x0 + 1240, y0 + 386)  # two motions: the client draws its cursor at the second
    time.sleep(0.25)
    agent.move(x0 + 1250, y0 + 380)
    time.sleep(0.6)


def _ui_click(agent: Any, u: int, v: int) -> None:
    import ro_agent as r

    x0, y0, _, _ = r.game_region()
    agent.move(x0 + u - 6, y0 + v + 4)  # a cold-jump UI click is ignored: two motions first
    time.sleep(0.25)
    agent.move(x0 + u, y0 + v)
    time.sleep(0.25)
    agent.click(x0 + u, y0 + v)
    time.sleep(0.5)


def state_now(agent: Any, screen: Any, tm: Mapping[str, Any]) -> dict[str, Any]:
    _park(agent)  # the cursor off every template
    return read(_grab_rgb(screen), tm)


def ensure(agent: Any, screen: Any, name: str, max_steps: int = 10) -> dict[str, Any]:
    """Reach layout ``name`` through the client's own controls, one verified step at a time.
    Raises LayoutError on an unreadable state or when it is not reached in ``max_steps``."""
    tm = load_templates()
    steps: list[str] = []
    for _ in range(max_steps):
        st = state_now(agent, screen, tm)
        step = next_step(st, name)
        if step is None:
            return {"layout": name, "steps": steps, "state": st}
        if step == "unknown":
            raise LayoutError(f"the client's layout is unreadable: {st} (steps {steps})")
        if step == "f12":
            agent.keys("F12")
            time.sleep(0.6)
        elif step == "arrow":
            _ui_click(agent, *ARROW_PX)
        else:
            _ui_click(agent, *tab_px(step.split(":", 1)[1]))
        steps.append(step)
    raise LayoutError(f"layout {name} not reached in {max_steps} steps: {steps}")


def select_tab(agent: Any, screen: Any, which: str) -> None:
    """Show chat tab ``which`` ("battle" / "regular") and verify it; LayoutError if not. A tab the
    chat window's standard does not have (chat_window.TABS; Regular Chat is gone since
    2026-11-05) is refused BEFORE any input: the empty tab strip passes a click to the world."""
    if which not in _chat().TABS:
        raise LayoutError(f"chat tab {which!r} is not in the chat window's standard "
                          f"{_chat().TABS}: nothing clicked")  # fmt: skip
    tm = load_templates()
    for _ in range(2):
        if state_now(agent, screen, tm).get("tab") == which:
            return
        _ui_click(agent, *tab_px(which))
    if state_now(agent, screen, tm).get("tab") != which:
        raise LayoutError(f"chat tab {which} not shown")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("read")
    e = sub.add_parser("ensure")
    e.add_argument("name", choices=LAYOUTS)
    a = ap.parse_args()
    sys.path.insert(0, str(ROOT / "scripts"))
    import ro_agent as r

    if a.cmd == "read":
        print(json.dumps(read(_grab_rgb(r.Screen()), load_templates())))
        return 0
    with r.session("rule:client-layout") as (agent, screen):
        r.activate_client(agent, screen)
        print(json.dumps(ensure(agent, screen, a.name)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
