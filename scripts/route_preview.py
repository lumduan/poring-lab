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

It runs in its OWN process, scripts/route_previewd.py (the daemon every walk run feeds in CELLS
through scripts/route_plan.py, Batt 2026-10-08), with its own grabber and its own agent
connection, so the walk rule's work cannot starve it. This module is its geometry (PreviewCore)
and its message.

DISPLAY ONLY: nothing here feeds a decision, and the message cannot carry input (the protocol).
"""

from __future__ import annotations

import functools
import math
import time
from collections.abc import Callable, Sequence
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
# The camera's move from FLOOR PATCHES (Batt 2026-10-08): each patch's shift, measured around the
# global shift (coarse to fine: the client's camera can jump ~60 px in one frame at a stop), against
# ITS OWN Jacobian from the camera model + GAT altitude at the floor point under it; a robust least
# squares gives the camera's move. Offline on the 12:49 recording vs packets, the error at the end
# of a step was 5.5 / 9.8 / 10.3 px (median / p95 / max), against 16.8 / 67.0 / 72.9 for the single
# global shift (A, the fallback) and 88 px for per-point patch tracking (it lost most points).
PATCH = 96
PATCH_DOWN = 2  # each patch is correlated at half resolution (48 x 48 real FFTs), refined sub-pixel
PATCH_MIN_Q = 0.15  # the correlation peak a patch needs
PATCH_MIN_STD = 2.0  # a flat patch has nothing to correlate
PATCH_HUBER_PX = 2.0
PATCH_MIN_N = 6  # fewer usable patches: the global shift instead
EASE_S = 0.2  # a correction at a stop eases in over this, never a jump (Batt 2026-10-08)
# A small Kalman filter on the camera position (Batt 2026-10-08; the AR / broadcast-overlay recipe):
# PROCESS = the floor patches' visual odometry (precise frame to frame, drifts over a step);
# MEASUREMENT = the ENGINE's deterministic walk (the rule's path at the walk speed, from the motion
# onset seen on the frames) minus the measured camera lag; FIX = the rule's cell at rest / /where.
# Offline on the 12:49 recording vs packets, the error left for the stop's fix: 0.04 cell median
# (max 0.21) against 0.12 (max 0.38) for the odometry alone; px 2.3 / 9.2 / 9.4 vs 5.3 / 9.9 / 10.2.
KF_Q_PER_S = 0.016  # odometry variance growth (cell^2 per second): ~0.04 cell per 0.1 s frame
KF_SIG_ARRIVE = 0.08  # the engine's camera at its arrival (cells)
KF_SIG_LOOSE = 0.6  # ... and a second or more before it: loose mid-walk (timing, path ties)
KF_SIG_FIX = 0.05  # the rule's cell at rest / a /where fix
DIAGONAL = 1.4  # rAthena's diagonal step cost (MOVE_DIAGONAL_COST 14 / MOVE_COST 10)
# The engine's ONSET is read from the frames, and only AFTER the click. 2026-10-08 13:45: the model
# was armed before the rule's ~1 s hover, a noise frame passed for the onset, and the engine ran the
# step early, pulling the camera a whole step ahead (drift 2.8 cells at a stop)
ONSET_AFTER_CLICK_S = 0.15  # the click reaches the server ~0.18 s later: no motion before this
ONSET_SHIFT_PX, ONSET_FEET_PX, ONSET_FRAMES = 1.0, 4.0, 2  # clear motion, two frames running
ONSET_TIMEOUT_S = 2.5  # nothing moved: a dead click, the engine stands down

Cell = tuple[float, float]


# --- the pixels ------------------------------------------------------------------------------
@functools.lru_cache(maxsize=4)
def _hann(h: int, w: int) -> np.ndarray:
    return (np.hanning(h)[:, None] * np.hanning(w)[None, :]).astype(np.float32)


def _box(g: np.ndarray, k: int) -> np.ndarray:
    """The k x k (odd) box mean of g, edge-padded: separable, by cumulative sums."""
    r = k // 2
    c = np.cumsum(np.pad(g, r, mode="edge"), axis=0, dtype=np.float64)
    c = np.vstack([np.zeros((1, c.shape[1])), c])
    v = (c[k:] - c[:-k]) / k
    c = np.hstack([np.zeros((v.shape[0], 1)), np.cumsum(v, axis=1)])
    return ((c[:, k:] - c[:, :-k]) / k).astype(np.float32)


def _band(img: np.ndarray, down: int, blur: bool = False, highpass: int = 0) -> np.ndarray:
    y0, y1, x0, x1 = BAND
    g = img[y0:y1:down, x0:x1:down, :3].astype(np.float32).mean(-1)
    if blur:
        g = _box(g, 3)
    if highpass:
        g = g - _box(g, highpass)
    g -= g.mean()
    my0, my1, mx0, mx1 = CHAR_MASK
    g[(my0 - y0) // down : (my1 - y0) // down, (mx0 - x0) // down : (mx1 - x0) // down] = 0.0
    return g * _hann(*g.shape)


def _sub(cm: float, c0: float, cp: float) -> float:
    d = cm - 2.0 * c0 + cp
    return 0.0 if d == 0 else float(np.clip(0.5 * (cm - cp) / d, -0.5, 0.5))


def scene_shift(a: np.ndarray, b: np.ndarray, down: int = DOWN, *, blur: bool = False,
                highpass: int = 0, power: float = 1.0) -> tuple[float, float]:  # fmt: skip
    """How far the SCENE moved from frame a to frame b (client px, sub-pixel): phase correlation of
    the band around the character, the client's UI windows excluded.

    The defaults are the previewer's. ``blur`` (3x3), ``highpass`` (minus a k x k box mean) and
    ``power`` < 1 (partial whitening, |R|^power) band-pass the correlation: the HUD scene's choice
    (2026-10-08 night). Measured on the 20:09 walk against the NPCs' own motion, the plain one read
    ~0 on 12 of 140 moving frames (a screen-fixed pattern wins the peak: full resolution doubled
    that); blur + highpass 9 + power 0.5 read ~0 on 1, error p95 8.5 -> 4.6 px, still frames
    unchanged."""
    fa = np.fft.fft2(_band(a, down, blur, highpass))
    fb = np.fft.fft2(_band(b, down, blur, highpass))
    r = fb * np.conj(fa)
    mag = np.abs(r) if power == 1.0 else np.abs(r) ** power
    c = np.fft.ifft2(r / (mag + 1e-9)).real
    h, w = c.shape
    iy, ix = np.unravel_index(int(np.argmax(c)), c.shape)
    dy = iy + _sub(c[iy - 1, ix], c[iy, ix], c[(iy + 1) % h, ix])
    dx = ix + _sub(c[iy, ix - 1], c[iy, ix], c[iy, (ix + 1) % w])
    dy = dy - h if dy > h / 2 else dy
    dx = dx - w if dx > w / 2 else dx
    return (float(dx * down), float(dy * down))


def _patch_usable(x: int, y: int) -> bool:
    """A patch centre clear of the client's UI windows and our own character."""
    h = PATCH // 2
    for x0, y0, x1, y1 in UI_WINDOWS:
        if x0 - 50 <= x <= x1 + 50 and y0 - 50 <= y <= y1 + 50:
            return False
    my0, my1, mx0, mx1 = CHAR_MASK
    if mx0 - h <= x <= mx1 + h and my0 - h <= y <= my1 + h:
        return False
    return h <= x <= 1280 - h and h <= y <= 720 - h


