"""scripts/explore_map.py (rogue-xmas02.md 4AL, dungeon@9.14): regions, knowledge, the choice."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import dungeon_hunt as dh  # noqa: E402
import explore_map as em  # noqa: E402


def grid(rows: list[str]) -> np.ndarray:
    return np.array([[ch == "." for ch in r] for r in rows], dtype=bool)


def test_component_is_8_connected_without_corner_cutting() -> None:
    g = grid(["..#..",
              ".##..",
              "#....",
              "..#.."])  # fmt: skip
    c = em.component(g, (0, 0))
    assert c[0, 0] and c[0, 1] and c[1, 0]
    assert not c[2, 1]  # (1,2) is only diagonal to (0,1) past two walls: no corner cut
    assert not c[0, 3]  # the right side is another component
    assert not em.component(g, (2, 0)).any()  # the start on a wall: empty


def test_regions_anchor_near_the_tile_centre_and_drop_small_tiles() -> None:
    walk = np.zeros((20, 20), dtype=bool)
    walk[0:10, 0:10] = True  # region (0, 0): 100 cells
    walk[15, 15] = True  # region (1, 1): 1 cell -> dropped
    reg = em.regions(walk, size=10, min_cells=15)
    assert set(reg) == {(0, 0)}
    assert reg[(0, 0)] in {(4, 4), (5, 4), (4, 5), (5, 5)}
    assert em.region_of((15, 3), 10) == (1, 0)


def test_merge_adds_and_keeps_runs_once(tmp_path: Path) -> None:
    a = em.Knowledge(map="m", runs=["r1"], regions={"0,0": {**em.empty_region(), "good": 2}},
                     visited={"1,1": 3})  # fmt: skip
    b = em.Knowledge(map="m", runs=["r1", "r2"], regions={"0,0": {**em.empty_region(), "good": 1},
                     "1,0": em.empty_region()}, visited={"1,1": 1, "2,2": 1})  # fmt: skip
    m = em.merge(a, b)
    assert m.runs == ["r1", "r2"] and m.regions["0,0"]["good"] == 3 and "1,0" in m.regions
    assert m.visited == {"1,1": 4, "2,2": 1}
    assert a.regions["0,0"]["good"] == 2  # PURE: the inputs are untouched
    saved = em.save_merged(b, root=tmp_path)
    assert saved.regions["0,0"]["good"] == 1
    again = em.save_merged(a, root=tmp_path)  # merged onto the file
    assert again.regions["0,0"]["good"] == 3
    assert em.load("m", root=tmp_path).to_json() == again.to_json()


def test_rates_start_at_the_mean_and_scores_prefer_good_new_near() -> None:
    know = em.Knowledge(map="m", regions={
        "0,0": {**em.empty_region(), "dwell_s": 600.0, "good": 10, "visits": 3},  # 1.0 / min
        "1,0": {**em.empty_region(), "dwell_s": 600.0, "good": 0, "visits": 3},  # 0.0 / min
    })  # fmt: skip
    r = em.rates(know, [(0, 0), (1, 0), (2, 0)])
    assert r[(0, 0)] > r[(2, 0)] > r[(1, 0)]  # the unvisited one sits at the prior (the mean)
    anchors = {(0, 0): (5, 5), (1, 0): (15, 5), (2, 0): (25, 5)}
    sc = em.scores(know, anchors, (5, 5), skip=[(0, 0)])
    assert set(sc) == {(1, 0), (2, 0)} and sc[(2, 0)] > sc[(1, 0)]  # new beats known-poor


def test_choose_samples_by_score_and_is_seeded() -> None:
    sc = {(0, 0): 1.0, (1, 0): 0.0}
    picks = [em.choose(sc, np.random.default_rng(i)) for i in range(200)]
    assert picks.count((0, 0)) > 150 and (1, 0) in picks  # mostly the best, not always
    assert em.choose(sc, np.random.default_rng(7)) == em.choose(sc, np.random.default_rng(7))
    assert em.choose({}, np.random.default_rng(0)) is None


def test_recorder_books_dwell_visits_fights_and_stalls() -> None:
    hits = {"n": 0}
    rec = em.Recorder("m", "run1", lambda t0, t1: hits["n"], size=10)
    rec.on_event({"kind": "hp_read", "pos": [3, 3]}, 0.0)
    rec.on_event({"kind": "hp_read", "pos": [4, 3]}, 1.0)
    rec.on_event({"kind": "hp_read", "pos": [4, 3]}, 2.0)
    rec.on_event({"kind": "hp_read", "pos": [12, 3]}, 30.0)  # a 28-s gap books 5 s only
    rec.on_event({"kind": "engage", "by": "box"}, 31.0)
    hits["n"] = 6
    rec.on_event({"kind": "fight_end"}, 40.0)
    rec.on_event({"kind": "engage", "by": "battle_log"}, 41.0)
    hits["n"] = 2
    rec.on_event({"kind": "fight_end"}, 45.0)
    rec.on_event({"kind": "stall", "to": [7, 9]}, 46.0)
    rec.arrived((1, 0))
    r0, r1 = rec.know.regions["0,0"], rec.know.regions["1,0"]
    assert r0["dwell_s"] == 7.0  # 1 + 1 + 5
    assert r1["fights"] == 2 and r1["good"] == 1 and r1["engages"] == 2
    assert r1["box_engages"] == 1 and r1["visits"] == 1
    assert rec.know.visited == {"3,3": 1, "4,3": 1, "12,3": 1}
    assert rec.know.refused == {"7,9": 1}


def test_the_runner_wires_explore_behind_its_flag() -> None:
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "explore" not in dh.fixes_of(dh.argparse.Namespace(**base))
    assert dh.fixes_of(dh.argparse.Namespace(**base, explore=True))["explore"][0] == em.REGION
    src = Path(dh.__file__).read_text()
    assert "goal = explore_goal(here)" in src and "explore_block(here)" in src
    assert 'raise SystemExit("dungeon@9.14 refused: --explore goes with --search patrol")' in src
    assert "ev_hooks.append(ex_rec.on_event)" in src
    assert "merged_ = em.save_merged(ex_rec.know)" in src
    # the patrol loop's own paths are unchanged
    assert "goal = patrol_goal(here)" in src and "skip_waypoint(here)  # carved off" in src
