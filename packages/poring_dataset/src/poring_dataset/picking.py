"""Which cell the client walks to for a pixel: the camera ray against the GAT's TOP surfaces.

walk@8/9 indoors (prt_church, 2026-10-08) clicked the projected centre of a cell and the server
walked to a NEIGHBOUR 19 + 6 times, always on the camera's side ((-1,-1), (0,-1), (-1,0) with the
indoor yaw): every time the neighbour was a RAISED walkable block (a pew's kneeler, all four corners
one cell = 5 units up). The client picks the first top surface the ray comes down through, so a
raised block's top covers the floor just behind it on screen. Side walls are not picked: the ray
passes through them to the floor behind (a march that counted the walls mispredicted 18 clicks).

Design-time check against the packets (offline, the tuning maps): this model names the server's
cell for 480 / 485 indoor clicks (the flat centre projection: 467) and 383 / 383 outdoor
(prt_fild08); the 5 misses lie 1-5 px from the model's cell boundary, hence ``safe_points``'
margin. The camera indoors is the console's carried-over yaw/distance (camera_rdp.json: not
measured on RDP), which is the likely source of those few pixels.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from poring_dataset.camera import CELL, Camera
from poring_dataset.gat import Gat

Array = npt.NDArray[np.float64]
NONE = -(10**6)  # no surface hit (off the map / outside the height band)
STEP = 0.05  # world units between march samples (a cell is 5)
WINDOW = 30  # cells around the origin whose heights bound the march
CHUNK = 1024  # pixels per march batch


def _heights(tiles: npt.NDArray[np.void], fx: Array, fy: Array) -> Array:
    """The bilinear GAT surface in each sample's tile, UP positive (GAT heights are negative-up)."""
    sw, se = tiles["sw"].astype(float), tiles["se"].astype(float)
    nw, ne = tiles["nw"].astype(float), tiles["ne"].astype(float)
    return np.asarray(-((sw * (1 - fx) + se * fx) * (1 - fy) + (nw * (1 - fx) + ne * fx) * fy))


def pick_cells(camera: Camera, gat: Gat, origin: tuple[int, int], px: Array,
               step: float = STEP) -> npt.NDArray[np.int64]:  # fmt: skip
    """(N, 2) cell OFFSETS from ``origin`` the client picks under client pixels ``px`` (N, 2): the
    first tile top the camera ray comes down through ((NONE, NONE) for no hit). ``origin`` is the
    cell the camera follows (our own)."""
    pts = np.atleast_2d(np.asarray(px, dtype=float))
    if len(pts) > CHUNK:  # bounded memory: (pixels x samples) arrays per chunk
        return np.concatenate([_pick(camera, gat, origin, pts[i : i + CHUNK], step)
                               for i in range(0, len(pts), CHUNK)])  # fmt: skip
    return _pick(camera, gat, origin, pts, step)


