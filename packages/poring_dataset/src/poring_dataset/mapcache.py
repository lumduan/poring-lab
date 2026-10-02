"""rAthena's map cache (db/*map_cache.dat) at the pinned SHA: per-cell walkability.

Format (src/tool/mapcache.cpp, src/map/map.cpp at RATHENA_REF; verified against the shipped files):
  file header   u32 file_size, u16 map_count, u16 padding (8 bytes, little-endian)
  per map       char name[12] (NUL-padded), i16 xs, i16 ys, i32 len, then `len` bytes of zlib
                holding xs*ys gat cell types, index x + y*xs
Cell types (map_gat2cell): 1 = wall, 5 = cliff (shootable) are NOT walkable; 0/2/3(water)/4/6 are.
map_getcellp(CELL_CHKNOPASS) also treats the last row and column (x >= xs-1, y >= ys-1) and anything
outside as not passable.

Load order = the map-server's (map.cpp): db/import, then db/pre-re (or db/re), then db/map_cache.dat
-- the first file that contains a map wins. The lab runs prere=yes: prt_fild08 and prt_church exist
ONLY in db/pre-re/map_cache.dat; new_4-1 only in db/map_cache.dat.

The files are server data from the pinned rAthena tarball (scripts/gen_mapcache.py writes them to
_generated/, gitignored, sha256-checked against mapcache.lock.json); not client assets.
"""

import json
import struct
import zlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
GENERATED = HERE / "_generated"
LOCK = HERE / "mapcache.lock.json"
NOT_WALKABLE = frozenset({1, 5})


class MapCacheError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MapGrid:
    name: str
    xs: int
    ys: int
    cells: bytes  # gat type per cell, index x + y*xs

    def gat(self, x: int, y: int) -> int:
        return self.cells[x + y * self.xs]

    def nopass(self, x: int, y: int) -> bool:
        """rAthena map_getcellp(..., CELL_CHKNOPASS)."""
        if x < 0 or x >= self.xs - 1 or y < 0 or y >= self.ys - 1:
            return True
        return self.cells[x + y * self.xs] in NOT_WALKABLE


def parse(data: bytes) -> dict[str, MapGrid]:
    if len(data) < 8:
        raise MapCacheError("map cache shorter than its header")
    file_size, count = struct.unpack_from("<IH", data, 0)
    if file_size != len(data):
        raise MapCacheError(f"header says {file_size} bytes, file has {len(data)}")
    out: dict[str, MapGrid] = {}
    pos = 8
    for _ in range(count):
        raw_name, xs, ys, length = struct.unpack_from("<12shhi", data, pos)
        pos += 20
        name = raw_name.split(b"\0", 1)[0].decode("ascii")
        cells = zlib.decompress(data[pos : pos + length])
        pos += length
        if len(cells) != xs * ys:
            raise MapCacheError(f"{name}: {len(cells)} cells for {xs}x{ys}")
        out[name] = MapGrid(name, xs, ys, cells)
    return out


def merge(caches: Iterable[dict[str, MapGrid]]) -> dict[str, MapGrid]:
    """First cache containing a map wins (the map-server's order)."""
    merged: dict[str, MapGrid] = {}
    for cache in caches:
        for name, grid in cache.items():
            merged.setdefault(name, grid)
    return merged


def load(directory: Path = GENERATED, *, prere: bool = True) -> dict[str, MapGrid]:
    """The lab's maps, in the map-server's precedence. Checks every file against the lock."""
    lock = json.loads(LOCK.read_text())
    order = ["import", "pre-re" if prere else "re", "base"]
    caches = []
    for key in order:
        entry = lock["files"][key]
        path = directory / entry["name"]
        if not path.exists():
            raise MapCacheError(f"{path} missing: run scripts/gen_mapcache.py")
        data = path.read_bytes()
        import hashlib

        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise MapCacheError(f"{path}: sha256 differs from mapcache.lock.json")
        caches.append(parse(data))
    return merge(caches)
