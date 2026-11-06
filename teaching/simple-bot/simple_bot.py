#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10,<3.15"
# dependencies = [
#     "numpy",
#     "opencv-python; sys_platform != 'linux'",
#     "opencv-python-headless; sys_platform == 'linux'",
#     "onnxruntime",
#     "mss",
#     "psutil",
#     "pywin32; sys_platform == 'win32'",
# ]
# ///
"""simple_bot.py: a SMALL vision bot for Ragnarok Online, written to be read and learned from.

WHAT IT DOES
    It plays on prt_fild08 (the field next to Prontera: Poring, Lunatic, Fabre, Pupa, Creamy) the
    way a person does: it LOOKS at the screen and MOVES the mouse. It never reads the game's memory
    and never touches its network traffic. It walks around, attacks the nearest monster, and picks
    up what the monster drops.

THE PIPELINE (every frame, many times per second)

    +-----------+      +-----------+      +-------------+      +-----------+
    |  CAPTURE  | ---> |  DETECT   | ---> |   DECIDE    | ---> |    ACT    |
    | screenshot|      | boxes on  |      | SEARCH /    |      | mouse     |
    | of the    |      | monsters, |      | ATTACK /    |      | clicks    |
    | game      |      | players,  |      | LOOT: where |      | (--act    |
    | (pixels)  |      | NPCs      |      | to click    |      |  only)    |
    +-----------+      +-----------+      +-------------+      +-----------+
          |                  |                   |                    |
          +------------------+---------+---------+--------------------+
                                       |
                    DRAW: the boxes, the planned line and the HUD
                    (the "bot view" window; with --overlay also over the game)

MODES (uv reads the "# /// script" block above and installs the libraries by itself)

    uv run simple_bot.py --replay samples --model v1.onnx                 images, no game
    uv run simple_bot.py --replay samples --model v1.onnx --save-dir out  save PNGs instead
    uv run simple_bot.py --replay samples --detector color                classic HSV, no model
    uv run simple_bot.py --watch --model v1.onnx                          live game, DRAW ONLY
    uv run simple_bot.py --watch --model v1.onnx --overlay                ... and over the game
    uv run simple_bot.py --act --model v1.onnx                            live game, CLICKS too

SAFETY: FOR YOUR OWN LOCAL SERVER ONLY. --act clicks only while the client is connected to
loopback / private (LAN) addresses and only while the client window is in front. On official
servers a bot breaks the terms of service, and their anti-cheat (GameGuard) blocks it anyway.

THE MODEL: poring-lab's "v1" YOLO detector exported to ONNX (classes player, monster, npc). It was
trained on the lab client's sprites at a 1280 x 720 client area: another client, resolution or
zoom can detect worse. Creamy flies (its sprite floats) and is often missed.

HOW TO READ THIS FILE: top to bottom follows the pipeline. Section 1 holds every setting; sections
2-7 are the stages; section 8 draws; section 9 runs it all.
"""

from __future__ import annotations

import argparse
import contextlib
import ipaddress
import json
import logging
import math
import random
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

# Only numpy and the standard library are imported up here. The heavy libraries (cv2 = OpenCV,
# onnxruntime, mss, the win32 modules) are imported INSIDE the functions that need them ("lazy"
# imports). So the pure logic can be imported and tested anywhere: no model, screen or Windows.


# LOGS (--logs): what the bot is doing, step by step, each line with the time. Python's standard
# `logging` module: every message has a LEVEL -- DEBUG (small details), INFO (the steps), WARNING
# (something is off). Without --logs only warnings and errors show.
LOG = logging.getLogger("simple_bot")
LOG_EVERY_S = 1.0  # --logs: one summary line per second from the live loop (not every frame)


def setup_logs(on: bool, file: str | None = None) -> None:
    """Turn the logs on (--logs) and/or copy them into a file (--log-file, which implies --logs).
    The lines look like:  14:03:07.512 INFO    window found: 'Ragnarok' (pid 4321)"""
    LOG.handlers.clear()
    LOG.propagate = False  # do not print every line twice through Python's root logger
    LOG.setLevel(logging.DEBUG if (on or file) else logging.WARNING)
    fmt = logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)-7s %(message)s", "%H:%M:%S")
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if file:
        handlers.append(logging.FileHandler(file, encoding="utf-8"))
    for h in handlers:
        h.setFormatter(fmt)
        LOG.addHandler(h)


def say(msg: str) -> None:
    """A progress line for the person at the screen: through the logs when --logs is on (so it also
    lands in --log-file, with the time), else a plain print."""
    if LOG.isEnabledFor(logging.INFO):
        LOG.info(msg)
    else:
        print(msg, flush=True)


# =================================================================================================
# 1. SETTINGS: what the bot assumes about the screen, the model and the timings
#    Units: pixels (px) of the client area, x to the right, y DOWN; times in seconds (s).
# =================================================================================================

CLIENT_W, CLIENT_H = 1280, 720  # set the client to windowed 1280 x 720 (the model's training size)

# The character's FEET. RO keeps your character at the centre of the client area, so this is a
# constant, not a detection. To calibrate it for your client: stand still, take a screenshot of the
# client area (or run --watch and look at the white cross in the bot view), and read the pixel
# where the feet touch the ground. On the lab client it is within ~10 px of the centre.
CHAR_X, CHAR_Y = 640, 360
# A "player" box whose feet are this close to CHAR is OUR OWN character. (The lab's v1 model was
# trained WITHOUT boxes on the bot's own character, so it rarely draws one; another model might.)
SELF_RADIUS = 30.0

# The client's UI windows as (x0, y0, x1, y1), measured on the lab's layout at 1280 x 720.
# A monster behind a window cannot be clicked (the click lands on the window), so the bot drops
# every detection whose centre lies in one, and never clicks inside one. Moved or resized a window
# in your client? Measure it on a screenshot and change it here.
UI_ZONES: dict[str, tuple[int, int, int, int]] = {
    "basic_info": (0, 0, 222, 145),  # top-left: name, HP / SP, levels, weight
    "hotkey_bar": (228, 0, 522, 36),  # top: the skill / item bar (F12 cycles its rows)
    "minimap": (1128, 8, 1280, 165),  # top-right: the map and its coordinates line
    "chat": (0, 578, 602, 720),  # bottom-left: the chat window and its input bar
}
EDGE_PX = 12  # never click this close to the client area's edge

# The detector (the v1 model)
CLASS_NAMES = ("player", "monster", "npc")  # the model's class ids 0, 1, 2 in this order
CONF = 0.25  # keep a box only if the model is at least 25 % sure
IOU = 0.5  # NMS: two boxes of one class overlapping by >= 50 % are the same object
# onnxruntime's Windows builds need Microsoft's C++ runtime (msvcp140.dll) 14.40 or newer (Visual
# Studio 2022 17.10+). With an older one, `import onnxruntime` itself dies with "Windows fatal
# exception: access violation" (seen on a class PC, 2026-11-06). The fix: install the latest
# "Microsoft Visual C++ Redistributable (x64)" once.
CPP_RUNTIME_MIN = (14, 40)
CPP_RUNTIME_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
PAD_GREY = 114  # the letterbox padding colour YOLO models are trained with

# The decide step's timings and distances
WANDER_MIN_PX, WANDER_MAX_PX = 150, 250  # SEARCH walks to a random point this far away
WANDER_EVERY_S = (2.0, 3.0)  # ... and picks a new one after a random 2-3 s
RECLICK_S = 1.0  # ATTACK clicks the target again this often while it stays
TRACK_PX = 90.0  # the target in the next frame = the nearest monster within this of its last feet
LOST_S = 1.5  # the target unseen this long = it died (or walked away): go LOOT
ATTACK_GIVE_UP_S = 20.0  # hitting one target longer than this: give up, SEARCH again
LOOT_GAP_S = 0.5  # LOOT clicks the dead monster's feet twice, this far apart
LOOT_DONE_S = 0.8  # ... then waits this long for the pick-up walk before SEARCH

# Lessons from the lab's bot (each one cost us real runs, so here they are rules):
# - NORTH COLUMN: a WALK click straight north of the character, in its own column, makes the client
#   send NO move request (the character just stands there). So a ground click with
#   |dx| < NORTH_COLUMN_PX and dy < 0 is moved sideways by NORTH_SHIFT_PX.
NORTH_COLUMN_PX, NORTH_SHIFT_PX = 10, 30
# - TWO MOTIONS PER CLICK: the client ignores a "cold jump" click (the cursor teleports onto the
#   target and presses at once), and it draws its own cursor only where a SECOND motion leaves the
#   mouse. So every click is: move 10-15 px next to the target, wait ~80 ms, move onto the target,
#   wait ~250 ms, then press and release.
APPROACH_PX = (10.0, 15.0)
APPROACH_S, SETTLE_S, PRESS_S = 0.08, 0.25, 0.05

# The --act safety gate (the same idea as the lab's "environment interlock")
NET_CHECK_S = 5.0  # re-check the client's network connections this often
VK_F12 = 0x7B  # the stop key's Windows code (RO also toggles its hotkey bar on F12: harmless)
CORNER_PX = 3  # the mouse inside the screen's top-left 3 x 3 px = stop at once (a fail-safe)

SEARCH, ATTACK, LOOT = "SEARCH", "ATTACK", "LOOT"  # the decide step's three states


# =================================================================================================
# 2. BOXES: one detection, and the small geometry helpers every stage uses
# =================================================================================================