def _pick(camera: Camera, gat: Gat, origin: tuple[int, int], pts: Array,
          step: float) -> npt.NDArray[np.int64]:  # fmt: skip
    eye, right, up, fwd = camera.basis()
    f = (camera.height / 2) / np.tan(camera.fov / 2)
    d = (fwd[None, :] + ((pts[:, 0] - camera.cx) / f)[:, None] * right[None, :]
         - ((pts[:, 1] - camera.cy) / f)[:, None] * up[None, :])  # fmt: skip
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    ox, oy = origin
    base = float(gat.altitude[oy, ox])
    y0, y1 = max(0, oy - WINDOW), min(gat.height, oy + WINDOW + 1)
    x0, x1 = max(0, ox - WINDOW), min(gat.width, ox + WINDOW + 1)
    win = gat.tiles[y0:y1, x0:x1]
    corners = -np.stack([win[n].astype(float) for n in ("sw", "se", "nw", "ne")]) - base
    top, bottom = float(corners.max()) + 1.0, float(corners.min()) - 1.0
    # the march covers only the height band the window's surfaces occupy
    t0 = (eye[1] - top) / -d[:, 1]
    t1 = (eye[1] - bottom) / -d[:, 1]
    k = max(2, int(np.ceil(float((t1 - t0).max()) / step)) + 1)
    t = t0[:, None] + (t1 - t0)[:, None] * np.linspace(0.0, 1.0, k)[None, :]
    p = eye[None, None, :] + t[:, :, None] * d[:, None, :]
    cx, cy = ox + p[..., 0] / CELL, oy + p[..., 2] / CELL
    ix, iy = np.floor(cx + 0.5).astype(int), np.floor(cy + 0.5).astype(int)
    ok = (ix >= 0) & (ix < gat.width) & (iy >= 0) & (iy < gat.height)
    tiles = gat.tiles[np.clip(iy, 0, gat.height - 1), np.clip(ix, 0, gat.width - 1)]
    h = _heights(tiles, cx + 0.5 - ix, cy + 0.5 - iy) - base
    # the previous sample on THIS sample's tile: above it -> the ray came down through the top;
    # below it -> it entered through a side wall, which the client does not pick
    pcx = np.concatenate([cx[:, :1], cx[:, :-1]], axis=1)
    pcy = np.concatenate([cy[:, :1], cy[:, :-1]], axis=1)
    hp = _heights(tiles, pcx + 0.5 - ix, pcy + 0.5 - iy) - base
    prev_y = np.concatenate([p[:, :1, 1], p[:, :-1, 1]], axis=1)
    hit = ok & (p[..., 1] <= h) & (prev_y > hp)
    first = np.argmax(hit, axis=1)
    any_hit = hit[np.arange(len(pts)), first]
    out = np.full((len(pts), 2), NONE, dtype=np.int64)
    rows = np.nonzero(any_hit)[0]
    out[rows, 0] = ix[rows, first[rows]] - ox
    out[rows, 1] = iy[rows, first[rows]] - oy
    return out


def safe_points(camera: Camera, gat: Gat, origin: tuple[int, int], rel: tuple[int, int],
                margin: float = 6.0, grid: float = 2.0, k: int = 5,
                spacing: float = 8.0) -> list[tuple[float, float]]:  # fmt: skip
    """Up to ``k`` client pixels that pick cell ``rel`` (an offset from ``origin``) with every pixel
    within ``margin`` px picking it too, the most interior first, at least ``spacing`` px apart
    (alternates for a unit covering the first). [] = the cell has no such pixel from here."""
    cells = np.array([rel], dtype=float)
    centre = camera.project(cells, gat.relative_altitude(origin, cells))[0]
    right = camera.project(cells + [1.0, 0.0], gat.relative_altitude(origin, cells + [1.0, 0.0]))[0]
    below = camera.project(cells + [0.0, 1.0], gat.relative_altitude(origin, cells + [0.0, 1.0]))[0]
    half = 1.5 * max(np.linalg.norm(right - centre), np.linalg.norm(below - centre), 2 * margin)
    n = int(2 * half / grid) + 1
    us = centre[0] - half + grid * np.arange(n)
    vs = centre[1] - half + grid * np.arange(n)
    uu, vv = np.meshgrid(us, vs)
    lab = pick_cells(camera, gat, origin, np.c_[uu.ravel(), vv.ravel()])
    mine = ((lab[:, 0] == rel[0]) & (lab[:, 1] == rel[1])).reshape(uu.shape)
    if not mine.any():
        return []
    # interior distance of each picked pixel: to the nearest grid pixel that picks something else
    # (the grid's own border counts as "else": nothing is known beyond it)
    other = ~mine
    other[0, :] = other[-1, :] = other[:, 0] = other[:, -1] = True
    oy_, ox_ = np.nonzero(other)
    my, mx = np.nonzero(mine)
    dist = np.sqrt(((my[:, None] - oy_[None, :]) ** 2 + (mx[:, None] - ox_[None, :]) ** 2).min(1))
    dist *= grid
    keep = dist >= margin + grid  # one grid step of slack: the boundary lies between samples
    order = np.argsort(-dist[keep], kind="stable")
    cand = np.c_[uu[my, mx][keep], vv[my, mx][keep]][order]
    out: list[tuple[float, float]] = []
    for u, v in cand:
        if all(np.hypot(u - a, v - b) >= spacing for a, b in out):
            out.append((float(u), float(v)))
        if len(out) >= k:
            break
    return out
