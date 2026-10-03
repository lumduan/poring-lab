"""A map's GAT: per-cell terrain type and corner ALTITUDE (Phase 2 projection; the walkability +
altitude graph for Phase 4 planning).

Format (the facts, from RagnarokResearchLab/RagLite @ d1ce2b1, Core/FileFormats/RagnarokGAT.lua,
used under its Apache-2.0 option -- THIRD_PARTY.md; the layout is re-expressed here, no code
copied):
    header, 14 bytes: "GRAT" | major u8 | minor u8 (1.2 or 1.3) | width u32 | height u32
    width * height tiles of 20 bytes, index x + y * width (y grows north):
        altitude SW, SE, NW, NE (float32, RO's inverted axis: NEGATIVE is up) | type u16 | u16
The type is the one rAthena's map cache stores per cell (mapcache.py): 1 wall and 5 cliff are not
walkable. Altitudes are in world units, 5 per cell horizontally (camera.CELL).

The data is CLIENT data: a GAT is read from the client's GRF into /dev/shm at run time and NEVER
committed (CLAUDE.md rule 4; Batt 2026-10-03) -- nothing here ships one.
"""

import struct
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from poring_dataset.mapcache import NOT_WALKABLE

HEADER = struct.Struct("<4sBBII")
TILE = np.dtype([("sw", "<f4"), ("se", "<f4"), ("nw", "<f4"), ("ne", "<f4"),
                 ("type", "<u2"), ("water", "<u2")])  # fmt: skip


class GatError(ValueError):
    """Not a GAT, or a GAT of an unknown version / size."""


@dataclass(frozen=True)
class Gat:
    width: int
    height: int
    version: str
    tiles: npt.NDArray[np.void]  # (height, width) structured, TILE

    @property
    def types(self) -> npt.NDArray[np.uint16]:
        return np.asarray(self.tiles["type"], dtype=np.uint16)

    @property
    def altitude(self) -> npt.NDArray[np.float64]:
        """(height, width): the mean of the 4 corners, UP positive (world units)."""
        t = self.tiles
        mean = (t["sw"].astype(float) + t["se"] + t["nw"] + t["ne"]) / 4.0
        return np.asarray(-mean, dtype=float)

    def altitude_at(self, x: int, y: int) -> float:
        return float(self.altitude[y, x])

    def walkable(self) -> npt.NDArray[np.bool_]:
        return ~np.isin(self.types, list(NOT_WALKABLE))

    def relative_altitude(
        self, origin: tuple[int, int], offsets: npt.NDArray[np.float64]
    ) -> npt.NDArray[np.float64]:
        """Altitude of origin + offset cells, relative to the origin cell (world units, up +).
        Fractional offsets (a moving entity) are bilinear over cell centres."""
        alt = self.altitude
        pts = np.asarray(offsets, dtype=float) + np.asarray(origin, dtype=float)
        x = np.clip(pts[:, 0], 0, self.width - 1)
        y = np.clip(pts[:, 1], 0, self.height - 1)
        x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
        x1, y1 = np.minimum(x0 + 1, self.width - 1), np.minimum(y0 + 1, self.height - 1)
        fx, fy = x - x0, y - y0
        a = (alt[y0, x0] * (1 - fx) * (1 - fy) + alt[y0, x1] * fx * (1 - fy)
             + alt[y1, x0] * (1 - fx) * fy + alt[y1, x1] * fx * fy)  # fmt: skip
        return np.asarray(a - alt[origin[1], origin[0]], dtype=float)


def parse(data: bytes) -> Gat:
    if len(data) < HEADER.size:
        raise GatError("shorter than a GAT header")
    magic, major, minor, width, height = HEADER.unpack_from(data)
    if magic != b"GRAT":
        raise GatError(f"magic {magic!r}, not GRAT")
    if (major, minor) not in ((1, 2), (1, 3)):
        raise GatError(f"GAT version {major}.{minor} (only 1.2 and 1.3)")
    want = HEADER.size + width * height * TILE.itemsize
    if len(data) != want:
        raise GatError(f"{len(data)} bytes for {width}x{height} (want {want})")
    tiles = np.frombuffer(data, TILE, count=width * height, offset=HEADER.size)
    return Gat(width, height, f"{major}.{minor}", tiles.reshape(height, width))


def walk_graph(gat: Gat) -> dict[str, npt.NDArray[np.int64] | npt.NDArray[np.float64]]:
    """The 8-neighbour walk graph of walkable cells, rAthena's diagonal rule (a diagonal step
    needs both orthogonal neighbours walkable), with each edge's climb in world units:
    {"src": (E,), "dst": (E,), "cost": (E,) 10 orthogonal / 14 diagonal, "climb": (E,)}."""
    ok = gat.walkable()
    alt = gat.altitude
    h, w = ok.shape
    src, dst, cost, climb = [], [], [], []
    ys, xs = np.nonzero(ok)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
        nx, ny = xs + dx, ys + dy
        inside = (nx >= 0) & (nx < w) & (ny >= 0) & (ny < h)
        sx, sy, tx, ty = xs[inside], ys[inside], nx[inside], ny[inside]
        good = ok[ty, tx]
        if dx and dy:
            good &= ok[sy, tx] & ok[ty, sx]
        sx, sy, tx, ty = sx[good], sy[good], tx[good], ty[good]
        src.append(sx + sy * w)
        dst.append(tx + ty * w)
        cost.append(np.full(len(sx), 14 if dx and dy else 10))
        climb.append(alt[ty, tx] - alt[sy, sx])
    return {
        "src": np.concatenate(src).astype(np.int64),
        "dst": np.concatenate(dst).astype(np.int64),
        "cost": np.concatenate(cost).astype(np.int64),
        "climb": np.concatenate(climb).astype(float),
    }
