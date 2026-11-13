"""SIMULATE for the editor (MW2, mw2-block-editor.md section 4): run a flow against STATIC server
data and return a TRACE: the cells walked per map, the exits taken, per-node outcomes and
durations, the events that fired. No game, no input path, no I/O.

It is MW1's simulated executor (`runtime.Sim`) driven by the map sheets (`poring_flow.sheet`):
- the scheduling, the events, pre-emption, `then`, relocation and the arrival checks are
  `runtime.Sim`'s, unchanged;
- a planner derived from the sheets replaces the fixed 3-tick plan: a walk takes its route on the
  walk grid (150 ms a cell, 212 ms a diagonal), an NPC must be on the map and an option in its
  menu, a Kafra sets the save point, a Butterfly Wing goes to the save point;
- the world the conditions read is a SCENARIO: starting vitals, a simulated loot model (weight per
  attack) and a timeline of changes (e.g. a death at t = 200 s). Those are the user's assumptions,
  never measurements; the trace echoes them.

The input batches `runtime.Sim` would emit are counted, never built or kept: nothing here can
reach the mux. Node paths are MW1's structural paths (`ir.sites`).

THE PLAY LIST (2026-11-10, Batt's Maps page: "watch the bot walk a -> b -> c, meet monsters and
talk to NPCs at the flow's positions", docs/planning/world-map-flows.md): `play` is the run in
ORDER, one step per thing the character does, with its start and end time (`t0`, `t1`), the map
block and map it happens on, and its cells: walk (the route), talk (the NPC and its cell), menu
(an option key), fight (the monster, its cell, whether it dropped loot), item (an item warp by
function names its `proc`), loot, respawn, act (any other block; a press_key's names its `key`),
wait, exit (from block / map -> to block / map / cell) and arrive (the map changed outside an
exit: a wing, a respawn). The browser animates it; it adds nothing the run did not do.
- ENCOUNTERS (`Scenario.encounters`, off by default so every older caller's trace is unchanged
  but for the added `play`): an attack places ONE monster deterministically from `Scenario.seed`
  (the block's target species the sheet spawns, weighted by spawn count; the explicit `mob` when
  the block names one), on a walkable cell 2..R cells from the character (R = the block's
  `within`, at most 12) that the walk grid reaches; the character walks up to the cell next to
  it, then the kill takes `attack_s`. Without encounters a fight stands still and names no
  monster (the model only spends its time), as before.
- Bounded: at most MAX_PLAY steps and MAX_PLAY_CELLS cells (a walk past the budget keeps its two
  ends, `trimmed`).
"""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from poring_env.protocol import Key, MouseButton, MouseMove, ReleaseAll
from poring_flow import functions as fn
from poring_flow import ir
from poring_flow.catalogue import Catalogue, catalogue
from poring_flow.models import detector_keys
from poring_flow.runtime import TICK_S, Plan, Sim, _Halt, _Tick, default_plan
from poring_flow.sheet import Cell, MapSheet, World

WALK_MS = 150  # RO's default walk speed: one cell
DIAG_MS = 212  # a diagonal step (x sqrt 2)
MAX_HORIZON_S = 3600
MAX_CELLS = 20_000  # every path segment together
MAX_EVENTS = 400
MAX_PLAY = 2000  # the play list's steps
MAX_PLAY_CELLS = 20_000  # every play step's cells together
MAX_SEED = 2**31 - 1
ENGAGE_DEFAULT = 9  # cells: where an encounter's monster stands when the block names no `within`
ENGAGE_MAX = 12
ENGAGE_TRIES = 60
# the blocks that walk up to an NPC and talk (the planner's NPC set)
NPC_BLOCKS = ("talk_npc", "set_save_point", "kafra_store", "kafra_withdraw", "buy", "sell",
              "rent_cart", "refine")  # fmt: skip
FIGHT_BLOCKS = ("attack_nearest", "finish_target", "hunt", "dungeon_hunt")
# the task-level hunts (the hunt block; the runner's dungeon_hunt, Amendment C): one monster per
# call with encounters on, else their default 1 s
HUNT_BLOCKS = ("hunt", "dungeon_hunt")
DetectKey = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,31}/[a-z][a-z0-9_]{0,47}$")]
ScenarioKey = Literal[
    "hp_percent", "sp_percent", "weight_percent", "is_dead", "engagement_seen", "engaged_species"
]


