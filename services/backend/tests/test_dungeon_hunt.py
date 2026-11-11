"""dungeon_hunt.py (dungeon@1, Batt 2026-10-22, demonstrations 3.98): the pure sustain rules of the
three strategies, the defend-scan ring, the triggers, and the runner's isolation (pixels in)."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402

A, B, C = (dh.STRATEGIES[k] for k in "ABC")


def test_a_potions_below_60_and_flies_below_25_or_on_a_fast_fall_under_60() -> None:
    st = dh.Sustain()
    assert dh.sustain(st, 0.0, 0.70, 1.0, A) == []
    assert [w for w, _ in dh.sustain(st, 0.2, 0.58, 1.0, A)] == ["potion"]
    assert dh.sustain(st, 0.4, 0.58, 1.0, A) == []  # inside the 0.7-s gap, no rise
    st2 = dh.Sustain()
    assert [w for w, _ in dh.sustain(st2, 0.0, 0.24, 1.0, A)] == ["fly"]  # the escape, alone
    st3 = dh.Sustain()
    dh.sustain(st3, 0.0, 0.90, 1.0, A)
    dh.sustain(st3, 1.0, 0.80, 1.0, A)
    # 0.90 -> 0.70 in 2 s = 526 HP/s, but HP is still >= 60 %: no rate escape for A
    assert [w for w, _ in dh.sustain(st3, 2.0, 0.70, 1.0, A)] == []
    st4 = dh.Sustain()
    dh.sustain(st4, 0.0, 0.75, 1.0, A)
    assert [w for w, _ in dh.sustain(st4, 2.0, 0.55, 1.0, A)] == ["fly"]  # fast and under 60 %


def test_b_drinks_only_in_an_emergency_and_rests_after_a_fight() -> None:
    st = dh.Sustain()
    assert dh.sustain(st, 0.0, 0.45, 1.0, B) == []  # A would drink here; B does not
    assert [w for w, _ in dh.sustain(st, 0.1, 0.29, 1.0, B)] == ["potion"]
    assert [w for w, _ in dh.sustain(dh.Sustain(), 0.0, 0.19, 1.0, B)] == ["fly"]
    assert dh.rest_wanted(B, 0.59, None) and not dh.rest_wanted(B, 0.61, None)
    assert not dh.rest_wanted(A, 0.10, None)  # A never rests


def test_c_heals_under_60_until_80_while_sp_pays_and_rests_only_when_it_cannot() -> None:
    st = dh.Sustain()
    assert dh.sustain(st, 0.0, 0.65, 1.0, C) == []
    assert [w for w, _ in dh.sustain(st, 0.1, 0.58, 1.0, C)] == ["heal"]
    assert dh.sustain(st, 0.5, 0.68, 1.0, C) == []  # Heal's 1-s after-cast delay
    assert [w for w, _ in dh.sustain(st, 1.3, 0.68, 0.8, C)] == ["heal"]  # still under 80 %
    assert dh.sustain(st, 2.5, 0.81, 0.7, C) == []  # healed past 80 %: done
    assert dh.sustain(dh.Sustain(), 0.0, 0.50, 0.10, C) == []  # 10 % SP < 34 SP: no Heal
    assert not dh.rest_wanted(C, 0.50, 0.50)  # SP pays: Heal, no rest
    assert dh.rest_wanted(C, 0.50, 0.05)  # SP short: rest as B
    st2 = dh.Sustain()
    assert [w for w, _ in dh.sustain(st2, 0.0, 0.28, 1.0, C)] == ["potion"]  # emergency first


def test_the_defend_ring_starts_orthogonal_and_covers_every_neighbour() -> None:
    r1 = dh.ring(1)
    assert len(r1) == 8 and set(r1) == {(x, y) for x in (-1, 0, 1) for y in (-1, 0, 1)} - {(0, 0)}
    assert all(abs(x) + abs(y) == 1 for x, y in r1[:4])
    assert len(dh.ring(2)) == 16


def test_an_hp_drop_of_two_points_in_a_second_and_a_half_is_a_hit() -> None:
    assert dh.hp_dropped([(0.0, 0.90), (1.0, 0.88)], 1.0)
    assert not dh.hp_dropped([(0.0, 0.90), (1.0, 0.89)], 1.0)
    assert not dh.hp_dropped([(0.0, 0.90), (2.0, 0.80)], 2.0)  # the old read is out of the window


def test_the_walk_target_is_the_farthest_fitting_cell_within_reach() -> None:
    path = [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)]
    assert dh.walk_target(path, 3, lambda c: True) == (3, (3, 0))
    assert dh.walk_target(path, 9, lambda c: c[0] <= 2) == (2, (2, 0))
    assert dh.walk_target(path, 3, lambda c: False) is None
    assert dh.nearest_spot([(10, 10), (3, 4)], (0, 0)) == (3, 4)


def test_the_pickup_hand_counts_only_without_a_sword() -> None:
    assert dh.pickup_seen({"pickup": 0.95, "sword": 0.40})
    assert not dh.pickup_seen({"pickup": 0.95, "sword": 0.80})
    assert not dh.pickup_seen({"pickup": 0.85, "sword": 0.10})


def test_the_rest_spots_are_on_the_route_grid_outside_the_zones() -> None:
    spots = dh.load_rest_spots()
    assert spots and all(len(s) == 2 for s in spots)
    import map_zones as mz

    zones = mz.load(dh.MAP, shape=(200, 200))
    assert zones is not None and not any(mz.in_no_enter(zones, s) for s in spots)


def test_the_runner_reads_no_packets_at_decision_time() -> None:
    """Pixels in: the module imports no packet code; the session's packets are WRITTEN after the
    run (record_session.write_packets, as survive.py does) and never read by it."""
    src = (ROOT / "scripts" / "dungeon_hunt.py").read_text()
    names = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    assert not {n for n in names if "packets" in n or n.endswith("_judge")}, names
    assert "read_packets" not in src and "packets.jsonl" not in src
    assert src.count("write_packets(") == 1


def test_the_etc_clear_drops_the_first_non_empty_slot() -> None:
    assert dh.first_item(["empty", "unknown", "loot"]) == 1
    assert dh.first_item(["empty", "empty"]) is None


def test_the_loot_list_model_groups_chained_kills_and_needs_the_item_on_the_floor() -> None:
    """dungeon_loot_list (Batt 11:5x, offline): a fight = kills <= 8 s apart; an item is reached
    by the list when it lies within 2 cells of our cell at ANY kill of its fight and is still on
    the floor when the loot step starts; by the sweep when it fell during the fight, in view."""
    import dungeon_loot_list as dl

    s = dl.NS
    assert dl.fights([0, 5 * s, 20 * s, 21 * s]) == [[0, 5 * s], [20 * s, 21 * s]]
    track = [(0, (100, 100)), (4 * s, (106, 100))]  # we moved 6 cells east between the kills
    west = {"t_fall": 0, "cell": (99, 101), "t_end": None}  # fell at the FIRST kill, west
    got = dl.reach(west, [0, 5 * s], track)
    assert got["list"] and got["sweep"]  # the last kill's 3 x 3 would have missed it
    gone = {"t_fall": 0, "cell": (99, 101), "t_end": 2 * s}  # a looter took it mid-fight
    assert not dl.reach(gone, [0, 5 * s], track)["list"]
    far = {"t_fall": 0, "cell": (90, 100), "t_end": None}
    assert not dl.reach(far, [0, 5 * s], track)["list"]


def test_the_no_entry_ring_is_counted_by_its_red() -> None:
    import numpy as np

    crop = np.zeros((64, 64, 3), np.uint8)
    assert dh.red_px(crop) == 0
    crop[10:20, 10:15] = (40, 30, 220)  # BGR: a red ring's pixels
    assert dh.red_px(crop) == 50 >= dh.NOENTRY_RED
    crop[30:40, 30:40] = (60, 170, 250)  # a torch's orange is not the ring's red
    assert dh.red_px(crop) == 50
    st: dict[str, float] = {"ang": 0.0}
    dh.turn_heading(st)
    assert abs(st["ang"] - 1.5707963) < 1e-6


def test_a_box_on_our_own_crusader_is_not_a_monster() -> None:
    assert dh.self_box(641, 300)  # 3.98 run 1's false trigger: (628,277)-(661,312)
    assert not dh.self_box(606, 325)  # a monster on the west neighbour cell
    assert not dh.self_box(900, 300)


def test_a_stalled_target_is_carved_out_of_the_route_grid() -> None:
    import numpy as np

    m = np.zeros((10, 10), dtype=bool)
    dh.carve(m, (1, 1), 2)
    assert m[0:4, 0:4].all() and m.sum() == 16  # clipped at the map's edge
    dh.carve(m, (8, 8), 2)
    assert m[6:10, 6:10].all() and m.sum() == 32


def test_a_route_starts_even_when_our_own_cell_is_carved() -> None:
    """Amendment D (3.98 run 2: 20 min standing at 45,60): a stall's carve can cover the cell we
    then stand on; A* from a cell off the grid returned None forever. route() holds our cell."""
    import numpy as np

    g = np.ones((12, 12), dtype=bool)
    carved = np.zeros_like(g)
    dh.carve(carved, (3, 3), 2)  # covers (2, 2) .. (5, 5): our cell (4, 4) among them
    p = dh.route(g, carved, (4, 4), (10, 10))
    assert p is not None and p[0] == (4, 4) and p[-1] == (10, 10)


def test_melee_ring_watches_the_cells_ahead_and_queues_each_sword_once() -> None:
    """MELEE-RING (Batt 2026-10-22 13:4x): the pointer rests on the ring cells AHEAD of the walk;
    while fighting, every SWORD cell joins the queue once."""
    assert dh.forward_cells((10, 10), (11, 10)) == [(1, 0), (1, -1), (1, 1)]  # east, +-45
    assert dh.forward_cells((10, 10), (10, 11))[0] == (0, 1)  # north (map y grows north)
    assert dh.forward_cells((10, 10), (10, 10)) == []
    q: list[dict[str, object]] = []
    assert dh.queue_add(q, (5, 5), 1.0) and not dh.queue_add(q, (5, 5), 2.0)
    assert dh.queue_add(q, (6, 5), 2.0) and [x["cell"] for x in q] == [(5, 5), (6, 5)]


def test_the_melee_ring_check_tells_kept_from_stopped_and_retargeted() -> None:
    """melee_ring_check (offline): a hover window while swinging keeps the swing when our next act
    is on the same target; a 1.5-s silence is a stop; a request on another unit is a retarget;
    a window that starts after the swing ended, or holds the kill, says so."""
    import melee_ring_check as mc

    s = mc.NS
    acts = [(0, 7), (int(0.73 * s), 7), (int(1.46 * s), 7)]
    assert mc.scan_verdict(int(0.5 * s), int(1.0 * s), acts, {}, [])["verdict"] == "kept"
    acts_stop = [(0, 7), (int(0.73 * s), 7)]
    assert mc.scan_verdict(int(1.0 * s), int(1.5 * s), acts_stop, {}, [])["verdict"] == "stopped"
    assert mc.scan_verdict(int(3.0 * s), int(4.0 * s), acts, {}, [])["verdict"] == "not_swinging"
    died = mc.scan_verdict(int(1.0 * s), int(2.0 * s), acts, {7: int(1.8 * s)}, [])
    assert died["verdict"] == "died_inside"
    rq = mc.scan_verdict(int(0.5 * s), int(1.0 * s), acts, {}, [int(0.6 * s)], [9])
    assert rq["verdict"] == "retargeted" and rq["requests"] == 1
    acts2 = [(0, 7), (int(0.8 * s), 9)]
    assert mc.scan_verdict(int(0.5 * s), int(1.0 * s), acts2, {}, [])["verdict"] == "retargeted"


H = dh.STRATEGIES["H"]


def test_h_heals_in_a_fight_under_50_and_between_fights_like_batt() -> None:
    # in a fight (not calm): no Heal at 70 %; under 50 % while SP pays
    assert dh.sustain(dh.Sustain(), 0.0, 0.70, 1.0, H) == []
    assert [w for w, _ in dh.sustain(dh.Sustain(), 0.0, 0.45, 0.5, H)] == ["heal"]
    # between fights (calm): Batt's rhythm -- under 93 % with SP >= 85 %
    assert [w for w, _ in dh.sustain(dh.Sustain(), 0.0, 0.92, 0.90, H, calm=True)] == ["heal"]
    assert dh.sustain(dh.Sustain(), 0.0, 0.92, 0.80, H, calm=True) == []  # SP short of 85 %
    assert dh.sustain(dh.Sustain(), 0.0, 0.95, 1.0, H, calm=True) == []  # HP not down enough
    st = dh.Sustain()
    dh.sustain(st, 0.0, 0.90, 1.0, H, calm=True)
    assert dh.sustain(st, 0.5, 0.90, 1.0, H, calm=True) == []  # the after-cast delay (1.1 s)
    # potions only in an emergency, and the escape as B
    assert [w for w, _ in dh.sustain(dh.Sustain(), 0.0, 0.29, 0.05, H)] == ["potion"]
    assert [w for w, _ in dh.sustain(dh.Sustain(), 0.0, 0.19, 1.0, H)] == ["fly"]


def test_h_rests_under_80_hp_or_30_sp_and_stands_when_full_with_sp_back() -> None:
    assert dh.rest_wanted(H, 0.79, 1.0) and dh.rest_wanted(H, 1.0, 0.29)
    assert not dh.rest_wanted(H, 0.81, 0.31)
    assert not dh.rest_done(H, 100, 35) and dh.rest_done(H, 99, 40)
    assert dh.rest_done(B, 100, None) and not dh.rest_done(B, 99, None)


def test_back_into_the_area_takes_the_nearest_area_cell() -> None:
    import numpy as np

    m = np.zeros((10, 10), bool)
    m[2:4, 7:9] = True
    assert dh.nearest_in(m, (2, 2)) == (7, 2)
    assert dh.nearest_in(m, (8, 3)) == (8, 3)
    assert dh.nearest_in(np.zeros((5, 5), bool), (1, 1)) is None


def test_the_plant_sweep_covers_the_area_on_a_lattice_nearest_first() -> None:
    import numpy as np

    walk = np.ones((40, 40), bool)
    walk[20, 22] = False
    cells = dh.plant_cells((20, 20, 4, 4), (30, 20), walk, n=50)
    assert all((x - 20) % 2 == 0 and (y - 20) % 2 == 0 for x, y in cells)
    assert (22, 20) not in cells  # not walkable
    assert dh.cheb2(cells[0], (30, 20)) == 6 and cells[0][0] == 24  # the nearest column first
    assert len(dh.plant_cells((20, 20, 4, 4), (30, 20), walk)) == dh.PLANT_HOVERS


def test_amendment_i_h_carries_ten_potions_and_never_rests_overweight() -> None:
    """4.00 Amendment I (p1): 50 White Potions (750 of 4,150) left loot room for ~15 min before
    50 % weight, where the server stops natural regen and four 5-min rests gave 0 HP."""
    assert H["potions_to"] == 10 and dh.POTIONS_TO == 40  # the other strategies unchanged
    assert dh.REGEN_STOP == 0.50
    src = (ROOT / "scripts" / "dungeon_hunt.py").read_text()
    assert "and not overweight" in src and '"why": "overweight"' in src


def test_overweight_is_the_red_weight_line() -> None:
    """Amendment I: the client paints Basic Info's weight line RED at >= 50 % (the digit reader
    returns None there); 4 live frames gave 0 red px below 50 % and 281 at 2,110 / 4,150."""
    import numpy as np

    from poring_env import weight as wt

    x, y, w, h = wt.rect_at()
    frame = np.full((720, 1280, 3), 255, np.uint8)
    frame[y + 5 : y + 15, x + 40 : x + 60] = (0, 0, 0)  # black text: not overweight
    assert not dh.overweight_red(frame)
    frame[y + 5 : y + 15, x + 60 : x + 70] = (20, 20, 230)  # 100 red px (BGR)
    assert dh.overweight_red(frame)
    frame2 = np.full((720, 1280, 3), 255, np.uint8)
    frame2[200:300, 200:300] = (20, 20, 230)  # red elsewhere (a monster): not the weight line
    assert not dh.overweight_red(frame2)


def test_amendment_j_a_jump_is_more_than_the_walk_could_cover() -> None:
    """pi3 (23:56): 21 cells in ~4.5 s of a plant strike is a WALK; a teleport is not."""
    assert not dh.is_jump((95, 57), (74, 54), 4.5)  # 21 cells, reach 4.5 / 0.15 + 5 = 35
    assert dh.is_jump((95, 57), (74, 54), 0.2)  # the same 21 cells in 0.2 s: a jump
    assert not dh.is_jump((95, 57), (80, 57), 0.1)  # 15 cells: under JUMP_CELLS, never a jump
    assert dh.is_jump((30, 160), (180, 20), 6.0)  # across the map in 6 s: a map change


def test_loot_v2_hovers_changed_cells_first_then_the_list_and_skips_known_empty_ones() -> None:
    here = (10, 10)
    changed = [(20.0, (14, 10)), (40.0, (12, 10))]
    plan = {(11, 10), (12, 10), (13, 13)}
    order = dh.loot_order(changed, plan, here, {}, [])
    assert order[:2] == [((12, 10), "changed"), ((14, 10), "changed")]  # nearest changed first
    assert [c for c, w in order if w == "list"] == [(11, 10), (13, 13)]  # then the list, once each
    # hovered empty at t 5 -> skipped, unless a kill within 2 cells came AFTER that hover
    assert (11, 10) not in [c for c, _w in dh.loot_order(changed, plan, here, {(11, 10): 5.0}, [])]
    again = dh.loot_order(changed, plan, here, {(11, 10): 5.0}, [((12, 11), 6.0)])
    assert (11, 10) in [c for c, _w in again]
    far = dh.loot_order(changed, plan, here, {(11, 10): 5.0}, [((20, 20), 6.0)])
    assert (11, 10) not in [c for c, _w in far]


def test_dungeon5_a_box_spot_is_ignored_after_two_box_fights_without_a_sword() -> None:
    """Batt 2026-10-23, decision 4. The REAL case, 4.00's ci5 (20261023T032727): the v1 box at the
    Black Mushroom spawn, the same box (523.1, 307.3, 552.7, 331.1) 58 times beside our cell
    162,136 (the last walk's start), no strike from any of those fights."""
    from poring_dataset import camera as cam

    cj = json.loads(
        (ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json").read_text()
    )
    camera = cam.camera_from_json(cj["camera"])
    uv = camera.project(np.asarray(dh.BOX_GRID, float), np.zeros(len(dh.BOX_GRID)))
    assert dh.nearest_rel(uv, dh.BOX_GRID, dh.FOOT_PX) == (0, 0)  # our own cell
    c = dh.nearest_rel(uv, dh.BOX_GRID, ((523.1 + 552.7) / 2, 331.1))
    assert c == (-3, 1)
    spot = (162 + c[0], 136 + c[1])
    s = dh.BoxSpots()
    assert not s.ignored(spot)
    assert s.miss(spot) == 1 and not s.ignored(spot)  # one miss: still believed
    assert s.miss((spot[0] + 1, spot[1])) == 2 and s.ignored(spot)  # the foot jitters a cell
    assert not s.ignored((spot[0] + 3, spot[1]))  # another spot stays live
    off = dh.BoxSpots(after=0)
    off.miss(spot)
    off.miss(spot)
    assert not off.ignored(spot)


def test_dungeon5_defaults_no_plant_sweep_box_spots_on_dungeon_icon_bar(monkeypatch) -> None:
    """Batt 2026-10-23, decisions 4 / 6 / 7 are the defaults of a plain run."""
    import survive as sv

    got = {}

    def fake_run(a):
        got["a"] = a
        return 0

    monkeypatch.setattr(dh, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["dungeon_hunt.py", "run", "--strategy", "H", "--seed", "1"])
    assert dh.main() == 0
    a = got["a"]
    assert a.plant_sweep is False and a.box_ignore == dh.BOX_IGNORE_AFTER == 2
    assert a.ag_match == sv.AG_MATCH_DUNGEON == 40.0
    # dungeon@6 (2026-10-24) adds --char / --map / --steal / tag banking; a plain run is still
    # dungeon@5's: the Crusader on orcsdun01, no steal, tags banked only off orcsdun01; dungeon@7
    # changes only what --steal does
    assert dh.VERSION == "dungeon@8.7"  # .1 position-unread fly, .2 no stand toggle on a hit,
    # .3 the stock read from the hotbar, .4 the stock guard in the run, .5 the safe end, .6 the
    # no-entry ring + one-cell no-entry carve + uncarve before a dead end's Fly Wing, .7 no walk
    # click straight north (column_dodge)
    assert (a.char, a.map, a.steal, a.bank_tags) == ("crusader", "orcsdun01", False, None)
    assert a.clear_map is False  # dungeon@8: @killmonster2 only when asked (Amendment A4)


def test_dungeon6_characters_keys_and_stock() -> None:
    """2026-10-24: the Thief's F3 is Steal (no Auto Guard, no Heal key), its max HP and stock are
    its own, and its setup never drops the Etc tab (Batt's Rough Oridecon / Elunium are Etc)."""
    cru, thf = dh.CHARS_CONF["crusader"], dh.CHARS_CONF["thief"]
    assert cru["keys"] is dh.KEYS and cru["autoguard"] and cru["clear_etc"]
    assert thf["keys"]["steal"] == "F3" and "autoguard" not in thf["keys"]
    assert "heal" not in thf["keys"] and not thf["autoguard"] and not thf["clear_etc"]
    assert (thf["max_hp"], thf["potions_to"], thf["wings_to"]) == (952, 10, 10)
    # the HP-rate trigger scales by the character's max HP: 10 % in 1 s
    hist = [(0.0, 0.9), (1.0, 0.8)]
    assert round(dh.rate_hp_s(hist, 1.0, max_hp=952)) == 95
    assert round(dh.rate_hp_s(hist, 1.0)) == 526  # the Crusader's 5260


def test_dungeon7_steal_rules() -> None:
    """Batt 2026-10-24 ~16:0x (4.04): ONE Steal first on EVERY monster while the SP pays for it
    (Steal costs 10 SP; the Thief has 112), plain strikes below; a monster is stolen from ONCE
    (pc_steal_item's steal_flag), so a target near a recent steal is not tried again; the cast =
    the SP percent falling; success = the weight readout rose."""
    assert dh.STEAL_SP == 10 and dh.CHARS_CONF["thief"]["max_sp"] == 112
    assert dh.steal_sp_pct(112) == 10  # ceil(1100 / 112): 11.2 SP floored, 10.6 rounded
    assert dh.steal_ready(10, 112) and dh.steal_ready(100, 112)
    assert not dh.steal_ready(9, 112) and not dh.steal_ready(None, 112)
    assert not dh.steal_ready(100, None)  # a character without SP never steals
    assert dh.steal_cast(100, 91) and dh.steal_cast(14, 5)  # 10 of 112 SP = 8.9 points
    assert not dh.steal_cast(100, 96) and not dh.steal_cast(100, None)
    assert not dh.steal_cast(None, 50)


def test_the_steal_cast_fall_scales_with_max_sp_and_keeps_the_thiefs_five() -> None:
    # dungeon@8: 10 SP is 8.9 % of the Thief's 112 but 3.0 % of the Rogue's 336
    assert dh.steal_sp_fall(112) == dh.STEAL_SP_FALL == 5
    assert dh.steal_sp_fall(336) == 2
    assert dh.steal_cast(100, 97, 336) and dh.steal_cast(30, 28, 336)
    assert not dh.steal_cast(100, 99, 336) and not dh.steal_cast(100, 96, 112)
    assert dh.steal_sp_pct(336) == 4  # ceil(100 * 11 / 336): the gate to open with a Steal


def test_the_rogue_is_the_thiefs_character_with_its_own_job_and_numbers() -> None:
    rogue, thief = dh.CHARS_CONF["rogue"], dh.CHARS_CONF["thief"]
    assert rogue["job"] == "rogue" and rogue["data"] == "thief"
    # Base 99 since 2026-11-05 (xmas_dun02; 2209 / 341 at the held Base 63, 2146 / 336 at 62)
    assert (rogue["max_hp"], rogue["max_sp"]) == (5070, 530)
    # dungeon@9.27 (--bare-steal): the Rogue's dagger on F5 is her one key the Thief lacks
    assert {k: v for k, v in rogue["keys"].items() if k != "equip"} == thief["keys"]
    assert rogue["keys"]["steal"] == "F3" and rogue["keys"]["equip"] == "F5"
    assert rogue["clear_etc"] is False and "data" not in thief
    done = [((100, 100), 10.0)]
    assert not dh.steal_forgotten(done, (101, 102), 20.0)  # within 2 cells, 10 s later
    assert dh.steal_forgotten(done, (103, 100), 20.0)  # 3 cells away: another monster
    assert dh.steal_forgotten(done, (100, 100), 10.0 + dh.STEAL_FORGET_S + 1)
    assert dh.steal_forgotten(done, None, 20.0)
    assert dh.stolen([570, 2430], [571, 2430]) is True
    assert dh.stolen([570, 2430], [570, 2430]) is False
    assert dh.stolen([570, 2430], [555, 2430]) is False  # a potion drunk meanwhile
    assert dh.stolen(None, [571, 2430]) is None


def test_dungeon7_steal_ring_order() -> None:
    """After the Steal walk the target stands beside us, on its own side: the major axis's
    neighbour first, the diagonal second (the other path shape), then the rest of ring 1."""
    ring1 = {(x, y) for x in (-1, 0, 1) for y in (-1, 0, 1)} - {(0, 0)}
    for rel in [(5, 2), (3, 3), (-2, 5), (1, -1), (0, 0), (0, -4), (-6, -1)]:
        order = dh.steal_ring_order(rel)
        assert len(order) == 8 and set(order) == ring1, rel
    assert dh.steal_ring_order((5, 2))[:2] == [(1, 0), (1, 1)]
    assert dh.steal_ring_order((-2, 5))[:2] == [(0, 1), (-1, 1)]
    assert dh.steal_ring_order((-6, -1))[:2] == [(-1, 0), (-1, -1)]
    assert dh.steal_ring_order((0, -4))[:2] == [(0, -1), (-1, -1)]  # then the nearest, by (x, y)
    assert dh.steal_ring_order((3, 3))[0] == (1, 1)  # a diagonal: one prediction
    assert dh.steal_ring_order((3, 3))[1] in {(0, 1), (1, 0)}
    assert dh.steal_ring_order((1, -1))[0] == (1, -1)  # already beside us: no walk, it stays


def test_dungeon6_rest_spots_per_map(tmp_path) -> None:
    """orcsdun01's rest spots stay required; a map without a file rests where it is."""
    assert dh.rest_spots_for("pay_fild07", tmp_path) == []
    (tmp_path / "config" / "dungeon").mkdir(parents=True)
    (tmp_path / "config" / "dungeon" / "pay_fild07.json").write_text('{"rest_spots": [[1, 2]]}')
    assert dh.rest_spots_for("pay_fild07", tmp_path) == [(1, 2)]
    try:
        dh.rest_spots_for("orcsdun01", tmp_path / "nowhere")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("orcsdun01 without its rest spots must refuse")


def test_loot_rhythm_is_v2s_order_with_batts_per_fight_bounds(monkeypatch) -> None:
    """4.02 (Batt 2026-10-23, decision 2): --loot rhythm = v2's order, 2.5 s and 2 pickups per
    fight (his demo: moved on 2.4 s after a fight, median, with one pickup)."""
    assert dh.LOOT_RHYTHM_BUDGET_S == 2.5 and dh.LOOT_RHYTHM_PICKS == 2
    assert dh.LOOT_FIGHT_BUDGET_S == 10.0  # v2's own budget is unchanged
    got = {}

    def fake_run(a):
        got["a"] = a
        return 0

    monkeypatch.setattr(dh, "run", fake_run)
    argv = ["dungeon_hunt.py", "run", "--strategy", "H", "--seed", "1", "--loot", "rhythm"]
    monkeypatch.setattr(sys, "argv", argv)
    assert dh.main() == 0 and got["a"].loot == "rhythm"
    src = (ROOT / "scripts" / "dungeon_hunt.py").read_text()
    assert 'loot_v2 = a.loot in ("v2", "rhythm")' in src  # rhythm runs v2's step


def test_the_rest_spots_name_is_bound_once_in_run() -> None:
    """4.01 Amendment C (li1 attempt 1, 22:55): dungeon@5's box spots were bound to `spots`, the
    name of the REST spots, and the first rest crashed (`nearest_spot(spots, ...)`: 'BoxSpots'
    object is not iterable). Every binding of `spots` inside run() must stay the rest spots."""
    tree = ast.parse((ROOT / "scripts" / "dungeon_hunt.py").read_text())
    run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run")
    bound = [
        t
        for n in ast.walk(run)
        if isinstance(n, ast.Assign | ast.AnnAssign)
        for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
        if isinstance(t, ast.Name) and t.id == "spots"
    ]
    assert len(bound) == 1
    assert "box_spots = (" in (ROOT / "scripts" / "dungeon_hunt.py").read_text()


def test_rest_sits_where_it_stands_on_a_map_without_rest_spots() -> None:
    """4.03 Amendment C: t1 (pay_fild07, no rest spots) never sat: 782 rest_go -> search."""
    assert dh.rest_sit_why(None, False, 0.0) == "no rest spot: sit where we stand"
    assert dh.rest_sit_why((5, 5), True, 0.0) == "at rest spot"
    assert dh.rest_sit_why((5, 5), False, 1.0) is None  # still walking to it
    assert dh.rest_sit_why((5, 5), False, dh.REST_WALK_MAX_S + 1) == "rest spot not reached"
    assert dh.nearest_spot([], (1, 1)) is None


def test_the_setup_waits_for_the_identity_after_each_warp() -> None:
    """dungeon@8 (4.05 pilot2, 2026-10-25 20:28): the line after the setup's @warp read the map's
    LOADING screen, its identity check refused and nothing was sent; the setup now waits (<= 20 s)
    until Basic Info reads the character again after every @warp."""
    src = Path(dh.__file__).read_text()
    i = src.index('if "@warp" in cmd:  # dungeon@8 (4.05 pilot2)')
    assert 'while not cr.check(screen, conf["job"], crk)' in src[i : i + 600]
    assert dh.WARP_READY_S == 20.0


def test_the_run_end_warps_home_after_a_death_too() -> None:
    """dungeon@8 (4.05 a1, 2026-10-25 22:04): @alive revived the Rogue on the spot beside the Orc
    Lord that had killed it, and it died again; the end warp to the clear stand now follows the
    death step as it follows every other end."""
    src = Path(dh.__file__).read_text()
    i = src.index('for cmd in ("@alive", "@heal"):')
    tail = src[i : i + 1500]
    assert "@warp {CLEAR_STAND[0]}" in tail and 'if reason != "death"' not in tail


def test_an_unread_position_costs_a_fly_wing_before_it_ends_the_run() -> None:
    """dungeon@8.1 (4.05 a5, 2026-10-26 00:21): the minimap readout over a bright roof never read
    and the run stopped at 30 s. Now: no read for POS_FLY_S -> a Fly Wing (<= POS_FLY_MAX a run,
    POS_FLY_S apart), and every Fly Wing restarts the 30-s window."""
    assert (dh.POS_FLY_S, dh.POS_FLY_MAX) == (20.0, 3) and dh.POS_FLY_S < 30.0
    src = Path(dh.__file__).read_text()
    i = src.index('"why": "pos_unread"})')
    block = src[i - 400 : i + 900]
    assert 'press("fly", "pos_unread")' in block and "pos_flies += 1" in block
    assert "tick - max(last_pos_t, fly_at) > 30.0" in block


def test_damage_while_sitting_never_presses_the_stand_toggle() -> None:
    """dungeon@8.2 (4.05 a6, 2026-10-26 00:3x): the server stands a sitting player up when hit
    (pinned pc.cpp pc_damage -> pc_setstand), so a "stand" press after a hit is a toggle that SITS
    the character back down; every potion and Fly Wing was then refused ("cannot use this item
    while sitting") and the run sat for 20 min. After damage the runner only records it."""
    src = Path(dh.__file__).read_text()
    assert 'press("stand", "hit while sitting")' not in src
    i = src.index('"why": "damage (the server stood us up)"')
    block = src[i - 500 : i]
    assert "if sitting and (tick - last_taken <= FIGHT_TAKEN_S or hp_dropped(" in block
    assert 'press("stand"' not in block


def test_the_stock_plan_tops_up_from_the_hotbar_and_refuses_an_unreadable_count() -> None:
    """dungeon@8.3 (4.05 a10, 2026-10-26 05:45): the DB's last save still showed a9's Fly Wings,
    so the setup added none; the hotbar showed an EMPTY slot (0). The plan adds from the drawn
    count, and an unreadable count stops the setup instead of guessing."""
    assert dh.stock_plan({504: 8, 601: 0}, {504: 10, 601: 10}) == {504: 2, 601: 10}
    assert dh.stock_plan({504: 14, 601: 10}, {504: 10, 601: 10}) == {504: 0, 601: 0}
    import pytest

    with pytest.raises(ValueError):
        dh.stock_plan({504: 10, 601: None}, {504: 10, 601: 10})
    assert dh.hotbar_slot("F1") == 0 and dh.hotbar_slot("F2") == 1
    with pytest.raises(ValueError):
        dh.hotbar_slot("Insert")
    assert dh.CHARS_CONF["rogue"]["hotbar_stock"] is True
    assert {dh.CHARS_CONF["rogue"]["keys"][k] for k in dh.STOCK_ITEMS} == {"F1", "F2"}


def test_the_npc_guard_refuses_fight_clicks_near_an_npc_only() -> None:
    """dungeon@9.0b (c2, 2026-10-26 12:53): a strike beside gef_fild10's bulletin board (69,340)
    opened its dialog. Fight clicks (strike / burst / Steal / loot) are refused within
    NPC_NO_FIGHT cells of an NPC; walk clicks and an unknown position are not refused here."""
    npcs = [(69, 340), (73, 340)]
    assert dh.npc_guard_blocks((68, 337), npcs, "strike")  # where c2 stood
    assert dh.npc_guard_blocks((77, 333), npcs, "loot")  # 7 / 4 cells: within 8
    assert not dh.npc_guard_blocks((82, 330), npcs, "strike")  # 9 cells from the Kafra
    assert not dh.npc_guard_blocks((68, 337), npcs, "walk")
    assert not dh.npc_guard_blocks(None, npcs, "strike")
    assert not dh.npc_guard_blocks((68, 337), [], "strike")
    assert {"strike", "strike_burst", "steal", "loot"} == dh.NPC_GUARDED


def test_the_miss_cue_starts_a_fight_like_a_hit_but_never_while_sitting() -> None:
    """dungeon@9.1 (docs/planning/gef10-miss-cue.md): the Miss drawn at our attacker is read in
    the HP loop (not while sitting: no stand toggle on a miss, 8.2) and a swing within
    FIGHT_TAKEN_S starts a fight; OFF by default and recorded in the run's fixes."""
    src = (Path(dh.__file__)).read_text()
    assert 'if miss_tpl is not None and not sitting and mode != "after":' in src
    assert "(hit_now or dropped or swing_now or near_ is not None)" in src
    assert '"by": "miss_cue"' in src
    a = dh.argparse.Namespace(plant_sweep=False, box_ignore=2, ag_match=40.0, walk_trust=False,
                              rest="spot", npc_guard=False, miss_cue=True)  # fmt: skip
    assert dh.fixes_of(a)["miss_cue"] is True
    assert dh.fixes_of(a)["miss_cue_rule"] == "9.1b"
    off = dh.argparse.Namespace(**{**vars(a), "miss_cue": False})
    assert "miss_cue_rule" not in dh.fixes_of(off)


def test_a_miss_read_before_the_fights_end_never_restarts_it() -> None:
    """9.1b (4.05 c6: 152 engages from 17 swings): a Miss still drawn after a quiet kill restarted
    the fight every 0.1 s. Only a Miss read AFTER the end starts the next fight; both fight-end
    paths set the floor."""
    end = 100.0
    assert dh.swing_engages(100.1, last_swing=99.9, swing_floor=-1e9)  # 9.1's rule: engages
    assert not dh.swing_engages(100.1, last_swing=99.9, swing_floor=end)  # read before the end
    assert dh.swing_engages(101.0, last_swing=100.9, swing_floor=end)  # a new read after it
    assert not dh.swing_engages(104.0, last_swing=101.4, swing_floor=end)  # older than 2.5 s
    src = (Path(dh.__file__)).read_text()
    assert src.count('mode, swing_floor = "after", tick') == 2
    assert "swing_now = swing_engages(tick, last_swing, swing_floor)" in src


def test_batts_no_rest_strategy_never_sits_and_drinks_below_40() -> None:
    """Batt 2026-10-26 ~14:5x: no sitting at all, HP kept above 20 % with White Potions."""
    p = dh.STRATEGIES["P"]
    assert not dh.rest_wanted(p, 0.21, 0.5) and not dh.rest_wanted(p, 0.05, 0.0)
    assert p["potion_below"] == 0.40 and p["fly_below"] == 0.15 and p["potions_to"] == 30


def test_p2_flies_on_a_swarm_drain_below_half() -> None:
    """Amendment U: c5's swarm -- 74 % -> 43 % in ~3 s (~190 HP/s) -> P2 flies; P did not."""
    hist = [(0.0, 0.74), (0.5, 0.69), (1.0, 0.63), (1.5, 0.58), (2.0, 0.53), (2.5, 0.47)]
    for name, flies in (("P2", True), ("P", False)):
        st = dh.Sustain()
        st.hist.extend(hist[:-1])
        got = dh.sustain(st, 3.0, 0.43, 1.0, {**dh.STRATEGIES[name], "max_hp": 2146})
        assert (got[:1] == [("fly", got[0][1])] if got else False) is flies, (name, got)


def test_a_stock_at_zero_ends_the_run_but_an_unread_count_never_does() -> None:
    """dungeon@8.4 (Amendment Y: c7 used its 10th Fly Wing at 28.5 min and hunted on with no
    escape): the hotbar count re-read after a press; 0 ends the run, None is retried."""
    assert dh.stock_out({504: 12, 601: 0}) == 601
    assert dh.stock_out({504: 0}) == 504
    assert dh.stock_out({504: 3, 601: None}) is None
    assert dh.stock_out({}) is None
    assert dh.STRATEGIES["P2"]["wings_to"] == 20 and dh.STRATEGIES["P2"]["potions_to"] == 30
    src = (Path(dh.__file__)).read_text()
    assert "stock_due[STOCK_ITEMS[what]] = time.monotonic() + STOCK_READ_S" in src
    assert 'reason = f"stock_out: item {out_item} reads 0 on the hotbar"' in src
    assert 'w_to = int(strat.get("wings_to") or conf["wings_to"])' in src
    assert dh.VERSION.startswith("dungeon@8.")


def test_the_end_flies_first_when_still_in_a_fight_or_low() -> None:
    """dungeon@8.5 (c10, 19:57:44: HP 907 -> 357 in 0.4 s at the time box, dead 0.96 s after
    run_end): a hit within 3.5 s, an HP fall, or HP under half = a Fly Wing before the end warp;
    never after a death, never into a hard bar's unknown UI."""
    now = 100.0
    calm = [(99.0, 0.9), (99.8, 0.9)]
    assert dh.end_escape_needed(now, 98.0, calm, "time_box")  # hit 2 s ago
    assert dh.end_escape_needed(now, -1e9, [(99.0, 0.42), (99.8, 0.17)], "time_box")  # falling
    assert dh.end_escape_needed(now, -1e9, [(99.8, 0.4)], "stock_out: item 504 reads 0")
    assert not dh.end_escape_needed(now, -1e9, calm, "time_box")
    assert not dh.end_escape_needed(now, 99.9, calm, "death")
    assert not dh.end_escape_needed(now, 99.9, calm, "hard_bar: unknown UI state {}")
    src = (Path(dh.__file__)).read_text()
    assert "if end_escape_needed(time.monotonic(), last_taken, st.hist, reason):" in src


def test_loot_trim_caps_v1_hovers_at_nine_and_never_sweeps() -> None:
    """gef10-eyes-loot.md E1 (the idle study: 80 of 84 pickups within the first 9 hovers; Batt's
    18:12:56 clip: ~10 s of hovers after the last pickup): v1's list and order, capped hovers."""
    assert dh.LOOT_TRIM_HOVERS == 9 and dh.LOOT_MAX_HOVERS == 30
    src = (Path(dh.__file__)).read_text()
    assert 'loot_trim = a.loot == "trim"' in src
    assert "loot_trim and n_hov >= LOOT_TRIM_HOVERS" in src
    assert "and here is not None and not loot_trim:" in src  # no sweep
    assert src.count("n_hov += 1") == 1  # an out-of-view cell is not a hover
    assert '"trim"]' in src and 'default="v1"' in src  # OFF by default


def test_the_rogue_is_held_at_its_level() -> None:
    """Batt 2026-10-26 ~20:5x: hold the Rogue at 63 (it levelled 62 -> 63 by hunting): a higher DB
    level is lowered by the setup, a lower one is never raised. Batt 2026-11-05 (xmas_dun02): base
    AGI 99 + DEX 99 -> Base 99; the char conf carries Lv 99's HP / SP (its status window)."""
    assert dh.level_lines(63, 63) == [] and dh.level_lines(62, 63) == []
    assert dh.level_lines(65, 63) == ["@baselevelup -2"]
    assert dh.level_lines(70, None) == []
    rogue = dh.CHARS_CONF["rogue"]
    assert rogue["level_hold"] == 99 and rogue["max_hp"] == 5070 and rogue["max_sp"] == 530
    assert dh.level_lines(99, 99) == []
    src = (Path(dh.__file__)).read_text()
    assert 'setup = [*level_lines(level_db, conf.get("level_hold")), "@heal"]' in src


def test_long_legs_continue_through_the_next_waypoint_and_stay_off_by_default() -> None:
    """gef10-idle-study.md 6.1: 52-56 % of the walk clicks were capped at the waypoint and the
    Rogue stood ~0.4 s at nearly every click. --walk-through continues the leg to waypoint i + 1
    (its waypoint marked passed once it is behind us); --walk-ahead sets the click distance."""
    leg, leg2 = [(0, 0), (1, 0), (2, 0)], [(2, 0), (3, 1), (4, 2)]
    assert dh.through_path(leg, leg2) == [(0, 0), (1, 0), (2, 0), (3, 1), (4, 2)]
    assert dh.through_path(leg, None) == leg and dh.through_path(leg, [(2, 0)]) == leg
    assert dh.through_path(leg, [(9, 9), (3, 1)]) == leg  # not joined at the waypoint
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True}  # fmt: skip
    off = dh.fixes_of(dh.argparse.Namespace(**base, walk_ahead=dh.WALK_AHEAD, walk_through=False))
    assert "walk_ahead" not in off and "walk_through" not in off  # old records unchanged
    on = dh.fixes_of(dh.argparse.Namespace(**base, walk_ahead=12, walk_through=True))
    assert on["walk_ahead"] == 12 and on["walk_through"] is True
    src = (Path(dh.__file__)).read_text()
    # 9.15b split the call (ahead_ = MR_WALK_AHEAD if mr else a.walk_ahead): behaviour unchanged
    assert "ahead_ = MR_WALK_AHEAD if mr else a.walk_ahead" in src
    assert "wt_ = walk_target(goal_path, ahead_, fits)" in src
    assert "pass_waypoint(here)  # --walk-through: its waypoint is behind us now" in src
    # the offline sim's bug (2026-10-26 21:2x): a through-leg ending NEAR its end must pass its
    # waypoint before the replan, or the replan routes back to it (oscillation at gef_fild10 wp 64)
    assert 'if patrol and near_end and wp_st["through"] is not None:' in src
    assert dh.WALK_AHEAD == 7


def test_the_walk_timer_is_an_option_and_recorded_only_when_changed() -> None:
    """gef10-idle-study.md 4a: decisions take ~0.9 s and fire every WALK_EVERY_S from their start,
    so the Rogue stood after nearly every click; --walk-every shortens the timer (OFF = 1.2 s)."""
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True, "walk_ahead": dh.WALK_AHEAD,
            "walk_through": False}  # fmt: skip
    assert "walk_every" not in dh.fixes_of(dh.argparse.Namespace(**base, walk_every=1.2))
    assert dh.fixes_of(dh.argparse.Namespace(**base, walk_every=0.8))["walk_every"] == 0.8
    src = (Path(dh.__file__)).read_text()
    # 9.13d added "and not loot_settling(...)" after it (False unless --kill-gap looted)
    assert "and tick - last_walk >= a.walk_every" in src and dh.WALK_EVERY_S == 1.2


