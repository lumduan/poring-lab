#!/usr/bin/env python3
"""live-blocks 5b-2 (docs/planning/live-blocks.md 13.4 and 14): THE STEP-TRACE EQUIVALENCE --
run()'s own driver against the box's hunt loop played as blocks, on SCRIPTED mode changes.

The box's canonical loop (services/frontend/src/lib/flow/fixtures/project_xmas_dun02_hunt.json, its
tab hunt)

    def hunt_loop(t):
        while True:
            t = find_target()
            fight_target(t)         # the monsters tab's recipe for t's species (today's: the Knife)

must call EXACTLY the step sequence run()'s driver loop calls, tick for tick. Both play the same
FAKE hunt: 20 step closures with the real steps' names, order and MODE SEMANTICS (the guards the
real steps have, which `huntstate_check.py drive` proves on the committed code: the fight step
acts only in mode fight and then ends the tick; the loot step only in mode after; the hold step
ends the tick on a lock or a fight; after turns after into search), whose effects -- an engage, a
lock, the steal's cue, a kill, the fight's end, a loot step's fight, a box Fly Wing, a rest, a
walk-sword engage that does NOT end its tick, a RUN_END, the run's time box -- are drawn from the
scenario's seed for each (tick, step, mode), so the same call in the same state has the same
effect in both runs. Then:

- A (the driver): run()'s loop exactly (`while clock() < t_end: if hunt_tick() == RUN_END: break`);
- B (the blocks): dungeon_hunt.HuntCursor over the same steps, driven by the REAL live player
  (flow_play.LivePlayer.hunt_drive) playing the fixture's hunt_loop -- the engine's interpreter,
  find_target / fight_target / the recipe dispatch at the lock (the fake lock asks the player's
  hunt_recipe as run() does);

and the two traces of (tick, step, signal) must be equal, with no step PASSED in B.

    hunt_trace.py check [--seeds N] [--project F]    every hand scenario + N random ones; rc 1 on a
                                                     difference (each one printed)

ITS LIMITS (what it does not show; the live A/B of section 14 is their check):
- the fake steps model the MODE SEMANTICS only, not the real steps' bodies, reads or input; that
  the real steps keep those semantics is huntstate_check.py drive's proof (the guards), and that
  run() without a drive is 5b-1's program is its AST identity;
- the box's survival events are not played (the fake survive step calls no hook): they play inside
  the common steps, which every block runs, so they cannot change which steps run;
- the clock is simulated (each step 10 ms, pace 200 ms); the cost of the player's interpreter
  between steps is not measured here (the A/B's tick pace line is);
- equal traces mean the same steps in the same order in the same ticks: with the same world the
  same program; a live run's world (frames, the server) differs between any two runs anyway.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
for _p in ("packages/poring_flow/src", "packages/poring_skills/src", "packages/poring_env/src"):
    if str(ROOT / _p) not in sys.path:
        sys.path.append(str(ROOT / _p))

import dungeon_hunt as dh  # noqa: E402

FIX = ROOT / "services/frontend/src/lib/flow/fixtures"
PROJECT = FIX / "project_xmas_dun02_hunt.json"
# live-blocks 5c (15.7): the ready-made box as functions in tabs -- hunt_loop() in main, its role
# blocks, the full hunt_tick(): the same hunt core, so the same steps
FUNCTIONS = FIX / "project_xmas_dun02_functions.json"
NODE = "xmas_dun02"
STEP_S, PACE_S = 0.01, 0.2  # the simulated cost of a step and of the pace sleep
SPECIES = ("mystcase", "cruiser", "cookie", "cookie_xmas")


@dataclass
class Scenario:
    """A scripted hunt: ``rates`` -- the chance of each effect, per (tick, step) where it may happen
    -- drawn from ``seed`` (a hash of seed, tick, step and mode: the same call in the same state
    has the same effect in both runs); ``script`` -- (tick, step) -> an effect name that happens
    there (hand scenarios); ``minutes`` -- the run's time box (t_end)."""

    name: str
    seed: int = 0
    minutes: float = 2.0
    rates: dict[str, float] = field(default_factory=dict)
    script: dict[tuple[int, str], str] = field(default_factory=dict)
    knife: bool = True  # the run swaps the Knife (a bare phase after each lock)