@dataclass(frozen=True)
class Box:
    """One detected unit: its rectangle in client pixels, how sure the model is, and its class.

    x0, y0 = the top-left corner, x1, y1 = the bottom-right corner (px); score 0..1; cls is one of
    CLASS_NAMES ("player", "monster", "npc"). frozen=True makes it read-only, like a tuple.
    """

    x0: float
    y0: float
    x1: float
    y1: float
    score: float
    cls: str

    @property
    def centre(self) -> tuple[float, float]:
        """The middle of the box (px). Used to test whether a UI window covers the unit."""
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    @property
    def foot(self) -> tuple[float, float]:
        """The unit's feet: the bottom centre of its box (px). Where it stands on the ground, so
        distances are measured feet to feet, and where its items fall when it dies."""
        return ((self.x0 + self.x1) / 2, self.y1)

    @property
    def hit_point(self) -> tuple[int, int]:
        """Where to click to hit it (px): the LOWER CENTRE, inside the sprite near its feet. A
        click on the box's very bottom edge can miss the sprite and land on the ground behind it,
        which is a walk, not an attack."""
        return (round((self.x0 + self.x1) / 2), round(self.y0 + 0.7 * (self.y1 - self.y0)))


def dist(p: tuple[float, float], q: tuple[float, float]) -> float:
    """The straight-line distance between two points (px), Pythagoras."""
    return math.hypot(p[0] - q[0], p[1] - q[1])


def overlaps(a: Box, b: Box) -> bool:
    """True when two boxes share at least some area (the overlap's width AND height are > 0)."""
    return min(a.x1, b.x1) > max(a.x0, b.x0) and min(a.y1, b.y1) > max(a.y0, b.y0)


def zone_at(x: float, y: float, zones: dict[str, tuple[int, int, int, int]] = UI_ZONES) -> str:
    """The name of the UI window covering point (x, y), or "" when none does.

    Lab lesson: the UI windows sit ON TOP of the game world. A monster under one cannot be clicked
    (the click goes to the window), and a click on a window can press its buttons."""
    for name, (x0, y0, x1, y1) in zones.items():
        if x0 <= x < x1 and y0 <= y < y1:
            return name
    return ""


def clickable(pt: tuple[float, float], w: int = CLIENT_W, h: int = CLIENT_H) -> bool:
    """May the bot click point `pt` (px)? Only inside the client area (EDGE_PX away from its
    border) and never on a UI window. Every click passes this check, whatever chose it."""
    x, y = pt
    inside = EDGE_PX <= x < w - EDGE_PX and EDGE_PX <= y < h - EDGE_PX
    return inside and not zone_at(x, y)


def is_self(b: Box, char: tuple[float, float] = (CHAR_X, CHAR_Y)) -> bool:
    """Is this box OUR OWN character? The model sees us as a "player" standing on CHAR."""
    return b.cls == "player" and dist(b.foot, char) <= SELF_RADIUS


# =================================================================================================
# 3. CAPTURE: find the client window and copy its pixels (Windows only)
# =================================================================================================


def set_dpi_aware() -> None:
    """Ask Windows for REAL pixels. With display scaling (125 %, 150 %) Windows otherwise reports
    "scaled" coordinates, and the screenshot, the window position and the clicks would disagree.
    Tries the newest API first, then older ones for older Windows versions."""
    import ctypes

    try:  # -4 = DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 (Windows 10 1703+)
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:  # 2 = PROCESS_PER_MONITOR_DPI_AWARE (Windows 8.1+)
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()  # Vista / 7


class ClientWindow:
    """The Ragnarok client's window, found by (part of) its title.

    Gives the window's position on the screen, its process id (pid: needed by the safety gate to
    look at the client's network connections) and whether it is the window in front."""

    def __init__(self, title: str) -> None:
        """Find exactly ONE visible window whose title contains `title` (any case). None, or more
        than one (e.g. a web page about Ragnarok), stops the program with a clear message: the bot
        must never guess which window it is looking at."""
        import win32gui
        import win32process

        found: list[tuple[int, str]] = []

        def visit(hwnd: int, _: Any) -> bool:
            """Called by EnumWindows once per top-level window (hwnd = its handle, a number)."""
            text = win32gui.GetWindowText(hwnd)
            if win32gui.IsWindowVisible(hwnd) and title.lower() in text.lower():
                found.append((hwnd, text))
            return True  # True = keep going through the windows

        win32gui.EnumWindows(visit, None)
        if not found:
            raise SystemExit(
                f"no visible window with '{title}' in its title: start the client "
                "(windowed), or give its title with --title"
            )
        if len(found) > 1:
            names = "; ".join(repr(t) for _, t in found)
            raise SystemExit(
                f"{len(found)} windows match '{title}' ({names}): give a more exact --title"
            )
        self.hwnd, self.title = found[0]
        # GetWindowThreadProcessId returns (thread id, process id): we want the process
        self.pid = int(win32process.GetWindowThreadProcessId(self.hwnd)[1])
        LOG.info("window found: %r (hwnd %s, pid %s)", self.title, self.hwnd, self.pid)

    def rect(self) -> tuple[int, int, int, int]:
        """The CLIENT AREA (the game picture, without title bar and borders) on the screen:
        (left, top, width, height) in screen px. Asked every frame: the window may move."""
        import win32gui

        _, _, w, h = win32gui.GetClientRect(self.hwnd)  # (0, 0, width, height)
        left, top = win32gui.ClientToScreen(self.hwnd, (0, 0))  # its top-left on the screen
        return int(left), int(top), int(w), int(h)

    def alive(self) -> bool:
        """True while the window still exists (the client was not closed)."""
        import win32gui

        return bool(win32gui.IsWindow(self.hwnd))

    def in_front(self) -> bool:
        """True when the client is the FOREGROUND window (the one that gets the keyboard and our
        clicks). The bot never clicks while another window is in front."""
        import win32gui

        return bool(win32gui.GetForegroundWindow() == self.hwnd)


class Grabber:
    """Copies a rectangle of the screen into a numpy picture, with mss (a fast screenshot
    library: one grab of 1280 x 720 takes a few milliseconds)."""

    def __init__(self) -> None:
        """Open mss once; it is reused for every frame."""
        import mss

        self.sct = mss.mss()

    def grab(self, left: int, top: int, w: int, h: int) -> np.ndarray:
        """Screen px rectangle -> a (h, w, 3) uint8 picture in BGR order (OpenCV's order)."""
        shot = self.sct.grab({"left": left, "top": top, "width": w, "height": h})
        # mss gives 4 channels B, G, R, A (A = alpha, unused): keep the first three
        return np.ascontiguousarray(np.asarray(shot)[:, :, :3])


# =================================================================================================
# 4. DETECT (the model): letterbox -> YOLO (onnxruntime) -> decode -> NMS
#    Ported from poring-lab's own detector (scripts/detector_worker.py): same maths, same numbers.
# =================================================================================================