def _ring_crop(
    floor_bgr: tuple[int, int, int], ring: bool, shift: tuple[int, int] = (0, 0)
) -> np.ndarray:
    """An 80 x 80 BGR cursor crop (hotspot at 40, 40): a floor, and the no-entry ring (pure red,
    ~2 px wide, radius 18 at (+4.5, +11.5) from the hotspot, the slash through it) when asked."""
    a = np.empty((80, 80, 3), np.uint8)
    a[:] = floor_bgr
    if ring:
        yy, xx = np.mgrid[0:80, 0:80]
        cx, cy = 40 + dh.RING_CX + shift[0], 40 + dh.RING_CY + shift[1]
        d = np.hypot(xx - cx, yy - cy)
        slash = (np.abs((xx - cx) + (yy - cy)) <= 1.5) & (d < dh.RING_R)
        a[(np.abs(d - dh.RING_R) <= 1.0) | slash] = (10, 5, 235)
    return a


def test_dungeon86_the_no_entry_sign_is_read_by_its_ring_not_by_any_red() -> None:
    """xmas_dun02 (p2 + X2): the old cue counted the ORANGE floor tiles (G 53-90) as the ring's red
    and carved 254 of 894 walk decisions (28 %); the ring is pure red on a fixed circle."""
    orange = (25, 80, 225)  # BGR: an xmas_dun02 floor tile (R 225, G 80, B 25)
    floor = _ring_crop(orange, ring=False)
    assert dh.red_px(floor[8:72, 8:72]) >= dh.NOENTRY_RED  # the old cue fires on the floor alone
    assert not dh.ring_seen(dh.ring_score(floor, 40, 40))  # the ring rule does not
    for bg in (orange, (0, 0, 0), (120, 140, 150)):  # on the floor, over the void, on stone
        sc = dh.ring_score(_ring_crop(bg, ring=True), 40, 40)
        assert dh.ring_seen(sc) and sc[1] == 0, (bg, sc)
    sc = dh.ring_score(_ring_crop(orange, ring=True, shift=(2, -3)), 40, 40)
    assert dh.ring_seen(sc) and (sc[2], sc[3]) == (2, -3)  # within RING_SHIFT
    carpet = _ring_crop((10, 5, 235), ring=False)  # pure red everywhere (a red carpet, a stocking)
    sc = dh.ring_score(carpet, 40, 40)
    assert sc[0] >= dh.RING_IN_MIN and sc[1] > dh.RING_OUT_MAX and not dh.ring_seen(sc)
    assert dh.ring_score(np.zeros((80, 80, 3), np.uint8), 40, 40) == (0, 0, 0, 0)


def test_dungeon86_a_no_entry_carves_one_cell_and_a_dead_end_forgets_the_carves_first() -> None:
    """p2 / X2's dead ends: 5 x 5 carves from false no-entry reads sealed the edge loop. A no-entry
    now carves its cell alone; a dead end first forgets every carve (once a minute), then flies."""
    m = np.zeros((10, 10), dtype=bool)
    dh.carve(m, (4, 4), dh.NOENTRY_CARVE_R)
    assert m.sum() == 1 and m[4, 4]
    assert dh.dead_end_step(0, 1e9) == "fly"  # nothing to forget: the map itself has no route
    assert dh.dead_end_step(7, dh.UNCARVE_MIN_S) == "uncarve"
    assert dh.dead_end_step(7, dh.UNCARVE_MIN_S - 1) == "fly"  # forgot them under a minute ago
    src = (Path(dh.__file__)).read_text()
    assert "carve(carved, c, NOENTRY_CARVE_R)" in src and "carve(carved, c, CARVE_R)" in src
    i_un, i_fly = src.index('counts["uncarve"] += 1'), src.index('press("fly", why_s)')
    assert i_un < i_fly  # the uncarve branch runs before the dead end's Fly Wing
    assert "noentry_red=RING_IN_MIN" in src and "noentry_red=NOENTRY_RED" not in src


