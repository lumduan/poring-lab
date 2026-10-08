"""The LIVE route preview, anchored to WHAT THE SCREEN SHOWS (Batt, 2026-10-08).

v1 (f7cac8e) re-projected the route from a TIMING model: the walk start time times the walk speed.
Batt's second recording (12:35) showed the route world-anchored at rest, but WHILE WALKING the
whole line detached from the character's feet (~50 px), and re-aligned after the stop. Measured on
our own 12:34 recording:
- the client's camera LAGS the character: mid-walk the feet sit up to ~36 px ahead of their rest
  screen point (median 11.7 px), and they return to it within a frame or two of the stop;
- the timing model also misses the stream's delay.

Now, for every frame it grabs:
1. **the scene's scroll** since the previous frame (phase correlation, sub-pixel) moves the CAMERA's
   world position c by -J^-1 scroll, where J is the camera model's px per cell at our cell;
2. **the FEET, measured on the frame:** the client draws our HP/SP bar BAR_OFFSET below them. The
   line starts there, and the character's cell is p = c + J^-1 (feet - anchor);
3. **no drift:** when the scene is still and the feet are back on the anchor, the camera snaps to
   the walk rule's believed cell (the latest snap()), so no error carries over between steps;
4. every route corner, the next click and the goal are projected relative to c; what p walked over
   in the last FADE_S fades out; the client's fixed UI windows travel as `clip` rectangles;
5. **the timestamp:** the message carries the grabbed frame's capture time (host clock), so the
   console draws it on the matching frame.

It runs in its OWN process, with its own grabber and its own agent connection, so the walk rule's
work cannot starve it.

DISPLAY ONLY: nothing here feeds a decision, and the message cannot carry input (the protocol).
"""

from __future__ import annotations

import contextlib
import functools
import json
import math
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

HZ = 20.0
FADE_S = 0.4
# The client's always-on UI windows at the frozen 1280x720 layout (client px: x0, y0, x1, y1): basic
# info + its menu icons, the hotbar, the small top window, the minimap (outdoors), the chat window
UI_WINDOWS = ((0, 0, 220, 326), (230, 0, 520, 132), (750, 0, 828, 36), (1135, 14, 1266, 162),
              (0, 532, 600, 626))  # fmt: skip
# The HP/SP bar the client draws under our character, relative to the feet (client px). Measured on
# the 2026-10-08 12:34 recording at rest: bar centre (640.0, 384.5), the camera model's feet
# (640.75, 361.89).
BAR_OFFSET = (-0.75, 22.6)
BAR_W, BAR_H = 60, 9
BAR_SEARCH_PX = 200  # the bar is looked for within this distance of its rest point
BAND = (200, 600, 300, 1100)  # y0, y1, x0, x1: the scroll band around the character, clear of UI
# Our character, its bar and name stay near the anchor while the floor scrolls under them: masked
# out of the scroll (they pulled the correlation towards zero; 2026-10-08 12:49 recording)
CHAR_MASK = (232, 412, 550, 731)  # y0, y1, x0, x1 (client px): the anchor +- the walking lag
DOWN = 2  # the band is phase-correlated at half resolution (~2.5 ms per FFT), refined sub-pixel
REST_SHIFT_PX = 0.75  # a scroll below this between two frames: the scene is still
REST_FEET_PX = 3.0  # and the feet this close to the anchor: the camera has caught up
REST_FRAMES = 3

Cell = tuple[float, float]


# --- the pixels ------------------------------------------------------------------------------
@functools.lru_cache(maxsize=4)
def _hann(h: int, w: int) -> np.ndarray:
    return (np.hanning(h)[:, None] * np.hanning(w)[None, :]).astype(np.float32)


