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
