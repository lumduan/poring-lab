#!/usr/bin/env python3
"""talk@1 (docs/demonstrations.md 3.30): talk to an NPC, choose a menu option BY ITS TEXT, close
the dialog.

    talk1.py pilot --scene prt_church|prontera [--n 3]     Step 0: never scored (its own seeds)
    talk1.py run   --scene prt_church|prontera [--n 50]    the scored run (3.30's seeds)
    options: --walk walk15|walk16 (3.29's READY version; default walk15), --contact-fix where|none

One trial (3.30):
  1. @warp to a seeded start cell 4-8 cells (Chebyshev) from the target: GAT-walkable, every other
     L3 NPC of the map >= 3 cells away. prt_church alternates Garnet / Henson; prontera: the guide.
  2. APPROACH with the READY walk rule (its route, its gates, its NPC clearance and substitutes):
     the goal is a seeded walkable cell 2-3 cells from the NPC, on our side (nearer the start than
     the NPC is), reachable from the start, never next to another L3 NPC.
  3. CONTACT, one click: the NPC's projected L3 cell and up its sprite (0, -14, -28 px), clicked
     only where the cursor reads TALK twice (cursor_gate.gated_click: TALK is the ONLY allowed
     shape of this one click). Before it, one /where fix (where@2) re-places the projection
     (--contact-fix none: the route's belief).
  4. The DIALOG by T2 (poring_env.npc_dialog) on STABLE frames (two fresh frames agree, the
     cursor parked away from the windows): NEXT -> click it; a MENU -> 5; CLOSE -> click it.
  5. CHOOSE BY TEXT (T3, poring_env.menu_text): the visible lines are read, the list is scrolled to
     its top and then to its bottom and the reads merged into the WHOLE list, which must equal one
     of the NPC's L3 menus (count, order, every line). The intended option (the trial's seeded one
     at the first menu, the end option at the next) is scrolled into view, read again on the
     current frame, clicked; OK only when the highlight is then on that line and it still reads
     so. Anything else is a safe decline: Cancel ("menu unread"), and a clean close if the server
     shows CLOSE.
  6. The runtime check: both windows gone on two consecutive stable frames.
L3 (the NPCs' cells and menus) is read at run time from data/kb/bindings/lab-rathena.json (local,
never committed). Packets are never read here (rule 1): talk1_score.py judges the session offline.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import random
import signal
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType
from typing import Any, Protocol

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_agent as r  # noqa: E402

from poring_env import menu_text as mt  # noqa: E402
from poring_env import npc_dialog as nd  # noqa: E402

RULE = "talk@1"
S = 1_000_000_000
Cell = tuple[int, int]
L3_PATH = r.ROOT / "data/kb/bindings/lab-rathena.json"
TEMPLATES = r.ROOT / nd.TEMPLATE_DIR
GLYPHS = r.ROOT / mt.DEFAULT_GLYPHS

BUDGET_S = 120.0  # 3.30: contact click -> close
OPEN_S = 6.0  # the dialog must open within this of the contact click
STEP_WAIT_S = 5.0  # a dialog with no button (the server's answer pending) at most this long
CHANGE_S = 3.0  # after a click, the window must change within this
GONE_S = 6.0  # the runtime check's window
STABLE_TRIES = 8
MAX_SCROLL = 12
MAX_UNREAD = 8  # consecutive unreadable observations before the trial gives up
MAX_IDLE_NEXT = 3  # NEXT clicks in a row that changed nothing: the dialog is stuck
CONTACT_POINTS = (0.0, -14.0, -28.0)  # 3.30 step 3 (the monster positive case's points)
TALK = "talk"
START_CELLS = (4, 8)
GOAL_CELLS = (2, 3)
OTHER_NPC_APART = 3
PARK = ((1250, 380), (1250, 300))  # the cursor's rest points (walk6's), right of the dialog
UI_PAD = 12.0


@dataclass(frozen=True, slots=True)
class Target:
    """A talk@1 target (3.30's table): found in L3 by map and cell; ``first``: the 1-based menu
    positions a trial may pick first (information options only; the end option is the last)."""

    key: str
    map: str
    cell: Cell
    menu_len: int
    first: tuple[int, ...]


TARGETS = {
    "garnet": Target("garnet", "prt_church", (103, 76), 7, (1, 2, 3, 4, 5, 6)),
    "henson": Target("henson", "prt_church", (103, 71), 8, (1, 2, 3, 4, 5, 6, 7)),
    # the guide's first option opens a mini-map submenu with a yes / no: never picked (3.30)
    "guide": Target("guide", "prontera", (154, 187), 4, (2, 3)),
}
SCENES: dict[str, tuple[tuple[str, ...], int]] = {
    "prt_church": (("garnet", "henson"), 20261130),  # alternate, seed 20261130 (3.30)
    "prontera": (("guide",), 20261131),
}
PILOT_SEEDS = {"prt_church": 20261132, "prontera": 20261133}  # step 0 only: fresh seeds


# --- L3 and the trial plan (pure) ---------------------------------------------------------------


def l3_target(l3: dict[str, Any], t: Target) -> dict[str, Any]:
    """The target's L3 name, cell and menus. SystemExit when L3 disagrees with 3.30's table."""
    at = [p for p in l3["npc"]["positions"]["npcs"]
          if p["map"] == t.map and (int(p["x"]), int(p["y"])) == t.cell]  # fmt: skip
    if len(at) != 1:
        raise SystemExit(f"L3: {len(at)} NPCs on {t.map} {t.cell} (want one): regenerate L3")
    name = str(at[0]["name"])
    menus = [list(m["options"]) for m in l3["npc"]["menus"]["by_npc"].get(name, [])]
    if not menus or len(menus[0]) != t.menu_len:
        raise SystemExit(f"L3: {t.key}'s first menu is not {t.menu_len} options (3.30)")
    for pos in (*t.first, t.menu_len):
        if mt.visible_text(menus[0][pos - 1]) in (None, ""):
            raise SystemExit(f"L3: {t.key}'s option {pos} is coloured or empty: never a target")
    others = [(int(p["x"]), int(p["y"])) for p in l3["npc"]["positions"]["npcs"]
              if p["map"] == t.map and (int(p["x"]), int(p["y"])) != t.cell]  # fmt: skip
    return {"name": name, "cell": t.cell, "map": t.map, "menus": menus, "others": others}


def cheb(a: Sequence[int], b: Sequence[int]) -> int:
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])))


def _walk(walkable: Any, c: Cell) -> bool:
    h, w = walkable.shape
    return 0 <= c[1] < h and 0 <= c[0] < w and bool(walkable[c[1], c[0]])


def start_cells(walkable: Any, npc: Cell, others: Sequence[Cell]) -> list[Cell]:
    """Walkable cells 4-8 from the NPC (Chebyshev), every other NPC >= 3 away; sorted."""
    lo, hi = START_CELLS
    return [(x, y) for y in range(npc[1] - hi, npc[1] + hi + 1)
            for x in range(npc[0] - hi, npc[0] + hi + 1)
            if lo <= cheb((x, y), npc) <= hi and _walk(walkable, (x, y))
            and all(cheb((x, y), o) >= OTHER_NPC_APART for o in others)]  # fmt: skip


def goal_cells(walkable: Any, npc: Cell, start: Cell, others: Sequence[Cell],
               reachable: Callable[[Cell, Cell], bool]) -> list[Cell]:  # fmt: skip
    """Walkable cells 2-3 from the NPC on our side (nearer the start than the NPC is), never next
    to another NPC, reachable from the start; sorted."""
    lo, hi = GOAL_CELLS
    d_npc = math.dist(npc, start)
    return [(x, y) for y in range(npc[1] - hi, npc[1] + hi + 1)
            for x in range(npc[0] - hi, npc[0] + hi + 1)
            if lo <= cheb((x, y), npc) <= hi and _walk(walkable, (x, y))
            and math.dist((x, y), start) < d_npc
            and all(cheb((x, y), o) > 1 for o in others) and reachable(start, (x, y))]  # fmt: skip


def plan_trials(scene: str, n: int, seed: int, info: dict[str, dict[str, Any]], walkable: Any,
                reachable: Callable[[Cell, Cell], bool]) -> list[dict[str, Any]]:  # fmt: skip
    """The seeded trials: target (alternating), start, goal and the first option's position.
    ``info``: l3_target() per target key of the scene."""
    keys, _ = SCENES[scene]
    rng = random.Random(seed)
    out: list[dict[str, Any]] = []
    for k in range(n):
        key = keys[k % len(keys)]
        t, inf = TARGETS[key], info[key]
        starts = start_cells(walkable, t.cell, inf["others"])
        if not starts:
            raise SystemExit(f"no start cell for {key}")
        start: Cell | None = None
        goals: list[Cell] = []
        for _ in range(100):
            start = rng.choice(starts)
            goals = goal_cells(walkable, t.cell, start, inf["others"], reachable)
            if goals:
                break
        if start is None or not goals:
            raise SystemExit(f"no goal cell for {key}")
        goal = rng.choice(goals)
        first = rng.choice(t.first)
        menu = inf["menus"][0]
        out.append({
            "k": k, "scene": scene, "target": key, "npc": inf["name"], "map": t.map,
            "npc_cell": list(t.cell), "start": list(start), "goal": list(goal),
            "first_position": first, "l3_options": list(menu),
            "intended": [menu[first - 1], menu[t.menu_len - 1]],
        })  # fmt: skip
    return out


# --- the dialog, by T2 and T3 (pure over an Io; the live Io is below) ---------------------------


class Io(Protocol):
    """What the dialog logic needs of the client: a fresh frame's T2 state (the cursor parked
    away), one UI click inside a window, a digest of the dialog's text, the clock."""

    def observe(self) -> tuple[nd.NpcUiState, Any]: ...

    def click(self, x: int, y: int, what: str, inside: nd.Box) -> int: ...

    def digest(self, frame: Any, state: nd.NpcUiState) -> str: ...

    def now(self) -> int: ...

    def wait(self, seconds: float) -> None: ...