def _band(img: np.ndarray, down: int) -> np.ndarray:
    y0, y1, x0, x1 = BAND
    g = img[y0:y1:down, x0:x1:down, :3].astype(np.float32).mean(-1)
    g -= g.mean()
    my0, my1, mx0, mx1 = CHAR_MASK
    g[(my0 - y0) // down : (my1 - y0) // down, (mx0 - x0) // down : (mx1 - x0) // down] = 0.0
    return g * _hann(*g.shape)


def _sub(cm: float, c0: float, cp: float) -> float:
    d = cm - 2.0 * c0 + cp
    return 0.0 if d == 0 else float(np.clip(0.5 * (cm - cp) / d, -0.5, 0.5))


def scene_shift(a: np.ndarray, b: np.ndarray, down: int = DOWN) -> tuple[float, float]:
    """How far the SCENE moved from frame a to frame b (client px, sub-pixel): phase correlation of
    the band around the character, the client's UI windows excluded."""
    fa, fb = np.fft.fft2(_band(a, down)), np.fft.fft2(_band(b, down))
    r = fb * np.conj(fa)
    c = np.fft.ifft2(r / (np.abs(r) + 1e-9)).real
    h, w = c.shape
    iy, ix = np.unravel_index(int(np.argmax(c)), c.shape)
    dy = iy + _sub(c[iy - 1, ix], c[iy, ix], c[(iy + 1) % h, ix])
    dx = ix + _sub(c[iy, ix - 1], c[iy, ix], c[iy, (ix + 1) % w])
    dy = dy - h if dy > h / 2 else dy
    dx = dx - w if dx > w / 2 else dx
    return (float(dx * down), float(dy * down))


def _bar_mask(img: np.ndarray) -> np.ndarray:
    """The bar's colours in a BGR(A) frame: the green HP row and the blue SP row."""
    b, g, r = (img[..., k].astype(np.int16) for k in (0, 1, 2))
    return ((g > 150) & (r < 100) & (b < 120)) | ((b > 150) & (r < 100) & (g < 150))


def find_feet(img: np.ndarray, anchor: Sequence[float]) -> tuple[float, float] | None:
    """Our character's feet on this BGR(A) frame (client px), from the HP/SP bar under them: the
    densest BAR_W x BAR_H block of bar colours near the bar's rest point. None if there is none."""
    rx, ry = anchor[0] + BAR_OFFSET[0], anchor[1] + BAR_OFFSET[1]
    x0 = max(0, int(rx - BAR_SEARCH_PX))
    y0 = max(0, int(ry - BAR_SEARCH_PX))
    win = img[y0 : int(ry + BAR_SEARCH_PX), x0 : int(rx + BAR_SEARCH_PX)]
    if win.shape[0] < BAR_H or win.shape[1] < BAR_W:
        return None
    ii = np.pad(_bar_mask(win).astype(np.int32).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    s = ii[BAR_H:, BAR_W:] - ii[:-BAR_H, BAR_W:] - ii[BAR_H:, :-BAR_W] + ii[:-BAR_H, :-BAR_W]
    ky, kx = np.unravel_index(int(np.argmax(s)), s.shape)
    if s[ky, kx] < 0.25 * BAR_W * BAR_H:  # at least a quarter of the block in bar colours
        return None
    bx, by = x0 + kx + BAR_W / 2, y0 + ky + BAR_H / 2
    return (float(bx - BAR_OFFSET[0]), float(by - BAR_OFFSET[1]))


def jacobian(camera: Any) -> np.ndarray:
    """J (2x2): screen px per cell at our own cell, so screen_delta = J @ cell_delta."""
    o, ex, ey = camera.project(np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]]), None)
    return np.column_stack([ex - o, ey - o])


# --- the route geometry ----------------------------------------------------------------------
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


def _pt(uv: tuple[float, float], kind: str) -> dict[str, Any]:
    return {"x": min(max(uv[0], 0.0), 1.0), "y": min(max(uv[1], 0.0), 1.0), "kind": kind}


