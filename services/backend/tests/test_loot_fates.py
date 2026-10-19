"""scripts/loot_fates.py: our kills' floor items, the loot step's 3 x 3 and the wider options
(OFFLINE, packets as truth). The REAL-session cases skip where the banked session is absent."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import arm_judge as aj  # noqa: E402
import loot_fates as lf  # noqa: E402

S = aj.NS


def _item(t_fall: float, cell: tuple[int, int], fate: str,
          t_end: float | None) -> dict[str, object]:  # fmt: skip
    return {"t_fall": int(t_fall * S), "cell": cell, "fate": fate,
            "t_end": None if t_end is None else int(t_end * S), "t_out": None}  # fmt: skip


def test_zone_is_the_clicked_3x3_its_outer_ring_and_beyond() -> None:
    assert lf.zone((10, 10), (10, 10)) == "in3x3" and lf.zone((11, 9), (10, 10)) == "in3x3"
    assert lf.zone((12, 9), (10, 10)) == "ring2" and lf.zone((8, 12), (10, 10)) == "ring2"
    assert lf.zone((13, 10), (10, 10)) == "beyond2"


def test_step_kills_takes_the_last_kill_before_the_step_near_its_cell() -> None:
    kills = [(10 * S, 1), (14 * S, 2), (15 * S, 3)]  # 3 died far away
    kcell = {(10 * S, 1): (50, 50), (14 * S, 2): (52, 51), (15 * S, 3): (90, 90)}
    items = {7: _item(13.8, (52, 51), "picked", 16.0), 8: _item(13.9, (53, 50), "looter", 17.0),
             9: _item(9.8, (50, 50), "picked", 11.0)}  # fmt: skip
    bot = [{"kind": "loot_fixed", "t_ns": 17 * S, "s": 2.0, "cell": [51, 51]},
           {"kind": "loot_fixed", "t_ns": 40 * S, "s": 2.0, "cell": [51, 51]},  # nothing died
           {"kind": "walk_click", "t_ns": 41 * S}]  # fmt: skip
    got = lf.step_kills(bot, items, kills, kcell)
    assert len(got) == 2
    assert got[0]["kill"] == (14 * S, 2) and got[0]["cell"] == (52, 51)
    assert got[0]["items"] == [7, 8]
    assert got[0]["ts"] == 15 * S and got[1]["kill"] is None and got[1]["items"] == []


def test_option_gain_counts_only_items_not_picked_and_still_there_at_the_extra_click() -> None:
    items = {
        1: _item(1.0, (12, 10), "out_of_sight", 30.0),  # left behind: a gain
        2: _item(1.0, (10, 12), "looter", 4.0),  # taken before its extra click
        3: _item(1.0, (8, 10), "picked", 3.5),  # picked anyway: no gain
        4: _item(1.0, (13, 10), "out_of_sight", 30.0),  # not on an extra cell
    }
    step = {"te": 3 * S, "s": 2.0, "dc": (10, 10), "items": [1, 2, 3, 4]}
    offs = [(2, 0), (0, 2), (-2, 0)]
    got = lf.option_gain([step], items, offs, p_click=1.0, p_pick=0.5, click_s=1.0, skip_s=0.0,
                         cap_s=None)  # fmt: skip
    assert got == {"gain": 0.5, "added_s": 3.0, "items_on_cells": 3}
    # the step's cap leaves room for 2 extra clicks only: (-2, 0) is never clicked
    capped = lf.option_gain([step], items, offs, 1.0, 0.5, 1.0, 0.0, cap_s=4.5)
    assert capped == {"gain": 0.5, "added_s": 2.0, "items_on_cells": 2}


V43_RUN1 = "20261019T152849-demo-hunt-flow43"


@pytest.mark.skipif(not (aj.DEMO / V43_RUN1 / "flow_judge.json").exists(),
                    reason="the real session is local only")  # fmt: skip
def test_real_v43_run_drops_outside_the_clicked_3x3_and_the_leaderboard_row() -> None:
    """v43 run 1 (a REAL session): the leaderboard's base has no "gone" left, its items split
    into the fates without a loss, and the loot steps' kills hold drops outside the clicked 3 x 3
    -- most of them within 1 cell of the SERVER's death cell (the bot's cell was off)."""
    s = lf.session(V43_RUN1)
    row = lf.run_summary(s)
    assert row["gone"] == 0 and row["items"] == sum(row[f] for f in lf.FATES)
    assert 0 < row["dc_exact_share"] <= row["dc_within1_share"] < 1 and 0 < row["in3x3_share"] < 1
    assert row["looter"] > 0 and row["out_of_sight"] > 0
    t = lf.outside_table([s])
    z = t["zones"]
    assert t["steps"]["steps"] == t["steps"]["with_kill"] + t["steps"].get("no_server_kill", 0)
    out = z["ring2"]["n"] + z["beyond2"]["n"]
    assert out > 0 and z["ring2"]["in_server_3x3"] + z["beyond2"]["in_server_3x3"] > out / 2
    assert 0 < t["ring_p_click"] < 1 and 0 < t["ring_p_pick"] <= 1