def test_dungeon87_a_walk_target_straight_north_moves_one_cell_aside() -> None:
    """p3's packets: no move request for 93 of 95 clicks at (0, +7), but for 32 of 33 at (+-1, +7);
    gef_fild10 (0, +7) 108 / 325 unsent, (+-1, +7) 0 / 88, (0, +5) 0 / 24."""
    here = (13, 27)
    every = lambda c: True  # noqa: E731
    assert dh.column_dodge(here, (13, 34), (14, 40), every) == ((14, 34), "side+1")
    assert dh.column_dodge(here, (13, 34), (11, 40), every) == ((12, 34), "side-1")  # toward nxt
    assert dh.column_dodge(here, (13, 34), None, every) == ((14, 34), "side+1")
    no_east = lambda c: c != (14, 34)  # noqa: E731
    assert dh.column_dodge(here, (13, 34), (14, 40), no_east) == ((12, 34), "side-1")
    only_column = lambda c: c[0] == 13  # noqa: E731  # a one-cell corridor: 5 up is still sent
    assert dh.column_dodge(here, (13, 34), (13, 40), only_column) == ((13, 32), "short")
    assert dh.column_dodge(here, (13, 34), (13, 40), lambda c: False) == ((13, 34), "none")
    for c in [(13, 32), (14, 34), (12, 34), (13, 20), (20, 27)]:  # 5 up, aside, south, east
        assert dh.column_dodge(here, c, None, every) == (c, None)
    assert dh.column_dodge(here, (13, 33), None, every)[1] == "side+1"  # 6 up: 5 / 6 unsent in p3
    src = (Path(dh.__file__)).read_text()
    assert "c, dodge = column_dodge(here, c, nxt_, usable)" in src
    i_dodge = src.index("c, dodge = column_dodge(")
    between = src[i_dodge : src.index("res = hover(u, v)\n", i_dodge)]
    assert "rel = (c[0] - here[0], c[1] - here[1])" in between  # the hover reads the moved cell
    assert dh.VERSION == "dungeon@8.7"


def test_a_full_lap_of_routeless_skips_flies_at_once() -> None:
    """gef10-idle-study.md 4c (c7: 412 skips, 45.8 s standing until the idle watchdog): a full lap
    of route-less skips in a row is a dead end and flies at once; a routed goal resets the count."""
    assert not dh.dead_end(79, 80) and dh.dead_end(80, 80) and not dh.dead_end(5, 0)
    src = (Path(dh.__file__)).read_text()
    assert 'wp_st["skips"] += 1  # route-less skips in a row (dead_end)' in src
    assert 'elif goal_path:\n                        wp_st["skips"] = 0' in src
    assert 'why_s = "dead_end" if patrol and dead_end(wp_st["skips"], len(wps)) else "idle"' in src


def test_a_patrol_on_xmas_dun02_starts_on_the_loop_never_in_the_maze() -> None:
    """Batt 2026-11-05: walk the EDGE clockwise. The search area's centre on xmas_dun02 is the maze
    next to the only exit warp: a patrol starts at PATROL_START (on the loop), each cell on the
    route grid and through the three stand-cell checks, else refused before any input."""
    import pytest

    assert dh.PATROL_START["xmas_dun02"] == ((7, 21), (114, 23))
    okr = np.ones((260, 260), bool)
    ok_check = lambda m, cells: None  # noqa: E731
    assert dh.patrol_start("xmas_dun02", okr, ok_check) == (7, 21)
    okr[21, 7] = False  # the start off the grid -> the fallback
    assert dh.patrol_start("xmas_dun02", okr, ok_check) == (114, 23)
    with pytest.raises(SystemExit, match="no patrol start"):
        dh.patrol_start("xmas_dun02", okr, lambda m, cells: "in a warp span")
    src = (Path(dh.__file__)).read_text()
    assert "if patrol and map_ in PATROL_START:" in src
    assert "start = patrol_start(map_, okr, map_prep.stand_check)" in src
    assert '"max_hp": conf["max_hp"], "max_sp": conf.get("max_sp"),' in src


def test_the_xmas_dun02_patrol_start_passes_on_the_real_map() -> None:
    """The real grids (the client GAT in /dev/shm, the zones, the KB's warps): START passes."""
    import pytest

    gat = Path("/dev/shm/poring-lab-tmp/gat/data/xmas_dun02.gat")
    if not gat.exists() or not (ROOT / "data/kb/warps.json").exists():
        pytest.skip("xmas_dun02's GAT or the KB is not on this host")
    import anim_region as ar
    import map_prep
    import map_routes as mroutes
    import map_zones as mz

    from poring_dataset import gat as gatmod

    stand = np.asarray(ar.stand_grid("xmas_dun02", gatmod.parse(gat.read_bytes())), dtype=bool)
    okr = mroutes.route_grid(stand, mz.load("xmas_dun02", shape=stand.shape))
    assert dh.patrol_start("xmas_dun02", okr, map_prep.stand_check) == (7, 21)
    assert not okr[130, 131]  # the arrival cell, one step from the exit warp: inside the zone


def test_the_run_shows_the_battle_log_tab_before_its_reader_starts() -> None:
    """2026-11-05: two chat tabs; battle_log.py live reads only a SHOWN Battle Log."""
    src = (Path(dh.__file__)).read_text()
    i_gate = src.index('ui_gate.ensure_clear(agent_raw, screen, why="dungeon-start")')
    i_tab = src.index('cl_.select_tab(agent_raw, screen, "battle")')
    i_reader = src.index('blt = hf.BattleLogTail(out / "battle_log_live.jsonl"')
    assert i_gate < i_tab < i_reader


def test_a_light_strip_read_counts_only_when_a_second_read_agrees() -> None:
    """X1b round 2: selfpos's opaque-glyph fallback (mode "light") is confirmed by the previous
    read within CONFIRM_S and the walk's reach; base reads count as before."""
    from types import SimpleNamespace as R

    pc = dh.PosConfirm()
    assert pc.accept(0.0, R(xy=(79, 93), mode="light")) is None  # nothing before it
    assert pc.accept(0.3, R(xy=(79, 94), mode="light")) == (79, 94)  # 1 cell in 0.3 s: walkable
    assert pc.accept(0.6, R(xy=(79, 84), mode="light")) is None  # 10 cells in 0.3 s: a misread
    assert pc.accept(0.9, R(xy=(79, 95), mode="light")) is None  # its predecessor was the misread
    assert pc.accept(1.2, R(xy=(79, 95), mode="light")) == (79, 95)
    assert pc.accept(3.0, R(xy=(79, 96), mode="light")) is None  # 1.8 s since: too old to confirm
    assert pc.accept(3.1, R(xy=(80, 96), mode="base")) == (80, 96)  # a base read: as before
    assert pc.accept(3.4, R(xy=(80, 97), mode="light")) == (80, 97)  # confirmed by the base read
    assert pc.accept(3.5, R(xy=None, mode="light_failed")) is None
    assert pc.unconfirmed == 4  # at 0.0, 0.6, 0.9 and 3.0 s


def test_each_hp_read_logs_its_readout_outcome() -> None:
    """2026-11-06 (logging only): the HP read says why it has no new position -- the reader's live
    failure reasons, for its next round."""
    from poring_env import selfpos as sp

    assert dh.read_outcome(None, None) == "settle"
    assert dh.read_outcome(sp.Reading((7, 21), "ok"), (7, 21)) == "base"
    light = sp.Reading((7, 21), "ok", mode="light")
    assert dh.read_outcome(light, (7, 21)) == "light"
    assert dh.read_outcome(light, None) == "unconfirmed"
    assert dh.read_outcome(sp.Reading(None, "layout"), None) == "base:layout"
    failed = sp.Reading(None, "no_glyph", mode="light_failed", light_reason="half_shadow")
    assert dh.read_outcome(failed, None) == "light_failed:half_shadow"
    src = (Path(dh.__file__)).read_text()
    assert '"rd": rd_why})' in src and "rd_why = read_outcome(rd, pos)" in src


def test_the_box_watcher_takes_the_maps_model_with_a_v1_rollback() -> None:
    src = (ROOT / "scripts" / "dungeon_hunt.py").read_text()
    assert "self.det: Any = unit_detector.for_map(map_name)" in src  # T-11 (Batt 2026-11-07)
    assert "self.det = unit_detector.for_map_gpu(map_name)" in src  # dungeon@8.9, same model
    assert 'None if a.box_model == "v1" else a.map' in src
    assert 'ev({"kind": "box_model", "choice": a.box_model, **boxes.model,' in src  # + every_s
    assert '"--box-model",\n        choices=["map", "v1"],\n        default="map",' in src


def test_box_strike_hovers_the_box_centre_then_its_body_point() -> None:
    """dungeon@8.8 (rogue-xmas02.md 4M): the box itself, not the 8 cells around us."""
    assert dh.box_hover_points([600.0, 200.0, 660.0, 320.0]) == [
        (630.0, 260.0),
        (630.0, 320.0 - dh.BODY_UP),
    ]


def test_box_strike_waits_for_our_walk_to_end() -> None:
    assert dh.settle_left(10.0, 10.0) == dh.BOX_SETTLE_S
    assert abs(dh.settle_left(10.0, 10.5) - (dh.BOX_SETTLE_S - 0.5)) < 1e-9
    assert dh.settle_left(10.0, 12.0) == 0.0
    # a 7-cell path at 150 ms a cell (1.05 s) has ended by then; ~6 cells of reach
    assert dh.BOX_SETTLE_S >= 7 * 0.150 and dh.BOX_TARGET_PX > dh.BOX_NEAR_PX


def test_wait_fresh_needs_a_grab_after_the_settle() -> None:
    import threading
    import time

    bw = dh.BoxWatch.__new__(dh.BoxWatch)
    bw.lock = threading.Lock()
    bw.last = (time.monotonic() - 5.0, [])
    since = time.monotonic()
    assert bw.wait_fresh(since, 0.15) is False  # only an older grab: no

    def later() -> None:
        time.sleep(0.1)
        with bw.lock:
            bw.last = (time.monotonic(), [])

    th = threading.Thread(target=later)
    th.start()
    assert bw.wait_fresh(since, 1.0) is True
    th.join()


def test_box_strike_is_wired_once_per_box_fight_and_off_by_default() -> None:
    src = (ROOT / "scripts" / "dungeon_hunt.py").read_text()
    assert (
        '"--box-strike",\n        action=argparse.BooleanOptionalAction,\n        default=False,'
        in src
    )
    assert 'and box_fight.get("box") is not None\n' in src
    assert 'and not box_fight.get("tried")\n' in src
    assert 'box_fight["tried"] = True  # dungeon@8.8: once per box fight' in src
    assert 'strike(u_b, v_b, rel_b, "box")' in src
    # the ring scan still follows when the box target finds no SWORD
    i_box = src.index("got_b = box_target()")
    i_ring = src.index('found = scan("defend", ring(1), "sword")', i_box)
    assert i_box < i_ring


# --- dungeon@8.9: the GPU box watcher and the box target's detection on demand (rogue 4N) ------


def test_the_ab_arms_alternate_by_box_target_and_the_others_keep_their_path() -> None:
    assert [dh.box_arm("ab", k) for k in range(5)] == ["gpu", "cpu", "gpu", "cpu", "gpu"]
    assert {dh.box_arm("gpu", k) for k in range(4)} == {"gpu"}
    assert {dh.box_arm("cpu", k) for k in range(4)} == {"cpu"}


def test_the_box_flags_that_cannot_work_are_refused() -> None:
    assert dh.box_flags_refused(False, True, "cpu") == "--box-now needs --box-strike"
    assert dh.box_flags_refused(True, False, "ab") == "--box-detector ab needs --box-now"
    assert dh.box_flags_refused(True, True, "ab") is None
    assert dh.box_flags_refused(False, False, "gpu") is None  # the GPU without the strike: fine
    assert dh.box_flags_refused(False, False, "cpu") is None  # the CPU-only rollback


def test_the_box_flags_default_to_todays_behaviour() -> None:
    src = (ROOT / "scripts" / "dungeon_hunt.py").read_text()
    # the GPU by default since pilot p8 passed G1 / G2 (rogue-xmas02.md 4N; the CPU behind it)
    assert '"--box-detector",\n        choices=["cpu", "gpu", "ab"],\n        default="gpu",' in src
    flag = '"--box-now",\n        action=argparse.BooleanOptionalAction,\n        default=False,'
    assert flag in src
    assert '"cpu" if a.box_detector == "cpu" else "gpu",' in src  # then --box-every (9.11)
    # dungeon@8.9: ONE hover with --box-now (dungeon@9.5 --lead-strike adds the fallback hover)
    assert "n_hover = 1 if a.box_now else len(points)" in src
    assert "for k_, (u_, v_) in enumerate(points[:n_hover]):  # dungeon@8.9: ONE hover" in src
    assert "meta = boxes.fresh_now(arm, BOX_TARGET_WAIT_S)" in src
    assert 'boxes.det.log_path = out / "detections.jsonl"' in src  # each GPU-path detection
    # without --box-now the box target is dungeon@8.8's, unchanged
    assert "fresh = boxes.wait_fresh(t_set, BOX_TARGET_WAIT_S)" in src


class _FakeDet:
    def __init__(self) -> None:
        self.calls: list[tuple[float, str]] = []
        self.last_path, self.last_ms, self.last_reason = "", 0.0, None

    def detect(self, img: object, prefer: str = "gpu") -> list[object]:
        self.calls.append((__import__("time").monotonic(), prefer))
        self.last_path, self.last_ms = prefer, 1.0
        return []


class _FakeScreen:
    def grab(self, *region: int) -> tuple[None, object]:
        return None, np.zeros((4, 6, 4), np.uint8)


def _watch(gpu: bool = True) -> dh.BoxWatch:
    import threading
    from collections import Counter

    bw = dh.BoxWatch.__new__(dh.BoxWatch)
    bw.det, bw.gpu, bw.screen, bw.region = _FakeDet(), gpu, _FakeScreen(), (0, 0, 6, 4)
    bw.lock = threading.Lock()
    bw.cond = threading.Condition(bw.lock)
    bw.last, bw.meta, bw.paths = (0.0, []), {"kick": 0}, Counter()
    bw.alarm, bw.alarm_n = (0.0, []), 0  # 9.19 / 9.19b
    bw.kick_ev, bw.kick_seq, bw.kick_prefer = threading.Event(), 0, None
    bw.halt, bw.n, bw.n_self, bw.n_skip = threading.Event(), 0, 0, 0
    bw.th = threading.Thread(target=bw._loop, daemon=True)
    bw.th.start()
    return bw


def test_fresh_now_serves_a_kick_at_once_by_the_asked_path() -> None:
    import time

    bw = _watch()
    try:
        t0 = time.monotonic()
        while bw.n < 1 and time.monotonic() - t0 < 2:
            time.sleep(0.01)
        assert bw.det.calls[0][1] == "gpu"  # the background: the GPU
        t_call = time.monotonic()
        meta = bw.fresh_now("cpu", 1.0)
        assert meta is not None and meta["path"] == "cpu" and meta["prefer"] == "cpu"
        assert meta["t"] >= t_call  # its grab started after the request
        assert time.monotonic() - t_call < 0.5 < dh.BOX_EVERY_S  # not the 1-s rhythm's next
        meta2 = bw.fresh_now("gpu", 1.0)
        assert meta2 is not None and meta2["path"] == "gpu" and meta2["kick"] == meta["kick"] + 1
        assert bw.paths["cpu"] == 1 and bw.paths["gpu"] >= 2
    finally:
        bw.stop()


def test_fresh_now_gives_up_after_its_timeout() -> None:
    import threading

    bw = dh.BoxWatch.__new__(dh.BoxWatch)  # no loop: nothing ever serves the kick
    bw.lock = threading.Lock()
    bw.cond = threading.Condition(bw.lock)
    bw.meta, bw.kick_ev, bw.kick_seq, bw.kick_prefer = {"kick": 0}, threading.Event(), 0, None
    assert bw.fresh_now("gpu", 0.1) is None


def test_walk_stop_ring1_walked_and_false_cells() -> None:
    """dungeon@9.2 (rogue-xmas02.md 4Q, pilot p10): p9's class-D strikes were clicks on our own
    glowing body that walked us off the attacker. A ring-1 strike stops on a scrolling scene."""
    # ring 1 only: a ring-2 or box target farther away is APPROACHED (a legitimate walk)
    assert all(dh.ring1(c) for c in dh.ring(1))
    assert not any(dh.ring1(c) for c in dh.ring(2)) and not dh.ring1((0, 0))
    # walked: the last WALK_STOP_N shifts all >= WALK_STOP_PX (one spike is not a walk)
    px, n = dh.WALK_STOP_PX, dh.WALK_STOP_N
    assert n == 2 and px == 10.0
    assert not dh.walked_now([])
    assert not dh.walked_now([(px + 5, 0.0)])  # a single spike
    assert not dh.walked_now([(px + 5, 0.0), (1.0, 2.0)])  # back to still
    assert dh.walked_now([(0.0, 0.0), (px, 0.0), (0.0, -px - 1)])  # two in a row, any direction
    assert not dh.walked_now([(6.0, 6.0), (7.0, 7.0)])  # 8.5 and 9.9 px: below the bar
    assert dh.walked_now([(8.0, 8.0), (7.5, 7.5)])  # 11.3 and 10.6 px
    # the defend scan skips a walked cell for FALSE_REL_S, then tries it again
    cells = dh.ring(1)
    fr = {(0, 1): 100.0}
    assert (0, 1) not in dh.drop_false(cells, fr, 100.0 + dh.FALSE_REL_S - 0.1)
    assert dh.drop_false(cells, fr, 100.0 + dh.FALSE_REL_S + 0.1) == cells
    assert dh.drop_false(cells, {}, 0.0) == cells
    assert len(dh.drop_false(cells, fr, 101.0)) == len(cells) - 1
    # only the fight paths use it, and the burst re-clicks later so the check sees the first walk
    assert dh.WALK_STOP_BY == ("scan", "stall_scan", "box", "queue")
    assert dh.WALK_STOP_GAP_S > dh.BURST_GAP_S
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "walk_stop" not in dh.fixes_of(dh.argparse.Namespace(**base, walk_stop=False))
    assert "walk_stop" not in dh.fixes_of(dh.argparse.Namespace(**base))  # older namespaces
    on = dh.fixes_of(dh.argparse.Namespace(**base, walk_stop=True))
    assert on["walk_stop"] == [dh.WALK_STOP_PX, dh.WALK_STOP_N, dh.WALK_STOP_GAP_S, dh.FALSE_REL_S]
    src = Path(dh.__file__).read_text()
    # a walked strike takes no lock on any fight path
    assert 'if strike(u, v, c, "scan"):' in src and 'if strike(u_b, v_b, rel_b, "box"):' in src
    assert 'if strike(u2, v2, c2, "stall_scan"):' in src
    assert 'if not strike(u_q, v_q, rel_q, "queue"):' in src
    assert '"walked" if walked is not None else' in src


def test_self_recheck_box_holds_the_own_body_points_of_p9_and_p10() -> None:
    """dungeon@9.3 (rogue-xmas02.md 4R, pilot p11; Batt chose option a): the defend scan's N / S
    body points lie on the Rogue's own sprite; a sword read there must persist SELF_RECHECK_S."""
    u0, v0 = 641.0, 362.0  # her feet point: E [1, 0]'s body point (675, 336) + BODY_UP, minus 34
    for u, v in ((641, 312), (641, 302), (641, 288), (641, 279), (641, 360), (641, 324)):
        assert dh.in_self_box(u, v, u0, v0), (u, v)  # p9 / p10's class-D and own-body strikes
    for u, v in ((675, 336), (607, 336), (675, 355), (674, 313), (641, 386), (641, 250)):
        assert not dh.in_self_box(u, v, u0, v0), (u, v)  # E / W / diagonals, S's feet, far N
    assert dh.SELF_RECHECK_S == 0.4
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "self_recheck" not in dh.fixes_of(dh.argparse.Namespace(**base, self_recheck=False))
    on = dh.fixes_of(dh.argparse.Namespace(**base, self_recheck=True))
    assert on["self_recheck"] == [dh.SELF_RECHECK_S, dh.SELF_HALF_W, dh.SELF_UP, dh.SELF_DOWN]
    src = Path(dh.__file__).read_text()
    # only the defend scan, only a sword, only on our own sprite; a failed second read goes on
    assert 'and purpose == "defend"' in src and "in_self_box(u, v_, *self_uv())" in src
    assert 'if res2["verdict"] != "sword":' in src and 'verdicts["self_transient"] += 1' in src


def test_the_rogue_holds_her_etc_tab_up_to_48_percent() -> None:
    """Batt 2026-11-08 (p11 refused at 40.7 %): the Rogue starts below 48 % without a drop; every
    other non-dropping character keeps CLEAR_AT; an unread weight or the red line refuses."""
    rogue, thief = dh.CHARS_CONF["rogue"], dh.CHARS_CONF["thief"]
    assert rogue["etc_hold_max"] == 0.48 == dh.WEIGHT_MAX and not rogue["clear_etc"]
    assert dh.etc_hold_refused(989 / 2430, False, rogue) is None  # the 11-08 refusal, now a start
    assert dh.etc_hold_refused(0.48, False, rogue) == "at or over 0.48"
    assert dh.etc_hold_refused(0.41, False, thief) == f"at or over {dh.CLEAR_AT}"
    assert dh.etc_hold_refused(None, False, rogue) and dh.etc_hold_refused(0.30, True, rogue)


def test_still_strike_waits_for_a_still_scene_and_carries_the_point_the_right_way() -> None:
    """dungeon@9.4 (rogue-xmas02.md 4S, pilot p12; Batt chose option b): far strikes wait for a
    still scene; walk_sword's point is carried by the scroll (scene_shift's sign, tested here)."""
    import route_preview as rp

    px, n = dh.STILL_PX, dh.STILL_N
    assert (px, n, dh.STILL_MAX_S) == (2.0, 3, 1.5)
    assert not dh.still_now([])
    assert not dh.still_now([(0.0, 0.0), (0.0, 0.0)])  # two quiet pairs: not yet
    assert dh.still_now([(14.0, 0.0), (0.5, 0.0), (0.0, 1.0), (1.2, 1.2)])  # 3 in a row < 2 px
    assert not dh.still_now([(0.0, 0.0), (0.0, 0.0), (0.0, 2.5)])  # the last one scrolls
    # the sign: a scene moved by (+10, +6) px reads (+10, +6), so a point carried by it follows
    rng = np.random.default_rng(20261108)
    a = (rng.random((720, 1280, 3)) * 255).astype(np.uint8)
    a = np.ascontiguousarray(np.repeat(np.repeat(a[::8, ::8], 8, axis=0), 8, axis=1)[:720, :1280])
    b = np.roll(np.roll(a, 6, axis=0), 10, axis=1)
    dx, dy = rp.scene_shift(a, b)
    assert abs(dx - 10) <= 2 and abs(dy - 6) <= 2, (dx, dy)
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "still_strike" not in dh.fixes_of(dh.argparse.Namespace(**base, still_strike=False))
    assert dh.fixes_of(dh.argparse.Namespace(**base, still_strike=True))["still_strike"] == [
        dh.STILL_PX, dh.STILL_N, dh.STILL_MAX_S]  # fmt: skip
    src = Path(dh.__file__).read_text()
    # far walk_sword strikes only (ring 1 attacks in place); no SWORD after the wait: no strike
    assert 'if getattr(a, "still_strike", False) and not ring1(rel):' in src
    assert "aim = still_retarget(u, v, rel)" in src and "u2, v2 = u + dx, v + dy" in src
    assert 'if verdict != "sword":' in src and 'counts["still_lost"] += 1' in src
    # the box path's detection comes after the still scene
    i_still = src.index("still_b, waited_b, _sh = wait_still()")
    assert i_still < src.index("t_set = time.monotonic()")


