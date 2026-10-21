"""left_behind.py (Batt 2026-10-20, step 3: why items are left behind): the pure parts. The real
8-run read (v42 + v44) is in docs/competition.md's loot block."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import left_behind as lb  # noqa: E402

S = 10**9


def test_a_loot_click_becomes_its_first_request() -> None:
    clicks = [{"t": 1 * S, "kind": "loot", "cell": [10, 10]},
              {"t": 2 * S, "kind": "loot", "cell": [11, 10]},
              {"t": 3 * S, "kind": "search", "cell": [20, 20]},
              {"t": 4 * S, "kind": "loot", "cell": [12, 10]}]  # fmt: skip
    packets = [{"t_mono_ns": 1 * S + 10**8, "type": "self_move_request", "x": 10, "y": 10},
               {"t_mono_ns": 2 * S + 10**8, "type": "pickup_request", "floor_id": 7},
               {"t_mono_ns": 2 * S + 2 * 10**8, "type": "pickup_result", "ok": False},
               {"t_mono_ns": 5 * S, "type": "self_move_request", "x": 1, "y": 1}]  # fmt: skip
    r = lb.click_results(clicks, packets)
    assert [x["what"] for x in r] == ["walk", "pickup", "none"]  # the search click is not loot
    assert r[0]["to"] == (10, 10) and r[1]["floor_id"] == 7 and r[1]["ok"] is False


def test_the_first_cause_that_holds() -> None:
    it = {"t_fall": 5 * S, "cell": (10, 10)}
    step = (4 * S, 8 * S)
    assert lb.cause_of(it, 1, False, None, None, None, []) == "no_loot_step"
    assert lb.cause_of({**it, "t_fall": 9 * S}, 1, True, step, (10, 10), None, []) == (
        "fell_after_step"
    )
    refused = [{"what": "pickup", "floor_id": 1, "ok": False}]
    assert lb.cause_of(it, 1, True, step, (10, 10), None, refused) == "pickup_refused"
    walked = [{"what": "walk", "to": (10, 10)}]
    assert lb.cause_of(it, 1, True, step, (10, 10), None, walked) == "clicked_walked"
    assert lb.cause_of(it, 1, True, step, (11, 11), None, []) == "in_plan_unclicked"
    assert lb.cause_of(it, 1, True, step, (13, 10), (11, 10), []) == "outside_plan_near_death_cell"
    assert lb.cause_of(it, 1, True, step, (13, 10), (14, 14), []) == "outside_plan"


def test_the_arm_of_a_kill_is_its_engagements_parity() -> None:
    assert lb.arm_of({"k": 3}) == "fix"
    assert lb.arm_of({"k": 4}) == "base"
    assert lb.arm_of(None) == "none"


def test_batts_rule_is_judged_against_its_own_plan_the_5x5_around_the_drawn_gm() -> None:
    """Under Batt's rule the plan is the 5 x 5 around the hovers' GM cell (``ref``), not the 3 x 3
    around the believed death cell. The real case: v51 run 1 (20261020T224434), the item at
    (229, 342), 3.0 s after its kill a looter took it, and the scan hovered its cell (the 10th of
    pass 1) 0.87 s later: the race."""
    t_k = 1255595191303636
    it = {"t_fall": t_k, "cell": (229, 342), "t_end": 1255598156865514, "t_out": None}
    step = (t_k + int(0.9 * S), t_k + int(9.0 * S))
    ref = [(230, 340)]
    late = {"t_ns": 1255599023933328, "cell": [229, 342], "ref": [230, 340], "seen": "empty"}
    assert lb.gm_cause_of(it, 1, step, ref, None, [], [late]) == "gone_before_hover"
    early = {**late, "t_ns": it["t_end"] - S, "seen": "sword"}  # a looter on the cell
    assert lb.gm_cause_of(it, 1, step, ref, None, [], [early, late]) == "hovered_read_sword"
    # never hovered: within 2 of the GM = planned, else outside (near the server's death cell?)
    assert lb.gm_cause_of(it, 1, step, ref, None, [], []) == "planned_not_hovered"
    far = {**it, "cell": (234, 342)}
    assert lb.gm_cause_of(far, 1, step, ref, (233, 342), [], []) == (
        "outside_gm_plan_near_death_cell"
    )
    assert lb.gm_cause_of(far, 1, step, ref, None, [], []) == "outside_gm_plan"
    # the old 3 x 3 around a believed death cell 3 off would call the same item "outside_plan"
    assert lb.cause_of(it, 1, True, step, (232, 342), None, []) == "outside_plan"
    assert lb.gm_cause_of({**it, "t_fall": step[1] + 1}, 1, step, ref, None, [], []) == (
        "fell_after_step"
    )


def test_a_v53_union_step_counts_the_believed_3x3_in_its_plan() -> None:
    """v53 (Batt 2026-10-21 decision 2): an item on the believed death cell's 3 x 3, outside the
    GM's 5 x 5, is in a union step's plan (planned_not_hovered), not outside it."""
    item = {"t_fall": 100, "cell": [20, 10]}
    step = (90, 200)
    refs = [(10, 10)]
    assert lb.gm_cause_of(item, 1, step, refs, (19, 10), [], []) == (
        "outside_gm_plan_near_death_cell")  # fmt: skip
    assert lb.gm_cause_of(item, 1, step, refs, (19, 10), [], [], {(20, 10)}) == (
        "planned_not_hovered")  # fmt: skip