def letterbox(img: np.ndarray, size: tuple[int, int]) -> tuple[np.ndarray, float, int, int]:
    """Fit a picture into the model's input size without stretching it ("letterbox", like a wide
    film on a TV: the free space is filled with bars, here grey 114).

    Input: img = a (h, w, 3) BGR picture; size = the model's (H, W) = (736, 1280) for v1.
    Output: the model's input tensor (1, 3, H, W) float32, RGB, values 0..1; the scale s; and the
    padding (left, top) in px, which `unletterbox` needs to map boxes back onto the picture.

    Example: a 1280 x 720 frame into 1280 x 736 is NOT scaled (s = 1): 8 grey rows go on top and 8
    at the bottom. YOLO wants sizes that are multiples of 32, and 720 is not (736 = 23 x 32)."""
    h, w = img.shape[:2]
    s = min(size[0] / h, size[1] / w)  # the biggest scale that fits BOTH ways
    nh, nw = round(h * s), round(w * s)  # the scaled picture's size (fits inside H x W)
    if (nh, nw) != (h, w):  # resize, nearest neighbour, in plain numpy (no OpenCV needed):
        ys = (np.arange(nh) / s).astype(int).clip(0, h - 1)  # for each new row: its source row
        xs = (np.arange(nw) / s).astype(int).clip(0, w - 1)  # for each new column: its source
        img = img[ys][:, xs]
    top, left = (size[0] - nh) // 2, (size[1] - nw) // 2  # half the free space on each side
    canvas = np.full((size[0], size[1], 3), PAD_GREY, np.uint8)  # all grey ...
    canvas[top : top + nh, left : left + nw] = img  # ... with the picture in the middle
    # BGR -> RGB (the model was trained on RGB); (H, W, C) -> (C, H, W); add a batch axis of 1;
    # bytes 0..255 -> floats 0..1
    x = canvas[..., ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
    return np.ascontiguousarray(x), s, left, top


def unletterbox(boxes: np.ndarray, s: float, left: int, top: int) -> np.ndarray:
    """Map boxes from the MODEL's pixels back to the picture's pixels: undo what letterbox did,
    in reverse order (first remove the padding, then divide by the scale).

    Input: boxes (n, 4) as x0, y0, x1, y1 in model px; s, left, top from `letterbox`.
    Output: (n, 4) float64 in picture px."""
    out = np.asarray(boxes, np.float64).copy()
    out[:, [0, 2]] = (out[:, [0, 2]] - left) / s  # the x columns
    out[:, [1, 3]] = (out[:, [1, 3]] - top) / s  # the y columns
    return out


def iou_one(box: np.ndarray, rest: np.ndarray) -> np.ndarray:
    """IoU = Intersection over Union: how much two boxes overlap, 0 (apart) .. 1 (identical).
    It is the shared area divided by the area the two cover together.

    Input: box (4,) and rest (n, 4), both x0, y0, x1, y1. Output: (n,) IoU of `box` with each."""
    xx0 = np.maximum(box[0], rest[:, 0])  # the shared rectangle: the larger left/top edges ...
    yy0 = np.maximum(box[1], rest[:, 1])
    xx1 = np.minimum(box[2], rest[:, 2])  # ... and the smaller right/bottom edges
    yy1 = np.minimum(box[3], rest[:, 3])
    inter = np.clip(xx1 - xx0, 0, None) * np.clip(yy1 - yy0, 0, None)  # 0 if they do not touch
    area_a = (box[2] - box[0]) * (box[3] - box[1])
    area_b = (rest[:, 2] - rest[:, 0]) * (rest[:, 3] - rest[:, 1])
    return np.asarray(inter / (area_a + area_b - inter + 1e-9))  # 1e-9: never divide by zero


def nms(boxes: np.ndarray, scores: np.ndarray, iou: float = IOU) -> list[int]:
    """Non-Maximum Suppression. The model proposes MANY overlapping boxes for each object (one
    per nearby grid cell). NMS keeps the best one per object:
      1. take the highest-scoring box left, and keep it;
      2. throw away every other box that overlaps it by IoU >= `iou` (the same object);
      3. repeat with what is left.
    Input: boxes (n, 4), scores (n,). Output: the indices of the boxes kept, best first."""
    order = np.argsort(-np.asarray(scores))  # indices sorted by score, highest first
    keep: list[int] = []
    while len(order):
        i = int(order[0])  # the best box still in the race
        keep.append(i)
        rest = order[1:]
        if not len(rest):
            break
        order = rest[iou_one(boxes[i], boxes[rest]) < iou]  # keep only boxes NOT overlapping it
    return keep


def decode(
    out: np.ndarray,
    s: float,
    left: int,
    top: int,
    conf: float = CONF,
    iou: float = IOU,
    names: Sequence[str] = CLASS_NAMES,
) -> list[Box]:
    """Turn the model's raw output into Box objects in picture px.

    The YOLO output has the shape (1, 4 + number of classes, N). For v1: (1, 7, 19320).
      - N = 19320 candidate boxes: one per cell of three grids laid over the 1280 x 736 input,
        with cells of 8, 16 and 32 px (160 x 92 + 80 x 46 + 40 x 23 = 19320). Small grids find
        small things, coarse grids big things.
      - rows 0-3: the box as centre x, centre y, width, height (model px);
      - rows 4-6: one score 0..1 per class (player, monster, npc).
    Steps: pick each candidate's best class; drop the ones below `conf`; turn centre + size into
    corners; map them back to the picture (`unletterbox`); NMS per class."""
    p = np.asarray(out)[0].T  # (N, 4 + nc): one row per candidate is easier to read
    if p.shape[1] != 4 + len(names):
        raise ValueError(f"the model has {p.shape[1] - 4} classes, the bot knows {len(names)}")
    cls_scores = p[:, 4:]
    cls = cls_scores.argmax(1)  # each candidate's most likely class ...
    score = cls_scores.max(1)  # ... and how sure the model is about it
    m = score >= conf  # a True/False mask: the candidates we keep
    if not m.any():
        return []
    cx, cy, w, h = p[m, 0], p[m, 1], p[m, 2], p[m, 3]
    corners = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], 1)  # centre -> corners
    xyxy = unletterbox(corners, s, left, top)
    result: list[Box] = []
    for c in np.unique(cls[m]):  # NMS separately per class: a player may stand on a monster
        idx = np.nonzero(cls[m] == c)[0]
        for k in nms(xyxy[idx], score[m][idx], iou):
            j = idx[k]
            x0, y0, x1, y1 = (round(float(v), 1) for v in xyxy[j])
            result.append(Box(x0, y0, x1, y1, round(float(score[m][j]), 3), names[int(c)]))
    return result


class OnnxDetector:
    """The v1 YOLO model, run on the CPU with onnxruntime (no GPU needed; ~0.1-0.5 s per frame,
    depending on the CPU). ONNX is a file format that many programs can run a trained model from."""

    label = "v1 YOLO (onnx)"

    def __init__(self, model: Path, conf: float = CONF, iou: float = IOU, threads: int = 0) -> None:
        """Load the model file. `threads` = CPU threads for it (0 = let onnxruntime choose)."""
        import onnxruntime as ort

        opts = ort.SessionOptions()
        if threads > 0:
            opts.intra_op_num_threads = threads
        LOG.info("onnxruntime %s: creating the session for %s", ort.__version__, model)
        t0 = time.perf_counter()
        self.sess = ort.InferenceSession(str(model), opts, providers=["CPUExecutionProvider"])
        inp = self.sess.get_inputs()[0]
        self.name = inp.name
        self.size = (int(inp.shape[2]), int(inp.shape[3]))  # (H, W) = (736, 1280) for v1
        self.conf, self.iou = conf, iou
        LOG.info("model loaded in %.0f ms: input %s %s, conf %.2f", (time.perf_counter() - t0)
                 * 1e3, self.name, list(inp.shape), conf)  # fmt: skip

    def detect(self, frame: np.ndarray) -> list[Box]:
        """A BGR picture (h, w, 3) -> the boxes found on it, in its own px."""
        x, s, left, top = letterbox(frame, self.size)
        out = self.sess.run(None, {self.name: x})[0]  # the model's raw output, see `decode`
        return decode(out, s, left, top, self.conf, self.iou)


# =================================================================================================
# 5. DETECT (classic image processing): a colour threshold, no model. ROUGH, for the basics.
# =================================================================================================


class ColorDetector:
    """Find Porings by their PINK colour, with four classic steps:

      1. BGR -> HSV. HSV splits a colour into Hue (which colour: red, green ... as an angle),
         Saturation (how strong: grey .. vivid) and Value (how bright). "Pink" is then a simple
         range, whatever the light.
      2. Threshold: keep the pixels whose H, S, V all lie in the range -> a black/white "mask".
      3. Clean the mask: OPEN removes white specks, CLOSE fills small black holes.
      4. Contours: the outlines of the white blobs. Keep the blobs of a Poring's size and shape.

    How the range was chosen: we read the H, S, V of Poring pixels on the sample pictures. A
    Poring's body is H 0-6 (pink sits next to red, at the START of the hue circle), S 70-135,
    V 170-255. Our own character's red hair and skin have the same hues but are darker or
    stronger, so V >= 190 and S <= 145 leave them out. On the 20 samples this range finds 21
    Poring blobs and no false ones; widen it to V >= 170, H <= 12, S <= 150 and it also "finds"
    the character in 9 of 20 pictures. Try it: change the numbers, run --replay, look.

    Its limits ARE the lesson: it only knows Porings (no Lunatic, Fabre, Pupa), anything pink
    fools it, a Poring in shadow is missed, and it knows no players or NPCs. The YOLO model learned
    all of that from thousands of labelled pictures instead of hand-picked numbers.
    """

    label = "colour (HSV, rough)"
    LOW, HIGH = (0, 50, 190), (10, 145, 255)  # H, S, V; OpenCV's hue is 0..179 (degrees / 2)
    MIN_AREA, MAX_AREA = 150, 4000  # a blob's size in px at 1280 x 720
    MIN_RATIO, MAX_RATIO = 0.5, 2.5  # width / height: a Poring is a round blob, not a line

    def detect(self, frame: np.ndarray) -> list[Box]:
        """A BGR picture (h, w, 3) -> "monster" boxes around pink blobs. score = how much of its
        box the blob fills (0..1): a crude stand-in for a model's confidence."""
        import cv2

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)  # step 1
        mask = cv2.inRange(hsv, np.array(self.LOW), np.array(self.HIGH))  # step 2: 255 = pink
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)  # step 3
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)  # step 4
        boxes = []
        for c in contours:
            area = cv2.contourArea(c)
            if not self.MIN_AREA <= area <= self.MAX_AREA:
                continue
            x, y, w, h = cv2.boundingRect(c)  # the smallest upright box around the blob
            if not self.MIN_RATIO <= w / h <= self.MAX_RATIO:
                continue
            boxes.append(Box(x, y, x + w, y + h, round(area / (w * h), 2), "monster"))
        return boxes


# =================================================================================================
# 6. DECIDE: which boxes may be targets, where to walk, and the state machine
#    SEARCH -> ATTACK -> LOOT -> SEARCH
# =================================================================================================


def sort_boxes(
    boxes: Sequence[Box],
    char: tuple[float, float] = (CHAR_X, CHAR_Y),
    w: int = CLIENT_W,
    h: int = CLIENT_H,
) -> tuple[list[Box], list[tuple[Box, str]]]:
    """Split the monster boxes into TARGETS (may be clicked) and DROPPED ones (with the reason,
    drawn grey in the bot view). Rules:
      - only "monster" boxes are ever targets (never a player, never an NPC);
      - not under a UI window (its centre), and its hit point must be clickable;
      - never a monster TOUCHING another player's or an NPC's box: the click could hit the person
        or open the NPC's dialog instead.
    Our own character's box does not count as "another player": monsters that hit us touch it."""
    others = [b for b in boxes if b.cls in ("player", "npc") and not is_self(b, char)]
    targets: list[Box] = []
    dropped: list[tuple[Box, str]] = []
    for b in boxes:
        if b.cls != "monster":
            continue
        zone = zone_at(*b.centre)
        touching = next((o for o in others if overlaps(b, o)), None)  # the first one, or None
        if zone:
            dropped.append((b, f"under {zone}"))
        elif not clickable(b.hit_point, w, h):
            dropped.append((b, "click point off limits"))
        elif touching is not None:
            dropped.append((b, f"touches a {touching.cls}"))
        else:
            targets.append(b)
    return targets, dropped


def choose_target(boxes: Sequence[Box], char: tuple[float, float] = (CHAR_X, CHAR_Y)) -> Box | None:
    """The NEAREST allowed monster (distance from our feet to its feet, px), or None."""
    targets, _ = sort_boxes(boxes, char)
    return min(targets, key=lambda b: dist(b.foot, char), default=None)