def test_clear_bag_restocks_the_run_stock_after_emptying_use() -> None:
    """clear-bag (Batt 2026-11-08): with the Use tab just emptied AND read empty, the restock is
    the whole run stock whatever the hotbar draws; without it, stock_plan's rule holds."""
    import pytest

    targets = {504: 10, 601: 10}
    assert dh.bag_restock(["etc", "use", "eqp"], {504: None, 601: None}, targets) == targets
    assert dh.bag_restock(["etc"], {504: 4, 601: 10}, targets) == {504: 6, 601: 0}
    with pytest.raises(ValueError):
        dh.bag_restock(["etc", "eqp"], {504: None, 601: 3}, targets)
    assert dh.BAG_TABS == ("etc", "use", "eqp")
    assert dh.CHARS_CONF["rogue"]["potions_to"] == 10 and dh.CHARS_CONF["rogue"]["wings_to"] == 10


def test_the_rogues_own_potion_stock_outranks_the_strategy() -> None:
    """Batt 2026-11-08 (Amendment G): 10 White Potions are enough for the Rogue; P2 asks 30."""
    p2 = dh.STRATEGIES["P2"]
    assert dh.potions_target(p2, dh.CHARS_CONF["rogue"]) == 10
    assert dh.potions_target(p2, dh.CHARS_CONF["thief"]) == 30  # unchanged: the strategy's
    assert dh.potions_target(p2, dh.CHARS_CONF["crusader"]) == 30
    assert dh.potions_target({}, dh.CHARS_CONF["crusader"]) == dh.POTIONS_TO


def test_lead_strike_matches_the_sprite_and_leads_a_walker_only() -> None:
    """dungeon@9.5 (rogue-xmas02.md 4V, pilot p14; Batt: "aim for the monsters that are
    walking"): the second detection's same sprite, its velocity, the lead capped, none when it
    stands; the lead needs a still scene and the led point falls back to the current one."""
    import math

    import pytest

    assert (dh.LEAD_GAP_S, dh.LEAD_MATCH_PX, dh.LEAD_MIN_PX_S, dh.LEAD_T_S, dh.LEAD_MAX_PX) == (
        0.12, 40.0, 25.0, 0.35, 64.0)  # fmt: skip
    b1 = (100.0, 200.0, 140.0, 260.0)  # centre (120, 230)
    later = [(300.0, 200.0, 340.0, 260.0), (110.0, 200.0, 150.0, 260.0),
             (101.0, 201.0, 139.0, 261.0)]  # centres 200, 10 and 1 px from b1's  # fmt: skip
    assert dh.box_centre(b1) == (120.0, 230.0)
    assert dh.same_box(b1, later) == (101.0, 201.0, 139.0, 261.0)  # the nearest centre
    assert dh.same_box(b1, [(300.0, 200.0, 340.0, 260.0)]) is None  # 200 px away: not it
    # walking east at 100 px/s over 0.12 s: led 35 px ahead of the second box's centre
    b2 = (112.0, 200.0, 152.0, 260.0)
    lp = dh.lead_point(b1, 10.0, b2, 10.12)
    assert lp["walking"] and abs(lp["speed"] - 100.0) < 1e-6
    assert lp["lead"] == pytest.approx((35.0, 0.0)) and lp["point"] == pytest.approx((167.0, 230.0))
    # a fast sprite's lead is capped at LEAD_MAX_PX, in its own direction
    fast = dh.lead_point(b1, 0.0, (148.0, 236.0, 188.0, 296.0), 0.12)  # (48, 36) px in 0.12 s
    assert math.hypot(*fast["lead"]) == pytest.approx(64.0)
    assert fast["lead"][0] / fast["lead"][1] == pytest.approx(48 / 36)
    # standing (jitter 1 px in 0.12 s = 8 px/s): no lead, the current centre
    still = dh.lead_point(b1, 0.0, (101.0, 200.0, 141.0, 260.0), 0.12)
    assert not still["walking"] and still["lead"] == (0.0, 0.0)
    assert still["point"] == (121.0, 230.0)
    assert dh.lead_point(b1, 1.0, b1, 1.0)["speed"] == 0.0  # no time between: no velocity
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "lead_strike" not in dh.fixes_of(dh.argparse.Namespace(**base, lead_strike=False))
    assert dh.fixes_of(dh.argparse.Namespace(**base, lead_strike=True))["lead_strike"] == [
        0.12, 40.0, 25.0, 0.35, 64.0]  # fmt: skip
    src = Path(dh.__file__).read_text()
    assert 'lead_rec["why"] = "not_still"' in src  # a scrolling scene: no lead
    assert 'points = [lp["point"], now_pt] if lp["walking"] else [now_pt]' in src
    assert "n_hover = 2  # the led point, then the sprite's current point once" in src


def test_quick_drop_gives_up_a_strike_that_does_not_connect() -> None:
    """dungeon@9.6 (rogue-xmas02.md 4W, pilot p15; Batt: "give it up and go for a new monster at
    once"): no arrow / damage 2.0 s after the click -> no lock; an arrow but no hit of ours 2.0 s
    after it -> the lock drops; then the box path again, twice a fight at most."""
    assert (dh.QUICK_ARROW_S, dh.QUICK_HIT_S, dh.QUICK_RETRY) == (2.0, 2.0, 2)
    # the arrow at 10.6 s, the click at 10.0 s, none of our hits since
    assert not dh.quick_no_hit(10.6, -1e9, 10.0, 12.5)  # 1.9 s after the arrow: still waiting
    assert dh.quick_no_hit(10.6, -1e9, 10.0, 12.7)  # 2.1 s: drop
    assert not dh.quick_no_hit(10.6, 11.2, 10.0, 13.0)  # a hit of ours after the click: kept
    assert not dh.quick_no_hit(None, -1e9, 10.0, 20.0)  # no arrow (a damage end): the old rule
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "quick_drop" not in dh.fixes_of(dh.argparse.Namespace(**base, quick_drop=False))
    assert dh.fixes_of(dh.argparse.Namespace(**base, quick_drop=True))["quick_drop"] == [
        2.0, 2.0, 2]  # fmt: skip
    src = Path(dh.__file__).read_text()
    assert "burst_s = QUICK_ARROW_S if quick else BURST_MAX_S" in src
    assert "while time.monotonic() - t_c < burst_s:" in src
    assert 'quick_rearm("no_arrow")' in src and 'quick_rearm("no_hit")' in src
    assert 'box_fight["tried"] = False' in src and "if n_ >= QUICK_RETRY:" in src


def test_engage_screen_takes_any_box_in_view_nearest_first() -> None:
    """dungeon@9.7 (rogue-xmas02.md 4X, pilot p16; Batt: "strike within what the screen shows,
    the nearest monster first"): both the patrol's trigger and the box path take any box whose
    body point is in view; BoxWatch.near orders by distance; off by default."""
    assert dh.BOX_SCREEN_PX >= 2000.0  # beyond any distance on the 1280 x 720 region
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "engage_screen" not in dh.fixes_of(dh.argparse.Namespace(**base, engage_screen=False))
    assert dh.fixes_of(dh.argparse.Namespace(**base, engage_screen=True))["engage_screen"] == [
        dh.BOX_SCREEN_PX]  # fmt: skip
    src = Path(dh.__file__).read_text()
    # dungeon@9.12 added `or unreachable(here_b, foot)` (False unless --reach-check)
    assert "return (skip_b(foot) or not in_view(foot[0], foot[1] - BODY_UP)" in src
    assert "near_ = boxes.near(FOOT_PX, BOX_SCREEN_PX, BOX_FRESH_S, skip_s)" in src
    assert "near_b = (boxes.near(FOOT_PX, BOX_SCREEN_PX, BOX_TARGET_WAIT_S + 1.0," in src
    # the default paths are unchanged
    assert "near_ = boxes.near(FOOT_PX, BOX_NEAR_PX, BOX_FRESH_S, skip_b)" in src
    assert "near_b = (boxes.near(FOOT_PX, BOX_TARGET_PX, BOX_TARGET_WAIT_S + 1.0) if fresh" in src


def test_box_watch_near_orders_by_distance_and_skips() -> None:
    """BoxWatch.near (the order --engage-screen relies on): the nearest foot within max_px; a
    box ``skip`` refuses is passed over; our own sprite's box never counts."""

    class B:
        def __init__(self, x0: float, y0: float, x1: float, y1: float) -> None:
            self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

    w = dh.BoxWatch.__new__(dh.BoxWatch)
    import threading
    import time

    w.lock = threading.Lock()
    w.n_self = w.n_skip = 0
    far, near = B(100, 100, 140, 160), B(500, 250, 540, 310)  # feet (120, 160) and (520, 310)
    w.last = (time.monotonic(), [far, near])
    assert w.near(dh.FOOT_PX, dh.BOX_SCREEN_PX, 5.0) == (500, 250, 540, 310)
    assert w.near(dh.FOOT_PX, dh.BOX_SCREEN_PX, 5.0, lambda f: f[0] > 400) == (100, 100, 140, 160)
    assert w.near(dh.FOOT_PX, dh.BOX_NEAR_PX, 5.0) is None  # both beyond ~3 cells


def test_boss_guard_names_and_fits() -> None:
    """--engage-screen's boss guard (Batt 2026-11-08, Amendment J: "except the boss and its
    minions"): the names from the KB (the boss spawn + its NPC_SUMMONSLAVE ids, both name tables),
    and the Battle Log's garbled reads fitted against bosses AND the map's species."""
    spawns = {"m": [{"name": "Cruiser", "id": 1248, "boss": False},
                    {"name": "Garm Baby", "id": 1515, "boss": False},
                    {"name": "Stormy Knight", "id": 1251, "boss": True}]}  # fmt: skip
    mobs = {"1251": {"name": "Stormy Knight"}, "1515": {"name": "Baby Hatii"},
            "1607": {"name": "Christmas Goblin"}, "1248": {"name": "Cruiser"}}  # fmt: skip
    skills = {"1251": [{"info": "Stormy Knight@NPC_SUMMONSLAVE", "vals": ["1515", "", ""]},
                       {"info": "Stormy Knight@NPC_SUMMONSLAVE", "vals": ["1607"]},
                       {"info": "Stormy Knight@AL_TELEPORT", "vals": ["1248"]}]}  # fmt: skip
    bosses = dh.boss_names("m", spawns, mobs, skills)
    assert bosses == ("Baby Hatii", "Christmas Goblin", "Garm Baby", "Stormy Knight")
    assert dh.boss_names("other", spawns, mobs, skills) == ()
    species = ("Christmas Cookie", "Cookie", "Cruiser", "Myst Case")
    # the reader's REAL reads on p16 (battle_log_live.jsonl): never a boss
    for read in ("?vst Case", "Cruiser", "Christmas Coo?ie", "Coo?ie", "Someone", "??st? Case"):
        assert dh.boss_of(read, bosses, species) is None, read
    # the bosses as the same reader would garble them ('?' unread, i for l, v for y)
    assert dh.boss_of("Stor?v ?ni?ht", bosses, species) == "Stormy Knight"
    assert dh.boss_of("Garm Babv", bosses, species) == "Garm Baby"
    assert dh.boss_of("Christmas Gobiin", bosses, species) == "Christmas Goblin"
    assert dh.boss_of("Babv Hatii", bosses, species) == "Baby Hatii"
    assert dh.boss_of(None, bosses, species) is None and dh.boss_of("Cruiser", (), species) is None
    assert dh.BOSS_AVOID_S == 30.0
    src = Path(dh.__file__).read_text()
    assert 'press("fly", "boss")' in src and "and tick >= boss_until):  # a box never" in src


def test_boss_guard_names_from_the_real_kb() -> None:
    """The lab's KB (data/kb, generated locally from the pinned rAthena; skipped where absent):
    xmas_dun02's boss is Stormy Knight, its summons Garm Baby (Baby Hatii) and Christmas Goblin."""
    import json

    import pytest

    kb = Path(dh.ROOT) / "data" / "kb"
    if not (kb / "spawns.json").exists():
        pytest.skip("no local KB")
    bosses = dh.boss_names("xmas_dun02", json.loads((kb / "spawns.json").read_text()),
                           json.loads((kb / "mobs.json").read_text()),
                           json.loads((kb / "mob_skills.json").read_text()))  # fmt: skip
    assert set(bosses) == {"Stormy Knight", "Garm Baby", "Baby Hatii", "Christmas Goblin"}


def test_far_single_clicks_once_and_waits_for_the_walk_up() -> None:
    """dungeon@9.8 (rogue-xmas02.md 4Z, pilot p18): p16's far misses -- the client walks to a far
    monster first and the burst's re-click at the same screen point landed on the floor. A strike
    4+ cells away clicks once and waits 1.0 s + 0.2 s a cell (<= 3.5 s); nearer ones burst."""
    assert (dh.FAR_CELLS, dh.FAR_BASE_S, dh.FAR_PER_CELL_S, dh.FAR_MAX_S) == (4, 1.0, 0.2, 3.5)
    assert dh.far_window((3, 1)) is None and dh.far_window((0, -2)) is None
    import pytest

    assert dh.far_window((4, 0)) == pytest.approx(1.8)
    assert dh.far_window((-2, 8)) == pytest.approx(2.6)
    assert dh.far_window((12, 3)) == pytest.approx(3.4) and dh.far_window((14, 0)) == 3.5
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "far_single" not in dh.fixes_of(dh.argparse.Namespace(**base, far_single=False))
    assert dh.fixes_of(dh.argparse.Namespace(**base, far_single=True))["far_single"] == [
        4, 1.0, 0.2, 3.5]  # fmt: skip
    src = Path(dh.__file__).read_text()
    assert "if far_w is None and n < BURST_MAX and time.monotonic() - t_c >= n * gap:" in src
    assert "hit_s=QUICK_HIT_S if far_w is None else max(QUICK_HIT_S, far_w)," in src
    # the post-arrow wait of --quick-drop takes the far window
    assert not dh.quick_no_hit(10.5, -1e9, 10.0, 13.0, 3.0)  # 2.5 s after the arrow, 3.0 window
    assert dh.quick_no_hit(10.5, -1e9, 10.0, 13.6, 3.0)


def test_skip_own_cells_never_strikes_through_her_sprite() -> None:
    """dungeon@9.9 (rogue-xmas02.md 4AB, Amendment J item 2c): the defend scan skips a cell whose
    hover point is on her own sprite (in_self_box), off by default."""
    u0, v0 = dh.FOOT_PX
    assert dh.in_self_box(u0, v0 - 40, u0, v0)  # her body
    assert not dh.in_self_box(u0 + 60, v0 - 40, u0, v0)  # a diagonal neighbour's body point
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "skip_own_cells" not in dh.fixes_of(dh.argparse.Namespace(**base))
    assert dh.fixes_of(dh.argparse.Namespace(**base, skip_own_cells=True))["skip_own_cells"] == [
        dh.SELF_HALF_W, dh.SELF_UP, dh.SELF_DOWN]  # fmt: skip
    src = Path(dh.__file__).read_text()
    assert 'verdicts["own_skip"] += 1  # dungeon@9.9: never through her own sprite' in src


def test_far_approach_walks_toward_a_far_target_first() -> None:
    """dungeon@9.10 (rogue-xmas02.md 4AC): p19's 9+ cell strikes missed 26 of 28 even with one
    click; a box target 9+ cells away is walked toward (4 cells short of it) and looked at again."""
    assert (dh.APPROACH_CELLS, dh.APPROACH_KEEP, dh.APPROACH_MAX, dh.APPROACH_HOLD_S) == (
        9, 4, 2, 3.0)  # fmt: skip
    assert dh.approach_cell((10, 0)) == (6, 0)
    assert dh.approach_cell((-12, 6)) == (-8, 4)
    assert dh.approach_cell((9, -9)) == (5, -5)
    assert dh.approach_cell((3, 1)) == (0, 0)  # already within 4 cells: no walk
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "far_approach" not in dh.fixes_of(dh.argparse.Namespace(**base))
    assert dh.fixes_of(dh.argparse.Namespace(**base, far_approach=True))["far_approach"] == [
        9, 4, 2, 3.0]  # fmt: skip
    src = Path(dh.__file__).read_text()
    assert 'click_at(u_a, v_a, "approach")' in src and "last_walk_click = time.monotonic()" in src
    assert "if lock is None and not approaching:  # dungeon@9.10: no scan mid-approach" in src
    assert "nonlocal last_walk_click" in src


def test_box_every_sets_the_watchers_rhythm() -> None:
    """dungeon@9.11 (rogue-xmas02.md 4AD): --box-every sets BoxWatch's rhythm; the default (1.0 s)
    leaves the run record unchanged."""
    assert dh.BOX_EVERY_S == 1.0
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "box_every" not in dh.fixes_of(dh.argparse.Namespace(**base, box_every=1.0))
    assert dh.fixes_of(dh.argparse.Namespace(**base, box_every=0.25))["box_every"] == 0.25
    src = Path(dh.__file__).read_text()
    assert "self.kick_ev.wait(max(0.0, every - (time.monotonic() - t)))" in src
    assert 'getattr(a, "box_every", BOX_EVERY_S))' in src


def test_reach_check_skips_boxes_the_server_would_not_walk_to() -> None:
    """dungeon@9.12 (rogue-xmas02.md 4AE): pilots p16-p21 clicked monsters behind walls for
    110-153 s a run (the server never answered those walk requests); a box whose cell is not
    reachable on one click (nor any of its 8 neighbours) is passed over."""

    class G:
        xs, ys = 30, 12
        wall = {(10, y) for y in range(0, 11)}  # a wall at x=10, open only at y=11

        def nopass(self, x: int, y: int) -> bool:
            return not (0 <= x < self.xs and 0 <= y < self.ys) or (x, y) in self.wall

    g = G()
    assert dh.reach_ok(g, (5, 5), (8, 5))  # same side, a straight walk
    assert not dh.reach_ok(g, (5, 1), (14, 1))  # behind the wall: a detour over 14 steps
    assert dh.reach_ok(g, (8, 9), (12, 9))  # behind the wall but the detour is short
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "reach_check" not in dh.fixes_of(dh.argparse.Namespace(**base))
    assert dh.fixes_of(dh.argparse.Namespace(**base, reach_check=True))["reach_check"] == [
        17, 14, "9.12b"]  # fmt: skip
    src = Path(dh.__file__).read_text()
    assert "or unreachable(here_s, foot))" in src  # the trigger
    assert "or unreachable(here, f)))" in src  # the box path (engage-screen)
    assert 'raise SystemExit(f"dungeon@9.12 refused: --reach-check: {e}")' in src  # fail closed
    # 9.12b: the target cell is the client's picked cell under the box's foot
    assert "reach_pick[kp_] = picked_cell(camera, gat, here_, foot)" in src


def test_picked_cell_on_the_real_camera_and_map() -> None:
    """dungeon@9.12b: our own cell's projected point picks our own cell (flat ground), and p25's
    strike at (110, 253) -> foot (560.7, 497.9) picks (108, 242), the monster's own cell by the
    packets (the client walked toward (108, 243); the flat projection said (108, 247)). Skipped
    when the run-time GAT is absent (rule 4: never committed)."""
    import pytest

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    gat_path = cam.GAT_DIR / "xmas_dun02.gat"
    if not gat_path.exists():
        pytest.skip("no run-time GAT (generated locally)")
    cj = json.loads((ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])
    gat = gatmod.parse(gat_path.read_bytes())
    assert dh.picked_cell(camera, gat, (110, 253), dh.FOOT_PX) == (110, 253)
    assert dh.picked_cell(camera, gat, (110, 253), (560.7, 497.9)) == (108, 242)


def test_kill_gap_takes_a_stopped_hit_stream_as_the_kill() -> None:
    """dungeon@9.13c (rogue-xmas02.md 4AF): no exp line at Base 99, so after 5 of our hits on the
    lock (9.13c; 2 in p24), none for 1.5 s (our hits come every 0.47 s) is the kill; off by
    default."""
    assert (dh.KILL_GAP_S, dh.KILL_GAP_HITS) == (1.5, 5)
    assert dh.kill_gapped(5, 1.6)
    assert not dh.kill_gapped(5, 1.4)  # still within ~3 swings
    assert not dh.kill_gapped(4, 5.0)  # a short contact (p24's false kills: 2-4 hits)
    assert not dh.kill_gapped(0, 9.0)
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "kill_gap" not in dh.fixes_of(dh.argparse.Namespace(**base))
    assert dh.fixes_of(dh.argparse.Namespace(**base, kill_gap=True))["kill_gap"] == [
        1.5, 5, "9.13d", 0.8]  # fmt: skip
    src = Path(dh.__file__).read_text()
    assert 'if getattr(a, "kill_gap", False) and kill_gapped(n_lock, tick - last_ours):' in src
    assert 'ev({"kind": "kill", "by": "hit_gap"' in src
    assert "ours_ticks.append(tick)" in src
    # the quiet-kill end the exp line used (pilot 4) is what ends the fight after it
    assert 'ev({"kind": "fight_end", "kills": len(kills_seen), "why": "quiet kill"})' in src


def test_kill_gap_quiet_end_before_the_box_path_looked_is_no_miss() -> None:
    """dungeon@9.13b: with --kill-gap, a box fight the quiet-kill rule closes before box_target ran
    is not booked as a box miss (p24: 14 of 15 misses, 10 spots ignored); without it, unchanged."""
    assert dh.kill_gap_no_miss(True, {"spot": (1, 2), "n0": 3})
    assert not dh.kill_gap_no_miss(True, {"spot": (1, 2), "n0": 3, "tried": True})
    assert not dh.kill_gap_no_miss(False, {"spot": (1, 2), "n0": 3})  # the default path
    src = Path(dh.__file__).read_text()
    assert 'if kill_gap_no_miss(getattr(a, "kill_gap", False), box_fight):' in src


def test_walk_pick_needs_the_clients_picked_cell_near_and_walkable() -> None:
    """dungeon@9.15 (rogue-xmas02.md 4AM): p28-p30's walk clicks whose picked cell was off by more
    than 1 or unwalkable went unsent 17 of 39 times (others 17 of 869); off by default."""
    okr = np.ones((10, 10), dtype=bool)
    okr[5, 5] = False
    assert dh.WALK_PICK_TOL == 1
    assert dh.walk_pick_ok((3, 3), (3, 3), okr) and dh.walk_pick_ok((4, 3), (3, 3), okr)
    assert not dh.walk_pick_ok((3, 6), (3, 3), okr)  # picked 3 cells off (a raised top)
    assert not dh.walk_pick_ok((5, 5), (5, 4), okr)  # picked an unwalkable cell
    assert not dh.walk_pick_ok(None, (3, 3), okr) and not dh.walk_pick_ok((12, 3), (9, 3), okr)
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "walk_pick" not in dh.fixes_of(dh.argparse.Namespace(**base))
    assert dh.fixes_of(dh.argparse.Namespace(**base, walk_pick=True))["walk_pick"] == [1, "9.15b"]
    src = Path(dh.__file__).read_text()
    assert "if not walk_pick_ok(pc_, c, okr):" in src
    # 9.15b: with no candidate passing the pick check, the plain fits (today's click)
    assert "wt_ = walk_target(goal_path, ahead_, fits_plain)" in src


def test_loot_settle_holds_walks_until_a_fresh_position() -> None:
    """9.13d (rogue-xmas02.md 4AR): after a loot step that clicked, no walk click until a position
    read 0.8 s after it, at most 3 s (p37: 8 of 11 dropped walk clicks right after such steps)."""
    assert (dh.LOOT_SETTLE_S, dh.LOOT_SETTLE_MAX_S) == (0.8, 3.0)
    assert dh.loot_settling(10.0, 10.5, 11.0)  # the last read is too early: hold
    assert not dh.loot_settling(10.0, 10.9, 11.0)  # a read 0.9 s after the step: walk
    assert not dh.loot_settling(10.0, 9.0, 13.5)  # 3 s passed: walk anyway
    assert not dh.loot_settling(-1e9, 5.0, 11.0)  # no loot step: never holds
    src = Path(dh.__file__).read_text()
    assert "and not loot_settling(loot_settle_t, last_pos_t, tick):" in src
    assert 'counts["loot_click"] += 1' in src