class Change(BaseModel):
    """One timeline entry: at `t` seconds, the scenario sets these sensor values."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    t: float = Field(ge=0, le=MAX_HORIZON_S)
    set: dict[ScenarioKey, float | bool | int] = Field(default_factory=dict, max_length=6)
    sees: dict[int, bool] = Field(default_factory=dict, max_length=10)  # mob id -> seen
    # a trained model's boxes (models.yaml, ADR-0020 Amendment B): "<model>/<class>" -> how many
    # boxes of that class it finds from t on (0 = it sees none); before any entry: 0
    detects: dict[DetectKey, Annotated[int, Field(ge=0, le=999)]] = Field(
        default_factory=dict, max_length=10
    )


class Scenario(BaseModel):
    """The simulated world: the user's assumptions, echoed in every trace."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    start_block: str | None = Field(default=None, pattern=ir.NAME)  # run a single map node
    start_entry: str | None = Field(default=None, pattern=ir.NAME)
    single_block: bool = False  # stop when the start block takes an exit
    horizon_s: float = Field(default=600, gt=0, le=MAX_HORIZON_S)
    hp_percent: float = Field(default=100, ge=0, le=100)
    sp_percent: float = Field(default=100, ge=0, le=100)
    weight_percent: float = Field(default=10, ge=0, le=100)
    weight_per_attack: float = Field(default=2, ge=0, le=50)  # the simulated loot model
    hp_per_attack: float = Field(default=0, ge=0, le=50)
    attack_s: float = Field(default=3, gt=0, le=60)  # one kill
    timeline: list[Change] = Field(default_factory=list, max_length=50)
    # the Maps page (2026-11-10): place a monster for every attack and walk up to it (the module
    # docstring); off = a fight stands still, as before. `seed` makes the placement repeatable.
    encounters: bool = False
    seed: int = Field(default=0, ge=0, le=MAX_SEED)

    @model_validator(mode="after")
    def _entry_needs_block(self) -> Scenario:
        if self.start_entry is not None and self.start_block is None:
            raise ValueError("start_entry needs start_block")
        return self


@dataclass
class NodeStats:
    runs: int = 0
    total_s: float = 0.0
    first_t: float | None = None
    last_t: float = 0.0
    last: str = ""
    outcomes: Counter[str] = field(default_factory=Counter)

    def doc(self) -> dict[str, Any]:
        return {
            "runs": self.runs,
            "total_s": round(self.total_s, 1),
            "first_t": None if self.first_t is None else round(self.first_t, 1),
            "last_t": round(self.last_t, 1),
            "last": self.last,
            "outcomes": dict(sorted(self.outcomes.items())),
        }


def _steps_ms(route: list[Cell]) -> int:
    ms = 0
    for (x0, y0), (x1, y1) in zip(route, route[1:], strict=False):
        ms += DIAG_MS if x0 != x1 and y0 != y1 else WALK_MS
    return ms


def _ticks(ms: float) -> int:
    return max(1, math.ceil(ms / (TICK_S * 1000)))


# One constant batch per kind: the executor's batches are counted, never kept (nothing is sent).
_CLICK = [
    MouseMove(t_mono_ns=0, x=0.5, y=0.5),
    MouseButton(t_mono_ns=0, button="left", action="down"),
    MouseButton(t_mono_ns=0, button="left", action="up"),
]
_KEY = [Key(t_mono_ns=0, code="F1", action="down"), Key(t_mono_ns=0, code="F1", action="up")]


