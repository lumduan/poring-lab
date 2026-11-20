"""live-blocks 5c (docs/planning/live-blocks.md 15): the runner block dissolved into functions in
tabs -- the player and the runner. The ready-made box as functions gives the hunt box's runner
exactly (argv, keys, settings, run() arguments); its hunt_tick() leaves out only an OPTIONAL step,
and the runner's cursor refuses any other; the step traces equal the driver's; the Run helper sees
its hunt core."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

import dungeon_hunt as dh  # noqa: E402
import flow_play as fp  # noqa: E402
import flow_run as fr  # noqa: E402
import hunt_trace as ht  # noqa: E402
import test_hunt_blocks as thb  # noqa: E402

from poring_flow import tick as tk  # noqa: E402

FIX = ROOT / "services/frontend/src/lib/flow/fixtures"
# the configured maximum run time: none since 2026-11-19 (Batt: no time limit unless set)
NO_MAX = 0
NODE = "xmas_dun02"
ONE = (FIX / "project_xmas_dun02.json").read_text()
HUNT = (FIX / "project_xmas_dun02_hunt.json").read_text()
FUN = (FIX / "project_xmas_dun02_functions.json").read_text()


def _plan(text: str) -> fp.RunnerPlan:
    got = fp.prepare(text, NODE, NO_MAX)
    assert not isinstance(got, str), got
    return got.runners[NODE]


def test_the_functions_box_plays_the_hunt_boxs_runner_exactly() -> None:
    """The hunt box's runner exactly, but for live-blocks 18.10 #1, 18.13 and 18.18: the ready-made
    functions box holds fly_first, fly_first_hp and fly_first_land ON (the one box and the hunt
    box, the reference arms, keep them off), so its argv carries --fly-first, --fly-first-hp and
    --fly-first-land (in that order) and its settings differ in those three alone -- FF_LAND_S at
    its default 0.75 s in every box, so no --tune; and for 18.15: its use_model names xmas02sk (the
    map's deployed model, with its alarm), the reference arms' xmas02 -- the box's run() model
    argument alone."""
    flags = ("--fly-first", "--fly-first-hp", "--fly-first-land")
    one, hunt, fun = _plan(ONE), _plan(HUNT), _plan(FUN)
    for a in (one, hunt):
        got, ref = fun.argv("L", Path("/S"), None), a.argv("L", Path("/S"), None)
        assert all(got.count(f) == 1 and f not in ref for f in flags)
        assert [x for x in got if x in flags] == list(flags)  # 18.18: land after the HP flag
        assert [x for x in got if x not in flags] == ref
        assert {k for k in fun.vals if fun.vals[k] != a.vals.get(k)} == {
            "fly_first",
            "fly_first_hp",
            "fly_first_land",
        }
        assert fun.vals["fly_first"] is True and fun.vals["fly_first_hp"] is True
        assert fun.vals["fly_first_land"] is True  # 18.18: s10ab passed
        assert a.vals["fly_first"] is False and a.vals["fly_first_hp"] is False
        assert a.vals["fly_first_land"] is False
        assert fun.vals["FF_LAND_S"] == a.vals["FF_LAND_S"] == 0.75
        assert not any("FF_LAND_S" in x for x in got)  # its default: the runner's own number
        fb, ab = fun.box_kwargs(), a.box_kwargs()
        assert fun.keys == a.keys and {k: v for k, v in fb.items() if k != "box_model"} == {
            k: v for k, v in ab.items() if k != "box_model"
        }
        # the functions box names the deployed model (xmas02v1080 since 2026-11-20, Amendment 24)
        assert ab["box_model"]["id"] == "xmas02" and fb["box_model"]["id"] == "xmas02v1080"
        assert fb["box_model"]["alarm"] == ["garm_baby", "g_gobline_xmas", "knight_of_windstorm"]
        assert "alarm" not in ab["box_model"]  # the reference arms' run() argument as before
    assert fun.loop == hunt.loop == "hunt_loop" and fun.tick_left_out == ()
    assert fun.skill_keys == hunt.skill_keys == ("F1",)
    assert fr.has_hunt_core(json.loads(FUN)) and fr.has_hunt_core(json.loads(HUNT))


def test_the_tables_agree_with_the_runner() -> None:
    assert tuple(s.name for s in tk.STEPS) == dh.STEP_NAMES
    assert tk.OPTIONAL == dh.DRIVE_OPTIONAL_STEPS
    assert tk.VERSION == dh.RUNNER_BLOCKS_VERSION == "9.56"
    # the optional steps are mode steps away from the hand-back points: leaving one out never moves
    # a hand-back
    assert not set(tk.OPTIONAL) & set(dh.HANDBACK_AT) and set(tk.OPTIONAL) <= set(dh.MODE_STEPS)


def test_the_cursor_leaves_out_only_an_optional_step_and_never_plays_it() -> None:
    fh = ht.FakeHunt(ht.hand_scenarios()[0])
    cur = dh.HuntCursor(fh.steps(), dh.HuntView(fh.hs, lambda: {}, fh.clock), t_end=12.0,
                        clock=fh.clock, trace=True)  # fmt: skip
    with pytest.raises(ValueError, match="only"):
        cur.leave_out(["ui"])
    with pytest.raises(ValueError, match="pace"):
        cur.leave_out(["loot", "pace"])
    cur.leave_out(["loot", "plant"])
    while cur.ended is None:
        cur.find_target()
        cur.wait_kill()
        cur.loot()
    assert cur.trace is not None
    assert not any(n in ("loot", "plant") and s != "left_out" for _t, n, s in cur.trace)
    assert cur.calls["loot"] == cur.calls["plant"] == 0 and cur.left["loot"] > 0
    assert cur.doc()["left_out"] == ["loot", "plant"] and not cur.passed


def _left_out_box(steps: list[str]) -> str:
    return ht.leave_out(FUN, steps)


def test_the_player_hands_the_left_out_steps_to_the_cursor() -> None:
    res, log, recs, seen = thb._play(_left_out_box(["loot"]), ht.hand_scenarios()[0])
    cur = seen["cursor"]
    assert cur.left_out == frozenset({"loot"}) and cur.calls["loot"] == 0
    start = next(r for r in log.recs if r["kind"] == "drive" and r["what"] == "start")
    assert start["left_out"] == ["loot"]
    assert recs[-1]["left_out"] == ["loot"]  # the runner's drive end record says so
    # the full tick: nothing left out, the driver's steps
    res2, _log2, recs2, seen2 = thb._play(FUN, ht.hand_scenarios()[0])
    assert seen2["cursor"].left_out == frozenset() and "left_out" not in recs2[-1]
    drv, _fh = ht.driver_trace(ht.hand_scenarios()[0])
    assert seen2["cursor"].trace == drv


def test_a_runner_that_refuses_the_left_out_step_refuses_the_drive() -> None:
    pl = ht.player_for(_left_out_box(["loot"]))

    class Old:  # a cursor whose leave_out refuses (a runner that does not take it)
        def leave_out(self, names: Any) -> None:
            raise ValueError("the tick may leave out only []")

        def doc(self) -> dict[str, Any]:
            return {}

    got = pl.hunt_drive(Old())
    assert got is not None and got.startswith("the box's tick:")


@pytest.mark.parametrize("scn", ht.hand_scenarios(), ids=lambda s: s.name)
def test_the_functions_box_calls_the_drivers_steps_tick_for_tick(scn: ht.Scenario) -> None:
    r = ht.compare(scn, FUN)
    assert r.same, r.first_diff


def test_random_scenarios_on_the_functions_box_and_a_left_out_step_differs() -> None:
    for scn in ht.random_scenarios(15):
        assert ht.compare(scn, FUN).same, scn.name
    r = ht.compare(ht.hand_scenarios()[0], _left_out_box(["loot"]))
    assert not r.same and "'loot', 'left_out'" in str(r.first_diff)  # the edit plays