def test_loot_first_holds_box_engages_and_ends_only_the_killing_fight() -> None:
    """dungeon@9.16 (rogue-xmas02.md 4AT): p38's kills lost their loot step to the next box on the
    screen, and the quiet-kill rule ended every fight begun in the 3 s after a kill at once (157
    engage / fight_end pairs in 3 min); off by default, so the default path is unchanged."""
    assert dh.box_engage_held(True, "after", True)
    assert not dh.box_engage_held(True, "after", False)  # nothing to loot: engage at once
    assert not dh.box_engage_held(True, "search", True)  # the loot step already ran
    assert not dh.box_engage_held(False, "after", True)  # the default path
    kills = [100.0]
    assert dh.quiet_kill_ends(kills, 101.0, 95.0, True)  # the fight that killed: ends
    assert not dh.quiet_kill_ends(kills, 101.0, 100.5, True)  # begun after the kill: goes on
    assert dh.quiet_kill_ends(kills, 101.0, 100.5, False)  # the default: as before
    assert not dh.quiet_kill_ends(kills, 103.5, 95.0, True)  # 3 s passed
    assert not dh.quiet_kill_ends([], 1.0, 0.0, False)
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "loot_first" not in dh.fixes_of(dh.argparse.Namespace(**base))
    assert dh.fixes_of(dh.argparse.Namespace(**base, loot_first=True))["loot_first"] == ["9.16"]
    src = Path(dh.__file__).read_text()
    # part 1: only a box waits (a hit, an HP drop or a Miss still starts the fight)
    assert "if near_ is not None and not (hit_now or dropped or swing_now) \\" in src
    assert "and box_engage_held(loot_first_on, mode, bool(loot_list)):" in src
    # part 2: the fight's start is the engage's tick
    assert "fight_t0 = tick  # 9.16 part 2" in src
    assert "if lock is None and quiet and quiet_kill_ends(kills_seen, tick, fight_t0," in src
    # part 3: the defend scan's first hand, clicked only without a hit in the last 1 s
    assert 'if vd == "pickup" and purpose == "defend" and loot_first_on and hand_at is None:' in src
    assert '"why": "scan_hand"' in src and "loot_list.append((here, time.monotonic()))" in src
    # the loot step itself is unchanged: the trim's hovers, nearest to where she stands
    assert "todo = sorted(plan - hovered, key=lambda c: (cheb2(c, here), c))" in src


def test_walk_pick_step_takes_the_pickable_step_nearest_the_goal() -> None:
    """dungeon@9.15c (rogue-xmas02.md 4AU): 7 of p38's 10 unsent walk clicks were 9.15b's plain
    fallback onto cells the client could not pick; the flag steps to a pickable one-click cell
    nearer the goal first. Off by default; 9.15b's plain click stays the last resort."""
    free = np.ones((5, 7), dtype=bool)
    free[1:4, 3] = False  # a wall with a gap at the top and the bottom
    d = dh.grid_steps(free, (6, 2))
    assert d[2, 6] == 0 and d[2, 4] == 2 and d[2, 2] == 5  # round the wall's top gap
    assert np.isinf(dh.grid_steps(free, (3, 2))).all()  # a goal on the wall: nothing reached
    early = dh.grid_steps(np.ones((50, 50), dtype=bool), (0, 0), until=[(2, 2)])
    assert early[2, 2] == 2 and np.isinf(early[49, 49])  # stops once (2, 2) has its count
    here = (1, 2)
    picked = {(2, 1), (2, 3), (4, 2)}  # the cells the client would pick right
    tried: list[tuple[int, int]] = []

    def fits(c: tuple[int, int]) -> bool:
        tried.append(c)
        return c in picked

    got = dh.pick_step(here, d, fits, lambda c: c != (4, 2), radius=4)
    assert got in {(2, 1), (2, 3)}  # (4, 2) is nearer the goal but not one click away
    assert tried[0] not in {(0, 1), (0, 2), (0, 3)}  # best first: no cell farther than us
    assert dh.pick_step(here, d, lambda c: False, lambda c: True) is None
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "walk_pick_step" not in dh.fixes_of(dh.argparse.Namespace(**base))
    rec = dh.fixes_of(dh.argparse.Namespace(**base, walk_pick=True, walk_pick_step=True))
    assert rec["walk_pick_step"] == [9, "9.15c"] and rec["walk_pick"] == [1, "9.15b"]
    src = Path(dh.__file__).read_text()
    assert '"dungeon@9.15c refused: --walk-pick-step goes with --walk-pick"' in src
    assert 'if wt_ is None and getattr(a, "walk_pick_step", False):' in src
    # the step is tried BEFORE 9.15b's plain click, which stays as it was
    i_step = src.index('if wt_ is None and getattr(a, "walk_pick_step", False):')
    i_plain = src.index("wt_ = walk_target(goal_path, ahead_, fits_plain)")
    assert i_step < i_plain
    assert 'rec_w["pick"] = pick_how' in src


def test_quiet_scan_skips_the_ring_scan_without_damage_in_5_s() -> None:
    """dungeon@9.17 (rogue-xmas02.md 4AW; Batt's clip 1: no damage in the last 5 s, no scan):
    p38-p40's defend scans with no hit on us in the 5 s before found a monster 7 times in 101.
    Off by default."""
    assert dh.QUIET_SCAN_S == 5.0
    never = -1e9
    assert not dh.scan_needed(100.0, never, never, never, False)  # nothing: skip
    assert dh.scan_needed(100.0, 96.0, never, never, False)  # hit on us 4 s ago
    assert dh.scan_needed(100.0, never, 95.5, never, False)  # our damage line 4.5 s ago
    assert dh.scan_needed(100.0, never, never, 99.0, False)  # a Miss at us
    assert dh.scan_needed(100.0, never, never, never, True)  # the HP just dropped
    assert not dh.scan_needed(100.0, 94.9, 94.0, 90.0, False)  # all older than 5 s
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "quiet_scan" not in dh.fixes_of(dh.argparse.Namespace(**base))
    rec = dh.fixes_of(dh.argparse.Namespace(**base, quiet_scan=True))
    assert rec["quiet_scan"] == [5.0, "9.17"]
    src = Path(dh.__file__).read_text()
    assert src.count("if quiet_scan_on and not scan_needed(") == 2  # the fight and the stall
    assert 'counts["quiet_scan_skip"] += 1' in src and 'counts["quiet_scan_skip_stall"] += 1' in src
    # without the flag both scans run exactly as before
    assert src.count('found = scan("defend", ring(1), "sword")') == 2


def test_boss_walk_walks_away_from_a_summon_and_flies_from_the_boss() -> None:
    """dungeon@9.18 (rogue-xmas02.md 4AZ; Batt: flee from the dog, walk away when you can): a guard
    on a summon walks to the farthest pickable one-click cell >= 8 away; the boss itself, a 3rd
    walk-away within 60 s or no cell keeps the Fly Wing. Off by default."""
    spawns = {"m": [{"id": 1251, "name": "Stormy Knight", "boss": True},
                    {"id": 1515, "name": "Garm Baby"},
                    {"id": 1249, "name": "Myst Case"}]}  # fmt: skip
    mobs = {"1251": {"name": "Stormy Knight"}, "1515": {"name": "Baby Hatii"}}
    assert dh.boss_spawn_names("m", spawns, mobs) == ("Stormy Knight",)
    assert dh.boss_walk_allowed("Garm Baby", ("Stormy Knight",), [], 100.0)
    assert not dh.boss_walk_allowed("Stormy Knight", ("Stormy Knight",), [], 100.0)  # the boss
    assert not dh.boss_walk_allowed(
        "Garm Baby", ("Stormy Knight",), [70.0, 90.0], 100.0
    )  # 2 in 60 s
    assert dh.boss_walk_allowed("Garm Baby", ("Stormy Knight",), [30.0, 90.0], 100.0)  # one is old
    here = (20, 20)
    t = dh.walk_away_target(here, lambda c: True, lambda c: True)
    assert t is not None and max(abs(t[0] - 20), abs(t[1] - 20)) == dh.BOSS_WALK_R  # the farthest
    t2 = dh.walk_away_target(
        here, lambda c: c[0] >= 20, lambda c: max(abs(c[0] - 20), abs(c[1] - 20)) <= 9
    )
    assert t2 is not None and t2[0] >= 20 and max(abs(t2[0] - 20), abs(t2[1] - 20)) == 9
    assert dh.walk_away_target(here, lambda c: True, lambda c: False) is None  # no cell: the wing
    assert dh.walk_away_target(here, lambda c: max(abs(c[0] - 20), abs(c[1] - 20)) < 8,
                               lambda c: True) is None  # nothing at least 8 away  # fmt: skip
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "boss_walk" not in dh.fixes_of(dh.argparse.Namespace(**base))
    rec = dh.fixes_of(dh.argparse.Namespace(**base, boss_walk=True, stage_mob="1515:2"))
    assert rec["boss_walk"] == [14, 8, 2.5, 2, 60.0, "9.18"] and rec["stage_mob"] == "1515:2"
    src = Path(dh.__file__).read_text()
    assert '"dungeon@9.18 refused: --boss-walk goes with --engage-screen"' in src
    assert "if boss_hit is not None and tick < boss_grace_until:" in src
    assert 'setup.append(f"@monster {int(mob_id)} {int(n_mob or 1)}")' in src
    # without a walk-away the Fly Wing path is the one it always was
    assert 'press("fly", "boss")' in src


def test_garm_fly_takes_the_wing_on_a_fresh_alarm_box_only() -> None:
    """dungeon@9.19 (rogue-xmas02.md 4BA; Batt: fly wing when a Garm Baby is SEEN): a box of an
    alarm class in a detection <= 1.5 s old takes the boss guard's Fly Wing; a model without the
    class gives no alarm box, so the flag is inert. Off by default."""
    import unit_detector as ud

    assert dh.ALARM_CLASSES == ("garm_baby",) and dh.GARM_FRESH_S == 1.5
    dog = ud.Box(100.0, 200.0, 160.0, 260.0, 0.81, "garm_baby")
    assert dh.alarm_seen((10.0, [dog]), 11.0) is dog
    assert dh.alarm_seen((10.0, [dog]), 11.6) is None  # stale
    assert dh.alarm_seen((10.0, []), 10.1) is None  # no alarm box
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "garm_fly" not in dh.fixes_of(dh.argparse.Namespace(**base))
    rec = dh.fixes_of(dh.argparse.Namespace(**base, garm_fly=True))
    assert rec["garm_fly"] == [["garm_baby"], 1.5, "9.19"]
    src = Path(dh.__file__).read_text()
    assert "alarm = [b for b in raw if b.cls in ALARM_CLASSES]  # 9.19: never struck" in src
    assert 'got = [b for b in raw if b.cls == "monster"]' in src  # only monsters are struck
    assert 'boss_hit = "Garm Baby"  # the boss guard\'s own Fly Wing path below' in src
    # the deployed model (xmas02-gb since 2026-11-10) never collapses garm_baby into "monster":
    # it is an alarm class, never a strike target
    assert "garm_baby" not in ud.MAP_MODELS["xmas_dun02"].collapse


def test_garm_confirm_waits_for_consecutive_alarm_detections() -> None:
    """dungeon@9.19b (rogue-xmas02.md 4BD; Batt 2026-11-10, option (a)): with --garm-confirm 2 the
    Fly Wing waits for alarm boxes in 2 CONSECUTIVE detections. p44's one false garm_baby box (a
    Cruiser under the Rogue) stood in a single detection: never a wing. A dog boxed in detections
    in a row (G0) flies on the second. The default (1) is 9.19 unchanged."""
    import unit_detector as ud

    assert dh.GARM_CONFIRM == 1
    dog = ud.Box(100.0, 200.0, 160.0, 260.0, 0.81, "garm_baby")
    # the streak: consecutive detections with an alarm box, the new one included
    n = 0
    seq_false = [False, False, True, False, False]  # p44 08:39:57-08:40:01: one box, one detection
    fired = []
    for i, has in enumerate(seq_false):
        n = dh.alarm_streak(n, has)
        a_ = (float(i), [dog] if has else [])
        fired.append(dh.alarm_seen(a_, float(i) + 0.1, streak=n, need=2) is not None)
    assert fired == [False] * 5
    n = 0
    seq_dog = [False, True, True, True]  # a dog in view for detections in a row
    fired = []
    for i, has in enumerate(seq_dog):
        n = dh.alarm_streak(n, has)
        a_ = (float(i), [dog] if has else [])
        fired.append(dh.alarm_seen(a_, float(i) + 0.1, streak=n, need=2) is not None)
    assert fired == [False, False, True, True]
    # need=1 (the default) is 9.19: the first box flies
    assert dh.alarm_seen((0.0, [dog]), 0.1, streak=1) is dog
    assert dh.alarm_seen((0.0, [dog]), 0.1) is dog
    # a stale streak does not fly either
    assert dh.alarm_seen((0.0, [dog]), 1.6, streak=3, need=2) is None
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    rec = dh.fixes_of(dh.argparse.Namespace(**base, garm_fly=True, garm_confirm=1))
    assert rec["garm_fly"] == [["garm_baby"], 1.5, "9.19"]
    rec = dh.fixes_of(dh.argparse.Namespace(**base, garm_fly=True, garm_confirm=2))
    assert rec["garm_fly"] == [["garm_baby"], 1.5, "9.19b", 2]
    src = Path(dh.__file__).read_text()
    assert "self.alarm_n = alarm_streak(self.alarm_n, bool(alarm))" in src
    assert "boxes.alarm, tick, streak=streak_, need=a.garm_confirm" in src


def _lf2_late_held() -> tuple[dh.PosConfirm, dh.Held]:
    """A base read at 0.0 s, then a light read of the same cell 2.0 s later (after a blocking
    action): PosConfirm holds it back for being LATE."""
    from types import SimpleNamespace as R

    pc = dh.PosConfirm()
    assert pc.check(0.0, R(xy=(79, 93), mode="base")) == ((79, 93), None)
    pos, held = pc.check(2.0, R(xy=(79, 93), mode="light"))
    assert pos is None and held == dh.Held(2.0, (79, 93), 2.0)
    return pc, held


def test_late_confirm_takes_a_newer_frames_agreeing_read() -> None:
    """dungeon@9.21 (--late-confirm, LF-2; rogue-xmas02.md 4BI, Study S-LF): a light read held
    back for coming > 1.0 s after the read before it is confirmed at once by a read of a NEWER
    frame (another bus frame id) that agrees by PosConfirm's own rule."""
    from types import SimpleNamespace as R

    pc, held = _lf2_late_held()
    assert dh.late_confirm_due(held)
    seen: list[int] = []

    def newer(t_ns: int, fid: int) -> tuple[int, str, int, str]:
        seen.append(fid)
        return t_ns + 40_000_000, "img2", fid + 1, "bus"

    pos, rec = dh.late_confirm(pc, held, (5_000_000_000, 10), newer,
                               lambda img: R(xy=(79, 93), mode="light"), lambda: 2.05)  # fmt: skip
    assert pos == (79, 93) and seen == [10]
    assert rec == {"lf2": "ok", "lf2_fid": [10, 11], "lf2_ms": 40, "lf2_xy": [79, 93]}
    assert pc.last == (2.05, (79, 93))  # the next tick is confirmed against the newer read
    # one cell in 0.05 s is within the reach rule (dt / 0.15 s + 1)
    pc, held = _lf2_late_held()
    pos, rec = dh.late_confirm(pc, held, (0, 10), newer,
                               lambda img: R(xy=(80, 93), mode="light"), lambda: 2.05)  # fmt: skip
    assert pos == (80, 93) and rec is not None and rec["lf2"] == "ok"
    # a BASE read on the newer frame counts on its own, as PosConfirm counts base reads today
    pc, held = _lf2_late_held()
    pos, rec = dh.late_confirm(pc, held, (0, 10), newer,
                               lambda img: R(xy=(82, 93), mode="base"), lambda: 2.05)  # fmt: skip
    assert pos == (82, 93) and rec is not None and rec["lf2"] == "base"


def test_late_confirm_refuses_a_differing_read_the_same_frame_and_no_frame_id() -> None:
    from types import SimpleNamespace as R

    reads: list[str] = []

    def read(img: str) -> R:
        reads.append(img)
        return R(xy=(79, 96), mode="light")  # 3 cells off after 0.05 s: beyond the reach rule

    pc, held = _lf2_late_held()
    pos, rec = dh.late_confirm(pc, held, (0, 10), lambda t, f: (t + 1, "img2", 11, "bus"), read,
                               lambda: 2.05)  # fmt: skip
    assert pos is None and rec is not None and rec["lf2"] == "differ" and rec["lf2_xy"] == [79, 96]
    assert pc.unconfirmed == 2  # held back again, as PosConfirm does
    # the stream repeated the frame: two reads of one picture are one read -- nothing is read
    pc, held = _lf2_late_held()
    pos, rec = dh.late_confirm(pc, held, (0, 10), lambda t, f: (t + 1, "img2", 10, "bus"), read,
                               lambda: 2.05)  # fmt: skip
    assert (pos, rec) == (None, {"lf2": "same_frame", "lf2_fid": [10, 10], "lf2_ms": 0})
    # an X grab carries no frame id (-1): a new frame cannot be proven
    pos, rec = dh.late_confirm(pc, held, (0, -1), lambda t, f: (t + 1, "img2", -1, "x11"), read,
                               lambda: 2.05)  # fmt: skip
    assert pos is None and rec is not None and rec["lf2"] == "no_bus"
    pos, rec = dh.late_confirm(pc, held, (0, 10), lambda t, f: None, read, lambda: 2.05)
    assert (pos, rec) == (None, {"lf2": "no_frame"})
    assert reads == ["img2"]  # only the first case read anything
    assert pc.last == (2.0, (79, 93))  # an unread second frame leaves PosConfirm as today
    failed = R(xy=None, mode="light_failed")
    pos, rec = dh.late_confirm(pc, held, (0, 10), lambda t, f: (t + 1, "img2", 11, "bus"),
                               lambda img: failed, lambda: 2.05)  # fmt: skip
    assert pos is None and rec is not None and rec["lf2"] == "no_read"
    assert dh.late_confirm_refusal(10, 11, "bus") is None
    assert dh.late_confirm_refusal(-1, 11, "bus") == "no_bus"


def test_late_confirm_is_only_for_late_reads_and_keeps_the_jump_bar() -> None:
    """A light read held back for DISAGREEING with a recent read (<= 1.0 s) is not LF-2's case;
    and a cell LF-2 accepts meets the same position-jump hard bar as any read."""
    from types import SimpleNamespace as R

    pc, _held = _lf2_late_held()
    assert pc.check(2.2, R(xy=(79, 94), mode="light"))[0] == (79, 94)
    pos, held = pc.check(2.4, R(xy=(79, 84), mode="light"))  # 10 cells in 0.2 s: a misread
    assert pos is None and held is not None and abs((held.dt or 0) - 0.2) < 1e-9
    assert not dh.late_confirm_due(held) and not dh.late_confirm_due(None)
    called: list[int] = []
    out = dh.late_confirm(pc, held, (0, 1), lambda t, f: called.append(f) or None,  # type: ignore[func-returns-value]
                          lambda img: None, lambda: 2.45)  # fmt: skip
    assert out == (None, None) and called == []
    assert dh.late_confirm_due(dh.Held(0.0, (1, 1), None))  # no read before it: late too
    # the jump bar: a far read confirmed by a newer frame is still a jump for the main loop
    pc, _held = _lf2_late_held()
    pos2, held2 = pc.check(2.0, R(xy=(100, 93), mode="light"))
    assert pos2 is None and held2 is not None
    far, rec = dh.late_confirm(pc, dh.Held(2.0, (100, 93), 2.0), (0, 10),
                               lambda t, f: (t + 1, "img2", 11, "bus"),
                               lambda img: R(xy=(100, 93), mode="light"), lambda: 2.05)  # fmt: skip
    assert far == (100, 93) and rec is not None and rec["lf2"] == "ok"
    assert dh.is_jump((79, 93), far, 2.0)  # 21 cells in 2.0 s: the hard bar trips
    src = Path(dh.__file__).read_text()
    i_lf2 = src.index("pos, lf2_ = late_confirm(pos_ok, held, img_meta, newer_readout")
    i_jump = src.index("if (here is not None and is_jump(here, p_, tick - last_pos_t)")
    assert i_lf2 < src.index("rd_why = read_outcome(rd, pos)") < i_jump
    assert "if late_confirm_on and held is not None:" in src
    assert src.count("late_confirm(pos_ok") == 1  # the main HP read only (read_here() as today)


def test_newer_frame_waits_for_another_frame_id() -> None:
    class FakeScreen:
        def __init__(self, frames: list[tuple[int, int, str]]) -> None:
            self.frames = frames

        def grab_meta(self, x: int, y: int, w: int, h: int) -> tuple[int, object, int, str]:
            t, fid, src = self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]
            return t, np.zeros((h, w, 4), np.uint8), fid, src

    got = dh.newer_frame(FakeScreen([(100, 7, "bus"), (100, 7, "bus"), (130, 8, "bus")]),
                         (0, 0, 4, 2), 100, 7)  # fmt: skip
    assert got is not None and (got[0], got[2], got[3]) == (130, 8, "bus")
    assert got[1].shape == (2, 4, 3)
    assert dh.newer_frame(FakeScreen([(100, 7, "bus")]), (0, 0, 4, 2), 100, 7, wait_s=0.03) is None
    x11 = dh.newer_frame(FakeScreen([(5, -1, "x11")]), (0, 0, 4, 2), 100, -1)
    assert x11 is not None and x11[2:] == (-1, "x11")  # at once; late_confirm refuses it


def test_late_confirm_is_off_by_default_and_recorded_in_the_fixes() -> None:
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "late_confirm" not in dh.fixes_of(dh.argparse.Namespace(**base))
    assert "late_confirm" not in dh.fixes_of(dh.argparse.Namespace(**base, late_confirm=False))
    rec = dh.fixes_of(dh.argparse.Namespace(**base, late_confirm=True))
    assert rec["late_confirm"] == [1.0, 0.25, "9.21"]
    src = Path(dh.__file__).read_text()
    flag = '"--late-confirm",\n        action=argparse.BooleanOptionalAction,\n'
    flag += "        default=False,"
    assert flag in src
    assert 'late_confirm_on = getattr(a, "late_confirm", False)' in src
    assert "9.20" not in dh.LATE_CONFIRM_VERSION  # 9.20 is --loot-sight's (xmas02-detector O.10)


def test_lf1_each_hp_read_logs_the_held_read_and_the_age_of_here() -> None:
    """LF-1 (logging only, ALWAYS on; Amendment R: it changes no behaviour): the held-back read's
    cell and its gap to the read before, and the age of ``here`` (s since the last fresh read)."""
    src = Path(dh.__file__).read_text()
    assert 'lf_rec = {"held": list(held.cell), "held_dt": dt_h}' in src
    hp = '"here_age_s": round(tick - last_pos_t, 2), **lf_rec,\n                    "rd": rd_why})'
    assert hp in src
    # PosConfirm.accept is check()'s first half: the same answers as before (the X1b test above)
    from types import SimpleNamespace as R

    pc = dh.PosConfirm()
    assert pc.check(0.0, R(xy=(1, 1), mode="light")) == (None, dh.Held(0.0, (1, 1), None))
    assert pc.check(0.1, R(xy=None, mode="light_failed")) == (None, None)


# --- --unread-step (dungeon@9.22, LF-4; rogue-xmas02.md 4BI, Amendment R; Study S-LF 4 and 2f) ---


def _mv(t: float, rel: tuple[int, int], by: str = "walk") -> dh.OwnMove:
    return dh.OwnMove(t, rel, by)