def avoid_north_column(
    pt: tuple[float, float], char: tuple[float, float] = (CHAR_X, CHAR_Y)
) -> tuple[int, int]:
    """Lab lesson: a WALK click straight NORTH of the character (in its own column, above it) makes
    the client send no move request at all. So such a point is moved NORTH_SHIFT_PX sideways, away
    from the column. Used for ground clicks (wander, loot). A click ON a monster is an attack
    request, not a walk, so attack clicks are not shifted (that would pull the character off the
    monster it is hitting). Input / output: a point in px."""
    dx, dy = pt[0] - char[0], pt[1] - char[1]  # dy < 0 = above us (y grows downwards)
    if abs(dx) < NORTH_COLUMN_PX and dy < 0:
        return (round(pt[0] + (NORTH_SHIFT_PX if dx >= 0 else -NORTH_SHIFT_PX)), round(pt[1]))
    return (round(pt[0]), round(pt[1]))


def wander_point(
    rng: random.Random,
    char: tuple[float, float] = (CHAR_X, CHAR_Y),
    w: int = CLIENT_W,
    h: int = CLIENT_H,
) -> tuple[int, int] | None:
    """SEARCH's walk target: a random clickable point WANDER_MIN_PX..WANDER_MAX_PX from the
    character, in a random direction (north column dodged). None if 50 tries found nothing.
    `rng` is the random generator: a fixed seed gives the same points every run (tests)."""
    for _ in range(50):
        a = rng.uniform(0, 2 * math.pi)  # a direction (radians) ...
        r = rng.uniform(WANDER_MIN_PX, WANDER_MAX_PX)  # ... and a distance (px)
        pt = avoid_north_column((char[0] + r * math.cos(a), char[1] + r * math.sin(a)), char)
        if clickable(pt, w, h):
            return pt
    return None


@dataclass
class Decision:
    """What the decide step wants THIS frame (the act step clicks it, the draw step shows it).

    state: SEARCH / ATTACK / LOOT; clicks: points to click now, in order (px, often none);
    line: (from the character, to where it is heading) for the drawing; target: the monster
    chosen (or None); note: a few words for the HUD."""

    state: str
    clicks: list[tuple[int, int]] = field(default_factory=list)
    line: tuple[tuple[int, int], tuple[int, int]] | None = None
    target: Box | None = None
    note: str = ""


class Decider:
    """The bot's "brain": a state machine. It gets the boxes of ONE frame and the time (s), keeps
    a little memory between frames, and returns a Decision.

        SEARCH  no monster: walk to a random point 150-250 px away; a new point every 2-3 s.
           | a monster is seen
           v
        ATTACK  the nearest allowed monster: click its lower centre, again every ~1 s.
           | the target unseen for > 1.5 s (it died)
           v
        LOOT    click its last feet twice, 0.5 s apart (pick up the drops), then back to SEARCH.

    A state machine keeps behaviour simple to follow: in each state only a few things can happen.
    """

    def __init__(
        self,
        rng: random.Random | None = None,
        char: tuple[float, float] = (CHAR_X, CHAR_Y),
        w: int = CLIENT_W,
        h: int = CLIENT_H,
    ) -> None:
        """rng: the random generator (wander points); char: our feet (px); w, h: the client size."""
        self.rng = rng or random.Random()
        self.char = char
        self.me = (round(char[0]), round(char[1]))  # our feet as whole pixels (lines start here)
        self.w, self.h = w, h
        self.state = SEARCH
        self.wander_pt: tuple[int, int] | None = None  # SEARCH: the current walk target
        self.wander_due = 0.0  # SEARCH: when to pick a new one (s)
        self.target: Box | None = None  # ATTACK: the monster we are hitting
        self.attack_since = self.last_seen = self.last_click = 0.0  # ATTACK's clocks (s)
        self.loot_pt: tuple[int, int] = self.me  # LOOT: where the target last stood
        self.loot_clicks = 0  # LOOT: clicks done (0, 1, 2)
        self.loot_next = 0.0  # LOOT: when the next step is due (s)

    def step(self, boxes: Sequence[Box], now: float) -> Decision:
        """One decision: the boxes seen now, the time now (s) -> what to do."""
        targets, _ = sort_boxes(boxes, self.char, self.w, self.h)
        if self.state == SEARCH:
            if targets:
                return self._start_attack(min(targets, key=lambda b: dist(b.foot, self.char)), now)
            return self._search(now)
        if self.state == ATTACK:
            d = self._attack(targets, now)
            if d is not None:
                return d  # still attacking (None = it just switched to LOOT)
        return self._loot(boxes, now)

    def _search(self, now: float) -> Decision:
        """SEARCH: keep walking to a random point; click a new one when the old one is due."""
        clicks: list[tuple[int, int]] = []
        if self.wander_pt is None or now >= self.wander_due:
            self.wander_pt = wander_point(self.rng, self.char, self.w, self.h)
            self.wander_due = now + self.rng.uniform(*WANDER_EVERY_S)
            if self.wander_pt is not None:
                clicks = [self.wander_pt]
        line = (self.me, self.wander_pt) if self.wander_pt else None
        return Decision(SEARCH, clicks, line, None, "no monster: wander")

    def _start_attack(self, b: Box, now: float) -> Decision:
        """SEARCH -> ATTACK: remember the target and click it at once."""
        self.state, self.target = ATTACK, b
        self.attack_since = self.last_seen = self.last_click = now
        return Decision(ATTACK, [b.hit_point], (self.me, b.hit_point), b, "new target")

    def _attack(self, targets: list[Box], now: float) -> Decision | None:
        """ATTACK: find our target again in this frame and click it every RECLICK_S; switch to
        LOOT (return None) once it has been unseen for LOST_S.

        "Find it again" (tracking, the simplest kind): the boxes of two frames carry no names, so
        the target is the monster whose feet are nearest to where its feet were, within TRACK_PX.
        It moves a little between frames, and the whole picture scrolls while we walk."""
        assert self.target is not None
        last = self.target
        near = [b for b in targets if dist(b.foot, last.foot) <= TRACK_PX]
        if near:
            b = min(near, key=lambda c: dist(c.foot, last.foot))
            self.target, self.last_seen = b, now
            if now - self.attack_since > ATTACK_GIVE_UP_S:  # cannot reach it? try something else
                self.state, self.wander_pt = SEARCH, None
                return Decision(SEARCH, [], None, None, "gave up on this target")
            clicks = []
            if now - self.last_click >= RECLICK_S:
                clicks, self.last_click = [b.hit_point], now
            return Decision(ATTACK, clicks, (self.me, b.hit_point), b, "hitting")
        if now - self.last_seen <= LOST_S:  # hidden for a moment (an effect, a missed frame)
            return Decision(
                ATTACK,
                [],
                (self.me, last.hit_point),
                last,
                f"target unseen {now - self.last_seen:.1f} s",
            )
        # Gone for good: it died (or walked off). Its drops lie at its feet. The picture scrolls
        # with the character, so a screen point is the same ground point only while we stand
        # still (we do: we were hitting it). A ground click, so: dodge the north column.
        self.state = LOOT
        self.loot_pt = avoid_north_column(last.foot, self.char)
        self.loot_clicks, self.loot_next = 0, now
        return None

    def _loot(self, boxes: Sequence[Box], now: float) -> Decision:
        """LOOT: click the drop point twice (LOOT_GAP_S apart; one click picks up one item), wait
        LOOT_DONE_S for the walk, then back to SEARCH and decide this same frame again."""
        if self.loot_clicks >= 2 and now >= self.loot_next:
            self.state, self.target, self.wander_pt = SEARCH, None, None
            return self.step(boxes, now)
        clicks: list[tuple[int, int]] = []
        if self.loot_clicks < 2 and now >= self.loot_next:
            if clickable(self.loot_pt, self.w, self.h):
                clicks = [self.loot_pt]
            self.loot_clicks += 1
            self.loot_next = now + (LOOT_GAP_S if self.loot_clicks < 2 else LOOT_DONE_S)
        return Decision(
            LOOT, clicks, (self.me, self.loot_pt), self.target, f"pick up ({self.loot_clicks}/2)"
        )


# =================================================================================================
# 7. ACT: the safety gate, then mouse input (Windows only)
# =================================================================================================


def remote_is_local(ip: str) -> bool:
    """Is this network address on YOUR machine or YOUR home network?

    loopback = this same computer (127.0.0.1, ::1); private = a home / school network (10.x.x.x,
    172.16-31.x.x, 192.168.x.x, and their IPv6 cousins). Everything else is the internet."""
    try:
        a = ipaddress.ip_address(ip.split("%")[0])  # "%..." = an IPv6 interface name: drop it
    except ValueError:
        return False  # not an address at all: never "local"
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped is not None:
        a = a.ipv4_mapped  # "::ffff:127.0.0.1" is the IPv4 address 127.0.0.1 in IPv6 clothing
    return a.is_loopback or a.is_private


def check_connections(remotes: Sequence[str]) -> tuple[bool, str]:
    """THE LOCAL-SERVER CHECK. Input: the remote addresses of the client's ESTABLISHED TCP
    connections (its open links to servers). Output: (ok, why).

    ok needs at least one connection (the client is logged in to something) and ALL of them local:
    a single internet address means a server that is not yours, and the bot must not click."""
    if not remotes:
        return False, "the client has no ESTABLISHED connection (log in to your local server)"
    public = sorted({r for r in remotes if not remote_is_local(r)})
    if public:
        return (
            False,
            f"the client talks to a PUBLIC address ({', '.join(public)}): not a local server",
        )
    return True, f"{len(remotes)} connection(s), all local"


def in_corner(x: int, y: int) -> bool:
    """The fail-safe: the mouse pushed into the primary screen's top-left corner (px)."""
    return 0 <= x < CORNER_PX and 0 <= y < CORNER_PX