RATES = {  # the random scenarios' (the hand ones script theirs)
    "engage": 0.08, "walk_sword": 0.04, "plant": 0.02, "queue": 0.03, "lock": 0.45, "cue": 0.3,
    "kill": 0.25, "end": 0.3, "loot_fight": 0.1, "recheck": 0.08, "box_fly": 0.01,
    "rest_go": 0.02, "rest_end": 0.15, "idle_fly": 0.01, "unreach": 0.02, "common_done": 0.01,
    "run_end": 0.0001, "relock": 0.2,
}  # fmt: skip


class FakeHunt:
    """The fake hunt: run()'s state as the cursor reads it (HuntView's), the 20 steps, the clock."""

    def __init__(self, scn: Scenario, on_lock: Callable[[str | None], None] | None = None) -> None:
        self.scn = scn
        self.t = 0.0
        self.tick = 0
        self.hs = _HS()
        self.on_lock = on_lock
        self.log: list[str] = []  # the effects, in order (the report)

    def clock(self) -> float:
        return self.t

    def _draw(self, what: str, step: str) -> bool:
        s = self.scn
        if s.script:
            return s.script.get((self.tick, step)) == what
        p = s.rates.get(what, 0.0)
        h = hashlib.sha256(f"{s.seed}/{self.tick}/{step}/{self.hs.mode}/{what}".encode()).digest()
        return int.from_bytes(h[:8], "big") / 2**64 < p

    def _fx(self, what: str) -> None:
        self.log.append(f"{self.tick}:{what}")

    def _engage(self, by: str, lock: bool) -> None:
        hs = self.hs
        sp = SPECIES[(self.tick * 7 + len(by)) % len(SPECIES)]
        hs.mode, hs.box_sp[0] = "fight", sp
        hs.box_fight = {"spot": [10 + self.tick % 5, 20], "box": [1.0, 2.0, 3.0, 4.0]}
        if lock:
            self._lock()
        self._fx(f"engage_{by}")

    def _lock(self) -> None:
        hs = self.hs
        hs.lock = {"t": self.t, "rel": [1, 0], "cell": hs.box_fight.get("spot")}
        if self.on_lock is not None:
            self.on_lock(hs.box_sp[0])  # run(): the lock asks the box's recipe (hook.recipe)
        if self.scn.knife:
            hs.bare.st.t_bare, hs.bare.st.stolen = self.t, False
        self._fx("lock")

    def steps(self) -> list[tuple[str, Callable[[], str | None]]]:
        return [(n, self._mk(n)) for n in dh.STEP_NAMES]

    def _mk(self, name: str) -> Callable[[], str | None]:
        def step() -> str | None:
            self.t += PACE_S if name == "pace" else STEP_S
            if name == "begin":
                self.tick += 1
            return getattr(self, f"s_{name}", self._common)(name)

        return step

    # -- the common steps: a RUN_END, a TICK_DONE (a walk away), a box Fly Wing --
    def _common(self, name: str) -> str | None:
        if self._draw("run_end", name):
            self._fx(f"run_end@{name}")
            return dh.RUN_END
        return None

    def s_survive(self, name: str) -> str | None:
        hs = self.hs
        if self._draw("box_fly", name):  # the box's Fly Wing: its after-the-fly steps
            hs.mode, hs.lock, hs.box_fight = "search", None, {}
            hs.bare.st.t_bare = None
            self._fx("box_fly")
            return dh.TICK_DONE
        return self._common(name)

    def s_engage(self, name: str) -> str | None:
        hs = self.hs
        if hs.mode == "fight" and self._draw("common_done", name):  # a walk away
            hs.mode, hs.lock = "search", None
            hs.bare.st.t_bare = None
            self._fx("walk_away")
            return dh.TICK_DONE
        if hs.mode != "fight" and self._draw("engage", name):
            self._engage("hit", lock=False)
        return None

    # -- the mode steps, each with its real guard --
    def s_fight(self, name: str) -> str | None:
        hs = self.hs
        if hs.mode != "fight":
            return None  # (the real step: its body is one `if hs.mode == "fight":`)
        st = hs.bare.st
        if hs.lock is None and self._draw("lock", name):
            self._lock()
        elif hs.lock is not None and st.t_bare is not None and self._draw("cue", name):
            st.t_bare, st.stolen = None, True
            self._fx("cue")
        elif hs.lock is not None and self._draw("kill", name):
            hs.kills_seen.append(self.t)
            hs.lock = None
            st.t_bare = None
            self._fx("kill")
            if self._draw("relock", name):  # the melee ring's queue: the next one at once
                self._lock()
        elif hs.lock is None and self._draw("unreach", name):
            hs.mode, hs.box_fight = "search", {}
            self._fx("unreach")
        elif hs.lock is None and self._draw("end", name):
            hs.mode = "after"
            self._fx("fight_end")
        return dh.TICK_DONE  # (in mode fight the real step always ends the tick: the proof)

    def s_hold(self, name: str) -> str | None:
        hs = self.hs
        if hs.mode == "fight" or hs.lock is not None:
            return dh.TICK_DONE
        if self._draw("recheck", name):
            self._fx("recheck")
            return dh.TICK_DONE
        return None

    def s_loot(self, name: str) -> str | None:
        hs = self.hs
        if hs.mode != "after":
            return None  # (the real step: two ifs on mode after)
        hs.counts["loot_click"] += 2
        self._fx("loot_step")
        if self._draw("loot_fight", name):  # a fight began inside the loot step
            self._engage("loot", lock=False)
            return dh.TICK_DONE
        return None

    def s_after(self, name: str) -> str | None:
        hs = self.hs
        if hs.mode in ("after", "search") and self._draw("rest_go", name):
            hs.mode = "rest"
            self._fx("rest_go")
        if hs.mode == "after":
            hs.mode = "search"
        return None

    def s_ready(self, name: str) -> str | None:
        hs = self.hs
        if hs.mode == "search" and self._draw("queue", name):  # --queue's next target: struck
            self._engage("queue", lock=True)
            return dh.TICK_DONE
        return None

    def s_rest(self, name: str) -> str | None:
        hs = self.hs
        if hs.mode != "rest":
            return None
        if self._draw("rest_end", name):
            hs.mode = "search"
            self._fx("rest_end")
        return dh.TICK_DONE

    def s_idle(self, name: str) -> str | None:
        if self.hs.mode == "search" and self._draw("idle_fly", name):
            self._fx("idle_fly")
            return dh.TICK_DONE
        return None

    def s_plant(self, name: str) -> str | None:
        if self.hs.mode == "search" and self.hs.lock is None and self._draw("plant", name):
            self._engage("plant", lock=True)
            return dh.TICK_DONE
        return None

    def s_search(self, name: str) -> str | None:
        if self.hs.mode == "search" and self._draw("walk_sword", name):
            self._engage("walk_sword", lock=True)  # (real: mode fight, then NO return: position
        return None  # and pace still run in this tick)


