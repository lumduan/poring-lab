"""The LIVE route preview (Batt, 2026-10-08, from his screen recording): anchored to the WORLD.

walk@8-11 sent the route ONCE per step in screen pixels, so when the camera followed the character
the scene scrolled under a route that stayed put (the line and the goal ring floated; the character
ended on a stale crosshair). Like a navigation app now:
1. the route is kept as MAP CELLS (the plan's corner polyline, the next click, the goal);
2. ~20 times a second it is re-projected with the walk rule's own camera model (indoor/outdoor,
   GAT altitude) relative to the character's CURRENT position, sent as a LIVE RoutePreview stamped
   with the host clock (the stream frames' clock too), so the console can draw the message nearest
   the displayed frame and nothing when none is close;
3. the current position while walking = the walk's deterministic timing (a straight step takes the
   walk speed, a diagonal 1.4x; the walk starts WALK_START_S after the click: the click reaches the
   server ~180 ms later), snapped to the cell on arrival or a /where fix;
4. the line starts at the character's feet; the stretch just walked over fades out over FADE_S and
   is dropped; the next click marker and the goal ring stay;
5. clear() on route end / map change; the client's fixed UI windows travel as `clip` rectangles.
DISPLAY ONLY: nothing here feeds a decision, and the message cannot carry input (protocol).
"""

from __future__ import annotations

import contextlib
import json
import math
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

HZ = 20.0
FADE_S = 0.4
WALK_START_S = 0.19  # the click -> the server's move (median 178 ms, walk@10's 720 clicks)
DIAGONAL = 1.4  # rAthena MOVE_DIAGONAL_COST 14 / MOVE_COST 10
# The client's always-on UI windows at the frozen 1280x720 layout (client px: x0, y0, x1, y1): basic
# info + its menu icons, the hotbar, the small top window, the minimap (outdoors), the chat window
UI_WINDOWS = ((0, 0, 220, 326), (230, 0, 520, 132), (750, 0, 828, 36), (1135, 14, 1266, 162),
              (0, 532, 600, 626))  # fmt: skip

Cell = tuple[float, float]


def timeline(start: Sequence[int], path: Sequence[Sequence[int]], t0_ns: int,
             ms_per_cell: float) -> list[tuple[Cell, int]]:  # fmt: skip
    """(cell, the time the character is ON it) for a walk from `start` along `path`."""
    out: list[tuple[Cell, int]] = [((float(start[0]), float(start[1])), t0_ns)]
    t = t0_ns
    prev = (int(start[0]), int(start[1]))
    for c in path:
        c = (int(c[0]), int(c[1]))
        diag = c[0] != prev[0] and c[1] != prev[1]
        t += int(ms_per_cell * (DIAGONAL if diag else 1.0) * 1e6)
        out.append(((float(c[0]), float(c[1])), t))
        prev = c
    return out


def position_at(tl: Sequence[tuple[Cell, int]], t_ns: int) -> Cell:
    """The character's (fractional) cell at t: linear between the cells of the walk."""
    if t_ns <= tl[0][1]:
        return tl[0][0]
    for (a, ta), (b, tb) in zip(tl, tl[1:], strict=False):
        if t_ns <= tb:
            f = (t_ns - ta) / max(tb - ta, 1)
            return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
    return tl[-1][0]