def live_refusal(mode: str, platform: str = sys.platform) -> str:
    """Why a live mode (--watch / --act) cannot run on this machine; "" = it can.
    The live modes need Windows (the window, the capture and the mouse calls are Windows APIs)."""
    if platform != "win32":
        return (
            f"--{mode} refused: the live modes run only on Windows, with the Ragnarok client "
            f"of YOUR OWN local server in a window (this machine is '{platform}'). "
            "Try the pipeline on images instead: --replay DIR."
        )
    return ""


ACT_BANNER = """
==================================================================================
 simple_bot --act  :  FOR YOUR OWN LOCAL SERVER ONLY
 - it clicks only while the client talks to loopback / private (LAN) addresses
   and only while the client window is in front (click the game to give it focus)
 - stop: press F12, or push the mouse into the screen's top-left corner
 - official servers: a bot breaks their terms of service (and GameGuard blocks it)
==================================================================================
"""


class SafetyGate:
    """The --act safety gate. The bot may click only while ALL of this holds:
      - the client window still exists and is the FOREGROUND window (checked before every click);
      - every ESTABLISHED TCP connection of the client's process goes to a loopback / private
        address (re-checked every NET_CHECK_S; a failure ends the run at once);
    and the run ENDS on F12, on the mouse in the screen's top-left corner, or after --minutes."""

    def __init__(self, window: ClientWindow, minutes: float) -> None:
        """window: the client; minutes: the run's time limit."""
        self.window = window
        self.deadline = time.monotonic() + minutes * 60  # monotonic = a clock that never jumps
        self.net_ok, self.net_why, self.net_at = False, "not checked yet", -1e9

    def remotes(self) -> list[str]:
        """The remote IP addresses of the client's ESTABLISHED TCP connections (psutil lists every
        connection of the machine; we keep the ones that belong to the client's pid)."""
        import psutil

        return [
            c.raddr.ip
            for c in psutil.net_connections(kind="tcp")
            if c.pid == self.window.pid and c.status == psutil.CONN_ESTABLISHED and c.raddr
        ]

    def check_network(self, force: bool = False) -> tuple[bool, str]:
        """(ok, why) of the local-server check, re-done when the last one is NET_CHECK_S old."""
        now = time.monotonic()
        if force or now - self.net_at >= NET_CHECK_S:
            remotes = self.remotes()
            self.net_ok, self.net_why = check_connections(remotes)
            self.net_at = now
            LOG.debug("network check: %s -> %s (%s)", sorted(set(remotes)) or "none",
                      "ok" if self.net_ok else "REFUSED", self.net_why)  # fmt: skip
        return self.net_ok, self.net_why

    def stop_reason(self) -> str:
        """A reason to END the run now, or "" to keep going."""
        import win32api

        if win32api.GetAsyncKeyState(VK_F12) & 0x8000:  # bit 15 set = the key is down right now
            return "F12 pressed"
        if in_corner(*win32api.GetCursorPos()):
            return "mouse in the top-left corner (fail-safe)"
        if time.monotonic() > self.deadline:
            return "--minutes reached"
        if not self.window.alive():
            return "the client window closed"
        return ""

    def may_click(self) -> tuple[bool, str]:
        """(ok, why) for ONE click right now: the client in front, and the network check ok."""
        if not self.window.in_front():
            return False, "client not in front: click the game window"
        return self.check_network()


def approach_point(
    pt: tuple[float, float], rng: random.Random, w: int = CLIENT_W, h: int = CLIENT_H
) -> tuple[int, int]:
    """The FIRST motion of a click (lab lesson: two motions per click): a point 10-15 px from the
    target in a random direction, kept inside the client area. Input / output in px."""
    a = rng.uniform(0, 2 * math.pi)
    r = rng.uniform(*APPROACH_PX)
    x = min(max(pt[0] + r * math.cos(a), 1), w - 2)
    y = min(max(pt[1] + r * math.sin(a), 1), h - 2)
    return (round(x), round(y))


