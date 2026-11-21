#!/usr/bin/env python3
"""The agent's operator tool for the lab's rAthena client: log in, create a character, recover a
black client, run GM validation queries and short measurement moves. There is NO play loop.

Rules it enforces (CLAUDE.md, ADR-0002/0006):
  * input only through the backend's /internal/agent (source=bot), so every event passes the mux;
  * refuses unless the mux is in ASSIST (Batt sets it); waits while a human lease is active; a
    /flows Run may also play in BOT (PORING_INPUT_MODES, Batt 2026-11-18; ADR-0020 Amendment
    2026-11-18), never in HUMAN;
    stops at once (exit 3) on any refusal -- it never fights the human;
  * credentials come from .env and are typed as SENSITIVE batches (the input log keeps only counts
    and timing); they are never printed, logged or passed on a command line;
  * before typing: the target must be verified in front -- the client by its active title bar,
    a dialog by its signature, a PowerShell console by its tab template; secrets are re-verified
    every 4 characters, and the keyboard layout must be ENG (tray signature);
  * in-game input only while OUR rAthena shows the account online=1;
  * no Run-dialog commands (Defender's ClickFix detection, 2026-10-01): the client is launched
    from the desktop shortcut and closed with Alt+F4; it touches PoringLab.exe only (the
    community-server client is never touched).

    ro_agent.py status
    ro_agent.py shot NAME                       full screen -> /dev/shm/.../shots/NAME.png
    ro_agent.py calibrate STATE [DX DY W H]     save STATE's signature (box: client-relative)
    ro_agent.py where                           best-matching calibrated state
    ro_agent.py click DX DY [--right] [--abs]   client-area-relative click (GAME_REGION origin)
    ro_agent.py drag X1 Y1 X2 Y2 [--right] [--abs]  paced press-move-release (RO camera: --right)
    ro_agent.py open-terminal                   the agent's own NON-elevated "poring-lab shell"
    ro_agent.py calibrate-shell                 once: its tab template + the shortcut's signature
    ro_agent.py calibrate-shell --stream        the same tab, cut from the console stream's frames
    ro_agent.py close-extra-shells              ONE "poring-lab shell" window (others get WM_CLOSE)
    ro_agent.py minimize-consoles               Win+Down each visible console (before the client)
    ro_agent.py watch-status                    the lab-client watcher task: state + log tail (crop)
    ro_agent.py file-check "C:\\path"           BEFORE asking Batt for a file drop: size, time and
                                                sha256 on Windows + his ready Copy-Item line
    ro_agent.py keys CODE...                    key taps (50 ms holds)
    ro_agent.py chord CODE...                   press in order, release in reverse
    ro_agent.py type TEXT                       US-layout ASCII into the focused field (+ \\n)
    ro_agent.py login player|gm                 login screen -> character in game, online=1
    ro_agent.py create-char player|gm           on an empty char-select slot (name from .env)
    ro_agent.py gm "@where"                     GM account only; logged to data/ro_agent/gm.jsonl
    ro_agent.py say [--thai-keys] TEXT          chat line (Thai: Kedmanee key positions)
    ro_agent.py close | launch | recover [player|gm] [--retries N] [--agent-id ID]
                                                (guarded_build runs `recover gm --retries 0
                                                --agent-id auto_recover` after a sniffer restart)

Coordinates: GAME_REGION (.env, "x,y,w,h") is the client area; clicks are relative to its origin
(the same region the backend's black-screen detector watches).
"""

import argparse
import contextlib
import json
import os
import random
import re
import struct
import subprocess
import sys
import threading
import time
import weakref
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from websockets.sync.client import ClientConnection, connect

from poring_backend.capture_lock import read_lock, read_window
from poring_backend.signature import SIG_MATCH, grey_thumb
from poring_backend.signature import find as sig_find

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_env  # noqa: E402  (a sibling, stdlib only: this copy's compose project names)

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "data" / "ro_agent"  # gitignored (rule 4): signatures + GM command log
SHOTS = Path("/dev/shm/poring-lab-tmp/shots")
LAB_STATE = ROOT / "state"  # the capture-backend lock + the interlock window, read FRESH
BACKEND = lab_env.container("backend")
DB = lab_env.container("db")
HOLD_S = 0.05  # 50 ms holds: 20 ms registers 6/6 in the client (docs/client/rathena-client.md)
# A chord's steps, paced: one instantaneous batch (down,down,up,up) is ignored by the client --
# Alt+F4 first (2026-10-01), then Alt+E/Q/S in game (2026-10-05, Batt). 60 ms closed it at once.
CHORD_STEP_S = 0.06
SHORTCUT_BOX = (80, 106, 64, 84)  # the "Ragnarok Offline" desktop icon + label
CLIENT = r"C:\RO-rAthena\client"
EXE = "PoringLab"  # the rAthena copy ONLY (ADR-0006: the community client is never touched)


# Client PROFILES (2026-10-05, the Thai-data experiment): which client copy, desktop shortcut,
# accounts and database. `kro` is the lab client and its rathena (everything as before); `th` is
# C:\RO-rAthena-th (the same exe + the Thai data.grf) and rathena-th/db-th, ONE AT A TIME with
# rathena. Picked by --profile or $RO_PROFILE. Signatures cut on the th client are `@thdata`
# variants of the same states (a state matches if any of its variants does).
@dataclass(frozen=True)
class Profile:
    name: str
    client: str
    db: str
    account_prefix: str  # <prefix>_AGENT_USER / _GM_USER / ... in .env
    shortcut_env: str  # "x,y" of the profile's desktop shortcut in .env
    variant: str | None  # the signature variant cut on this client
    removed: str | None = None  # why this profile's client copy no longer exists (refused)


PROFILES = {
    "kro": Profile("kro", CLIENT, DB, "RATHENA", "RO_SHORTCUT", None),
    # INTENTIONALLY INERT since 2026-10-06 (ADR-0019, Batt: "the Thai-data decision is final"):
    # the copy and its shortcut were removed from the Dell, so its shortcut position now points
    # at nothing (or at whatever icon moves there). rathena-th stays a stopped server-side option.
    "th": Profile("th", r"C:\RO-rAthena-th\client", lab_env.container("db-th"), "RATHENA_TH",
                  "RO_SHORTCUT_TH", "thdata",
                  removed="its client copy C:\\RO-rAthena-th and its desktop shortcut were "
                          "REMOVED from the Dell on 2026-10-06 (ADR-0019; the Thai-data decision "
                          "is final). Recreate the copy, its AssistAddr override, its firewall "
                          "rule and its shortcut, then clear `removed`, before using --profile th"),
}  # fmt: skip
PROFILE = PROFILES["kro"]


def use_profile(name: str | None) -> Profile:
    """Select the client profile for this process (default: $RO_PROFILE, else kro)."""
    global PROFILE, DB
    key = name or os.environ.get("RO_PROFILE") or "kro"
    if key not in PROFILES:
        raise Stop(f"unknown client profile {key!r} (known: {', '.join(sorted(PROFILES))})")
    if PROFILES[key].removed:
        raise Stop(f"client profile {key!r} is unavailable: {PROFILES[key].removed}")
    PROFILE = PROFILES[key]
    DB = PROFILE.db
    return PROFILE


# One matcher for this tool and the backend's typing-only foreground gate (2026-10-06):
# poring_backend.signature (SIG_SCALE 8; SIG_MATCH 6.0 -- true matches 0-2, near misses ~10).

SHIFTED = {
    "!": "Digit1", "@": "Digit2", "#": "Digit3", "$": "Digit4", "%": "Digit5", "^": "Digit6",
    "&": "Digit7", "*": "Digit8", "(": "Digit9", ")": "Digit0", "_": "Minus", "+": "Equal",
    "{": "BracketLeft", "}": "BracketRight", "|": "Backslash", ":": "Semicolon", '"': "Quote",
    "<": "Comma", ">": "Period", "?": "Slash", "~": "Backquote",
}  # fmt: skip
PLAIN = {
    " ": "Space", "-": "Minus", "=": "Equal", "[": "BracketLeft", "]": "BracketRight",
    "\\": "Backslash", ";": "Semicolon", "'": "Quote", ",": "Comma", ".": "Period", "/": "Slash",
    "`": "Backquote", "\n": "Enter", "\t": "Tab",
}  # fmt: skip


class Stop(SystemExit):
    """A refusal, a wrong screen or a failed check: stop, report, never retry against a human."""


use_profile(None)  # $RO_PROFILE also applies when another script imports this module


def ns() -> int:
    return time.monotonic_ns()


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", file=sys.stderr, flush=True)


# --- .env (never printed) -------------------------------------------------------------------------


def env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def account(which: str) -> tuple[str, str, str]:
    e = env()
    prefix = f"{PROFILE.account_prefix}_" + {"player": "AGENT", "gm": "GM"}[which]
    user, pw, char = e.get(f"{prefix}_USER"), e.get(f"{prefix}_PASSWORD"), e.get(f"{prefix}_CHAR")
    if not (user and pw and char):
        raise Stop(f"{prefix}_USER/_PASSWORD/_CHAR missing in .env")
    return user, pw, char


def real_game_region() -> tuple[int, int, int, int]:
    """The client's REAL area in desktop pixels (.env GAME_REGION). A replaced ``game_region``
    (a test's fixed client, a caller's) IS the client: it is returned as is."""
    replaced = globals().get("game_region")
    if replaced is not None and replaced is not _VIRTUAL_AWARE_GAME_REGION:
        region: tuple[int, int, int, int] = replaced()
        return region
    raw = env().get("GAME_REGION", "")
    if not raw:
        raise Stop("GAME_REGION is not set in .env (the client area, x,y,w,h)")
    x, y, w, h = (int(v) for v in raw.split(","))
    return x, y, w, h


# Phase 2 (docs/planning/fullscreen-client.md section 7): a client that is not 1280x720 is seen
# through the VIRTUAL 1280x720 client -- everything built on 1280x720 (the runner, its readers,
# the detector) runs unchanged. It lives at a far origin, never a desktop pixel, so a point there
# is known to be virtual: grabs there return the virtual frame, pointer positions there are mapped
# to the screen by the view's vectors (poring_env.clientview).
VIRTUAL_X0 = 100_000
# The lab's interface panels in the virtual client, measured 2026-11-18 at 1920x1080: Basic Info,
# the hotbars and the chat window stay at their SAVED pixels; the minimap sticks to the top-right.
LAB_PANELS: tuple[tuple[str, tuple[int, int, int, int], str], ...] = (
    ("basic_info", (0, 0, 230, 150), "saved"),
    ("hotbar", (226, 0, 300, 40), "saved"),
    ("hotbar2", (744, 0, 90, 36), "saved"),
    ("chat", (0, 578, 600, 142), "saved"),
    ("minimap", (1130, 10, 150, 160), "tr"),
)
# The pointer is drawn at its own size wherever it is (not scaled with the world): its area
# around the hotspot is pasted unscaled at the virtual pointer position.
# ➡️ 2026-11-19 (Batt's clips: "the cursor was a hand when it scanned, but it did not click"): the
# box was the WALK arrow's (-12, -12, 48, 56). The other shapes reach further from the hotspot --
# measured on the v3 references' supports: pickup hand x -18..+11, y -15..+8; sword x -20..+28,
# y -21..+31; warp x -32..+31 -- so the hand lost its left and top edge to the shrunk world and
# its colour recall stayed under cursor_sword.PICKUP_MIN (0.80-0.82 on his client; 145 of its
# 207 missed pixels were in the cut-off zone): no loot click at all. The box is now the cursor
# readers' whole 64 x 64 crop plus their +-2 px shift search, centred on the hotspot.
CURSOR_BOX = (-34, -34, 68, 68)
_POINTER: tuple[float, float] | None = None  # the last virtual pointer position sent

# The interface windows, FOUND by their shape (teaching-prerun.md 4f, fullscreen-client.md
# milestone 3; Batt 2026-11-19: "make it work with every client ... we know what RO's main UI looks
# like: start from that"). Basic Info and the hotbar by poring_env.panelfind's rules, the chat
# window by chat_window.find_any (any size, any width); each one found is moved, in the virtual
# client, to its
# LAB_PANELS place, so the readers built at the lab's places read any layout. A window not found
# keeps the lab's place (its reads then fail, in words); the minimap keeps the top-right corner
# (RO never moves it); hotbar2 keeps its saved place.
PANELS_FILE = lab_env.shm("tmp") / "panels.json"  # the last find, for this copy's processes
PANELS_ENV = "PORING_PANELS_FILE"  # another file (the tests: each its own)
# xmas02-items-1080.md T-I5 (2026-11-20; the 1080 clear-bag "slot 0 did not drop twice"): the
# INVENTORY is a panel while it is open. RO draws it 1:1 at the same client pixels at any screen
# size (the lab's home (0, 120), gm_state.INV_SLOT1's window); in the virtual picture it was part of
# the scaled world, so its slots read the wrong pixels and a drag from one started elsewhere. It is
# found by bag_count's oval lattice at its home in the REAL frame, at most every INV_CHECK_S, and
# is a panel only while found (a closed bag's place stays the world). Its size is the found
# window's: 7 columns x its rows, read from the pixels (bag_count.rows_at; a player drags it taller,
# Batt's live bag 7 x 9, 2026-11-21).
INV_HOME = (0, 120)
VIRTUAL_W_PX, VIRTUAL_H_PX = 1280, 720  # the virtual client (poring_env.clientview's VIRTUAL_W/H)
INV_CHECK_S = 0.5  # the drop opens the bag, waits 1.0 s, then reads it
_INV: dict[str, Any] = {"origin": None, "size": None, "t": -1e9, "prompt": None}
# ... and the drop's QUANTITY PROMPT (its OK button, gm_state.PROMPT_OK_BOX at 720), which RO draws
# native-size near the screen's centre: at 1920x1080 its OK button is at (964, 462), i.e. the 720
# box + (320, 150) (measured 2026-11-20, template distance 0.0). x is the centring, (w - 1280) / 2;
# y is not half the height, so it is SEARCHED +- PROMPT_SEARCH px around the expected place, only
# while the bag is open, and is a panel only while its OK button matches.
PROMPT_Y_PER_PX = 150 / 360  # the measured y offset per pixel of height over 720
PROMPT_SEARCH = 40
PANELS_TTL_S = 120.0  # another process's find is used this long, for the same client region
PANEL_CHECK_S = 2.0  # a run re-checks each found window at its place this often (< 1 ms)
PANEL_SEARCH_S = 15.0  # and searches again at most this often when one moved or is missing
# 2026-11-19: a window still missing after a search is searched for half as often each time, up to
# this (Batt's hotbar was never found: a 1.7 s search every 15 s on this host's CPU); a found
# window that moved is still searched for at PANEL_SEARCH_S. Every search after the first runs
# in a BACKGROUND thread, never inside a grab (a grab waits for a fresh frame within 1.5 s).
PANEL_SEARCH_MAX_S = 120.0
PANEL_SEARCH_SYNC_ENV = "PORING_PANEL_SEARCH_SYNC"  # "1": search inside the tick (the tests)
# where each finder's origin sits in the lab's virtual client (measured 2026-11-19 on the lab's
# 1280x720 and 1920x1080 frames: the finders return exactly these there)
LAB_WINDOW_ORIGINS = {"basic_info": (0, 0), "hotbar": (230, 0)}
CHAT_LAB_BOTTOM = 719  # LAB_PANELS' chat box: six lines, its bottom row at 719
CHAT_LAB_TEXT_TOP = 598  # and its top border's row (its tabs above it: the box starts at 578)
_PANELS: dict[str, Any] = {}  # this process's last find (find_panels), its checks' clocks
_PANELS_FILE_CACHE: list[Any] = [0.0, None]  # (when read, the file's state)
_PANELS_LOCK = threading.Lock()


def _lab_box(name: str) -> tuple[int, int, int, int]:
    return next(box for n, box, _ in LAB_PANELS if n == name)