PATCHES = tuple((x, y) for y in range(200, 660, 90) for x in range(300, 1200, 110)
                if _patch_usable(x, y))  # fmt: skip


def gray(img: np.ndarray) -> np.ndarray:
    """The frame's luminance as the uint16 sum of B, G and R, once per frame for every patch. The
    scale does not matter to a phase correlation (2 ms, against 40 ms for a float mean)."""
    return img[..., 0].astype(np.uint16) + img[..., 1] + img[..., 2]


def patch_shifts(
    ga: np.ndarray, gb: np.ndarray, off: Sequence[float]
) -> tuple[list[int], np.ndarray, np.ndarray]:
    """Each usable patch's shift from gray frame ga to gb (client px), measured around the global
    shift ``off``, all patches in one batched FFT: (patch indices, shifts (N, 2), peaks (N,))."""
    h = PATCH // 2
    ox, oy = int(round(off[0])), int(round(off[1]))
    idx = [i for i, (x, y) in enumerate(PATCHES)
           if h <= x + ox <= ga.shape[1] - h and h <= y + oy <= ga.shape[0] - h]  # fmt: skip
    if not idx:
        return [], np.zeros((0, 2)), np.zeros(0)
    pa = np.stack([ga[PATCHES[i][1] - h : PATCHES[i][1] + h, PATCHES[i][0] - h : PATCHES[i][0] + h]
                   for i in idx])  # fmt: skip
    pb = np.stack([gb[PATCHES[i][1] + oy - h : PATCHES[i][1] + oy + h,
                      PATCHES[i][0] + ox - h : PATCHES[i][0] + ox + h] for i in idx])  # fmt: skip
    dn = PATCH_DOWN
    pa = pa[:, ::dn, ::dn].astype(np.float32) / 3.0  # back to 0..255
    pb = pb[:, ::dn, ::dn].astype(np.float32) / 3.0
    m = PATCH // dn
    textured = (pa.std(axis=(1, 2)) >= PATCH_MIN_STD) & (pb.std(axis=(1, 2)) >= PATCH_MIN_STD)
    hann = _hann(m, m)
    fa = np.fft.rfft2((pa - pa.mean(axis=(1, 2), keepdims=True)) * hann)
    fb = np.fft.rfft2((pb - pb.mean(axis=(1, 2), keepdims=True)) * hann)
    r = fb * np.conj(fa)
    c = np.fft.irfft2(r / (np.abs(r) + 1e-9), s=(m, m))
    flat = c.reshape(len(idx), -1).argmax(1)
    iy, ix = flat // m, flat % m
    n = np.arange(len(idx))
    q = c[n, iy, ix]
    keep, out, qs = [], [], []
    for k in range(len(idx)):
        if not textured[k] or q[k] < PATCH_MIN_Q:
            continue
        ck, y0, x0 = c[k], int(iy[k]), int(ix[k])
        dy = y0 + _sub(ck[y0 - 1, x0], ck[y0, x0], ck[(y0 + 1) % m, x0])
        dx = x0 + _sub(ck[y0, x0 - 1], ck[y0, x0], ck[y0, (x0 + 1) % m])
        dy = dy - m if dy > m / 2 else dy
        dx = dx - m if dx > m / 2 else dx
        keep.append(idx[k])
        out.append((dx * dn + ox, dy * dn + oy))
        qs.append(float(q[k]))
    return keep, np.array(out, dtype=float).reshape(-1, 2), np.array(qs, dtype=float)


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
        self.prev_gray: np.ndarray | None = None
        self.ease_from = np.zeros(2)  # the correction still being eased in (cells)
        self.ease_t0 = 0
        self.var = 0.0  # the Kalman variance of c (cells^2, isotropic)
        self.rest_cell: np.ndarray | None = (
            None  # the rule's cell for THIS rest: measured each frame
        )
        self.engine: dict[str, Any] | None = None  # the rule's walk, armed at its click
        self.t_prev = 0
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

    def walk(self, start: Sequence[int], path: Sequence[Sequence[int]], ms_per_cell: float,
             t_click_ns: int) -> None:  # fmt: skip
        """The rule CLICKED (at t_click_ns) a walk from `start` along `path` (cells after start):
        the ENGINE's model, timed from the motion onset the frames show after the click."""
        cells = [(int(c[0]), int(c[1])) for c in path if (int(c[0]), int(c[1])) != tuple(start)]
        if not cells:
            self.engine = None
            return
        self.engine = {"start": (float(start[0]), float(start[1])), "path": cells,
                       "ms": float(ms_per_cell), "t_click": int(t_click_ns), "run": 0,
                       "first": None, "onset": None, "arrive": None}  # fmt: skip

    def _engine_pos(self, t_ns: int) -> np.ndarray:
        e = self.engine
        assert e is not None and e["onset"] is not None
        p, t = np.array(e["start"]), float(e["onset"])
        for q in e["path"]:
            dt = e["ms"] * (DIAGONAL if (q[0] != p[0] and q[1] != p[1]) else 1.0) * 1e6
            if t_ns <= t + dt:
                return p + max(0.0, (t_ns - t) / dt) * (np.array(q, dtype=float) - p)
            t += dt
            p = np.array(q, dtype=float)
        return p

    def _kf(self, z: np.ndarray, sig: float) -> np.ndarray:
        """A Kalman update of c towards z; returns the correction applied (cells)."""
        assert self.c is not None
        k = self.var / (self.var + sig * sig)
        corr = k * (z - self.c)
        self.c = self.c + corr
        self.var = (1.0 - k) * self.var
        return corr

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

    def _ease(self, t_ns: int) -> np.ndarray:
        k = max(0.0, 1.0 - (t_ns - self.ease_t0) / (EASE_S * 1e9))
        return self.ease_from * k

    def _norm(self, u: float, v: float) -> tuple[float, float]:
        return ((self.gx + float(u)) / self.dw, (self.gy + float(v)) / self.dh)

    def _project_rel(self, c: np.ndarray, rel: np.ndarray) -> np.ndarray:
        """Offsets from the camera (N, 2) -> client px, the camera at c (GAT altitude)."""
        alt = None
        if self.gat is not None:
            ci = (int(round(c[0])), int(round(c[1])))
            frac = np.asarray(c, dtype=float) - ci
            alt = self.gat.relative_altitude(ci, rel + frac)
            alt = alt - self.gat.relative_altitude(ci, frac[None, :])[0]
        return np.asarray(self.camera.project(rel, alt), dtype=float)

    def _project_from(self, c: np.ndarray, world: np.ndarray) -> np.ndarray:
        """World cells (N, 2) -> client px, the camera at c."""
        return self._project_rel(c, world - c)

    def _with_jacobian(self, c: np.ndarray, rel: np.ndarray, h: float = 1e-2) -> tuple[
        np.ndarray, np.ndarray, np.ndarray
    ]:  # fmt: skip
        """px of c + rel, and its derivatives along rel x and y: ONE projection call."""
        n = len(rel)
        px = self._project_rel(c, np.vstack([rel, rel + [h, 0.0], rel + [0.0, h]]))
        return px[:n], (px[n : 2 * n] - px[:n]) / h, (px[2 * n :] - px[:n]) / h

    def _camera_jacobian(
        self, c: np.ndarray, world: np.ndarray, h: float = 1e-2
    ) -> tuple[np.ndarray, np.ndarray]:
        """How each floor point's px moves per cell of CAMERA move (x, y). The camera's own
        altitude reference moves with it (it follows the terrain): measured, it matters
        (2026-10-08: the floor-offset derivative alone gave 8 / 30 px at a step's end, this
        5.5 / 9.8). The three projections share ONE camera.project call."""
        cs = [np.asarray(c, dtype=float), c + np.array([h, 0.0]), c + np.array([0.0, h])]
        rels, alts = [], []
        for ck in cs:
            rel = world - ck
            rels.append(rel)
            if self.gat is not None:
                ci = (int(round(ck[0])), int(round(ck[1])))
                frac = ck - ci
                a = self.gat.relative_altitude(ci, rel + frac)
                alts.append(a - self.gat.relative_altitude(ci, frac[None, :])[0])
        alt = None if self.gat is None else np.concatenate(alts)
        px = np.asarray(self.camera.project(np.vstack(rels), alt), dtype=float)
        n = len(world)
        return (px[n : 2 * n] - px[:n]) / h, (px[2 * n :] - px[:n]) / h

    def _floor_points(self, c: np.ndarray, px: np.ndarray) -> np.ndarray:
        """The world floor points (N, 2) seen at client px (N, 2), the camera at c: Newton,
        vectorized; two steps from the camera model's local Jacobian are enough."""
        rel = (px - self.anchor) @ self.jinv.T
        for _ in range(2):
            p, jx, jy = self._with_jacobian(c, rel)
            r = p - px
            det = jx[:, 0] * jy[:, 1] - jy[:, 0] * jx[:, 1]
            det = np.where(np.abs(det) < 1e-9, 1e-9, det)
            ux = (jy[:, 1] * r[:, 0] - jy[:, 0] * r[:, 1]) / det
            uy = (-jx[:, 1] * r[:, 0] + jx[:, 0] * r[:, 1]) / det
            rel = rel - np.stack([ux, uy], axis=1)
        return np.asarray(c) + rel

    def camera_move(self, ga: np.ndarray, gb: np.ndarray, c: np.ndarray,
                    off: Sequence[float]) -> tuple[np.ndarray | None, int]:  # fmt: skip
        """The camera's move (cells) from gray frame ga to gb: each floor patch's shift against its
        own Jacobian (camera model + GAT), robust least squares. None below PATCH_MIN_N patches."""
        idx, s, q = patch_shifts(ga, gb, off)
        if len(idx) < PATCH_MIN_N:
            return None, len(idx)
        world = self._floor_points(c, np.array([PATCHES[i] for i in idx], dtype=float))
        jx, jy = self._camera_jacobian(c, world)
        w, d = q.copy(), np.zeros(2)
        for _ in range(4):  # IRLS, Huber
            axx, axy = np.sum(w * (jx * jx).sum(1)), np.sum(w * (jx * jy).sum(1))
            A = np.array([[axx, axy], [axy, np.sum(w * (jy * jy).sum(1))]])
            rhs = np.array([np.sum(w * (jx * s).sum(1)), np.sum(w * (jy * s).sum(1))])
            d = np.linalg.solve(A, rhs)
            res = np.linalg.norm(s - (jx * d[0] + jy * d[1]), axis=1)
            w = q * np.where(res > PATCH_HUBER_PX, PATCH_HUBER_PX / np.maximum(res, 1e-6), 1.0)
        return d, len(idx)

    def step(self, t_ns: int, img: np.ndarray) -> dict[str, Any] | None:
        shift = scene_shift(self.prev, img) if self.prev is not None else (0.0, 0.0)
        g = gray(img)
        n_patches = 0
        dt = max(0.0, (t_ns - self.t_prev) / 1e9) if self.t_prev else 0.0
        if self.c is not None and self.prev is not None and self.prev_gray is not None:
            d, n_patches = self.camera_move(self.prev_gray, g, self.c, shift)
            # PREDICT: the floor patches' fit, else the global shift (the scene moves against
            # the camera); the variance grows with time
            self.c = self.c + d if d is not None else self.c - self.jinv @ np.array(shift)
            self.var += KF_Q_PER_S * dt
        self.prev, self.prev_gray = img, g
        feet = find_feet(img, self.anchor)
        at_anchor = feet is not None and math.dist(feet, self.anchor) < REST_FEET_PX
        moving = math.hypot(*shift) >= REST_SHIFT_PX or not at_anchor
        if moving:
            self.await_motion, self.rest_cell = False, None
        self.rest = 0 if moving else self.rest + 1
        corr = np.zeros(2)
        e = self.engine
        if e is not None and self.c is not None:
            clear = math.hypot(*shift) >= ONSET_SHIFT_PX or (
                feet is not None and math.dist(feet, self.anchor) >= ONSET_FEET_PX
            )
            if e["onset"] is None and t_ns >= e["t_click"] + ONSET_AFTER_CLICK_S * 1e9:
                if clear:
                    if e["run"] == 0:  # between the last still frame and this one
                        e["first"] = (self.t_prev + t_ns) // 2 if self.t_prev else t_ns
                    e["run"] += 1
                else:
                    e["run"] = 0
            if e["onset"] is None and e["run"] >= ONSET_FRAMES:
                e["onset"] = e["first"]
                legs = zip([e["start"], *e["path"][:-1]], e["path"], strict=True)
                secs = sum(e["ms"] / 1000 * (DIAGONAL if (q[0] != a[0] and q[1] != a[1]) else 1.0)
                           for a, q in legs)  # fmt: skip
                e["arrive"] = e["onset"] + int(1e9 * secs)
            if e["onset"] is not None and feet is not None:  # MEASURE: the engine's camera
                z = self._engine_pos(t_ns) - self.jinv @ (np.asarray(feet) - self.anchor)
                rem = max(0.0, (e["arrive"] - t_ns) / 1e9)
                corr += self._kf(z, KF_SIG_ARRIVE + KF_SIG_LOOSE * min(rem, 1.0))
                # what it moves eases in on screen too (2026-10-08 v5: up to 0.36 cell a frame)
                self.ease_from, self.ease_t0 = -corr + self._ease(t_ns), t_ns
            if e["onset"] is not None and t_ns > e["arrive"] + 1e9 and not moving:
                self.engine = None  # the walk is over
            elif e["onset"] is None and t_ns > e["t_click"] + ONSET_TIMEOUT_S * 1e9:
                self.engine = None  # nothing moved: a dead click
        snapped = False
        if self.rest >= REST_FRAMES and self.belief is not None and not self.await_motion:
            if self.c is None:
                self.c = np.array(self.belief)
            self.rest_cell, self.belief, snapped = np.array(self.belief), None, True
        if self.rest_cell is not None and self.rest >= REST_FRAMES:
            # FIX: the rule's cell is measured on EVERY rest frame until the next move, so the
            # filter converges (~5-8 frames) instead of leaving part of the error for the next
            # step; what each update moves eases in on screen (never a jump)
            fix = self._kf(self.rest_cell, KF_SIG_FIX)
            self.ease_from, self.ease_t0 = -fix + self._ease(t_ns), t_ns
        self.t_prev = t_ns
        self.last = {"t": t_ns, "shift": shift, "feet": feet, "snapped": snapped,
                     "patches": n_patches, "var": round(self.var, 4),
                     "engine_corr": [round(float(v), 3) for v in corr],
                     "c": None if self.c is None else self.c.tolist()}  # fmt: skip
        if not self.active or self.c is None:
            return None
        c = self.c + self._ease(t_ns)  # the camera as DRAWN
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
    return {"type": "route_preview", "t_mono_ns": t, "frame_id": -1, "live": True, "label": label,
            **body}  # fmt: skip