def test_unread_step_waits_for_a_young_walk_click_then_steps_then_flies() -> None:
    """LF-4's pure decision on a tick the pos_unread rule would press the Fly Wing: no wing while
    a walk click of ours is < 2 s old (p39 250.96 s: the wing came 0.13 s after one); else a step;
    a step's fresh read gets 2 s; after 2 steps the wing, as before."""
    assert (dh.UNREAD_WALK_S, dh.UNREAD_STEPS, dh.UNREAD_STEP_CELLS) == (2.0, 2, 2)
    assert (dh.UNREAD_READ_S, dh.UNREAD_MAX_S) == (2.0, 15.0)
    mv = _mv(0.0, (11, 0))

    def d(now: float, walk_t: float = -1e9, steps: int = 0, step_t: float = -1e9,
          move: dh.OwnMove | None = mv, here: bool = True) -> tuple[str, str]:  # fmt: skip
        return dh.unread_step_decide(now, 100.0, walk_t, steps, step_t, move, here)

    # (a) p39: the walk click 0.13 s before the rule fired -> wait, re-checked on the next tick
    assert d(100.13, walk_t=100.0) == ("wait", "walk_sent")
    assert d(101.99, walk_t=100.0) == ("wait", "walk_sent")
    assert d(102.0, walk_t=100.0) == ("step", "")  # 2 s old: the wait is over
    # (b) a step, then its read's 2 s; the second step; (d) then the wing
    assert d(100.0) == ("step", "")
    assert d(101.5, steps=1, step_t=100.0) == ("wait", "step_read")
    assert d(102.0, steps=1, step_t=100.0) == ("step", "")
    assert d(103.0, steps=2, step_t=102.0) == ("wait", "step_read")
    assert d(104.0, steps=2, step_t=102.0) == ("wing", "steps")
    # no own move since the last Fly Wing: no way back is known -> the wing, as today
    assert d(100.0, move=None) == ("wing", "no_move")
    # no held cell (after a Fly Wing, or before the first read): nothing to judge a step from
    assert d(100.0, here=False) == ("wing", "no_here")
    # the backstop: never more than UNREAD_MAX_S after the rule came due, even mid-wait
    assert d(115.01, walk_t=115.0) == ("wing", "max")
    assert d(115.0, walk_t=114.5) == ("wait", "walk_sent")


def test_unread_step_simulated_escapes_end_fresh_or_by_the_wing() -> None:
    """(c) a fresh read ends the escape with no wing; (d) none after 2 steps -> the wing. Ticks at
    the runner's READ_HZ through the pure decision, with the read's arrival given."""

    def escape(fresh_at: float | None, walk_t: float) -> tuple[str, list[float]]:
        t0, steps, step_t, now, clicks = 0.0, 0, -1e9, 0.0, []
        while True:
            if fresh_at is not None and now >= fresh_at:
                return "fresh", clicks
            act, _why = dh.unread_step_decide(now, t0, walk_t, steps, step_t, _mv(-5.0, (8, 0)),
                                              True)  # fmt: skip
            if act == "wing":
                return "wing", clicks
            if act == "step":
                steps, step_t = steps + 1, now
                clicks.append(round(now, 1))
            now = round(now + 1.0 / dh.READ_HZ, 6)

    # p39: the walk 0.13 s before the rule fired -> at 1.8 s it is 1.93 s old (wait); steps at
    # 2.0 and 4.0 s (each read's 2 s), then the wing at 6.0 s
    assert escape(None, walk_t=-0.13) == ("wing", [2.0, 4.0])
    assert escape(2.6, walk_t=-0.13) == ("fresh", [2.0])  # step 1's read came: no wing
    assert escape(0.4, walk_t=-0.13) == ("fresh", [])  # the young walk itself freshened it
    assert escape(None, walk_t=-1e9) == ("wing", [0.0, 2.0])  # p47: no young walk, steps at once
    assert escape(3.0, walk_t=-1e9) == ("fresh", [0.0, 2.0])  # step 2's read came


def test_unread_step_goes_back_along_her_last_own_move() -> None:
    """(b): the step is 2 cells (Chebyshev) OPPOSITE to her last own-command movement -- a walk
    click's to - from, a far strike's walk-up; Fly Wings end the way she came."""
    assert dh.unread_step_rel((8, 0)) == (-2, 0)  # p47: the box strike at rel (8, 0)
    assert dh.unread_step_rel((11, 0)) == (-2, 0)
    assert dh.unread_step_rel((5, 3)) == (-2, -1)  # 1.2 -> 1
    assert dh.unread_step_rel((4, 3)) == (-2, -2)  # 1.5 -> 2 (half away from zero)
    assert dh.unread_step_rel((4, 1)) == (-2, -1)  # 0.5 -> 1, not banker's 0
    assert dh.unread_step_rel((-4, -1)) == (2, 1)  # symmetric
    assert dh.unread_step_rel((0, -7)) == (0, 2)
    assert dh.unread_step_rel((-1, 1)) == (2, -2)
    assert dh.unread_step_rel((0, 0)) is None
    for m in [(7, 3), (-9, 2), (1, -6), (3, 3)]:
        s = dh.unread_step_rel(m)
        assert s is not None and max(abs(s[0]), abs(s[1])) == 2
    moves = [_mv(1.0, (3, 0)), _mv(2.0, (0, 5), "strike"), _mv(3.0, (0, 0), "approach")]
    assert dh.last_own_move(moves, fly_at=-1e9) == moves[1]  # (0, 0) aims nowhere: skipped
    assert dh.last_own_move(moves, fly_at=2.5) is None  # every move before the Fly Wing
    assert dh.last_own_move(moves, fly_at=1.5) == moves[1]
    assert dh.last_own_move([], fly_at=-1e9) is None  # no own command: no step, the wing
    # (a)'s clock: walk clicks only (a strike's walk-up is not a walk click)
    assert dh.walk_click_t(moves) == 3.0
    assert dh.walk_click_t([_mv(1.0, (3, 0), "boss_walk"), _mv(2.0, (4, 4), "strike")]) == 1.0
    assert dh.walk_click_t([_mv(2.0, (4, 4), "strike")]) == -1e9
    assert {"walk", "boss_walk", "approach"} == dh.UNREAD_WALK_BY
    # the dead reckoning's displacement: a walk its rel, a strike stops beside the target
    assert dh.own_move_disp(_mv(0.0, (3, -4))) == (3, -4)
    assert dh.own_move_disp(_mv(0.0, (8, 0), "strike")) == (7, 0)
    assert dh.own_move_disp(_mv(0.0, (-2, 3), "strike")) == (-1, 2)


def test_unread_step_dodges_her_own_sprite_and_stays_in_view() -> None:
    """The step's point is SCREEN-RELATIVE (the flat projection about her sprite at the screen
    centre). Only (0, +2) of the 2-cell steps lies on her own sprite: hovered one cell aside."""
    from poring_dataset import camera as cam

    cj = json.loads(
        (ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json").read_text()
    )
    camera = cam.camera_from_json(cj["camera"])

    def uv(c: tuple[int, int]) -> tuple[float, float]:
        u, v = camera.project(np.asarray([c], float), np.zeros(1))[0]
        return float(u), float(v)

    def on_self(c: tuple[int, int]) -> bool:
        return dh.in_self_box(*uv(c), dh.FOOT_PX[0], dh.FOOT_PX[1])

    steps = {dh.unread_step_rel((dx, dy)) for dx in range(-9, 10) for dy in range(-9, 10)} - {None}
    assert len(steps) == 16  # the Chebyshev-2 ring
    assert {s for s in steps if s is not None and on_self(s)} == {(0, 2)}
    assert dh.unread_step_cells((0, 2), on_self) == [(1, 2), (-1, 2)]
    assert dh.unread_step_cells((-2, 0), on_self) == [(-2, 0)]
    for s in steps:
        assert s is not None
        for c in dh.unread_step_cells(s, on_self):
            u, v = uv(c)
            assert 30 <= u < 1280 - 30 and 30 <= v < 720 - 30  # in view, near the centre
            assert abs(u - dh.FOOT_PX[0]) <= 140 and abs(v - dh.FOOT_PX[1]) <= 100


def test_unread_step_judges_the_keep_outs_from_every_cell_she_may_be_on() -> None:
    """The zone / NPC checks need a map cell, and ``here`` is stale: they are judged from the HELD
    cell AND the held cell moved by our own commands since the last fresh read, with a margin of
    UNREAD_SAFE_R cells. p47: held (101, 208); a box strike at rel (8, 0) took her to (112, 207)."""
    held = (101, 208)
    moves = [_mv(1.0, (2, 1)), _mv(5.0, (8, 0), "strike")]
    assert dh.unread_candidates(None, moves, 4.0, -1e9) == []
    assert dh.unread_candidates(held, moves, 6.0, -1e9) == [held]  # nothing since the read
    assert dh.unread_candidates(held, moves, 4.0, -1e9) == [held, (108, 208)]  # p47: 4 cells off
    assert dh.unread_candidates(held, moves, 0.9, -1e9) == [held, (110, 209)]
    assert dh.unread_candidates(held, moves, 0.9, 3.0) == [held, (108, 208)]  # not before a wing
    assert dh.unread_candidates(held, moves, 5.4, -1e9) == [held, (108, 208)]  # within the lag
    back = [_mv(1.0, (3, 0)), _mv(2.0, (-3, 0))]
    assert dh.unread_candidates(held, back, 0.0, -1e9) == [held]  # there and back: one cell

    forbid = np.zeros((60, 60), dtype=bool)
    forbid[30:35, 30:35] = True  # a no-enter block
    assert dh.UNREAD_SAFE_R == 12
    assert dh.unread_step_safe([(10, 10)], (-2, 0), forbid, [], None) is None
    assert dh.unread_step_safe([(18, 32)], (-2, 0), forbid, [], None) == "zone_near"  # 12 off
    assert dh.unread_step_safe([(17, 32)], (-2, 0), forbid, [], None) is None  # 13 off
    # the held cell is clear, the dead-reckoned one is not: refused (prefer no step)
    assert dh.unread_step_safe([(5, 5), (25, 25)], (2, 0), forbid, [], None) == "zone_near"
    assert dh.unread_step_safe([(5, 5)], (2, 0), forbid, [(10, 14)], None) == "npc_near"
    assert dh.unread_step_safe([(5, 5)], (2, 0), forbid, [(5, 18)], None) is None
    assert dh.unread_step_safe([(5, 5), (-3, 5)], (2, 0), forbid, [], None) == "off_map"
    assert dh.unread_step_safe([], (2, 0), forbid, [], None) == "no_cell"
    # the walk click's own segment rule, from each candidate (reached with no margin)
    import map_zones as mz

    zones = mz.parse({"map": "t", "reviewed_by": "batt", "reviewed": "2026-11-10",
                      "no_cross": [{"id": "l", "note": "n", "points": [[11, 0], [11, 59]]}],
                      "no_enter": []}, "t", shape=(60, 60))  # fmt: skip
    line = mz.no_cross_mask(zones, (60, 60))
    assert dh.unread_step_safe([(10, 10)], (2, 0), line, [], zones, r=0) == "no_cross"
    assert dh.unread_step_safe([(10, 10)], (-2, 0), line, [], zones, r=0) is None
    assert dh.unread_step_safe([(10, 10)], (-2, 0), line, [], zones) == "zone_near"


def test_unread_step_is_never_refused_at_xmas_dun02s_dead_patches_but_is_near_its_warp() -> None:
    """xmas_dun02's one keep-out (the exit warp's span + 4, x 124-134 y 125-135) is >= 26 cells
    from every recurring dead patch of S-LF (p36-p47): every step from them passes; near it none."""
    import map_zones as mz

    zones = mz.load("xmas_dun02", shape=(300, 300))
    assert zones is not None
    forbid = mz.no_enter_mask(zones, (300, 300)) | mz.no_cross_mask(zones, (300, 300))
    steps = {dh.unread_step_rel((dx, dy)) for dx in range(-3, 4) for dy in range(-3, 4)} - {None}
    dead = [(112, 207), (118, 213), (129, 41), (136, 37), (121, 206), (141, 98), (141, 99),
            (88, 232), (89, 235), (181, 136), (183, 136)]  # fmt: skip
    for c in dead:
        for s in steps:
            assert s is not None
            assert dh.unread_step_safe([c], s, forbid, [], zones) is None, (c, s)
    for c in [(129, 120), (120, 130), (140, 140), (129, 113)]:  # within 12 of the area
        assert dh.unread_step_safe([c], (2, 0), forbid, [], zones) == "zone_near", c
    assert dh.unread_step_safe([(129, 112)], (2, 0), forbid, [], zones) is None  # 13 off


def test_unread_step_is_off_by_default_and_recorded_in_the_fixes() -> None:
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "unread_step" not in dh.fixes_of(dh.argparse.Namespace(**base))
    assert "unread_step" not in dh.fixes_of(dh.argparse.Namespace(**base, unread_step=False))
    rec = dh.fixes_of(dh.argparse.Namespace(**base, unread_step=True))
    assert rec["unread_step"] == [2.0, 2, 2, 2.0, 12, 15.0, "9.22"]
    assert dh.UNREAD_STEP_VERSION not in ("9.20", "9.21")  # --loot-sight's, --late-confirm's
    src = Path(dh.__file__).read_text()
    flag = '"--unread-step",\n        action=argparse.BooleanOptionalAction,\n'
    flag += "        default=False,"
    assert flag in src
    assert 'unread_step_on = getattr(a, "unread_step", False)' in src
    assert '"fixes": fixes_of(a)' in src  # run_start and the manifest both record it
    # the run refuses before any input when the KB cannot list the map's NPCs
    assert 'raise SystemExit(f"dungeon@9.22 refused: --unread-step: {e}") from None' in src


def test_unread_step_is_wired_into_the_pos_unread_rule_only() -> None:
    """The flag off: unread_held returns False first and nothing else changes (the wing's events
    are today's). On: the step is the ONE new world click, through click_at, after a CLEAR read
    only; a fresh read ends the escape; the search walk holds its clicks while one runs."""
    src = Path(dh.__file__).read_text()
    i_rule = src.index("and not unread_held(tick)):")
    i_stuck = src.index('"why": "pos_unread"})')
    assert src.index("and pos_flies < POS_FLY_MAX") < i_rule < i_stuck  # due first (short-circuit)
    assert src[i_stuck : i_stuck + 200].count('press("fly", "pos_unread")') == 1
    body = src[src.index("def unread_held(now: float) -> bool:") :]
    body = body[: body.index("\n        def ", 10)]
    assert body.index("if not unread_step_on:\n                return False") < body.index("ust.")
    assert body.count("click_at(") == 1 and 'click_at(u_u, v_u, "unread_step")' in body
    assert body.index('if act_w != "click":') < body.index("click_at(u_u, v_u")
    assert "trusted=False, enabled=False" in body  # no --walk-trust for the step
    assert "project(None, [c_u])" in body  # screen-relative: no map cell
    assert "unread_step_safe(cands, rel_u, unread_forbid, unread_npcs, zones)" in body
    assert body.index("unread_step_safe(") < body.index("hover(u_u, v_u)")
    assert src.count('click_at(u_u, v_u, "unread_step")') == 1
    assert "unread_step" not in dh.NPC_GUARDED  # a walk-type click, as the walk's
    # (c): a fresh main read ends the escape, after the jump bar, before ``here`` moves
    i_fresh = src.index('unread_end("fresh", at=list(p_)')
    assert src.index("if (here is not None and is_jump(here, p_, tick - last_pos_t)") < i_fresh
    assert i_fresh < src.index("here, last_pos_t = p_, tick")
    # no search walk click while an escape runs; every other Fly Wing ends the escape
    assert "and tick - last_walk >= a.walk_every and not unread_active() \\\n" in src
    hook = 'if what == "fly" and why != "pos_unread":\n                unread_end("fly", why=why)'
    assert hook in src
    # the way she came: the walk click, the boss walk-away, the far approach, a far strike, and
    # --unreach-escape's walk click (dungeon@9.26, a "walk")
    assert src.count("note_move(") == 6  # the definition + 5 sources
    for s_ in ('note_move(rel, "walk")', '"boss_walk")', 'note_move(cell_a, "approach")',
               'note_move(rel, "strike")'):  # fmt: skip
        assert s_ in src
    # the event (slf_score.py's LF-4 block reads these shapes): one kind, its outcome in "event"
    assert '{"kind": "unread_step", "event": event, "steps": ust["steps"],' in src
    assert '{"kind": "unread_step", "event": "wait", "why": why_u,' in body
    assert '{"kind": "unread_step", "event": "step", "n": ust["steps"], "rel": list(c_u),' in body
    for end_ in ('unread_end("wing", why=why_u)', 'unread_end("refused", why=why_safe,',
                 'unread_end("refused", why="cursor",'):  # fmt: skip
        assert end_ in body
    # LF-4 leaves the fight branch alone: the rule is still checked outside fights only
    fight_end = "time.sleep(max(0.0, 1.0 / READ_HZ - (time.monotonic() - tick)))\n"
    assert fight_end + "                    continue" in src


# --- --still-target (dungeon@9.23, LS-2; rogue-xmas02.md Study S-LS) ------------------------------


def test_foot_shift_measures_the_foot_only() -> None:
    """The foot is box_target's: the bottom edge's centre. A box that grows upward (a sprite's
    head, an attack pose) has not moved; a diagonal step is measured as one distance."""
    b1 = (100.0, 200.0, 140.0, 260.0)  # foot (120, 260)
    assert dh.foot_shift(b1, b1) == 0.0
    assert dh.foot_shift(b1, (112.0, 200.0, 152.0, 260.0)) == 12.0  # 12 px east
    assert dh.foot_shift(b1, (100.0, 180.0, 140.0, 260.0)) == 0.0  # taller, the same foot
    assert dh.foot_shift(b1, (103.0, 204.0, 143.0, 264.0)) == 5.0  # (3, 4)
    assert dh.foot_shift((103.0, 204.0, 143.0, 264.0), b1) == 5.0  # symmetric
    assert dh.foot_shift([100, 200, 140, 260, 0.9], b1) == 0.0  # extra fields ignored


def test_press_decide_strikes_a_still_sprite_and_holds_a_walker() -> None:
    """D2's verdict: the same sprite (same_box: the nearest centre within LEAD_MATCH_PX) whose foot
    moved < WALKER_PX is struck as today; >= WALKER_PX is held; no match cannot judge."""
    b1 = (100.0, 200.0, 140.0, 260.0)
    near = (109.9, 200.0, 149.9, 260.0)  # 9.9 px east
    end, b2, moved = dh.press_decide(b1, [(400.0, 200.0, 440.0, 260.0), near])
    assert end == "strike" and b2 == near and moved is not None and abs(moved - 9.9) < 1e-9
    end, b2, moved = dh.press_decide(b1, [(110.0, 200.0, 150.0, 260.0)])  # exactly 10 px
    assert (end, b2, moved) == ("hold", (110.0, 200.0, 150.0, 260.0), 10.0)
    assert dh.press_decide(b1, [(130.0, 200.0, 170.0, 260.0)])[0] == "hold"  # 30 px: a walker
    assert dh.press_decide(b1, [(200.0, 200.0, 240.0, 260.0)]) == ("no_match", None, None)
    assert dh.press_decide(b1, []) == ("no_match", None, None)
    # the nearest centre is the sprite, not the first box listed
    assert dh.press_decide(b1, [(125.0, 200.0, 165.0, 260.0), (102.0, 200.0, 142.0, 260.0)])[:2] \
        == ("strike", (102.0, 200.0, 142.0, 260.0))  # fmt: skip
    assert dh.nearest_centre_px(b1, [(200.0, 200.0, 240.0, 260.0), (160.0, 200.0, 200.0, 260.0)]) \
        == 60.0  # fmt: skip
    assert dh.nearest_centre_px(b1, []) is None


def test_hold_end_rule() -> None:
    """lost (no match) first; still = HOLD_STILL_N shifts IN A ROW under WALKER_PX (it may come on
    the poll that also reaches the backstop); timeout at HOLD_MAX_S; else poll again."""
    assert (dh.WALKER_PX, dh.HOLD_GAP_S, dh.HOLD_MAX_S, dh.HOLD_STILL_N) == (10.0, 0.25, 2.5, 2)
    assert dh.hold_end([], 0.3, True) is None
    assert dh.hold_end([12.0], 0.3, True) is None
    assert dh.hold_end([12.0, 3.0], 0.55, True) is None  # one still shift is not still
    assert dh.hold_end([12.0, 3.0, 4.0], 0.8, True) == "still"
    assert dh.hold_end([3.0, 4.0], 0.55, True) == "still"  # stopped right after D2
    assert dh.hold_end([3.0, 12.0, 4.0], 0.8, True) is None  # not in a row
    assert dh.hold_end([9.99, 9.99], 0.55, True) == "still"
    assert dh.hold_end([10.0, 3.0], 0.55, True) is None  # 10 px is a walker's shift
    assert dh.hold_end([12.0, 15.0], 2.49, True) is None
    assert dh.hold_end([12.0, 15.0], 2.5, True) == "timeout"
    assert dh.hold_end([12.0, 3.0, 2.0], 2.6, True) == "still"  # still wins on the same poll
    assert dh.hold_end([3.0, 2.0], 0.3, False) == "lost"  # no match: lost, whatever came before
    assert dh.hold_end([12.0], 3.0, False) == "lost"


class _HoldClock:
    """A fake clock for hold_track: sleep and each detection advance it."""

    def __init__(self) -> None:
        self.t = 100.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


def _hold_run(steps: list[float | str | None],
              guard_at: int | None = None) -> tuple[dict, list, list]:  # fmt: skip
    """hold_track on a scripted sprite: each step is a foot x offset (the box moves east to it; a
    float), None (no detection came: the full timeout passes) or "far" (only a box 200 px away)."""
    clk = _HoldClock()
    grabs: list[float] = []
    timeouts: list[float] = []
    script = list(steps)
    polls = [0]

    def detect(timeout: float) -> tuple[float, list[tuple[float, ...]]] | None:
        timeouts.append(timeout)
        step = script.pop(0)
        if step is None:
            clk.t += timeout
            return None
        t_g = clk.t
        grabs.append(t_g)
        clk.t += 0.05  # the detection's own time
        if step == "far":
            return t_g, [(300.0, 200.0, 340.0, 260.0)]
        x = 100.0 + float(step)
        return t_g, [(x, 200.0, x + 40.0, 260.0), (600.0, 100.0, 640.0, 160.0)]

    def guard() -> bool:
        polls[0] += 1
        return guard_at is not None and polls[0] >= guard_at

    hd = dh.hold_track((100.0, 200.0, 140.0, 260.0), clk.t, detect, guard, clock=clk,
                       sleep=clk.sleep)  # fmt: skip
    return hd, grabs, timeouts


def test_hold_track_waits_for_two_still_detections_every_gap() -> None:
    """A walker 20 px on, then standing: still on the 3rd poll; the polls are HOLD_GAP_S apart
    (grab to grab), the last matched box is the one struck."""
    hd, grabs, timeouts = _hold_run([20.0, 23.0, 25.0])
    assert hd["end"] == "still" and hd["polls"] == 3
    assert hd["shifts"] == [20.0, 3.0, 2.0]
    assert hd["box"] == (125.0, 200.0, 165.0, 260.0) and hd["t"] == grabs[-1]
    assert [round(b - a, 6) for a, b in zip([100.0, *grabs], grabs, strict=False)] == [0.25] * 3
    assert timeouts[0] == 1.8 and hd["lost_px"] is None  # BOX_TARGET_WAIT_S, the time left
    hd2, _g, _t = _hold_run([2.0, 3.0])  # it stopped right after D2
    assert (hd2["end"], hd2["polls"]) == ("still", 2)


def test_hold_track_times_out_on_a_walker_and_stays_bounded() -> None:
    hd, grabs, timeouts = _hold_run([15.0 * (k + 1) for k in range(40)])
    assert hd["end"] == "timeout" and hd["polls"] == 10  # grabs at +0.25 .. +2.5 s
    assert all(s == 15.0 for s in hd["shifts"])
    assert dh.HOLD_MAX_S <= hd["hold_s"] < dh.HOLD_MAX_S + dh.HOLD_GAP_S
    assert all(0.1 <= t <= 1.8 for t in timeouts) and timeouts[-1] == 0.1  # never past the cap
    assert hd["box"] == (250.0, 200.0, 290.0, 260.0)  # the last matched box


def test_hold_track_lost_escaped_and_a_missing_detection() -> None:
    hd, _g, _t = _hold_run(["far"])
    assert (hd["end"], hd["polls"], hd["shifts"]) == ("lost", 1, [])
    assert hd["lost_px"] == 200.0 and hd["box"] == (100.0, 200.0, 140.0, 260.0)
    hd, _g, _t = _hold_run([20.0, 40.0], guard_at=2)  # the 2nd poll's guard_tick flew away
    assert (hd["end"], hd["polls"], hd["shifts"]) == ("escaped", 1, [20.0])
    hd, _g, _t = _hold_run([5.0], guard_at=1)  # flew away before the first poll
    assert (hd["end"], hd["polls"]) == ("escaped", 0)
    # no detection came (1.8 s): it neither breaks nor makes a still pair; the hold goes on
    hd, _g, timeouts = _hold_run([None, 2.0, 3.0])
    assert hd["end"] == "still" and hd["shifts"] == [None, 2.0, 1.0] and hd["polls"] == 3
    assert timeouts[0] == 1.8 and round(timeouts[1], 6) == 0.45  # the 2.5-s backstop's left


def test_still_target_is_refused_where_it_could_not_check() -> None:
    """--still-target needs the box target's SWORD (--box-strike), its own detection (--box-now)
    and a still scene (--still-strike); --lead-strike would replace the box it compares."""
    assert dh.still_target_refused(True, True, True, False) is None
    need = "--still-target needs --box-strike --box-now"
    assert dh.still_target_refused(False, True, True, False) == need
    assert dh.still_target_refused(True, False, True, False) == need
    still = "--still-target needs --still-strike"
    assert dh.still_target_refused(True, True, False, False) == still
    lead = "--still-target does not go with --lead-strike"
    assert dh.still_target_refused(True, True, True, True) == lead
    src = Path(dh.__file__).read_text()
    i_ref = src.index('raise SystemExit(f"dungeon@9.23 refused: {why_st}")')
    assert i_ref < src.index("typed: list[str] = []")  # before the setup types anything


def test_still_target_is_off_by_default_and_recorded_in_the_fixes() -> None:
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "still_target" not in dh.fixes_of(dh.argparse.Namespace(**base))
    assert "still_target" not in dh.fixes_of(dh.argparse.Namespace(**base, still_target=False))
    rec = dh.fixes_of(dh.argparse.Namespace(**base, still_target=True))
    assert rec["still_target"] == [10.0, 0.25, 2.5, "9.23"]
    rest = {k: v for k, v in rec.items() if k != "still_target"}
    assert rest == dh.fixes_of(dh.argparse.Namespace(**base))  # its own key only
    assert dh.STILL_TARGET_VERSION not in ("9.20", "9.21", "9.22")  # loot-sight, LF-2, LF-4
    src = Path(dh.__file__).read_text()
    flag = '"--still-target",\n        action=argparse.BooleanOptionalAction,\n'
    flag += "        default=False,"
    assert flag in src
    assert 'still_target_on = getattr(a, "still_target", False)' in src
    assert src.count('"fixes": fixes_of(a)') == 2  # run_start and the manifest both record it


def test_still_target_is_wired_at_the_box_targets_sword_only() -> None:
    """The flag off: box_target's SWORD branch is today's (one guarded block, before box_spot).
    On: press_check's D2 by the box target's arm, the hold through hold_track with guard_tick, the
    re-aim only after box_target's selection gate and a SWORD read; no input path of its own."""
    src = Path(dh.__file__).read_text()
    body = src[src.index("        def box_target() -> tuple[Cell, tuple[float, float]] | None:") :]
    body = body[: body.index("\n        def ", 10)]
    i_sword = body.index('if res_["verdict"] == "sword":')
    i_on = body.index("if still_target_on:  # dungeon@9.23 (LS-2)", i_sword)
    assert i_sword < i_on < body.index("sp_ = box_spot(here, foot)", i_sword)
    assert body.count("still_target_on") == 1 and src.count("press_check(") == 2
    assert 'rec["press"], today_p, got_p = press_check(' in body
    assert 'near_b, meta, arm, bool(still_rec.get("still", False)))' in body
    pc = src[src.index("        def press_check(") :]
    pc = pc[: pc.index("\n        def self_uv(")]
    assert "click_at(" not in pc and "agent." not in pc and ".click(" not in pc
    assert pc.count("hover(") == 1  # the still box's first hover point
    assert 'meta2 = boxes.fresh_now(arm_ or "gpu", BOX_TARGET_WAIT_S)' in pc
    assert "end, b2, moved = press_decide(b1, got2)" in pc
    assert "hd = hold_track(b, t_b, detect_, guard_tick)" in pc
    assert "u_e, v_e = box_hover_points(last)[0]" in pc
    i_far = pc.index('prs["gate"] = "far"')
    i_skip = pc.index('prs["gate"] = "skip"')
    i_view = pc.index('prs["verdict2"] = "off"')
    i_hover = pc.index('prs["verdict2"] = str(hover(u_e, v_e)["verdict"])')
    i_sword2 = pc.index('if prs["verdict2"] != "sword":')
    i_ret = pc.index("return end, (rel_e, (u_e, v_e))")
    assert i_far < i_skip < i_view < i_hover < i_sword2 < i_ret
    # the event's "press" record: these five fields from the start, for every end
    assert '{"moved_px": None, "det2_ms": None, "hold_ms": 0, "polls": 0,' in pc
    assert 'counts[f"still_target_{end}"] += 1' in pc


# --- --lead-press (dungeon@9.24, LS-1; rogue-xmas02.md Study S-LS, 4BP) ---------------------------


def test_lead_press_constants() -> None:
    assert (dh.LEAD_PX, dh.LEAD_AGE_S, dh.LEAD_CAP_PX, dh.LEAD_CAP_CELLS) == (15.0, 0.57, 32.0, 1.0)
    assert dh.LEAD_PRESS_VERSION == "9.24" and dh.WALKER_PX < dh.LEAD_PX
    assert dh.LEAD_PRESS_VERSION not in ("9.20", "9.21", "9.22", "9.23")


def test_press_lead_decides_strike_hold_or_lead_by_the_foot_shift() -> None:
    """< WALKER_PX: today's strike; [WALKER_PX, LEAD_PX): LS-2's hold; >= LEAD_PX: led. Grabs out
    of order give no velocity: held."""
    b1 = (100.0, 200.0, 140.0, 260.0)  # foot (120, 260)

    def east(px: float) -> tuple[float, float, float, float]:
        return (100.0 + px, 200.0, 140.0 + px, 260.0)

    def decide(px: float, t2: float = 10.3) -> str:
        return str(dh.press_lead(b1, 10.0, east(px), t2, 10.35)["decision"])

    assert [decide(px) for px in (0.0, 9.9, 10.0, 14.9, 15.0, 30.0)] == [
        "strike", "strike", "hold", "hold", "lead", "lead"]  # fmt: skip
    assert dh.press_lead(b1, 10.0, east(12.0), 10.3, 10.35) == {"decision": "hold", "moved": 12.0}
    assert dh.press_lead(b1, 10.0, east(20.0), 10.0, 10.35) == \
        {"decision": "hold", "moved": 20.0, "why": "dt"}  # fmt: skip
    assert dh.press_lead(b1, 10.0, east(20.0), 9.9, 10.35)["why"] == "dt"
    # a box that grew upward (an attack pose, a head) did not move: struck as today
    taller = (100.0, 150.0, 140.0, 260.0)
    assert dh.press_lead(b1, 10.0, taller, 10.3, 10.35)["decision"] == "strike"


def test_press_lead_is_velocity_times_the_age_from_d2() -> None:
    """v = the foot's shift / the time between the two grabs; age = LEAD_AGE_S + the time already
    spent since D2's grab; the led point = D2's FIRST hover point (its centre) + the lead; the led
    foot = D2's foot + the lead (box_spot's cell)."""
    b1 = (100.0, 200.0, 140.0, 260.0)
    b2 = (112.0, 216.0, 152.0, 276.0)  # foot (120, 260) -> (132, 276): (12, 16), 20 px
    big_x, big_y = (500.0, 0.0), (0.0, -500.0)  # cells too big to cap anything
    pl = dh.press_lead(b1, 10.0, b2, 10.4, 10.43, big_x, big_y)
    assert pl["decision"] == "lead" and pl["moved"] == 20.0
    assert [round(x, 6) for x in pl["v"]] == [30.0, 40.0]  # px / s over the 0.4 s between grabs
    assert abs(pl["age_s"] - 0.60) < 1e-9  # 0.57 + 0.03 since D2's grab
    assert [round(x, 6) for x in pl["raw"]] == [18.0, 24.0] and pl["raw"] == pl["lead"]  # 0.6 s
    assert (pl["capped"], pl["cap"]) == (False, "cell")
    assert [round(x, 6) for x in pl["point"]] == [150.0, 270.0]  # D2's centre (132, 246) + lead
    assert [round(x, 6) for x in pl["foot"]] == [150.0, 300.0]  # D2's foot (132, 276) + lead
    assert dh.box_hover_points(b2)[0] == (132.0, 246.0)
    # D2's grab "after" now (clock skew) adds nothing: the constant alone
    assert dh.press_lead(b1, 10.0, b2, 10.4, 10.3, big_x, big_y)["age_s"] == dh.LEAD_AGE_S
    # a walker going up and left: the lead points the same way
    pl2 = dh.press_lead(b1, 10.0, (76.0, 170.0, 116.0, 230.0), 10.3, 10.3, big_x, big_y)
    assert pl2["v"][0] < 0 and pl2["v"][1] < 0 and pl2["lead"][0] < 0 and pl2["lead"][1] < 0


def test_lead_cap_one_cell() -> None:
    """At most one cell, Chebyshev, on the camera's per-cell screen vectors (34 px across, 24 px up
    here): a straight walk is cut to one step, a diagonal to one diagonal step; a short lead stays.
    Without usable vectors: at most LEAD_CAP_PX (32 px), the direction kept."""
    ex, ey = (34.0, 0.0), (0.0, -24.0)
    assert dh.lead_cap((51.0, 0.0), ex, ey) == ((34.0, 0.0), True, "cell")
    assert dh.lead_cap((-51.0, 0.0), ex, ey) == ((-34.0, 0.0), True, "cell")
    assert dh.lead_cap((0.0, 36.0), ex, ey) == ((0.0, 24.0), True, "cell")
    lead, capped, rule = dh.lead_cap((68.0, -36.0), ex, ey)  # (2, 1.5) cells -> (1, 0.75)
    assert [round(x, 6) for x in lead] == [34.0, -18.0] and capped and rule == "cell"
    assert dh.lead_cap((20.0, -10.0), ex, ey) == ((20.0, -10.0), False, "cell")
    assert dh.lead_cap((34.0, -24.0), ex, ey) == ((34.0, -24.0), False, "cell")  # exactly 1 cell
    # skewed vectors (the camera's perspective): the cap is still one step along each axis
    lead, capped, _ = dh.lead_cap((90.0, 0.0), (33.2, 0.0), (-1.2, -22.6))
    assert capped and [round(x, 6) for x in lead] == [33.2, 0.0]
    lead, capped, _ = dh.lead_cap((0.0, 60.0), (33.2, 0.0), (-1.2, -22.6))  # 2.65 cells along y
    assert capped and [round(x, 6) for x in lead] == [0.0, 22.6]
    # the 32-px fallback: no vectors, a zero one, or parallel ones
    for cx, cy in ((None, None), (ex, None), ((0.0, 0.0), ey), ((34.0, 0.0), (17.0, 0.0))):
        lead, capped, rule = dh.lead_cap((300.0, 400.0), cx, cy)
        assert [round(x, 6) for x in lead] == [19.2, 25.6] and capped and rule == "px"
        assert abs((lead[0] ** 2 + lead[1] ** 2) ** 0.5 - dh.LEAD_CAP_PX) < 1e-9
    assert dh.lead_cap((20.0, 10.0)) == ((20.0, 10.0), False, "px")
    # press_lead hands its vectors to the cap: a fast walker is led one cell, not v x age
    b1 = (100.0, 200.0, 140.0, 260.0)
    pl = dh.press_lead(b1, 10.0, (130.0, 200.0, 170.0, 260.0), 10.3, 10.3, ex, ey)  # 100 px / s
    assert [round(x, 6) for x in pl["raw"]] == [57.0, 0.0] and pl["capped"]
    assert [round(x, 6) for x in pl["lead"]] == [34.0, 0.0]
    pl_px = dh.press_lead(b1, 10.0, (130.0, 200.0, 170.0, 260.0), 10.3, 10.3)
    assert [round(x, 6) for x in pl_px["lead"]] == [32.0, 0.0] and pl_px["cap"] == "px"


def test_lead_press_is_refused_without_still_target_or_with_lead_strike() -> None:
    assert dh.lead_press_refused(True, False) is None
    need = "--lead-press needs --still-target"
    assert dh.lead_press_refused(False, False) == need
    assert dh.lead_press_refused(False, True) == need
    assert dh.lead_press_refused(True, True) == "--lead-press does not go with --lead-strike"
    src = Path(dh.__file__).read_text()
    i_st = src.index('raise SystemExit(f"dungeon@9.23 refused: {why_st}")')
    i_lp = src.index('raise SystemExit(f"dungeon@9.24 refused: {why_lp}")')
    assert i_st < i_lp < src.index("typed: list[str] = []")  # before the setup types anything
    assert 'if getattr(a, "lead_press", False):  # dungeon@9.24 (LS-1)' in src[i_st:i_lp]


def test_lead_press_is_off_by_default_and_recorded_in_the_fixes() -> None:
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False, "still_target": True}  # fmt: skip
    assert "lead_press" not in dh.fixes_of(dh.argparse.Namespace(**base))
    assert "lead_press" not in dh.fixes_of(dh.argparse.Namespace(**base, lead_press=False))
    rec = dh.fixes_of(dh.argparse.Namespace(**base, lead_press=True))
    assert rec["lead_press"] == [15.0, 0.57, 32.0, 1.0, "9.24"]
    assert rec["still_target"] == [10.0, 0.25, 2.5, "9.23"]  # LS-2's record is unchanged
    rest = {k: v for k, v in rec.items() if k != "lead_press"}
    assert rest == dh.fixes_of(dh.argparse.Namespace(**base))  # its own key only
    src = Path(dh.__file__).read_text()
    flag = '"--lead-press",\n        action=argparse.BooleanOptionalAction,\n'
    flag += "        default=False,"
    assert flag in src
    assert src.count('lead_press_on = getattr(a, "lead_press", False)') == 1
    assert src.count('"fixes": fixes_of(a)') == 2  # run_start and the manifest both record it