ReadMenu = Callable[[Any, nd.MenuView], mt.MenuSnapshot]


@dataclass(frozen=True)
class Seen:
    state: nd.NpcUiState
    frame: Any
    snap: mt.MenuSnapshot | None
    digest: str

    def key(self) -> tuple[Any, ...]:
        lines = None if self.snap is None else tuple(ln.key for ln in self.snap.lines)
        return (self.state.signature(), self.digest, lines)


def menu_reader(glyphs: mt.MenuGlyphs) -> ReadMenu:
    def read(frame: Any, menu: nd.MenuView) -> mt.MenuSnapshot:
        lines = tuple(mt.read_row(np.ascontiguousarray(frame[y : y + h, x : x + w, :3]), glyphs)
                      for x, y, w, h in menu.rows)  # fmt: skip
        return mt.MenuSnapshot(lines, menu.can_scroll_up, menu.can_scroll_down)

    return read


def observe_stable(io: Io, read_menu: ReadMenu, tries: int = STABLE_TRIES) -> Seen:
    """A state two consecutive fresh frames agree on (windows, button, highlight, scrollbar, the
    dialog text and every menu line); a not-ok "unstable" state otherwise."""

    def look() -> Seen:
        st, frame = io.observe()
        snap = read_menu(frame, st.menu) if st.ok and st.menu is not None else None
        return Seen(st, frame, snap, io.digest(frame, st) if st.ok else "")

    prev = look()
    for _ in range(tries):
        cur = look()
        if prev.state.ok and cur.state.ok and prev.key() == cur.key():
            return cur
        prev = cur
        io.wait(0.1)
    reason = prev.state.reason if not prev.state.ok else "unstable"
    return Seen(nd.NpcUiState(False, reason, 0.0), prev.frame, None, "")


