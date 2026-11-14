#!/usr/bin/env python3
"""THE LIVE BLOCK PLAYER (Batt 2026-11-13: "build the player of blocks in the real game first";
docs/planning/live-blocks.md stage 1, ADR-0020 Amendment E): it plays a PROJECT's map node in the
real game, block by block.

    flow_play.py play --project FILE --node NODE --label LABEL --max-s N [--stop-file F]
                      [--project-hash H] [--runner-config FILE]
    flow_play.py plan --project FILE --node NODE --max-s N    (PURE: what it would play; no screen)

The Run helper (scripts/flow_run.py) starts `play` for POST /flows/run/project, as it starts the
runner for the runner's Run; nothing else should.

HOW IT PLAYS: the project compiles (poring_flow.project.compile_project) and the engine's own tree
runtime (poring_flow.runtime.Sim: the event classes, inserts at safe points, pre-empts, atomic
sections, functions with inputs, relocation) runs it with a LIVE environment in place of the fake
one (`LivePlayer`): the real clock (a tick every TICK_S, paced), the sensors read from PIXELS each
tick (HP / SP percent: hp_percent.py; the weight readout: gm_state; the death dialog: gm_vitals'
signature; the map's NAME: the minimap's picture, minimap_id.py -- no /where is ever typed), and
input through ONE ro_agent Agent (/internal/agent, the backend's mux: ASSIST, the human's lease,
the interlock and the foreground gate apply to every press; the UI gate clears the client at the
start, as the runner's own start does).

WHAT PLAYS (poring_flow.live, the ONE place; blocks.yaml `live: true`): press_key (ro_agent's
paced tap), wait / wait_until on the live sensors, if / while / repeat / for / set / call / return
/ stop / break / continue, events (insert or pre-empt, on fresh values each tick), an item warp by
a function (its body runs, then the minimap must name the target node's map within the exit's
timeout, else the run stops), and the HUNT CORE: a dungeon_hunt block plays the runner
(scripts/dungeon_hunt.py run) IN THIS PROCESS with the SAME Agent and Screen (one process, one
input writer; dungeon@9.48: run(a, hook=..., session=...)), its argv exactly the Run helper's for
that map (flow_run.FIXED, the flow's flags, flow_config.argv of the config with the node's keys),
its time box the player's remaining time. Its TICK HOOK is called once per runner tick. When it
ends on its own map exit (the Butterfly Wing home, the respawn), the player relocates by the map's
name, or ends when no node of the project is there. Anything else is refused BEFORE ANY INPUT, each
one named ("walk_to cannot play live yet (stage 4)").

THE BOX'S SURVIVAL INSIDE THE HUNT CORE (stage 2, live-blocks.md section 3.2; dungeon@9.49): the
node's own events (and Global's) play WHILE the runner hunts. On every runner tick -- its survival
point, and guard_tick's quick read inside a long action -- the runner calls the hook's
``survive(HuntTick, press)``: the player sets the box's sensors from the tick (hp_percent,
sp_percent, sees_boss: the runner's boss read; is_dead), evaluates the box's events by the
engine's own rules (edges, until / rearm, cooldown_s, limits: runtime.Sim._perceive / _fire), then
plays every due body at once at that safe point -- the pre-empts first, a ReleaseAll before each
(the engine's rule), then the inserts (runtime.Sim._run_inserts) -- through ``press``: the
runner's own press of that role (one Agent, one writer; the runner waits while the box plays). The
runner's own handlers the box plays are off for that run (poring_flow.live.hunt_plan's PLAYS,
passed as run(box_plays=...)); after a box Fly Wing the runner runs its own after-the-fly steps.
A tick with no HP read and no boss line decides nothing (the runner's own sustain reads nothing
without an HP read either). An event's limit (handler_runaway, max_per_run) or a refused key ends
the run through the runner's normal end, then the player ends with that reason.

THE BOX'S FUNCTIONS AT THE RUNNER'S MOMENTS (stage 3, live-blocks.md section 3.3; dungeon@9.50):
the Knife swap (knife_on before the steal strike, knife_back after the steal or its time box), the
way home at the end (home) and the death exit's two presses (respawn, respawn_confirm) are the
box's FUNCTIONS when the project writes them so (poring_flow.live.hunt_plan: a knife / home
function that is more than one press_key; a respawn function of click_at). The runner keeps
deciding WHEN: at each of its moments it calls the hook's ``call(role, why, press, click)``, and
the player plays that function's STEPS (prepared before any input: presses, waits, clicks, through
calls with literal arguments) NOW -- each press through the runner's own press of a key of that
moment, each click as its own two-motion click (the death exit only), each wait slept exactly (at
most 1 s in all) -- while the runner waits; its read-backs and retries stay its own. The WEIGHT
event (an event that reads weight_percent() and stops) decides on the runner's weight read, at its
UI watch (its own moment, never mid-fight): it ends the run normally, and the runner's end flies
her home. A role function that is one press_key stays the runner's own key: a box without these
plays exactly as stage 2 (run() gets no box_roles).

THE BOX'S MONSTERS (stage 4a, live-blocks.md section 3.4; dungeon@9.51): `use_model("xmas02")` in
the node's main names the hunt core's model (a models.yaml entry: the runner refuses, before any
input, one that is not the file its box detector loads there), and one function per monster,
`attack_<class>(t, priority=N)` (the tab `monsters`), is that monster's RECIPE of the runner's
steps (poring_flow.recipes: strike / wait_steal / wait_kill / loot(t) and the hunt core's knife_on()
/ knife_back(), in one of the two orders the runner plays). The plan is decided before any input
(live.hunt_plan -> RunnerPlan.recipes); at its LOCK -- a new target's first strike -- the runner
calls the hook's ``recipe(species, why)`` and the player answers with that species' recipe
(LivePlayer.hunt_recipe, recorded), or None (the runner's own). The runner plays it with its own
code: a recipe without knife_on strikes that monster without the Knife swap. A box without
use_model and recipes plays exactly as stage 3 (run() gets no box_model, no box_recipes).

THE BOX EATS FROM THE HOTBAR (2026-11-14, Batt ~14:0x: "the moment we get a Candy Cane or a Candy,
eat it to add HP right away; that also cuts the weight"; live-blocks.md section 10; dungeon@9.52):
the sensor hotbar_count(key) is the count drawn on a row-1 hotbar slot. Inside a hunt core the
player reads it from the runner's tick frame (HuntTick.frame) with the runner's own reader
(hotbar_count.read_count, its digit templates loaded at run time from data/hotbar), only for the
keys the box's events name (live.hunt_plan -> RunnerPlan.hotbar_keys) and at most once every
HOTBAR_EVERY_S a key (between reads it keeps the last value); an empty slot reads 0, a count it
cannot read is unknown -- an event that reads it is then not evaluated (it never fires, and a
repeating one pauses). Elsewhere it is unknown. An event's presses through dungeon_hunt's eat
function are EAT presses: the runner presses them through its own press path (run(box_eat=...)).

THE START, before any input: the project validates; the node is a map node; every block plays live;
the time box fits the Settings maximum (--max-s); each hunt core's keys resolve from the node's
functions (project.runner_keys) and its runner settings from the config file; then the START CHECK
reads the screen only (no Agent open yet): with a hunt core on the start node, the runner's own
read-only check (dungeon@9.45/9.46, in-process, under its no-input guard: identity, her map read
from the minimap, the chat input closed, the weight, the stock on the role keys); else identity,
the chat input closed and the map's name read as the node's map. PLAYER MODE always: it types no
line at all, GM or other.

STOP: the Run helper's stop file. At the next tick outside an atomic section the player ends (a
hunt core ends through the runner's own Stop: its --stop-file, its normal end), everything held is
released (ReleaseAll) and the run ends. The time box: min(the project's max_runtime_s, --max-s).

ITS RECORD: a session folder /dev/shm/poring-lab-demo/<time>-play-<label>/events.jsonl, as the
runner's (the helper's Live tracker and the page's live line read it): run_start, each block entered
(`block`, its node path "<node>/<tab>/<site>"), each key pressed (`key`: the key only), each event
fired (`event`: its name, its node path, the READING that fired it, `in` "hunt" inside the hunt
core), the HP / SP / weight / map once a second (`hp_read`), the hunt core's own events
mirrored (`hunt_start`, the runner's kills, loot, presses, `hunt_end`), and `run_end` with its
reason and its words.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import time
from collections.abc import Callable, Generator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
for _p in ("packages/poring_flow/src", "packages/poring_skills/src", "packages/poring_env/src"):
    if str(ROOT / _p) not in sys.path:
        sys.path.append(str(ROOT / _p))

import flow_config as fc  # noqa: E402
import flow_run as fr  # noqa: E402

from poring_env.protocol import Key, ReleaseAll  # noqa: E402
from poring_flow import functions as fn  # noqa: E402
from poring_flow import ir, live  # noqa: E402
from poring_flow import project as pj  # noqa: E402
from poring_flow import recipes as rc  # noqa: E402
from poring_flow.runtime import (  # noqa: E402
    MAIN_RANK,
    Relocate,
    Sim,
    _Frame,
    _Halt,
    _Tick,
    hotbar_world_key,
)

VERSION = live.VERSION  # dungeon_hunt.SURVIVAL_EVENTS_VERSION (test_live_player.py pins them)
DEMO = fr.DEMO
HP_EVERY_S = 1.0  # the hp_read record (the live line's HP), not the sensor read (every tick)
WEIGHT_EVERY_S = 0.5  # the weight readout needs two equal reads (gm_state._weight): not each tick
EXPECT_S = 20.0  # after a Butterfly Wing's press, a map change within this long is expected
SETTLE_S = 20.0  # a relocation waits this long for the minimap to name the map
SETTLE_POLL_S = 0.25
BLOCK_LOG_S = 1.0  # the same node entered again within this long is not logged again (a loop)
# 2026-11-14 (live-blocks.md 10): hotbar_count(key) inside the hunt core -- each key is read from
# the runner's tick frame at most this often (between reads it keeps the last value): a press's
# count change shows within ~0.5 s, and an eat event's cooldown (the one box: 1.5 s) is longer
HOTBAR_EVERY_S = 1.0
HOTBAR_ROWS = 40  # the game frame's top rows that hold row 1's icons and counts (hotbar_count.py)
ROLE_PRESS = {"heal_key": "potion", "fly_key": "fly", "home_key": "home", "knife_key": "opener",
              "dagger_key": "equip"}  # flow_run.PRESS_BLOCK's words (the live line)  # fmt: skip
MIRROR = frozenset({*fr.EVENT_BLOCK, "press", "death", "player_home", "player_end",
                    "player_respawn", "stock", "stop_file", "hook_stop", "run_start",
                    "run_end", "escape", "box_refused"})  # fmt: skip
CHECK_LABEL = "flowplay-check"


def refuse(words: str) -> str:
    return f"flow_play refused before any input: {words}"


def _sense_names(e: Any) -> set[str]:
    return {x.sensor for x in ir.sub_exprs(e) if isinstance(x, ir.Sense)}


# --- the plan (PURE: no screen, no input) ---------------------------------------------------------
@dataclass(frozen=True)
class RunnerPlan:
    """A hunt core's runner on one map node: the Run helper's flow for that map, the keys from the
    node's functions, the settings (the config file's, the keys over them)."""

    block: str
    flow_id: str
    keys: dict[str, str]
    vals: dict[str, Any]
    # stage 2: the box's events that play inside this hunt core and the runner's own handlers
    # they replace (poring_flow.live.hunt_plan; dungeon_hunt run(box_plays=...))
    events: tuple[str, ...] = ()
    plays: frozenset[str] = frozenset()
    # stage 3: the role functions the hunt core calls (role -> its steps, its function's name),
    # the events that decide on the weight read, where knife_on's body leaves her
    calls: Mapping[str, tuple[fn.Step, ...]] = field(default_factory=dict)
    call_names: Mapping[str, str] = field(default_factory=dict)
    weight_events: tuple[str, ...] = ()
    knife_ends: str = "opener"
    # stage 4a: the box's model (use_model's catalogue entry) and its monsters' recipes (species
    # -> poring_flow.recipes.Recipe), the species the runner strikes with its own recipe
    model_doc: Mapping[str, Any] | None = None
    recipes: Mapping[str, Any] = field(default_factory=dict)
    default_species: tuple[str, ...] = ()
    # 2026-11-14 (live-blocks.md 10): the keys the box's events eat (through dungeon_hunt's eat
    # function, its name) and the keys their hotbar_count reads name (read from the tick frame)
    eat_keys: tuple[str, ...] = ()
    eat_name: str | None = None
    hotbar_keys: tuple[str, ...] = ()

    def box_kwargs(self) -> dict[str, Any]:
        """dungeon_hunt run(...)'s box arguments: none at all for a box without events, functions,
        model or recipes (the CLI's run); each stage's only where the box plays it."""
        box: dict[str, Any] = {"box_plays": sorted(self.plays)} if self.plays else {}  # stage 2
        if self.calls:  # stage 3: the roles the box's functions play (none: exactly as 9.49)
            box["box_roles"] = self.box_roles()
        if self.model_doc is not None:  # stage 4a: use_model (none: exactly as 9.50)
            box["box_model"] = dict(self.model_doc)
        if self.recipes:  # stage 4a: the monsters' recipes
            box["box_recipes"] = {sp: r.doc() for sp, r in sorted(self.recipes.items())}
        if self.eat_keys:  # 2026-11-14: the keys the box eats (none: exactly as 9.51)
            box["box_eat"] = list(self.eat_keys)
        return box

    def box_roles(self) -> dict[str, str]:
        """dungeon_hunt run(box_roles=...): each called role, with where its body leaves her."""
        ends = {"knife_on": self.knife_ends, "knife_back": "armed", "home": "home",
                "respawn": "save_point", "respawn_confirm": "save_point"}  # fmt: skip
        return {r: ends[r] for r in self.calls}

    def argv(self, label: str, stop_file: Path | None, minutes: float | None) -> list[str]:
        """Exactly the Run helper's runner argv for this map (flow_run.command without its head),
        its --minutes the player's remaining time when that is shorter."""
        flow = fr.FLOWS[self.flow_id]
        stop = [] if stop_file is None else ["--stop-file", str(stop_file)]
        out = [*fr.FIXED, "--label", label, *stop, *flow.flags, *fc.argv(self.vals)]
        if minutes is not None and "--minutes" in out:
            i = out.index("--minutes") + 1
            out[i] = f"{min(float(out[i]), minutes):.2f}"
        return out


@dataclass(frozen=True)
class Prepared:
    project: pj.Project
    compiled: pj.Compiled
    node: str
    project_hash: str
    cap_s: float
    runners: dict[str, RunnerPlan]  # map block -> its hunt core's runner
    roles: dict[str, str] = field(default_factory=dict)  # key -> its role's word (the live line)

    @property
    def flow(self) -> ir.Flow:
        assert self.compiled.flow is not None
        return self.compiled.flow

    @property
    def map(self) -> str:
        node = self.project.node(self.node)
        assert isinstance(node, pj.MapNode)
        return node.map.map

    def doc(self) -> dict[str, Any]:
        return {"version": VERSION, "project": self.project.name, "node": self.node,
                "map": self.map, "project_hash": self.project_hash, "cap_s": self.cap_s,
                "runners": {b: {"flow": p.flow_id, "keys": p.keys, "events": list(p.events),
                                "box_plays": sorted(p.plays),
                                **({"box_roles": p.box_roles(),
                                    "calls": {r: [x.doc() for x in st]
                                              for r, st in p.calls.items()}}
                                   if p.calls else {}),
                                **({"box_model": dict(p.model_doc)} if p.model_doc else {}),
                                **({"box_recipes": p.box_kwargs()["box_recipes"],
                                    "default_species": list(p.default_species)}
                                   if p.recipes else {}),
                                **({"box_eat": list(p.eat_keys), "eat": p.eat_name}
                                   if p.eat_keys else {}),
                                **({"hotbar_keys": list(p.hotbar_keys)}
                                   if p.hotbar_keys else {})} for b, p in
                            self.runners.items()}}  # fmt: skip


def runner_flow(map_: str) -> str | None:
    """The Run helper's runner flow for a map (flow_run.FLOWS: today xmas_dun02's)."""
    return next((k for k, f in fr.FLOWS.items() if f.map == map_), None)


def prepare(text: str, node: str, max_s: int | None, *, config_dir: Path = fr.CONFIG_DIR,
            runner_vals: Mapping[str, Mapping[str, Any]] | None = None,
            want_hash: str | None = None) -> Prepared | str:  # fmt: skip
    """PURE but for the config file: the plan, or why the run is refused (words) -- everything
    decided before any screen is read or any input path opened."""
    try:
        p = pj.from_json(text)
    except pj.ProjectError as e:
        return refuse(f"the project does not validate: {'; '.join(e.messages[:5])}")
    if pj.has_secret(p):
        return refuse("the project holds a credential that is not a plain name (never played)")
    h = pj.project_hash(p)
    if want_hash is not None and want_hash != h:
        return refuse(f"the project's hash {h[:12]} is not the checked {want_hash[:12]}")
    n = p.node(node)
    if not isinstance(n, pj.MapNode):
        return refuse(f"{node} is no map node of the project (the player starts on a map node)")
    try:
        c = pj.compile_project(p)
    except pj.ProjectError as e:
        return refuse(f"the project does not compile: {'; '.join(e.messages[:5])}")
    if c.flow is None:
        return refuse("the project has no map node")
    bad = live.problems(c.flow)
    if bad:
        shown = [f"{b.words} at {c.where(b.path).path or b.path}" for b in bad[:12]]
        more = f" (+{len(bad) - 12} more)" if len(bad) > 12 else ""
        return refuse(f"{len(bad)} cannot play live: " + "; ".join(shown) + more)
    if max_s is None:
        return refuse("no configured maximum run time (--max-s)")
    if p.max_runtime_s > max_s:
        return refuse(f"max_runtime_s {p.max_runtime_s} is above the configured maximum {max_s}")
    runners: dict[str, RunnerPlan] = {}
    roles: dict[str, str] = {}
    for block, _a in live.runner_blocks(c.flow):
        if block in runners:
            continue
        b = c.flow.workflow.blocks if c.flow.workflow else []
        map_ = next(x.map.map for x in b if x.name == block)
        fid = runner_flow(map_)
        if fid is None:
            return refuse(f"{block}: no runner plays {map_} (the hunt core plays "
                          f"{', '.join(sorted(f.map for f in fr.FLOWS.values()))})")  # fmt: skip
        rk = pj.runner_keys(p, block, c)
        if rk.keys is None:
            return refuse(f"{block}'s keys: {'; '.join(rk.problems[:5])}")
        if runner_vals is not None and block in runner_vals:
            vals, why = dict(runner_vals[block]), fc.clash(dict(runner_vals[block]))
        else:
            vals, _src, _ks, why = fr.run_values(fr.FLOWS[fid], rk.keys, config_dir)
        if why:
            return refuse(f"{block}'s runner settings: {why}")
        hp = live.hunt_plan(c.flow, block)  # its problems refused above (live.problems)
        runners[block] = RunnerPlan(block, fid, dict(rk.keys), vals, hp.events, hp.plays,
                                    dict(hp.calls), dict(hp.call_names), hp.weight_events,
                                    hp.knife_ends, hp.model_doc, dict(hp.recipes),
                                    hp.default_species, hp.eat_keys, hp.eat_name,
                                    hp.hotbar_keys)  # fmt: skip
        roles.update({k: ROLE_PRESS[f] for f, k in rk.keys.items() if f in ROLE_PRESS})
        roles.update({k: "eat" for k in hp.eat_keys})  # 2026-11-14: the live line's words
    return Prepared(p, c, node, h, float(min(p.max_runtime_s, max_s)), runners, roles)


# --- the session record (the runner's shape: the helper's Live tracker reads it) ------------------
class SessionLog:
    def __init__(self, demo: Path, label: str, clock_ns: Callable[[], int] = time.monotonic_ns):
        self.dir = demo / f"{time.strftime('%Y%m%dT%H%M%S')}-play-{label}"
        self.dir.mkdir(parents=True, exist_ok=False)
        self.fh = (self.dir / "events.jsonl").open("a")
        self.ns = clock_ns
        self.n = 0

    def ev(self, rec: Mapping[str, Any]) -> None:
        self.fh.write(json.dumps({"t_ns": self.ns(), **rec}) + "\n")
        self.fh.flush()
        self.n += 1

    def close(self) -> None:
        self.fh.close()


# --- the live I/O: what the player touches (fakes in tests/test_live_player.py) -------------------
class LiveIO:
    """The interface: a clock, the sensors, the start check's screen, ONE input path. The real
    one is `PixelIO`; every method may raise SystemExit (ro_agent.Stop) to stop the run."""

    agent: Any = None
    screen: Any = None

    def clock(self) -> float:
        return time.monotonic()

    def sleep(self, s: float) -> None:
        time.sleep(s)

    def ns(self) -> int:
        return time.monotonic_ns()

    def senses(self) -> dict[str, Any]:  # hp_percent, sp_percent, weight_percent, is_dead, map
        raise NotImplementedError

    def open(self) -> None:  # the input path: an Agent (ASSIST, the lock, the human's lease)
        raise NotImplementedError

    def ui_clear(self) -> None:  # the UI gate and the client in front, as the runner's start
        raise NotImplementedError

    def tap(self, code: str) -> None:  # a hotbar key, paced (ro_agent.Agent.keys)
        raise NotImplementedError

    def release(self) -> None:  # ReleaseAll
        raise NotImplementedError

    def hotbar_counts(self, frame: Any, keys: Sequence[str]) -> dict[str, int | None]:
        """2026-11-14: each key's drawn count on the hunt core's tick frame (0: an empty slot;
        None: unread). This interface reads none (unknown); PixelIO reads the pixels."""
        return {k: None for k in keys}

    def close(self) -> None:
        pass


def read_hotbar(frame: Any, keys: Sequence[str], tpl: Mapping[str, Any]) -> dict[str, int | None]:
    """PURE (2026-11-14, live-blocks.md 10): each row-1 key's count on a game-region frame, by the
    runner's own reader (hotbar_count.read_count on hotbar_count.gray of the frame's top
    HOTBAR_ROWS rows; dungeon_hunt.hotbar_slot): 0 for an empty slot, None when it cannot be read
    (no frame, or a digit the templates do not match)."""
    import dungeon_hunt as dh
    import hotbar_count as hb
    import numpy as np

    if frame is None:
        return {k: None for k in keys}
    g = hb.gray(np.asarray(frame)[:HOTBAR_ROWS])
    return {k: hb.read_count(g, dh.hotbar_slot(k), dict(tpl)) for k in keys}


class PixelIO(LiveIO):
    """The real game: ro_agent's Screen and Agent, the runner's own pixel readers."""

    def __init__(self) -> None:
        import dungeon_hunt as dh
        import gm_vitals as gv
        import hp_percent as hpp
        import numpy as np
        import ro_agent as r

        self.r, self.np, self.hpp, self.dead_state = r, np, hpp, gv.DEAD_STATE
        z = np.load(hpp.GLYPHS)  # the runner's own load (dungeon_hunt.run)
        self.glyphs = {("%" if k == "pct" else k[1:]): z[k] for k in z.files}
        self.refs = dh.load_map_refs()
        self.region = r.game_region()
        self.screen = r.Screen()
        self.agent = None
        self._w: int | None = None
        self._w_t = -1e9
        self._hb_tpl: dict[str, Any] | None = None  # the hotbar digits, loaded at the first read

    def ns(self) -> int:
        return int(self.r.ns())

    def frame(self) -> Any:
        img = self.r.grab_after(self.screen, self.region, self.r.ns())
        return self.np.ascontiguousarray(self.np.asarray(img)[..., :3])

    def senses(self) -> dict[str, Any]:
        import gm_state
        import minimap_id as mi

        img = self.frame()
        out: dict[str, Any] = {
            "hp_percent": self.hpp.read(img, self.glyphs),
            "sp_percent": self.hpp.read(img, self.glyphs, self.hpp.SP_DY),
            "is_dead": bool(self.r.is_state(self.screen, self.dead_state)),
            "map": None if self.refs is None else mi.read_map(img, self.refs).map,
        }
        if time.monotonic() - self._w_t >= WEIGHT_EVERY_S:
            share = gm_state.weight_share(gm_state._weight((img, self.frame())))
            self._w = None if share is None else int(round(share * 100))
            self._w_t = time.monotonic()
        out["weight_percent"] = self._w
        return out

    def open(self) -> None:
        self.agent = self.r.Agent("flow_play")
        self.agent.wait_for_human()

    def ui_clear(self) -> None:
        import ui_gate

        ui_gate.ensure_clear(self.agent, self.screen, why="flow-play-start")
        self.r.activate_client(self.agent, self.screen)  # verified in front (its title bar)

    def tap(self, code: str) -> None:
        self.agent.keys(code)  # down, 50 ms, up, 50 ms: the client takes a paced tap

    def hotbar_counts(self, frame: Any, keys: Sequence[str]) -> dict[str, int | None]:
        """The runner's own hotbar reader on the tick's frame; its digit templates are the
        client's pixels, loaded at RUN TIME from data/hotbar (never in git). Missing templates:
        no digit reads (a count is unknown), an empty slot still reads 0."""
        if self._hb_tpl is None:
            import hotbar_count as hb

            try:
                self._hb_tpl = hb.load()
            except (OSError, KeyError, ValueError):
                self._hb_tpl = {}
        return read_hotbar(frame, keys, self._hb_tpl)

    def release(self) -> None:
        if self.agent is not None:
            self.agent.send([{"type": "release_all", "t_mono_ns": self.r.ns(), "frame_id": -1}])

    def close(self) -> None:
        if self.agent is not None:
            self.agent.close()
        self.screen.close()


# --- the hunt core (dungeon_hunt in-process) ------------------------------------------------------
@dataclass
class HuntResult:
    reason: str | None = None  # the runner's run_end reason
    error: str | None = None  # it refused or stopped (its words)
    home: bool = False  # its player end pressed the Butterfly Wing
    respawned: bool = False
    dead: bool = False
    rc: int | None = None
    ticks: int = 0
    survive_calls: int = 0  # stage 2: the hook's survive calls (main ticks and quick reads)
    calls: int = 0  # stage 3: the hook's calls of the box's role functions
    recipes: int = 0  # stage 4a: the hook's recipe answers (one per target, at its lock)

    @property
    def left(self) -> bool:
        """It left the map by its own way (the wing home, the respawn)."""
        return self.home or self.respawned

    @property
    def ok(self) -> bool:
        r = self.reason or ""
        return self.error is None and (r == "time_box" or r.startswith(("weight_home",
                                                                        "stock_out",
                                                                        "stock_keep")))  # fmt: skip


class HuntHook:
    """The runner's TICK HOOK (dungeon@9.48) and its event mirror: the player's stop, read access
    to the runner's HUD values each tick, the runner's events into the player's own record."""

    def __init__(self, player: LivePlayer, res: HuntResult) -> None:
        self.player, self.res = player, res
        self.last: Any = None
        self._hp_t = -1e9

    def tick(self, view: Any) -> str | None:
        self.res.ticks += 1
        self.last = view
        return self.player.hunt_halt_words() or self.player.stop_due()

    def survive(self, view: Any, press: Callable[[str, str], str | None]) -> str | None:
        """dungeon@9.49: the box's survival events on this runner tick (LivePlayer.hunt_tick)."""
        self.res.survive_calls += 1
        return self.player.hunt_tick(view, press)

    def call(self, role: str, why: str, press: Callable[[str, str], str | None],
             click: Callable[[int, int, str], bool] | None = None) -> str | None:  # fmt: skip
        """dungeon@9.50: the box's function for a role, at the runner's moment (LivePlayer.
        hunt_call)."""
        self.res.calls += 1
        return self.player.hunt_call(role, why, press, click)

    def recipe(self, species: str | None, why: str) -> dict[str, Any] | None:
        """dungeon@9.51: the box's recipe for a target's species at the runner's lock (LivePlayer.
        hunt_recipe): the plan decided before any input, or None (the runner's own)."""
        self.res.recipes += 1
        return self.player.hunt_recipe(species, why)

    def event(self, rec: Mapping[str, Any], t_mono: float) -> None:
        k = rec.get("kind")
        if k == "run_end":
            self.res.reason = str(rec.get("reason") or "")
        elif k == "player_end":
            self.res.home = bool(rec.get("home"))
            self.res.respawned = bool(rec.get("respawned"))
            self.res.dead = bool(rec.get("dead"))
        if k == "hp_read":  # the live line's HP, once a second
            if t_mono - self._hp_t < HP_EVERY_S:
                return
            self._hp_t = t_mono
        elif k not in MIRROR:
            return
        out = dict(rec)
        if k in ("run_start", "run_end"):
            out["kind"] = f"hunt_{k}"
        self.player.rec.ev(out)


class HuntCore:
    """A dungeon_hunt block, played by the runner IN THIS PROCESS (one input writer)."""

    def __init__(self, label: str, stop_file: Path | None,
                 run_fn: Callable[..., int] | None = None,
                 args_fn: Callable[[Sequence[str]], Any] | None = None) -> None:  # fmt: skip
        self.label, self.stop_file = label, stop_file
        self.run_fn, self.args_fn = run_fn, args_fn
        self.n = 0

    def play(self, player: LivePlayer, plan: RunnerPlan) -> HuntResult:
        import dungeon_hunt as dh

        run_fn = self.run_fn or dh.run
        args_fn = self.args_fn or dh.args_for
        self.n += 1
        left_min = (player.cap_s - player.t) / 60.0
        res = HuntResult()
        if left_min < 1.0:
            res.error = "under a minute of the time box left: the hunt core does not start"
            return res
        argv = plan.argv(f"{self.label}-hunt{self.n}", self.stop_file, left_min)
        box = plan.box_kwargs()  # stage 2-4a: only what the box plays (none: the CLI's run)
        player.rec.ev({"kind": "hunt_start", "node": player.node_path, "n": self.n,
                       "flow": plan.flow_id, "keys": plan.keys, "argv": argv,
                       "events": list(plan.events), "box_plays": sorted(plan.plays),
                       **({"box_eat": box["box_eat"]} if "box_eat" in box else {}),
                       **({"hotbar_keys": list(plan.hotbar_keys)} if plan.hotbar_keys else {}),
                       **({"box_model": box["box_model"]["id"]} if "box_model" in box else {}),
                       **({"box_recipes": box["box_recipes"],
                           "default_species": list(plan.default_species)}
                          if "box_recipes" in box else {})})  # fmt: skip
        hook = HuntHook(player, res)
        try:
            a = args_fn(argv)
            res.rc = run_fn(a, hook=hook, session=(player.io.agent, player.io.screen), **box)
        except SystemExit as e:  # its preamble's refusal, or ro_agent.Stop inside its session
            res.error = str(e)[:400] or "the runner stopped"
        player.rec.ev({"kind": "hunt_end", "n": self.n, "reason": res.reason, "error": res.error,
                       "home": res.home, "respawned": res.respawned, "dead": res.dead,
                       "ticks": res.ticks, "survive_calls": res.survive_calls,
                       "calls": res.calls, "recipes": res.recipes, "rc": res.rc})  # fmt: skip
        return res


# --- the live runtime -----------------------------------------------------------------------------
class LivePlayer(Sim):
    """runtime.Sim with the live environment (the module docstring): its seams `_advance` (the
    real clock, paced, then a fresh sensor read), `_waited` (real seconds), `_guard` (Stop, the
    time box) and `Relocate`; its actions, exits, relocation and safety built-ins bound live."""

    def __init__(self, prep: Prepared, lio: LiveIO, log: SessionLog, *,
                 stop_file: Path | None, hunt: HuntCore | None) -> None:  # fmt: skip
        super().__init__(prep.flow, world={}, max_ticks=10**9)
        self.prep, self.c, self.io, self.rec = prep, prep.compiled, lio, log
        self.stop_file, self.hunt = stop_file, hunt
        self.block = prep.node
        self.cap_s = prep.cap_s
        self.paths: dict[int, str] = {}
        for site in ir.sites(self.flow):
            self.paths[id(site.stmt)] = self.c.where(site.path).path
            for a in ir.actions_in(site.stmt):
                self.paths.setdefault(id(a), self.c.where(site.path).path)
        self.node_path = ""
        self.words: str | None = None  # the end in a player's words, when a block gave them
        self.flow_stop: str | None = None  # a stop statement's reason, when one ended the run
        self.keys_sent: list[str] = []
        self._t0 = lio.clock()
        self._next = self._t0
        self._expect_until = -1.0
        self._map_before: str | None = None
        self._last_block: tuple[str, float] = ("", -1e9)
        self._hp_t = -1e9
        # stage 2: the box's events inside a running hunt core (hunt_tick)
        self._port: Callable[[str, str], str | None] | None = None  # the runner's own press
        self._hunt_keys: frozenset[str] = frozenset()  # the events that play in the hunt core
        self._hunt_weight: frozenset[str] = frozenset()  # stage 3: those on the weight read
        self._hunt_halt: _Halt | None = None  # one of them ended the run (its words: words)
        self._playing: str | None = None  # the event whose body plays now (its key)
        self._readings: dict[str, dict[str, Any]] = {}  # event key -> the reading that fired it
        # 2026-11-14: hotbar_count inside the hunt core -- the keys it reads, each one's last read
        self._hunt_hotbar: tuple[str, ...] = ()
        self._hotbar_t: dict[str, float] = {}

    # -- the clock and the sensors --
    def stop_due(self) -> str | None:
        """Why the run must end now (None: it goes on): Stop pressed, or the time box over."""
        if self.stop_file is not None and self.stop_file.exists():
            return "Stop pressed"
        if self.io.clock() - self._t0 >= self.cap_s:
            return "the time box ended"
        return None

    def read(self) -> None:
        v = self.io.senses()
        changes = {k: v.get(k) for k in ("hp_percent", "sp_percent", "weight_percent")}
        changes["is_dead"] = v.get("is_dead")
        m = v.get("map")
        if m is not None and m != self.world.get("map"):
            changes["map"] = m
        if self.expect_map_change:
            cause = "exit"
        elif self.t < self._expect_until:
            cause = "expected"
        else:
            cause = "world"
        self._set(changes, cause)
        if self.t - self._hp_t >= HP_EVERY_S:
            self._hp_t = self.t
            hp = self.world.get("hp_percent")
            w = self.world
            self.rec.ev({"kind": "hp_read", "pct": hp, "sp_pct": w.get("sp_percent"),
                         "weight_pct": w.get("weight_percent"), "dead": w.get("is_dead"),
                         "map": w.get("map")})  # fmt: skip

    def start_world(self, map_: str) -> None:
        """The start's own read: the map the start check read, no change seen."""
        self.world["map"] = map_
        self.read()
        self.world["map_load_seen"] = False
        self.world.pop("_map_cause", None)

    def _apply_timeline(self) -> None:  # the sensors are read in _advance (each tick, fresh)
        return

    def _advance(self, dt: float) -> None:
        self._next += dt
        now = self.io.clock()
        if self._next > now:
            self.io.sleep(self._next - now)
        else:
            self._next = now  # an overrun tick is not caught up in a burst
        self.t = self.io.clock() - self._t0
        if self._port is None:  # inside the hunt core the runner's tick is the reading (stage 2)
            self.read()

    def _waited(self, waited: float, t_start: float) -> float:
        return self.t - t_start

    def _guard(self) -> None:
        why = self.stop_due()
        if why is None:
            return
        if why == "Stop pressed" and self.stack and self.stack[-1].atomic:
            return  # an atomic section ends first (2.5 rule 5)
        raise _Halt("stopped" if why == "Stop pressed" else "max_runtime")

    # -- input: every batch through the ONE agent --
    def _emit(self, owner: str, events: list[Any], why: str) -> None:
        super()._emit(owner, events, why)
        only_release = all(isinstance(e, ReleaseAll) for e in events)
        try:
            i = 0
            while i < len(events):
                e = events[i]
                nxt = events[i + 1] if i + 1 < len(events) else None
                if isinstance(e, ReleaseAll):
                    self.io.release()
                    self.rec.ev({"kind": "release", "why": why})
                elif (isinstance(e, Key) and e.action == "down" and isinstance(nxt, Key)
                      and nxt.action == "up" and nxt.code == e.code):  # fmt: skip
                    rec: dict[str, Any] = {"kind": "key", "key": e.code, "node": self.node_path}
                    if self._port is not None:  # stage 2, inside the hunt core: the runner's OWN
                        # press of that role (its record, count and stock read; mirrored to ours)
                        if self._port(e.code, self._box_why()) is None:
                            self.words = (f"the box pressed {e.code} inside the hunt core: a key "
                                          "the hunt core does not hand the box")  # fmt: skip
                            raise _Halt("not_live_input")
                        rec["in"] = "hunt"
                    else:
                        self.io.tap(e.code)
                        if e.code in self.prep.roles:  # the live line's words (PRESS_DOING)
                            self.rec.ev({"kind": "press", "what": self.prep.roles[e.code],
                                         "key": e.code})  # fmt: skip
                    self.keys_sent.append(e.code)
                    self.rec.ev(rec)
                    i += 1
                else:
                    raise _Halt("not_live_input")
                i += 1
        except SystemExit as e:  # ro_agent.Stop: the mux refused (mode, lease, gate, interlock)
            if only_release:
                self.rec.ev({"kind": "release_failed", "why": str(e)[:300]})
                return
            if self._port is not None:
                raise  # inside the hunt core: the runner's own Stop handling (its session ends)
            self.words = f"the input was refused: {str(e)[:300]}"
            raise _Halt("input_refused") from None

    # -- the statements: their node paths --
    def _reason_of(self, st: Any, owner: str) -> str:
        return self.paths.get(id(st)) or owner

    def _stmt(self, st: Any, owner: str) -> Generator[_Tick, str | None, str]:
        path = self.paths.get(id(st))
        if path:
            self.node_path = path
            last, at = self._last_block
            if path != last or self.t - at >= BLOCK_LOG_S:
                what = st.block if isinstance(st, ir.ActionStmt) else st.kind
                if isinstance(st, ir.WaitUntil) and isinstance(st.cond, ir.Lit):
                    what = "wait"
                self.rec.ev({"kind": "block", "node": path, "what": what,
                             "by": self.c.where(owner).path or owner})  # fmt: skip
            self._last_block = (path, self.t)
        if isinstance(st, ir.Stop):
            self.words = f'the flow stopped at {path or owner} (stop "{st.reason}")'
            self.flow_stop = st.reason
        return (yield from super()._stmt(st, owner))

    def _action(self, a: ir.ActionStmt, owner: str) -> Generator[_Tick, str | None, str]:
        for e in a.params.values():  # a parameter that is a function's value runs first
            if any(isinstance(x, ir.CallV) for x in ir.sub_exprs(e)):
                yield from self._pre(e, owner, {})
        if a.block == fn.PRESS:
            while True:
                key = self.key(a)
                if key not in self.hotbar:
                    return "failed"  # a key off the hotbar sends nothing (as the simulator)
                ns = self.io.ns()
                sent = yield _Tick(
                    [
                        Key(t_mono_ns=ns, code=key, action="down"),
                        Key(t_mono_ns=ns, code=key, action="up"),
                    ],
                    False,
                    fn.PRESS,
                )
                if sent == "restart":
                    continue
                if sent == "fail":
                    return "failed"
                break
            yield _Tick(None, False, "press_key check")
            if key in self.wing_keys and not self.in_exit_function:  # a Butterfly Wing's key
                self._map_before = self.world.get("map")
                self._expect_until = self.t + EXPECT_S
            return "ok"
        if a.block == "assert_save_point":  # the author's assertion: no input
            yield _Tick(None, False, "assert_save_point")
            return "ok"
        if a.block == rc.MODEL_BLOCK:  # stage 4a: the hunt core's model (no input; prepared)
            yield _Tick(None, False, rc.MODEL_BLOCK)
            return "ok"
        if a.block == fn.RUNNER_BLOCK:
            return (yield from self._hunt_core())
        raise _Halt(f"not_live_{a.block}")  # never: prepare() refused it before any input

    def _hunt_core(self) -> Generator[_Tick, str | None, str]:
        yield _Tick(None, False, "dungeon_hunt")  # a safe point before the runner takes over
        plan = self.prep.runners.get(self.block)
        if self.hunt is None or plan is None:
            self.words = f"no runner for {self.block}"
            return "failed"
        self._hunt_keys = frozenset(plan.events)  # stage 2: they play through its tick hook
        self._hunt_weight = frozenset(plan.weight_events)  # stage 3: on its weight read only
        self._hunt_hotbar, self._hotbar_t = plan.hotbar_keys, {}  # 2026-11-14: from its frames
        try:
            res = self.hunt.play(self, plan)
        finally:
            self._hunt_keys = self._hunt_weight = frozenset()
            self.world["sees_boss"] = None  # the runner's boss read: unknown outside it
            for k in self._hunt_hotbar:  # hotbar_count: unknown outside it too
                self.world[hotbar_world_key(k)] = None
            self._hunt_hotbar = ()
        self._next = self.io.clock()
        self.t = self.io.clock() - self._t0
        if res.left:  # its own map exit: the map change it made is expected
            self._map_before, self._expect_until = self.world.get("map"), self.t + EXPECT_S
        self.read()
        if self._hunt_halt is not None:  # a box event ended it (the runner's normal end ran)
            halt, self._hunt_halt = self._hunt_halt, None
            if res.home and self.words:  # stage 3: the weight home's stop, then the way home
                self.words = f"{self.words}; the hunt core flew her home"
            raise halt
        if res.error is not None:
            self.words = f"the hunt core ended: {res.error}"
            return "failed"
        why = self.stop_due()
        here = self.world.get("map")
        if why == "Stop pressed":
            raise _Halt("stopped")
        if res.dead or res.reason == "death":
            by = (f"the box's {plan.call_names['respawn']}()" if "respawn" in plan.calls
                  else "the runner")  # fmt: skip
            self.words = (f"she died in the hunt; {by} pressed her respawn at the save point"
                          if res.respawned else "she died in the hunt: the death dialog is a "
                          "person's (the respawn did not arrive)")  # fmt: skip
            raise _Halt("dead")
        if why is not None:  # the time box: the runner's own end ran (a player's way home)
            self.words = "the hunt core flew her home" if res.home else None
            raise _Halt("max_runtime")
        if res.left:  # its own map exit: the run follows her by the map's name
            raise Relocate()
        if here is not None and here != self.tree.blocks[self.block].map.map:
            self.words = f"after the hunt core the minimap reads {here}, not the node's map"
            raise _Halt("unexpected_map")
        if not res.ok:
            self.words = f"the hunt core ended: {res.reason}"
        yield _Tick(None, False, "dungeon_hunt check")
        return "ok" if res.ok else "failed"

    # -- exits and relocation: by the map's NAME (the minimap) --
    def _exit(self, x: ir.Exit, owner: str) -> Generator[_Tick, str | None, None]:
        if x.kind != "item_warp" or x.proc is None:
            raise _Halt(f"not_live_{x.kind}")  # never: prepare() refused it
        to = self.tree.blocks[x.to_block]
        want = to.map.map
        self.expect_map_change = True
        try:
            self.in_exit_function = True
            try:
                yield from self._call(x.proc, [], {}, owner)
            finally:
                self.in_exit_function = False
            t0 = self.t
            while self.world.get("map") != want:
                if self.t - t0 >= x.timeout_s:
                    self.words = (f"the item warp to {to.name} did not arrive: the minimap reads "
                                  f"{self.world.get('map')} after {x.timeout_s:.0f} s")  # fmt: skip
                    raise _Halt("exit_not_arrived")
                yield _Tick(None, False, "take_exit arrival")
            self.block = to.name
            self.log.append((self.t, "block", to.name))
            self.log_block(to.name, "exit")
        finally:
            self.expect_map_change = False

    def log_block(self, block: str, how: str) -> None:
        self.rec.ev({"kind": "map_node", "node": block, "how": how, "map": self.world.get("map")})

    def _settled_map(self) -> str | None:
        """The map the minimap names, waiting (no input) up to SETTLE_S for a name -- and, after
        a Butterfly Wing's press, for another map than the one before it."""
        end = self.io.clock() + SETTLE_S
        pending = self.t < self._expect_until
        while True:
            m = self.world.get("map")
            if m is not None and not (pending and m == self._map_before):
                return str(m)
            if self.io.clock() >= end or self.stop_due() is not None:
                return None if m is None else str(m)
            self.io.sleep(SETTLE_POLL_S)
            self.t = self.io.clock() - self._t0
            self.read()

    def _relocate(self) -> None:
        m = self._settled_map()
        target = self._resume_block(m, None)
        if target is None:
            self.words = (f"she is on {m}: no map node of the project plays there, so the run "
                          "ends" if m else "the minimap names no map: the run ends")  # fmt: skip
            raise _Halt("relocate_no_block")
        self.block = target
        self.log.append((self.t, "relocate", target))
        self.log_block(target, "relocate")
        self.stack.append(_Frame("main", MAIN_RANK, self._main_gen(target)))

    # -- events --
    def _fire(self, e: Any) -> None:
        super()._fire(e)
        reading = self._reading_of(e)
        self._readings[e.key] = reading
        self.rec.ev({"kind": "event", "event": e.key, "mode": e.handler.mode,
                     "node": self.c.where(e.label).path or e.label, "reading": reading,
                     **({"in": "hunt"} if self._port is not None else {})})  # fmt: skip

    def _reading_of(self, e: Any) -> dict[str, Any]:
        """The values its conditions read when it fired (the record; the press's why); a
        hotbar_count read as "hotbar_count(F6)" (2026-11-14)."""
        h = e.handler
        conds = [c for c in (h.when, h.until, h.rearm) if c is not None]
        names = sorted({x.sensor for c in conds for x in ir.sub_exprs(c)
                        if isinstance(x, ir.Sense) and not x.args
                        and x.sensor not in live.HELPER_SENSORS})  # fmt: skip
        world_key = {"current_map": "map", "position": "cell"}
        out = {n: self.world.get(world_key.get(n, n)) for n in names}
        hot = sorted({k for c in conds for x in ir.sub_exprs(c)
                      if (k := fn.hotbar_key(x)) is not None})  # fmt: skip
        out.update({f"{fn.HOTBAR_SENSOR}({k})": self.world.get(hotbar_world_key(k)) for k in hot})
        return out

    def _box_why(self) -> str:
        """A box press's why in the runner's record: "box fly_away (hp_percent 80, sees_boss
        True)" -- the event and the reading that fired it."""
        key = self._playing or "?"
        shown = ", ".join(f"{k} {v}" for k, v in (self._readings.get(key) or {}).items())
        return f"box {key}" + (f" ({shown})" if shown else "")

    def _play_sync(self, e: Any, gen: Generator[_Tick, str | None, str]) -> str:
        saved, self._playing = self._playing, e.key
        try:
            return super()._play_sync(e, gen)
        finally:
            self._playing = saved

    # -- stage 2: the box's events INSIDE the hunt core (its tick hook) --
    def hunt_tick(self, view: Any, press: Callable[[str, str], str | None]) -> str | None:
        """One runner tick (dungeon_hunt.HuntTick; the module docstring): the box's sensors from
        it, its events by the engine's rules, every due body played NOW through ``press``. None:
        the runner goes on; words: the run ends (the runner's normal end)."""
        if self._hunt_halt is not None:
            return self.hunt_halt_words()
        w = getattr(view, "weight_pct", None)
        if w is not None:  # stage 3: the runner's weight read (its UI watch): the weight events
            return self._weight_tick(int(w), press)
        keys = self._hunt_keys - self._hunt_weight
        if not keys:
            return None
        boss = None if view.quick else view.boss is not None  # quick: no Battle Log read
        vitals = view.hp_pct is not None or bool(boss)
        self.t = self.io.clock() - self._t0
        read = self._hotbar_read(getattr(view, "frame", None))  # 2026-11-14: from its frame
        if not vitals and not read:
            return None  # nothing to decide on: no HP read, no boss line, no hotbar count
        changes: dict[str, Any] = {}
        if vitals:
            changes.update({"hp_percent": view.hp_pct, "sp_percent": view.sp_pct,
                            "sees_boss": boss})  # fmt: skip
            if not view.quick:
                changes["is_dead"] = bool(view.dead)
        changes.update({hotbar_world_key(k): v for k, v in read.items()})
        self._set(changes, "world")
        node_path, self._port = self.node_path, press
        try:
            for e in self._perceive(lambda x: x.key in keys and self._decides(x, vitals)):
                self._fire(e)
            self._preempt_now(keys)
            self._run_inserts()
        except _Halt as h:
            self._hunt_halt = h
            return self.hunt_halt_words()
        finally:
            self._port, self.node_path = None, node_path
        return None

    def _hotbar_read(self, frame: Any) -> dict[str, int | None]:
        """2026-11-14: the hotbar keys due a read on this tick (each at most every HOTBAR_EVERY_S;
        between reads the world keeps the last value), read from the tick's frame. {}: none due,
        or no frame."""
        if not self._hunt_hotbar or frame is None:
            return {}
        due = [k for k in self._hunt_hotbar
               if self.t - self._hotbar_t.get(k, -1e9) >= HOTBAR_EVERY_S]  # fmt: skip
        if not due:
            return {}
        for k in due:
            self._hotbar_t[k] = self.t
        return dict(self.io.hotbar_counts(frame, due))

    def _decides(self, e: Any, vitals: bool) -> bool:
        """May the event be evaluated on this hunt tick: an event that reads HP, SP or the boss
        needs a tick that carries them (stage 2's rule); one that reads hotbar_count needs every
        slot it reads known (an unreadable count never fires it, and a repeating one pauses)."""
        h = e.handler
        conds = [c for c in (h.when, h.until, h.rearm) if c is not None]
        reads = set().union(set(), *(_sense_names(c) for c in conds))
        hot = {k for c in conds for x in ir.sub_exprs(c) if (k := fn.hotbar_key(x)) is not None}
        if any(self.world.get(hotbar_world_key(k)) is None for k in hot):
            return False
        return vitals or (bool(hot) and not reads & set(live.VITAL_SENSORS))

    def _weight_tick(self, w: int, press: Callable[[str, str], str | None]) -> str | None:
        """Stage 3: the weight read of the runner's UI watch -- only the WEIGHT events are
        evaluated (its own moment, never mid-fight), and a due one plays now (a pre-empt: its
        stop ends the run, the runner's normal end flies her home). No insert plays here."""
        keys = self._hunt_weight
        if not keys:
            return None
        self.t = self.io.clock() - self._t0
        self._set({"weight_percent": w}, "world")
        node_path, self._port = self.node_path, press
        try:
            for e in self._perceive(lambda x: x.key in keys):
                self._fire(e)
            self._preempt_now(keys)
        except _Halt as h:
            self._hunt_halt = h
            return self.hunt_halt_words()
        finally:
            self._port, self.node_path = None, node_path
        return None

    def hunt_call(self, role: str, why: str, press: Callable[[str, str], str | None],
                  click: Callable[[int, int, str], bool] | None = None) -> str | None:  # fmt: skip
        """Stage 3: the box's function for ``role`` at the runner's moment (the module docstring):
        its steps NOW -- a press through ``press`` (the runner's own press of a key of this
        moment), a click through ``click`` (the death exit's), a wait slept exactly -- while the
        runner waits. None: played; words: it could not (the runner records it and ends the run
        normally). It plays during the runner's normal end too (the swap back, the way home),
        after a box event ended the run."""
        plan = self.prep.runners.get(self.block)
        steps = None if plan is None else plan.calls.get(role)
        if plan is None or steps is None:
            return f"the box has no function for the hunt core's {role}"
        name = plan.call_names[role]
        path = self.c.where(name).path or name
        tag = f"box {name} ({why})"
        self.rec.ev({"kind": "call", "role": role, "function": name, "why": why, "node": path,
                     "in": "hunt", "steps": [x.doc() for x in steps]})  # fmt: skip
        for st in steps:
            if st.kind == "wait":
                self.io.sleep(st.s)
            elif st.kind == "press":
                assert st.key is not None
                if press(st.key, tag) is None:
                    return (f"the box's {name} pressed {st.key} at the hunt core's {role}: a key "
                            "it does not hand the box there")  # fmt: skip
                self.keys_sent.append(st.key)
                self.rec.ev({"kind": "key", "key": st.key, "node": path, "in": "hunt"})
            else:
                if click is None or not click(st.x, st.y, tag):
                    return (f"the box's {name} clicked at {st.x}, {st.y} at the hunt core's "
                            f"{role}: a click it does not take there")  # fmt: skip
                self.rec.ev({"kind": "click", "at": [st.x, st.y], "node": path, "in": "hunt"})
        return None

    def hunt_recipe(self, species: str | None, why: str) -> dict[str, Any] | None:
        """Stage 4a: the box's recipe for a target's species at the runner's LOCK (the module
        docstring) -- its plan, decided before any input; the runner plays its steps with its own
        code. None: the runner's own recipe (no function for that species, or unknown). Recorded
        once per target (`recipe`: the species, the function, its node path, its steps)."""
        plan = self.prep.runners.get(self.block)
        r = None if plan is None or species is None else plan.recipes.get(species)
        rec: dict[str, Any] = {"kind": "recipe", "species": species, "why": why, "in": "hunt"}
        if r is None:
            self.rec.ev({**rec, "function": None, "default": True})
            return None
        self.rec.ev({**rec, "function": r.function, "node": self.c.where(r.function).path
                     or r.function, "steps": list(r.steps), "knife": r.knife})  # fmt: skip
        return dict(r.doc())

    def _preempt_now(self, keys: frozenset[str]) -> None:
        """The box's due PRE-EMPTS, each played to its end now (the runner it suspends is between
        two of its own steps), in the queue's order: a ReleaseAll before its first batch (2.5 rule
        4); `then` resume (live.hunt_plan refuses any other)."""
        while True:
            self.queue.sort()
            i = next((j for j, q in enumerate(self.queue) if q[-1] in keys), None)
            if i is None:
                return
            e = self._event(self.queue.pop(i)[-1])
            if e is None:
                continue
            self._release(f"pre-empt by {e.key}")
            self.preempts.append((len(self.out) - 1, e.label))
            self._st(e.key).runs.append(self.t)
            self.log.append((self.t, "preempt", e.key))
            out = self._play_sync(e, self._handler_gen(e))
            if out != "ok":
                raise _Halt(out)

    def hunt_halt_words(self) -> str | None:
        """Why a box event ends the run inside the hunt core (None: none did)."""
        h = self._hunt_halt
        if h is None:
            return None
        if not self.words:
            self.words = HUNT_HALT_WORDS.get(h.reason, f"a box event stopped the run ({h.reason})")
        return f"the box: {self.words}"

    def _handler_gen(self, e: Any) -> Generator[_Tick, str | None, str]:
        if e.built_in:  # stage 1: the always-on safety events play as the SAFE END
            self.words = BUILT_IN_WORDS.get(e.key, f"{e.key}: the run ends")
            raise _Halt(e.key)
        return (yield from super()._handler_gen(e))


HUNT_HALT_WORDS = {
    "handler_runaway": "an event fired more often than its max_fires_per_10min without its stop "
                       "holding, inside the hunt core: the run ends",
    "insert_failed": "an inserted event failed inside the hunt core: the run ends",
}  # fmt: skip
BUILT_IN_WORDS = {
    "dead": "she died: the run ends and the death dialog is a person's (outside a hunt core the "
            "respawn is a later stage)",
    "hp_critical": "her HP fell under 20 %: the run ends (the escape plays live in stage 2)",
    "unexpected_map": "the minimap named another map, not by one of the project's exits: the run "
                      "ends (a person looks)",
}  # fmt: skip


def end_words(end: str, words: str | None, elapsed_s: float, flow_stop: str | None = None) -> str:
    """PURE: the end in a player's words (the page's end line; matpilot 2026-11-13)."""
    mins = int(elapsed_s // 60)
    head = {"stopped": "Stopped by you", "max_runtime": "The time box ended",
            "done": "The flow ended (its main finished)"}.get(end)  # fmt: skip
    if head is None:
        head = "The flow stopped" if flow_stop is not None and end == flow_stop else f"Ended: {end}"
    w = (words or "").strip().rstrip(".")
    return f"{head} after {mins} min." + (f" {w[0].upper()}{w[1:]}." if w else "")


# --- the start check (reads only: no input path is open yet) --------------------------------------
def runner_check(plan: RunnerPlan, *, run_fn: Callable[..., int] | None = None) -> dict[str, Any]:
    """The runner's own read-only start check (dungeon@9.45/9.46), IN-PROCESS under its no-input
    guard (ro_agent's Agent and session refuse while it runs; restored after), its argv the hunt
    core's: the same lines the Run helper's check ticks."""
    import dungeon_hunt as dh
    import ro_agent as r

    saved = (r.Agent, r.session)
    buf = io.StringIO()
    try:
        dh.no_input_guard()
        a = dh.args_for(plan.argv(CHECK_LABEL, None, None), cmd="check")
        with contextlib.redirect_stdout(buf):
            try:
                (run_fn or dh.run)(a)
            except SystemExit as e:
                print(f"refused: {e}")
    finally:
        r.Agent, r.session = saved  # type: ignore[misc]
    sys.stdout.write(buf.getvalue())
    return fr.parse_check_output(buf.getvalue())


def generic_check(lio: PixelIO, map_: str) -> dict[str, Any]:
    """No hunt core on the start node: identity (the name plate and the job, no DB), the chat
    input closed and the map's name read as the node's map -- the runner's own functions."""
    import crusader as cr
    import dungeon_hunt as dh

    conf = dh.CHARS_CONF["rogue"]  # flow_run.FIXED's character (the lab's Rogue)
    items: list[dict[str, Any]] = []
    got = cr.check(lio.screen, conf["job"], conf.get("data", "rogue"), db=False)
    items.append(dh.check_item("identity", bool(got.get("ok")),
                               "the name plate and the job read hers" if got.get("ok")
                               else f"identity: {got.get('why')}"))  # fmt: skip
    m_read = dh.read_start_map(lio.frame, lio.refs, dh.PLAYER_MAP_S)
    ok, words = dh.player_map_verdict(map_, m_read, lio.refs)
    items.append(dh.check_item("cell", ok, words, None if m_read is None else m_read.map))
    is_open = bool(lio.r.is_state(lio.screen, "chat_open"))
    why = dh.player_chat_refused(is_open, "now")
    items.append(dh.check_item("chat", why is None, why or "the chat input is closed"))
    return {"items": items, **dh.check_verdict(items)}


def check_refusal(got: Mapping[str, Any]) -> str | None:
    """PURE: why the start check refuses the run (None: it may start). Any failed line the runner
    refuses on, and the map line not READ as the node's map (a person places her there)."""
    items = list(got.get("items") or [])
    if not items:
        return str(got.get("detail") or "the start check read nothing")
    bad = [i for i in items if i.get("ok") is False and i.get("refuses", True)]
    if bad:
        return "; ".join(f"{i.get('id')}: {i.get('words')}" for i in bad)
    cell = next((i for i in items if i.get("id") == "cell"), None)
    if cell is None or cell.get("ok") is not True:
        return f"her map is not read as the start node's: {cell.get('words') if cell else '-'}"
    return None


# --- play -----------------------------------------------------------------------------------------
def play(prep: Prepared, lio: LiveIO, *, label: str, stop_file: Path | None,
         demo: Path = DEMO, checker: Callable[[Prepared, LiveIO], dict[str, Any]] | None = None,
         hunt: HuntCore | None = None) -> int:  # fmt: skip
    """The run: the start check (reads), the input path, the UI gate, the runtime, the end.
    0: it played and ended; 2: refused before any input."""
    checker = checker or default_checker
    got = checker(prep, lio)
    why = check_refusal(got)
    if why is not None:
        print(refuse(f"the start check: {why}"), flush=True)
        return 2
    if stop_file is not None and stop_file.exists():
        print(refuse("Stop was pressed before the start"), flush=True)
        return 2
    log = SessionLog(demo, label, lio.ns)
    player: LivePlayer | None = None
    end, words = "failed", None
    try:
        lio.open()  # the ONE input path (refuses unless ASSIST and the lock is steady)
        lio.ui_clear()
        player = LivePlayer(prep, lio, log, stop_file=stop_file,
                            hunt=hunt or HuntCore(label, stop_file))  # fmt: skip
        log.ev({"kind": "run_start", "player": "flow_play", "version": VERSION,
                "project": prep.project.name, "project_hash": prep.project_hash,
                "node": prep.node, "map": prep.map, "cap_s": prep.cap_s,
                "check": {"ok": got.get("ok"), "items": got.get("items")},
                "runners": {b: p.flow_id for b, p in prep.runners.items()}})  # fmt: skip
        player.start_world(prep.map)
        end = player.run()
        words = player.words
    except SystemExit as e:  # ro_agent.Stop outside a block (the Agent, the UI gate, a grab)
        end, words = "input_refused", f"stopped by the input path or the screen: {str(e)[:300]}"
        with contextlib.suppress(BaseException):
            lio.release()
    except Exception as e:  # noqa: BLE001 -- a fault: release, record, end (never a silent stop)
        end, words = "error", f"{type(e).__name__}: {str(e)[:300]}"
        with contextlib.suppress(BaseException):
            lio.release()
    except KeyboardInterrupt:
        end, words = "stopped_by_parent", "the helper ended it (Stop's grace passed)"
        with contextlib.suppress(BaseException):
            lio.release()
        raise
    finally:
        elapsed = 0.0 if player is None else player.t
        text = end_words(end, words, elapsed, None if player is None else player.flow_stop)
        log.ev({"kind": "run_end", "reason": end, "words": text,
                "keys": [] if player is None else player.keys_sent})  # fmt: skip
        log.close()
        print(f"flow_play: {text}", flush=True)
        lio.close()
    return 0


def default_checker(prep: Prepared, lio: LiveIO) -> dict[str, Any]:
    plan = prep.runners.get(prep.node)
    if plan is not None:
        return runner_check(plan)
    assert isinstance(lio, PixelIO)
    return generic_check(lio, prep.map)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("play", "plan"):
        p = sub.add_parser(name)
        p.add_argument("--project", required=True, type=Path)
        p.add_argument("--node", required=True)
        p.add_argument(
            "--max-s",
            type=int,
            default=None,
            help="the Settings page's maximum run time (the run-start check's)",
        )
        p.add_argument("--project-hash", default=None, help="the hash the backend checked")
        p.add_argument(
            "--runner-config",
            type=Path,
            default=None,
            help="the helper's resolved runner settings, {block: values}",
        )
        if name == "play":
            p.add_argument("--label", required=True)
            p.add_argument("--stop-file", type=Path, default=None)
    a = ap.parse_args(argv)
    rv = json.loads(a.runner_config.read_text()) if a.runner_config else None
    prep = prepare(a.project.read_text(), a.node, a.max_s, runner_vals=rv,
                   want_hash=a.project_hash)  # fmt: skip
    if isinstance(prep, str):
        print(prep, flush=True)
        return 2
    if a.cmd == "plan":
        print(json.dumps(prep.doc(), indent=1))
        return 0
    os.environ.setdefault("TMPDIR", "/dev/shm/poring-lab-tmp")
    return play(prep, PixelIO(), label=a.label, stop_file=a.stop_file)


if __name__ == "__main__":
    raise SystemExit(main())