class Mouse:
    """Moves and clicks the real mouse through the Windows SendInput API, with ctypes (Python's
    built-in way to call C functions in Windows DLLs: no extra library).

    SendInput takes INPUT records. A mouse INPUT says: move to (dx, dy) and/or press a button."""

    MOVE, LEFTDOWN, LEFTUP = 0x0001, 0x0002, 0x0004  # MOUSEEVENTF_* flags: what this INPUT does
    ABSOLUTE, VIRTUALDESK = 0x8000, 0x4000  # dx, dy are a position (not a step) over ALL monitors

    def __init__(self) -> None:
        """Describe Windows' C structures to ctypes and read the desktop's size."""
        import ctypes
        from ctypes import wintypes

        class MOUSEINPUT(ctypes.Structure):
            """The C struct MOUSEINPUT, field by field, in Windows' order."""

            _fields_ = [
                ("dx", wintypes.LONG),
                ("dy", wintypes.LONG),  # the position
                ("mouseData", wintypes.DWORD),  # wheel steps (unused here)
                ("dwFlags", wintypes.DWORD),  # MOVE / LEFTDOWN / LEFTUP / ABSOLUTE ...
                ("time", wintypes.DWORD),  # 0 = Windows stamps the time itself
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        class INPUT(ctypes.Structure):
            """The C struct INPUT: a type (0 = mouse) then the event. In C the event is a union
            of mouse / keyboard / hardware events; the mouse one is the largest, so this layout
            has the size Windows expects."""

            _fields_ = [("type", wintypes.DWORD), ("mi", MOUSEINPUT)]

        self.ctypes, self.MOUSEINPUT, self.INPUT = ctypes, MOUSEINPUT, INPUT
        self.user32 = ctypes.windll.user32
        gsm = self.user32.GetSystemMetrics  # 76-79 = the virtual desktop's left, top, w, h
        self.vx, self.vy, self.vw, self.vh = gsm(76), gsm(77), gsm(78), gsm(79)

    def _send(self, flags: int, x: int = 0, y: int = 0) -> None:
        """Send ONE mouse INPUT with these flags and position."""
        inp = self.INPUT(0, self.MOUSEINPUT(x, y, 0, flags, 0, 0))
        self.user32.SendInput(1, self.ctypes.byref(inp), self.ctypes.sizeof(self.INPUT))

    def move(self, x: int, y: int) -> None:
        """Move the cursor to SCREEN pixel (x, y). An ABSOLUTE position is not given in pixels:
        Windows wants 0..65535 across the whole desktop, so the pixel is scaled to that range."""
        nx = round((x - self.vx) * 65535 / max(self.vw - 1, 1))
        ny = round((y - self.vy) * 65535 / max(self.vh - 1, 1))
        self._send(self.MOVE | self.ABSOLUTE | self.VIRTUALDESK, nx, ny)

    def press(self) -> None:
        """A left click where the cursor is: button down, a short pause, button up."""
        self._send(self.LEFTDOWN)
        time.sleep(PRESS_S)
        self._send(self.LEFTUP)


def click(
    pt: tuple[int, int], origin: tuple[int, int], mouse: Mouse, gate: SafetyGate, rng: random.Random
) -> str:
    """ONE click at client point `pt` (px), the lab's way, behind the safety gate.

    origin = the client area's top-left on the screen (screen px = origin + client px).
    1. refuse a point on a UI window or the edge; ask the gate (client in front, local server);
    2. motion 1: next to the target (10-15 px off), wait APPROACH_S;
    3. motion 2: onto the target, wait SETTLE_S (the client redraws its cursor there);
    4. ask the gate AGAIN (a lot can change in a third of a second), then press and release.
    Returns "" when it clicked, else why it did not."""
    if not clickable(pt):
        LOG.info("no click at %s: on a UI window or the edge", pt)
        return f"refused {pt}: on a UI window or the edge"
    ok, why = gate.may_click()
    if not ok:
        LOG.info("no click at %s: %s", pt, why)
        return why
    ax, ay = approach_point(pt, rng)
    mouse.move(origin[0] + ax, origin[1] + ay)
    time.sleep(APPROACH_S)
    mouse.move(origin[0] + pt[0], origin[1] + pt[1])
    time.sleep(SETTLE_S)
    ok, why = gate.may_click()
    stop = gate.stop_reason()
    if not ok or stop:
        LOG.info("no click at %s (checked again just before pressing): %s", pt,
                 why if not ok else stop)  # fmt: skip
        return why if not ok else stop
    mouse.press()
    LOG.debug("clicked at client %s = screen %s", pt, (origin[0] + pt[0], origin[1] + pt[1]))
    return ""


# =================================================================================================
# 8. DRAW: the bot view window (boxes, the target, the planned line, the HUD) and the overlay
# =================================================================================================

COLOURS = {"player": (255, 160, 0), "monster": (40, 40, 255), "npc": (40, 200, 40)}  # B, G, R
LINE_COLOURS = {SEARCH: (255, 255, 0), ATTACK: (0, 255, 255), LOOT: (0, 165, 255)}
OVERLAY_KEY = (255, 0, 255)  # the overlay's "transparent" colour (magenta): never draw with it
AA = 16  # cv2.LINE_AA: anti-aliased (smooth-edged) lines and text


def draw_scene(
    img: np.ndarray,
    boxes: Sequence[Box],
    dropped: Sequence[tuple[Box, str]],
    d: Decision,
    char: tuple[int, int],
) -> np.ndarray:
    """Draw what the bot sees and plans onto `img` (in place; also returned):
      - the UI zones (thin grey) where it never clicks;
      - every box with its class and score (player blue, monster red, npc green; our own
        character says "self"; dropped monsters grey with the reason under them);
      - a white cross on our feet (CHAR);
      - the target (thick yellow box), the planned line and its end circle (SEARCH cyan, ATTACK
        yellow, LOOT orange) and red dots on this frame's clicks.
    Colours are (B, G, R): OpenCV stores pixels blue first."""
    import cv2

    font = cv2.FONT_HERSHEY_SIMPLEX
    for name, (x0, y0, x1, y1) in UI_ZONES.items():
        cv2.rectangle(img, (x0, y0), (x1 - 1, y1 - 1), (150, 150, 150), 1, AA)
        cv2.putText(img, f"UI: {name}", (x0 + 4, y1 - 6), font, 0.4, (150, 150, 150), 1, AA)
    gone = {id(b) for b, _ in dropped}
    for b in boxes:
        p0, p1 = (round(b.x0), round(b.y0)), (round(b.x1), round(b.y1))
        colour = (130, 130, 130) if id(b) in gone else COLOURS.get(b.cls, (200, 200, 200))
        cv2.rectangle(img, p0, p1, colour, 2, AA)
        tag = "self" if is_self(b, char) else f"{b.cls} {b.score:.2f}"
        cv2.putText(img, tag, (p0[0], max(p0[1] - 5, 12)), font, 0.45, colour, 1, AA)
    for b, why in dropped:
        cv2.putText(img, why, (round(b.x0), round(b.y1) + 14), font, 0.4, (130, 130, 130), 1, AA)
    cv2.drawMarker(img, char, (255, 255, 255), cv2.MARKER_CROSS, 16, 2, AA)
    colour = LINE_COLOURS.get(d.state, (255, 255, 255))
    if d.target is not None:
        t = d.target
        p0, p1 = (round(t.x0) - 3, round(t.y0) - 3), (round(t.x1) + 3, round(t.y1) + 3)
        cv2.rectangle(img, p0, p1, (0, 255, 255), 3, AA)
    if d.line is not None:
        cv2.line(img, d.line[0], d.line[1], colour, 2, AA)
        cv2.circle(img, d.line[1], 7, colour, 2, AA)
    for pt in d.clicks:
        cv2.circle(img, pt, 5, (0, 0, 255), -1, AA)
    return img


def hud_text(mode: str, d: Decision, fps: float, ms: dict[str, float], boxes: Sequence[Box]) -> str:
    """The HUD line: mode | state and note | frames per second | ms per stage | box count."""
    n_mon = sum(b.cls == "monster" for b in boxes)
    stages = "  ".join(f"{k} {v:.0f}" if v >= 1 else f"{k} {v:.1f}" for k, v in ms.items())
    return (
        f"{mode} | {d.state}: {d.note} | {fps:.1f} fps | ms: {stages} | "
        f"boxes {len(boxes)} (monster {n_mon})"
    )


def with_hud_strip(img: np.ndarray, text: str) -> np.ndarray:
    """The bot view's HUD: a black strip with `text` added UNDER the picture (covers nothing)."""
    import cv2

    strip = np.zeros((26, img.shape[1], 3), np.uint8)
    cv2.putText(strip, text, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, AA)
    return np.vstack([img, strip])  # stack the picture and the strip top to bottom


def draw_overlay_hud(img: np.ndarray, text: str) -> None:
    """The overlay's HUD: the HUD text in two lines (split before " | ms:") in the bottom-right
    corner of the game, on a black box measured to fit the text (cv2.getTextSize)."""
    import cv2

    font, scale = cv2.FONT_HERSHEY_SIMPLEX, 0.42
    head, sep, tail = text.partition(" | ms:")
    lines = [head, "ms:" + tail] if sep else [text]
    sizes = [cv2.getTextSize(t, font, scale, 1)[0] for t in lines]  # (width, height) in px
    box_w = max(sz[0] for sz in sizes) + 12
    h, w = img.shape[:2]
    y = h - 8 - 18 * (len(lines) - 1)  # the first line's baseline
    cv2.rectangle(img, (w - box_w - 4, y - 16), (w - 4, h - 4), (0, 0, 0), -1)
    for t in lines:
        cv2.putText(img, t, (w - box_w + 2, y), font, scale, (255, 255, 255), 1, AA)
        y += 18


def overlay_picture(
    w: int,
    h: int,
    boxes: Sequence[Box],
    dropped: Sequence[tuple[Box, str]],
    d: Decision,
    char: tuple[int, int],
    hud: str,
) -> np.ndarray:
    """The overlay's w x h picture: the same drawings as the bot view, and OVERLAY_KEY (magenta,
    see-through) everywhere else.

    Why draw on BLACK first: OpenCV smooths the edges of lines and text by MIXING their colour
    with the background (anti-aliasing; its text is smoothed even when asked not to be). On a
    magenta background the mixed edge pixels would be "almost magenta", not see-through, and show
    as a pink fringe. On black they are just darker edges, like a shadow. Then every pixel still
    exactly black (nothing was drawn there) becomes the see-through magenta."""
    pic = np.zeros((h, w, 3), np.uint8)
    draw_scene(pic, boxes, dropped, d, char)
    pic[np.all(pic == 0, axis=2)] = OVERLAY_KEY  # untouched pixels -> see-through
    draw_overlay_hud(pic, hud)  # after the key: its black box must stay black (visible)
    return pic


class Overlay:
    """--overlay: a see-through window laid exactly over the game, showing the same drawings.

    How it works (Windows "layered" window):
      - every pixel in OVERLAY_KEY (pure magenta) is fully transparent (a "colour key"), so only
        the drawings show;
      - WS_EX_TRANSPARENT + WS_EX_LAYERED: the mouse passes THROUGH it to the game;
      - WS_EX_NOACTIVATE: it never takes the focus, so the game stays the foreground window;
      - WS_EX_TOPMOST: always above the game;
      - SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE): the window is shown on the monitor but
        LEFT OUT of every screen capture. The bot captures exactly the screen area the overlay
        covers: without this, the next frame would contain our own boxes and text, and the
        detector would look at (and might "detect") the bot's drawings. Windows 10 2004+ only;
        if it fails the overlay is refused, never shown half-safe.
    """

    WDA_EXCLUDEFROMCAPTURE = 0x11

    def __init__(self, w: int, h: int) -> None:
        """Create the w x h px overlay window (hidden behind nothing, showing nothing yet)."""
        import ctypes
        from ctypes import wintypes

        self.ct, self.w, self.h = ctypes, w, h
        # Our OWN handles on the system DLLs (not the shared ctypes.windll ones), so the
        # signatures declared below cannot clash with another library's
        u32, gdi, k32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32"), ctypes.WinDLL("kernel32")
        self.u32, self.gdi = u32, gdi
        W, i, ptr = wintypes, ctypes.c_int, ctypes.c_void_p
        LRESULT = ctypes.c_ssize_t  # a pointer-sized signed number
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)

        def sig(fn: Any, restype: Any, *argtypes: Any) -> None:
            """Declare a C function's result and argument types. Without this ctypes assumes
            "int" (32 bits), and a 64-bit Windows handle could be cut short."""
            fn.restype, fn.argtypes = restype, list(argtypes)

        sig(u32.DefWindowProcW, LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
        sig(u32.RegisterClassExW, W.ATOM, ptr)
        sig(u32.CreateWindowExW, W.HWND, W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, i, i, i, i,
            W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID)  # fmt: skip
        sig(u32.SetLayeredWindowAttributes, W.BOOL, W.HWND, W.DWORD, W.BYTE, W.DWORD)
        sig(u32.SetWindowDisplayAffinity, W.BOOL, W.HWND, W.DWORD)
        sig(u32.ShowWindow, W.BOOL, W.HWND, i)
        sig(u32.SetWindowPos, W.BOOL, W.HWND, W.HWND, i, i, i, i, W.UINT)
        sig(u32.InvalidateRect, W.BOOL, W.HWND, ptr, W.BOOL)
        sig(u32.BeginPaint, W.HDC, W.HWND, ptr)
        sig(u32.EndPaint, W.BOOL, W.HWND, ptr)
        sig(u32.PeekMessageW, W.BOOL, ptr, W.HWND, W.UINT, W.UINT, W.UINT)
        sig(u32.TranslateMessage, W.BOOL, ptr)
        sig(u32.DispatchMessageW, LRESULT, ptr)
        sig(u32.DestroyWindow, W.BOOL, W.HWND)
        sig(gdi.StretchDIBits, i, W.HDC, i, i, i, i, i, i, i, i, ptr, ptr, W.UINT, W.DWORD)
        sig(k32.GetModuleHandleW, W.HMODULE, W.LPCWSTR)

        class WNDCLASSEXW(ctypes.Structure):
            """The C struct describing a window class (its message handler and its name)."""

            _fields_ = [
                ("cbSize", wintypes.UINT),
                ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
                ("hIconSm", wintypes.HICON),
            ]

        class PAINTSTRUCT(ctypes.Structure):
            """The C struct BeginPaint fills in while the window repaints."""

            _fields_ = [
                ("hdc", wintypes.HDC),
                ("fErase", wintypes.BOOL),
                ("rcPaint", wintypes.RECT),
                ("fRestore", wintypes.BOOL),
                ("fIncUpdate", wintypes.BOOL),
                ("rgbReserved", ctypes.c_byte * 32),
            ]

        class BITMAPINFOHEADER(ctypes.Structure):
            """The C struct describing our picture's memory layout to Windows."""

            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        self.PAINTSTRUCT = PAINTSTRUCT
        # 32 bits per pixel (B, G, R, unused); a NEGATIVE height = the rows go top to bottom,
        # like numpy's (a positive one would mean bottom-up and draw the picture upside down)
        self.bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        self.buf: np.ndarray | None = None  # the picture to paint (B, G, R, A)
        self._proc = WNDPROC(self._wndproc)  # keep a reference: Windows calls it later
        hinst = k32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.lpszClassName = "SimpleBotOverlay"
        u32.RegisterClassExW(ctypes.byref(wc))
        layered, transparent, topmost = 0x00080000, 0x00000020, 0x00000008  # WS_EX_* styles
        toolwindow, noactivate, popup = 0x00000080, 0x08000000, 0x80000000  # popup = no frame
        self.hwnd = u32.CreateWindowExW(
            layered | transparent | topmost | toolwindow | noactivate,
            "SimpleBotOverlay",
            "simple-bot overlay",
            popup,
            0,
            0,
            w,
            h,
            None,
            None,
            hinst,
            None,
        )
        if not self.hwnd:
            raise RuntimeError("could not create the overlay window")
        key = OVERLAY_KEY[2] | (OVERLAY_KEY[1] << 8) | (OVERLAY_KEY[0] << 16)  # COLORREF 0x00BBGGRR
        u32.SetLayeredWindowAttributes(self.hwnd, key, 0, 0x1)  # 0x1 = LWA_COLORKEY
        if not u32.SetWindowDisplayAffinity(self.hwnd, self.WDA_EXCLUDEFROMCAPTURE):
            u32.DestroyWindow(self.hwnd)
            raise RuntimeError(
                "SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE) failed (needs "
                "Windows 10 2004+): no overlay, the detector would see it"
            )
        u32.ShowWindow(self.hwnd, 4)  # 4 = SW_SHOWNOACTIVATE: show it without taking the focus

    def _wndproc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        """The window's message handler: Windows calls it for every event of the window."""
        if msg == 0x000F:  # WM_PAINT: Windows asks us to draw the window: copy our picture in
            ps = self.PAINTSTRUCT()
            hdc = self.u32.BeginPaint(hwnd, self.ct.byref(ps))
            if self.buf is not None:  # 0x00CC0020 = SRCCOPY: plain copy, pixel for pixel
                self.gdi.StretchDIBits(
                    hdc,
                    0,
                    0,
                    self.w,
                    self.h,
                    0,
                    0,
                    self.w,
                    self.h,
                    self.ct.c_void_p(self.buf.ctypes.data),
                    self.ct.byref(self.bmi),
                    0,
                    0x00CC0020,
                )
            self.u32.EndPaint(hwnd, self.ct.byref(ps))
            return 0
        if msg == 0x0014:  # WM_ERASEBKGND: we paint every pixel ourselves: no flicker
            return 1
        if msg == 0x0084:  # WM_NCHITTEST: answer "transparent" (-1): the mouse goes to the game
            return -1
        return int(self.u32.DefWindowProcW(hwnd, msg, wparam, lparam))  # the rest: the default

    def show(self, picture_bgr: np.ndarray, left: int, top: int) -> None:
        """Show this picture (w x h, magenta = see-through) over the screen point (left, top)."""
        import cv2

        self.buf = np.ascontiguousarray(cv2.cvtColor(picture_bgr, cv2.COLOR_BGR2BGRA))
        # -1 = HWND_TOPMOST; 0x0010 = SWP_NOACTIVATE (move it with the game, never take focus)
        self.u32.SetWindowPos(self.hwnd, -1, left, top, self.w, self.h, 0x0010)
        self.u32.InvalidateRect(self.hwnd, None, False)  # "please repaint" -> a WM_PAINT
        self.pump()

    def pump(self) -> None:
        """Handle the overlay's waiting messages now (this is what runs `_wndproc`)."""
        from ctypes import wintypes

        msg = wintypes.MSG()
        while self.u32.PeekMessageW(self.ct.byref(msg), self.hwnd, 0, 0, 1):  # 1 = PM_REMOVE
            self.u32.TranslateMessage(self.ct.byref(msg))
            self.u32.DispatchMessageW(self.ct.byref(msg))

    def close(self) -> None:
        """Remove the overlay window."""
        self.u32.DestroyWindow(self.hwnd)


# =================================================================================================
# 9. MAIN LOOP: replay (pictures) or live (watch / act), and the command line
# =================================================================================================

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp")


def list_images(paths: Sequence[str]) -> list[Path]:
    """The image files to replay: each argument is an image, or a folder whose images are taken
    (sorted by name; sub-folders are not entered)."""
    out: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            out += sorted(f for f in p.iterdir() if f.suffix.lower() in IMAGE_SUFFIXES)
        elif p.suffix.lower() in IMAGE_SUFFIXES:
            out.append(p)
    return out


def cpp_runtime_version() -> tuple[int, ...] | None:
    """Windows only: the file version of System32\\msvcp140.dll (Microsoft's C++ runtime, e.g.
    (14, 42, 34433, 0)), or None when it cannot be read."""
    import os

    import win32api

    path = os.path.join(os.environ.get("SYSTEMROOT", r"C:\Windows"), "System32", "msvcp140.dll")
    try:
        info = win32api.GetFileVersionInfo(path, "\\")  # "\\" = the fixed version block
    except Exception:  # pywin32 raises its own error type when the file is missing
        return None
    ms, ls = int(info["FileVersionMS"]), int(info["FileVersionLS"])  # two 32-bit halves
    return (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)


def runtime_warning(version: tuple[int, ...] | None) -> str:
    """PURE: a warning when the C++ runtime is missing or older than CPP_RUNTIME_MIN, else ""."""
    if version is None:
        return (f"WARNING: Microsoft's C++ runtime (msvcp140.dll) was not found; if Python closes "
                f"with 'access violation' next, install it: {CPP_RUNTIME_URL}")  # fmt: skip
    if tuple(version[:2]) < CPP_RUNTIME_MIN:
        have = ".".join(str(v) for v in version)
        need = ".".join(str(v) for v in CPP_RUNTIME_MIN)
        return (f"WARNING: Microsoft's C++ runtime (msvcp140.dll) is {have}, older than the "
                f"{need} onnxruntime needs: if Python closes with 'access violation' next, install "
                f"the latest one (once): {CPP_RUNTIME_URL}")  # fmt: skip
    return ""


def make_detector(args: argparse.Namespace) -> OnnxDetector | ColorDetector:
    """The detector the command line asked for: the YOLO model (needs --model) or the colour one.

    On Windows onnxruntime needs a NEW copy of Microsoft's C++ runtime, msvcp140.dll (see
    CPP_RUNTIME_MIN): with an old one, its import dies with "access violation" and no Python error.
    So the version is checked and warned about first. Windows also loads a DLL only once per
    program, so the model is loaded BEFORE OpenCV (a precaution: no other library can bring an
    older copy in first)."""
    if args.detector == "color":
        return ColorDetector()
    if not args.model:
        raise SystemExit(
            "the onnx detector needs --model PATH (e.g. --model v1.onnx), or use --detector color"
        )
    if not Path(args.model).is_file():
        raise SystemExit(f"--model {args.model}: no such file")
    if sys.platform == "win32":  # warn BEFORE the import that crashes on an old runtime
        version = cpp_runtime_version()
        LOG.info("msvcp140.dll version: %s", version)
        warning = runtime_warning(version)
        if warning:
            print(warning, flush=True)
    say(f"loading the model {args.model} ...")
    return OnnxDetector(Path(args.model), args.conf, IOU, args.threads)


def run_replay(args: argparse.Namespace) -> int:
    """REPLAY: the pipeline on image files. No game, no input, works on any computer.

    Each picture: read -> detect -> decide -> draw, then show it (any key = next, q = quit) or
    save it as a PNG (--save-dir). By default every picture is judged on its own by a fresh bot
    (what would it do if it saw THIS?); --sequence treats the pictures as one recording at --fps,
    so the state machine runs across them. --json writes every frame's boxes and decision."""
    files = list_images(args.replay)
    if not files:
        raise SystemExit(f"no images (.png .jpg .jpeg .bmp) in {args.replay}")
    det = make_detector(args)  # BEFORE cv2: see make_detector
    import cv2

    show = not args.save_dir and not args.no_show
    out_dir = Path(args.save_dir) if args.save_dir else None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
    decider = Decider(random.Random(args.seed))
    rows: list[dict[str, Any]] = []
    sums = {"read": 0.0, "detect": 0.0, "decide": 0.0}
    n_boxes = n_mon = 0
    say(f"replay: {len(files)} image(s), detector {det.label}")
    for i, f in enumerate(files):
        t0 = time.perf_counter()
        frame = cv2.imread(str(f))  # a (h, w, 3) BGR picture, or None
        if frame is None:
            say(f"  {f.name}: unreadable, skipped")
            continue
        t1 = time.perf_counter()
        boxes = det.detect(frame)
        t2 = time.perf_counter()
        h, w = frame.shape[:2]
        if not args.sequence:
            decider = Decider(random.Random(args.seed + i), w=w, h=h)
        d = decider.step(boxes, i / args.fps)  # the "time" of frame i in a recording
        t3 = time.perf_counter()
        ms = {"read": (t1 - t0) * 1e3, "detect": (t2 - t1) * 1e3, "decide": (t3 - t2) * 1e3}
        for k in sums:
            sums[k] += ms[k]
        mon = sum(b.cls == "monster" for b in boxes)
        n_boxes, n_mon = n_boxes + len(boxes), n_mon + mon
        tgt = d.target
        target = f"target {tgt.cls} {tgt.score:.2f} at {tgt.hit_point}" if tgt else "no target"
        say(
            f"  [{i + 1}/{len(files)}] {f.name}: {len(boxes)} boxes ({mon} monster), detect "
            f"{ms['detect']:.0f} ms -> {d.state} ({d.note}), {target}, clicks {d.clicks}"
        )
        rows.append(
            {
                "file": str(f),
                "state": d.state,
                "clicks": d.clicks,
                "line": d.line,
                "boxes": [[b.x0, b.y0, b.x1, b.y1, b.score, b.cls] for b in boxes],
                "ms": {k: round(v, 1) for k, v in ms.items()},
            }
        )
        if not show and out_dir is None:
            continue
        _, dropped = sort_boxes(boxes, decider.char, w, h)
        pic = draw_scene(frame.copy(), boxes, dropped, d, decider.me)
        fps = 1000.0 / max(ms["read"] + ms["detect"] + ms["decide"], 1e-3)
        pic = with_hud_strip(pic, hud_text("REPLAY", d, fps, ms, boxes))
        if out_dir is not None:
            cv2.imwrite(str(out_dir / f"{f.stem}.png"), pic)
            continue
        try:
            cv2.imshow("simple-bot view (any key: next, q: quit)", pic)
        except cv2.error:
            raise SystemExit("this OpenCV has no window support: add --save-dir OUT") from None
        if cv2.waitKey(0) & 0xFF in (ord("q"), 27):  # 27 = Esc
            break
    n = max(len(rows), 1)
    print(
        f"done: {len(rows)} frame(s), {n_boxes} boxes ({n_mon} monster), mean ms per frame: "
        + ", ".join(f"{k} {v / n:.1f}" for k, v in sums.items())
    )
    if args.json:
        Path(args.json).write_text(json.dumps(rows))
    if out_dir is not None:
        print(f"annotated pictures in {out_dir}")
    if show:
        cv2.destroyAllWindows()
    return 0


def run_live(args: argparse.Namespace) -> int:
    """WATCH (draw only, never any input) or ACT (also click, behind the safety gate).

    The loop, as fast as the CPU allows:
        stop? -> capture -> detect -> decide -> [act: gate, clicks] -> draw (bot view, overlay)
    Returns the exit code: 0 = stopped normally, 3 = the safety gate stopped it."""
    det = make_detector(args)  # BEFORE cv2: see make_detector
    import cv2

    LOG.info("opencv %s, numpy %s", cv2.__version__, np.__version__)
    set_dpi_aware()
    say(f"looking for the game window ('{args.title}' in its title) ...")
    window = ClientWindow(args.title)
    grabber = Grabber()
    rng = random.Random(args.seed)
    gate = SafetyGate(window, args.minutes)
    mouse: Mouse | None = None
    if args.act:
        print(ACT_BANNER)
        ok, why = gate.check_network(force=True)
        if not ok:
            print(f"--act refused: {why}")
            return 3
        mouse = Mouse()
        print("network check:", why)
        print("starting in 5 s: click the game window to put it in front ...")
        time.sleep(5)
    overlay = None
    left, top, w, h = window.rect()
    if (w, h) != (CLIENT_W, CLIENT_H):
        print(
            f"WARNING: the client area is {w} x {h}; the settings (character, UI windows) and "
            f"the model expect {CLIENT_W} x {CLIENT_H}"
        )
    if args.overlay:
        try:
            overlay = Overlay(w, h)
        except RuntimeError as e:
            print(f"overlay off: {e}")
    decider = Decider(rng, w=w, h=h)
    mode = "ACT" if args.act else "WATCH (no input)"
    print(
        f"{mode}: window {window.title!r} (pid {window.pid}), client area {w} x {h} at "
        f"({left}, {top}); stop: F12 / mouse to the top-left corner / q in the bot view"
    )
    LOG.info("client area %d x %d at (%d, %d); the loop starts", w, h, left, top)
    t_prev, fps = time.perf_counter(), 0.0
    frames, last_log, last_state = 0, 0.0, ""
    try:
        while True:
            reason = gate.stop_reason()
            if reason:
                print(f"stopped: {reason}")
                LOG.info("stopped: %s after %d frames", reason, frames)
                return 0
            t0 = time.perf_counter()
            left, top, w, h = window.rect()  # the window may have moved
            frame = grabber.grab(left, top, w, h)  # CAPTURE
            t1 = time.perf_counter()
            boxes = det.detect(frame)  # DETECT
            t2 = time.perf_counter()
            d = decider.step(boxes, time.monotonic())  # DECIDE
            t3 = time.perf_counter()
            if mouse is not None:  # ACT
                ok, why = gate.check_network()
                if not ok:  # the client left the local server: stop clicking at once
                    print(f"SAFETY STOP: {why}")
                    LOG.warning("SAFETY STOP: %s", why)
                    return 3
                for pt in d.clicks:
                    status = click(pt, (left, top), mouse, gate, rng)
                    if status:
                        d.note += f" [no click: {status}]"
                        break
            t4 = time.perf_counter()
            ms = {
                "capture": (t1 - t0) * 1e3,
                "detect": (t2 - t1) * 1e3,
                "decide": (t3 - t2) * 1e3,
                "act": (t4 - t3) * 1e3,
            }
            now_fps = 1.0 / max(t4 - t_prev, 1e-3)
            fps = now_fps if fps == 0 else 0.8 * fps + 0.2 * now_fps  # smoothed: easier to read
            t_prev = t4
            frames += 1
            if d.state != last_state:  # every change of state, at once
                LOG.info("state %s -> %s (%s)", last_state or "start", d.state, d.note)
                last_state = d.state
            if time.monotonic() - last_log >= LOG_EVERY_S:  # and a summary once a second
                last_log = time.monotonic()
                LOG.debug(
                    "frame %d | %s: %s | boxes %d (monster %d) | target %s | clicks %s | "
                    "ms %s | %.1f fps", frames, d.state, d.note, len(boxes),
                    sum(b.cls == "monster" for b in boxes),
                    f"{d.target.cls} {d.target.score:.2f}" if d.target else "none", d.clicks,
                    {k: round(v) for k, v in ms.items()}, fps)  # fmt: skip
            hud = hud_text(mode, d, fps, ms, boxes)
            _, dropped = sort_boxes(boxes, decider.char, w, h)
            view = draw_scene(frame.copy(), boxes, dropped, d, decider.me)  # DRAW
            if args.view_scale != 1.0:
                view = cv2.resize(
                    view, None, fx=args.view_scale, fy=args.view_scale, interpolation=cv2.INTER_AREA
                )
            cv2.imshow("simple-bot view (q: quit)", with_hud_strip(view, hud))
            # the overlay's picture size is fixed when it is created: skip it while the client
            # area has another size (resize the client back to make it reappear)
            if overlay is not None and (w, h) == (overlay.w, overlay.h):
                overlay.show(overlay_picture(w, h, boxes, dropped, d, decider.me, hud), left, top)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):  # waitKey also lets the window redraw
                print("stopped: q")
                LOG.info("stopped: q after %d frames", frames)
                return 0
    finally:  # whatever happened: remove our windows
        if overlay is not None:
            overlay.close()
        cv2.destroyAllWindows()


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """The command line (run with --help to see it)."""
    ap = argparse.ArgumentParser(description="simple_bot: a small vision bot for learning")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument(
        "--replay", nargs="+", metavar="DIR_OR_IMAGE", help="run on image files (no game, no input)"
    )
    mode.add_argument(
        "--watch",
        action="store_true",
        help="live: capture the client, detect, decide, DRAW only (the default)",
    )
    mode.add_argument(
        "--act",
        action="store_true",
        help="live: also CLICK, behind the safety gate (Windows, local server only)",
    )
    ap.add_argument("--model", help="the ONNX model (v1.onnx)")
    ap.add_argument(
        "--detector",
        choices=("onnx", "color"),
        default="onnx",
        help="onnx = the YOLO model; color = a rough HSV demo (Porings only)",
    )
    ap.add_argument("--conf", type=float, default=CONF, help="minimum box score (default 0.25)")
    ap.add_argument("--threads", type=int, default=0, help="CPU threads for the model (0 = auto)")
    ap.add_argument("--title", default="Ragnarok", help="part of the client window's title")
    ap.add_argument(
        "--overlay",
        action="store_true",
        help="also draw over the game (Windows 10 2004+; invisible to capture)",
    )
    ap.add_argument("--view-scale", type=float, default=0.75, help="size of the bot view window")
    ap.add_argument("--minutes", type=float, default=10.0, help="end a live run after this long")
    ap.add_argument("--save-dir", help="replay: save annotated PNGs here (no window)")
    ap.add_argument("--no-show", action="store_true", help="replay: no window, no pictures")
    ap.add_argument("--json", help="replay: write every frame's boxes and decision to this file")
    ap.add_argument(
        "--sequence",
        action="store_true",
        help="replay: the images are ONE recording (keep the state machine going)",
    )
    ap.add_argument("--fps", type=float, default=5.0, help="replay --sequence: frames per second")
    ap.add_argument("--seed", type=int, default=1, help="random seed (wander points)")
    ap.add_argument(
        "--logs",
        action="store_true",
        help="print what the bot does, step by step, with the time (where it is, why no click)",
    )
    ap.add_argument("--log-file", help="also write the logs to this file (implies --logs)")
    return ap.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Start here: read the command line, refuse what this machine cannot do, run the mode."""
    import faulthandler

    # If a library written in C/C++ crashes (a "native" crash), Python itself dies and normally
    # prints NOTHING. faulthandler prints which Python line was running, so a crash is never silent.
    # (skipped when stderr is not a real file: inside a test, some IDE consoles)
    with contextlib.suppress(ValueError, OSError):
        faulthandler.enable()
    args = parse_args(argv)
    setup_logs(args.logs, args.log_file)
    mode = "replay" if args.replay else "act" if args.act else "watch"  # no mode given = --watch
    LOG.info("simple_bot %s: python %s on %s", mode, sys.version.split()[0], sys.platform)
    LOG.debug("options: %s", vars(args))
    try:
        if args.replay:
            return run_replay(args)
        why = live_refusal(mode)
        if why:
            print(why, file=sys.stderr)
            return 2
        return run_live(args)
    except Exception:  # a Python error: its full traceback goes to the logs (and the screen)
        LOG.exception("simple_bot stopped on an error")
        raise


if __name__ == "__main__":
    sys.exit(main())
