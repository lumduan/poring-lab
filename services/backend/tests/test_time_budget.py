"""scripts/time_budget.py: the time budget's pure functions on SYNTHETIC packets / events (the
definitions in its docstring, one case each), and the route extraction on a synthetic loop."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import time_budget as tb  # noqa: E402

S = tb.NS
ME = tb.AID
LADY, WARRIOR = 1273, 1023


def pk(t: float, **kw: object) -> dict:
    return {"t_mono_ns": int(t * S), **kw}


def ev(t: float, kind: str, **kw: object) -> dict:
    return {"t_ns": int(t * S), "kind": kind, **kw}


def appear(t: float, gid: int, x: int, y: int, job: int = LADY) -> dict:
    return pk(t, type="entity_appear", gid=gid, objtype=5, x=x, y=y, job=job)


def move(t: float, a: tuple[int, int], b: tuple[int, int]) -> dict:
    return pk(t, type="self_move", x0=a[0], y0=a[1], x1=b[0], y1=b[1])


def hit(t: float, src: int, dst: int, dmg: int, kind: str = "normal") -> dict:
    return pk(t, type="act", src_gid=src, target_gid=dst, damage=dmg, kind=kind, action=0)


def died(t: float, gid: int) -> dict:
    return pk(t, type="entity_vanish", gid=gid, reason=1)


def srt(xs: list[dict]) -> list[dict]:
    return sorted(xs, key=lambda e: e["t_mono_ns"])


# --- spans and labels -----------------------------------------------------------------------------


def test_merge_clip_minus_overlap() -> None:
    assert tb.merge([(5, 9), (1, 3), (2, 4), (9, 10), (7, 7)]) == [(1, 4), (5, 10)]
    assert tb.clip([(0, 5), (8, 20)], 2, 10) == [(2, 5), (8, 10)]
    assert tb.minus((0, 10), [(2, 3), (5, 7)]) == [(0, 2), (3, 5), (7, 10)]
    assert tb.overlap([(0, 5), (8, 20)], 3, 10) == 2 + 2


def test_each_instant_takes_the_first_label_that_covers_it_and_the_rest_is_idle() -> None:
    """rest > fight > loot > react > close > search; idle = none of them; the seconds sum to the
    window and the approach's two parts sum into 'approach'."""
    spans = {"search": [(0, 10 * S)], "react": [(2 * S, 4 * S)], "close": [(4 * S, 5 * S)],
             "fight": [(5 * S, 9 * S)], "rest": [(8 * S, 12 * S)],
             "loot": [(3 * S, 6 * S)]}  # fmt: skip
    segs = tb.label(0, 14 * S, spans)
    assert [(a // S, b // S, c) for a, b, c in segs] == [
        (0, 2, "search"), (2, 3, "react"), (3, 5, "loot"), (5, 8, "fight"), (8, 12, "rest"),
        (12, 14, "idle")]  # fmt: skip
    by = tb.seconds_by(segs)
    assert by == {"fight": 3.0, "approach": 1.0, "loot": 2.0, "rest": 4.0, "search": 2.0,
                  "idle": 2.0}  # fmt: skip
    assert sum(by.values()) == 14.0
    assert tb.seconds_by(segs, 4 * S, 9 * S)["fight"] == 3.0
    assert tb.label_at(segs, int(2.5 * S)) == "approach" and tb.label_at(segs, 20 * S) is None


def test_idle_is_split_by_what_surrounds_it() -> None:
    k = tb.idle_kind
    assert k("search", "search") == "inside_search"
    assert k("fight", "loot") == "loot_pause" and k("loot", "search") == "loot_pause"
    assert k("fight", "search") == "after_fight"
    assert k("search", "react") == "before_engage" and k("search", "fight") == "before_engage"
    assert k("rest", "search") == "around_rest" and k("search", "rest") == "around_rest"
    assert k(None, "search") == "other"
    segs = [(0, S, "search"), (S, 3 * S, "idle"), (3 * S, 4 * S, "search"), (4 * S, 5 * S, "idle"),
            (5 * S, 6 * S, "react")]  # fmt: skip
    c = tb.causes_by(segs)
    assert c["idle_inside_search"] == 2.0 and c["idle_before_engage"] == 1.0
    assert c["search_walk"] == 2.0 and c["approach_react"] == 1.0
    assert sum(c.values()) == 6.0
    assert tb.seg_causes(segs)[1] == "idle_inside_search"


# --- engagements ---------------------------------------------------------------------------------


def a_fight() -> list[dict]:
    """We stand at 10,10; an Orc Lady (gid 7) appears at 12,10 (after our last walk ended) and
    swings at us at 1 s (a miss); we request it at 2 s (it is 2 cells away), our first hit at 3 s,
    more hits, it dies at 6 s."""
    return srt([
        move(0.0, (10, 10), (10, 10)),
        appear(0.5, 7, 12, 10),
        hit(1.0, 7, ME, 0),
        pk(2.0, type="attack_request", target_gid=7, action=7, is_attack=True, kind="repeat"),
        hit(3.0, ME, 7, 300), hit(4.0, 7, ME, 112), hit(4.5, ME, 7, 300),
        hit(5.5, ME, 7, 300, "multi_hit"),
        died(6.0, 7),
    ])  # fmt: skip


def test_an_engagement_from_its_first_act_on_us_to_its_death() -> None:
    tr = tb.Track(a_fight())
    (e,) = tb.engagements(a_fight(), 0, 10 * S, tr)
    assert e["approach_by"] == "attacked" and e["t_approach"] == 1 * S
    assert e["t_respond"] == 2 * S and e["t_first"] == 3 * S and e["t_kill"] == 6 * S
    assert e["ttk_s"] == 3.0 and e["approach_s"] == 2.0 and e["react_s"] == 1.0
    assert e["engage_dist"] == 2 and e["hits_before_first"] == 0 and e["killed"]
    assert e["joined"] is False


def test_a_second_monster_joins_and_a_disengaged_one_ends_after_its_tail() -> None:
    p = srt([*a_fight(), appear(0.0, 8, 11, 11, WARRIOR), hit(4.2, 8, ME, 90),
             appear(0.0, 9, 9, 9), hit(20.0, ME, 9, 300)])  # fmt: skip
    eng = tb.engagements(p, 0, 30 * S, tb.Track(p))
    first = next(e for e in eng if e["gid"] == 7)
    assert first["joined"] is True
    lone = next(e for e in eng if e["gid"] == 9)
    assert not lone["killed"] and lone["t_end"] == 20 * S + int(tb.FIGHT_TAIL_S * S)
    assert lone["approach_by"] == "none" and lone["approach_s"] == 0.0


def test_the_walk_that_ends_at_the_target_starts_the_approach() -> None:
    """Two walk clicks toward a still monster at 20,10 (destinations within WALK_NEAR of it), then
    the request; the approach starts at the first of those walks."""
    p = srt([
        move(0.0, (10, 10), (10, 10)), appear(0.0, 7, 20, 10),
        move(1.0, (10, 10), (15, 10)),  # not near it: not part of the approach
        move(2.0, (12, 10), (18, 10)), move(3.0, (15, 10), (19, 10)),
        pk(3.5, type="attack_request", target_gid=7, action=7, is_attack=True),
        hit(4.0, ME, 7, 300), died(5.0, 7),
    ])  # fmt: skip
    (e,) = tb.engagements(p, 0, 10 * S, tb.Track(p))
    assert e["approach_by"] == "walk" and e["t_approach"] == 2 * S and e["react_s"] == 0.0


# --- loot ----------------------------------------------------------------------------------------


def test_a_piles_loot_runs_from_the_walk_to_its_item_until_its_last_pickup() -> None:
    p = srt([
        move(0.0, (10, 10), (10, 10)),
        pk(1.0, type="floor_item_appear", floor_id=1, item_id=7053, x=12, y=10, kind="fall"),
        pk(1.1, type="floor_item_appear", floor_id=2, item_id=931, x=13, y=11, kind="fall"),
        move(2.0, (10, 10), (12, 10)),
        pk(2.5, type="pickup_request", floor_id=1), pk(2.6, type="pickup_result", ok=True),
        pk(3.0, type="pickup_request", floor_id=2), pk(3.1, type="pickup_result", ok=True),
        # a third item far away, picked much later: a span of its own
        pk(1.0, type="floor_item_appear", floor_id=3, item_id=998, x=40, y=40, kind="fall"),
        pk(30.0, type="pickup_request", floor_id=3),  # never answered
    ])  # fmt: skip
    assert tb.piles(p) == {1: 0, 2: 0, 3: 1}
    picks = tb.pickups(p, 0, 60 * S)
    assert [(x["t_start"], x["t_end"], x["ok"]) for x in picks] == [
        (2 * S, int(2.6 * S), True), (2 * S, int(3.1 * S), True),  # one walk ended at both
        (30 * S, 30 * S + int(tb.PICK_NONE_S * S), False)]  # fmt: skip
    assert tb.loot_spans(picks) == [(2 * S, int(3.1 * S)), (30 * S, int(30.3 * S))]
    assert tb.fall_to_pick(picks) == [1.5, 29.0]


# --- rest, maps, HP -------------------------------------------------------------------------------


def test_rest_spans_from_the_runner_and_time_on_another_map() -> None:
    evs = [ev(10, "rest_go"), ev(12, "rest_start"), ev(40, "rest_end"), ev(90, "rest_start")]
    assert tb.runner_rest_spans(evs, 0, 100 * S) == [(10 * S, 40 * S), (90 * S, 100 * S)]
    p = [pk(0.0, type="map_change", map="gef_fild10.gat"),
         pk(50.0, type="map_change", map="in_orcs01.gat"),
         pk(70.0, type="map_change", map="gef_fild10.gat"),
         pk(90.0, type="map_change", map="in_orcs01.gat")]  # fmt: skip
    assert tb.map_spans(p, 10 * S, 100 * S) == [(50 * S, 70 * S), (90 * S, 100 * S)]
    assert tb.first_off_map(p, 10 * S, 100 * S) == 50 * S
    assert tb.first_off_map(p, 10 * S, 40 * S) == 40 * S


def test_hp_economy_damage_potions_and_regen_sitting_or_not() -> None:
    hp = [(0, 1000), (5, 900), (6, 911), (10, 1361), (20, 1372), (23, 1383)]
    p = [pk(t, type="stat_change", name="hp", value=v) for t, v in hp]
    p.append(pk(9.8, type="use_item_result", ok=True, item_id=504, aid=ME))
    h = tb.hp_economy(srt(p), 0, 30 * S, [(19 * S, 30 * S)])
    assert (h["damage"], h["potion_hp"], h["potions"]) == (100, 450, 1)
    assert (h["regen_not_sitting"], h["regen_sitting"]) == (11, 22)
    assert h["sitting_s"] == 11.0 and h["regen_sitting_hp_s"] == round(22 / 11, 3)


# --- a whole session -----------------------------------------------------------------------------


def a_session() -> tuple[list[dict], list[dict]]:
    """Two kills 20 s apart, with a walk (search), a loot, an idle stretch and a sit between."""
    p = [*a_fight(),
         pk(6.1, type="floor_item_appear", floor_id=1, item_id=7053, x=12, y=10, kind="fall"),
         move(7.0, (10, 10), (11, 10)),
         pk(7.2, type="pickup_request", floor_id=1), pk(7.3, type="pickup_result", ok=True,
                                                           item_id=7053, amount=1),
         move(8.0, (11, 10), (15, 10)),  # 4 cells: ~0.6 s of walking
         pk(10.0, type="act", src_gid=ME, target_gid=ME, kind="sit", action=2, damage=0),
         pk(15.0, type="act", src_gid=ME, target_gid=ME, kind="stand", action=3, damage=0),
         appear(15.0, 8, 16, 10, WARRIOR), hit(20.0, 8, ME, 0),
         hit(21.0, ME, 8, 300), hit(24.0, 8, ME, 80), hit(25.0, ME, 8, 300),
         died(26.0, 8)]  # fmt: skip
    evs = [ev(0, "run_start", char="rogue"), ev(19.0, "scan", ms=500), ev(30, "run_end")]
    return srt(p), evs


def test_a_session_budget_sums_to_its_window_and_counts_per_kill() -> None:
    p, evs = a_session()
    r = tb.analyse(p, evs, 0, 30 * S)
    b = {c: v["s"] for c, v in r["budget"].items()}
    assert abs(sum(b.values()) - 30.0) < 0.2
    assert r["kills"] == 2 and r["kills_h"] == 240.0
    assert b["fight"] == 3.0 + 5.0 and b["rest"] == 5.0 and b["loot"] > 0
    assert r["cycle"]["n"] == 1 and r["cycle"]["total"]["median"] == 20.0
    assert r["hits_taken"] == 2 and r["hits_per_kill"] == 1.0 and r["damage_per_kill"] == 96.0
    assert r["attempts_on_us"] == 4 and r["unanswered_attackers"]["monsters"] == 0
    assert r["time_to_kill_s"]["median"] == 4.0  # 3 s and 5 s
    assert r["approach_by"] == {"attacked": 2}  # each swung at us first (1 s, 20 s)
    assert r["rest_check_s"]["sitting_packets"] == 5.0
    assert r["runner_activity_by_cause_s"]["idle_around_rest"]["scan"] == 0.5  # 18.5-19 s
    assert r["walking"]["cells"] == 5
    assert set(r["causes_s"]) == set(tb.CAUSES)
    assert abs(sum(r["causes_s"].values()) - 30.0) < 0.2


def test_pooling_sums_and_retakes_the_rates() -> None:
    p, evs = a_session()
    r = tb.analyse(p, evs, 0, 30 * S)
    pooled = tb.pool([r, r])
    assert pooled["kills"] == 4 and pooled["seconds"] == 60.0 and pooled["kills_h"] == 240.0
    assert pooled["cycle"]["n"] == 2 and pooled["hits_per_kill"] == 1.0
    assert pooled["per_kill_s"] == r["per_kill_s"]


def test_losses_are_additive_and_the_cumulative_rate_reaches_the_target() -> None:
    target = {"per_kill_s": {"fight": 5.0, "rest": 1.0, "idle": 4.0}}
    bot = {"per_kill_s": {"fight": 5.0, "rest": 30.0, "idle": 25.0}}
    rows = tb.losses(target, bot, "per_kill_s")
    assert [r["cause"] for r in rows] == ["rest", "idle", "fight"]
    assert sum(r["lost_s_per_kill"] for r in rows) == 60.0 - 10.0
    assert rows[0]["kills_h_if_only_this_matched"] == round(3600 / 31.0, 1)
    assert rows[0]["share_of_gap"] == 0.58
    assert rows[-1]["kills_h_cumulative"] == 360.0  # the target's own 3600 / 10


def test_sustain_buys_the_net_hp_back_by_sitting_or_potions() -> None:
    row = {"kills": 10, "kills_h": 200.0,
           "per_kill_s": {"fight": 5.0, "approach": 1.0, "loot": 0.0, "rest": 0.0, "search": 8.0,
                          "idle": 4.0},
           "hp": {"damage": 600, "regen_not_sitting": 200}}  # fmt: skip
    s = tb.sustain(row, 4.0, 400.0)
    assert s["net_hp_per_kill"] == 40.0 and s["rest_needed_s_per_kill"] == 10.0
    assert s["kills_h_sustained_by_sitting"] == round(3600 / 28.0, 1)
    assert s["potions_h_at_own_rate"] == 20.0


# --- the route -----------------------------------------------------------------------------------


def square(n: int = 40, x0: int = 10, y0: int = 10) -> list[tuple[int, int]]:
    """A clockwise square lap (x east, y north): north edge west -> east, then down, then back."""
    top = [(x0 + i, y0 + n) for i in range(n)]
    right = [(x0 + n, y0 + n - i) for i in range(n)]
    bottom = [(x0 + n - i, y0) for i in range(n)]
    left = [(x0, y0 + i) for i in range(n + 1)]
    return top + right + bottom + left


def test_waypoints_keep_the_corners_and_space_8_to_15_cells() -> None:
    cells = square()
    idx = tb.waypoints(cells)
    wps = [cells[i] for i in idx]
    assert (50, 50) in wps and (50, 10) in wps and (10, 10) in wps  # the corners
    gaps = [tb.cheb(a, b) for a, b in zip(wps, wps[1:], strict=False)]
    assert all(tb.WP_MIN <= g <= tb.WP_MAX for g in gaps[:-1])
    assert tb.signed_area(wps) < 0  # clockwise with y north
    dense = tb.densify(wps, loop=True)
    assert max(tb.route_dist(c, dense) for c in cells) == 0
    assert tb.route_dist((30, 45), dense) == 5


def test_a_lap_ends_when_the_walk_comes_back_near_its_start() -> None:
    cells = square() + [(10 + i, 50) for i in range(1, 30)]  # the second lap begins
    assert tb.lap_end(cells, away=30, back=3) == 160 - 3  # (10, 47): 3 cells from the start
    assert tb.lap_end([(0, 0), (5, 5)], away=30) is None


def test_despike_drops_an_out_and_back_detour() -> None:
    wps = [(0, 0), (10, 0), (20, 0), (20, 12), (21, 1), (30, 0), (40, 0)]
    assert tb.despike(wps) == [(0, 0), (10, 0), (20, 0), (21, 1), (30, 0), (40, 0)]
    assert tb.turn_deg((0, 0), (1, 0), (2, 0)) == 0.0
    assert round(tb.turn_deg((0, 0), (1, 0), (1, 1))) == 90


def test_snap_moves_a_waypoint_off_the_grid_to_a_walked_cell_near_it() -> None:
    walk = np.ones((20, 20), dtype=bool)
    walk[5, 5] = False  # walkable[y, x]
    wps, moved = tb.snap([(5, 5), (8, 8)], walk, [(5, 5), (6, 7), (7, 5)])
    assert wps == [(6, 7), (8, 8)] or wps == [(7, 5), (8, 8)]
    assert moved[0][0] == [5, 5]
    g = tb.gat_check([[5, 5], [8, 8]], [(5, 5), (6, 6)], walk)
    assert g == {"waypoints_not_walkable": [[5, 5]], "leg_cells_walkable_share": 0.5}


def test_the_route_file_is_json_with_its_waypoints() -> None:
    doc = {"source": "x", "map": "gef_fild10", "kind": "loop",
           "waypoints": [[1, 2], [3, 4], [5, 6]]}  # fmt: skip
    text = tb.route_json(doc, per_line=2)
    assert json.loads(text) == doc and text.count("\n") == 9


def test_the_committed_route_file_loads_and_is_a_clockwise_loop() -> None:
    """config/routes/gef_fild10-batt-loop.json: waypoints only (with its source), each a whole
    cell on the map, consecutive ones 1..2 x WP_MAX cells apart (a dropped spike joins its two
    neighbours into one leg), clockwise."""
    p = Path(__file__).resolve().parents[3] / "config" / "routes" / "gef_fild10-batt-loop.json"
    doc = json.loads(p.read_text())
    assert set(doc) == {"source", "map", "kind", "waypoints"} and doc["kind"] == "loop"
    wps = [tuple(w) for w in doc["waypoints"]]
    assert len(wps) >= 30 and all(len(w) == 2 and all(isinstance(v, int) for v in w) for w in wps)
    assert all(0 <= v < 400 for w in wps for v in w)
    legs = [tb.cheb(a, b) for a, b in zip(wps, [*wps[1:], wps[0]], strict=True)]
    assert all(1 <= g <= 2 * tb.WP_MAX for g in legs)
    assert tb.signed_area(wps) < 0
