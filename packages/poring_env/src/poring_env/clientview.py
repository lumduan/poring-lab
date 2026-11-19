"""The virtual 1280x720 client (docs/planning/fullscreen-client.md section 7; Batt 2026-11-18:
"support every screen size; find a way with calculation, like vectors").

Everything the bot reads and clicks was built on a 1280x720 client. RO does not scale its picture
with the screen: its interface panels keep their pixel size, anchored to a corner or an edge, and
the 3D world keeps the player at the centre. So a point of the client is mapped by a VECTOR:

- a UI point: ``real = panel.real_xy + (virtual - panel.virtual_xy)`` -- the panel moved by its
  anchor's vector, same size (scale 1);
- a world point: ``real = centre_real + k * (virtual - centre_virtual)`` -- a vector from the
  centre scaled by the world's scale ``k`` at that size (1 at 1280x720).

A ``ClientView`` holds one frame's client: where it is in the frame (a window anywhere, or the
whole frame in fullscreen), the world's scale and centre, and where each panel is. It maps a
virtual point to the frame (clicks), a frame point back (reads), and builds the virtual 1280x720
picture from a real frame -- so the code built on 1280x720 runs unchanged on any screen.

Pure: numpy only, no X, no I/O.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

VIRTUAL_W, VIRTUAL_H = 1280, 720
Box = tuple[int, int, int, int]  # x, y, w, h
Anchor = Literal["tl", "tr", "bl", "br", "t", "b", "l", "r", "c"]
Mode = Literal["window", "fullscreen"]


def anchor_point(anchor: Anchor, w: float, h: float) -> tuple[float, float]:
    """PURE: the anchor's point in a w x h client (tl = top-left ... c = the centre)."""
    xs = {"l": 0.0, "c": w / 2, "r": float(w)}
    ys = {"t": 0.0, "c": h / 2, "b": float(h)}
    horiz = {"tl": "l", "tr": "r", "bl": "l", "br": "r", "t": "c", "b": "c", "l": "l", "r": "r",
             "c": "c"}[anchor]  # fmt: skip
    vert = {"tl": "t", "tr": "t", "bl": "b", "br": "b", "t": "t", "b": "b", "l": "c", "r": "c",
            "c": "c"}[anchor]  # fmt: skip
    return xs[horiz], ys[vert]


@dataclass(frozen=True)
class Panel:
    """One interface panel: its box in the virtual client, and its top-left in the REAL client
    (client pixels; its size is the same: RO's interface does not scale)."""

    name: str
    virtual: Box
    real_xy: tuple[int, int]

    @classmethod
    def anchored(cls, name: str, virtual: Box, anchor: Anchor,
                 real_size: tuple[int, int]) -> Panel:  # fmt: skip
        """The panel at the same vector from ``anchor`` in a real client of ``real_size`` as
        from that anchor in the virtual 1280x720 one (a panel that sticks to a corner or edge)."""
        vx, vy, _, _ = virtual
        ax_v, ay_v = anchor_point(anchor, VIRTUAL_W, VIRTUAL_H)
        ax_r, ay_r = anchor_point(anchor, *real_size)
        return cls(name, virtual, (round(ax_r + (vx - ax_v)), round(ay_r + (vy - ay_v))))

    @property
    def offset(self) -> tuple[int, int]:
        """The panel's vector: real top-left minus virtual top-left."""
        return self.real_xy[0] - self.virtual[0], self.real_xy[1] - self.virtual[1]

    def holds_virtual(self, vx: float, vy: float) -> bool:
        x, y, w, h = self.virtual
        return x <= vx < x + w and y <= vy < y + h

    def holds_real(self, cx: float, cy: float) -> bool:
        x, y = self.real_xy
        _, _, w, h = self.virtual
        return x <= cx < x + w and y <= cy < y + h


