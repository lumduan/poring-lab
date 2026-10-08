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
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from poring_env.protocol import Key, MouseButton, MouseMove, ReleaseAll
from poring_flow import ir
from poring_flow.catalogue import Catalogue, catalogue
from poring_flow.runtime import TICK_S, Plan, Sim, _Halt, _Tick
from poring_flow.sheet import Cell, MapSheet, World

WALK_MS = 150  # RO's default walk speed: one cell
DIAG_MS = 212  # a diagonal step (x sqrt 2)
MAX_HORIZON_S = 3600
MAX_CELLS = 20_000  # every path segment together
MAX_EVENTS = 400
ScenarioKey = Literal[
    "hp_percent", "sp_percent", "weight_percent", "is_dead", "engagement_seen", "engaged_species"
]


class Change(BaseModel):
    """One timeline entry: at `t` seconds, the scenario sets these sensor values."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    t: float = Field(ge=0, le=MAX_HORIZON_S)
    set: dict[ScenarioKey, float | bool | int] = Field(default_factory=dict, max_length=6)
    sees: dict[int, bool] = Field(default_factory=dict, max_length=10)  # mob id -> seen


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
        timeline: list[tuple[float, dict[str, Any]]] = []
        for ch in sc.timeline:
            changes: dict[str, Any] = {}
            for k, v in ch.set.items():
                changes[k] = ir.MobRef(id=int(v)) if k == "engaged_species" else v
            changes.update({f"sees:{m}": seen for m, seen in ch.sees.items()})
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
        self._exit_planned: tuple[list[Cell], bool] | None = None
        self._exit_ctx: ir.Exit | None = None
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
        else:
            self._planned[id(a)] = (route, estimated)
        return Plan(ticks=_ticks(ms + extra_ms), effects={"cell": to})

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
        if a.block in ("close_dialog", "close_npc_dialog"):
            self.dialog_npc = None
            return Plan(ticks=5)
        if a.block in ("attack_nearest", "finish_target"):
            w = min(100.0, float(self.world.get("weight_percent") or 0) + sc.weight_per_attack)
            hp = max(1.0, float(self.world.get("hp_percent") or 0) - sc.hp_per_attack)
            return Plan(
                ticks=_ticks(sc.attack_s * 1000), effects={"weight_percent": w, "hp_percent": hp}
            )
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
        return _KEY if a.block == "use_item" or (spec is not None and spec.types) else _CLICK

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

    def _stmt(self, st: Any, owner: str) -> Generator[_Tick, str | None, str]:
        path = self.paths.get(id(st))
        t0 = self.t
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
        self._record(path, t0, outcome)
        return r

    def _action(self, a: ir.ActionStmt, owner: str) -> Generator[_Tick, str | None, str]:
        t0 = self.t
        out = yield from super()._action(a, owner)
        self._last_outcome[id(a)] = out
        if id(a) in self.do_paths:
            self._record(self.do_paths[id(a)] + ":" + a.block, t0, out)
        planned = self._planned.pop(id(a), None)
        m = self.world.get("map")
        if out == "ok" and planned is not None and isinstance(m, str):
            self._segment(planned, self._where(a), m)
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
        if planned is not None and isinstance(before_map, str):  # walked on the map it left
            self._segment(planned, f"{before_block}: exit {x.kind}", before_map)
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
            "notes": sorted(set(self.notes))[:50],
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
