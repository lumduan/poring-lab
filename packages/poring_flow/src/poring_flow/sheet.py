"""The map sheet: per-map L3 data as an INPUT interface (ADR-0020 13.2).

Everything a map block offers in the editor and everything the linter checks comes from the active
server's static data. This module fixes the SHAPE only; the generator from L3 (the extended
extraction Batt approved on 2026-10-08: NPC warp targets per option, the Kafra save cell, the map
flags) is later work. Committed tests use SYNTHETIC sheets only.

- Real sheets are generated LOCALLY from the pinned rAthena, never committed (CLAUDE.md rule 4):
  `data/kb/maps/<server>/<map>.json` (one `MapSheet`) and `data/kb/maps/<server>/_server.json`
  (mobs and items), the names MW1 fixes. `load_world` reads only the maps a flow names.
- A missing entry fails closed (13.2): the linter reports it unsupported, never guesses.
- `Walk` is the walkability grid ('.' walkable, '#' not). `route()` is our own clean A* with RO's
  8-way moves (a diagonal needs both orthogonal neighbours walkable), costs 10 / 14.
"""

from __future__ import annotations

import heapq
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_CFG = ConfigDict(extra="forbid", frozen=True)
MAPS_DIR = Path("data/kb/maps")
Cell = tuple[int, int]


class Mob(BaseModel):
    model_config = _CFG
    id: int
    label: str | None = None  # display only (synthetic in tests)
    level: int = Field(ge=1, le=999)
    aggressive: bool = False  # mob_db ai / mode flags
    chases: bool = False
    immobile: bool = False
    boss: bool = False
    turns_into: list[int] = []  # metamorphosis (classes.json)
    look_alike: list[int] = []  # species the detector may confuse with this one
    # training-cost.md section 4's class; an owner / agent judgement, not derived
    difficulty: Literal["similar", "static", "normal", "boss_multi_form"] = "normal"


class Item(BaseModel):
    model_config = _CFG
    id: int
    label: str | None = None
    kind: Literal["heal", "fly_wing", "butterfly_wing", "other"] = "other"


class Spawn(BaseModel):
    model_config = _CFG
    mob: int
    count: int = Field(ge=1)
    boss: bool = False  # a boss spawn line
    # the spawn line's area, (x0, y0, x1, y1) inclusive; None = anywhere on the map (rAthena's
    # 0,0). The zones lint warns when every cell of a target's spawn areas is closed (2026-10-21)
    area: tuple[int, int, int, int] | None = None

    def cells(self, walk: Walk | None) -> set[Cell] | None:
        """The walkable cells of its area (every cell when there is no walk grid); None for a
        spawn anywhere on the map."""
        if self.area is None:
            return None
        x0, y0, x1, y1 = self.area
        out = {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}
        return {c for c in out if walk.walkable(c)} if walk is not None else out


class Warp(BaseModel):
    model_config = _CFG
    x: int
    y: int
    span_x: int = Field(default=0, ge=0)
    span_y: int = Field(default=0, ge=0)
    to_map: str
    to_x: int
    to_y: int

    def cells(self) -> set[Cell]:
        return {
            (x, y)
            for x in range(self.x - self.span_x, self.x + self.span_x + 1)
            for y in range(self.y - self.span_y, self.y + self.span_y + 1)
        }


class NpcWarp(BaseModel):  # the warp a script makes after a menu path (Batt approved, Q27)
    model_config = _CFG
    options: list[str] = Field(min_length=1)
    to_map: str
    to_x: int
    to_y: int


class Kafra(BaseModel):
    model_config = _CFG
    services: list[Literal["save", "storage", "teleport", "cart"]]
    save_cell: Cell | None = None  # the respawn / Butterfly Wing arrival (Batt approved, Q27)


class Npc(BaseModel):
    model_config = _CFG
    key: str
    x: int
    y: int
    menu: list[str] = []  # option KEYS this NPC offers
    warps: list[NpcWarp] = []
    kafra: Kafra | None = None


class MapFlags(BaseModel):
    model_config = _CFG
    noteleport: bool = False  # no Fly Wing
    noreturn: bool = False  # no Butterfly Wing


