#!/usr/bin/env python3
"""The chat window's STANDARD place and size (Batt 2026-11-05), read from pixels and restored
through the client's OWN controls only.

    chat_window.py read                      what the screen shows (no input)
    chat_window.py ensure [--why W]          reach the standard (F10 / the padlock / a drag of the
                                             white input bar; Enter only behind the UI gate)
    chat_window.py cut-padlock OPEN LOCKED   design time: the padlock templates from two client
                                             frames (PNG, 1280 x 720 or a full desktop grab)

THE STANDARD (Batt 2026-11-05, "drag it to the bottom-left corner, about 6 lines; make this the
default"): the window docked at the client's bottom-left corner (left x 0, its last row y 719),
SIX message lines, the padlock CLOSED (Batt's answer: lock after docking), one tab, Battle Log.
On 11-04 a moved chat window refused every typed line (chat_open 76-141 vs <= 6) and stopped the
guest demo: the check runs at every game entry (ro_agent.enter_game) and before every typed line
(ro_agent.open_chat), so a moved or resized window is put back before anything is typed.

THE CLIENT'S CONTROLS (seen live 2026-11-05 11:3x-11:4x, Batt's demonstration recorded with the
input log; docs/client/rathena-client.md "The chat window standard"):
- SIZE: F10, or the round icon at the input bar's right end (tooltip "Change size(F10)"). One press
  steps 3 -> 6 -> 9 -> 12 -> 15 lines -> the window HIDDEN -> the input bar alone -> 3 again; the
  window's BOTTOM stays put and each step moves the message area's top by 42 px. F10 works with
  the padlock closed.
- PLACE: a left drag on the WHITE INPUT BAR, only while the padlock is OPEN (Batt 2026-11-04). The
  bar is drawn only while the chat input is open: with it closed the message area runs down to the
  bottom, so the fix opens the input first (Enter, after ui_gate.ensure_clear).
- PADLOCK: the right end of the icon row above the message area; one click toggles it. Open, the
  row shows keyboard, settings, ">>", "+", "-" and the open padlock; closed, only keyboard,
  settings and the closed padlock. "+" / "-" ADD / DELETE TABS: never clicked (the "-" ends 8 px
  left of the padlock click point).
- The message area and the empty tab strip are CLICK-THROUGH (2026-10-19): no press lands there.

ONE GEOMETRY for every reader: the frozen Phase 2 layout of every session before 2026-11-05
(``LEGACY``: 3 lines, its last row at y 624) is this same window 95 px higher, and the formulas
below give back each of the old hard-coded numbers (ro_agent's chat_open box and chat_input
click, client_layout's tab row and rectangle, where_fix / chat_cue / battle_log's areas;
test_chat_window.py pins them). Live code reads ``active()`` (the standard unless
$PORING_CHAT_GEOMETRY says "legacy": replays and judges of older sessions).

Padlock templates are client pixels: data/ui_anchors/chat_window/padlock.npz (gitignored, never
committed), cut with ``cut-padlock``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "data/ui_anchors/chat_window/padlock.npz"
SHOTS = Path("/dev/shm/poring-lab-tmp/chat-window")
ENV = "PORING_CHAT_GEOMETRY"

LINE_PITCH = 14
SIZES = (3, 6, 9, 12, 15)  # message lines; the F10 cycle then hides the window, then shows the bar
WHITE = 225  # luma: the window's white borders and the open input bar (247-255 on a clean frame)
BAR_ROWS = (19, 3)  # the input bar's white field: rows bottom - 19 .. bottom - 3


@dataclass(frozen=True)
class Geometry:
    """The chat window at ``lines`` message lines, its last row at client y ``bottom``, its left
    edge at x ``left`` (client px of the 1280 x 720 game region)."""

    lines: int
    bottom: int
    left: int = 0

    @property
    def text_top(self) -> int:
        """The message area's white top border (not drawn under the selected tab)."""
        return self.bottom - 37 - LINE_PITCH * self.lines

    @property
    def tab_row(self) -> int:
        """The SELECTED tab's white top border."""
        return self.text_top - 16

    @property
    def chat_open_box(self) -> tuple[int, int, int, int]:
        """ro_agent's chat_open signature box (x, y, w, h): the open input bar."""
        return (self.left, self.bottom - 20, 570, 12)

    @property
    def input_px(self) -> tuple[int, int]:
        """A click INTO the input (and the drag's press point on the white bar)."""
        return (self.left + 300, self.bottom - 11)

    @property
    def padlock_px(self) -> tuple[int, int]:
        """The padlock's body, open or closed (open x 580-594, closed 581-590; y 589-594)."""
        return (self.left + 585, self.text_top - 7)

    @property
    def rect(self) -> tuple[int, int, int, int]:
        """The window for the UI masks (x0, y0, x1, y1): client_layout.RECTS's chat entry."""
        return (self.left, self.tab_row + 3, self.left + 600, min(720, self.bottom + 2))

    @property
    def message_area(self) -> tuple[int, int, int, int]:
        """where_fix's area (x0, y0, x1, y1): the lines, the scrollbar, the input's top border."""
        return (self.left, self.text_top, self.left + 640, self.bottom - 24)

    @property
    def cue_area(self) -> tuple[int, int, int, int]:
        """chat_cue's area (x0, y0, x1, y1): the message lines only."""
        return (self.left, self.text_top, self.left + 570, self.bottom - 31)

    def line_y0(self, n_read: int = 3) -> int:
        """battle_log's line 0 band top when it reads the NEWEST ``n_read`` lines (the bottom
        ones: a new line scrolls the others up)."""
        return self.text_top + 6 + LINE_PITCH * (self.lines - n_read)

    @property
    def battle_crop(self) -> tuple[int, int, int, int]:
        """battle_log's live grab (x0, y0, x1, y1): the tab strip down to the last line."""
        return (self.left, self.tab_row - 1, self.left + 600, self.bottom - 24)