def wait_change(io: Io, read_menu: ReadMenu, before: Seen,
                timeout: float = CHANGE_S) -> Seen | None:  # fmt: skip
    """The first stable state that differs from ``before``; None if none within ``timeout``."""
    end = io.now() + int(timeout * S)
    while io.now() < end:
        cur = observe_stable(io, read_menu)
        if cur.state.ok and cur.key() != before.key():
            return cur
        io.wait(0.1)
    return None


def _point(box: nd.Box) -> tuple[int, int]:
    return nd.centre(box)


def _row_point(box: nd.Box) -> tuple[int, int]:
    """Inside a row's text part: its first 60 px (the start of any option), its middle row."""
    x, y, w, h = box
    return x + min(40, w // 2), y + h // 2


@dataclass
class DialogPlan:
    intended: tuple[str, str]  # the first menu's seeded option, then the end option
    menus: list[list[str]]  # the NPC's L3 menus


@dataclass
class DialogLog:
    steps: list[dict[str, Any]] = field(default_factory=list)
    reads: list[dict[str, Any]] = field(default_factory=list)
    choices: list[dict[str, Any]] = field(default_factory=list)
    outcome: str | None = None
    declined: dict[str, Any] | None = None
    close_click: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"steps": self.steps, "reads": self.reads, "choices": self.choices,
                "outcome": self.outcome, "declined": self.declined,
                "close_click": self.close_click}  # fmt: skip


def click(io: Io, log: DialogLog, xy: tuple[int, int], what: str, inside: nd.Box) -> int:
    t = io.click(xy[0], xy[1], what, inside)
    log.steps.append({"click": what, "at": list(xy), "t": t})
    return t


def decline(io: Io, read_menu: ReadMenu, seen: Seen, why: str, log: DialogLog) -> str:
    """3.30's safe decline: the menu's Cancel (by image), only on a menu read with certainty."""
    log.declined = {"why": why, "t": None}
    if seen.state.ok and seen.state.menu is not None:
        m = seen.state.menu
        log.declined["t"] = click(io, log, _point(m.cancel_rect), "cancel", m.rect)
        wait_change(io, read_menu, seen)
    return "declined"


