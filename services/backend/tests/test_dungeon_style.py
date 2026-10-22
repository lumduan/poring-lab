"""dungeon_style.py (Batt 2026-10-22: how his orcsdun01 demo hunted, the same ruler for the bot):
the pure pieces, and a positive case on the REAL demo when it is banked (skipped otherwise)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_style as ds  # noqa: E402

NS = ds.NS
DEMO = "20261022T184536-demo-human-demo-orcsdun01-crusader"


def test_fights_merge_events_closer_than_the_gap_and_the_pack_counts_attackers() -> None:
    cb = [(0, "theirs", 1), (1 * NS, "ours", 1), (2 * NS, "theirs", 2), (2 * NS, "theirs", 3),
          (10 * NS, "theirs", 4)]  # fmt: skip
    f = ds.fights_of(cb)
    assert [len(x) for x in f] == [4, 1]
    assert ds.pack_size(f[0]) == 3 and ds.pack_size(f[1]) == 1


def test_openness_is_the_distance_to_the_nearest_wall() -> None:
    w = np.ones((9, 9), bool)
    w[:, 0] = False
    d = ds.openness(w)
    assert d[4, 0] == 0 and d[4, 1] == 1 and d[4, 4] == 4
    assert (
        ds.open_class(2) == "corridor" and ds.open_class(3) == "mid" and ds.open_class(4) == "open"
    )


def test_the_circuit_is_simplified_and_its_direction_named() -> None:
    sq = [(0, 0), (5, 0), (10, 0), (10, 5), (10, 10), (5, 10), (0, 10), (0, 5)]
    track = [(i * NS, c) for i, c in enumerate(sq)]
    out = ds.circuit(track, 0, 100 * NS, eps=1.0, merge=0)
    assert out["waypoints"] == [[0, 0], [10, 0], [10, 10], [0, 10], [0, 5]]
    assert out["direction"].startswith("counter-clockwise")  # east, then north: CCW, y north
    rev = ds.circuit([(i * NS, c) for i, c in enumerate(reversed(sq))], 0, 100 * NS, 1.0, 0)
    assert rev["direction"].startswith("clockwise")


def test_gaps_rank_the_largest_seconds_lost_per_kill_first() -> None:
    bot = {"time_split_s_per_kill": {"fighting": 8.8, "walking_outside_fights": 5.9,
                                     "standing_outside_fights": 26.4}}  # fmt: skip
    tgt = {"time_split_s_per_kill": {"fighting": 5.4, "walking_outside_fights": 0.7,
                                     "standing_outside_fights": 1.6}}  # fmt: skip
    assert [g["component"] for g in ds.gaps(bot, tgt)][0] == "standing_outside_fights"


def test_batts_real_demo_is_a_clockwise_circuit() -> None:
    import dungeon_judge as dj
    import flow_judge as fj

    if not (dj.session_dir(DEMO) / "packets.jsonl.gz").exists():
        pytest.skip("Batt's demo is not banked here")
    ev, pk, man = dj.load(DEMO)
    t0, t1 = dj.live_window(man, 961)
    track, _mv = fj.gm_track(pk)
    out = ds.circuit(track, t0, t1)
    assert out["direction"].startswith("clockwise")
    assert out["waypoints"][0] == [32, 166]  # the entrance (the in_orcs01 arrival)