class _St:
    def __init__(self) -> None:
        self.t_bare: float | None = None
        self.stolen = False


class _Bare:
    def __init__(self) -> None:
        self.st = _St()


class _HS:
    def __init__(self) -> None:
        self.mode = "search"
        self.lock: dict[str, Any] | None = None
        self.box_fight: dict[str, Any] = {}
        self.box_sp: list[str | None] = [None]
        self.bare: _Bare | None = _Bare()
        self.kills_seen: list[float] = []
        self.counts: Counter[str] = Counter()
        self.here = (10, 10)


Trace = list[tuple[int, str, str | None]]


def driver_trace(scn: Scenario) -> tuple[Trace, FakeHunt]:
    """A: run()'s driver loop, exactly (hunt_tick over hunt_steps; the loop's condition)."""
    fh = FakeHunt(scn)
    trace: Trace = []
    steps = fh.steps()

    def hunt_tick() -> str | None:
        for name_, step_ in steps:
            sig_ = step_()
            trace.append((fh.tick, name_, sig_))
            if sig_ is not None:
                return sig_
        return None

    t_end = scn.minutes * 60.0
    while fh.clock() < t_end:
        if hunt_tick() == dh.RUN_END:
            break
    return trace, fh


class _Mem:
    """The player's record, in memory."""

    def __init__(self) -> None:
        self.recs: list[dict[str, Any]] = []

    def ev(self, rec: Any) -> None:
        self.recs.append(dict(rec))

    def close(self) -> None:
        return None