class PreviewCore:
    """The preview's state and geometry, one grabbed frame at a time (in-process; testable)."""

    def __init__(self, camera: Any, gat: Any, region: Sequence[int], desktop: Sequence[int],
                 label: str = "") -> None:  # fmt: skip
        self.camera, self.gat = camera, gat
        self.gx, self.gy, self.gw, self.gh = (int(v) for v in region)
        self.dw, self.dh = (int(v) for v in desktop)
        self.label = label[:64]
        self.anchor = np.asarray(camera.project(np.array([[0.0, 0.0]]), None)[0], dtype=float)
        self.jinv = np.linalg.inv(jacobian(camera))
        self.route: list[Cell] = []
        self.goal: Cell | None = None
        self.click: Cell | None = None
        self.active = False
        self.c: np.ndarray | None = None  # the CAMERA's world position (fractional cells)
        self.belief: Cell | None = None  # the walk rule's cell, applied at the next rest
        self.await_motion = False  # a step's belief waits for the move it describes
        self.rest = 0
        self.seg = 0
        self.prev: np.ndarray | None = None
        self.trail: list[tuple[Cell, int]] = []
        self.last: dict[str, Any] = {}  # the last frame's measurements (for the offline check)

    # --- what the walk rule says ------------------------------------------------------------
    def set_route(self, position: Sequence[int], corners: Sequence[Sequence[int]],
                  goal: Sequence[int], click: Sequence[int] | None = None) -> None:  # fmt: skip
        here = (float(position[0]), float(position[1]))
        self.route = [here, *[(float(c[0]), float(c[1])) for c in corners]]
        self.goal = (float(goal[0]), float(goal[1]))
        self.click = None if click is None else (float(click[0]), float(click[1]))
        self.seg, self.active = 0, True
        if self.c is None:  # the plan is made at rest
            self.c = np.array(here)
        self.belief, self.await_motion = here, False

    def snap(self, cell: Sequence[int]) -> None:
        """The rule believes a STEP ends on `cell`: applied to the camera at the first rest AFTER
        the move it describes (the rule may say so before the character starts: 2026-10-08, a
        belief applied before the move put the camera a whole step ahead)."""
        self.belief, self.await_motion = (float(cell[0]), float(cell[1])), True
        self.click = None

    def snap_fix(self, cell: Sequence[int]) -> None:
        """A /where fix: where we stand NOW, applied at the next rest."""
        self.belief, self.await_motion = (float(cell[0]), float(cell[1])), False

    def clear(self) -> dict[str, Any]:
        self.active, self.route, self.trail, self.goal, self.click = False, [], [], None, None
        return {"points": [], "passed": [], "clip": []}

    # --- one frame --------------------------------------------------------------------------
    def to_norm(self, cells: Sequence[Cell], c: np.ndarray) -> list[tuple[float, float]]:
        """Map cells -> desktop-normalized pixels, the camera at world position c."""
        if not cells:
            return []
        rel = np.array([(q[0] - c[0], q[1] - c[1]) for q in cells], dtype=float)
        ci = (int(round(c[0])), int(round(c[1])))
        alt = None
        if self.gat is not None:
            rel_i = rel + np.array([c[0] - ci[0], c[1] - ci[1]])
            alt = self.gat.relative_altitude(ci, rel_i)
            alt = alt - self.gat.relative_altitude(ci, np.array([[c[0] - ci[0], c[1] - ci[1]]]))[0]
        px = self.camera.project(rel, alt)
        return [self._norm(u, v) for u, v in px]

    def _norm(self, u: float, v: float) -> tuple[float, float]:
        return ((self.gx + float(u)) / self.dw, (self.gy + float(v)) / self.dh)

    def step(self, t_ns: int, img: np.ndarray) -> dict[str, Any] | None:
        shift = scene_shift(self.prev, img) if self.prev is not None else (0.0, 0.0)
        self.prev = img
        feet = find_feet(img, self.anchor)
        if self.c is not None:
            self.c = self.c - self.jinv @ np.array(shift)  # the scene moves against the camera
        at_anchor = feet is not None and math.dist(feet, self.anchor) < REST_FEET_PX
        moving = math.hypot(*shift) >= REST_SHIFT_PX or not at_anchor
        if moving:
            self.await_motion = False
        self.rest = 0 if moving else self.rest + 1
        snapped = False
        if self.rest >= REST_FRAMES and self.belief is not None and not self.await_motion:
            self.c, self.belief, snapped = np.array(self.belief), None, True
        self.last = {"t": t_ns, "shift": shift, "feet": feet, "snapped": snapped,
                     "c": None if self.c is None else self.c.tolist()}  # fmt: skip
        if not self.active or self.c is None:
            return None
        c = self.c
        off = np.zeros(2) if feet is None else np.asarray(feet) - self.anchor
        pv = c + self.jinv @ off
        p: Cell = (float(pv[0]), float(pv[1]))
        ahead, self.seg = remaining(self.route, p, self.seg)
        if feet is not None or math.hypot(*shift) >= REST_SHIFT_PX:
            self.trail.append((p, t_ns))
        self.trail = [(q, t) for q, t in self.trail if (t_ns - t) / 1e9 < FADE_S]
        region = (self.gx / self.dw, self.gy / self.dh, (self.gx + self.gw) / self.dw,
                  (self.gy + self.gh) / self.dh)  # fmt: skip
        line = self.to_norm(ahead, c)
        if feet is not None:  # the line starts at the feet the frame SHOWS
            line[0] = self._norm(*feet)
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
        for cell, kind in ((self.goal, "goal"), (self.click, "click")):
            if cell is None:
                continue
            (u, v) = self.to_norm([cell], c)[0]
            if region[0] <= u <= region[2] and region[1] <= v <= region[3]:
                points.append(_pt((u, v), kind))
        passed = []
        tr = self.trail
        for (a, _), (b, tb) in zip(tr, tr[1:], strict=False):
            na, nb = self.to_norm([a, b], c)
            seg = clip_segment(na, nb, region)
            if seg is not None:
                passed.append({"points": [_pt(seg[0], "waypoint"), _pt(seg[1], "waypoint")],
                               "age_ms": int((t_ns - tb) / 1e6)})  # fmt: skip
        clip = [{"x": (self.gx + x0) / self.dw, "y": (self.gy + y0) / self.dh,
                 "w": (x1 - x0) / self.dw, "h": (y1 - y0) / self.dh}
                for x0, y0, x1, y1 in UI_WINDOWS]  # fmt: skip
        return {"points": points[:64], "passed": passed[-16:], "clip": clip, "t": t_ns}


