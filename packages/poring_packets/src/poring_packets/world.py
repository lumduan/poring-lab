"""World state from decoded packets: map, own character, entities, and walk interpolation.

Walk timing follows rAthena (unit.cpp:226-238, path.hpp:11-12): each step takes `speed` ms, or
speed*14/10 when diagonal; walks start at a server tick (gettick = CLOCK_MONOTONIC ms, mod 2^32).
Packets carry only the start and end cells, so without the map's walkability (GAT, Phase 2) the path
is rAthena's own fallback: diagonal first, then straight (path.cpp:292-325). Exact on open ground;
around obstacles the error is bounded by the detour.
"""

from dataclasses import dataclass, field

MOVE_COST = 10
MOVE_DIAGONAL_COST = 14
DEFAULT_SPEED = 150
TICK_MOD = 1 << 32


# rAthena's option bits (status.hpp OPTION_*) that make the client draw a unit as nothing.
HIDDEN_OPTIONS = 0x2 | 0x4 | 0x40  # HIDE, CLOAK, INVISIBLE

# RO headings: 0 = north, counter-clockwise in 45 degree steps (rAthena dirx/diry, map.hpp).
HEADING_OF_STEP = {(0, 1): 0, (-1, 1): 1, (-1, 0): 2, (-1, -1): 3,
                   (0, -1): 4, (1, -1): 5, (1, 0): 6, (1, 1): 7}  # fmt: skip


def heading_of(dx: float, dy: float) -> int | None:
    """The heading of a step (signs only); None for no step."""
    key = ((dx > 0) - (dx < 0), (dy > 0) - (dy < 0))
    return HEADING_OF_STEP.get(key)


def path_cells(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """Cells after the start, diagonal steps first, then straight."""
    cells: list[tuple[int, int]] = []
    x, y = x0, y0
    while (x, y) != (x1, y1):
        dx = (x1 > x) - (x1 < x)
        dy = (y1 > y) - (y1 < y)
        x, y = x + dx, y + dy
        cells.append((x, y))
    return cells


@dataclass
class Walk:
    x0: int
    y0: int
    x1: int
    y1: int
    start_tick: int  # server tick (ms, mod 2^32)
    speed: int = DEFAULT_SPEED

    def position_at(self, tick: int) -> tuple[float, float]:
        """Interpolated position at server tick `tick` (cell units, sub-cell while stepping)."""
        elapsed = (tick - self.start_tick) % TICK_MOD
        if elapsed > TICK_MOD // 2:  # before the walk started
            return float(self.x0), float(self.y0)
        x, y = float(self.x0), float(self.y0)
        for cx, cy in path_cells(self.x0, self.y0, self.x1, self.y1):
            diagonal = cx != x and cy != y
            step = self.speed * (MOVE_DIAGONAL_COST if diagonal else MOVE_COST) / MOVE_COST
            if elapsed < step:
                frac = elapsed / step
                return x + (cx - x) * frac, y + (cy - y) * frac
            elapsed -= int(step)
            x, y = float(cx), float(cy)
        return float(self.x1), float(self.y1)


@dataclass
class Entity:
    gid: int
    objtype: int
    job: int
    name: str
    x: int
    y: int
    speed: int = DEFAULT_SPEED
    walk: Walk | None = None
    dir: int | None = None  # heading 0..7 from the appear packet (0 = north, counter-clockwise)
    effect_state: int = 0  # option bits from the appear packet (HIDDEN_OPTIONS: not drawn)


@dataclass
class World:
    map: str | None = None
    aid: int | None = None
    self_x: int | None = None
    self_y: int | None = None
    self_walk: Walk | None = None
    self_speed: int = DEFAULT_SPEED
    stats: dict[str, int] = field(default_factory=dict)
    entities: dict[int, Entity] = field(default_factory=dict)

    def apply(self, etype: str, f: dict[str, object]) -> None:  # noqa: PLR0912
        """Update from one decoded event (type + fields)."""
        if etype in ("char_selected", "map_change"):
            self.map = str(f["map"])
            self.entities.clear()
            self.self_walk = None
            if etype == "map_change":
                self.self_x, self.self_y = int(str(f["x"])), int(str(f["y"]))
        elif etype == "map_enter":
            self.self_x, self.self_y = int(str(f["x"])), int(str(f["y"]))
            self.self_walk = None
        elif etype == "self_move":
            x0, y0, x1, y1 = (int(str(f[k])) for k in ("x0", "y0", "x1", "y1"))
            self.self_walk = Walk(x0, y0, x1, y1, int(str(f["server_tick"])), self.self_speed)
            self.self_x, self.self_y = int(str(f["x1"])), int(str(f["y1"]))
        elif etype == "stat_change":
            name = str(f["name"])
            self.stats[name] = int(str(f["value"]))
            if name == "speed":
                self.self_speed = int(str(f["value"]))
        elif etype == "entity_appear":
            gid = int(str(f["gid"]))
            objtype, job, x, y = (int(str(f[k])) for k in ("objtype", "job", "x", "y"))
            speed = int(str(f["speed"])) or DEFAULT_SPEED
            heading = f.get("heading")
            ent = Entity(gid, objtype, job, str(f["name"]), x, y, speed,
                         dir=None if heading is None else int(str(heading)),
                         effect_state=int(str(f.get("effect_state") or 0)))  # fmt: skip
            if f.get("x1") is not None:
                ent.walk = Walk(ent.x, ent.y, int(str(f["x1"])), int(str(f["y1"])),
                                int(str(f["move_start_tick"])), ent.speed)  # fmt: skip
            self.entities[gid] = ent
        elif etype == "entity_vanish":
            self.entities.pop(int(str(f["gid"])), None)
        elif etype == "entity_stop":
            gid = int(str(f["gid"]))
            if gid == self.aid:
                self.self_x, self.self_y, self.self_walk = int(str(f["x"])), int(str(f["y"])), None
            elif gid in self.entities:
                ent = self.entities[gid]
                ent.x, ent.y, ent.walk = int(str(f["x"])), int(str(f["y"])), None

    def self_position(self, tick: int | None) -> tuple[float, float] | None:
        if self.self_walk is not None and tick is not None:
            return self.self_walk.position_at(tick)
        if self.self_x is None or self.self_y is None:
            return None
        return float(self.self_x), float(self.self_y)