def player_for(text: str, node: str = NODE) -> Any:
    """The REAL live player of the project's node, prepared before any input, on an IO that has
    no screen and no input path (nothing here may press: the drive's blocks call only the steps)."""
    import flow_play as fp

    prep = fp.prepare(text, node, 0)  # no configured maximum (Batt 2026-11-19)
    if isinstance(prep, str):
        raise SystemExit(prep)

    class NoIO(fp.LiveIO):
        def __init__(self) -> None:
            self.now = 0.0

        def clock(self) -> float:
            return self.now

        def sleep(self, s: float) -> None:
            self.now += s

        def ns(self) -> int:
            return int(self.now * 1e9)

        def senses(self) -> dict[str, Any]:
            return {}

        def tap(self, code: str) -> None:
            raise AssertionError(f"the harness may not press ({code})")

    pl = fp.LivePlayer(prep, NoIO(), _Mem(), stop_file=None, hunt=None)  # type: ignore[arg-type]
    pl.block = node
    return pl


def blocks_trace(scn: Scenario, text: str, node: str = NODE) -> tuple[Trace, FakeHunt, Any]:
    """B: the cursor over the same steps, driven by the live player playing the node's hunt loop."""
    pl = player_for(text, node)
    fh = FakeHunt(scn, on_lock=lambda sp: pl.hunt_recipe(sp, "lock"))
    cur = dh.HuntCursor(fh.steps(), dh.HuntView(fh.hs, lambda: {"mode": fh.hs.mode}, fh.clock),
                        t_end=scn.minutes * 60.0, clock=fh.clock, trace=True)  # fmt: skip
    got = pl.hunt_drive(cur)
    if got is not None:
        raise SystemExit(f"the hunt loop stopped: {got}")
    assert cur.trace is not None
    return cur.trace, fh, cur


def hand_scenarios() -> list[Scenario]:
    """One per transition the cursor must hand over at (13.4's cases)."""
    S = Scenario  # noqa: N806

    def at(**kw: str) -> dict[tuple[int, str], str]:
        out = {}
        for k, v in kw.items():
            tick, step = k[1:].split("_", 1)
            out[(int(tick), step)] = v
        return out

    return [
        S("one fight: engage, lock, cue, kill, end, loot", minutes=0.2,
          script=at(t3_engage="engage", t4_fight="lock", t6_fight="cue", t8_fight="kill",
                    t9_fight="end")),
        S("a fight that never locks", minutes=0.2, script=at(t2_engage="engage", t5_fight="end")),
        S("the loot step starts a fight", minutes=0.2,
          script=at(t2_engage="engage", t3_fight="lock", t4_fight="kill", t5_fight="end",
                    t6_loot="loot_fight", t7_fight="lock", t8_fight="kill", t9_fight="end")),
        S("the recheck holds a tick after the fight", minutes=0.2,
          script=at(t2_engage="engage", t3_fight="lock", t4_fight="kill", t5_fight="end",
                    t6_hold="recheck")),
        S("a box Fly Wing mid-fight", minutes=0.2,
          script=at(t2_engage="engage", t3_fight="lock", t5_survive="box_fly")),
        S("a walk-sword engage keeps its tick (position and pace run in mode fight)", minutes=0.2,
          script=at(t2_search="walk_sword", t4_fight="kill", t5_fight="end")),
        S("a plant and a queued target", minutes=0.2,
          script=at(t2_plant="plant", t3_fight="kill", t4_fight="end", t6_ready="queue",
                    t7_fight="kill", t8_fight="end")),
        S("a rest", minutes=0.2, script=at(t2_after="rest_go", t5_rest="rest_end")),
        S("two kills in one fight (the melee ring's queue)", minutes=0.2,
          script=at(t2_engage="engage", t3_fight="lock", t4_fight="kill", t5_fight="lock",
                    t6_fight="kill", t7_fight="end")),
        S("an unreachable attacker", minutes=0.2,
          script=at(t2_engage="engage", t4_fight="unreach")),
        S("a RUN_END mid-fight", minutes=0.2,
          script=at(t2_engage="engage", t3_fight="lock", t4_battle_log="run_end")),
        S("the run's time box mid-search", minutes=0.05),
        S("no Knife: no bare phase", minutes=0.2, knife=False,
          script=at(t2_engage="engage", t3_fight="lock", t4_fight="kill", t5_fight="end")),
    ]  # fmt: skip