def panel_places(basic: Any, hotbar: Any, chat: Mapping[str, Any] | None) -> dict[str, Any]:
    """PURE: each window found -> its panel {"virtual": box, "real_xy", "origin", ...} -- the lab
    box moved by the found window's vector from its lab place. A chat window of another size or
    width (Batt 2026-11-19: "support many lines; do not limit the width") gets its OWN box, its
    bottom-left on the lab's (the readers count its lines up from the bottom)."""
    out: dict[str, Any] = {}
    for name, f in (("basic_info", basic), ("hotbar", hotbar)):
        if f is None:
            continue
        box = _lab_box(name)
        lx, ly = LAB_WINDOW_ORIGINS[name]
        ox, oy = f.origin
        out[name] = {"virtual": list(box), "real_xy": [box[0] + ox - lx, box[1] + oy - ly],
                     "origin": [ox, oy], "score": [f.score, f.of]}  # fmt: skip
        if getattr(f, "pitch", None) is not None:  # the hotbar's slot pitch (the lab's: 29)
            out[name]["pitch"] = int(f.pitch)
    if chat and chat.get("lines") and chat.get("bottom") is not None:
        import chat_window as cw

        bx, by, bw, bh = _lab_box("chat")
        left, top, bottom = int(chat["left"]), int(chat["text_top"]), int(chat["bottom"])
        right = int(chat.get("right", left + cw.BORDER_X))
        ww = right - left + (bw - cw.BORDER_X)  # the lab: 596 + 4 = 600
        hh = bottom - top + (bh - (CHAT_LAB_BOTTOM - CHAT_LAB_TEXT_TOP))  # the lab: 121 + 21
        out["chat"] = {"virtual": [bx, CHAT_LAB_BOTTOM + 1 - hh, ww, hh],
                       "real_xy": [bx + left, bottom + 1 - hh], "origin": [left, top],
                       "right": right, "bottom": bottom,
                       "lines": int(chat["lines"])}  # fmt: skip
    return out


def _default_xy(name: str, box: tuple[int, int, int, int], how: str,
                size: tuple[int, int]) -> tuple[int, int]:  # fmt: skip
    from poring_env.clientview import Panel

    return Panel.anchored(name, box, "tr", size).real_xy if how == "tr" else (box[0], box[1])


def panels_moved(found: Mapping[str, Any], size: tuple[int, int]) -> bool:
    """PURE: a found window sits off its lab place (then even a 1280x720 client is virtual)."""
    for name, box, how in LAB_PANELS:
        f = found.get(name)
        if f is not None and (tuple(f["real_xy"]) != _default_xy(name, box, how, size)
                              or tuple(f["virtual"]) != box):  # fmt: skip
            return True
    return False


def panels_file() -> Path:
    return Path(os.environ.get(PANELS_ENV) or PANELS_FILE)


def _panel_state() -> dict[str, Any]:
    """The windows found for THIS client region: this process's find, else another process's
    (PANELS_FILE, at most PANELS_TTL_S old), else {} (the lab's places)."""
    try:
        region = list(real_game_region())
    except (Stop, OSError, ValueError):
        return {}
    with _PANELS_LOCK:
        if _PANELS.get("region") == region:
            return _PANELS
    now = time.monotonic()
    if now - float(_PANELS_FILE_CACHE[0]) > 1.0:
        try:
            got = json.loads(panels_file().read_text())
        except (OSError, ValueError):
            got = None
        _PANELS_FILE_CACHE[0], _PANELS_FILE_CACHE[1] = now, got
    got = _PANELS_FILE_CACHE[1]
    if (isinstance(got, dict) and got.get("region") == region
            and time.time() - float(got.get("t_wall") or 0) <= PANELS_TTL_S):  # fmt: skip
        return got
    return {}


def find_panels(screen: Any = None, real: Any = None) -> dict[str, Any]:
    """Find the windows on the REAL client (a fresh grab of ``screen``, or the frame ``real``):
    this process's state, and PANELS_FILE for the others. Pixels only; nothing is kept but the
    numbers."""
    import chat_window as cw

    from poring_env import panelfind as pf

    region = real_game_region()
    if real is None:
        real = screen.grab_meta(*region)[1]
    bgr = np.ascontiguousarray(np.asarray(real)[..., :3])
    lum = pf.luma(bgr)
    basic, hotbar = pf.find_basic_info(lum), pf.find_hotbar(lum)
    # the chat window is searched OUTSIDE the windows already found (chat_window.find_any's
    # ``avoid``, 2026-11-20): over a bright scene the hotbar's edge reads as a 1-line chat window
    avoid = [(x, y, x + bw, y + bh) for f in panel_places(basic, hotbar, None).values()
             for (x, y), (_, _, bw, bh) in [(f["real_xy"], f["virtual"])]]  # fmt: skip
    found = panel_places(basic, hotbar, cw.find_any(bgr[..., ::-1], avoid))
    size = (region[2], region[3])
    st = {"v": 1, "region": list(region), "t_wall": time.time(), "found": found,
          "moved": panels_moved(found, size),
          "missing": [n for n in ("basic_info", "hotbar", "chat") if n not in found]}  # fmt: skip
    now = time.monotonic()
    with _PANELS_LOCK:
        before = dict(_PANELS) if _PANELS.get("region") == list(region) else {}
        # a search that finds no window the last one missed is one more miss (the backoff)
        new = set(found) - set(before.get("found") or {})
        misses = int(before.get("misses") or 0) + 1 if before and st["missing"] and not new else 0
        _PANELS.clear()
        _PANELS.update(st, checked=now, searched=now, misses=misses)
    try:
        f = panels_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f".{f.name}.{os.getpid()}")
        tmp.write_text(json.dumps(st) + "\n")
        os.replace(tmp, f)
    except OSError:
        pass  # this process still has its own state
    return st


def _panel_still_there(name: str, f: Mapping[str, Any], lum: Any, rgb: Any) -> bool:
    """A cheap re-check of one found window at its place (no search)."""
    from poring_env import panelfind as pf

    ox, oy = f["origin"]
    if name == "basic_info":
        return pf.basic_info_at(lum, (ox, oy)) >= pf.BASIC_MIN_ROWS
    if name == "hotbar":
        return pf.hotbar_at(lum, (ox, oy), int(f.get("pitch") or 29)) >= pf.HOTBAR_MIN_AT
    import chat_window as cw

    y0, y1 = max(0, oy - 2), int(f["bottom"]) + 1
    x0, x1 = max(0, ox), int(f.get("right", ox + cw.BORDER_X)) + 5
    got = cw.find_any(rgb[y0:y1, x0:x1])
    return bool(got and got.get("lines") == f.get("lines") and got.get("bottom") == y1 - 1 - y0
                and got.get("left") == ox - x0)  # fmt: skip


def _panels_tick(real: Any) -> None:
    """In the virtual grab path: the first frame finds the windows; then each found window is
    re-checked at its place every PANEL_CHECK_S, and a moved or missing one is searched for again
    at most every PANEL_SEARCH_S (a player may drag a window mid-run)."""
    try:
        region = list(real_game_region())
    except (Stop, OSError, ValueError):
        return
    now = time.monotonic()
    with _PANELS_LOCK:
        st = dict(_PANELS) if _PANELS.get("region") == region else None
    if st is None:
        find_panels(real=real)
        return
    if now - float(st.get("checked") or 0) < PANEL_CHECK_S:
        return
    with _PANELS_LOCK:
        _PANELS["checked"] = now
    from poring_env import panelfind as pf

    bgr = np.ascontiguousarray(np.asarray(real)[..., :3])
    lum, rgb = pf.luma(bgr), bgr[..., ::-1]
    gone = [n for n, f in (st.get("found") or {}).items() if not _panel_still_there(n, f, lum, rgb)]
    since = now - float(st.get("searched") or 0)
    if (gone and since >= PANEL_SEARCH_S) or (st.get("missing") and since >= missing_wait(st)):
        _search_again(real)


def inventory_tick(screen: Any, now: float | None = None, *, force: bool = False) -> bool:
    """T-I5: is the bag open at its home (bag_count.rows_at on the REAL pixels around it)? At most
    every INV_CHECK_S; the answer (and the window's size, by its rows) is kept for client_view (the
    inventory panel). A small real grab (the tallest window and a margin), so the virtual grab path
    stays cheap. ``force``: look now, whatever
    the last look's age -- before a click into the bag (gm_state._tab; xmas02-items-1080.md
    Amendment 9: a tab click sent before any grab saw the bag open went to the WORLD)."""
    import bag_count as bc

    t = time.monotonic() if now is None else now
    with _PANELS_LOCK:
        if not force and t - float(_INV["t"]) < INV_CHECK_S:
            return _INV["origin"] is not None
        _INV["t"] = t
    try:
        rx, ry, rw, rh = real_game_region()
        bx, by, bw, bh = bc.bag_box(INV_HOME, bc.ROWS_MAX)  # its rows are read, not assumed
        x0, y0 = max(0, bx), max(0, by)
        w, h = min(bw - (x0 - bx), rw - x0), min(bh - (y0 - by), rh - y0)
        _, sub, _, _ = screen.grab_meta(rx + x0, ry + y0, w, h)
        bgr = np.ascontiguousarray(np.asarray(sub)[..., :3])
        rows = bc.rows_at(bgr, (INV_HOME[0] - x0, INV_HOME[1] - y0))
        open_ = rows is not None
        size = bc.window_size(rows) if rows is not None else None
        prompt = _prompt_ok_at(screen, (rx, ry, rw, rh)) if open_ else None
    except (Stop, OSError, ValueError):
        open_, size, prompt = False, None, None
    with _PANELS_LOCK:
        _INV["origin"] = INV_HOME if open_ else None
        _INV["size"] = size
        _INV["prompt"] = prompt
    return open_


def _prompt_ok_at(screen: Any, region: tuple[int, int, int, int]) -> tuple[int, int] | None:
    """T-I5: the quantity prompt's OK button on the REAL client (client px), or None: its template
    (gm_state's prompt_ok.npy) searched around its expected place for this client size."""
    import gm_state as gs

    rx, ry, rw, rh = region
    bx, by, bw, bh = gs.PROMPT_OK_BOX
    ex = bx + (rw - VIRTUAL_W_PX) // 2
    ey = by + round((rh - VIRTUAL_H_PX) * PROMPT_Y_PER_PX)
    x0, y0 = max(0, ex - PROMPT_SEARCH), max(0, ey - PROMPT_SEARCH)
    w = min(bw + 2 * PROMPT_SEARCH, rw - x0)
    h = min(bh + 2 * PROMPT_SEARCH, rh - y0)
    if w < bw or h < bh:
        return None
    _, sub, _, _ = screen.grab_meta(rx + x0, ry + y0, w, h)
    g = gs.to_gray(np.ascontiguousarray(np.asarray(sub)[..., :3]))
    ref = np.load(gs.LOOT_DIR / "prompt_ok.npy")
    win = np.lib.stride_tricks.sliding_window_view(g, (bh, bw))
    d = np.abs(win - ref).mean(axis=(2, 3))
    iy, ix = np.unravel_index(int(np.argmin(d)), d.shape)
    if float(d[iy, ix]) > gs.PROMPT_MATCH:
        return None
    return x0 + int(ix), y0 + int(iy)


def _panels_due() -> bool:
    """_panels_tick would look at the windows now (the first frame, or PANEL_CHECK_S since the
    last check): that read needs the whole real frame; any other virtual read needs only its box."""
    try:
        region = list(real_game_region())
    except (Stop, OSError, ValueError):
        return False
    with _PANELS_LOCK:
        st = dict(_PANELS) if _PANELS.get("region") == region else None
    return st is None or time.monotonic() - float(st.get("checked") or 0) >= PANEL_CHECK_S


def missing_wait(st: Mapping[str, Any]) -> float:
    """PURE: how long a window still missing waits for its next search (doubling per miss)."""
    return min(PANEL_SEARCH_S * 2.0 ** int(st.get("misses") or 0), PANEL_SEARCH_MAX_S)


_SEARCH: list[threading.Thread | None] = [None]


def _search_again(real: Any) -> None:
    """A search after the first: in a background thread (one at a time), so the grab that
    noticed it returns at once; PORING_PANEL_SEARCH_SYNC=1 searches here (the tests)."""
    if os.environ.get(PANEL_SEARCH_SYNC_ENV) == "1":
        find_panels(real=real)
        return
    th = _SEARCH[0]
    if th is not None and th.is_alive():
        return
    frame = np.array(real, copy=True)

    def work() -> None:
        with contextlib.suppress(Exception):  # a failed search keeps the last state
            find_panels(real=frame)

    th = threading.Thread(target=work, name="panel-search", daemon=True)
    _SEARCH[0] = th
    th.start()


def panels_words(st: Mapping[str, Any] | None = None) -> list[str]:
    """The windows as the Run's log says them (numbers and places only)."""
    st = _panel_state() if st is None else st
    if not st:
        return ["the windows: not looked for yet (the lab's places are assumed)"]
    found = st.get("found") or {}
    try:
        size = tuple(st["region"][2:4])
    except (KeyError, TypeError):
        size = (1280, 720)
    names = {"basic_info": "Basic Info", "hotbar": "the hotbar", "chat": "the chat window"}
    out = []
    for name, label in names.items():
        f = found.get(name)
        if f is None:
            out.append(f"{label} NOT found (closed, collapsed or covered): the lab's place is "
                       "assumed, so what it shows cannot be read")  # fmt: skip
            continue
        box, how = _lab_box(name), next(h for n, _, h in LAB_PANELS if n == name)
        at_lab = (tuple(f["real_xy"]) == _default_xy(name, box, how, size)  # type: ignore[arg-type]
                  and tuple(f["virtual"]) == box)  # fmt: skip
        ox, oy = f["origin"]
        where = (f"left {ox}, bottom {f['bottom']}, {f['lines']} lines, "
                 f"{int(f.get('right', ox + 596)) - ox + 1} px wide" if name == "chat"
                 else f"({ox}, {oy})")  # fmt: skip
        score = f" ({f['score'][0]} of {f['score'][1]} of its shape's cues)" if "score" in f else ""
        placed = "the lab's place" if at_lab else "moved to the lab's place in the bot's view"
        out.append(f"{label} found at {where}{score}: {placed}")
    out.append("the minimap: the top-right corner (RO keeps it there)")
    return out


def client_view() -> Any:
    """The view of the real client: the identity at 1280x720; otherwise the world scaled by the
    client's height / 720 about its centre (measured), the lab's panels, the pointer's picture."""
    from poring_env.clientview import VIRTUAL_H, VIRTUAL_W, ClientView, Panel

    x, y, w, h = real_game_region()
    st = _panel_state()
    found = st.get("found") or {}
    if (w, h) == (VIRTUAL_W, VIRTUAL_H) and not st.get("moved"):
        return ClientView((x, y, w, h))
    mode = "fullscreen" if (x, y) == (0, 0) and (w, h) == desktop() else "window"
    panels = [Panel(name, tuple(found[name]["virtual"]), tuple(found[name]["real_xy"]))
              if name in found else
              Panel.anchored(name, box, "tr", (w, h)) if how == "tr" else
              Panel(name, box, (box[0], box[1])) for name, box, how in LAB_PANELS]  # fmt: skip
    with _PANELS_LOCK:
        inv, size, prompt = _INV["origin"], _INV.get("size"), _INV.get("prompt")
    if inv is not None and size is not None:  # T-I5: the open inventory, 1:1 at its home
        panels.append(Panel("inventory", (INV_HOME[0], INV_HOME[1], *size),
                            (int(inv[0]), int(inv[1]))))  # fmt: skip
    if prompt is not None:  # and the drop's quantity prompt's OK button, 1:1 at its 720 place
        import gm_state as gs

        panels.append(Panel("prompt", gs.PROMPT_OK_BOX, (int(prompt[0]), int(prompt[1]))))
    base = ClientView((x, y, w, h), mode, h / VIRTUAL_H, None, tuple(panels))
    if _POINTER is not None and base.panel_at(*_POINTER) is None:  # over the world
        vx, vy = _POINTER
        cx, cy = base.to_client(vx, vy)
        dx, dy, bw, bh = CURSOR_BOX
        panels.append(Panel("cursor", (round(vx) + dx, round(vy) + dy, bw, bh),
                            (round(cx) + dx, round(cy) + dy)))  # fmt: skip
    return ClientView((x, y, w, h), mode, h / VIRTUAL_H, None, tuple(panels))


def virtual_active() -> bool:
    """The real client is not 1280x720, or a window of it was found off its lab place
    (teaching-prerun.md 4f): the code built on 1280x720 sees the virtual client."""
    try:
        _, _, w, h = real_game_region()
    except (Stop, OSError):
        return False
    return (w, h) != (1280, 720) or bool(_panel_state().get("moved"))


def game_region() -> tuple[int, int, int, int]:
    """The client area the bot's code works in: the real one at 1280x720, else the virtual
    1280x720 client at VIRTUAL_X0 (grabs and pointer positions there are mapped)."""
    if virtual_active():
        return VIRTUAL_X0, 0, 1280, 720
    return real_game_region()


_VIRTUAL_AWARE_GAME_REGION = game_region


def real_xy(x: float, y: float) -> tuple[int, int]:
    """A pointer position -> desktop pixels: a virtual one by the view's vectors, else as is."""
    global _POINTER
    if x >= VIRTUAL_X0:
        _POINTER = (x - VIRTUAL_X0, y)
        fx, fy = client_view().to_real(x - VIRTUAL_X0, y)
        return int(round(fx)), int(round(fy))
    return int(x), int(y)


# --- database checks (read-only; credentials via stdin, never argv) -------------------------------