LEGACY = Geometry(lines=3, bottom=624)  # every session before 2026-11-05 (the frozen layout)
STANDARD = Geometry(lines=6, bottom=719)  # Batt 2026-11-05: docked bottom-left, six lines
GEOMETRIES = {"standard": STANDARD, "legacy": LEGACY}
TABS = ("battle",)  # the standard's tabs (Batt 2026-11-05: Regular Chat is gone)


CUTOVER_SID = "20261105T12"  # sessions recorded from here on show the 2026-11-05 standard


def for_sid(sid: str, name: str | None = None) -> Geometry:
    """The chat window a RECORDED session shows: ``name`` ("legacy" / "standard") when given,
    else the frozen layout for every session before CUTOVER_SID (by the SID's date prefix).
    Offline readers of recorded frames use this, never ``active()``."""
    if name:
        return GEOMETRIES[name]
    return LEGACY if sid[:11] < CUTOVER_SID else STANDARD


def select(name: str) -> None:
    """This process's chat geometry ("legacy" to replay or judge sessions before 2026-11-05)."""
    if name not in GEOMETRIES:
        raise ValueError(f"unknown chat geometry {name!r}")
    os.environ[ENV] = name


def active() -> Geometry:
    return GEOMETRIES.get(os.environ.get(ENV, "standard"), STANDARD)


# --- reading (pure) -----------------------------------------------------------------------------


def luma(img_rgb: Any) -> np.ndarray:
    a = np.asarray(img_rgb)[..., :3].astype(np.float32)
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


# The window's frame (x offsets from its left, measured 2026-11-05 11:4x-12:25 on three frames:
# 6 lines with a scrollbar, input open / closed; 12 lines WITHOUT one, input closed). The client
# draws the scrollbar only once the log holds more lines than the window shows (a fresh login:
# none; 4.06 C4's first attempt stopped on that), so the reader never needs it:
# - the message area's WHITE TOP BORDER (row text_top) ends at x left + 592;
# - the RIGHT BORDER, column left + 596, luma 129-154, runs from text_top + 1 to the bottom with
#   the input closed, to bottom - 24 with it open (then the input bar's frame: 206, 247...);
# - the SEPARATOR row bottom - 23 is uniform (std ~4): luma ~139 closed, ~196 open; with the input
#   open the bar's white frame rows follow (bottom - 22, - 21; 247-255).
TOP_END = 592
BORDER_X, BORDER_LO, BORDER_HI = 596, 115.0, 175.0
SEP_STD = 12.0
SEP_CLOSED = (115.0, 175.0)
SEP_OPEN = (175.0, 225.0)