def test_lead_press_is_wired_in_press_checks_hold_only() -> None:
    """The flag off: press_check's hold is LS-2's (lead_aim is never called, got stays None ->
    hold_still). On: a hold is first offered to lead_aim; a led (rel, point) comes back through
    box_target's re-aim return (box_target itself is unchanged) to strike() -> click_at, the
    same path as every strike; lead_aim reads no cursor, clicks nothing, applies its gates in
    order."""
    src = Path(dh.__file__).read_text()
    body = src[src.index("        def box_target() -> tuple[Cell, tuple[float, float]] | None:") :]
    body = body[: body.index("\n        def ", 10)]
    assert "lead_press" not in body and "lead_aim" not in body  # box_target untouched
    assert "if got_p is not None:  # it stood still and read SWORD again: its box" in body
    assert src.count("lead_press_on") == 3  # its definition + press_check's two
    assert src.count("lead_aim(") == 2  # its def + press_check's one call
    pc = src[src.index("        def press_check(") :]
    pc = pc[: pc.index("\n        def hold_still(")]
    assert pc.count("lead_press_on") == 2
    i_init = pc.index('prs["lead"] = None')
    assert pc.index("if lead_press_on:\n") < i_init < pc.index("if not still_ or meta_ is None:")
    i_hold = pc.index('if end == "hold":')
    i_on = pc.index("if lead_press_on:  # dungeon@9.24 (LS-1)", i_hold)
    i_call = pc.index('got = lead_aim(b1, float(meta_["t"]), b2, t2, prs)', i_on)
    i_led = pc.index('end = "led"', i_call)
    i_still = pc.index('end, got = hold_still(b2, t2, arm_ or "gpu", float(meta_["t"]), prs)')
    assert i_hold < i_on < i_call < i_led < i_still < pc.index('prs["end"] = end')
    assert "got: tuple[Cell, tuple[float, float]] | None = None" in pc[:i_hold]
    assert 'counts[f"still_target_{end}"] += 1' in pc  # -> still_target_led
    la = src[src.index("        def lead_aim(") :]
    la = la[: la.index("\n        def self_uv(")]
    for word in ("hover(", "click_at(", "agent.", ".click(", "fresh_now(", "sleep("):
        assert word not in la, word
    assert "pl = press_lead(b1, t1, b2, t2, time.monotonic(), ex, ey)" in la
    assert "ex, ey = cell_steps(camera, ((b2[0] + b2[2]) / 2, b2[3]))" in la
    i_dec = la.index('if pl["decision"] != "lead":')
    i_far = la.index('gate = "far"')
    i_skip = la.index('gate = "skip"')
    i_off = la.index('gate = "off"')
    i_self = la.index('gate = "self"')
    i_rec = la.index('prs["lead"] = {"v_px_s": r1(pl["v"]), "age_s": round(pl["age_s"], 3),')
    i_gate = la.index("if gate is not None:")
    i_spot = la.index("sp_l = box_spot(here, foot_l)")
    i_ret = la.index("return rel_l, (u_l, v_l)")
    assert i_dec < i_far < i_skip < i_off < i_self < i_rec < i_gate < i_spot < i_ret
    assert '"sword": "unchecked"' in la  # LS-1's known risk, in every lead record
    for key in ('"lead_px": r1(pl["lead"])', '"capped": pl["capped"]', '"point": r1((u_l, v_l))'):
        assert key in la, key