def scroll(io: Io, read_menu: ReadMenu, seen: Seen, way: str, log: DialogLog) -> Seen | None:
    """One click on a scroll arrow; the new stable menu (it must have changed), else None."""
    m = seen.state.menu
    if m is None or not m.scrollbar:
        return None
    box = m.up_rect if way == "up" else m.down_rect
    click(io, log, _point(box), f"scroll_{way}", m.rect)
    cur = wait_change(io, read_menu, seen)
    if cur is None or not cur.state.ok or cur.state.menu is None or cur.snap is None:
        return None
    return cur


def choose(io: Io, read_menu: ReadMenu, seen: Seen, plan: DialogPlan, stage: int,
           log: DialogLog) -> str:  # fmt: skip
    """3.30 step 5 on a menu: "chosen" or "declined"."""
    if stage >= 2:
        return decline(io, read_menu, seen, "an unexpected third menu", log)
    target = plan.intended[stage]
    want = mt.visible_text(target)
    assert seen.snap is not None
    snaps = [seen.snap]
    scrolls = 0
    while snaps[0].can_scroll_up and scrolls < MAX_SCROLL:  # the list's top first
        got = scroll(io, read_menu, seen, "up", log)
        if got is None or got.snap is None:
            return decline(io, read_menu, seen, "menu unread: scroll", log)
        seen, snaps, scrolls = got, [got.snap], scrolls + 1
    while snaps[-1].can_scroll_down and scrolls < MAX_SCROLL:
        got = scroll(io, read_menu, seen, "down", log)
        if got is None or got.snap is None:
            return decline(io, read_menu, seen, "menu unread: scroll", log)
        seen = got
        snaps.append(got.snap)
        scrolls += 1
    full = mt.accumulate(snaps)
    rec: dict[str, Any] = {"stage": stage, "list": full.reason, "lines": len(full.keys),
                           "snapshots": len(snaps),
                           "refused": [ln.reason for ln in (full.lines or ())
                                       if ln.key is None]}  # fmt: skip
    log.reads.append(rec)
    checks = [mt.cross_check(full, menu) for menu in plan.menus]
    fit = [i for i, c in enumerate(checks) if c.ok]
    rec["l3_fit"] = fit
    if len(fit) != 1:
        why = "menu unread" if full.reason != "ok" else "menu differs from L3"
        return decline(io, read_menu, seen, why, log)
    menu, cross = plan.menus[fit[0]], checks[fit[0]]
    if target not in menu:
        return decline(io, read_menu, seen, "the intended option is not in this menu", log)
    idx = mt.line_of(full, target)
    if idx is None or full.tops == ():
        return decline(io, read_menu, seen, "menu unread: the intended line", log)
    rows = len(seen.snap.lines) if seen.snap is not None else 4
    top = full.tops[-1]
    while not top <= idx < top + rows:
        got = scroll(io, read_menu, seen, "up" if idx < top else "down", log)
        scrolls += 1
        if got is None or got.snap is None or scrolls > 2 * MAX_SCROLL:
            return decline(io, read_menu, seen, "menu unread: scroll to the line", log)
        seen = got
        aligned = mt.align(got.snap, full)
        if aligned is None:
            return decline(io, read_menu, seen, "menu unread: lost the list", log)
        top = aligned
    row = idx - top
    assert seen.snap is not None and seen.state.menu is not None
    if seen.snap.lines[row].key != want:
        return decline(io, read_menu, seen, "menu unread: the line now", log)
    for attempt in range(2):
        m = seen.state.menu
        assert m is not None
        click(io, log, _row_point(m.rows[row]), f"row_{row}", m.rect)
        after = observe_stable(io, read_menu)
        st = after.state
        if st.ok and st.menu is None:  # the row click chose by itself (never by guess: logged)
            log.choices.append({"stage": stage, "line": idx, "row": row,
                                "packet_index": cross.packet_index[idx], "t_ok": None,
                                "by_row_click": True})  # fmt: skip
            return "chosen"
        if (st.ok and st.menu is not None and after.snap is not None
                and st.menu.highlight_row == row and mt.align(after.snap, full) == top
                and after.snap.lines[row].key == want):  # fmt: skip
            t_ok = click(io, log, _point(st.menu.ok_rect), "ok", st.menu.rect)
            log.choices.append({"stage": stage, "line": idx, "row": row,
                                "packet_index": cross.packet_index[idx], "t_ok": t_ok,
                                "attempt": attempt})  # fmt: skip
            wait_change(io, read_menu, after)
            return "chosen"
        if not (st.ok and st.menu is not None and after.snap is not None):
            break
        seen = after
    return decline(io, read_menu, seen, "the highlight is not on the line", log)