class Walk(BaseModel):
    model_config = _CFG
    width: int = Field(ge=1, le=2048)
    height: int = Field(ge=1, le=2048)
    rows: list[str]  # rows[y][x]; '.' walkable, '#' not

    @model_validator(mode="after")
    def _shape(self) -> Walk:
        if len(self.rows) != self.height or any(len(r) != self.width for r in self.rows):
            raise ValueError("rows must be height strings of width characters")
        if any(set(r) - {".", "#"} for r in self.rows):
            raise ValueError("rows hold only '.' and '#'")
        return self

    def walkable(self, c: Cell) -> bool:
        x, y = c
        return 0 <= x < self.width and 0 <= y < self.height and self.rows[y][x] == "."

    def route(self, a: Cell, b: Cell) -> list[Cell] | None:
        """A shortest 8-way path from a to b (both included), or None."""
        if not (self.walkable(a) and self.walkable(b)):
            return None
        best: dict[Cell, int] = {a: 0}
        came: dict[Cell, Cell] = {}
        heap = [(0, 0, a)]
        while heap:
            _, g, c = heapq.heappop(heap)
            if c == b:
                out = [c]
                while c in came:
                    c = came[c]
                    out.append(c)
                return out[::-1]
            if g > best.get(c, 1 << 60):
                continue
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == dy == 0:
                        continue
                    n = (c[0] + dx, c[1] + dy)
                    if not self.walkable(n):
                        continue
                    if (
                        dx
                        and dy
                        and not (
                            self.walkable((c[0] + dx, c[1])) and self.walkable((c[0], c[1] + dy))
                        )
                    ):
                        continue
                    ng = g + (14 if dx and dy else 10)
                    if ng < best.get(n, 1 << 60):
                        best[n] = ng
                        came[n] = c
                        h = 10 * max(abs(b[0] - n[0]), abs(b[1] - n[1]))
                        heapq.heappush(heap, (ng + h, ng, n))
        return None


class MapSheet(BaseModel):
    model_config = _CFG
    map: str
    town: bool = False
    spawns: list[Spawn] = []
    npcs: list[Npc] = []
    warps: list[Warp] = []
    flags: MapFlags | None = None  # None: not extracted yet (fails closed where it matters)
    walk: Walk | None = None  # None: no walkability (route checks report it unsupported)

    def npc(self, key: str) -> Npc | None:
        return next((n for n in self.npcs if n.key == key), None)

    def warp_at(self, c: Cell) -> Warp | None:
        return next((w for w in self.warps if c in w.cells()), None)

    def spawned(self) -> list[int]:
        return sorted({s.mob for s in self.spawns})

    def boss_lines(self) -> list[int]:
        return sorted({s.mob for s in self.spawns if s.boss})


class World(BaseModel):
    """The server's static data the linter reads: map sheets, mobs and items."""

    model_config = _CFG
    server: str
    sheets: dict[str, MapSheet] = {}
    mobs: dict[int, Mob] = {}
    items: dict[int, Item] = {}

    def sheet(self, map_id: str) -> MapSheet | None:
        return self.sheets.get(map_id)

    def items_of(self, kind: str) -> list[int]:
        return sorted(i.id for i in self.items.values() if i.kind == kind)


class ServerData(BaseModel):  # _server.json
    model_config = _CFG
    server: str
    mobs: list[Mob] = []
    items: list[Item] = []


def load_world(server: str, maps: list[str], root: Path = MAPS_DIR) -> World:
    """The sheets of the maps a flow names, generated locally (a missing one is left out)."""
    folder = root / server
    base = folder / "_server.json"
    data = ServerData.model_validate(json.loads(base.read_text())) if base.exists() else None
    sheets = {}
    for m in sorted(set(maps)):
        p = folder / f"{m}.json"
        if p.exists():
            sheets[m] = MapSheet.model_validate(json.loads(p.read_text()))
    return World(
        server=server,
        sheets=sheets,
        mobs={m.id: m for m in data.mobs} if data else {},
        items={i.id: i for i in data.items} if data else {},
    )