def test_cell_steps_on_the_runner_camera() -> None:
    """The cap's cell, by the runner's own camera (camera_rdp.json, the RDP fit): one step is ~34 px
    across and ~24 px up / down on screen (so a flat 32-px cap would not be one cell), a little
    smaller farther up the screen; and lead_cap on those vectors leads one cell at most."""
    from poring_dataset import camera as cam

    cj = json.loads(
        (ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json").read_text()
    )
    camera = cam.camera_from_json(cj["camera"])
    ex, ey = dh.cell_steps(camera, dh.FOOT_PX)  # our own cell
    assert [round(x, 1) for x in ex] == [34.1, 0.0] and [round(x, 1) for x in ey] == [0.0, -23.8]
    ex2, ey2 = dh.cell_steps(camera, (772.0, 269.0))  # (4, 4) cells off, up the screen
    assert 32.5 < ex2[0] < 33.5 and -23.0 < ey2[1] < -21.5 and abs(ey2[0]) < 2.0
    lead, capped, rule = dh.lead_cap((60.0, 0.0), ex, ey)
    assert capped and rule == "cell" and [round(x, 1) for x in lead] == [34.1, 0.0]
    lead, capped, rule = dh.lead_cap((0.0, 40.0), ex, ey)
    assert capped and rule == "cell" and [round(x, 1) for x in lead] == [0.0, 23.8]
    lead, capped, _ = dh.lead_cap((60.0, -40.0), ex, ey)  # diagonal: one diagonal step
    assert capped and [round(x, 1) for x in lead] == [34.1, -22.7]


def test_near_single_9_25_moves_the_one_click_rule_to_two_cells() -> None:
    """dungeon@9.25 (S-LF5 R2): --near-single clicks once from 2 cells (0-1 keep the burst); the
    default stays 4; it needs --far-single; the fixes record carries it only when on."""
    assert dh.far_window((0, 3)) is None and dh.far_window((4, 0)) == 1.8
    assert dh.far_window((0, 3), dh.NEAR_SINGLE_CELLS) == 1.6
    assert dh.far_window((2, -1), dh.NEAR_SINGLE_CELLS) == 1.4
    assert dh.far_window((1, 1), dh.NEAR_SINGLE_CELLS) is None
    assert dh.NEAR_SINGLE_CELLS == 2 and dh.NEAR_SINGLE_VERSION == "9.25"
    base = dh.argparse.Namespace(plant_sweep=False, box_ignore=2, ag_match=40.0, walk_trust=False,
                                 rest="spot", npc_guard=False, far_single=True)  # fmt: skip
    assert "near_single" not in dh.fixes_of(base)
    on = dh.argparse.Namespace(**{**vars(base), "near_single": True})
    assert dh.fixes_of(on)["near_single"] == [2, "9.25"]
    assert dh.fixes_of(on)["far_single"] == dh.fixes_of(base)["far_single"]


def test_near_single_still_9_25b_gates_the_two_three_cell_reclick_on_the_scroll() -> None:
    """dungeon@9.25b (R2b, 4BT): only 2-3-cell strikes are scroll-gated; a re-click goes out
    while the scene moved < WALK_STOP_PX; it refuses with --near-single; fixes only when on."""
    assert dh.near_still_cells((2, -1), True) and dh.near_still_cells((0, 3), True)
    assert not dh.near_still_cells((1, 1), True) and not dh.near_still_cells((4, 0), True)
    assert not dh.near_still_cells((2, 0), False)
    assert dh.near_still_reclick((3.0, 4.0)) and not dh.near_still_reclick((6.0, 8.0))
    assert dh.NEAR_STILL_VERSION == "9.25b"
    base = dh.argparse.Namespace(plant_sweep=False, box_ignore=2, ag_match=40.0, walk_trust=False,
                                 rest="spot", npc_guard=False, far_single=True)  # fmt: skip
    assert "near_single_still" not in dh.fixes_of(base)
    on = dh.argparse.Namespace(**{**vars(base), "near_single_still": True})
    assert dh.fixes_of(on)["near_single_still"] == [2, 4, 10.0, "9.25b"]
    src = Path(dh.__file__).read_text()
    assert 'if still_rec is None or still_rec["stopped_s"] is None:' in src
    assert src.count('click_at(u, v, "strike_burst")') == 1


# --- --bare-steal (dungeon@9.27, rogue-xmas02.md 4BX; Batt 2026-11-11) ----------------------------

BS = dh.bs


def _hotbar_frame(bag: bool, dark: bool = False, popup: int | None = None) -> np.ndarray:
    """A game-region frame's top rows (BGR): the hotbar's white slots with the dagger's icon in
    slot 4 while it is in the BAG, and optionally the item popup of width ``popup``."""
    img = np.full((110, 800, 3), 120, np.uint8)
    if dark:
        img[:] = 10
        return img
    img[3:34, 240:520] = 235
    for k in range(9):
        img[3:34, 245 + 29 * k] = 192
    if bag:
        x0 = 246 + 29 * 4 + 9
        img[8:18, x0 : x0 + 6] = 60
    if popup is not None:  # test_bare_steal.draw_popup's frame
        x0, t, b = BS.POPUP_LEFT, BS.POPUP_TOP, BS.POPUP_BOTTOM
        x1 = x0 + popup - 1
        img[t + 2 : b - 1, x0 : x0 + 2] = 255
        img[t + 2 : b - 1, x0 + 2] = 190
        img[t + 2 : b - 1, x0 + 3 : x1 - 1] = 254
        img[t, x0 + 3 : x1 - 1] = 255
        img[b, x0 + 3 : x1 - 1] = 255
        img[t + 8 : t + 22, x0 + 8 : x0 + 22] = 40
        img[t + 10 : t + 20, x0 + 30 : x0 + 30 + popup // 2 : 3] = 40
    return img


def _armed_ref() -> np.ndarray:
    return BS.slot_crop(BS.slot_gray(_hotbar_frame(False)))


class _SimFrame(np.ndarray):
    """A simulated frame that also carries what the client SHOWED (the windows, the origin)."""

    win: tuple[str, ...] = ()
    org: tuple[int, int] | None = None


class _BareSim:
    """A simulated client for the swaps, on SIM time: the equipment window TOGGLES on its chord
    and shows ``open_s`` / ``close_s`` later; a double-click on its weapon slot while it SHOWS
    puts the dagger in the bag ``off_s`` later; the equip key wears it ``on_s`` later. Every
    input is logged with the windows the runner had READ last."""

    def __init__(self, *, open_s: float = 0.8, close_s: float = 0.3, off_s: float = 0.2,
                 on_s: float = 0.2, chord_ok: bool = True, close_ok: bool = True,
                 takes_off: bool = True, puts_on: bool = True,
                 origin: tuple[int, int] = (185, 300), others: tuple[str, ...] = (),
                 bag: bool = False, popup: int | None = None) -> None:  # fmt: skip
        self.open_s, self.close_s, self.off_s, self.on_s = open_s, close_s, off_s, on_s
        self.chord_ok, self.close_ok = chord_ok, close_ok
        self.takes_off, self.puts_on = takes_off, puts_on
        self.origin, self.others, self.popup = origin, others, popup
        self.t, self.want, self.vis, self.chord_t = 0.0, False, False, -1e9
        self.bag = self.bag_to = bag
        self.bag_t = -1e9
        self.dark = 0  # this many next frames are dark (a teleport)
        self.log: list[tuple[Any, ...]] = []
        self.read: tuple[str, ...] = ()
        self.lines: list[dict[str, Any]] = []
        self.fly_at: float | None = None  # guard() is True from then (a Fly Wing inside a swap)

    def _now(self) -> None:
        if self.want != self.vis and self.t - self.chord_t >= (
                self.open_s if self.want else self.close_s):  # fmt: skip
            self.vis = self.want
        if self.bag != self.bag_to and self.t >= self.bag_t:
            self.bag = self.bag_to

    def chord(self) -> None:
        self._now()
        self.log.append(("chord", self.read))
        if not self.chord_ok or (self.want and not self.close_ok):
            return
        self.want, self.chord_t = not self.want, self.t

    def frame(self) -> _SimFrame:
        self.t += 0.03
        self._now()
        dark = self.dark > 0
        self.dark -= int(dark)
        f = _hotbar_frame(self.bag, dark, self.popup).view(_SimFrame)
        f.win = tuple(sorted((("equipment",) if self.vis else ()) + self.others))
        f.org = self.origin if self.vis else None
        return f

    def windows(self, f: _SimFrame) -> list[str]:
        self.read = f.win
        return list(f.win)

    def origin_of(self, f: _SimFrame) -> tuple[int, int] | None:
        return f.org

    def double_click(self, x: int, y: int) -> None:
        self._now()
        self.log.append(("dclick", (x, y), self.read))
        slot = (self.origin[0] + BS.WEAPON_SLOT[0], self.origin[1] + BS.WEAPON_SLOT[1])
        if self.vis and (x, y) == slot and self.takes_off and not self.bag_to:
            self.bag_to, self.bag_t = True, self.t + self.off_s

    def press(self, why: str) -> None:
        self._now()
        self.log.append(("press", why))
        if self.bag_to and self.puts_on:
            self.bag_to, self.bag_t = False, self.t + self.on_s

    def guard(self) -> bool:
        return self.fly_at is not None and self.t >= self.fly_at

    def sleep(self, s: float) -> None:
        self.t += s

    def io(self) -> dh.BareIo:
        return dh.BareIo(frame=self.frame, windows=self.windows, origin=self.origin_of,
                         chord=self.chord, double_click=self.double_click, press=self.press,
                         lines=lambda: self.lines, guard=self.guard, sleep=self.sleep,
                         clock=lambda: self.t)  # fmt: skip


class _Stop(Exception):
    pass


def _ctl(sim: _BareSim) -> tuple[dh.BareCtl, Any, list[dict[str, Any]]]:
    from collections import Counter

    counts: Counter[str] = Counter()
    evs: list[dict[str, Any]] = []
    return dh.BareCtl(sim.io(), _armed_ref(), counts, evs.append, _Stop), counts, evs


def _kinds(sim: _BareSim) -> list[str]:
    return [str(e[0]) for e in sim.log]


def test_bare_steal_flag_refusals_and_the_run_start_record(monkeypatch, capsys) -> None:
    import pytest

    got: dict[str, Any] = {}

    def fake_run(a: Any) -> int:
        got["a"] = a
        return 0

    monkeypatch.setattr(dh, "run", fake_run)
    argv = ["dungeon_hunt.py", "run", "--strategy", "P2", "--seed", "1", "--char", "rogue"]
    monkeypatch.setattr(sys, "argv", argv)
    assert dh.main() == 0 and got["a"].bare_steal is False  # OFF by default
    monkeypatch.setattr(sys, "argv", [*argv, "--bare-steal"])
    assert dh.main() == 0 and got["a"].bare_steal is True
    monkeypatch.setattr(sys, "argv", ["dungeon_hunt.py", "run", "--help"])
    with pytest.raises(SystemExit):
        dh.main()
    help_ = " ".join(capsys.readouterr().out.split())
    assert "rogue-xmas02.md 4BX" in help_ and "under 50 % HP" in help_
    # the refusals (the Rogue only; never with the Steal opening; the dagger's key is F5)
    rogue = dh.CHARS_CONF["rogue"]["keys"]
    assert dh.bare_steal_refused("rogue", False, rogue) is None
    thief = dh.CHARS_CONF["thief"]["keys"]
    assert "the thief's" in str(dh.bare_steal_refused("thief", False, thief))
    assert "the crusader's" in str(dh.bare_steal_refused("crusader", False, dh.KEYS))
    assert "--steal" in str(dh.bare_steal_refused("rogue", True, rogue))
    assert "F5" in str(dh.bare_steal_refused("rogue", False, {**rogue, "equip": "F6"}))
    assert rogue["equip"] == BS.EQUIP_KEY and dh.hotbar_slot(rogue["equip"]) == BS.EQUIP_SLOT
    # the record: fixes_of (run_start's "fixes" and the manifest) and run_start's own key
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "bare_steal" not in dh.fixes_of(dh.argparse.Namespace(**base))
    rec = dh.fixes_of(dh.argparse.Namespace(**base, bare_steal=True))
    assert rec["bare_steal"] == [8.0, 0.5, "F5", 4, "9.27"]
    assert {k: v for k, v in rec.items() if k != "bare_steal"} == dh.fixes_of(
        dh.argparse.Namespace(**base))  # fmt: skip
    src = Path(dh.__file__).read_text()
    i_ref = src.index('raise SystemExit(f"dungeon@9.27 refused: {why_bs}")')
    assert i_ref < src.index("typed: list[str] = []")  # before the setup types anything
    i_cut = src.index('raise r.Stop(f"dungeon@9.27 refused: --bare-steal: {why_br} {bare_rec}")')
    i_start = src.index('ev({"kind": "run_start", "strategy": a.strategy')
    assert src.index("for cmd in setup:\n            setup_line(cmd)\n        bench.close") < i_cut
    assert i_cut < i_start  # the reference is cut after the setup, before the run's start
    assert '**({"bare_steal": fixes_of(a)["bare_steal"], "bare_ref": bare_rec,' in src[i_start:]


def test_the_run_start_cuts_the_armed_reference_only_from_an_empty_f5_slot() -> None:
    ref, rec, why = dh.bare_ref_cut(BS.slot_gray(_hotbar_frame(False)))
    assert why is None and ref is not None and rec["empty"] is True
    ref2, rec2, why2 = dh.bare_ref_cut(BS.slot_gray(_hotbar_frame(True)))
    assert ref2 is None and "in the bag" in str(why2) and rec2["empty"] is False
    ref3, rec3, why3 = dh.bare_ref_cut(BS.slot_gray(_hotbar_frame(False, dark=True)))
    assert ref3 is None and why3 is None and rec3["empty"] is None  # unreadable: read again
    assert dh.BARE_REF_WAIT_S == 3.0
    assert dh.bare_read(_hotbar_frame(False), ref) is False
    assert dh.bare_read(_hotbar_frame(True), ref) is True
    assert dh.bare_read(_hotbar_frame(False, dark=True), ref) is None


def test_clear_bag_refuses_while_the_dagger_is_in_the_bag() -> None:
    """clear-bag drops every inventory stack: the Rogue BARE (the dagger in the bag, its icon on
    F5) would lose the dagger. Refused before the warp and before any tab is touched."""
    rogue = dh.CHARS_CONF["rogue"]["keys"]
    assert dh.clear_bag_bare_refused(BS.slot_gray(_hotbar_frame(False)), rogue) is None
    assert "drop it" in str(dh.clear_bag_bare_refused(BS.slot_gray(_hotbar_frame(True)), rogue))
    dark = BS.slot_gray(_hotbar_frame(False, dark=True))
    assert "unreadable" in str(dh.clear_bag_bare_refused(dark, rogue))
    assert dh.clear_bag_bare_refused(BS.slot_gray(_hotbar_frame(True)), dh.KEYS) is None
    src = Path(dh.__file__).read_text()
    body = src[src.index("def clear_bag(a: argparse.Namespace) -> int:") :]
    body = body[: body.index("\ndef load_rest_spots(")]
    i_ref = body.index("raise r.Stop(why_bb)")
    assert body.index('raise r.Stop(f"identity {got}")') < i_ref < body.index("@warp")
    assert i_ref < body.index("clear_tab(agent, screen, tab=tab")


def test_bare_unequip_reads_each_step_and_clicks_only_into_the_open_window() -> None:
    sim = _BareSim()
    res = dh.bare_unequip_seq(sim.io(), _armed_ref())
    assert res["ok"] and res["bare"] and res["why"] == "off" and res["fail"] is None
    assert res["stop"] is None and res["chords"] == 2 and res["ms"] < 3000
    assert _kinds(sim) == ["chord", "dclick", "chord"]
    assert sim.log[0][1] == ()  # the chord only after NO window read open
    assert sim.log[1][1] == (203, 402) and "equipment" in sim.log[1][2]  # read OPEN first
    assert res["at"] == [203, 402] and res["origin"] == [185, 300]
    assert sim.read == () and not sim.vis and sim.bag  # read CLOSED at the end; the dagger off
    moved = _BareSim(origin=(190, 305))  # the window found 5 px off its home: aimed from there
    res2 = dh.bare_unequip_seq(moved.io(), _armed_ref())
    assert res2["ok"] and moved.log[1][1] == (208, 407) and res2["origin"] == [190, 305]


def test_bare_unequip_never_clicks_when_the_window_does_not_open_and_closes_a_late_one() -> None:
    sim = _BareSim(chord_ok=False)
    res = dh.bare_unequip_seq(sim.io(), _armed_ref())
    assert not res["ok"] and res["fail"] == "bare_fail_open" and res["why"] == "not_open"
    assert _kinds(sim) == ["chord"] and not sim.bag and res["bare"] is False
    assert res["stop"] is None
    late = _BareSim(open_s=1.5)  # shows after OPEN_S (1.2), within LATE_S more
    res2 = dh.bare_unequip_seq(late.io(), _armed_ref())
    assert res2["fail"] == "bare_fail_open" and res2.get("late") is True
    assert _kinds(late) == ["chord", "chord"]  # no double-click: ONE more chord closes it
    assert not late.vis and late.read == () and not late.bag and res2["stop"] is None


def test_bare_unequip_skips_while_a_window_is_open() -> None:
    sim = _BareSim(others=("inventory",))
    res = dh.bare_unequip_seq(sim.io(), _armed_ref())
    assert res["fail"] == "bare_skip_ui" and res["windows"] == ["inventory"]
    assert sim.log == [] and not res["ok"]  # no chord into an unknown UI


def test_bare_unequip_fails_off_cleanly_and_stops_on_a_window_that_stays() -> None:
    sim = _BareSim(takes_off=False)
    res = dh.bare_unequip_seq(sim.io(), _armed_ref())
    assert not res["ok"] and res["fail"] == "bare_fail_off" and res["why"] == "not_off"
    assert _kinds(sim) == ["chord", "dclick", "chord"] and not sim.vis and sim.read == ()
    stuck = _BareSim(close_ok=False)
    res2 = dh.bare_unequip_seq(stuck.io(), _armed_ref())
    assert res2["stop"] is not None and "equipment" in res2["stop"]
    assert _kinds(stuck) == ["chord", "dclick", "chord", "chord"]  # ONE more chord, then stop
    assert res2["bare"]  # the dagger came off: the runner keeps that truth before it stops


def test_bare_equip_reads_the_dagger_back_on_and_presses_again_only_on_a_readable_bare() -> None:
    sim = _BareSim(bag=True)
    res = dh.bare_equip_seq(sim.io(), _armed_ref(), "cyan")
    assert res["ok"] is True and res["presses"] == 1 and not sim.bag
    stuck = _BareSim(bag=True, puts_on=False)
    res2 = dh.bare_equip_seq(stuck.io(), _armed_ref(), "time")
    assert res2["ok"] is False and res2["presses"] == 2 and _kinds(stuck) == ["press", "press"]
    dark = _BareSim(bag=True, puts_on=False)
    dark.dark = 99  # a teleport's dark frames: unreadable -- no second press, no failure
    res3 = dh.bare_equip_seq(dark.io(), _armed_ref(), "safety", press=False)
    assert res3["ok"] is None and res3["presses"] == 0 and dark.log == []


def test_bare_ctl_one_target_unequips_once_equips_on_the_cue_and_at_its_end() -> None:
    sim = _BareSim()
    ctl, counts, evs = _ctl(sim)
    aims: list[int] = []
    assert ctl.before_strike("box", 0.9, lambda: aims.append(1) is None)
    assert sim.bag and not ctl.st.armed and aims == [1] and counts["bare_unequip"] == 1
    ctl.struck()
    ctl.tick(sim.t, True, True, sim.frame(), 0.9)
    assert not ctl.st.armed  # bare, locked, no cue yet
    sim.lines.append({"colour": "cyan"})  # a steal: a NEW item-colour Battle Log line
    ctl.tick(sim.t, True, True, sim.frame(), 0.9)
    assert ctl.st.armed and not sim.bag and counts["bare_equip_cyan"] == 1
    ctl.tick(sim.t, False, True, sim.frame(), 0.9)  # its lock went (a kill): the target is over
    assert ctl.tgt is None and counts["bare_equip_fight_end"] == 0  # armed: nothing pressed
    assert ctl.before_strike("scan", 0.9, lambda: True) and counts["bare_unequip"] == 2
    ctl.struck()
    ctl.tick(sim.t, False, True, sim.frame(), 0.9)  # killed bare-handed: the dagger on at once
    assert ctl.st.armed and not sim.bag and counts["bare_equip_fight_end"] == 1
    whats = [(e["what"], e["why"]) for e in evs]
    assert whats == [("unequip", "off"), ("equip", "cyan")] + [("unequip", "off"),
                                                                ("equip", "fight_end")]  # fmt: skip
    assert _kinds(sim) == ["chord", "dclick", "chord", "press"] * 2


def test_bare_ctl_drops_the_click_when_the_target_left_and_swaps_once_per_target() -> None:
    sim = _BareSim()
    ctl, counts, evs = _ctl(sim)
    assert ctl.before_strike("box", 0.9, lambda: False) is False  # no SWORD after the swap
    assert counts["bare_aim_lost"] == 1 and sim.bag and evs[-1]["what"] == "aim"
    n = len(sim.log)
    assert ctl.before_strike("scan", 0.9, lambda: False) is True  # bare already: no 2nd swap,
    assert len(sim.log) == n  # and no aim check (the scan's own SWORD read just found it)
    ctl.tick(sim.t, False, True, sim.frame(), 0.9)  # no lock yet, still fighting: stays bare
    assert not ctl.st.armed and ctl.tgt is not None
    plain = _BareSim()
    ctl2, counts2, _ = _ctl(plain)
    assert ctl2.before_strike("plant", 0.9, None) and plain.log == []  # a plant: as it is
    assert ctl2.before_strike("box", 0.4, None) and counts2["bare_skip_hp"] == 1
    assert plain.log == []  # under BARE_HP_MIN nothing comes off


def test_bare_ctl_puts_the_dagger_on_before_a_fly_wing_and_never_stays_bare_outside_a_fight(
) -> None:  # fmt: skip
    sim = _BareSim()
    ctl, counts, evs = _ctl(sim)
    ctl.before_strike("box", 0.9, None)
    ctl.struck()
    assert sim.bag
    ctl.escape()  # press("fly") calls it before the Fly Wing's key
    sim.log.append(("fly",))
    assert _kinds(sim)[-2:] == ["press", "fly"] and sim.log[-2][1] == "safety"
    assert ctl.pending == "safety" and evs[-1]["pending"] is True
    sim.dark = 40  # the teleport's dark frames: the read-back waits, no failure counted
    ctl.tick(sim.t, False, False, sim.frame(), 0.9)
    assert ctl.pending == "safety" and counts["bare_fail_on"] == 0
    sim.dark = 0
    ctl.tick(sim.t, False, False, sim.frame(), 0.9)  # mode search now: read back, target over
    assert ctl.st.armed and ctl.pending is None and counts["bare_equip_safety"] == 1
    assert ctl.tgt is None and sum(k == "press" for k in _kinds(sim)) == 1  # ONE key press
    # the safety net: bare with no target in hand and no fight -> on at once
    net = _BareSim()
    ctl2, counts2, _ = _ctl(net)
    ctl2.before_strike("box", 0.9, None)
    ctl2.tgt = None
    ctl2.tick(net.t, False, False, net.frame(), 0.9)
    assert ctl2.st.armed and counts2["bare_equip_fight_end"] == 1


def test_bare_ctl_a_popup_shown_at_the_unequip_is_no_cue_a_new_one_is() -> None:
    sim = _BareSim(popup=188)  # the last fight's loot popup is still drawn
    ctl, counts, _ = _ctl(sim)
    ctl.before_strike("box", 0.9, None)
    ctl.struck()
    ctl.tick(sim.t, True, True, sim.frame(), 0.9)
    assert not ctl.st.armed  # the same popup: no steal
    sim.popup = 240  # another item's popup (a longer name): a steal
    ctl.tick(sim.t, True, True, sim.frame(), 0.9)
    assert ctl.st.armed and counts["bare_equip_popup"] == 1


def test_bare_ctl_stops_after_three_failed_swaps_in_a_row_and_ends_armed() -> None:
    import pytest

    sim = _BareSim(takes_off=False)  # the dagger never comes off (not worn? another key?)
    ctl, counts, _ = _ctl(sim)
    for _k in range(2):
        assert ctl.before_strike("box", 0.9, None)  # armed: the strike goes on with the dagger
        ctl.struck()
        ctl.tick(sim.t, False, True, sim.frame(), 0.9)  # that target's end
    with pytest.raises(_Stop):
        ctl.before_strike("box", 0.9, None)
    assert counts["bare_fail_off"] == 3
    ok = _BareSim()
    ctl2, counts2, _ = _ctl(ok)
    ctl2.before_strike("box", 0.9, None)
    n = len(ok.log)
    assert ctl2.run_end(dead=True)["armed"] is False and len(ok.log) == n  # dead: nothing pressed
    rec = ctl2.run_end()
    assert rec["armed"] and rec["slot"] == "armed" and counts2["bare_equip_run_end"] == 1


def test_bare_ctl_a_fly_wing_inside_the_swap_ends_it_closed_and_keys_the_dagger() -> None:
    """guard_tick runs on every poll of the swap: a Fly Wing there ends the swap -- the window is
    still read closed (a late one too), and when the dagger had come off its key goes at once."""
    sim = _BareSim()
    sim.fly_at = 0.9  # after the double-click (0.84), before the dagger reads off (1.04)
    ctl, counts, evs = _ctl(sim)
    assert ctl.before_strike("box", 0.9, lambda: True)  # strike() then sees escaped[0]
    unequip = next(e for e in evs if e["what"] == "unequip")
    assert unequip["escaped"] is True and unequip["why"] == "late_off" and sim.bag
    assert _kinds(sim) == ["chord", "dclick", "chord", "press"] and sim.log[-1][1] == "safety"
    assert not sim.vis and sim.read == () and ctl.pending == "safety"
    early = _BareSim()
    early.fly_at = 0.5  # before the window showed (0.83): no double-click, the late one closed
    ctl2, counts2, evs2 = _ctl(early)
    assert ctl2.before_strike("box", 0.9, lambda: True)
    assert evs2[0]["why"] == "escaped" and evs2[0]["escaped"] is True
    assert _kinds(early) == ["chord", "chord"] and not early.vis and early.read == ()
    assert ctl2.st.armed and ctl2.pending is None and counts2["bare_fail_open"] == 0


def test_ui_double_click_is_two_motions_then_two_paced_presses() -> None:
    moves: list[tuple[int, int]] = []
    sent: list[dict[str, Any]] = []
    naps: list[float] = []

    class _Agent:
        def move(self, x: int, y: int) -> None:
            moves.append((x, y))

        def send(self, events: list[dict[str, Any]]) -> None:
            sent.extend(events)

    dh.ui_double_click(_Agent(), 300, 450, (1440, 900), lambda: 7, naps.append)
    assert moves == [(303, 453), (300, 450)]
    assert [e["action"] for e in sent] == ["down", "up", "down", "up"]
    assert all(e["type"] == "mouse_button" and e["button"] == "left" for e in sent)
    assert all((e["x"], e["y"]) == (300 / 1440, 450 / 900) for e in sent)
    assert naps == [0.05, 0.1, 0.04, 0.04, 0.04, 0.04]


def test_window_origin_finds_the_window_near_its_home_with_the_gates_own_match() -> None:
    from types import SimpleNamespace

    from poring_env import ui_anchors as ua

    tmpl = np.random.default_rng(0).integers(0, 255, (13, 60)).astype(np.float32)
    reg = SimpleNamespace(windows={"equipment": ua.WINDOWS["equipment"]},
                          templates={"equipment": tmpl}, masks={})  # fmt: skip
    ox, oy = ua.WINDOWS["equipment"].template_offset

    def frame_at(dx: int, dy: int) -> np.ndarray:
        img = np.full((720, 1280, 3), 100, np.uint8)
        x, y = 185 + ox + dx, 300 + oy + dy
        img[y : y + 13, x : x + 60] = tmpl.astype(np.uint8)[..., None]
        return img

    assert dh.window_origin(frame_at(0, 0), reg, "equipment") == (185, 300)
    assert dh.window_origin(frame_at(5, 5), reg, "equipment") == (190, 305)
    assert dh.window_origin(frame_at(40, 0), reg, "equipment") is None  # beyond HOME_PX
    assert dh.window_origin(np.full((720, 1280, 3), 100, np.uint8), reg, "equipment") is None


def test_bare_steal_is_wired_off_by_default_at_strike_tick_escapes_and_end() -> None:
    """The flag off: ``bare`` stays None and every hook is a no-op (today's run). On: the swap is
    strike()'s FIRST step, before its frame and its click; the lock is marked on its last
    return; the dagger's key goes BEFORE every Fly Wing (press) and before both walk-aways; the
    tick runs before the fight branch; the run_end record carries the final state."""
    src = Path(dh.__file__).read_text()
    assert src.count("bare = BareCtl(") == 1
    i_on = src.index("        if bare_on:  # dungeon@9.27: every input is the runner's own")
    assert i_on < src.index("bare = BareCtl(") < src.index("        def strike(u: float")
    assert "bare: BareCtl | None = None" in src
    body = src[src.index("        def strike(u: float, v: float, rel: Cell, by: str) -> bool:") :]
    body = body[: body.index("\n        def box_target(")]
    hook = 'if not bare.before_strike(by, hp_b, lambda: hover(u, v)["verdict"] == "sword"):'
    i_b = body.index(hook)
    assert i_b < body.index("if escaped[0]:\n                    return True") < body.index(
        "ref = frame()") < body.index('click_at(u, v, "strike")')  # fmt: skip
    assert body.rstrip().endswith("bare.struck()  # dungeon@9.27: the caller holds this target's "
                                  "lock now\n            return True")  # fmt: skip
    pb = src[src.index("        def press(what: str, why: str) -> None:") :]
    pb = pb[: pb.index("\n        def ", 10)]
    assert pb.index("bare.escape()") < pb.index("agent_raw.keys(keys_[what])")
    assert 'if what == "fly" and bare is not None:' in pb
    assert src.count("bare.escape()") == 3  # press + the boss walk-away + the unreach walk
    for ind in (" " * 24, " " * 16):  # the boss guard's walk-away; --unreach-escape's walk
        assert (f"{ind}bare.escape()  # dungeon@9.27: never walk away bare\n{ind}"
                'click_at(u_w, v_w, "walk")') in src  # fmt: skip
    assert ('bare.tick(tick, lock is not None, mode == "fight", img, frac)\n'
            "                # --- FIGHT: locked, or scan for the attacker") in src  # fmt: skip
    i_end = src.index('bare_final = bare.run_end(dead=reason == "death")')
    assert i_end < src.index('ev({"kind": "run_end", "reason": reason')
    assert '**({"bare": bare_final} if bare_final is not None else {})' in src
    assert 'ev({"kind": "bare_after_alive", **bare.run_end()})' in src
    # the I/O is the runner's own: the gate's window read, its chord, press(), ui_double_click
    assert "windows=lambda f_: ui_gate.windows_at_home(f_, bare_reg)" in src
    assert "chord=lambda: agent_raw.chord(*bare_keys)" in src
    assert 'press=lambda why_: press("equip", why_)' in src
    assert "ui_double_click(agent, gx0 + u_, gy0 + v_, r.desktop(), r.ns)" in src
    assert src.count("ui_double_click(") == 2  # its definition + the one call