def db_query(sql: str) -> list[list[str]]:
    script = (
        'MYSQL_PWD="$MARIADB_PASSWORD" exec mariadb -u"$MARIADB_USER" -N -B "$MARIADB_DATABASE"'
    )
    out = subprocess.run(
        ["docker", "exec", "-i", DB, "sh", "-c", script],
        input=sql, capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return [line.split("\t") for line in out.splitlines() if line]


def sql_str(value: str) -> str:
    if not value.replace("_", "").isalnum():
        raise Stop("unexpected characters in an account value")
    return f"'{value}'"


def online_chars(which: str) -> list[str]:
    user = account(which)[0]
    rows = db_query(
        "SELECT c.name FROM `char` c JOIN login l ON l.account_id = c.account_id "
        f"WHERE l.userid = {sql_str(user)} AND c.online = 1;"
    )
    return [r[0] for r in rows]


def any_online() -> int:
    return int(db_query("SELECT COUNT(*) FROM `char` WHERE online = 1;")[0][0])


# --- screen (a persistent grab helper inside the backend container: same X, same clock) -----------

# Console mode with a LIVE S2 writer (V3b): the frame bus, not X -- the same decoded frames the
# console and the bot see, stamped with the writer's decode time; X would show the never-painted
# input window (black). Anything else: X, as always. ONE rule: poring_backend.grabsource.
_HELPER = r"""
import struct, sys
import numpy as np
from poring_backend.grabsource import GrabSource
src = GrabSource()
out = sys.stdout.buffer
for line in sys.stdin:
    x, y, w, h = map(int, line.split())
    t, img, source = src.grab((x, y, w, h))
    out.write(struct.pack("<qIIqB", t, img.shape[1], img.shape[0], src.last_frame_id,
                          1 if source == "bus" else 0))
    out.write(np.ascontiguousarray(img).tobytes())
    out.flush()
"""
HELPER_HEADER = "<qIIqB"  # t_mono_ns, w, h, bus frame_id (-1 = X), source (1 = bus)


_DESKTOP: tuple[int, int] | None = None


def desktop() -> tuple[int, int]:
    """The Windows session's REAL size (w, h) at the screen's top-left, queried once per process
    inside the backend: its SESSION_SIZE clipped to the running Xvfb, never what .env says (between
    an .env write and a recreate the two differ). Clicks are normalised by it, and the backend maps
    them back over the same area (ADR-0009 amendment: the canvas may be larger than the session)."""
    global _DESKTOP
    if _DESKTOP is None:
        probe = (
            "import os, mss; from poring_env.x11 import parse_session_size, session_extent; "
            "m = mss.MSS(display=':99').monitors[0]; "
            "s = parse_session_size(os.environ.get('SESSION_SIZE', '')); "
            "print(*session_extent(s, m['width'], m['height']))"
        )
        out = subprocess.run(
            ["docker", "exec", BACKEND, "python", "-c", probe],
            capture_output=True, text=True, check=True,
        ).stdout.split()  # fmt: skip
        _DESKTOP = (int(out[0]), int(out[1]))
    return _DESKTOP


def tray_lang() -> tuple[int, int, int, int]:
    """The ENG / ไทย indicator left of the clock: anchored to the bottom-right corner (1098,764 on
    the 1280x800 desktop)."""
    w, h = desktop()
    return w - 182, h - 36, 36, 22


def tray_strip() -> tuple[int, int, int, int]:
    """Where the ENG/ไทย indicator can sit (it moves with the tray's icons)."""
    w, h = desktop()
    return w - 380, h - 36, 340, 22


def box_of(img: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    """PURE: ``img[y:y+h, x:x+w]`` as a whole (h, w) box, the parts outside ``img`` 0 (black).

    2026-11-21 (Batt's live Run 11202100, hunt 2's code error): a monster box at the top of the
    1080 screen put the cursor reader's 64 x 64 crop above the frame; the slice gave NO rows (a
    negative start), shape (0, 64), and the reader stopped the hunt core. Every grab now returns
    the size it was asked for: what lies off the frame is black, never a cursor or a unit."""
    out = np.zeros((h, w, *img.shape[2:]), dtype=img.dtype)
    ih, iw = img.shape[:2]
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, iw), min(y + h, ih)
    if x1 > x0 and y1 > y0:
        out[y0 - y : y1 - y, x0 - x : x1 - x] = img[y0:y1, x0:x1]
    return out


def desktop_clip(x: int, y: int, w: int, h: int, size: tuple[int, int] | None
                 ) -> tuple[int, int, int, int]:  # fmt: skip
    """PURE: a desktop box clipped to the desktop: its top-left at 0 or more, and its far edges
    inside ``size`` when the size is known (None: only the top-left edge is clipped)."""
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = x + w, y + h
    if size is not None:
        x1, y1 = min(x1, size[0]), min(y1, size[1])
    return x0, y0, x1 - x0, y1 - y0


class Screen:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            ["docker", "exec", "-i", BACKEND, "python", "-u", "-c", _HELPER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        )  # fmt: skip

    def grab(self, x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray]:
        t, img, _, _ = self.grab_meta(x, y, w, h)
        return t, img

    def grab_meta(self, x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray, int, str]:
        """(t_mono_ns, BGRA, the bus writer's frame_id or -1, "bus" | "x11"). A bus frame's t is
        its decode-complete time; an X grab's is the moment of the grab. A box at VIRTUAL_X0 is
        cut from the virtual 1280x720 frame of the real client (client_view). In a Run
        (PORING_PAUSE_AWAY=1) a grab waits while the game is off the screen (away_gate)."""
        away_gate(self)
        return self._grab_raw(x, y, w, h)

    def _grab_raw(self, x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray, int, str]:
        """grab_meta without the pause gate (the gate's own looks)."""
        if x >= VIRTUAL_X0:
            from poring_env.clientview import VIRTUAL_H, VIRTUAL_W, ClientView

            if virtual_active():
                inventory_tick(self)  # T-I5: the open bag is a panel (its slots 1:1)
            view = client_view()
            rx, ry, rw, rh = view.rect
            vx = x - VIRTUAL_X0
            inside = vx >= 0 and y >= 0 and vx + w <= VIRTUAL_W and y + h <= VIRTUAL_H
            if inside and not _panels_due():
                # s11scr 2026-11-19: only the real pixels this box reads (a 64 x 64 box at 1080:
                # ~3 ms, not the 69 ms of the whole frame through the pipe + the whole picture)
                local = ClientView((0, 0, rw, rh), view.mode, view.world_scale,
                                   view.world_centre, view.panels)  # fmt: skip
                src = local.source_rect((vx, y, w, h), (rw, rh))
                if src is None:
                    t, _, frame_id, path = self.grab_meta(rx, ry, 1, 1)
                    return t, local.crop_from(np.zeros((1, 1, 4), np.uint8), None, (vx, y, w, h),
                                              (rw, rh)), frame_id, path  # fmt: skip
                sx, sy, sw, sh = src
                t, sub, frame_id, path = self.grab_meta(rx + sx, ry + sy, sw, sh)
                if sub.shape[:2] == (sh, sw):
                    return t, local.crop_from(sub, src, (vx, y, w, h), (rw, rh)), frame_id, path
            t, real, frame_id, path = self.grab_meta(rx, ry, rw, rh)
            _panels_tick(real)  # 4f: the windows found, re-checked, searched again if moved
            view = client_view()
            local = ClientView((0, 0, rw, rh), view.mode, view.world_scale, view.world_centre,
                               view.panels)  # fmt: skip
            vf = local.virtual_frame(real)
            return t, box_of(vf, vx, y, w, h), frame_id, path
        clip = desktop_clip(x, y, w, h, _DESKTOP)
        if clip != (x, y, w, h):  # 2026-11-21: a box off the desktop's edge (box_of)
            cx, cy, cw, ch = clip
            if cw <= 0 or ch <= 0:
                t, _, frame_id, path = self._grab_raw(0, 0, 1, 1)
                return t, np.zeros((h, w, 4), np.uint8), frame_id, path
            t, sub, frame_id, path = self._grab_raw(cx, cy, cw, ch)
            return t, box_of(sub, x - cx, y - cy, w, h), frame_id, path
        return self._helper_grab(x, y, w, h)

    def _helper_grab(self, x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray, int, str]:
        """One desktop box from the backend's grab helper (the box inside the desktop)."""
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(f"{x} {y} {w} {h}\n".encode())
        self.proc.stdin.flush()
        size = struct.calcsize(HELPER_HEADER)
        t, gw, gh, frame_id, bus = struct.unpack(HELPER_HEADER, self.proc.stdout.read(size))
        raw = self.proc.stdout.read(gw * gh * 4)
        img = np.frombuffer(raw, np.uint8).reshape(gh, gw, 4)
        return t, img, frame_id, "bus" if bus else "x11"

    def full(self) -> np.ndarray:
        return self.grab(0, 0, *desktop())[1]

    def close(self) -> None:
        with contextlib.suppress(Exception):
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.wait(timeout=3)


def to_png(bgra: np.ndarray, path: Path) -> Path:
    import zlib

    h, w = bgra.shape[:2]
    rgb = bgra[:, :, 2::-1].astype(np.uint8)
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    return path


def signature_path(state: str) -> Path:
    return STATE_DIR / "signatures" / f"{state}.npy"


def region_for(state: str) -> tuple[int, int, int, int]:
    """Desktop region of a state's signature: fixed for Windows UI, else a box relative to the
    client origin saved at calibration (a dialog, not the animated background)."""
    if state == "eng":
        raw = env().get("RO_TRAY_LANG", "")  # the ENG/ไทย indicator moves with the tray's icons
        if raw:
            x, y, w, h = (int(v) for v in raw.split(","))
            return x, y, w, h
        return tray_lang()
    if state in ("shortcut_icon", "shortcut_icon_sel"):
        x, y = shortcut_xy()
        return x - 32, y - 34, SHORTCUT_BOX[2], SHORTCUT_BOX[3]
    if state in ("shell_shortcut_icon", "shell_shortcut_icon_sel"):
        x, y = shell_shortcut_xy()
        return x - 32, y - 34, SHORTCUT_BOX[2], SHORTCUT_BOX[3]
    meta = signature_path(state).with_suffix(".json")
    if state in DESKTOP_BOX_STATES and meta.exists():  # Windows' own UI: desktop pixels
        doc = json.loads(meta.read_text())
        bx, by, bw, bh = doc["box"]
        cut = doc.get("session")  # the taskbar sticks to the screen's bottom (its tray: the right)
        if cut:
            w, h = desktop()
            dx = w - int(cut[0]) if state == "taskbar" else 0  # its buttons are centred: slid
            return bx + dx, by + h - int(cut[1]), bw, bh
        return bx, by, bw, bh
    x, y, w, h = game_region()
    if state == "chat_open":
        # the open input bar of the chat window's STANDARD place (Batt 2026-11-05: docked at the
        # bottom-left, 6 lines; chat_window.py). The template is the same bar: the saved box
        # [0, 604, 570, 12] is the frozen layout's (chat_window.LEGACY), 95 px higher
        import chat_window

        dx, dy, bw, bh = chat_window.active().chat_open_box
        return x + dx, y + dy, bw, bh
    if meta.exists():
        dx, dy, bw, bh = json.loads(meta.read_text())["box"]
        if state in DIALOG_STATES and unmeasured_size():  # a login dialog: found, real pixels
            rx, ry, _, _ = real_game_region()
            vx, vy = _VECTORS.get(state, (0, 0))
            return rx + dx + vx, ry + dy + vy, bw, bh
        return x + dx, y + dy, bw, bh
    return x, y, w, h


# Locale variants (ADR-0012; 2026-10-03, the Thai pack): signatures/<state>@<locale>.npy is the SAME
# box in another locale pack's text. A state matches if ANY of its variants does; the English
# signature is never overwritten, so switching packs back needs no recalibration.
LOCALE_SEP = "@"


def base_state(state: str) -> str:
    return state.split(LOCALE_SEP, 1)[0]


def signature_variants(state: str) -> list[Path]:
    """The signature files that stand for ``state``: itself (if calibrated) and, for a base
    state, every ``state@locale`` variant. An explicit ``state@locale`` is just that file."""
    path = signature_path(state)
    found = [path] if path.exists() else []
    if LOCALE_SEP not in state:
        found += sorted(path.parent.glob(f"{state}{LOCALE_SEP}*.npy"))
    return found


def calibrate(screen: Screen, state: str, box: list[int] | None = None) -> None:
    if state == "eng_stream":  # the console stream's ENG template (only that file)
        _, img = screen.grab(*region_for("eng"))
        np.save(STATE_DIR / "signatures" / "eng_full_stream.npy", _grey(img))
        to_png(img, SHOTS / "sig_eng_stream.png")
        log(f"stream ENG template saved ({img.shape[1]}x{img.shape[0]})")
        return
    path = signature_path(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    if box is not None:
        doc: dict[str, Any] = {"box": box}
        if base_state(state) in DESKTOP_BOX_STATES:  # anchored: the session it was cut in
            doc["session"] = list(desktop())
        path.with_suffix(".json").write_text(json.dumps(doc))
    _, img = screen.grab(*region_for(state if box is not None else base_state(state)))
    np.save(path, grey_thumb(img))
    if state == "eng":  # full resolution, for the sliding tray search
        np.save(STATE_DIR / "signatures" / "eng_full.npy", _grey(img))
    to_png(img, SHOTS / f"sig_{state}.png")
    log(f"signature {state} saved ({img.shape[1]}x{img.shape[0]})")


def _grey(img: np.ndarray) -> np.ndarray:
    px = img[:, :, :3].astype(np.float32)
    return px[..., 0] * 0.114 + px[..., 1] * 0.587 + px[..., 2] * 0.299


# One ENG template per display path: the H.264 console stream softens the tray's small text, so
# the RDP template measured 6.8 there against a 6.0 threshold (2026-10-03). Not a looser guard: a
# second template, calibrated on the stream while the tray visibly said ENG.
ENG_TEMPLATES = ("eng_full.npy", "eng_full_stream.npy")


def eng_distance(screen: Screen) -> float:
    """Best match of a full-resolution ENG template anywhere in the tray strip: the indicator's
    x shifts as tray icons come and go (1086 vs 1115 on the same account, 2026-10-01)."""
    _, img = screen.grab(*tray_strip())
    strip = _grey(img)
    best = float("inf")
    for name in ENG_TEMPLATES:
        path = STATE_DIR / "signatures" / name
        if not path.exists():
            continue
        tmpl = np.load(path)
        th, tw = tmpl.shape
        for x in range(0, strip.shape[1] - tw + 1):
            best = min(best, float(np.abs(strip[:th, x : x + tw] - tmpl).mean()))
    return best


class FrozenStream(Stop):
    """No frame decoded AFTER an action arrived in time: the stream is frozen (a dropped frame
    waiting for an IDR), so the action's effect is UNKNOWN -- never decide on the older picture
    (the frame-age guard, 2026-10-04: a frozen frame made the chat look closed at 05:58)."""


FRESH_WAIT_S = 1.5  # the longest measured freeze was 239 ms; a static screen sends no frames


def grab_after(
    screen: Screen, region: tuple[int, int, int, int], after_ns: int | None
) -> np.ndarray:
    """``region`` from a frame decoded after ``after_ns`` (bus) -- an X grab is always "now".
    Without ``after_ns`` it is a plain grab, exactly as before."""
    if after_ns is None:
        return screen.grab(*region)[1]
    return grab_after_meta(screen, region, after_ns)[1]


def grab_after_meta(
    screen: Screen, region: tuple[int, int, int, int], after_ns: int
) -> tuple[int, np.ndarray, int, str]:
    """grab_after with the frame's meta: (t_mono_ns, BGRA, the bus frame_id or -1, "bus" |
    "x11"). dungeon@9.21 (LF-2) keeps the frame id of the frame it read."""
    end = time.monotonic() + FRESH_WAIT_S
    while True:
        started = time.monotonic()
        t, img, frame_id, source = screen.grab_meta(*region)
        if source != "bus" or t > after_ns:
            return t, img, frame_id, source
        # 2026-11-19 (Batt's Runs flowplay-11191458..1510, 4 of 4 ended here): only a grab that
        # BEGAN after the deadline proves the stream frozen. One slow grab (a 1.7 s window search
        # on a 1920x1080 frame, now in the background) used to cross the deadline with the frame
        # it took before the action, and the run ended on a healthy stream (p95 73 ms).
        if started > end:
            raise FrozenStream(f"no frame newer than the action within {FRESH_WAIT_S} s")
        time.sleep(0.02)


def distance(screen: Screen, state: str, after_ns: int | None = None) -> float:
    if state == "eng" and (STATE_DIR / "signatures" / "eng_full.npy").exists():
        return eng_distance(screen)
    paths = signature_variants(state)
    if not paths:
        raise Stop(f"no signature for {state!r}: run `ro_agent.py calibrate {state}` first")
    img = grab_after(screen, region_for(base_state(state)), after_ns)
    cur = grey_thumb(img)
    best = float("inf")
    for path in paths:
        ref = np.load(path)
        if cur.shape == ref.shape:
            best = min(best, float(np.abs(cur - ref).mean()))
    if best > SIG_MATCH and base_state(state) in DIALOG_STATES and unmeasured_size():
        best = min(best, find_dialog(screen, base_state(state), paths, after_ns))
    return best


def unmeasured_size() -> bool:
    """The client's size has no measured login layout (LAYOUTS): its dialogs are found. An
    unreadable GAME_REGION is never 'unmeasured' (the fixed boxes decide, as before)."""
    try:
        _, _, w, h = real_game_region()
    except (Stop, OSError):
        return False
    return (w, h) not in LAYOUTS


def find_dialog(screen: Screen, state: str, paths: Sequence[Path], after_ns: int | None) -> float:
    """Find a login-screen dialog anywhere in the client by its picture; remember its vector from
    its 1280x720 box (the box saved at calibration). The distance of the best place."""
    meta = signature_path(state).with_suffix(".json")
    if not meta.exists():
        return float("inf")
    bx, by, _, _ = json.loads(meta.read_text())["box"]
    x, y, w, h = real_game_region()  # the login dialogs: real pixels
    client = grab_after(screen, (x, y, w, h), after_ns)
    # where it is expected: moved like a dialog already found, else by the rule measured at 1080p
    # (x centred, y at 0.625 of the extra height; docs/planning/fullscreen-client.md section 7)
    vx, vy = next(iter(_VECTORS.values()), ((w - 1280) // 2, round(0.625 * (h - 720))))
    best = (float("inf"), 0, 0)
    for path in paths:
        ref = np.load(path).astype(np.float32)
        best = min(best, sig_find(client, ref, hint=(bx + vx, by + vy)))
    d, fx, fy = best
    if d <= SIG_MATCH:
        _VECTORS[state] = (fx - bx, fy - by)
    return d


def is_state(screen: Screen, state: str, after_ns: int | None = None) -> bool:
    """``after_ns``: judge only a frame decoded after this time (the effect of an action)."""
    return distance(screen, state, after_ns) <= SIG_MATCH


def wait_state(screen: Screen, states: list[str], timeout: float) -> str:
    if not any(signature_variants(st) for st in states):  # first run: calibrating
        log(f"no signature yet for {states}: waiting {min(timeout, 25):.0f} s instead")
        time.sleep(min(timeout, 25))
        return "uncalibrated"
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        for st in states:
            if signature_variants(st) and is_state(screen, st):
                return st
        time.sleep(0.5)
    to_png(screen.full(), SHOTS / f"timeout_{'_'.join(states)}.png")
    raise Stop(f"timed out ({timeout:.0f} s) waiting for {states}; screenshot saved")


def black(screen: Screen) -> bool:
    _, img = screen.grab(*game_region())
    px = img[::4, ::4, :3].astype(np.uint16)
    luma = (px[..., 0] * 29 + px[..., 1] * 150 + px[..., 2] * 77) >> 8
    return bool((luma < 10).mean() >= 0.98)


# --- the mux channel ------------------------------------------------------------------------------


def backend_ws() -> str:
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    from backend_addr import backend_ip  # the DEFAULT network's address (two networks since c2)

    ip = backend_ip(BACKEND)
    if not ip:
        raise Stop(f"{BACKEND} has no address on the default network (not running?)")
    return f"ws://{ip}:8001/internal/agent"


def backend_health() -> dict[str, Any]:
    """The backend's /health (public port, the default network's address), or {}."""
    import urllib.request

    url = backend_ws().replace("ws://", "http://").replace(":8001/internal/agent", ":8000/health")
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            data: dict[str, Any] = json.loads(resp.read())
            return data
    except OSError:
        return {}


# --- the environment interlock (ADR-0016, rewritten 2026-10-04) -----------------------------------


class Unattested(Stop):
    """The mux refused bot input: no attested lab session and no operator window (ADR-0016).
    Never retried as if the screen were at fault (dataset_activity.safe_gm re-raises it)."""


WINDOW_MIN_LEFT_S = 25


def ensure_window(
    kind: str, phase: str, seconds: int = 90, min_left: float = WINDOW_MIN_LEFT_S
) -> None:
    """Login and desktop phases happen before (or outside) an attested in-game session: open a
    bounded operator window through the HOST tool (capture_backend.py window; never the agent
    channel). Skipped when a window of this kind is open long enough (capture_backend opens its
    own before its ro_agent steps, holding the mutation lock), and for LOGIN while the interlock
    is green. A DESKTOP window is opened even while green: the foreground gate needs it.

    The window is read FRESH from the host's state/ with the backend's own parser: /health reports
    the interlock as of its last 1 Hz tick. Right after capture_backend re-opened its window for the
    new SEQ, that stale view said "no window", so the child `window` command waited 30 s for the
    flock its own parent held and to-console failed (21:18, 21:26 and 21:43 on 2026-10-04; the one
    run whose check landed after a tick went through)."""
    open_now = read_window(LAB_STATE, read_lock(LAB_STATE), time.time())
    if open_now is not None and open_now[0] == kind and open_now[2] >= min_left:
        return
    env_status = backend_health().get("environment") or {}
    if env_status.get("state") == "green" and kind != "desktop":
        # Green lets presses through the interlock, but NOT typing outside the client: the
        # typing-only foreground gate exempts the agent's own console steps only under a DESKTOP
        # window (Batt's answer 1, 2026-10-06). Skipping it while green refused every console
        # line and minimize-consoles after the post-reboot GM login (2026-10-06 19:54).
        return
    cmd = [sys.executable, str(ROOT / "scripts" / "capture_backend.py"), "window", kind,
           "--seconds", str(seconds), "--reason", phase]  # fmt: skip
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise Stop(f"could not open the {kind} window for {phase}: {res.stderr.strip()[-300:]}")
    log(f"interlock: {kind} window for {phase} ({seconds} s)")


def key(code: str, action: str) -> dict[str, Any]:
    return {"type": "key", "t_mono_ns": ns(), "frame_id": -1, "code": code, "action": action}


def tap(code: str, shift: bool = False) -> list[dict[str, Any]]:
    if shift:
        return [
            key("ShiftLeft", "down"),
            key(code, "down"),
            key(code, "up"),
            key("ShiftLeft", "up"),
        ]
    return [key(code, "down"), key(code, "up")]


def char_events(c: str) -> list[dict[str, Any]]:
    if c.isascii() and c.isalpha():
        return tap(f"Key{c.upper()}", shift=c.isupper())
    if c.isascii() and c.isdigit():
        return tap(f"Digit{c}")
    if c in PLAIN:
        return tap(PLAIN[c])
    if c in SHIFTED:
        return tap(SHIFTED[c], shift=True)
    raise Stop("cannot type that character (US-layout ASCII only)")  # never echo the character


# max_queue=None: no receive-side flow control. With the library's default (16 frames) its reader
# thread STOPS reading the socket once 16 unread messages queue up -- ~16 s of the backend's 1 Hz
# status -- so pings go unanswered and the connection dies 20-40 s later, and a close then waits
# its 10 s timeout ("sent 1000 (OK); no close frame received", to-console 2026-10-04). Callers do
# host work between sends (docker exec read-backs, subprocesses); the backlog is ~1 KB/s of status,
# read through by the next _drain. test_ro_agent_ws.py reproduces both behaviours.
AGENT_WS: dict[str, Any] = {"open_timeout": 5, "max_size": 2**20, "max_queue": None}

# The mux modes an Agent may send in. ASSIST alone by default: every script of ours plays where the
# person can take the lease at any moment. Batt 2026-11-18 ("with BOT it must run too"; ADR-0020
# Amendment 2026-11-18): a /flows Run may play in BOT as well, where the mux drops the human's input
# and the person stops it with Stop or by switching to HUMAN. The Run helper (scripts/flow_run.py)
# names that for its own processes only, in PORING_INPUT_MODES ("ASSIST,BOT"). HUMAN is never one.
# Fullscreen (docs/planning/fullscreen-client.md): Windows' own UI whose signature boxes are in
# DESKTOP pixels (not relative to GAME_REGION); the taskbar-absent rule, the backend gate's
# (foreground.TASKBAR_ABSENT_MIN); how long an ENG reading taken before the launch stands
DESKTOP_BOX_STATES = ("taskbar", "taskbar_client_icon")
# Phase 2 (docs/planning/fullscreen-client.md section 7): on a client size with no measured login
# layout, each login-screen dialog is FOUND by its own picture (signature.find); its vector from its
# 1280x720 place then moves its checks and its click points. The server list is the service list's
# twin (the same OK at the same place), so its OK takes the service dialog's vector.
DIALOG_STATES = ("service_select", "login", "server_select", "char_select", "char_make")
DIALOG_OF_POINT = {
    "service_ok": "service_select", "server_ok": "service_select", "server_row": "service_select",
    "id": "login", "password": "login", "login_button": "login",
    "slot1": "char_select", "char_name": "char_make", "char_create": "char_make",
}  # fmt: skip
_VECTORS: dict[str, tuple[int, int]] = {}
# ➡️ 20 -> 10 (s11scr 2026-11-20 00:0x, the lab at 1920x1080). The shown taskbar reads 0.0-1.3
# (every layout seen, 720 and 1080). The game in front read 49.9-111.7 at 720, but 33-181 at 1080
# over 25 Fly Wing spots and 19.52 at one dark corner: under 20, so the gate refused every key
# and the Run paused there (s11scr-1080 r02B's end, r03B's setup). 10 keeps 7x above the taskbar.
TASKBAR_ABSENT_MIN = 10.0  # the backend's (foreground.py), the same bar
ENG_FRESH_S = 600.0
_ENG_AT: float | None = None

MODES_ENV = "PORING_INPUT_MODES"
MODES_DEFAULT = ("ASSIST",)
MODES_ALLOWED = ("ASSIST", "BOT")


def input_modes(value: str | None) -> tuple[str, ...]:
    """PURE: PORING_INPUT_MODES -> the modes an Agent may send in (unset or empty: ASSIST alone).
    Anything but ASSIST and BOT is refused, HUMAN above all (the person's own mode)."""
    names = tuple(dict.fromkeys(n.strip().upper() for n in (value or "").split(",") if n.strip()))
    bad = [n for n in names if n not in MODES_ALLOWED]
    if bad:
        raise Stop(f"{MODES_ENV}={value!r}: only {', '.join(MODES_ALLOWED)} ({bad} refused)")
    return names or MODES_DEFAULT


# --- a Run pauses while the game is off the screen (Batt 2026-11-18: "if a user presses Alt+Tab,
# only pause; when the game is back the bot must detect the screen and play on by itself") -------
# Every grab and every press passes ro_agent, so the gate is here, not in the (byte-pinned) runner:
# its threads and its Battle Log subprocess all freeze in place and go on with fresh frames.
AWAY_ENV = "PORING_PAUSE_AWAY"  # "1": this process's (and its children's) grabs and presses wait
AWAY_CHECK_S = 0.25  # a verdict "on the screen" is reused this long (a key press looks again)
AWAY_POLL_S = 0.25  # while away: one look this often
AWAY_SETTLE_S = 1.5  # back: on the screen and drawn this long without a break, then the bot goes on
AWAY_DARK = 8.0  # the client's centre darker than this (grey mean): not drawn yet (a mode switch)
AWAY_KEY_RETRIES = 3  # a key the backend refused (the game left the screen mid-press): pause, again
FOREGROUND_REASONS = frozenset({"client_not_foreground", "foreground_stale_frame"})
AWAY_HOOK: Callable[[str, dict[str, Any]], None] | None = None  # "pause" / "resume" (flow_play)
AWAY_STOP: Callable[[], str | None] | None = None  # while paused: why to stop now (Stop pressed)
_AWAY_LOCK = threading.Lock()
_AWAY: dict[str, Any] = {"t": -1e9, "why": None, "since": None}
_THREAD_AGENTS: dict[int, weakref.WeakSet[Any]] = {}
_REFS: dict[str, np.ndarray] = {}


def pause_away() -> bool:
    """A Run's pause is on in this process (flow_play sets it; inherited by its children)."""
    return os.environ.get(AWAY_ENV) == "1"


def away_verdict(full: bool, taskbar_d: float | None, title_d: float | None) -> str | None:
    """PURE: why the game is not on the screen, or None: it is, or nothing can tell (no template
    -- a pause needs a proof; the backend's own gate still refuses keys). Fullscreen: Windows
    hides its taskbar while a fullscreen window is in front (the backend's rule, the same bar).
    A window: its active title-bar signature."""
    if full:
        if taskbar_d is not None and taskbar_d < TASKBAR_ABSENT_MIN:
            return ("the Windows taskbar shows: the game is not in front (Alt+Tab, the Start menu, "
                    "a Windows pop-up or another window)")  # fmt: skip
        return None
    if title_d is not None and title_d > SIG_MATCH:
        return ("the game window is not the active window (its title bar is not lit): another "
                "window is in front")  # fmt: skip
    return None


def _raw_distance(screen: Screen, state: str) -> float | None:
    """``distance`` on the raw grab path (no pause gate, no dialog search); None: no template."""
    paths = signature_variants(state)
    if not paths:
        return None
    _, img, _, _ = screen._grab_raw(*region_for(base_state(state)))
    cur = grey_thumb(img)
    ds = []
    for path in paths:
        ref = _REFS.get(str(path))
        if ref is None:
            ref = _REFS.setdefault(str(path), np.load(path))
        if ref.shape == cur.shape:
            ds.append(float(np.abs(cur - ref).mean()))
    return min(ds) if ds else None


def away_now(screen: Screen) -> str | None:
    """Why the game is not on the screen now, from one look, or None (away_verdict)."""
    full = fullscreen()
    taskbar = _raw_distance(screen, "taskbar") if full else None
    title = None if full else _raw_distance(screen, "client_title_active")
    return away_verdict(full, taskbar, title)


def client_drawn(screen: Screen) -> bool:
    """The client's centre is not black: after a return the game redraws a beat later."""
    x, y, w, h = real_game_region()
    _, img, _, _ = screen._grab_raw(x + w // 2 - 160, y + h // 2 - 90, 320, 180)
    return float(np.asarray(img)[..., :3].mean()) >= AWAY_DARK


def away_state() -> dict[str, Any]:
    """The pause as it stands: {"paused": bool, "why", "for_s"} (a snapshot, for a log line)."""
    with _AWAY_LOCK:
        since = _AWAY["since"]
        return {"paused": since is not None, "why": _AWAY["why"],
                "for_s": None if since is None else round(time.monotonic() - since, 1)}  # fmt: skip


def _away_note(kind: str, info: dict[str, Any]) -> None:
    hook = AWAY_HOOK
    if hook is None:
        log(f"PAUSED: {info.get('why')}" if kind == "pause" else
            f"RESUMED after {info.get('after_s')} s: the game is back on the screen")  # fmt: skip
        return
    with contextlib.suppress(Exception):  # a log line never stops the run
        hook(kind, info)


def away_gate(screen: Screen, *, fresh: bool = False) -> None:
    """A Run's pause (PORING_PAUSE_AWAY=1): while the game is off the screen this waits -- the
    caller grabs and presses nothing -- and returns once the game is back AND drawn for
    AWAY_SETTLE_S without a break. Its thread's Agents let go of what they hold at the start and
    are read meanwhile (their websocket stays healthy). The first thread to see it notes "pause"
    (AWAY_HOOK), the first to see it end "resume". AWAY_STOP (Stop pressed) ends the wait: Stop.
    ``fresh``: look now, never the cached verdict (a key press: the backend refuses a key while
    the game is not in front)."""
    if not pause_away():
        return
    with _AWAY_LOCK:
        if not fresh and _AWAY["why"] is None and time.monotonic() - _AWAY["t"] < AWAY_CHECK_S:
            return
    why = away_now(screen)
    with _AWAY_LOCK:
        _AWAY["t"], _AWAY["why"] = time.monotonic(), why
        if why is None:
            return
        first = _AWAY["since"] is None
        if first:
            _AWAY["since"] = time.monotonic()
    if first:
        _away_note("pause", {"why": why, "t_wall": time.time()})
    for a in _thread_agents():
        a.release_quiet()
    shown: float | None = None
    while True:
        stop_why = AWAY_STOP() if AWAY_STOP is not None else None
        if stop_why:
            raise Stop(stop_why)
        agents = _thread_agents()
        if agents:
            for a in agents:
                a._drain(AWAY_POLL_S / len(agents))
        else:
            time.sleep(AWAY_POLL_S)
        if away_now(screen) is not None or not client_drawn(screen):
            shown = None
            continue
        shown = shown if shown is not None else time.monotonic()
        if time.monotonic() - shown >= AWAY_SETTLE_S:
            break
    with _AWAY_LOCK:
        since = _AWAY["since"]
        _AWAY.update(t=time.monotonic(), why=None, since=None)
    if since is not None:
        _away_note("resume", {"after_s": round(time.monotonic() - since, 1), "t_wall": time.time()})


def _thread_agents() -> list[Any]:
    return list(_THREAD_AGENTS.get(threading.get_ident(), ()))


def is_release(e: Mapping[str, Any]) -> bool:
    """PURE: an event that only lets go (always sent, never paused)."""
    return e.get("type") == "release_all" or (
        e.get("type") in ("key", "mouse_button") and e.get("action") == "up"
    )


def refused_for_foreground(chunk: Sequence[Mapping[str, Any]], ack: Mapping[str, Any]) -> bool:
    """PURE: the backend refused this batch only because the game was not in front, and every
    event of it was a key (so sending it again repeats nothing that went through)."""
    reasons = set(ack.get("reasons") or ())
    return (bool(reasons) and reasons <= FOREGROUND_REASONS
            and all(e.get("type") == "key" for e in chunk)
            and int(ack.get("dropped") or 0) == len(chunk))  # fmt: skip


def virtual_event(ev: dict[str, Any]) -> dict[str, Any]:
    """A pointer event whose normalised position is a VIRTUAL point (x beyond 1: a caller that
    normalised a virtual pixel by the desktop, the runner's raw double-click) -> its real one."""
    x, y = ev.get("x"), ev.get("y")
    if ev.get("type") not in ("mouse_move", "mouse_button") or x is None or y is None:
        return ev
    w, h = desktop()
    if float(x) * w < VIRTUAL_X0:
        return ev
    rx, ry = real_xy(float(x) * w, float(y) * h)
    return {**ev, "x": rx / w, "y": ry / h}


class Agent:
    """One /internal/agent connection; every send checks the mode (ASSIST; a /flows Run also BOT:
    input_modes) and waits out a human lease (ASSIST's only: the mux drops human input in BOT)."""

    modes: tuple[str, ...] = MODES_DEFAULT  # the instance's own from PORING_INPUT_MODES

    def __init__(self, name: str = "ro_agent", *, allow_handover: bool = False) -> None:
        self.allow_handover = allow_handover  # only scripts/capture_backend.py, mid-handover
        self.modes = input_modes(os.environ.get(MODES_ENV))
        self._conn = connect(backend_ws(), **AGENT_WS)
        self.ws: ClientConnection = self._conn.__enter__()
        hello = {"type": "agent_hello", "t_mono_ns": ns(), "frame_id": -1, "agent_id": name,
                 "version": "1"}  # fmt: skip
        self.ws.send(json.dumps(hello))
        self.status: dict[str, Any] = {}
        # hunt-flow v34 (2026-10-17 22:3x): None = the DEFAULT, a blocking 50 ms drain before every
        # send (each click's three sends waited 150 ms on it, half of a ~0.3 s click). A number =
        # PACED sends: the status messages already queued are read without blocking, and a send
        # waits only until this long after the previous one (the old drain's minimum spacing kept
        # at 0.05: no two inputs closer than today; only the dead wait after other work goes).
        self.min_send_gap_s: float | None = None
        self._last_send = 0.0
        self._gate_screen: Screen | None = None  # the pause gate's own looks (made when needed)
        _THREAD_AGENTS.setdefault(threading.get_ident(), weakref.WeakSet()).add(self)
        self._drain(1.5, want="status")
        if self.status.get("mode") not in self.modes:
            self.ws.close()
            raise Stop(f"mux mode is {self.status.get('mode')}, not {' or '.join(self.modes)}: "
                       "no input sent")  # fmt: skip
        self.backend = self._check_capture_backend()

    def _check_capture_backend(self) -> str:
        """ADR-0009: input only while the capture-backend lock is steady, and the host file and the
        backend agree on it (a backend created before the lock mount reports nothing)."""
        lock = self.status.get("capture_backend")
        host = read_lock(LAB_STATE)
        if lock is None:
            print("WARNING: the backend reports no capture_backend (predates the lock)", flush=True)
            return host.backend
        if lock.get("backend") == "hold" or host.backend == "hold":
            self.ws.close()
            raise Stop(f"capture-backend lock HOLD ({lock.get('reason') or host.reason}): no input")
        if (lock.get("phase") == "switching" or host.phase == "switching") and not (
            self.allow_handover
        ):
            self.ws.close()
            raise Stop("a capture-backend handover is in progress: no input sent")
        if (lock.get("backend"), lock.get("seq")) != (host.backend, host.seq):
            self.ws.close()
            raise Stop(
                f"capture-backend lock mismatch: host {host.backend}/{host.seq}, backend "
                f"{lock.get('backend')}/{lock.get('seq')} (scripts/capture_backend.py status)"
            )
        return str(lock["backend"])

    def idle(self, seconds: float) -> None:
        """Wait without sending input, reading the backend's messages so the connection stays
        healthy (a session left unread for ~35 s failed its websocket keepalive, 2026-10-02)."""
        end = time.monotonic() + seconds
        while (left := end - time.monotonic()) > 0:
            self._drain(min(1.0, left))

    def _drain(self, timeout: float, want: str | None = None) -> dict[str, Any] | None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                msg = json.loads(self.ws.recv(timeout=max(0.0, end - time.monotonic())))
            except TimeoutError:
                break
            if msg.get("type") == "status":
                self.status = msg
            if msg.get("type") == "error":
                raise Stop(f"backend error reply: {msg.get('reason')}")
            if want and msg.get("type") == want:
                return dict(msg)
        return None

    def _drain_ready(self) -> None:
        """Every message already received, without blocking (status / error handled as _drain)."""
        while True:
            try:
                msg = json.loads(self.ws.recv(timeout=0))
            except TimeoutError:
                return
            if msg.get("type") == "status":
                self.status = msg
            if msg.get("type") == "error":
                raise Stop(f"backend error reply: {msg.get('reason')}")

    def _pre_send(self) -> None:
        """Before a send: the default 50 ms drain, or (``min_send_gap_s``) the queued messages
        plus the rest of the minimum gap since the previous send, draining meanwhile."""
        if self.min_send_gap_s is None:
            self._drain(0.05)
            return
        self._drain_ready()
        rest = self.min_send_gap_s - (time.monotonic() - self._last_send)
        if rest > 0:
            self._drain(rest)

    def wait_for_human(self, max_wait_s: float = 600.0) -> None:
        """Batt holds the ASSIST lease: wait (never fight), up to max_wait_s, then stop. A mode
        this Agent may not send in (HUMAN; BOT unless input_modes names it) stops it; in BOT the
        mux drops the human's input, so there is no lease to wait out."""
        end = time.monotonic() + max_wait_s
        while True:
            self._pre_send()
            lease = self.status.get("lease_until_ns")
            mode = self.status.get("mode")
            if mode not in self.modes:
                raise Stop(f"mux left {' / '.join(self.modes)} ({mode}): stopping")
            if mode == "BOT" or not lease or lease < ns():
                return
            if time.monotonic() > end:
                raise Stop("the human kept the lease for 10 min: giving up")
            log("human lease active: waiting")
            self._drain(1.0)

    def gate_screen(self) -> Screen:
        if getattr(self, "_gate_screen", None) is None:  # a test's Agent may skip __init__
            self._gate_screen = Screen()
        assert self._gate_screen is not None
        return self._gate_screen

    def release_quiet(self) -> None:
        """Let go of whatever this Agent holds (a pause's start): one release_all, never raises
        (releases always pass the mux)."""
        with contextlib.suppress(Exception):
            msg = {"type": "agent_input", "t_mono_ns": ns(), "frame_id": -1, "t_capture_ns": ns(),
                   "events": [{"type": "release_all", "t_mono_ns": ns(), "frame_id": -1}],
                   "sensitive": False}  # fmt: skip
            self.ws.send(json.dumps(msg))
            self._drain(1.0, want="input_ack")

    def send(self, events: list[dict[str, Any]], *, sensitive: bool = False) -> None:
        events = [virtual_event(e) for e in events]
        pausing = pause_away() and not all(is_release(e) for e in events)
        if pausing:  # a Run: never press while the game is off the screen (away_gate)
            down = any(e.get("type") == "key" and e.get("action") == "down" for e in events)
            away_gate(self.gate_screen(), fresh=down)
        self.wait_for_human()
        for i in range(0, len(events), 64):
            chunk = events[i : i + 64]
            msg = {"type": "agent_input", "t_mono_ns": ns(), "frame_id": -1, "t_capture_ns": ns(),
                   "events": chunk, "sensitive": sensitive}  # fmt: skip
            tries = 0
            while True:
                self.ws.send(json.dumps(msg))
                self._last_send = time.monotonic()
                ack = self._drain(3.0, want="input_ack")
                if ack is None:
                    raise Stop("no input_ack within 3 s")
                if not (
                    pausing and tries < AWAY_KEY_RETRIES and refused_for_foreground(chunk, ack)
                ):
                    break
                tries += 1  # the game left the screen between the look and the key: pause, again
                away_gate(self.gate_screen(), fresh=True)
                self.wait_for_human()
                msg = {**msg, "t_mono_ns": ns(), "t_capture_ns": ns()}
            if ack["dropped"]:
                why = f"mux refused {ack['dropped']}/{len(chunk)} ({ack['reasons']}): stopping"
                if "environment_unattested" in ack["reasons"]:
                    raise Unattested(why)
                raise Stop(why)

    def keys(self, *codes: str) -> None:
        for c in codes:
            self.send([key(c, "down")])
            time.sleep(HOLD_S)
            self.send([key(c, "up")])
            time.sleep(HOLD_S)

    def clear_field(self, n: int) -> None:
        """n paced Backspaces. The client drops edit keys injected back-to-back in one batch (only
        4 of 24 registered, 2026-10-01); typed characters arrive intact (they come as WM_CHAR)."""
        for _ in range(n):
            self.send([key("Backspace", "down")])
            time.sleep(0.03)
            self.send([key("Backspace", "up")])
            time.sleep(0.03)

    def chord(self, *codes: str) -> None:
        """Press in order, release in reverse, each step its own batch CHORD_STEP_S apart (the
        modifier is held while the key goes down and up). Whatever was pressed is released even
        when a later step is refused: a stuck Alt would turn every later click into Alt+click."""
        pressed: list[str] = []
        try:
            for c in codes:
                self.send([key(c, "down")])
                pressed.append(c)
                time.sleep(CHORD_STEP_S)
        finally:
            for c in reversed(pressed):
                with contextlib.suppress(Stop):  # releases always pass the mux; keep the cause
                    self.send([key(c, "up")])
                time.sleep(CHORD_STEP_S)

    def type_text(self, text: str, *, sensitive: bool = False) -> None:
        for c in text:  # one balanced batch per character, paced
            self.send(char_events(c), sensitive=sensitive)
            time.sleep(0.03)

    def type_secret(self, text: str, guard: Callable[[], None]) -> None:
        """Sensitive typing that re-verifies the target screen before it starts and every 4
        characters (2026-10-01: a password typed into a PowerShell window that had covered the
        client was executed and saved to PSReadLine history). `guard` raises Stop."""
        for i, c in enumerate(text):
            if i % 4 == 0:
                guard()
            self.send(char_events(c), sensitive=True)
            time.sleep(0.03)

    def move(self, x: int, y: int) -> None:
        """A pointer move, CLAMPED into the desktop (2026-10-19, hunt-flow@43 run 4: a move above
        the desktop was dropped by the backend's validation, never acknowledged, and the run
        stopped on the missing ack). A clamp is logged with its caller, to find the source."""
        x, y = real_xy(x, y)
        w, h = desktop()
        cx, cy = min(max(int(x), 0), w - 1), min(max(int(y), 0), h - 1)
        if (cx, cy) != (int(x), int(y)):
            import traceback

            fr = traceback.extract_stack(limit=3)[0]
            log(f"pointer move ({x}, {y}) clamped into the desktop, from "
                f"{Path(fr.filename).name}:{fr.lineno} {fr.name}")  # fmt: skip
        self.send([{"type": "mouse_move", "t_mono_ns": ns(), "frame_id": -1,
                    "x": cx / w, "y": cy / h}])  # fmt: skip

    def _on_desktop(self, x: float, y: float, what: str) -> None:
        """A press outside the desktop is never sent (clamping it would press whatever lies at
        the desktop's edge): a clear Stop naming the point, not a dropped message."""
        w, h = desktop()
        if not (0 <= x < w and 0 <= y < h):
            raise Stop(f"{what} outside the desktop at ({x}, {y}): not sent")

    def click(self, x: int, y: int, button: str = "left") -> None:
        x, y = real_xy(x, y)
        self._on_desktop(x, y, "click")
        w, h = desktop()
        nx, ny = x / w, y / h
        self.move(x, y)
        time.sleep(HOLD_S)
        for action in ("down", "up"):
            self.send([{"type": "mouse_button", "t_mono_ns": ns(), "frame_id": -1,
                        "button": button, "action": action, "x": nx, "y": ny}])  # fmt: skip
            time.sleep(HOLD_S)

    def drag(
        self, x1: int, y1: int, x2: int, y2: int, button: str = "left", steps: int = 10
    ) -> None:
        """Press at (x1, y1), move to (x2, y2) in `steps` paced moves, release. RO's camera
        (right-drag) reads motion spread over frames while the button is held, so the moves are
        30 ms apart, never one batch; the button is released even if a move is refused."""
        x1, y1 = real_xy(x1, y1)
        x2, y2 = real_xy(x2, y2)
        self._on_desktop(x1, y1, "drag start")
        self._on_desktop(x2, y2, "drag end")
        w, h = desktop()
        self.move(x1, y1)
        time.sleep(HOLD_S)
        self.send([{"type": "mouse_button", "t_mono_ns": ns(), "frame_id": -1, "button": button,
                    "action": "down", "x": x1 / w, "y": y1 / h}])  # fmt: skip
        try:
            for i in range(1, steps + 1):
                time.sleep(0.03)
                self.move(round(x1 + (x2 - x1) * i / steps), round(y1 + (y2 - y1) * i / steps))
        finally:
            time.sleep(HOLD_S)
            self.send([{"type": "mouse_button", "t_mono_ns": ns(), "frame_id": -1,
                        "button": button, "action": "up", "x": x2 / w, "y": y2 / h}])  # fmt: skip

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.ws.close()
        gate = getattr(self, "_gate_screen", None)
        if gate is not None:
            gate.close()
            self._gate_screen = None


@contextlib.contextmanager
def session(
    name: str = "ro_agent", *, allow_handover: bool = False
) -> Iterator[tuple[Agent, Screen]]:
    screen = Screen()
    try:
        agent = Agent(name, allow_handover=allow_handover)
    except BaseException:
        screen.close()
        raise
    try:
        yield agent, screen
    finally:
        agent.close()
        screen.close()


def at(dx: int, dy: int) -> tuple[int, int]:
    x, y, _, _ = game_region()
    return x + dx, y + dy


def centre_offset(dx: int, dy: int) -> tuple[int, int]:
    """Login/char-select windows are centred in the client area: offsets from its centre."""
    x, y, w, h = game_region()
    return x + w // 2 + dx, y + h // 2 + dy


# --- Windows one-liners through the Run dialog ----------------------------------------------------


# --- an existing PowerShell console (never the Run dialog: Defender's ClickFix detection) -------


# Templates per console kind: a Windows Terminal tab, and a classic console window's title bar
# (Batt's elevated console opened as one on 2026-10-02 -- same icon + title, another background).
# "poring-lab shell" is the agent's OWN terminal (open_terminal, Batt 2026-10-03); a plain
# "Windows PowerShell" tab is one Batt opened.
SHELL_TEMPLATE = "shell_tab_template.npy"
# One copy per display path, like ENG_TEMPLATES: the console stream's H.264 softens a tab's small
# text, so a template cut on RDP frames may miss it there (2026-10-03: `calibrate-shell --stream`).
STREAM_SUFFIX = "_stream.npy"


def template_names(name: str) -> tuple[str, str]:
    return name, name.removesuffix(".npy") + STREAM_SUFFIX


CONSOLE_TEMPLATES = {
    False: (SHELL_TEMPLATE, "ps_tab_template.npy"),
    True: ("ps_admin_tab_template.npy", "ps_admin_conhost_template.npy"),
}


def find_console(screen: Screen, admin: bool = False) -> tuple[int, int, float] | None:
    """Locate an ACTIVE Windows PowerShell tab or title bar anywhere on screen by template (its
    icon + title), anchored on the icon's blue pixels. Returns (x, y, error) of the template origin
    of the best match over the kind's templates, or None. A dark heuristic is not enough: the
    black wallpaper passed one (2026-10-01, Enter landed on the desktop and launched CPU-Z's UAC
    prompt -- declined)."""
    rgb = screen.full()[:, :, 2::-1].astype(np.int16)
    best: tuple[int, int, float] | None = None
    for name in (n for base in CONSOLE_TEMPLATES[admin] for n in template_names(base)):
        path = STATE_DIR / "signatures" / name
        if not path.exists():
            continue
        found = _match_console(rgb, np.load(path).astype(np.int16))
        if found is not None and (best is None or found[2] < best[2]):
            best = found
    if best is None and not any(
        (STATE_DIR / "signatures" / n).exists() for n in CONSOLE_TEMPLATES[admin]
    ):
        raise Stop(f"no PowerShell console template ({', '.join(CONSOLE_TEMPLATES[admin])})")
    return best


def _match_console(rgb: np.ndarray, tmpl: np.ndarray) -> tuple[int, int, float] | None:
    """One template (RGB int16) against the screen (RGB int16): (x, y, error) or None."""
    th, tw = tmpl.shape[:2]
    blue = (tmpl[..., 2] > 150) & (tmpl[..., 0] < 110)
    # Anchor on an INTERIOR icon pixel (all 8 neighbours blue too): an edge pixel is anti-aliased
    # and changes with the tab's sub-pixel position (missed a visible tab, 2026-10-01).
    inner = blue.copy()
    inner[1:-1, 1:-1] &= (
        blue[:-2, 1:-1] & blue[2:, 1:-1] & blue[1:-1, :-2] & blue[1:-1, 2:]
        & blue[:-2, :-2] & blue[:-2, 2:] & blue[2:, :-2] & blue[2:, 2:]
    )  # fmt: skip
    inner[[0, -1], :] = False
    inner[:, [0, -1]] = False
    pts = np.argwhere(inner) if inner.any() else np.argwhere(blue)
    ay, ax = (int(v) for v in pts[len(pts) // 2])
    h, w = rgb.shape[:2]
    anchor = tmpl[ay, ax]
    cand = np.argwhere(np.abs(rgb - anchor).max(axis=2) <= 24) - (ay, ax)
    ok = (cand[:, 0] >= 0) & (cand[:, 1] >= 0) & (cand[:, 0] + th <= h) & (cand[:, 1] + tw <= w)
    cand = cand[ok]
    if len(cand) == 0:
        return None
    # Vectorised pre-filter on a sparse grid of template pixels, so blue game pixels matching the
    # anchor (there were >5000 with water on screen, 2026-10-01) can't crowd the tab out.
    gy, gx = np.mgrid[0:th:4, 0:tw:8]
    gy, gx = gy.ravel(), gx.ravel()
    sample = rgb[cand[:, 0, None] + gy, cand[:, 1, None] + gx]  # (n, k, 3)
    coarse = np.abs(sample - tmpl[gy, gx]).mean(axis=(1, 2))
    best: tuple[int, int, float] | None = None
    for i in np.argsort(coarse)[:20]:
        oy, ox = int(cand[i, 0]), int(cand[i, 1])
        err = float(np.abs(rgb[oy : oy + th, ox : ox + tw] - tmpl).mean())
        if best is None or err < best[2]:
            best = (ox, oy, err)
    return best if best is not None and best[2] < 10 else None


def any_console(screen: Screen) -> bool:
    """A PowerShell console -- normal OR Administrator -- is visible. Never right-drag, click the
    world or press game keys then: a right-click in a console pastes the clipboard."""
    return find_console(screen) is not None or find_console(screen, admin=True) is not None


def minimize_consoles(agent: Agent, screen: Screen) -> None:
    """Minimise every visible PowerShell console (normal and Administrator): focus it by its tab,
    then Win+Down (a second press when the first only restored a maximised window)."""
    if any_console(screen):
        ensure_window("desktop", "minimize-consoles")
    for admin in (False, True):
        for _ in range(3):
            found = find_console(screen, admin)
            if found is None:
                break
            agent.click(found[0] + 40, found[1])  # the tab label: focuses, never pastes
            time.sleep(0.5)
            agent.chord("MetaLeft", "ArrowDown")
            time.sleep(0.8)
    if any_console(screen):
        raise Stop("a PowerShell console stays visible after Win+Down: minimise it by hand")


def focus_console(agent: Agent, screen: Screen, admin: bool = False) -> tuple[int, int]:
    """Click the console's own tab and re-verify it is the active window; its tab origin."""
    ensure_window("desktop", "console")
    log("focus_console: window ok; looking for the console")
    found = find_console(screen, admin)
    log(f"focus_console: found {found is not None}")
    if found is None:
        to_png(screen.full(), SHOTS / "console_missing.png")
        raise Stop("no active PowerShell console on screen: nothing typed")
    ox, oy, _ = found
    agent.click(ox + 75, oy + 9)  # its tab: focuses that window
    log("focus_console: clicked its tab")
    time.sleep(0.4)
    again = find_console(screen, admin)
    if again is None or abs(again[0] - ox) > 2 or abs(again[1] - oy) > 2:
        raise Stop("the console moved or lost focus after the click: nothing typed")
    return ox, oy


def console_type(
    agent: Agent, screen: Screen, command: str, admin: bool = False, *, prove: bool = True
) -> None:
    """Type a NON-secret command line into the verified console (it lands in PSReadLine history,
    so never a credential: use console_secret for those), and (prove) return only once it RAN."""
    focus_console(agent, screen, admin)
    type_line(agent, screen, command, prove=prove)


PROOF_TIMEOUT_S = 6.0


def proven_line(command: str, cells: int) -> str:
    """`cls`, the proof bar, then the command (its own leading `cls; ` dropped: it would wipe the
    bar the moment it is drawn)."""
    body = command.removeprefix("cls; ")
    return f"cls; Write-Host (' ' * {cells}) -BackgroundColor DarkMagenta; {body}"


def type_line(agent: Agent, screen: Screen, command: str, *, prove: bool = True) -> None:
    """One command line into the console ALREADY verified in front.

    Escape first: PSReadLine's RevertLine drops any half-typed input, even a multi-line `>>` one,
    and never touches a running command. On 2026-10-04 a long line cut off mid-typing left an
    unclosed `{`, and every later line was appended to it at a `>>` prompt and never ran -- tscon
    included, so the console showed the Windows sign-in screen.

    prove: the line starts with `cls` + a DarkMagenta bar of a width no bar on screen has now, and
    this returns only once that bar shows (a Stop otherwise): the line ran, not an older one."""
    # A window long enough for THIS line (~9 characters/s, 2026-10-05: a 30 s window expired
    # mid-line and the mux refused the rest) -- skipped while the interlock is green.
    ensure_window("desktop", "console-line", 120, min(110.0, 15 + len(command) / 7))
    agent.keys("Escape")
    time.sleep(0.2)
    if not prove:
        agent.type_text(command + "\n")
        return
    cells = fresh_cells(screen.full(), (MARKER_PROOF,))
    agent.type_text(proven_line(command, cells) + "\n")
    deadline = time.monotonic() + PROOF_TIMEOUT_S
    while time.monotonic() < deadline:
        time.sleep(0.4)
        if any(cells_match(n, cells) for _, n in marker_runs(screen.full(), MARKER_PROOF)):
            return
    to_png(screen.full(), SHOTS / "console_line_not_run.png")
    raise Stop("the console did not run the typed line (no fresh proof bar): stopped")


def console_secret(agent: Agent, screen: Screen, var: str, admin: bool = False) -> None:
    """Answer a `Read-Host -AsSecureString` prompt with the .env value of ``var``: sensitive input
    batches (the input log keeps counts only), the console re-verified every 4 characters. The
    value goes to the SecureString, never to a command line or the PSReadLine history."""
    value = env().get(var)
    if not value:
        raise Stop(f"{var} is not set in .env")
    ox, oy = focus_console(agent, screen, admin)

    def guard() -> None:
        now = find_console(screen, admin)
        if now is None or abs(now[0] - ox) > 2 or abs(now[1] - oy) > 2:
            raise Stop("the console lost focus while typing a secret: stopped")

    agent.type_secret(value, guard)
    guard()
    agent.keys("Enter")


def require_eng(screen: Screen) -> None:
    """The keyboard layout is ENG (the tray's indicator) -- or Stop. Fullscreen hides the tray
    while the client is in front: there the reading taken on the desktop just before the launch
    (launch_client, this process, within ENG_FRESH_S) stands for it; nothing else does."""
    global _ENG_AT
    if fullscreen() and taskbar_hidden(screen) is True:
        if _ENG_AT is not None and time.monotonic() - _ENG_AT <= ENG_FRESH_S:
            return
        raise Stop("fullscreen hides the tray: the keyboard layout was not read before the client "
                   "went fullscreen (`ro_agent.py recover` reads it before launching): no "
                   "credentials typed")  # fmt: skip
    if not is_state(screen, "eng"):
        to_png(screen.full(), SHOTS / "layout_not_eng.png")
        raise Stop("keyboard layout is not ENG (tray): no credentials typed")
    _ENG_AT = time.monotonic()


def fullscreen() -> bool:
    """The client fills the session: GAME_REGION at (0, 0) with the session's size. It draws no
    title bar (docs/planning/fullscreen-client.md; derived, never a setting of its own)."""
    x, y, w, h = real_game_region()
    return (x, y) == (0, 0) and (w, h) == desktop()


def taskbar_hidden(screen: Screen, after_ns: int | None = None) -> bool | None:
    """Fullscreen's proof that the client is in front: Windows hides its taskbar while a
    fullscreen window is in front. True: the frame's taskbar box is at least TASKBAR_ABSENT_MIN
    from the taskbar's template (the backend's foreground gate uses the same rule); False: the
    taskbar shows (or is unsure: fail closed); None: no template (calibrate it first)."""
    if not signature_path("taskbar").exists():
        return None
    return distance(screen, "taskbar", after_ns) >= TASKBAR_ABSENT_MIN


def activate_client(agent: Agent, screen: Screen) -> None:
    """Click the client's own title bar, then VERIFY it is the foreground window (its active
    title-bar signature; inactive scores ~30). Another window can cover the title bar: on
    2026-10-01 a console did, the click focused the console, and a camera rotation's
    right-clicks pasted the Windows clipboard onto its prompt (not executed; cleared).
    FULLSCREEN: no title bar to click, and a click anywhere else lands in the game (she would
    walk): only VERIFY -- the taskbar hidden on a fresh frame -- else Stop."""
    if fullscreen():
        hidden = taskbar_hidden(screen, after_ns=ns())
        if hidden is None:
            raise Stop("fullscreen: no taskbar template (`ro_agent.py calibrate taskbar 0 Y W 48` "
                       "while the desktop shows): stopped")  # fmt: skip
        if not hidden:
            to_png(screen.full(), SHOTS / "client_not_front.png")
            raise Stop("the fullscreen client is not in front (the taskbar shows): bring it to "
                       "the front with its taskbar button; stopped")  # fmt: skip
        return
    x, y, w, _ = real_game_region()  # its own title bar: real pixels
    clicked = ns()
    agent.click(x + w // 2, y - 15)
    if not signature_path("client_title_active").exists():
        time.sleep(0.4)
        return
    end = time.monotonic() + 2.0  # the title repaints a beat after focus returns
    while not is_state(screen, "client_title_active", after_ns=clicked):
        if time.monotonic() > end:
            to_png(screen.full(), SHOTS / "client_not_front.png")
            raise Stop("the client is not the foreground window after activation: stopped")
        time.sleep(0.2)


def login_guard(screen: Screen) -> Callable[[], None]:
    """The login dialog is visible and uncovered, and the layout is ENG -- or Stop."""

    def check() -> None:
        if not is_state(screen, "login"):
            to_png(screen.full(), SHOTS / "guard_login_not_visible.png")
            raise Stop("the login dialog is not visible (covered or gone): stopped typing")
        require_eng(screen)

    return check


def to_char_select(agent: Agent, screen: Screen, which: str) -> None:
    """Service select or login screen -> character select, credentials typed as sensitive."""
    ensure_window("login", "login")
    user, pw, _ = account(which)
    st = wait_state(screen, ["service_select", "login"], 10)
    if st == "service_select":
        # A freshly launched window takes its first click as activation: retry, bounded.
        for _ in range(3):
            agent.click(*layout("service_ok"))
            with contextlib.suppress(Stop):
                wait_state(screen, ["login"], 4)
                break
        else:
            raise Stop("the service-select OK did not register after 3 clicks")
    activate_client(agent, screen)
    guard = login_guard(screen)
    guard()
    # The ID field may hold a remembered id ("Save ID"): click it, go to the end, clear it.
    agent.click(*layout("id"))
    guard()
    agent.keys("End")
    agent.clear_field(24)
    agent.type_secret(user, guard)
    agent.click(*layout("password"))
    guard()
    agent.clear_field(32)
    agent.type_secret(pw, guard)
    guard()
    # Click "Login" rather than Enter: with Enter the client never dialled the char server
    # (2026-10-01, both agent accounts; a human clicking logged in fine).
    agent.click(*layout("login_button"))
    log(f"{which} credentials sent (sensitive)")
    # Choose the server AT ONCE: the client gives up ("Failed to Connect to Server", without even
    # dialling the char server) when no server is chosen within ~1-2 s of the list arriving.
    # A human picking it in 1.3 s worked; the agent waiting 2-19 s failed 8/8 (2026-10-01).
    # The list arrives ~10 ms after the login reply; RDP shows it at reduced quality first, so a
    # signature can lag by seconds. Click OK on a fixed delay instead.
    time.sleep(0.8)
    agent.click(*layout("server_ok"))
    wait_state(screen, ["char_select"], 20)
    log("character select")


def enter_game(
    agent: Agent, screen: Screen, which: str, char: str | None = None, *, any_char: bool = False
) -> None:
    """Enter the game from character select with the SELECTED slot (Enter). ``char``: the character
    that slot holds when it is not the account's .env one (the GM account's Rogue / Crusader
    slots; the caller clicked that slot first); it must be one of the account's characters.
    ``any_char`` (with no ``char``): accept whichever of the account's characters the selected
    slot holds. ``recover`` uses it: the client re-selects the LAST slot played, which on the GM
    account is usually the Rogue, not the .env character (2026-11-13: two false "never came
    online" failures, and a needless relaunch, while the Rogue was online)."""
    chars = account_chars(which)
    if any_char and char is None:
        wanted = set(chars)
        if not wanted:
            raise Stop(f"{which}: no character yet: run `ro_agent.py create-char {which}`")
    else:
        char = char or account(which)[2]
        if char not in chars:
            raise Stop(f"{which}: no character {char!r} yet: run `ro_agent.py create-char {which}`")
        wanted = {char}
    ensure_window("login", "enter-game")  # covers the gap until the session is attested
    agent.keys("Enter")
    end = time.monotonic() + 40
    came: list[str] = []
    while time.monotonic() < end:
        came = sorted(wanted & set(online_chars(which)))
        if came:
            break
        time.sleep(1)
    else:
        to_png(screen.full(), SHOTS / f"login_{which}_not_online.png")
        raise Stop(f"{which}: the character never came online=1")
    for _ in range(20):
        if not black(screen):
            log(f"{which} in game ({', '.join(came)}): online=1 and drawing")
            ensure_chat_window(agent, screen, f"enter_game:{which}")
            return
        time.sleep(1)
    raise Stop(f"{which}: online=1 but the game region stays black")


CHAT_SETTLE_S = 8.0  # after a login the HUD draws a moment after the scene (no window yet: wait)


def ensure_chat_window(agent: Agent, screen: Screen, why: str) -> None:
    """THE CHAT WINDOW CHECK (Batt 2026-11-05: "check the chat window first, every time we enter
    the game"): its standard place, size and padlock (chat_window.py), restored through the
    client's own controls; a failure stops here, before anything is typed. On 11-04 a moved
    window refused every typed line of the guest demo."""
    import chat_window

    end = time.monotonic() + CHAT_SETTLE_S
    while chat_window.check(screen) is None and time.monotonic() < end:
        time.sleep(0.5)  # the HUD not drawn yet; a hidden window stays None and ensure shows it
    try:
        chat_window.ensure(agent, screen, why=why)
    except chat_window.ChatWindowError as exc:
        raise Stop(str(exc)) from None


def create_char(agent: Agent, screen: Screen, which: str) -> None:
    """From character select: first slot -> Human, default look -> the name from .env -> Create."""
    _, _, char = account(which)
    if char in account_chars(which):
        log(f"{which}: {char!r} already exists")
        return
    ensure_window("login", "char-make")
    if not is_state(screen, "char_make"):
        wait_state(screen, ["char_select"], 10)
        agent.click(*layout("slot1"))
        wait_state(screen, ["char_make"], 10)
    agent.click(*layout("char_name"))
    agent.keys("End")
    agent.clear_field(24)
    agent.type_text(char)
    agent.click(*layout("char_create"))
    end = time.monotonic() + 15
    while char not in account_chars(which):
        if time.monotonic() > end:
            to_png(screen.full(), SHOTS / f"create_{which}_failed.png")
            raise Stop(f"{which}: {char!r} was not created")
        time.sleep(1)
    log(f"{which}: created {char!r}")


def login(agent: Agent, screen: Screen, which: str, *, any_char: bool = False) -> None:
    to_char_select(agent, screen, which)
    enter_game(agent, screen, which, any_char=any_char)


# Login-screen layout, client-relative (GAME_REGION origin), per client size, measured on the live
# client (docs/client/rathena-client.md "Agent automation"). Never guessed at runtime: an unknown
# size stops.
LAYOUTS: dict[tuple[int, int], dict[str, tuple[int, int]]] = {
    # 1024x768 window: client 1008 wide, bottom hidden by the taskbar (visible 721).
    (1008, 721): {
        "service_ok": (578, 560),
        "id": (461, 504),
        "password": (461, 526),
        "login_button": (604, 529),
        "server_row": (509, 404),
        "server_ok": (578, 560),
        "slot1": (101, 159),
        "char_name": (606, 358),
        "char_create": (798, 476),
    },
    # 800x664 window (2026-10-01): client 784x625 at (248,99), fully above the taskbar.
    (784, 625): {
        "service_ok": (466, 495),
        "id": (349, 439),
        "password": (349, 461),
        "login_button": (492, 463),
        "server_ok": (466, 495),
        "chat_input": (300, 613),
    },
    # 1296x759 window (2026-10-02, frozen for Phase 2): a 1:1 1280x720 client at (80,77) of the
    # 1440x900 session. The login dialogs sit +248,+60 from the 784x625 layout (the old signature
    # templates match there, distance ~2); the in-game windows keep their client positions.
    (1280, 720): {
        "service_ok": (714, 555),
        "id": (597, 499),
        "password": (597, 521),
        "login_button": (740, 523),
        "server_ok": (714, 555),
        # "chat_input": the chat window's standard place (chat_window.active().input_px, below)
        # character select / make (2026-10-05, the th client: the same kRO UI as the main one)
        "slot1": (231, 156),
        "char_name": (742, 354),
        "char_create": (934, 472),
    },
}


def layout(name: str) -> tuple[int, int]:
    _, _, w, h = game_region()
    if name == "chat_input" and (w, h) == (1280, 720):
        import chat_window  # the chat window's standard place (Batt 2026-11-05)

        return at(*chat_window.active().input_px)
    if name in DIALOG_OF_POINT and unmeasured_size():  # a found dialog: its vector, real pixels
        dialog = DIALOG_OF_POINT[name]
        rx, ry, rw, rh = real_game_region()
        if dialog not in _VECTORS:
            raise Stop(f"the {dialog} dialog was not found on this {rw}x{rh} client ({name})")
        bx, by = LAYOUTS[(1280, 720)][name]
        vx, vy = _VECTORS[dialog]
        return rx + bx + vx, ry + by + vy
    try:
        dx, dy = LAYOUTS[(w, h)][name]
    except KeyError:
        raise Stop(f"no measured layout for a {w}x{h} client ({name})") from None
    return at(dx, dy)


def account_chars(which: str) -> list[str]:
    user = account(which)[0]
    rows = db_query(
        "SELECT c.name FROM `char` c JOIN login l ON l.account_id = c.account_id "
        f"WHERE l.userid = {sql_str(user)};"
    )
    return [r[0] for r in rows]


CHAT_RECHECK_S = 2.0  # open_chat's re-judging window on fresh frames (2026-10-09)


def open_chat(agent: Agent, screen: Screen) -> None:
    """Make sure the chat input is open (Enter opens it), then click INTO it: an open but
    unfocused input (e.g. after clicks on the world) drops the first keystrokes -- a `@warp ...`
    went out as public chat without its `@warp ` (2026-10-01)."""
    # THE UI GATE first (Batt 2026-10-09, walk@17 item 6, mandatory): no Enter into an unknown
    # state -- an NPC dialog / menu or an open window is closed by known steps, or this stops.
    import ui_gate

    ui_gate.ensure_clear(agent, screen, why="open_chat")
    # THE CHAT WINDOW CHECK (Batt 2026-11-05) before the Enter: a window moved or resized since the
    # last line is put back first (one read and no input when it is in place)
    ensure_chat_window(agent, screen, "open_chat")
    # Enter toggles an EMPTY input. The signature can miss an input that IS open (the blinking text
    # cursor, 2026-10-02): then the first Enter closed it -- so toggle up to twice.
    pressed: int | None = None
    for _ in range(2):
        if is_state(screen, "chat_open", after_ns=pressed):
            break
        pressed = ns()
        agent.keys("Enter")
        time.sleep(1.0)
    # judged on a frame decoded AFTER the last Enter: a frozen frame is FrozenStream, not "closed"
    if not is_state(screen, "chat_open", after_ns=pressed):
        # RECOVERY (Batt 2026-10-09; three held-out runs stopped here): re-judge on FRESH frames for
        # up to CHAT_RECHECK_S, no key sent -- a progressive RDP frame still refining, or a scene
        # change behind the translucent chat window. The probe of the same day showed the client's
        # repeat refusal leaves the input open and empty (chat_repeat_probe.py chat), so it is not
        # that. A real failure saves the frame and the distances, then stops as before.
        dists: list[float] = []
        end = time.monotonic() + CHAT_RECHECK_S
        while time.monotonic() < end:
            d = distance(screen, "chat_open")
            dists.append(round(float(d), 2))
            if d <= SIG_MATCH:
                break
            time.sleep(0.25)
        else:
            shot = to_png(screen.full(), Path("/dev/shm/poring-lab-tmp/chat-open-fail")
                          / f"{time.strftime('%Y%m%d-%H%M%S')}.png")  # fmt: skip
            raise Stop(f"the chat input did not open: nothing typed (chat_open distances {dists}, "
                       f"match <= {SIG_MATCH}; frame {shot})")  # fmt: skip
        log(f"chat input recognised on a re-check (distances {dists})")
    agent.click(*layout("chat_input"))
    time.sleep(0.2)


def chat_line(agent: Agent, screen: Screen, text: str, *, reason: str | None = None,
              on_refuse: str = "raise") -> bool:  # fmt: skip
    """Open the chat input if it is closed, type, send (Enter). Every line passes the TYPING GUARD
    first (scripts/chat_guard.py, ADR-0020 #10, Batt 2026-10-09): no filler line, no 3rd identical
    line in a row, a minimum interval, /where once per need within the run's budget, every /where
    logged with ``reason``. A refusal raises chat_guard.ChatRefused, or with ``on_refuse="skip"``
    returns False; the guard never waits a line out or types another one instead."""
    import chat_guard

    if not chat_guard.before_typing(text, reason=reason, on_refuse=on_refuse):
        log(f"chat guard: refused {text!r} (not typed)")
        return False
    open_chat(agent, screen)
    agent.type_text(text + "\n")
    return True


def gm(agent: Agent, screen: Screen, command: str) -> bool:
    """Type one GM line. True when typed; False when the typing guard skipped it as an identical
    REPEAT (the only refusal that does not stop the caller): a caller that records the line as
    sent must check this (2026-11-05: collect_v2 recorded an @monsterignore the guard had
    skipped)."""
    if not command.startswith("@"):
        raise Stop("GM commands start with @")
    _, _, char = account("gm")
    if char not in online_chars("gm"):
        raise Stop("the GM character is not online=1 on our rAthena: nothing sent")
    if black(screen):
        raise Stop("the game region is black: nothing sent")
    record = {"t_mono_ns": ns(), "t_wall": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "cmd": command}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with (STATE_DIR / "gm.jsonl").open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    activate_client(agent, screen)  # a Windows popup can take focus at any time
    import chat_guard

    try:
        chat_line(agent, screen, command)
    except chat_guard.ChatRefused as exc:
        # only an identical REPEAT is skipped (the walk harness's @killmonster2 before every
        # route: the client drops such repeats anyway); any other refusal stops the caller
        if exc.rule != "repeat":
            raise Stop(str(exc)) from None
        log(f"gm: {command} NOT typed ({exc})")
        return False
    log(f"gm: {command}")
    return True


def say(agent: Agent, screen: Screen, which: str, text: str, thai_keys: bool) -> None:
    _, _, char = account(which)
    if char not in online_chars(which):
        raise Stop(f"{which} is not online=1: nothing sent")
    activate_client(agent, screen)
    import chat_guard

    chat_guard.before_typing(text)  # the TYPING GUARD (ADR-0020 #10): raises ChatRefused
    open_chat(agent, screen)  # typed while closed, the letters are hotkeys (2026-10-01)
    if thai_keys:
        require_eng(screen)
        agent.chord("MetaLeft", "Space")  # next input language (ENG -> Thai Kedmanee)
        time.sleep(0.8)
        if is_state(screen, "eng"):
            raise Stop("layout did not switch to Thai: nothing typed")
        try:
            agent.type_text(text + "\n")
        finally:
            agent.chord("MetaLeft", "Space")
            time.sleep(0.8)
        require_eng(screen)
    else:
        agent.type_text(text + "\n")
    log(f"said ({'thai keys' if thai_keys else 'ascii'}) as {which}")


# The "Ragnarok Offline" desktop shortcut (C:\\RO-rAthena\\PoringLab.cmd); its icon position depends
# on the Windows account's desktop layout: RO_SHORTCUT="x,y" in .env.
SHORTCUT = (112, 140)


def shortcut_xy() -> tuple[int, int]:
    raw = env().get(PROFILE.shortcut_env, "")
    if not raw:
        return SHORTCUT
    x, y = (int(v) for v in raw.split(","))
    return x, y


def close_client(agent: Agent, screen: Screen) -> None:  # noqa: ARG001
    """Alt+F4 on the client itself (a lost-D3D client still takes window messages); confirm the
    quit prompt if it shows. No PowerShell: Run-dialog PowerShell trips Defender's ClickFix
    detection (2026-10-01, severity 5, the processes were killed)."""
    ensure_window("login", "close")  # the session may already be gone (a lost-D3D client)
    activate_client(agent, screen)
    agent.chord("AltLeft", "F4")  # paced (CHORD_STEP_S): one instantaneous batch is ignored
    time.sleep(3)
    log("close requested (Alt+F4)")


def client_absent(screen: Screen) -> bool:
    """No client window at all: the strip its title bar would occupy (above the game region) is
    the bare black desktop. A lost-D3D client renders a black GAME region but still draws its
    title bar, so this never mistakes it for a closed one (that would launch a second client).
    FULLSCREEN: there is no strip above it. Absent only when PROVEN: the taskbar shows and the
    client's own taskbar button (``taskbar_client_icon``, cut while it runs behind another
    window) is nowhere on it. In front, minimized-and-unsure, or no icon template: not absent."""
    if fullscreen():
        if taskbar_hidden(screen) is not False:
            return False  # in front, or unsure
        if not signature_path("taskbar_client_icon").exists():
            return False  # cannot tell: never launch a second client
        return not taskbar_icon_found(screen)
    x, y, w, _ = real_game_region()
    _, img = screen.grab(x, y - 30, w, 26)
    px = img[::2, ::4, :3].astype(np.uint16)
    luma = (px[..., 0] * 29 + px[..., 1] * 150 + px[..., 2] * 77) >> 8
    return bool((luma < 10).mean() >= 0.98)


def taskbar_icon_found(screen: Screen) -> bool:
    """The client's taskbar button anywhere along the taskbar row (Windows moves it with the
    other running programs): its template slid across the row at its saved height, 2 px steps."""
    tpl = np.load(signature_path("taskbar_client_icon")).astype(np.float32)
    bx, by, bw, bh = region_for("taskbar_client_icon")
    w = desktop()[0]
    _, row = screen.grab(0, by, w, bh)
    for x0 in range(0, max(1, w - bw + 1), 2):
        cur = grey_thumb(np.ascontiguousarray(row[:, x0 : x0 + bw]))
        if cur.shape == tpl.shape and float(np.abs(cur - tpl).mean()) <= SIG_MATCH:
            return True
    return False


def launch_client(agent: Agent, screen: Screen) -> None:
    """Double-click the desktop shortcut (a plain user action; it starts PoringLab.exe with
    __COMPAT_LAYER=RunAsInvoker, i.e. non-elevated)."""

    def visible() -> bool:  # the icon, plain or selected (highlighted after a double-click)
        return is_state(screen, "shortcut_icon") or (
            signature_path("shortcut_icon_sel").exists() and is_state(screen, "shortcut_icon_sel")
        )

    ensure_window("login", "launch")
    if not visible():
        # Win+D is typing outside the client: the typing-only foreground gate (2026-10-06) lets
        # it through only in a DESKTOP window (Batt's exemption for the agent's own desktop work)
        ensure_window("desktop", "show-desktop")
        agent.chord("MetaLeft", "KeyD")  # show the desktop: windows may cover the icon
        time.sleep(1.5)
    if not visible():
        to_png(screen.full(), SHOTS / "shortcut_not_visible.png")
        raise Stop("the desktop shortcut is not visible: no double-click")
    if fullscreen():  # the tray is about to vanish under the client: read the layout now
        require_eng(screen)
    x, y = shortcut_xy()
    agent.move(x, y)
    time.sleep(0.1)
    for action in ("down", "up", "down", "up"):
        agent.send([{"type": "mouse_button", "t_mono_ns": ns(), "frame_id": -1, "button": "left",
                     "action": action, "x": x / desktop()[0], "y": y / desktop()[1]}])  # fmt: skip
        time.sleep(0.04)
    log("launch requested (desktop shortcut, non-elevated)")
    wait_state(screen, ["service_select", "login"], 90)


# The durable lab-client watcher (Batt, 2026-10-05): a scheduled task as the standard user runs
# %USERPROFILE%\poring-lab-watch\labwatch.ps1 (every 500 ms: a lab-client exe with a non-lab TCP
# connection is killed and logged; an `alive` line every ~60 s). Read-only status line:
WATCH_STATUS = (
    "$i = Get-ScheduledTaskInfo -TaskName 'poring-lab watch'; "
    "'task ' + (Get-ScheduledTask -TaskName 'poring-lab watch').State + ' last=' + $i.LastRunTime"
    " + ' result=' + $i.LastTaskResult; "
    "Get-Content (Join-Path $env:USERPROFILE 'poring-lab-watch\\watch.log') -Tail 3; "
    "'KILLED lines: ' + @(Select-String -Path (Join-Path $env:USERPROFILE "
    "'poring-lab-watch\\watch.log') -Pattern 'KILLED').Count; 'now ' + (Get-Date -f s)"
)

# The agent's own terminal (Batt, 2026-10-03): a desktop shortcut "poring-lab shell" ->
# `wt.exe -w new new-tab --title "poring-lab shell" --suppressApplicationTitle -d C:\RO-rAthena
# powershell.exe -NoLogo`, NOT "Run as administrator" (checked in the .lnk at creation). The Run
# dialog stays forbidden (Defender ClickFix); elevated consoles stay Batt's (UAC).
# SHELL_SHORTCUT="x,y" in .env.
SHELL_SHORTCUT = (37, 645)


def elevation_check(cells: int) -> str:
    """The check line; its marker is ``cells`` wide, a width no bar on screen has (fresh_cells),
    so a marker left by an earlier check can never pass for this one (2026-10-04: a stale green
    bar passed three checks typed into a `>>` prompt that never ran them)."""
    return (
        "cls; if (([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::"
        "GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) "
        f"{{ Write-Host (' ' * {cells}) -BackgroundColor DarkRed }} "
        f"else {{ Write-Host (' ' * {cells}) -BackgroundColor DarkGreen }}"
    )


MARKER_RED, MARKER_GREEN = (197, 15, 31), (19, 161, 14)  # Campbell DarkRed / DarkGreen
MARKER_PROOF = (136, 23, 152)  # Campbell DarkMagenta: type_line's proof bar, never a verdict colour
CELL_W = 9  # px per cell in the agent's shell: its 40-cell marker measured 360 px (2026-10-04)
MARKER_CELLS = range(24, 61)  # proof/marker widths: >= 150 px, and inside the console window


def shell_shortcut_xy() -> tuple[int, int]:
    raw = env().get("SHELL_SHORTCUT", "")
    if not raw:
        return SHELL_SHORTCUT
    x, y = (int(v) for v in raw.split(","))
    return x, y


def find_shell(screen: Screen) -> tuple[int, int, float] | None:
    """The ACTIVE "poring-lab shell" tab (its own templates only: RDP and stream), or None."""
    paths = [
        p for n in template_names(SHELL_TEMPLATE) if (p := STATE_DIR / "signatures" / n).exists()
    ]
    if not paths:
        raise Stop("no poring-lab shell template: run `ro_agent.py calibrate-shell` once")
    rgb = screen.full()[:, :, 2::-1].astype(np.int16)
    best: tuple[int, int, float] | None = None
    for path in paths:
        found = _match_console(rgb, np.load(path).astype(np.int16))
        if found is not None and (best is None or found[2] < best[2]):
            best = found
    return best


def marker_runs(
    bgra: np.ndarray, colour: tuple[int, int, int], min_run: int = 150
) -> list[tuple[int, int]]:
    """(row, px) of the longest solid run of ``colour`` in every row that has one >= min_run."""
    hit = np.abs(bgra[:, :, 2::-1].astype(np.int16) - np.array(colour)).max(axis=2) <= 30
    out: list[tuple[int, int]] = []
    for y in np.nonzero(hit.sum(axis=1) >= min_run)[0]:
        row = np.concatenate(([0], hit[y].astype(np.int8), [0]))
        edges = np.flatnonzero(np.diff(row))
        longest = int((edges[1::2] - edges[::2]).max(initial=0))
        if longest >= min_run:
            out.append((int(y), longest))
    return out


def cells_match(px: int, cells: int) -> bool:
    return abs(px - cells * CELL_W) <= CELL_W // 2


def fresh_cells(
    bgra: np.ndarray, colours: tuple[tuple[int, int, int], ...], rng: random.Random | None = None
) -> int:
    """A marker width (cells) within 1 cell of no bar of ``colours`` now on screen: a bar of this
    width can only come from the line about to be typed."""
    taken = {round(px / CELL_W) for c in colours for _, px in marker_runs(bgra, c)}
    free = [n for n in MARKER_CELLS if all(abs(n - t) > 1 for t in taken)]
    if not free:
        raise Stop("no free marker width (the console is full of bars): stopped")
    return (rng or random).choice(free)


def marker_colour(bgra: np.ndarray, min_run: int = 150, cells: int | None = None) -> str | None:
    """'red' / 'green' if a horizontal run of >= min_run marker pixels is on screen (the newest,
    bottom-most wins), else None. ``cells``: only a run of exactly that width counts."""
    found: tuple[int, str] | None = None
    for name, colour in (("red", MARKER_RED), ("green", MARKER_GREEN)):
        for y, px in marker_runs(bgra, colour, min_run):
            if cells is not None and not cells_match(px, cells):
                continue
            if found is None or y > found[0]:
                found = (y, name)
    return found[1] if found else None


def open_terminal(agent: Agent, screen: Screen) -> tuple[int, int]:
    """The agent's own NON-elevated terminal, in front: reuse a visible "poring-lab shell" tab, or
    double-click the shortcut and wait for one. Any mismatch stops (Batt: stop and ask)."""
    ensure_window("desktop", "open-terminal")
    found = find_shell(screen)
    if found is None:

        def visible() -> bool:
            return is_state(screen, "shell_shortcut_icon") or (
                signature_path("shell_shortcut_icon_sel").exists()
                and is_state(screen, "shell_shortcut_icon_sel")
            )

        if not visible():
            to_png(screen.full(), SHOTS / "shell_shortcut_not_visible.png")
            raise Stop("the 'poring-lab shell' shortcut is not visible: nothing clicked")
        x, y = shell_shortcut_xy()
        agent.move(x, y)
        time.sleep(0.1)
        for action in ("down", "up", "down", "up"):
            agent.send([{"type": "mouse_button", "t_mono_ns": ns(), "frame_id": -1,
                         "button": "left", "action": action, "x": x / desktop()[0],
                         "y": y / desktop()[1]}])  # fmt: skip
            time.sleep(0.04)
        deadline = time.monotonic() + 20
        while found is None and time.monotonic() < deadline:
            time.sleep(1)
            found = find_shell(screen)
        if found is None:
            to_png(screen.full(), SHOTS / "shell_not_found.png")
            raise Stop("no window titled 'poring-lab shell' within 20 s: nothing typed")
        log("opened 'poring-lab shell' (desktop shortcut)")
        opened_new = True
    else:
        opened_new = False
    ox, oy, _ = found
    agent.click(ox + 75, oy + 9)  # its tab: focuses that window
    time.sleep(0.4)
    again = find_shell(screen)
    if again is None or abs(again[0] - ox) > 2 or abs(again[1] - oy) > 2:
        raise Stop("'poring-lab shell' moved or lost focus after the click: nothing typed")
    agent.keys("Escape")  # drop any half-typed input first (type_line's docstring)
    time.sleep(0.2)
    cells = fresh_cells(screen.full(), (MARKER_RED, MARKER_GREEN))
    agent.type_text(elevation_check(cells) + "\n")
    deadline = time.monotonic() + 10
    colour = None
    while colour is None and time.monotonic() < deadline:
        time.sleep(0.8)
        colour = marker_colour(screen.full(), cells=cells)
    if colour != "green":
        to_png(screen.full(), SHOTS / "shell_elevation_check.png")
        raise Stop(f"'poring-lab shell' is not verified non-elevated (marker {colour}): stop")
    log("'poring-lab shell' is in front and NOT elevated")
    if opened_new:  # an older one was minimised or hidden: keep exactly one (Batt, 2026-10-03)
        type_line(agent, screen, CLOSE_EXTRA_SHELLS)
        time.sleep(3)
        log("closed any other 'poring-lab shell' window (see the shell for the count)")
    return ox, oy


# Exactly one agent terminal (Batt, 2026-10-03): open_terminal opens a NEW window whenever the old
# one is minimised. Typed into the verified front shell: every OTHER top-level window titled
# exactly "poring-lab shell" gets WM_CLOSE (a one-tab Windows Terminal window closes); Batt's own
# consoles have other titles and the foreground window is never touched. Then the count.
CLOSE_EXTRA_SHELLS = (
    "cls; Add-Type -TypeDefinition 'using System;using System.Text;using System.Runtime."
    "InteropServices;public class PlShells{public delegate bool P(IntPtr h,IntPtr l);"
    '[DllImport("user32.dll")]public static extern bool EnumWindows(P p,IntPtr l);'
    '[DllImport("user32.dll")]public static extern int GetWindowText(IntPtr h,StringBuilder s,'
    'int n);[DllImport("user32.dll")]public static extern IntPtr GetForegroundWindow();'
    '[DllImport("user32.dll")]public static extern bool PostMessage(IntPtr h,uint m,IntPtr w,'
    "IntPtr l);}' -ErrorAction SilentlyContinue; "
    "function Get-PlShells { $hs = New-Object System.Collections.ArrayList; "
    "[void][PlShells]::EnumWindows({ param($h, $l) $sb = New-Object System.Text.StringBuilder 256; "
    "[void][PlShells]::GetWindowText($h, $sb, 256); "
    "if ($sb.ToString() -ceq 'poring-lab shell') { [void]$hs.Add($h) }; $true }, [IntPtr]::Zero); "
    "$hs }; $fg = [PlShells]::GetForegroundWindow(); $before = @(Get-PlShells); "
    "$before | Where-Object { $_ -ne $fg } | ForEach-Object { "
    "[void][PlShells]::PostMessage($_, 0x10, [IntPtr]::Zero, [IntPtr]::Zero) }; "
    "Start-Sleep 2; 'poring-lab shell windows: ' + $before.Count + ' -> ' + @(Get-PlShells).Count"
)


def file_check_command(path: str) -> str:
    """The read-only check typed before Batt is asked to drop a file (Batt, 2026-10-03)."""
    if "'" in path:
        raise Stop("a path with a single quote: check it by hand")
    return (
        f"cls; $p = '{path}'; $i = Get-Item -LiteralPath $p -ErrorAction Stop; "
        "'{0}  {1:N0} B  {2}  sha256 {3}' -f $i.FullName, $i.Length, $i.LastWriteTime, "
        "(Get-FileHash -LiteralPath $p).Hash"
    )


def copy_item_line(path: str) -> str:
    """The ready line Batt pastes into HIS console to drop the file (never the agent's)."""
    return f"Copy-Item -LiteralPath '{path}' -Destination " + r"'\\tsclient\transfer\'"


def calibrate_shell(screen: Screen, stream: bool = False) -> None:
    """Once, with a fresh 'poring-lab shell' window ACTIVE and its shortcut visible: save its tab
    template (located by the PowerShell tab icon) and the shortcut icon's signature. ``stream``:
    the console stream's copy of the tab template only (cut while streaming)."""
    rgb = screen.full()[:, :, 2::-1]
    ps = np.load(STATE_DIR / "signatures" / "ps_tab_template.npy")
    icon_only = ps[:, :24].astype(np.int16)  # the PowerShell icon (columns 3-18), no title text
    found = _match_console(rgb.astype(np.int16), icon_only)
    if found is None:
        raise Stop("no active PowerShell tab icon on screen: open 'poring-lab shell' first")
    ox, oy, _ = found
    h, w = ps.shape[:2]
    crop = np.ascontiguousarray(rgb[oy : oy + h, ox : ox + w]).astype(np.uint8)
    name = template_names(SHELL_TEMPLATE)[1 if stream else 0]
    np.save(STATE_DIR / "signatures" / name, crop)
    if stream:
        log(f"stream shell tab template saved at ({ox},{oy}) as {name}")
        return
    to_png(np.dstack([crop[..., ::-1], np.full(crop.shape[:2], 255, np.uint8)]),
           SHOTS / "sig_shell_tab.png")  # fmt: skip
    for state in ("shell_shortcut_icon_sel",):
        calibrate(screen, state)
    log(f"shell tab template saved at ({ox},{oy}); icon signature saved")


def recover(which: str, retries: int = 2, agent_id: str = "ro_agent-recover") -> None:
    """Close, relaunch and log in ``which``. ``retries``: further attempts after a failure (the
    auto recover after a sniffer restart passes 0: one attempt, no loop). ``agent_id`` names the
    connection in the backend's input log (agent_hello) and on the console."""
    for attempt in range(1, retries + 2):
        try:
            with session(agent_id) as (agent, screen):
                agent.wait_for_human()
                if client_absent(screen):  # 2026-10-04: a previous attempt had closed it already
                    log(f"recover attempt {attempt}: no client window: launching")
                else:
                    log(f"recover attempt {attempt}: closing the client")
                    close_client(agent, screen)
                launch_client(agent, screen)
                login(agent, screen, which, any_char=True)  # the remembered slot (2026-11-13)
                return
        except Stop as exc:
            log(f"recover attempt {attempt} failed: {exc}")
            if attempt > retries or "ASSIST" in str(exc) or "refused" in str(exc):
                raise
            time.sleep(10)


def status() -> None:
    out: dict[str, Any] = {"online_total": any_online()}
    for which in ("player", "gm"):
        with contextlib.suppress(Stop):
            out[f"{which}_online"] = bool(online_chars(which))
    screen = Screen()
    try:
        states = sorted(p.stem for p in (STATE_DIR / "signatures").glob("*.npy"))
        dist = {}
        for s in states:
            with contextlib.suppress(Stop):
                dist[s] = round(distance(screen, s), 1)
        out["signature_distance"] = dist
    finally:
        screen.close()
    print(json.dumps(out, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("cmd")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--right", action="store_true")
    ap.add_argument("--admin", action="store_true", help="console: the Administrator tab template")
    ap.add_argument("--abs", action="store_true", help="click: desktop pixels, not client-relative")
    ap.add_argument("--thai-keys", action="store_true")
    ap.add_argument("--stream", action="store_true", help="calibrate-shell: the stream's copy")
    ap.add_argument("--as", dest="who", default="gm", choices=["player", "gm"])
    ap.add_argument("--retries", type=int, default=2, help="recover: attempts after a failure")
    ap.add_argument(
        "--agent-id",
        default="ro_agent-recover",
        help="recover: the agent id the backend logs (auto_recover: guarded_build)",
    )
    ap.add_argument(
        "--profile", choices=sorted(PROFILES), default=None,
        help="client profile: kro (default) or th (C:\\RO-rAthena-th + rathena-th)",
    )  # fmt: skip
    a = ap.parse_args()
    use_profile(a.profile)
    cmd, args = a.cmd, a.args
    if cmd == "status":
        return status()
    if cmd in ("shot", "crop", "calibrate", "where"):
        screen = Screen()
        try:
            if cmd == "shot":
                print(to_png(screen.full(), SHOTS / f"{args[0]}.png"))
            elif cmd == "crop":  # crop NAME X Y W H (desktop pixels)
                x, y, w, h = (int(v) for v in args[1:5])
                print(to_png(screen.grab(x, y, w, h)[1], SHOTS / f"{args[0]}.png"))
            elif cmd == "calibrate":
                calibrate(screen, args[0], [int(v) for v in args[1:5]] if len(args) == 5 else None)
            else:
                for st in sorted(p.stem for p in (STATE_DIR / "signatures").glob("*.npy")):
                    print(f"{st:16} {distance(screen, st):6.1f}")
        finally:
            screen.close()
        return None
    if cmd == "find-panels":  # 4f: find the windows now (pixels only; prints numbers)
        screen = Screen()
        try:
            st = find_panels(screen)
        finally:
            screen.close()
        print(json.dumps({"found": st["found"], "moved": st["moved"], "missing": st["missing"]}))
        for ln in panels_words(st):
            print(ln)
        return None
    if cmd == "recover":
        if a.retries < 0 or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", a.agent_id):
            raise Stop("recover: --retries >= 0, --agent-id letters/digits/_.- (<= 64)")
        return recover(args[0] if args else "player", a.retries, a.agent_id)
    with session() as (agent, screen):
        if cmd == "click":
            xy = (int(args[0]), int(args[1]))
            agent.click(*(xy if a.abs else at(*xy)), "right" if a.right else "left")
        elif cmd == "open-terminal":
            open_terminal(agent, screen)
        elif cmd == "calibrate-shell":
            calibrate_shell(screen, stream=a.stream)
        elif cmd == "close-extra-shells":
            open_terminal(agent, screen)
            console_type(agent, screen, CLOSE_EXTRA_SHELLS)
            time.sleep(4)
            print(to_png(screen.full(), SHOTS / "close_extra_shells.png"))
        elif cmd == "minimize-consoles":
            minimize_consoles(agent, screen)
        elif cmd == "watch-status":  # the durable watcher (scheduled task; Batt 2026-10-05)
            open_terminal(agent, screen)
            console_type(agent, screen, WATCH_STATUS)
            time.sleep(3)
            print(to_png(screen.full(), SHOTS / "watch_status.png"))
        elif cmd == "file-check":  # file-check "<windows path>": BEFORE asking Batt for a drop
            open_terminal(agent, screen)
            console_type(agent, screen, file_check_command(args[0]))
            time.sleep(4)
            print(to_png(screen.full(), SHOTS / "file_check.png"))
            print("for Batt's console: " + copy_item_line(args[0]))
        elif cmd == "drag":
            x1, y1, x2, y2 = (int(v) for v in args[:4])
            p1, p2 = ((x1, y1), (x2, y2)) if a.abs else (at(x1, y1), at(x2, y2))
            agent.drag(*p1, *p2, "right" if a.right else "left")
        elif cmd == "keys":
            agent.keys(*args)
        elif cmd == "chord":
            agent.chord(*args)
        elif cmd == "type":
            agent.type_text(args[0].replace("\\n", "\n"))
        elif cmd == "login":
            login(agent, screen, args[0])
        elif cmd == "to-char-select":
            to_char_select(agent, screen, args[0])
        elif cmd == "create-char":
            create_char(agent, screen, args[0])
        elif cmd == "enter-game":
            enter_game(agent, screen, args[0])
        elif cmd == "console-secret":  # console-secret VAR [--admin]
            console_secret(agent, screen, args[0], a.admin)
        elif cmd == "console":  # console "<command>" [shot-name] [wait-s] [--admin]
            console_type(agent, screen, args[0], a.admin)
            time.sleep(float(args[2]) if len(args) > 2 else 2.0)
            if len(args) > 1 and args[1] != "-":
                to_png(screen.full(), SHOTS / f"{args[1]}.png")
        elif cmd == "gm":
            gm(agent, screen, args[0])
        elif cmd == "say":
            say(agent, screen, a.who, args[0], a.thai_keys)
        elif cmd == "close":
            close_client(agent, screen)
        elif cmd == "launch":
            launch_client(agent, screen)
        else:
            raise Stop(f"unknown command {cmd}")
    return None


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        print(f"STOP: {stop}", file=sys.stderr)
        sys.exit(3)
