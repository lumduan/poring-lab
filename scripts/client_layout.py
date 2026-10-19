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
TARGET = {"standard": {"rows": 4, "panel": "expanded", "tab": "regular"},
          "hunt": {"rows": 1, "panel": "collapsed", "tab": "battle"}}  # fmt: skip
# template crops (x0, y0, x1, y1) and the click points of the client's own controls
BOX = {"tabs": (2, 530, 160, 547), "arrow": (101, 132, 117, 145), "row1": (231, 3, 247, 22),
       "row2": (232, 44, 246, 64), "row4": (232, 107, 246, 127)}  # fmt: skip
ARROW_PX = (109, 138)
TAB_PX = {"battle": (42, 538), "regular": (119, 538)}
MATCH = {"tabs": 8.0, "arrow": 15.0, "row": 10.0}
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
    return RECTS[name or active()]


def _grey(img: Any, box: tuple[int, int, int, int]) -> Any:
    x0, y0, x1, y1 = box
    c = np.asarray(img)[y0:y1, x0:x1, :3].astype(np.float32)
    return c[..., 0] * 0.299 + c[..., 1] * 0.587 + c[..., 2] * 0.114  # RGB


def load_templates(root: Path = TEMPLATES) -> dict[str, Any]:
    names = ("tabs_battle", "tabs_regular", "arrow_collapsed", "arrow_expanded", "row1", "row2",
             "row4")  # fmt: skip
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
    rows: int | None = 4 if (r1 and r2 and r4) else 1 if (r1 and not r2) else 0 if not r1 else None
    return {"rows": rows, "panel": panel, "tab": tab}


def read(img_rgb: Any, tm: Mapping[str, Any]) -> dict[str, Any]:
    """The layout a game-region RGB frame shows (``decide`` on its template distances)."""
    box = {"tabs_battle": "tabs", "tabs_regular": "tabs", "arrow_collapsed": "arrow",
           "arrow_expanded": "arrow", "row1": "row1", "row2": "row2", "row4": "row4"}  # fmt: skip
    d = {k: float(np.abs(_grey(img_rgb, BOX[b]) - tm[k]).mean()) for k, b in box.items()}
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
        return f"tab:{t['tab']}"
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
            _ui_click(agent, *TAB_PX[step.split(":", 1)[1]])
        steps.append(step)
    raise LayoutError(f"layout {name} not reached in {max_steps} steps: {steps}")


def select_tab(agent: Any, screen: Any, which: str) -> None:
    """Show chat tab ``which`` ("battle" / "regular") and verify it; LayoutError if not."""
    tm = load_templates()
    for _ in range(2):
        if state_now(agent, screen, tm).get("tab") == which:
            return
        _ui_click(agent, *TAB_PX[which])
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
