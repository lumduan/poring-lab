"""World state from decoded packets: map, own character, entities, and walk interpolation.

Walk timing follows rAthena (unit.cpp:226-238, path.hpp:11-12): each step takes `speed` ms, or
speed*14/10 when diagonal; walks start at a server tick (gettick = CLOCK_MONOTONIC ms, mod 2^32).
Packets carry only the start and end cells, so without the map's walkability (GAT, Phase 2) the path
is rAthena's own fallback: diagonal first, then straight (path.cpp:292-325). Exact on open ground;
around obstacles the error is bounded by the detour.

What a unit SHOWS besides its position (Phase 3 M3) is kept in its `Motion`:
  * a timed action from ZC_NOTIFY_ACT: the source's attack swing for the attack motion the packet
    carries (`src_speed`, rAthena amotion), and the target's flinch for its damage motion
    (`dmotion`). The newer action is the one shown;
  * sitting, from the same packet's sit and stand types;
  * its turns: the appear heading, ZC_CHANGE_DIRECTION, and an attacker facing its target;
  * the walk an entity_stop cut short (the facing it ended with).
A unit that vanishes because it died moves to `dead` while its die animation plays.
poring_dataset.timeline turns all of it into a state at any time. Packets carry no tick for turns,
sitting, stops or deaths: those are timed by the event's receive time (`t_mono_ns`, same clock)
when the caller passes it.
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

# ZC_NOTIFY_ACT types (decode.ACT_KINDS) that a weapon attack produces: the source swings even on a
# miss or a lucky dodge. The skill-side types (splash, single, repeat, touch) start no swing here.
ATTACK_KINDS = frozenset({"normal", "endure", "multi_hit", "multi_hit_endure", "critical",
                          "lucky_dodge", "multi_hit_critical"})  # fmt: skip
# Types after which a DAMAGED target flinches. Not the endure types: a hit on an enduring unit is
# sent as one so that it keeps going (rAthena clif_calc_delay, clif.cpp:5142-5176; OpenKore calls
# them ..._NOMOTION). Not a lucky dodge, nor pickup / sit / stand.
FLINCH_KINDS = frozenset({"normal", "splash", "single", "repeat", "multi_hit", "critical", "touch",
                          "multi_hit_critical"})  # fmt: skip
VANISH_DIED = 1  # ZC_NOTIFY_VANISH reason (decode.VANISH_REASONS)
DEAD_KEEP_MS = 10_000  # how long `dead` keeps a unit after its death (longer than any die action)
DEAD_KEEP_MAX = 512


def heading_of(dx: float, dy: float) -> int | None:
    """The heading of a step (signs only); None for no step."""
    key = ((dx > 0) - (dx < 0), (dy > 0) - (dy < 0))
    return HEADING_OF_STEP.get(key)


def direction_toward(dx: int, dy: int) -> int | None:
    """The heading from a cell toward another (dx, dy) away, by the game's rule for "the direction
    of a cell" (rAthena map_calc_dir_xy, map.cpp:3208-3245): an axis while the offset is within a
    1:3 slope of it, else the diagonal. The east half (dx >= 0) keeps its exact 1:3 boundary on the
    axis, the west half on the diagonal. None for the same cell."""
    if not dx and not dy:
        return None
    ax, ay = abs(dx), abs(dy)
    if dx >= 0:
        along_x, along_y = ax >= 3 * ay, 3 * ax < ay
    else:
        along_x, along_y = ax > 3 * ay, 3 * ax <= ay
    if along_x:
        return 6 if dx > 0 else 2
    if along_y:
        return 0 if dy > 0 else 4
    return heading_of(dx, dy)


def ticks_since(tick: int, start: int) -> int:
    """`tick - start` in ms on the 2^32 server clock, signed: negative when `tick` is earlier."""
    d = (tick - start) % TICK_MOD
    return d - TICK_MOD if d >= TICK_MOD // 2 else d


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
class Action:
    """A timed action a unit shows: `attacking` (its swing) or `hurt` (a hit's flinch)."""

    kind: str
    start_tick: int  # server tick (ms, mod 2^32) of the ZC_NOTIFY_ACT
    duration_ms: int  # attack: the source's attack motion; hurt: the target's damage motion
    other: int  # attack: the target's gid; hurt: the attacker's
    act: str = "normal"  # the packet's type name (critical, multi_hit, ...)

    def active(self, tick: int) -> bool:
        return 0 <= ticks_since(tick, self.start_tick) < self.duration_ms


@dataclass(frozen=True)
class Turn:
    """An explicit facing and when it was set (tick None: unknown, older than anything timed)."""

    heading: int
    tick: int | None
    source: str  # "appear", "turn" (ZC_CHANGE_DIRECTION) or "target" (its attack's)


@dataclass
class Motion:
    action: Action | None = None
    sitting: bool = False
    turn: Turn | None = None
    cut: tuple[Walk, int] | None = None  # the walk an entity_stop cut short, and when it did

    def start(self, action: Action) -> None:
        """The newer action is the one shown (a flinch interrupts a swing, a swing a flinch)."""
        if self.action is None or ticks_since(action.start_tick, self.action.start_tick) >= 0:
            self.action = action


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
    dir: int | None = None  # heading 0..7 from the appear packet / ZC_CHANGE_DIRECTION
    effect_state: int = 0  # option bits from the appear packet (HIDDEN_OPTIONS: not drawn)
    motion: Motion = field(default_factory=Motion)
    died_tick: int | None = None  # set when it moves to World.dead


def _int(f: dict[str, object], key: str) -> int:
    return int(str(f[key]))


def _rx_tick(f: dict[str, object]) -> int | None:
    t = f.get("t_mono_ns")
    return None if t is None else (int(str(t)) // 1_000_000) % TICK_MOD


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
    self_motion: Motion = field(default_factory=Motion)
    dead: dict[int, Entity] = field(default_factory=dict)  # died recently (die animation)
    tick: int | None = None  # the latest tick seen: receive time, else a packet's server tick
    dead_keep_ms: int = DEAD_KEEP_MS

    def apply(self, etype: str, f: dict[str, object]) -> None:
        """Update from one decoded event (type + fields, plus `t_mono_ns` when the caller has it:
        it times the turns, stops and deaths the packets carry no tick for)."""
        rx = _rx_tick(f)
        if rx is not None:
            self.tick = rx
        elif f.get("server_tick"):
            self.tick = _int(f, "server_tick")
        if etype in ("char_selected", "map_change"):
            self.map = str(f["map"])
            self.entities.clear()
            self.dead.clear()
            self.self_walk = None
            self.self_motion = Motion()
            if etype == "map_change":
                self.self_x, self.self_y = _int(f, "x"), _int(f, "y")
        elif etype == "map_enter":
            self.self_x, self.self_y = _int(f, "x"), _int(f, "y")
            self.self_walk = None
            facing = f.get("facing")
            if facing is not None and int(str(facing)) < 8:
                self.self_motion.turn = Turn(int(str(facing)), rx, "appear")
        elif etype == "self_move":
            x0, y0, x1, y1 = (_int(f, k) for k in ("x0", "y0", "x1", "y1"))
            self.self_walk = Walk(x0, y0, x1, y1, _int(f, "server_tick"), self.self_speed)
            self.self_x, self.self_y = x1, y1
            self.self_motion.cut, self.self_motion.sitting = None, False
        elif etype == "stat_change":
            name = str(f["name"])
            self.stats[name] = _int(f, "value")
            if name == "speed":
                self.self_speed = _int(f, "value")
        elif etype == "entity_appear":
            self._appear(f, rx)
        elif etype == "entity_vanish":
            ent = self.entities.pop(_int(f, "gid"), None)
            died = rx if rx is not None else self.tick
            if ent is not None and _int(f, "reason") == VANISH_DIED and died is not None:
                ent.died_tick = died
                self.dead[ent.gid] = ent
        elif etype == "entity_stop":
            self._stop(f, rx)
        elif etype == "entity_turn":
            gid, heading = _int(f, "gid"), f.get("heading")
            motion = self.motion_of(gid)
            if heading is not None and motion is not None:
                motion.turn = Turn(int(str(heading)), rx, "turn")
                if gid in self.entities:
                    self.entities[gid].dir = int(str(heading))
        elif etype == "act":
            self._act(f, rx)
        if self.dead:
            self._prune()

    def _appear(self, f: dict[str, object], rx: int | None) -> None:
        gid = _int(f, "gid")
        objtype, job, x, y = (_int(f, k) for k in ("objtype", "job", "x", "y"))
        speed = _int(f, "speed") or DEFAULT_SPEED
        heading = f.get("heading")
        ent = Entity(gid, objtype, job, str(f["name"]), x, y, speed,
                     dir=None if heading is None else int(str(heading)),
                     effect_state=int(str(f.get("effect_state") or 0)))  # fmt: skip
        # Every walk of a unit in sight is a new move entry (rAthena clif_move): what it is
        # showing carries over to the new Entity.
        old = self.entities.get(gid)
        if old is not None:
            ent.motion = old.motion
        self.dead.pop(gid, None)  # a respawn keeps its block id
        if ent.dir is not None:
            ent.motion.turn = Turn(ent.dir, rx, "appear")
        if f.get("x1") is not None:
            ent.walk = Walk(ent.x, ent.y, _int(f, "x1"), _int(f, "y1"),
                            _int(f, "move_start_tick"), ent.speed)  # fmt: skip
            ent.motion.cut, ent.motion.sitting = None, False
        self.entities[gid] = ent

    def _stop(self, f: dict[str, object], rx: int | None) -> None:
        gid = _int(f, "gid")
        if gid == self.aid:
            if self.self_walk is not None and rx is not None:
                self.self_motion.cut = (self.self_walk, rx)
            self.self_x, self.self_y, self.self_walk = _int(f, "x"), _int(f, "y"), None
        elif gid in self.entities:
            ent = self.entities[gid]
            if ent.walk is not None and rx is not None:
                ent.motion.cut = (ent.walk, rx)
            ent.x, ent.y, ent.walk = _int(f, "x"), _int(f, "y"), None

    def _act(self, f: dict[str, object], rx: int | None) -> None:
        kind, src, dst = str(f["kind"]), _int(f, "src_gid"), _int(f, "target_gid")
        src_motion = self.motion_of(src)
        if kind in ("sit", "stand"):
            if src_motion is not None:
                src_motion.sitting = kind == "sit"
            return
        tick = _int(f, "server_tick") or rx
        if tick is None or src == dst:
            return
        src_speed = _int(f, "src_speed")
        if kind in ATTACK_KINDS and src_speed > 0 and src_motion is not None:
            src_motion.start(Action("attacking", tick, src_speed, dst, kind))
            src_motion.sitting = False
            # The server leaves the attacker's direction alone (battle.conf attack_direction_change
            # 0); the CLIENT is assumed to turn it toward its target -- M4 checks this on frames.
            a, b = self.position_of(src, tick), self.position_of(dst, tick)
            if a is not None and b is not None:
                facing = direction_toward(round(b[0]) - round(a[0]), round(b[1]) - round(a[1]))
                if facing is not None:
                    src_motion.turn = Turn(facing, tick, "target")
        dst_motion = self.motion_of(dst)
        hit = _int(f, "damage") != 0 or _int(f, "damage2") != 0  # -1: an amount hidden from us
        dmotion = _int(f, "dmotion")
        if kind in FLINCH_KINDS and hit and dmotion > 0 and dst_motion is not None:
            dst_motion.start(Action("hurt", tick, dmotion, src, kind))
            dst_motion.sitting = False

    def _prune(self) -> None:
        if self.tick is not None:
            for gid in [g for g, e in self.dead.items()
                        if e.died_tick is not None
                        and ticks_since(self.tick, e.died_tick) > self.dead_keep_ms]:  # fmt: skip
                del self.dead[gid]
        while len(self.dead) > DEAD_KEEP_MAX:
            del self.dead[next(iter(self.dead))]

    def motion_of(self, gid: int) -> Motion | None:
        """Our own character's or an entity's Motion; None for a unit not in sight."""
        if gid == self.aid:
            return self.self_motion
        ent = self.entities.get(gid)
        return None if ent is None else ent.motion

    def position_of(self, gid: int, tick: int) -> tuple[float, float] | None:
        """Where a unit is at `tick` (the diagonal-first walk; no map grid here)."""
        if gid == self.aid:
            return self.self_position(tick)
        ent = self.entities.get(gid)
        if ent is None:
            return None
        return ent.walk.position_at(tick) if ent.walk is not None else (float(ent.x), float(ent.y))

    def self_position(self, tick: int | None) -> tuple[float, float] | None:
        if self.self_walk is not None and tick is not None:
            return self.self_walk.position_at(tick)
        if self.self_x is None or self.self_y is None:
            return None
        return float(self.self_x), float(self.self_y)