def remaining(route: Sequence[Cell], p: Cell, start_seg: int = 0) -> tuple[list[Cell], int]:
    """The route still ahead of the character: p, then every corner after the segment p is on (the
    closest segment, searched forward from `start_seg`). Returns (polyline, that segment)."""
    if len(route) < 2:
        return [p, *route], 0
    best, bseg = math.inf, start_seg
    for k in range(start_seg, len(route) - 1):
        a, b = route[k], route[k + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = dx * dx + dy * dy
        f = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
        d = math.hypot(a[0] + f * dx - p[0], a[1] + f * dy - p[1])
        if d < best - 1e-9:
            best, bseg = d, k
    return [p, *route[bseg + 1 :]], bseg


def clip_segment(
    a: Cell, b: Cell, box: tuple[float, float, float, float]
) -> tuple[Cell, Cell] | None:
    """Liang-Barsky: the part of a-b inside box (x0, y0, x1, y1), or None."""
    x0, y0, x1, y1 = box
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for pv, qv in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if pv == 0:
            if qv < 0:
                return None
            continue
        r = qv / pv
        if pv < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return None
    return (a[0] + t0 * dx, a[1] + t0 * dy), (a[0] + t1 * dx, a[1] + t1 * dy)


class LivePreview:
    """Sends LIVE RoutePreview messages for the walk rule's current route, in its own thread."""

    def __init__(self, send: Callable[[str], None], camera: Any, gat: Any, region: Sequence[int],
                 desktop: Sequence[int], label: str = "", hz: float = HZ,
                 clock: Callable[[], int] = time.monotonic_ns) -> None:  # fmt: skip
        self.send, self.camera, self.gat = send, camera, gat
        self.gx, self.gy, self.gw, self.gh = (int(v) for v in region)
        self.dw, self.dh = (int(v) for v in desktop)
        self.label, self.hz, self.clock = label[:64], hz, clock
        self.lock = threading.Lock()
        self.route: list[Cell] = []
        self.click: Cell | None = None
        self.goal: Cell | None = None
        self.stand: Cell | None = None
        self.walk_tl: list[tuple[Cell, int]] | None = None
        self.seg = 0
        self.trail: list[tuple[Cell, int]] = []
        self.active = False
        self.sent: list[dict[str, Any]] = []  # every message, for the offline check
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # --- what the walk rule tells it ------------------------------------------------------------
    def set_route(self, position: Sequence[int], corners: Sequence[Sequence[int]],
                  goal: Sequence[int], click: Sequence[int] | None = None) -> None:  # fmt: skip
        with self.lock:
            here = (float(position[0]), float(position[1]))
            if self.walk_tl is None:
                self.stand = here
            self.route = [here, *[(float(c[0]), float(c[1])) for c in corners]]
            self.goal = (float(goal[0]), float(goal[1]))
            self.click = None if click is None else (float(click[0]), float(click[1]))
            self.seg = 0
            self.active = True

    def walk(self, start: Sequence[int], path: Sequence[Sequence[int]], t_click_ns: int,
             ms_per_cell: float) -> None:  # fmt: skip
        with self.lock:
            self.walk_tl = timeline(start, path, t_click_ns + int(WALK_START_S * 1e9), ms_per_cell)
            self.click = None

    def snap(self, cell: Sequence[int]) -> None:
        with self.lock:
            self.walk_tl, self.stand = None, (float(cell[0]), float(cell[1]))

    def clear(self) -> None:
        with self.lock:
            self.active, self.route, self.walk_tl, self.trail = False, [], None, []
        self._send({"points": [], "passed": [], "clip": []})

    # --- the thread -------------------------------------------------------------------------------
    def start(self) -> LivePreview:
        self._thread = threading.Thread(target=self._run, name="route-preview", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.wait(1.0 / self.hz):
            try:
                msg = self.build(self.clock())
                if msg is not None:
                    self._send(msg)
            except Exception:  # noqa: BLE001 -- the preview never breaks the walk
                pass

    # --- the geometry -------------------------------------------------------------------------
    def here(self, t_ns: int) -> Cell | None:
        if self.walk_tl is not None:
            p = position_at(self.walk_tl, t_ns)
            if t_ns >= self.walk_tl[-1][1]:  # arrived: stand there
                self.stand, self.walk_tl = self.walk_tl[-1][0], None
            return p
        return self.stand

    def to_norm(self, cells: Sequence[Cell], p: Cell) -> list[tuple[float, float]]:
        """Map cells -> desktop-normalized pixels, the camera centred on the character at p."""
        if not cells:
            return []
        rel = np.array([(c[0] - p[0], c[1] - p[1]) for c in cells], dtype=float)
        pi = (int(round(p[0])), int(round(p[1])))
        rel_i = rel + np.array([p[0] - pi[0], p[1] - pi[1]])
        alt = None if self.gat is None else self.gat.relative_altitude(pi, rel_i)
        if alt is not None:  # the camera's own height follows the fractional position
            alt = alt - self.gat.relative_altitude(pi, np.array([[p[0] - pi[0], p[1] - pi[1]]]))[0]
        px = self.camera.project(rel, alt)
        return [((self.gx + float(u)) / self.dw, (self.gy + float(v)) / self.dh) for u, v in px]

    def build(self, t_ns: int) -> dict[str, Any] | None:
        with self.lock:
            if not self.active:
                return None
            p = self.here(t_ns)
            if p is None:
                return None
            ahead, self.seg = remaining(self.route, p, self.seg)
            if self.walk_tl is not None:
                self.trail.append((p, t_ns))
            self.trail = [(c, t) for c, t in self.trail if (t_ns - t) / 1e9 < FADE_S]
            region = (self.gx / self.dw, self.gy / self.dh, (self.gx + self.gw) / self.dw,
                      (self.gy + self.gh) / self.dh)  # fmt: skip
            line = self.to_norm(ahead, p)
            points: list[dict[str, Any]] = []
            for i in range(len(line) - 1):
                seg = clip_segment(line[i], line[i + 1], region)
                if seg is None:
                    break
                if not points:
                    points.append(_pt(seg[0], "feet" if i == 0 else "waypoint"))
                points.append(_pt(seg[1], "waypoint"))
                if seg[1] != line[i + 1]:
                    break  # the route leaves the view: draw up to the edge
            if len(line) == 1:
                points.append(_pt(line[0], "feet"))
            extra = [(self.goal, "goal")] + ([(self.click, "click")] if self.click else [])
            for cell, kind in extra:
                if cell is None:
                    continue
                (u, v) = self.to_norm([cell], p)[0]
                if region[0] <= u <= region[2] and region[1] <= v <= region[3]:
                    points.append(_pt((u, v), kind))
            passed = []
            tr = self.trail
            for (a, _), (b, tb) in zip(tr, tr[1:], strict=False):
                na, nb = self.to_norm([a, b], p)
                seg = clip_segment(na, nb, region)
                if seg is not None:
                    passed.append({"points": [_pt(seg[0], "waypoint"), _pt(seg[1], "waypoint")],
                                   "age_ms": int((t_ns - tb) / 1e6)})  # fmt: skip
            clip = [{"x": (self.gx + x0) / self.dw, "y": (self.gy + y0) / self.dh,
                     "w": (x1 - x0) / self.dw, "h": (y1 - y0) / self.dh}
                    for x0, y0, x1, y1 in UI_WINDOWS]  # fmt: skip
            return {"points": points[:64], "passed": passed[-16:], "clip": clip, "t": t_ns}

    def _send(self, body: dict[str, Any]) -> None:
        t = int(body.pop("t", self.clock()))
        msg = {"type": "route_preview", "t_mono_ns": t, "frame_id": -1, "live": True,
               "ttl_ms": 300, "label": self.label, **body}  # fmt: skip
        self.sent.append(msg)
        with contextlib.suppress(Exception):  # display only: never a reason to stop
            self.send(json.dumps(msg))


def _pt(uv: tuple[float, float], kind: str) -> dict[str, Any]:
    return {"x": min(max(uv[0], 0.0), 1.0), "y": min(max(uv[1], 0.0), 1.0), "kind": kind}
