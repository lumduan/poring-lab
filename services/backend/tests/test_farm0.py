"""farm0.py's pure parts (Batt 2026-10-15: the first end-to-end playable demo, unscored)."""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import farm0  # noqa: E402

BOX = (0, 0, 39, 39)


def test_choose_target_is_the_nearest_inside_the_box() -> None:
    cands = [("far", (20, 20)), ("near", (12, 11)), ("none", None), ("out", (50, 50))]
    assert farm0.choose_target(cands, (10, 10), BOX) == ("near", (12, 11))
    assert farm0.choose_target([("out", (50, 50)), ("x", None)], (10, 10), BOX) is None


def test_approach_goal_is_a_stand_cell_near_the_target_never_on_it() -> None:
    ok = np.ones((40, 40), dtype=bool)
    goal = farm0.approach_goal((20, 20), (10, 20), ok, approach=2, box=BOX)
    assert goal is not None and goal != (20, 20)
    assert farm0.cheb(goal, (20, 20)) <= 2 and goal[0] == 18  # the near side
    ok[:, :] = False
    ok[22, 22] = True
    assert farm0.approach_goal((20, 20), (10, 20), ok, approach=2, box=BOX) == (22, 22)
    ok[:, :] = False
    assert farm0.approach_goal((20, 20), (10, 20), ok, approach=2, box=BOX) is None


def test_wander_goal_is_seeded_and_stays_in_the_box_on_stand_cells() -> None:
    ok = np.ones((40, 40), dtype=bool)
    a = farm0.wander_goal((20, 20), ok, random.Random(7), (8, 12), BOX)
    b = farm0.wander_goal((20, 20), ok, random.Random(7), (8, 12), BOX)
    assert a == b and a is not None
    assert 7 <= farm0.cheb(a, (20, 20)) <= 12 and farm0.in_box(a, BOX)
    assert farm0.wander_goal((20, 20), np.zeros((40, 40), dtype=bool), random.Random(7)) is None


def test_split_adds_each_interval_to_its_category_and_ranks() -> None:
    s = farm0.Split()
    s.to("finding", 0.0)
    s.to("walking", 2.0)
    s.to("fighting", 7.0)
    s.to("finding", 8.0)
    s.to(None, 9.0)
    assert s.s["finding"] == 3.0 and s.s["walking"] == 5.0 and s.s["fighting"] == 1.0
    assert s.ranked()[0] == ("walking", 5.0)
    assert farm0.per_hour(3, 1800.0) == 6.0 and farm0.per_hour(1, 0.0) is None


def test_takeover_stops_instead_of_waiting() -> None:
    class Agent:
        def __init__(self, status: dict[str, Any]) -> None:
            self.status = status

        def _drain(self, _t: float) -> None:
            return None

    calm = Agent({"mode": "ASSIST", "lease_until_ns": 0})
    farm0.stop_on_takeover(calm)
    calm.wait_for_human()  # no lease: returns, the input goes out
    held = Agent({"mode": "ASSIST", "lease_until_ns": 2**62})
    farm0.stop_on_takeover(held)
    with pytest.raises(farm0.FarmStop):
        held.wait_for_human()
    human = Agent({"mode": "HUMAN"})
    farm0.stop_on_takeover(human)
    with pytest.raises(farm0.FarmStop):
        human.wait_for_human()


def test_exp_gained_counts_across_a_level_up() -> None:
    st = [
        {"name": "var22", "value": 9},
        {"name": "base_exp", "value": 0},
        {"name": "base_exp", "value": 4},  # +4
        {"name": "base_exp", "value": 2},  # level up: 9 - 4 = 5, then 2 -> +7
        {"name": "var22", "value": 16},
        {"name": "base_exp", "value": 6},  # +4
        {"name": "job_exp", "value": 1},
        {"name": "job_exp", "value": 3},
    ]
    assert farm0.exp_gained(st, "base") == 15
    assert farm0.exp_gained(st, "job") == 2


def test_kills_from_packets_needs_our_hit_and_a_death() -> None:
    ev = [
        {"type": "entity_appear", "gid": 1, "job": 1002},
        {"type": "entity_appear", "gid": 2, "job": 1063},
        {"type": "entity_appear", "gid": 3, "job": 1184},
        {"type": "act", "src_gid": farm0.GM_AID, "target_gid": 1},
        {"type": "act", "src_gid": farm0.GM_AID, "target_gid": 3},
        {"type": "act", "src_gid": 2, "target_gid": farm0.GM_AID},
        {"type": "entity_vanish", "gid": 1, "reason": 1},
        {"type": "entity_vanish", "gid": 2, "reason": 1},  # died, never hit by us: not a kill
        {"type": "entity_vanish", "gid": 3, "reason": 0},  # walked out of view: not a kill
    ]
    k = farm0.kills_from_packets(ev)
    assert k["kills"] == 1 and k["by_species"] == {"Poring": 1}
    assert k["non_target_jobs_hit"] == [1184] and k["acts_onto_gm"] == 1