def dialog_loop(io: Io, read_menu: ReadMenu, plan: DialogPlan, t_click: int,
                budget_s: float = BUDGET_S) -> DialogLog:  # fmt: skip
    """3.30 steps 4-6 after the contact click. The outcome is None when the dialog was closed by
    our CLOSE click after both choices; else the failure (or safe decline) it ended with."""
    log = DialogLog()
    end = t_click + int(budget_s * S)
    opened = None
    while io.now() < t_click + int(OPEN_S * S):
        seen = observe_stable(io, read_menu)
        if seen.state.ok and (seen.state.dialog is not None or seen.state.menu is not None):
            opened = seen
            break
        io.wait(0.2)
    if opened is None:
        log.outcome = "no dialog"
        return log
    stage, unread, idle_next = 0, 0, 0
    last_key, last_change = opened.key(), io.now()
    while True:
        if io.now() >= end:
            log.outcome = log.outcome or "timeout"
            return log
        seen = observe_stable(io, read_menu)
        st = seen.state
        if not st.ok:
            unread += 1
            log.steps.append({"unread": st.reason, "t": io.now()})
            if unread >= MAX_UNREAD:
                log.outcome = log.outcome or "dialog unread"
                return log
            io.wait(0.2)
            continue
        unread = 0
        if seen.key() != last_key:
            last_key, last_change = seen.key(), io.now()
        if st.menu is not None:
            if seen.snap is None:
                io.wait(0.2)
                continue
            if log.declined is not None:  # the Cancel did not take: never click again
                log.outcome = log.outcome or "menu unread"
                return log
            if choose(io, read_menu, seen, plan, stage, log) == "chosen":
                stage += 1
            else:
                log.outcome = "menu unread"
            continue
        if st.dialog is not None:
            d = st.dialog
            if d.button == "next":
                click(io, log, _point(d.button_rect), "next", d.rect)
                idle_next = 0 if wait_change(io, read_menu, seen) is not None else idle_next + 1
                if idle_next >= MAX_IDLE_NEXT:
                    log.outcome = log.outcome or "dialog stuck"
                    return log
                continue
            if d.button == "close":
                log.close_click = click(io, log, _point(d.button_rect), "close", d.rect)
                if stage < 2 and log.outcome is None:
                    log.outcome = "closed before both choices"
                return log
            if io.now() - last_change > int(STEP_WAIT_S * S):
                log.outcome = log.outcome or "dialog stuck"
                return log
            io.wait(0.2)
            continue
        log.outcome = log.outcome or "dialog vanished"  # gone without our CLOSE
        return log


def runtime_gone(io: Io, read_menu: ReadMenu, timeout: float = GONE_S) -> dict[str, Any]:
    """3.30 step 6: both windows gone on two consecutive stable observations."""
    end = io.now() + int(timeout * S)
    streak, seen_states = 0, []
    while io.now() < end:
        cur = observe_stable(io, read_menu)
        seen_states.append(cur.state.reason if not cur.state.ok else
                           "gone" if cur.state.gone else "open")  # fmt: skip
        streak = streak + 1 if cur.state.gone else 0
        if streak >= 2:
            return {"closed": True, "observations": seen_states}
        io.wait(0.1)
    return {"closed": False, "observations": seen_states}


# --- the live parts -----------------------------------------------------------------------------


def in_ui(u: float, v: float, pad: float = UI_PAD) -> bool:
    import route_preview

    return any(x0 - pad <= u <= x1 + pad and y0 - pad <= v <= y1 + pad
               for x0, y0, x1, y1 in route_preview.UI_WINDOWS)  # fmt: skip


class LiveIo:
    """The client through ro_agent: frames decoded after the last action, the cursor parked away
    from the windows before a frame is judged (two motions: the client draws its cursor only where
    a second motion leaves it), and THE one UI click of talk@1 (test_click_census.py)."""

    def __init__(self, agent: Any, screen: Any, templates: nd.DialogTemplates) -> None:
        self.agent, self.screen, self.t = agent, screen, templates
        self.last_action: int | None = None
        self.parked = False
        self.hints: dict[str, tuple[int, int]] = {}
        self.park_k = 0

    def park(self) -> None:
        gx, gy, _, _ = r.game_region()
        pu, pv = PARK[self.park_k % 2]
        self.park_k += 1
        self.agent.move(gx + pu - 3, gy + pv - 3)
        time.sleep(0.05)
        self.agent.move(gx + pu, gy + pv)
        time.sleep(0.6)
        self.parked = True

    def observe(self) -> tuple[nd.NpcUiState, Any]:
        if not self.parked:
            self.park()
        frame = r.grab_after(self.screen, r.game_region(), self.last_action)[..., :3]
        frame = np.ascontiguousarray(frame)
        st = nd.state(frame, self.t, self.hints)
        for f in st.finds:
            if f.origin is not None:
                self.hints[f.name] = f.origin
        return st, frame

    def click(self, x: int, y: int, what: str, inside: nd.Box) -> int:
        bx, by, bw, bh = inside
        if not (bx <= x < bx + bw and by <= y < by + bh):
            raise r.Stop(f"talk@1: a {what} click at {x},{y} outside its window {inside}")
        gx, gy, _, _ = r.game_region()
        self.agent.move(gx + x - 3, gy + y - 3)
        time.sleep(0.05)
        self.agent.move(gx + x, gy + y)
        time.sleep(0.15)
        t = r.ns()
        self.agent.click(gx + x, gy + y)  # a UI click: inside a window T2 read on a stable frame
        self.last_action = t
        self.parked = False
        return t

    def digest(self, frame: Any, state: nd.NpcUiState) -> str:
        if state.dialog is None:
            return "-"
        x0, y0, _, _ = state.dialog.rect
        dx, dy, w, h = self.t.geometry.dialog_text
        ink = np.asarray(frame[y0 + dy : y0 + dy + h, x0 + dx : x0 + dx + w, :3]).max(axis=-1) < 100
        return hashlib.sha1(np.packbits(ink).tobytes()).hexdigest()[:12]

    def now(self) -> int:
        return r.ns()

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)