def message(
    body: dict[str, Any], label: str, clock: Callable[[], int] = time.monotonic_ns
) -> dict[str, Any]:
    t = int(body.pop("t", clock()))
    return {"type": "route_preview", "t_mono_ns": t, "frame_id": -1, "live": True, "ttl_ms": 300,
            "label": label, **body}  # fmt: skip


# --- its own process ---------------------------------------------------------------------------
def _run(conn: Any, camera: Any, gat: Any, region: Sequence[int], desktop: Sequence[int],
         label: str, hz: float, log_path: str | None) -> None:  # fmt: skip
    """The preview process: grab -> step -> send, at hz; commands from the walk rule's process."""
    import ro_agent as r

    core = PreviewCore(camera, gat, region, desktop, label)
    agent = r.Agent("route-preview")
    screen = r.Screen()
    log = open(log_path, "a") if log_path else None  # noqa: SIM115 -- closed at stop
    gx, gy, gw, gh = (int(v) for v in region)

    def send(body: dict[str, Any], meas: dict[str, Any] | None = None) -> None:
        msg = message(body, core.label)
        with contextlib.suppress(Exception):  # display only: never a reason to stop
            agent.ws.send(json.dumps(msg))
        if log is not None:
            log.write(json.dumps({**msg, "measured": meas}) + "\n")

    try:
        while True:
            t0 = time.monotonic()
            while conn.poll():
                cmd, args = conn.recv()
                if cmd == "stop":
                    return
                if cmd == "clear":
                    send(core.clear())
                else:
                    getattr(core, cmd)(*args)
            t, img = screen.grab(gx, gy, gw, gh)
            body = core.step(t, img)
            if body is not None:
                send(body, core.last)
            with contextlib.suppress(Exception):  # the backend's status messages: drop them
                while True:
                    agent.ws.recv(timeout=0)
            time.sleep(max(0.0, 1.0 / hz - (time.monotonic() - t0)))
    finally:
        if log is not None:
            log.close()
        with contextlib.suppress(Exception):
            agent.ws.close()


class LivePreview:
    """The walk rule's handle on the preview process."""

    def __init__(
        self, camera: Any, gat: Any, region: Sequence[int], desktop: Sequence[int],
        label: str = "", hz: float = HZ, log_path: Path | None = None,
    ) -> None:  # fmt: skip
        self.args = (camera, gat, tuple(region), tuple(desktop), label[:64], hz,
                     None if log_path is None else str(log_path))  # fmt: skip
        self.proc: Any = None
        self.conn: Any = None

    def start(self) -> LivePreview:
        import multiprocessing as mp

        ctx = mp.get_context("spawn")
        self.conn, child = ctx.Pipe()
        self.proc = ctx.Process(target=_run, args=(child, *self.args), name="route-preview",
                                daemon=True)  # fmt: skip
        self.proc.start()
        return self

    def _cmd(self, name: str, *args: Any) -> None:
        with contextlib.suppress(Exception):
            self.conn.send((name, args))

    def set_route(self, position: Sequence[int], corners: Sequence[Sequence[int]],
                  goal: Sequence[int], click: Sequence[int] | None = None) -> None:  # fmt: skip
        self._cmd("set_route", tuple(position), [tuple(c) for c in corners], tuple(goal),
                  None if click is None else tuple(click))  # fmt: skip

    def snap(self, cell: Sequence[int]) -> None:
        self._cmd("snap", tuple(cell))

    def snap_fix(self, cell: Sequence[int]) -> None:
        self._cmd("snap_fix", tuple(cell))

    def clear(self) -> None:
        self._cmd("clear")

    def stop(self) -> None:
        self._cmd("stop")
        if self.proc is not None:
            self.proc.join(timeout=5)
            if self.proc.is_alive():
                self.proc.terminate()