def _sep(lum: np.ndarray, y: int, left: int, band: tuple[float, float]) -> bool:
    """Row ``y`` is the separator: uniform across the window, its luma in ``band``."""
    if not 0 <= y < lum.shape[0]:
        return False
    row = lum[y, left + 5 : left + 590]
    return (
        bool(row.size) and float(row.std()) <= SEP_STD and band[0] <= float(row.mean()) <= band[1]
    )


def _border_run(lum: np.ndarray, y0: int, left: int) -> int | None:
    """The last row of the right border's continuous run from ``y0``, None if it is not there."""
    col = lum[:, left + BORDER_X]
    ok = (col >= BORDER_LO) & (col <= BORDER_HI)
    if y0 + 6 > len(col) or not ok[y0 : y0 + 6].all():
        return None
    off = np.flatnonzero(~ok[y0:])
    return y0 + int(off[0]) - 1 if off.size else lum.shape[0] - 1


def find(img_rgb: Any) -> dict[str, Any] | None:
    """The chat window on a game-region RGB frame: {"left", "text_top", "bottom", "lines",
    "input": "open" | "closed"}; {"lines": 0, ...} for the input bar alone; {"lines": None,
    "obscured": True, ...} for a window seen in part (its top border and right border found, its
    bottom not: the pointer over it, or a closed input whose bottom the scene hides): never a size
    to act on; None when no window is seen (hidden, or the input bar alone with the input
    closed)."""
    lum = luma(img_rgb)
    h, w = lum.shape
    white = lum >= WHITE
    counts = white.sum(axis=1)
    obscured: dict[str, Any] | None = None
    for y in np.nonzero(counts >= 450)[0]:
        y = int(y)
        edges = np.flatnonzero(np.diff(np.concatenate(([0], white[y].astype(np.int8), [0]))))
        for s, e in zip(edges[0::2], edges[1::2], strict=True):
            left = int(e) - 1 - TOP_END
            # the top border starts inside the window (x left + 3, or after the selected tab);
            # the input bar's white rows run from its left edge to x left + 597: never a border
            if e - s < 450 or left < 0 or s < left or left + BORDER_X >= w:
                continue
            run_end = _border_run(lum, y + 2, left)
            if run_end is None:
                continue
            found: dict[str, Any] | None = None
            sep = run_end + 1  # input OPEN: the border stops at the separator, the bar follows
            if sep + 3 < h and _sep(lum, sep, left, SEP_OPEN) and \
                    float(lum[sep + 1 : sep + 3, left + 5 : left + 590].mean()) >= 235:  # fmt: skip
                found = {"bottom": sep + 23, "input": "open"}
            elif _sep(lum, run_end - 23, left, SEP_CLOSED):  # CLOSED: the border runs to the bottom
                found = {"bottom": run_end, "input": "closed"}
            if found is not None:
                span = found["bottom"] - 37 - y
                if span % LINE_PITCH == 0 and span // LINE_PITCH in SIZES:
                    return {"left": left, "text_top": y, "bottom": found["bottom"],
                            "lines": span // LINE_PITCH, "input": found["input"]}  # fmt: skip
            obscured = obscured or {"left": left, "text_top": y, "bottom": None}
    if obscured is not None:
        return {**obscured, "lines": None, "input": None, "obscured": True}
    # the input bar alone (F10's last size): 17 white rows across the bar's message field; with a
    # message area above it (the right border) but no top border found, it is "obscured" too
    full = counts >= 450
    run = 0
    for y in range(h):
        run = run + 1 if full[y] else 0
        if run == 17 and y + 3 < h:
            bottom = y + 3
            cols = np.flatnonzero(lum[bottom - 11] >= 180)
            left = int(cols[0]) if cols.size else 0
            above = lum[max(bottom - 30, 0) : bottom - 24, min(left + BORDER_X, w - 1)]
            if above.size and bool(((above >= BORDER_LO) & (above <= BORDER_HI)).all()):
                return {"left": left, "text_top": None, "bottom": bottom, "lines": None,
                        "input": "open", "obscured": True}  # fmt: skip
            return {"left": left, "text_top": None, "bottom": bottom, "lines": 0, "input": "open"}
    return None


PADLOCK_BOX = (578, -14, 597, -2)  # x0, dy0, x1, dy1: from (left, text_top)
PADLOCK_MATCH, PADLOCK_MARGIN = 20.0, 15.0


def _padlock_crop(img_rgb: Any, left: int, text_top: int) -> np.ndarray:
    x0, dy0, x1, dy1 = PADLOCK_BOX
    return np.asarray(img_rgb)[text_top + dy0 : text_top + dy1, left + x0 : left + x1, :3]


def icon_mask(crop_rgb: Any) -> np.ndarray:
    """The icons' own pixels: their blue fill and their white outline (the scene shows around)."""
    a = np.asarray(crop_rgb)[..., :3].astype(np.int32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return ((b >= 170) & (b - r >= 40)) | (np.minimum(np.minimum(r, g), b) >= 225)


def padlock_distances(
    img_rgb: Any, st: Mapping[str, Any], tm: Mapping[str, Any]
) -> dict[str, float]:
    """Mean |grey| difference to each template over the pixels either template draws."""
    cur = luma(_padlock_crop(img_rgb, int(st["left"]), int(st["text_top"])))
    mask = tm["mask"]
    return {k: round(float(np.abs(cur - tm[k])[mask].mean()), 1) for k in ("open", "locked")}


def padlock_state(d: Mapping[str, float]) -> str | None:
    """PURE: "open" / "locked" from the template distances, None when neither is clear (the
    cursor over it, a frame still refining): the caller parks the pointer and reads again."""
    if d["open"] <= PADLOCK_MATCH and d["locked"] - d["open"] >= PADLOCK_MARGIN:
        return "open"
    if d["locked"] <= PADLOCK_MATCH and d["open"] - d["locked"] >= PADLOCK_MARGIN:
        return "locked"
    return None


def read(img_rgb: Any, tm: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """``find`` plus the padlock (``tm`` from load_templates; None leaves it unread)."""
    st = find(img_rgb)
    if st is None or not st["lines"] or tm is None:
        return st
    d = padlock_distances(img_rgb, st, tm)
    return {**st, "padlock": padlock_state(d), "padlock_dist": d}


def is_standard(st: Mapping[str, Any] | None, g: Geometry = STANDARD, lock: bool = True) -> bool:
    if not st or st.get("lines") != g.lines:
        return False
    if st.get("left") != g.left or st.get("bottom") != g.bottom:
        return False
    return not lock or st.get("padlock") == "locked"


def next_step(
    st: Mapping[str, Any] | None, g: Geometry = STANDARD, lock: bool = True
) -> str | None:
    """PURE: the next control towards the standard, None when there.
    "f10" (size, or showing a hidden window), "unlock" / "lock" (the padlock), "open_input"
    (Enter behind the UI gate: the drag handle is drawn only while the input is open), "drag",
    "unknown" (the padlock unread: the caller re-reads, never acts blind)."""
    if st is not None and st.get("obscured"):
        # seen in part with the input closed: open it (the bar shows the bottom); else re-read
        return "open_input" if st.get("text_top") is not None and st.get("input") is None \
            else "unknown"  # fmt: skip
    if st is None or not st.get("lines"):
        return "f10"
    placed = st.get("left") == g.left and st.get("bottom") == g.bottom
    if not placed:
        if st.get("padlock") is None:
            return "unknown"
        if st["padlock"] == "locked":
            return "unlock"
        if st.get("input") != "open":
            return "open_input"
        return "drag"
    if st["lines"] != g.lines:
        return "f10"
    if lock and st.get("padlock") != "locked":
        return "unknown" if st.get("padlock") is None else "lock"
    return None


# --- templates (local client pixels) --------------------------------------------------------------


def load_templates(path: Path = TEMPLATES) -> dict[str, Any] | None:
    if not path.exists():
        return None
    z = np.load(path)
    return {"open": z["open"], "locked": z["locked"], "mask": z["mask"].astype(bool)}


def _client(png: Path) -> np.ndarray:
    from PIL import Image

    a = np.asarray(Image.open(png).convert("RGB"))
    if a.shape[:2] == (720, 1280):
        return a
    sys.path.insert(0, str(ROOT / "scripts"))
    import ro_agent as r

    x0, y0, w, h = r.game_region()
    return a[y0 : y0 + h, x0 : x0 + w]


def cut_padlock(open_png: Path, locked_png: Path, out: Path = TEMPLATES) -> dict[str, Any]:
    """Design time: the two padlock crops (grey) and the union of their icon pixels, each from a
    frame where ``find`` sees the window (the pointer parked away from the icon row)."""
    crops = {}
    for k, png in (("open", open_png), ("locked", locked_png)):
        img = _client(png)
        st = find(img)
        if not st or not st["lines"]:
            raise SystemExit(f"{png}: no chat window found")
        crops[k] = _padlock_crop(img, st["left"], st["text_top"])
    mask = icon_mask(crops["open"]) | icon_mask(crops["locked"])
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out, open=luma(crops["open"]), locked=luma(crops["locked"]), mask=mask)
    tm = load_templates(out)
    assert tm is not None
    return {"out": str(out), "mask_px": int(mask.sum()),
            "cross": {k: padlock_distances(_client(p), find(_client(p)) or {}, tm)
                      for k, p in (("open", open_png), ("locked", locked_png))}}  # fmt: skip


# --- live ----------------------------------------------------------------------------------------


class ChatWindowError(RuntimeError):
    pass


def _grab_rgb(screen: Any) -> np.ndarray:
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
    agent.move(x0 + u + 6, y0 + v + 4)  # from the RIGHT: the "-" (delete tab) is left of it
    time.sleep(0.25)
    agent.move(x0 + u, y0 + v)
    time.sleep(0.4)
    agent.click(x0 + u, y0 + v)
    time.sleep(0.6)


def _drag(agent: Any, st: Mapping[str, Any], g: Geometry) -> None:
    import ro_agent as r

    x0, y0, _, _ = r.game_region()
    u, v = Geometry(st["lines"], st["bottom"], st["left"]).input_px
    tu, tv = g.input_px
    agent.move(x0 + u + 6, y0 + v + 2)  # two motions onto the bar before the press
    time.sleep(0.25)
    agent.move(x0 + u, y0 + v)
    time.sleep(0.4)
    agent.drag(x0 + u, y0 + v, x0 + tu, y0 + tv, steps=16)
    time.sleep(0.8)


def check(screen: Any) -> dict[str, Any] | None:
    """Read only (no input): the window as the screen shows it now."""
    return read(_grab_rgb(screen), load_templates())


def _backend() -> str:
    """The capture lock's display path ("rdp" / "console" / ...), read as gm_state reads it."""
    import record_session

    return str(record_session.read_lock(ROOT / "state").backend)


def _key(step: str, st: Mapping[str, Any] | None) -> tuple[Any, ...]:
    """What a step must change: the same step on the same window means it had no effect."""
    if st is None:
        return (step, None)
    return (step, *(st.get(k) for k in ("left", "bottom", "lines", "input", "padlock")))


def ensure(agent: Any, screen: Any, *, why: str, g: Geometry | None = None, lock: bool = True,
           max_steps: int = 14) -> dict[str, Any]:  # fmt: skip
    """Reach the standard through the client's own controls, one verified step at a time. Fast
    path: one read and no input when the window is already standard. Raises ChatWindowError on
    an unreadable state or a step without effect (with a saved frame); never presses Enter
    except through the UI gate."""
    g = g or active()
    tm = load_templates()
    if tm is None:
        raise ChatWindowError(f"no padlock templates ({TEMPLATES}): run `chat_window.py "
                              "cut-padlock` first")  # fmt: skip
    st = read(_grab_rgb(screen), tm)
    if is_standard(st, g, lock):
        return {"standard": True, "steps": [], "state": st, "why": why}
    backend = _backend()
    if backend != "rdp":  # measured on RDP only: no fixing input on a path not proven
        raise ChatWindowError(f"chat window not standard ({st}) and the display path is "
                              f"{backend!r}: its reader is proven on rdp only; "
                              "nothing done")  # fmt: skip
    _park(agent)  # the pointer off the icon row and the bar, then judge again
    steps: list[str] = []
    f10s = 0
    last: tuple[Any, ...] | None = None
    for _ in range(max_steps):
        st = read(_grab_rgb(screen), tm)
        step = next_step(st, g, lock)
        if step is None:
            if steps:
                import ro_agent as r

                r.log(f"chat window: standard after {steps} ({why})")
            return {"standard": True, "steps": steps, "state": st, "why": why}
        key = _key(step, st)
        if step == "unknown" or (key == last and step != "f10"):
            shot = _shot(screen, "unreadable" if step == "unknown" else "no-effect")
            raise ChatWindowError(f"chat window: {step!r} at {st} after {steps} (frame {shot})")
        last = key
        if step == "f10":
            f10s += 1
            if f10s > len(SIZES) + 3:
                shot = _shot(screen, "f10-cycle")
                raise ChatWindowError(f"chat window: {f10s} F10 presses without the standard "
                                      f"size ({st}; frame {shot})")  # fmt: skip
            import ro_agent as r

            r.activate_client(agent, screen)
            agent.keys("F10")
            time.sleep(0.9)
        elif step in ("unlock", "lock"):
            assert st is not None
            _ui_click(agent, *Geometry(st["lines"], st["bottom"], st["left"]).padlock_px)
            _park(agent)
        elif step == "open_input":
            import ro_agent as r
            import ui_gate

            ui_gate.ensure_clear(agent, screen, why=f"chat_window:{why}")
            r.activate_client(agent, screen)
            agent.keys("Enter")  # the input is CLOSED here (the bar is not drawn): Enter opens it
            time.sleep(1.0)
        elif step == "drag":
            assert st is not None
            _drag(agent, st, g)
            _park(agent)
        steps.append(step)
    shot = _shot(screen, "steps")
    raise ChatWindowError(f"chat window not standard after {max_steps} steps: {steps} ({st}; "
                          f"frame {shot})")  # fmt: skip


def _shot(screen: Any, tag: str) -> str:
    import ro_agent as r

    path = SHOTS / f"{time.strftime('%Y%m%d-%H%M%S')}-{tag}.png"
    r.to_png(screen.full(), path)
    return str(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("read")
    e = sub.add_parser("ensure")
    e.add_argument("--why", default="cli")
    e.add_argument("--no-lock", action="store_true")
    c = sub.add_parser("cut-padlock")
    c.add_argument("open_png", type=Path)
    c.add_argument("locked_png", type=Path)
    a = ap.parse_args()
    if a.cmd == "cut-padlock":
        print(json.dumps(cut_padlock(a.open_png, a.locked_png)))
        return 0
    sys.path.insert(0, str(ROOT / "scripts"))
    import ro_agent as r

    if a.cmd == "read":
        st = read(_grab_rgb(r.Screen()), load_templates())
        print(json.dumps({"state": st, "standard": is_standard(st)}))
        return 0
    with r.session("rule:chat-window") as (agent, screen):
        print(json.dumps(ensure(agent, screen, why=a.why, lock=not a.no_lock), default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