def load_l3() -> dict[str, Any]:
    if not L3_PATH.exists():
        raise SystemExit(f"{L3_PATH} missing: kb_route.py + kb_bindings.py (T1, local)")
    return dict(json.loads(L3_PATH.read_text()))


def load_readers(info: dict[str, dict[str, Any]]) -> tuple[nd.DialogTemplates, mt.MenuGlyphs]:
    """T2 and T3's locally cut templates; SystemExit when any is missing or cannot read a target
    menu's characters."""
    if not (TEMPLATES / nd.PARAMS_FILE).exists() or not GLYPHS.exists():
        raise SystemExit("T2 / T3 templates missing: talk_calibrate.py cut (design time)")
    t = nd.load_templates(TEMPLATES)
    missing = [*t.missing, *([] if nd.CLOSE in t.images else [nd.CLOSE])]
    if missing:
        raise SystemExit(f"T2 templates missing: {missing}")
    g = mt.load_menu_glyphs(GLYPHS)
    texts = [o for inf in info.values() for m in inf["menus"][:1] for o in m]
    lacking = g.missing(texts)
    if lacking:
        raise SystemExit(f"T3 glyphs lack {len(lacking)} characters of the target menus")
    return t, g


@dataclass
class Rig:
    agent: Any
    screen: Any
    walk: Any  # walk15 / walk16 (its route function, unchanged)
    pr: Any
    camera: Any
    gat: Any
    w: Any
    band: Any
    seg_max: int
    noentry: Any
    relocalise: Any
    read_position: Any
    where_templates: Any
    io: LiveIo
    read_menu: ReadMenu
    contact_fix: str