@dataclass(frozen=True)
class ClientView:
    """One frame's client. ``rect``: the client's area in the frame (frame pixels: a window's
    client area, or the whole frame in fullscreen). ``world_scale``: real pixels per virtual pixel
    of the 3D world. ``world_centre``: the real-client point of the virtual centre (640, 360);
    None = the real client's centre. ``panels``: the interface panels, later ones drawn on top."""

    rect: Box
    mode: Mode = "window"
    world_scale: float = 1.0
    world_centre: tuple[float, float] | None = None
    panels: tuple[Panel, ...] = ()

    @property
    def size(self) -> tuple[int, int]:
        return self.rect[2], self.rect[3]

    @property
    def centre(self) -> tuple[float, float]:
        if self.world_centre is not None:
            return self.world_centre
        return self.rect[2] / 2, self.rect[3] / 2

    @property
    def identity(self) -> bool:
        """The client IS the virtual one: 1280x720, the world unscaled, every panel in place."""
        return (
            self.size == (VIRTUAL_W, VIRTUAL_H)
            and self.world_scale == 1.0
            and self.centre == (VIRTUAL_W / 2, VIRTUAL_H / 2)
            and all(p.offset == (0, 0) for p in self.panels)
        )

    def panel_at(self, vx: float, vy: float) -> Panel | None:
        """The panel drawn at a virtual point (the topmost), or None: the world."""
        for p in reversed(self.panels):
            if p.holds_virtual(vx, vy):
                return p
        return None

    def to_client(self, vx: float, vy: float) -> tuple[float, float]:
        """A virtual point -> the real CLIENT point (client pixels)."""
        p = self.panel_at(vx, vy)
        if p is not None:
            dx, dy = p.offset
            return vx + dx, vy + dy
        cx, cy = self.centre
        k = self.world_scale
        return cx + k * (vx - VIRTUAL_W / 2), cy + k * (vy - VIRTUAL_H / 2)

    def to_real(self, vx: float, vy: float) -> tuple[float, float]:
        """A virtual point -> the FRAME point (where a click must land)."""
        x, y = self.to_client(vx, vy)
        return self.rect[0] + x, self.rect[1] + y

    def to_virtual(self, fx: float, fy: float) -> tuple[float, float]:
        """A frame point -> the virtual point (the inverse of to_real): inside a panel's real box
        by its vector, else by the world's inverse."""
        cx_, cy_ = fx - self.rect[0], fy - self.rect[1]
        for p in reversed(self.panels):
            if p.holds_real(cx_, cy_):
                dx, dy = p.offset
                return cx_ - dx, cy_ - dy
        cx, cy = self.centre
        k = self.world_scale
        return VIRTUAL_W / 2 + (cx_ - cx) / k, VIRTUAL_H / 2 + (cy_ - cy) / k

    def virtual_frame(self, frame: NDArray[np.uint8]) -> NDArray[np.uint8]:
        """The virtual 1280x720 picture of a real frame (H, W, C): the world resampled around the
        centre (nearest pixel; a plain crop at scale 1), then each panel copied to its virtual
        place. Parts outside the real client are 0."""
        x0, y0, w, h = self.rect
        client = frame[max(0, y0) : y0 + h, max(0, x0) : x0 + w]
        ch, cw = client.shape[:2]
        out = np.zeros((VIRTUAL_H, VIRTUAL_W, *frame.shape[2:]), dtype=frame.dtype)
        cx, cy = self.centre
        k = self.world_scale
        xs = np.floor(cx + k * (np.arange(VIRTUAL_W) + 0.5 - VIRTUAL_W / 2)).astype(np.int64)
        ys = np.floor(cy + k * (np.arange(VIRTUAL_H) + 0.5 - VIRTUAL_H / 2)).astype(np.int64)
        _resample_into(out, client, xs, ys, cw, ch, 0, 0)
        # a panel sits ON the world in the real frame: the world layer shows it again, shrunk, as a
        # ghost where the world transform puts its real box. The world behind it is unknown: blank
        for p in self.panels:
            rx, ry = p.real_xy
            _, _, pw, ph = p.virtual
            gx0 = VIRTUAL_W / 2 + (rx - cx) / k
            gy0 = VIRTUAL_H / 2 + (ry - cy) / k
            gx1 = VIRTUAL_W / 2 + (rx + pw - cx) / k
            gy1 = VIRTUAL_H / 2 + (ry + ph - cy) / k
            x0_, x1_ = max(0, int(np.floor(gx0))), min(VIRTUAL_W, int(np.ceil(gx1)))
            y0_, y1_ = max(0, int(np.floor(gy0))), min(VIRTUAL_H, int(np.ceil(gy1)))
            if x1_ > x0_ and y1_ > y0_ and not self.identity:
                out[y0_:y1_, x0_:x1_] = 0
        for p in self.panels:
            vx, vy, pw, ph = p.virtual
            rx, ry = p.real_xy
            sx0, sy0 = max(0, rx), max(0, ry)
            sx1, sy1 = min(cw, rx + pw), min(ch, ry + ph)
            if sx1 <= sx0 or sy1 <= sy0:
                continue  # the panel is off the real client
            dx0, dy0 = vx + (sx0 - rx), vy + (sy0 - ry)
            tx0, ty0 = max(0, dx0), max(0, dy0)
            tx1 = min(VIRTUAL_W, dx0 + (sx1 - sx0))
            ty1 = min(VIRTUAL_H, dy0 + (sy1 - sy0))
            if tx1 <= tx0 or ty1 <= ty0:
                continue
            sy, sx = sy0 + (ty0 - dy0), sx0 + (tx0 - dx0)
            out[ty0:ty1, tx0:tx1] = client[sy : sy + (ty1 - ty0), sx : sx + (tx1 - tx0)]
        return out

    # --- one box of the virtual picture from the real pixels it needs (s11scr, 2026-11-19) -----
    # A virtual read of a 64 x 64 box took 69 ms at 1920x1080: the whole real frame came through
    # the grab pipe and the whole virtual picture was built, to cut 64 x 64 of it (a real 64 x 64
    # read: 3.4 ms). The cursor check reads every 30 ms inside 0.35 s, so it got ~4 reads instead
    # of ~10 and its SWORD verdict came late or never ("unknown" 57 % at 1080, 0-5 % at 720).
    # These two give exactly virtual_frame(frame)[y:y+h, x:x+w] from the frame's sub-rectangle
    # that holds every real pixel the box reads (test_clientview: equal on random boxes).

    def _world_axes(self, x: int, y: int, w: int, h: int) -> tuple[NDArray[np.int64], ...]:
        cx, cy = self.centre
        k = self.world_scale
        xs = np.floor(cx + k * (np.arange(x, x + w) + 0.5 - VIRTUAL_W / 2)).astype(np.int64)
        ys = np.floor(cy + k * (np.arange(y, y + h) + 0.5 - VIRTUAL_H / 2)).astype(np.int64)
        return xs, ys

    def _client_box(self, frame_size: tuple[int, int]) -> tuple[int, int, int, int]:
        """The client's top-left in the frame and its size there (virtual_frame's ``client``)."""
        x0, y0, w, h = self.rect
        fw, fh = frame_size
        ox, oy = max(0, x0), max(0, y0)
        return ox, oy, max(0, min(fw, x0 + w) - ox), max(0, min(fh, y0 + h) - oy)

    def _panel_copy(self, p: Panel, cw: int, ch: int) -> tuple[int, int, int, int, int, int] | None:
        """A panel's copy as virtual_frame makes it: (tx0, ty0, tx1, ty1, sx, sy) -- the virtual
        target box and its source top-left in client pixels -- or None (off the client)."""
        vx, vy, pw, ph = p.virtual
        rx, ry = p.real_xy
        sx0, sy0 = max(0, rx), max(0, ry)
        sx1, sy1 = min(cw, rx + pw), min(ch, ry + ph)
        if sx1 <= sx0 or sy1 <= sy0:
            return None
        dx0, dy0 = vx + (sx0 - rx), vy + (sy0 - ry)
        tx0, ty0 = max(0, dx0), max(0, dy0)
        tx1, ty1 = min(VIRTUAL_W, dx0 + (sx1 - sx0)), min(VIRTUAL_H, dy0 + (sy1 - sy0))
        if tx1 <= tx0 or ty1 <= ty0:
            return None
        return tx0, ty0, tx1, ty1, sx0 + (tx0 - dx0), sy0 + (ty0 - dy0)

    def _ghost(self, p: Panel) -> tuple[int, int, int, int] | None:
        """The panel's ghost in the world layer (virtual x0, y0, x1, y1), blanked; or None."""
        if self.identity:
            return None
        cx, cy = self.centre
        k = self.world_scale
        rx, ry = p.real_xy
        _, _, pw, ph = p.virtual
        x0_ = max(0, int(np.floor(VIRTUAL_W / 2 + (rx - cx) / k)))
        x1_ = min(VIRTUAL_W, int(np.ceil(VIRTUAL_W / 2 + (rx + pw - cx) / k)))
        y0_ = max(0, int(np.floor(VIRTUAL_H / 2 + (ry - cy) / k)))
        y1_ = min(VIRTUAL_H, int(np.ceil(VIRTUAL_H / 2 + (ry + ph - cy) / k)))
        return (x0_, y0_, x1_, y1_) if x1_ > x0_ and y1_ > y0_ else None

    def source_rect(self, box: Box, frame_size: tuple[int, int]) -> Box | None:
        """PURE: the frame rectangle (x, y, w, h) holding every real pixel that the virtual box
        (x, y, w, h) reads in virtual_frame, for a frame of ``frame_size``; None: none."""
        x, y, w, h = box
        ox, oy, cw, ch = self._client_box(frame_size)
        xs, ys = self._world_axes(x, y, w, h)
        xs, ys = xs[(xs >= 0) & (xs < cw)], ys[(ys >= 0) & (ys < ch)]
        rects: list[tuple[int, int, int, int]] = []
        if xs.size and ys.size:
            rects.append((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
        for p in self.panels:
            c = self._panel_copy(p, cw, ch)
            if c is None:
                continue
            tx0, ty0, tx1, ty1, sx, sy = c
            ix0, iy0 = max(tx0, x), max(ty0, y)
            ix1, iy1 = min(tx1, x + w), min(ty1, y + h)
            if ix1 > ix0 and iy1 > iy0:
                rects.append((sx + ix0 - tx0, sy + iy0 - ty0, sx + ix1 - tx0, sy + iy1 - ty0))
        if not rects:
            return None
        ux0, uy0 = min(r[0] for r in rects), min(r[1] for r in rects)
        ux1, uy1 = max(r[2] for r in rects), max(r[3] for r in rects)
        return ox + ux0, oy + uy0, ux1 - ux0, uy1 - uy0

    def crop_from(self, region: NDArray[np.uint8], region_rect: Box | None, box: Box,
                  frame_size: tuple[int, int]) -> NDArray[np.uint8]:  # fmt: skip
        """PURE: virtual_frame(frame)[y:y+h, x:x+w] built from ``region``, the frame's pixels
        at ``region_rect`` (source_rect's; None: nothing is read, the box is all 0)."""
        x, y, w, h = box
        out = np.zeros((h, w, *region.shape[2:]), dtype=region.dtype)
        if region_rect is None:
            return out
        ox, oy, cw, ch = self._client_box(frame_size)
        bx, by = region_rect[0] - ox, region_rect[1] - oy  # the region's origin, client pixels
        xs, ys = self._world_axes(x, y, w, h)
        _resample_into(out, region, xs, ys, cw, ch, bx, by)
        for p in self.panels:
            g = self._ghost(p)
            if g is None:
                continue
            gx0, gy0, gx1, gy1 = g
            ix0, iy0 = max(gx0, x), max(gy0, y)
            ix1, iy1 = min(gx1, x + w), min(gy1, y + h)
            if ix1 > ix0 and iy1 > iy0:
                out[iy0 - y : iy1 - y, ix0 - x : ix1 - x] = 0
        for p in self.panels:
            c = self._panel_copy(p, cw, ch)
            if c is None:
                continue
            tx0, ty0, tx1, ty1, sx, sy = c
            ix0, iy0 = max(tx0, x), max(ty0, y)
            ix1, iy1 = min(tx1, x + w), min(ty1, y + h)
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            ssx, ssy = sx + (ix0 - tx0) - bx, sy + (iy0 - ty0) - by
            out[iy0 - y : iy1 - y, ix0 - x : ix1 - x] = region[
                ssy : ssy + (iy1 - iy0), ssx : ssx + (ix1 - ix0)
            ]
        return out


def _resample_into(
    out: NDArray[np.uint8],
    src: NDArray[np.uint8],
    xs: NDArray[np.int64],
    ys: NDArray[np.int64],
    cw: int,
    ch: int,
    bx: int,
    by: int,
) -> None:
    """The world's nearest-pixel resample: ``out[i, j] = src[ys[i] - by, xs[j] - bx]`` wherever
    the client pixel (xs[j], ys[i]) lies inside the cw x ch client, else ``out`` stays. ``xs`` and
    ``ys`` only grow, so the inside ones are one run each: a slice and two axis takes (~1 ms for
    the 1280x720 picture at 1080p; the 2-D fancy index took ~20-45 ms)."""
    okx = np.flatnonzero((xs >= 0) & (xs < cw))
    oky = np.flatnonzero((ys >= 0) & (ys < ch))
    if okx.size == 0 or oky.size == 0:
        return
    c0, c1, r0, r1 = int(okx[0]), int(okx[-1]) + 1, int(oky[0]), int(oky[-1]) + 1
    rows = np.take(src, ys[r0:r1] - by, axis=0)
    out[r0:r1, c0:c1] = np.take(rows, xs[c0:c1] - bx, axis=1)


def anchored_view(rect: Box, mode: Mode, layout: Sequence[tuple[str, Box, Anchor]], *,
                  world_scale: float = 1.0) -> ClientView:  # fmt: skip
    """PURE: a view whose panels each stick to their anchor (``layout``: name, virtual box,
    anchor) in a real client of ``rect``'s size -- the default before the panels are found."""
    size = (rect[2], rect[3])
    panels = tuple(Panel.anchored(name, box, anchor, size) for name, box, anchor in layout)
    return ClientView(rect, mode, world_scale, None, panels)