def random_scenarios(n: int) -> list[Scenario]:
    return [Scenario(f"random seed {i}", seed=i, minutes=3.0, rates=dict(RATES),
                     knife=i % 5 != 4) for i in range(1, n + 1)]  # fmt: skip


@dataclass
class Compared:
    scn: Scenario
    same: bool
    ticks: int
    steps: int
    passed: dict[str, int]
    effects: Counter[str]
    first_diff: str | None


def compare(scn: Scenario, text: str, node: str = NODE) -> Compared:
    a, fa = driver_trace(scn)
    b, _fb, cur = blocks_trace(scn, text, node)
    b_called = [x for x in b if x[2] != "passed"]
    diff = None
    for i, (x, y) in enumerate(zip(a, b, strict=False)):
        if x != y:
            diff = f"call {i}: the driver {x}, the blocks {y}"
            break
    if diff is None and len(a) != len(b):
        diff = f"the driver called {len(a)} steps, the blocks {len(b)}"
    eff = Counter(e.split(":", 1)[1] for e in fa.log)
    same = diff is None and b_called == b
    return Compared(scn, same, fa.tick, len(a), dict(cur.passed), eff, diff)


def short_boxes(text: str, s: float = 1.0) -> str:
    """The same project with every hunt block's time box (its timeout_s: find_target's,
    fight_target's, the recipes' steps') at ``s`` seconds: a block then hands back on its time
    box all the time, and the next block takes over at that point (13.4: a time box never changes
    the steps run)."""
    import json

    d = json.loads(text)
    blocks = {"find_target", "fight_target", "strike", "wait_steal", "wait_kill", "loot"}

    def walk(stmts: list[Any]) -> None:
        for st in stmts:
            if st.get("kind") == "action" and st.get("block") in blocks:
                st["timeout_s"] = s
            for k in ("body", "then", "orelse"):
                walk(st.get(k) or [])

    for n in d["nodes"]:
        for t in n.get("tabs") or []:
            for df in t.get("defs") or []:
                walk(df["body"])
    return json.dumps(d)


def leave_out(text: str, steps: Sequence[str]) -> str:
    """The same project with its hunt_tick() leaving these steps out (5c: an OPTIONAL step's edit;
    the trace then PASSES those steps: the edit plays)."""
    import json

    d = json.loads(text)
    blocks = {f"step_{x}" for x in steps}
    for n in d["nodes"]:
        for t in n.get("tabs") or []:
            for df in t.get("defs") or []:
                if df["name"] == "hunt_tick":
                    df["body"] = [st for st in df["body"] if st.get("block") not in blocks]
    return json.dumps(d)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--seeds", type=int, default=50)
    c.add_argument("--project", type=Path, default=None,
                   help="one project (default: the hunt box and the functions box, 5c)",
                   )  # fmt: skip
    a = ap.parse_args(argv)
    bad = 0
    total: Counter[str] = Counter()
    runs: list[tuple[Scenario, str, str]] = []
    for path in [a.project] if a.project else [PROJECT, FUNCTIONS]:
        text = path.read_text()
        tag = "" if a.project else f" [{path.stem.removeprefix('project_')}]"
        runs += [(scn, text, tag) for scn in [*hand_scenarios(), *random_scenarios(a.seeds)]]
        runs += [(scn, short_boxes(text), f"{tag} (every time box 1 s)")
                 for scn in random_scenarios(10)]  # fmt: skip
    for scn, txt, how in runs:
        r = compare(scn, txt)
        total.update(r.effects)
        bad += not r.same
        eff = ", ".join(f"{k} {v}" for k, v in sorted(r.effects.items()))
        print(f"{'SAME' if r.same else 'DIFFERS'}  {scn.name}{how}: {r.ticks} ticks, "
              f"{r.steps} steps"
              f"{'' if r.same else ' -- ' + str(r.first_diff)}"
              f"{'' if not r.passed else f' (passed {r.passed})'}  [{eff}]")  # fmt: skip
    print(f"effects over all scenarios: {dict(sorted(total.items()))}")
    verdict = "YES, every scenario" if not bad else f"NO in {bad}"
    print(f"the driver's trace == the hunt loop's: {verdict} ({len(runs)} scenarios)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