def rig_up(agent: Any, screen: Any, mapname: str, walk_name: str, templates: nd.DialogTemplates,
           glyphs: mt.MenuGlyphs, contact_fix: str) -> Rig:  # fmt: skip
    import rule_run as rr
    import unit_detector
    import walk5 as w5
    import walk6 as w6
    import walk11 as w11
    import walk15 as w15
    import where_fix as wf

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_env import selfpos

    walk = importlib.import_module(walk_name)
    gat = gatmod.parse((cam.GAT_DIR / f"{mapname}.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    base = cam.camera_from_json(cj["camera"])
    indoor = mapname in cam.load_indoor_table()
    camera = (cam.camera_for_map(base, True, cj["indoor"]["yaw_deg"], cj["indoor"]["distance"])
              if indoor else base)  # fmt: skip
    w11.UNITS["detector"] = unit_detector.UnitDetector()  # fails closed: no detector, no run
    w11.UNITS["ms_per_cell"] = w11.map_ms_per_cell(mapname)
    w11.UNITS["memory"] = w15.NpcClearMemory()  # walk@15's memory (walk@16 runs it too)
    digits = selfpos.load_digit_templates()

    def read_position() -> tuple[int, int] | None:
        xy = selfpos.read_minimap_xy(screen.grab(*r.game_region())[1][:, :, :3], digits)
        return None if xy is None else (int(xy[0]), int(xy[1]))

    where_t = wf.load_templates(wf.TEMPLATES_V2)
    return Rig(
        agent, screen, walk, w11.Prober9(agent, screen, w6.CursorRefs.load(w11.CURSOR_REFS_V2)),
        camera, gat, w5.World(camera, gat, (0, 0)), rr.ec_band(),
        w11.SEG_INDOOR if indoor else w11.SEG_OPEN, np.load(w5.NOENTRY_MASK),
        walk.where_relocalise(where_t), read_position, where_t, LiveIo(agent, screen, templates),
        menu_reader(glyphs), contact_fix,
    )  # fmt: skip


def contact(rig: Rig, npc: Cell, trial: dict[str, Any]) -> int | None:
    """3.30 step 3: the ONE TALK-gated click (cursor_gate: TALK read twice, no motion between)."""
    import cursor_gate

    u, v = (float(c) for c in rig.w.project([npc])[0])
    tries: list[dict[str, Any]] = []
    trial["contact"] = {"belief": list(rig.w.position), "at": [round(u, 1), round(v, 1)],
                        "tries": tries}  # fmt: skip
    for dv in CONTACT_POINTS:
        if in_ui(u, v + dv):
            tries.append({"dv": dv, "skip": "ui"})
            continue
        got = cursor_gate.gated_click(rig.pr, u, v + dv, allow=(TALK,))
        tries.append({"dv": dv, **{k: got.get(k) for k in ("clicked", "why", "shape")}})
        if got["clicked"]:
            rig.io.last_action = int(got["t_click"])
            rig.io.parked = False
            return int(got["t_click"])
    return None


def run_trial(rig: Rig, plan: dict[str, Any], first_on_map: bool, info: dict[str, Any],
              log_seg: Callable[..., None]) -> dict[str, Any]:  # fmt: skip
    import bench
    import rule_run as rr
    import walk11 as w11
    import where_fix as wf

    trial: dict[str, Any] = {k: plan[k] for k in ("k", "scene", "target", "npc", "npc_cell",
                                                   "start", "goal", "first_position",
                                                   "l3_options", "intended")}  # fmt: skip
    trial.update(t_start=r.ns(), t_contact_click=None, runtime={"closed": False})
    agent, screen = rig.agent, rig.screen
    pre = runtime_gone(rig.io, rig.read_menu, timeout=4.0)
    if not pre["closed"]:
        raise r.Stop(f"talk@1 trial {plan['k']}: an NPC window is open at the start "
                     f"({pre['observations'][-3:]}): stopped, never clicked blind")  # fmt: skip
    sx, sy = plan["start"]
    r.gm(agent, screen, f"@warp {plan['map']} {sx} {sy}")
    time.sleep(rr.SCENE_ENTRY_S if first_on_map else rr.WARP_SETTLE_S)
    bench.close_chat(agent, screen)
    r.activate_client(agent, screen)
    rig.w.position = (sx, sy)
    w11.UNITS["memory"].reset()  # a warp: the remembered cells belong to the old spot
    pos = rig.read_position()
    start_fix = None
    if pos is not None:
        rig.w.position = pos
    else:
        start_fix = rig.relocalise(agent, screen, rig.w, rig.noentry, rig.band)
    goal = (int(plan["goal"][0]), int(plan["goal"][1]))
    did = rig.walk.walk_route(
        rig.pr, rig.w, goal, rig.band, rig.seg_max, log_seg, rig.noentry, rig.read_position,
        relocalise=rig.relocalise, label=f"talk@1 {plan['scene']} trial {plan['k']}",
        expect_goal=rig.walk.WALK, fixed_at_start=bool(start_fix and start_fix.get("ok")),
    )  # fmt: skip
    trial["approach"] = {
        "start_fix": start_fix, "arrived": bool(did.get("arrived_belief")),
        "decline": did.get("decline"), "end_believed": list(rig.w.position),
        **{k: did.get(k) for k in ("clicks", "covered", "relocs", "replans", "sides",
                                   "substitute", "npc_substitute", "waited_s")},
    }  # fmt: skip
    if not did.get("arrived_belief"):
        trial["t_end"] = r.ns()
        trial["result_runtime"] = "approach"
        return trial
    if rig.contact_fix == "where":
        got = wf.fix_v2(agent, screen, rig.where_templates, rig.w.position, rig.w.walkable)
        trial["contact_fix"] = {"xy": got["xy"], "rejects": got["rejects"]}
        if got["xy"] is not None:
            rig.w.position = tuple(got["xy"])
        bench.close_chat(agent, screen)
        r.activate_client(agent, screen)
    t_click = contact(rig, tuple(plan["npc_cell"]), trial)  # type: ignore[arg-type]
    trial["t_contact_click"] = t_click
    if t_click is None:
        trial["t_end"] = r.ns()
        trial["result_runtime"] = "contact"
        return trial
    dplan = DialogPlan((plan["intended"][0], plan["intended"][1]), info["menus"])
    log = dialog_loop(rig.io, rig.read_menu, dplan, t_click)
    trial["dialog"] = log.as_dict()
    trial["runtime"] = runtime_gone(rig.io, rig.read_menu)
    trial["t_end"] = r.ns()
    trial["result_runtime"] = log.outcome or ("closed" if trial["runtime"]["closed"] else
                                              "not gone")  # fmt: skip
    return trial


def _terminate(signum: int, frame: FrameType | None) -> None:
    raise KeyboardInterrupt(f"signal {signal.Signals(signum).name}")


def run(mode: str, scene: str, n: int, seed: int, walk_name: str, contact_fix: str) -> int:
    import bench
    import operator_hud
    import record_session
    import route_plan
    import walk6 as w6
    import walk11 as w11
    import walk12 as w12

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_dataset.walk import walk_path
    from poring_env.demo import DemoLog, new_session_id

    l3 = load_l3()
    keys, _ = SCENES[scene]
    info = {k: l3_target(l3, TARGETS[k]) for k in keys}
    templates, glyphs = load_readers(info)
    mapname = TARGETS[keys[0]].map
    gat = gatmod.parse((cam.GAT_DIR / f"{mapname}.gat").read_bytes())
    walkable = gat.walkable()

    def reachable(a: Cell, b: Cell) -> bool:
        return walk_path(w6.Grid(walkable, set()), a[0], a[1], b[0], b[1], max_len=48) is not None

    plans = plan_trials(scene, n, seed, info, walkable, reachable)
    sid = new_session_id(f"talk1-{mode}-{scene}")
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena", rule=RULE,
              account="gm", mode=mode, scene=scene, map=mapname, n=n, seed=seed, walk=walk_name,
              contact_fix=contact_fix, budget_s=BUDGET_S, contact_points=list(CONTACT_POINTS),
              t2=templates.meta, t3=glyphs.meta)  # fmt: skip
    print(json.dumps({"session": sid, "rule": RULE, "mode": mode, "scene": scene, "n": n,
                      "seed": seed, "walk": walk_name}), flush=True)  # fmt: skip
    t_first = r.ns()
    trials: list[dict[str, Any]] = []
    ended, code, why = "complete", 0, ""
    plan_tok = route_plan.enable(f"{RULE}-{scene}-{seed}", mapname)
    hud = operator_hud.enable(f"{RULE} {scene}")
    try:
        with r.session(f"rule:{RULE}") as (agent, screen):
            rig = rig_up(agent, screen, mapname, walk_name, templates, glyphs, contact_fix)
            try:
                for k, plan in enumerate(plans):
                    segs: list[dict[str, Any]] = []

                    def log_seg(t_click: int, frm: Cell, end: Cell, step: dict[str, Any],
                                segs: list[dict[str, Any]] = segs) -> None:  # fmt: skip
                        if step.get("clicked"):
                            segs.append({"t": t_click, "from": list(frm), "end": list(end),
                                         "outcome": step.get("outcome")})  # fmt: skip

                    trial = run_trial(rig, plan, k == 0, info[plan["target"]], log_seg)
                    trial["walk_clicks"] = segs
                    trials.append(trial)
                    print(json.dumps({x: trial.get(x) for x in
                                      ("k", "target", "first_position", "result_runtime")}
                                     | {"closed": trial["runtime"].get("closed")}),
                          flush=True)  # fmt: skip
            finally:
                bench.close_chat(agent, screen)
                det = w11.UNITS.get("detector")
                if det is not None:  # rig_up may have failed before it loaded one
                    det.close()
    except BaseException as exc:  # noqa: BLE001 -- every way out finishes the session
        ended, code, why = w12.ended_by(exc)
    finally:
        route_plan.disable(plan_tok)
        operator_hud.disable(hud)
        (log.dir / "trials.json").write_text(json.dumps(trials, default=str))
        packets: dict[str, Any]
        try:
            events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
            packets = {"packet_events": len(events), "packet_anchor": anchor}
        except Exception as exc:  # noqa: BLE001 -- the end is written whatever the packets do
            packets = {"packets_error": f"{type(exc).__name__}: {exc}"[:300]}
        log.finish(trials=len(trials), ended=ended, reason=why[:300], exit_code=code, **packets)
    print(json.dumps({"session": sid, "trials": len(trials), "ended": ended, "reason": why[:300],
                      "dir": str(log.dir)}), flush=True)  # fmt: skip
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("mode", choices=("pilot", "run"))
    ap.add_argument("--scene", choices=sorted(SCENES), required=True)
    ap.add_argument("--n", type=int)
    ap.add_argument("--seed", type=int, help="default: 3.30's (run) / the pilot's own (pilot)")
    ap.add_argument("--walk", choices=("walk15", "walk16"), default="walk15")
    ap.add_argument("--contact-fix", choices=("where", "none"), default="where")
    a = ap.parse_args()
    n = a.n if a.n is not None else (3 if a.mode == "pilot" else 50)
    seed = a.seed if a.seed is not None else (
        PILOT_SEEDS[a.scene] if a.mode == "pilot" else SCENES[a.scene][1])  # fmt: skip
    signal.signal(signal.SIGTERM, _terminate)
    return run(a.mode, a.scene, n, seed, a.walk, a.contact_fix)


if __name__ == "__main__":
    sys.exit(main())
