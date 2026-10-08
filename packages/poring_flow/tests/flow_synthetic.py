"""SYNTHETIC map sheets and server data for the tests (ADR-0020 13.8: committed fixtures hold
synthetic map data only). Every id, key, cell, count and level here is made up; the walk grids are
open fields with optional walls. Nothing is read from rAthena or the client.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from poring_flow import pyview
from poring_flow.ir import Flow
from poring_flow.sheet import (
    Item,
    Kafra,
    MapFlags,
    MapSheet,
    Mob,
    Npc,
    NpcWarp,
    Spawn,
    Walk,
    Warp,
    World,
)

FIXTURES = Path(__file__).parent / "fixtures"
ALLOW = MapFlags(noteleport=False, noreturn=False)


def grid(w: int, h: int, walls: tuple[tuple[int, int, int, int], ...] = ()) -> Walk:
    """An open w x h field; each wall is (x0, y0, x1, y1), inclusive."""
    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            blocked = any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in walls)
            row.append("#" if blocked else ".")
        rows.append("".join(row))
    return Walk(width=w, height=h, rows=rows)


def sheet(map_id: str, **kw: Any) -> MapSheet:
    kw.setdefault("flags", ALLOW)
    kw.setdefault("walk", grid(200, 200))
    return MapSheet(map=map_id, **kw)


ITEMS = {
    9001: Item(id=9001, label="Potion", kind="heal"),
    9002: Item(id=9002, label="Butterfly Wing", kind="butterfly_wing"),
    9003: Item(id=9003, label="Fly Wing", kind="fly_wing"),
}

FARM_MOBS = {
    9101: Mob(id=9101, level=5),
    9102: Mob(id=9102, level=6),
    9103: Mob(id=9103, level=10),
    9104: Mob(id=9104, level=8),
    9105: Mob(id=9105, level=12),
    9106: Mob(id=9106, level=12),
    9109: Mob(id=9109, level=40, aggressive=True, boss=True, difficulty="boss_multi_form"),
}


def farm_sheets(**over: MapSheet) -> dict[str, MapSheet]:
    """The three maps of Batt's example (13.6.8): town (map_1), relay (map_2), farm (map_3)."""
    sheets = {
        "map_1": sheet(
            "map_1",
            town=True,
            warps=[Warp(x=150, y=20, to_map="map_2", to_x=40, to_y=300)],
            npcs=[
                Npc(
                    key="n_k1",
                    x=146,
                    y=90,
                    kafra=Kafra(services=["save", "storage"], save_cell=(150, 180)),
                )
            ],
        ),
        "map_2": sheet(
            "map_2",
            walk=grid(100, 320),
            npcs=[
                Npc(
                    key="n_2b71",
                    x=40,
                    y=302,
                    menu=["o_5d0e"],
                    warps=[NpcWarp(options=["o_5d0e"], to_map="map_3", to_x=100, to_y=100)],
                )
            ],
        ),
        "map_3": sheet(
            "map_3",
            spawns=[
                Spawn(mob=9101, count=20),
                Spawn(mob=9102, count=20),
                Spawn(mob=9103, count=10),
                Spawn(mob=9104, count=5),
                Spawn(mob=9105, count=10),
                Spawn(mob=9106, count=10),
                Spawn(mob=9109, count=1, boss=True),
            ],
        ),
    }
    sheets.update(over)
    return sheets


def farm_world(**over: MapSheet) -> World:
    return World(server="lab-rathena", sheets=farm_sheets(**over), mobs=FARM_MOBS, items=ITEMS)


def farm_flow() -> Flow:
    return pyview.parse((FIXTURES / "farm_loop.flow").read_text())


# --- the Byalan fixture (13.3's worked example): iz_dun00 + iz_dun01, 7 species ------------------
# The map ids are the real maps' names; the species ids, levels and counts are SYNTHETIC. The labels
# name the species training-cost.md section 5 lists, for readability only.
BYALAN_MOBS = {
    9201: Mob(id=9201, label="Plankton", level=10),
    9202: Mob(id=9202, label="Marina", level=21),
    9203: Mob(id=9203, label="Kukre", level=11),
    9204: Mob(id=9204, label="Hydra", level=14, aggressive=True, immobile=True),
    9205: Mob(id=9205, label="Vadon", level=19),
    9206: Mob(id=9206, label="Cornutus", level=23),
    9207: Mob(id=9207, label="Black Mushroom", level=1, immobile=True, difficulty="static"),
}


def byalan_world() -> World:
    s0 = sheet(
        "iz_dun00", spawns=[Spawn(mob=m, count=10) for m in (9201, 9202, 9203, 9204, 9205, 9207)]
    )
    s1 = sheet(
        "iz_dun01",
        spawns=[Spawn(mob=m, count=10) for m in (9201, 9202, 9203, 9204, 9205, 9206, 9207)],
    )
    return World(
        server="lab-rathena", sheets={"iz_dun00": s0, "iz_dun01": s1}, mobs=BYALAN_MOBS, items=ITEMS
    )


def resolve_all(block: str, concept: str, params: dict[str, str]) -> None:
    """A synthetic environment where every binding resolves."""