class TraceSim(Sim):
    """`runtime.Sim` with a sheet-driven planner and a per-node trace."""

    def __init__(
        self,
        flow: ir.Flow,
        world: World | None,
        scenario: Scenario | None = None,
        cat: Catalogue | None = None,
    ) -> None:
        self.scenario = scenario or Scenario()
        self.static = world
        self.notes: list[str] = []
        sc = self.scenario
        if flow.workflow is not None:
            wf = flow.workflow
            names = {b.name: b for b in wf.blocks}
            block_name = sc.start_block or wf.start_block
            if block_name not in names:
                raise ValueError(f"no map block {block_name}")
            block = names[block_name]
            entry_name = sc.start_entry or (
                wf.start_entry if block_name == wf.start_block else block.entries[0].name
            )
            entry = next((e for e in block.entries if e.name == entry_name), None)
            if entry is None:
                raise ValueError(f"{block_name} has no entry {entry_name}")
            start_map: str | None = block.map.map
            start_cell = (entry.at.x, entry.at.y) if entry.at is not None else None
            if start_cell is None:
                self.notes.append(f"entry {entry_name} is 'anywhere': the start cell is unknown")
        else:
            if sc.start_block is not None:
                raise ValueError("a plain flow has no map blocks")
            block_name, entry_name, start_map, start_cell = "", None, None, None
        values: dict[str, Any] = {
            "hp_percent": sc.hp_percent,
            "sp_percent": sc.sp_percent,
            "weight_percent": sc.weight_percent,
            "is_dead": False,
            "engagement_seen": False,
            "map": start_map,
            "cell": start_cell,
        }
        for item in world.items.values() if world else []:
            if item.kind == "butterfly_wing":
                values[f"wing:{item.id}"] = "butterfly"
        # every model / class pair the flow reads starts at 0 boxes (the scenario sets others)
        values.update({f"detect:{k}": 0 for k in detector_keys(flow)})
        timeline: list[tuple[float, dict[str, Any]]] = []
        for ch in sc.timeline:
            changes: dict[str, Any] = {}
            for k, v in ch.set.items():
                changes[k] = ir.MobRef(id=int(v)) if k == "engaged_species" else v
            changes.update({f"sees:{m}": seen for m, seen in ch.sees.items()})
            changes.update({f"detect:{k}": n for k, n in ch.detects.items()})
            timeline.append((ch.t, changes))
        super().__init__(
            flow,
            world=values,
            timeline=timeline,
            planner=self._plan,
            cat=cat or catalogue(),
            max_ticks=_ticks(sc.horizon_s * 1000),
        )
        self.block = block_name
        self.start = {
            "block": block_name or None,
            "entry": entry_name,
            "map": start_map,
            "cell": list(start_cell) if start_cell else None,
        }
        self.paths: dict[int, str] = {}
        self.do_paths: dict[int, str] = {}
        for site in ir.sites(flow):
            self.paths[id(site.stmt)] = site.path
            for a in ir.actions_in(site.stmt):
                if a is not site.stmt:
                    self.do_paths[id(a)] = site.path
        self.stats: dict[str, NodeStats] = {}
        self.block_time: dict[str, float] = {}
        self.block_visits: Counter[str] = Counter({block_name: 1} if block_name else {})
        self.transitions: list[dict[str, Any]] = []
        self.segments: dict[tuple[str, tuple[Cell, ...]], dict[str, Any]] = {}
        self.cells_kept = 0
        self.batches = 0
        self.dialog_npc: str | None = None  # the NPC whose dialog the last talk opened
        self._planned: dict[int, tuple[list[Cell], bool]] = {}
        self._planned_ms: dict[int, float] = {}  # the walk part of a planned action, in ms
        self._fights: dict[int, dict[str, Any]] = {}  # an encounter's monster, by action
        self._exit_planned: tuple[list[Cell], bool] | None = None
        self._exit_ms = 0.0
        self.play: list[dict[str, Any]] = []  # the run in order (the module docstring)
        self.play_cells = 0
        self.play_capped = False
        self.encounter_n = 0
        # the run is over: generators the run left open are closed later (garbage collection), and
        # that GeneratorExit is no pre-emption: it must not add a step after the result
        self._done = False
        self._exit_ctx: ir.Exit | None = None
        self._exit_stmt: ir.TakeExit | None = None  # the take_exit running (its node path)
        self._pending_respawn: str | None = None
        self._last_outcome: dict[int, str] = {}

    # --- the static data ------------------------------------------------------------------------
    def _sheet(self) -> MapSheet | None:
        m = self.world.get("map")
        return self.static.sheet(m) if self.static and isinstance(m, str) else None

    def _route(self, to: Cell) -> tuple[list[Cell] | None, bool]:
        """(cells, estimated): a route on the walk grid, or a straight estimate without one."""
        here = self.world.get("cell")
        sheet = self._sheet()
        if here is None:
            return [to], True
        here = (int(here[0]), int(here[1]))
        if sheet is not None and sheet.walk is not None:
            return sheet.walk.route(here, to), False
        return [here, to], True

    def _near(self, npc_cell: Cell) -> Cell:
        """The walkable cell next to an NPC that is closest to the character."""
        sheet = self._sheet()
        here = self.world.get("cell")
        if sheet is None or sheet.walk is None:
            return npc_cell
        best: tuple[int, Cell] | None = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                c = (npc_cell[0] + dx, npc_cell[1] + dy)
                if (dx or dy) and sheet.walk.walkable(c):
                    d = max(abs(c[0] - here[0]), abs(c[1] - here[1])) if here else 0
                    if best is None or d < best[0]:
                        best = (d, c)
        return best[1] if best else npc_cell

    def _walk_plan(self, a: ir.ActionStmt, to: Cell, extra_ms: float, exit_: bool = False) -> Plan:
        route, estimated = self._route(to)
        if route is None:
            self.notes.append(
                f"{self._where(a)}: ({to[0]}, {to[1]}) is unreachable on the walk grid"
            )
            return Plan(ticks=1, outcome="failed")
        ms = _steps_ms(route) if not estimated else WALK_MS * self._chebyshev(to)
        if exit_:
            self._exit_planned = (route, estimated)
            self._exit_ms = ms
        else:
            self._planned[id(a)] = (route, estimated)
            self._planned_ms[id(a)] = ms
        return Plan(ticks=_ticks(ms + extra_ms), effects={"cell": to})

    # --- encounters (the Maps page; the module docstring) -----------------------------------------
    def _block_now(self) -> ir.MapBlock | None:
        return self.tree.blocks.get(self.block) if self.block else None

    def _encounter_mob(
        self, a: ir.ActionStmt, sheet: MapSheet | None, rng: random.Random
    ) -> int | None:
        """The species this attack meets: the block's `mob` when it names one, else a TARGET
        species the sheet spawns (any spawn but the ignored ones in a block without targets),
        weighted by its spawn count; a target the sheet does not list still counts once."""
        named = self._eval(a.params.get("mob")) if "mob" in a.params else None
        if isinstance(named, ir.MobRef):
            return named.id
        b = self._block_now()
        targets = {m.id for m in b.targets} if b else set()
        ignore = {m.id for m in b.ignore} if b else set()
        pool: Counter[int] = Counter()
        for sp in sheet.spawns if sheet else []:
            if (not targets or sp.mob in targets) and sp.mob not in ignore:
                pool[sp.mob] += sp.count
        for m in sorted(targets - set(pool)):
            pool[m] += 1
        if not pool:
            return None
        ids = sorted(pool)
        return rng.choices(ids, weights=[pool[i] for i in ids])[0]

    def _encounter_cell(
        self, sheet: MapSheet | None, here: Cell, radius: int, rng: random.Random, mob: int | None
    ) -> tuple[Cell, list[Cell], bool] | None:
        """(the monster's cell, the walk up to the cell next to it, estimated): a walkable cell
        2..radius cells away that the walk grid reaches in a short route (inside the species'
        spawn area when the sheet gives one and it is near); None when no such cell is found."""
        walk = sheet.walk if sheet else None
        area: set[Cell] | None = None
        for sp in sheet.spawns if sheet else []:
            if sp.mob == mob and sp.area is not None:
                area = (area or set()) | (sp.cells(walk) or set())
        for attempt in range(ENGAGE_TRIES):
            dx, dy = rng.randint(-radius, radius), rng.randint(-radius, radius)
            if max(abs(dx), abs(dy)) < 2:
                continue
            c = (here[0] + dx, here[1] + dy)
            # the spawn area first; past half the tries, any near cell (the area is far away)
            if area is not None and attempt < ENGAGE_TRIES // 2 and c not in area:
                continue
            if walk is None:
                if c[0] < 0 or c[1] < 0:
                    continue
                return c, [here, self._next_to(here, c)], True
            if not walk.walkable(c):
                continue
            route = walk.route(here, c)
            if route is None or len(route) > 2 * radius + 2:
                continue
            return c, route[:-1] or [here], False
        return None

    @staticmethod
    def _next_to(here: Cell, c: Cell) -> Cell:
        """The cell next to `c` on the straight line from `here` (no walk grid: an estimate)."""
        sx = (here[0] > c[0]) - (here[0] < c[0])
        sy = (here[1] > c[1]) - (here[1] < c[1])
        return (c[0] + sx, c[1] + sy)

    def _fight_plan(self, a: ir.ActionStmt, effects: dict[str, Any]) -> Plan:
        sc = self.scenario
        here = self.world.get("cell")
        if not sc.encounters or here is None:
            return Plan(ticks=_ticks(sc.attack_s * 1000), effects=effects)
        here = (int(here[0]), int(here[1]))
        sheet = self._sheet()
        self.encounter_n += 1
        rng = random.Random(f"{sc.seed}:{self.encounter_n}:{self.world.get('map')}")
        mob = self._encounter_mob(a, sheet, rng)
        within = self._eval(a.params.get("within")) if "within" in a.params else None
        radius = within if isinstance(within, int) and not isinstance(within, bool) else None
        radius = max(2, min(ENGAGE_MAX, radius if radius is not None else ENGAGE_DEFAULT))
        placed = self._encounter_cell(sheet, here, radius, rng, mob)
        if placed is None:
            self.notes.append(f"{self._where(a)}: no cell for a monster near ({here[0]}, "
                              f"{here[1]}): the fight stands still")  # fmt: skip
            self._fights[id(a)] = {"mob": mob, "at": None}
            return Plan(ticks=_ticks(sc.attack_s * 1000), effects=effects)
        cell, walk, estimated = placed
        (x0, y0), (x1, y1) = walk[0], walk[-1]
        ms = WALK_MS * max(abs(x1 - x0), abs(y1 - y0)) if estimated else _steps_ms(walk)
        if len(walk) > 1:
            self._planned[id(a)] = (walk, estimated)
        self._planned_ms[id(a)] = ms
        self._fights[id(a)] = {"mob": mob, "at": [cell[0], cell[1]]}
        return Plan(ticks=_ticks(ms + sc.attack_s * 1000), effects={**effects, "cell": walk[-1]})

    def _chebyshev(self, to: Cell) -> int:
        here = self.world.get("cell")
        return 0 if here is None else max(abs(to[0] - here[0]), abs(to[1] - here[1]))

    def _where(self, a: ir.ActionStmt) -> str:
        return self.paths.get(id(a)) or self.do_paths.get(id(a)) or a.block

    def _plan(self, a: ir.ActionStmt, sim: Sim) -> Plan:
        sc = self.scenario
        sheet = self._sheet()
        if self._exit_ctx is not None and id(a) not in self.paths and id(a) not in self.do_paths:
            return self._exit_plan(a, self._exit_ctx, sheet)  # runtime.Sim's own exit action
        if a.block == "walk_to":
            cell = self._eval(a.params.get("cell")) if "cell" in a.params else None
            if not isinstance(cell, ir.CellRef):
                return Plan(ticks=1, outcome="failed")
            if self.world.get("map") is None:  # a plain flow: its first cell names the map
                self.world["map"] = cell.map
            if cell.map != self.world.get("map"):
                self.notes.append(f"{self._where(a)}: walk_to a cell on {cell.map}, not this map")
                return Plan(ticks=1, outcome="failed")
            return self._walk_plan(a, (cell.x, cell.y), 0)
        if a.block in ("talk_npc", "set_save_point", "kafra_store", "kafra_withdraw", "buy",
                       "sell", "rent_cart", "refine"):  # fmt: skip
            ref = self._eval(a.params.get("npc")) if "npc" in a.params else None
            npc = sheet.npc(ref.key) if sheet and isinstance(ref, ir.NpcRef) else None
            if npc is None:
                key = ref.key if isinstance(ref, ir.NpcRef) else "?"
                self.notes.append(f"{self._where(a)}: npc {key} is not on {self.world.get('map')}")
                return Plan(ticks=1, outcome="failed")
            if a.block == "set_save_point" and (
                npc.kafra is None or "save" not in npc.kafra.services
            ):
                self.notes.append(f"{self._where(a)}: npc {npc.key} offers no save service")
                return Plan(ticks=1, outcome="failed")
            self.dialog_npc = npc.key if a.block == "talk_npc" else None
            return self._walk_plan(a, self._near((npc.x, npc.y)), 1500)
        if a.block == "choose_menu":
            ref = self._eval(a.params.get("option")) if "option" in a.params else None
            npc = sheet.npc(self.dialog_npc) if sheet and self.dialog_npc else None
            if npc is None or not isinstance(ref, ir.OptionRef) or ref.key not in npc.menu:
                self.notes.append(
                    f"{self._where(a)}: option {getattr(ref, 'key', '?')} is not in the open "
                    f"dialog's menu ({self.dialog_npc or 'no dialog open'})"
                )
                return Plan(ticks=5, outcome="failed")
            return Plan(ticks=5)
        if a.block == "close_dialog":
            self.dialog_npc = None
            return Plan(ticks=5)
        if a.block in ("attack_nearest", "finish_target") or (
            a.block in HUNT_BLOCKS and sc.encounters
        ):  # a hunt meets one monster per call with encounters on (else its default 1 s, as before)
            w = min(100.0, float(self.world.get("weight_percent") or 0) + sc.weight_per_attack)
            hp = max(1.0, float(self.world.get("hp_percent") or 0) - sc.hp_per_attack)
            return self._fight_plan(a, {"weight_percent": w, "hp_percent": hp})
        if a.block == "use_item":
            item = self._eval(a.params.get("item")) if "item" in a.params else None
            kind = (
                self.static.items[item.id].kind
                if self.static and isinstance(item, ir.ItemRef) and item.id in self.static.items
                else None
            )
            if kind == "heal":
                return Plan(
                    ticks=1,
                    effects={
                        "hp_percent": min(100.0, float(self.world.get("hp_percent") or 0) + 25)
                    },
                )
            return Plan(ticks=1)
        if a.block == "respawn":
            return Plan(ticks=30, effects={"hp_percent": 50.0})
        if a.block == fn.PRESS:  # one hotbar press (runtime.default_plan's)
            return default_plan(a, self)
        spec = self.cat.blocks[a.block].spec if a.block in self.cat.blocks else None
        if spec is not None and spec.profile == "atomic":
            return Plan(ticks=10, atomic=(0, 10))
        return Plan(ticks=10)

    def _exit_plan(self, a: ir.ActionStmt, x: ir.Exit, sheet: MapSheet | None) -> Plan:
        """The ticks of an exit's own actions: walk onto the warp, or to the NPC, then choose."""
        if x.kind == "walk_exit" and x.warp is not None:
            return self._walk_plan(a, (x.warp.x, x.warp.y), 1000, exit_=True)
        if x.kind == "npc_warp" and x.npc is not None:
            npc = sheet.npc(x.npc.key) if sheet else None
            if npc is None:
                self.notes.append(
                    f"exit npc_warp: npc {x.npc.key} is not on {self.world.get('map')}"
                )
                return Plan(ticks=10)
            missing = [o.key for o in x.options if o.key not in npc.menu]
            if missing:
                self.notes.append(
                    f"exit npc_warp: {', '.join(missing)} not in npc {npc.key}'s menu"
                )
            return self._walk_plan(
                a, self._near((npc.x, npc.y)), 1500 + 500 * len(x.options), exit_=True
            )
        return Plan(ticks=10)

    # --- the trace ------------------------------------------------------------------------------
    def _batch(self, a: ir.ActionStmt, hold: bool) -> list[Any]:
        spec = self.cat.blocks[a.block].spec if a.block in self.cat.blocks else None
        keyed = a.block in ("use_item", fn.PRESS) or (spec is not None and spec.types)
        return _KEY if keyed else _CLICK

    def _emit(self, owner: str, events: list[Any], why: str) -> None:
        self.batches += 1
        for ev in events:
            if isinstance(ev, ReleaseAll):
                self.held = False
            elif isinstance(ev, MouseButton | Key):
                self.held = ev.action == "down" or (self.held and ev.action != "up")

    def _release(self, why: str) -> None:
        self.batches += 1
        self.held = False

    def _stat(self, path: str) -> NodeStats:
        return self.stats.setdefault(path, NodeStats())

    def _record(self, path: str | None, t0: float, outcome: str) -> None:
        if path is None:
            return
        s = self._stat(path)
        s.runs += 1
        s.total_s += self.t - t0
        s.first_t = t0 if s.first_t is None else s.first_t
        s.last_t = self.t
        s.last = outcome
        s.outcomes[outcome] += 1

    def _reason_of(self, st: Any, owner: str) -> str:
        return self.paths.get(id(st)) or owner

    def _stmt(self, st: Any, owner: str) -> Generator[_Tick, str | None, str]:
        path = self.paths.get(id(st))
        t0 = self.t
        if isinstance(st, ir.TakeExit):
            self._exit_stmt = st
        try:
            r = yield from super()._stmt(st, owner)
        except _Halt as h:
            self._record(path, t0, "stopped" if isinstance(st, ir.Stop) else f"halt:{h.reason}")
            raise
        except GeneratorExit:
            self._record(path, t0, "interrupted")
            raise
        outcome = "ok"
        if isinstance(st, ir.ActionStmt):
            outcome = self._last_outcome.get(id(st), "ok")
        elif isinstance(st, ir.TakeExit):
            outcome = "exit"
        elif isinstance(st, ir.WaitUntil) and self.t > t0:
            self._play_step({"kind": "wait", "t0": t0, "t1": self.t, "node": path or owner,
                             "outcome": "ok"})  # fmt: skip
        self._record(path, t0, outcome)
        return r

    def _action(self, a: ir.ActionStmt, owner: str) -> Generator[_Tick, str | None, str]:
        t0 = self.t
        # (block, map, cell, the open dialog's NPC, weight) when it starts: a step names where
        # it began (a wing ends on another map)
        before = (self.block, self.world.get("map"), self.world.get("cell"), self.dialog_npc,
                  self.world.get("weight_percent"))  # fmt: skip
        try:
            out = yield from super()._action(a, owner)
        except GeneratorExit:  # pre-empted: the model leaves the character where it was
            self._planned.pop(id(a), None)
            self._planned_ms.pop(id(a), None)
            self._fights.pop(id(a), None)
            if self._done:
                raise
            self._play_step({"kind": "act", "t0": t0, "t1": self.t, "action": a.block,
                             "node": self._where(a), "outcome": "interrupted"}, before)  # fmt: skip
            raise
        self._last_outcome[id(a)] = out
        if id(a) in self.do_paths:
            self._record(self.do_paths[id(a)] + ":" + a.block, t0, out)
        planned = self._planned.pop(id(a), None)
        walk_ms = self._planned_ms.pop(id(a), 0.0)
        fight = self._fights.pop(id(a), None)
        m = self.world.get("map")
        if out == "ok" and planned is not None and isinstance(m, str):
            self._segment(planned, self._where(a), m)
        self._play_action(a, t0, before, out, planned, walk_ms, fight)
        if out == "ok" and a.block == "set_save_point":
            self._set_save_point(a)
        if out == "ok" and a.block == "respawn":
            self._pending_respawn = self.block or "main"
            if self.save_point is None:
                self.notes.append(
                    f"t={self.t:.0f}s: respawn with an UNKNOWN save point: the model keeps the "
                    "character where it died (the real client sends it to the save point)"
                )
        return out

    # --- the play list (the module docstring) ---------------------------------------------------
    def _play_step(self, step: dict[str, Any], before: tuple[Any, ...] | None = None) -> None:
        if len(self.play) >= MAX_PLAY:
            self.play_capped = True
            return
        block, m = (before[0], before[1]) if before else (self.block, self.world.get("map"))
        out: dict[str, Any] = {
            "block": block or None,
            "map": m if m is not None else self.world.get("map"),
        }
        out.update(step)
        out["t0"], out["t1"] = round(out["t0"], 2), round(max(out["t0"], out["t1"]), 2)
        if "seen_t" in out:
            out["seen_t"] = round(out["seen_t"], 2)
        cells = out.get("cells")
        if cells is not None:
            if self.play_cells + len(cells) > MAX_PLAY_CELLS:
                out["cells"], out["trimmed"] = [cells[0], cells[-1]], True
            self.play_cells += len(out["cells"])
        self.play.append(out)

    def _play_walk(self, before: tuple[Any, ...], t0: float, ms: float, planned: Any,
                   node: str, purpose: str, outcome: str) -> float:  # fmt: skip
        """A walk step for a planned route; returns when it ends (the rest of the action
        follows it). Nothing when the action did not walk (a failure before it moved)."""
        if planned is None or outcome != "ok":
            return t0
        route, estimated = planned
        if len(route) < 2:
            return t0
        t1 = t0 + ms / 1000
        self._play_step({"kind": "walk", "t0": t0, "t1": t1, "cells": [list(c) for c in route],
                         "estimated": estimated, "node": node, "purpose": purpose,
                         "outcome": outcome}, before)  # fmt: skip
        return t1

    def _play_action(
        self,
        a: ir.ActionStmt,
        t0: float,
        before: tuple[Any, ...],
        out: str,
        planned: Any,
        walk_ms: float,
        fight: dict[str, Any] | None,
    ) -> None:
        node = self._where(a)
        base = {"node": node, "action": a.block, "outcome": out}
        sheet = self.static.sheet(before[1]) if self.static and isinstance(before[1], str) else None
        if a.block == "walk_to":
            if not self._play_walk(before, t0, walk_ms, planned, node, "walk", out) > t0:
                self._play_step({**base, "kind": "act", "t0": t0, "t1": self.t}, before)
        elif a.block in NPC_BLOCKS:
            ref = self._eval(a.params.get("npc")) if "npc" in a.params else None
            npc = sheet.npc(ref.key) if sheet and isinstance(ref, ir.NpcRef) else None
            t = self._play_walk(before, t0, walk_ms, planned, node, "npc", out)
            self._play_step({**base, "kind": "talk", "t0": t, "t1": self.t,
                             "npc": ref.key if isinstance(ref, ir.NpcRef) else None,
                             "at": [npc.x, npc.y] if npc else None}, before)  # fmt: skip
        elif a.block in ("choose_menu", "close_dialog"):
            ref = self._eval(a.params.get("option")) if "option" in a.params else None
            self._play_step({**base, "kind": "menu", "t0": t0, "t1": self.t, "npc": before[3],
                             "option": ref.key if isinstance(ref, ir.OptionRef) else None},
                            before)  # fmt: skip
        elif a.block in FIGHT_BLOCKS and (a.block not in HUNT_BLOCKS or fight is not None):
            t = self._play_walk(before, t0, walk_ms, planned, node, "engage", out)
            gained = float(self.world.get("weight_percent") or 0) > float(before[4] or 0)
            self._play_step({**base, "kind": "fight", "t0": t, "t1": self.t, "seen_t": t0,
                             "mob": fight["mob"] if fight else None,
                             "at": fight["at"] if fight else None,
                             "loot": out == "ok" and gained}, before)  # fmt: skip
        elif a.block == "use_item":
            item = self._eval(a.params.get("item")) if "item" in a.params else None
            iid = item.id if isinstance(item, ir.ItemRef) else None
            kind = self.static.items[iid].kind if self.static and iid in self.static.items else None
            self._play_step({**base, "kind": "item", "t0": t0, "t1": self.t, "item": iid,
                             "item_kind": kind}, before)  # fmt: skip
        elif a.block in ("loot", "respawn"):
            self._play_step({**base, "kind": a.block, "t0": t0, "t1": self.t}, before)
        elif a.block == fn.PRESS:  # an act that names its hotbar key (Amendment C)
            self._play_step({**base, "kind": "act", "t0": t0, "t1": self.t, "key": fn.key_of(a)},
                            before)  # fmt: skip
        else:
            self._play_step({**base, "kind": "act", "t0": t0, "t1": self.t}, before)
        m1 = self.world.get("map")
        if out == "ok" and m1 != before[1] and before[1] is not None:  # a wing, a respawn
            cell = self.world.get("cell")
            self._play_step({"kind": "arrive", "t0": self.t, "t1": self.t, "via": a.block,
                             "node": node, "map": m1, "block": self.block or None,
                             "cell": list(cell) if cell else None})  # fmt: skip

    def _set_save_point(self, a: ir.ActionStmt) -> None:
        sheet = self._sheet()
        ref = self._eval(a.params.get("npc")) if "npc" in a.params else None
        npc = sheet.npc(ref.key) if sheet and isinstance(ref, ir.NpcRef) else None
        m = self.world.get("map")
        if npc is None or not isinstance(m, str):
            return
        cell = npc.kafra.save_cell if npc.kafra and npc.kafra.save_cell else None
        if cell is None:
            self.notes.append(f"npc {npc.key}: its save cell is not in the map sheet; the model "
                              f"uses the npc's own cell")  # fmt: skip
            cell = (npc.x, npc.y)
        self.save_point = (m, (int(cell[0]), int(cell[1])))

    def _segment(self, planned: tuple[list[Cell], bool], node: str, m: str) -> None:
        route, estimated = planned
        if not route:
            return
        key = (m, tuple(route))
        seg = self.segments.get(key)
        if seg is not None:
            seg["count"] += 1
            return
        if self.cells_kept + len(route) > MAX_CELLS:
            return
        self.cells_kept += len(route)
        self.segments[key] = {
            "map": m,
            "node": node,
            "cells": [list(c) for c in route],
            "estimated": estimated,
            "count": 1,
            "t": round(self.t, 1),
        }

    def _exit(self, x: ir.Exit, owner: str) -> Generator[_Tick, str | None, None]:
        before_block, before_map, t0 = self.block, self.world.get("map"), self.t
        before = (before_block, before_map, self.world.get("cell"), self.dialog_npc,
                  self.world.get("weight_percent"))  # fmt: skip
        if x.kind == "item_warp" and self.save_point is None:
            self.notes.append(
                f"t={self.t:.0f}s: {before_block}'s item_warp with an UNKNOWN save point: the "
                f"model arrives at {x.to_block}.{x.to_entry} (the real client goes to the save "
                "point)"
            )
        self._exit_ctx = x
        try:
            yield from super()._exit(x, owner)
        finally:
            self._exit_ctx = None
        planned, self._exit_planned = self._exit_planned, None
        exit_ms, self._exit_ms = self._exit_ms, 0.0
        if planned is not None and isinstance(before_map, str):  # walked on the map it left
            self._segment(planned, f"{before_block}: exit {x.kind}", before_map)
        self._play_exit(x, t0, before, planned, exit_ms, owner)
        self.transitions.append(
            {
                "t": round(self.t, 1),
                "kind": x.kind,
                "from": before_block,
                "to": self.block if self.block != before_block else x.to_block,
                "entry": x.to_entry,
                "arrived": self.block == x.to_block,
                "map": self.world.get("map"),
                "s": round(self.t - t0, 1),
            }
        )
        if self.block != before_block:
            self.block_visits[self.block] += 1
        if self.scenario.single_block:
            raise _Halt("single_block_exit")

    def _play_exit(self, x: ir.Exit, t0: float, before: tuple[Any, ...], planned: Any,
                   ms: float, owner: str) -> None:  # fmt: skip
        """An exit's steps on the map it leaves (the walk onto the warp or up to the NPC, the talk
        and its options, the wing), then the exit itself: where it arrived."""
        node = self.paths.get(id(self._exit_stmt)) if self._exit_stmt is not None else None
        node = node or f"{before[0] or 'main'}: exit {x.kind}"
        base = {"node": node, "action": f"take_exit {x.kind}", "outcome": "ok"}
        t = self._play_walk(before, t0, ms, planned, node, "exit", "ok")
        if x.kind == "npc_warp" and x.npc is not None:
            sheet = (
                self.static.sheet(before[1]) if self.static and isinstance(before[1], str) else None
            )
            npc = sheet.npc(x.npc.key) if sheet else None
            self._play_step({**base, "kind": "talk", "t0": t, "t1": self.t, "npc": x.npc.key,
                             "at": [npc.x, npc.y] if npc else None,
                             "options": [o.key for o in x.options]}, before)  # fmt: skip
        elif x.kind == "item_warp":
            item = self._eval(x.item) if isinstance(x.item, ir.Var) else x.item
            iid = item.id if isinstance(item, ir.ItemRef) else None
            kind = self.static.items[iid].kind if self.static and iid in self.static.items else None
            step = {**base, "kind": "item", "t0": t, "t1": self.t, "item": iid, "item_kind": kind}
            if x.proc is not None:  # an item warp by function (Amendment C): its presses ran
                step["proc"] = x.proc
            self._play_step(step, before)
        cell = self.world.get("cell")
        self._play_step({**base, "kind": "exit", "t0": self.t, "t1": self.t, "exit": x.kind,
                         "from_block": before[0] or None, "to_block": x.to_block,
                         "to_entry": x.to_entry, "to_map": self.world.get("map"),
                         "cell": list(cell) if cell else None,
                         "arrived": self.block == x.to_block,
                         "warp": [x.warp.x, x.warp.y] if x.warp is not None else None},
                        before)  # fmt: skip

    def _relocate(self) -> None:
        before = self.block
        super()._relocate()
        if self.block != before:
            self.block_visits[self.block] += 1
        if self._pending_respawn is not None:
            self.transitions.append(
                {
                    "t": round(self.t, 1),
                    "kind": "death_respawn",
                    "from": self._pending_respawn,
                    "to": self.block,
                    "entry": None,
                    "arrived": True,
                    "map": self.world.get("map"),
                    "s": 0.0,
                }
            )
            self._pending_respawn = None

    def _step(self, frame: Any) -> bool:
        if self.block:
            self.block_time[self.block] = self.block_time.get(self.block, 0.0) + TICK_S
        return super()._step(frame)

    # --- the result -----------------------------------------------------------------------------
    def result(self) -> dict[str, Any]:
        end = self.run()
        self._done = True
        events = [
            {"t": round(t, 1), "kind": kind, "what": what}
            for t, kind, what in self.log[:MAX_EVENTS]
        ]
        horizon = end == "max_ticks"
        return {
            "end": "horizon" if horizon else end,
            "t_end_s": round(self.t, 1),
            "start": self.start,
            "final": {
                "block": self.block or None,
                "map": self.world.get("map"),
                "cell": list(self.world["cell"]) if self.world.get("cell") else None,
                "hp_percent": self.world.get("hp_percent"),
                "weight_percent": self.world.get("weight_percent"),
            },
            "save_point": (
                {"map": self.save_point[0], "cell": list(self.save_point[1])}
                if self.save_point
                else None
            ),
            "nodes": {p: s.doc() for p, s in sorted(self.stats.items())},
            "blocks": {
                b: {"visits": self.block_visits.get(b, 0), "time_s": round(t, 1)}
                for b, t in sorted(self.block_time.items())
            },
            "transitions": self.transitions[:MAX_EVENTS],
            "paths": list(self.segments.values()),
            "events": events,
            "events_capped": len(self.log) > MAX_EVENTS,
            "input_batches_counted": self.batches,
            # #10 (Batt 2026-10-09): every /where read with its reason, against the budget
            "where": {
                "count": len(self.where),
                "budget": self.flow.where_budget,
                "over": len(self.where) > self.flow.where_budget,
                "reads": [{"t": round(t, 1), "reason": r} for t, r in self.where[:MAX_EVENTS]],
            },
            "notes": sorted(set(self.notes))[:50],
            # the run in order for the Maps page's map view (the module docstring)
            "play": list(self.play),
            "play_capped": self.play_capped,
            "scenario": self.scenario.model_dump(mode="json"),
            "world": {
                "server": self.static.server if self.static else None,
                "maps": sorted(self.static.sheets) if self.static else [],
            },
        }


def simulate(
    flow: ir.Flow,
    world: World | None,
    scenario: Scenario | None = None,
    cat: Catalogue | None = None,
) -> dict[str, Any]:
    """Run the flow against the static data and the scenario; return the trace document."""
    return TraceSim(flow, world, scenario, cat).result()
