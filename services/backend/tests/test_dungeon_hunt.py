"""dungeon_hunt.py (dungeon@1, Batt 2026-10-22, demonstrations 3.98): the pure sustain rules of the
three strategies, the defend-scan ring, the triggers, and the runner's isolation (pixels in)."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

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
    assert rogue["keys"] == thief["keys"] and rogue["keys"]["steal"] == "F3"
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
    assert "walk_target(goal_path, MR_WALK_AHEAD if mr else a.walk_ahead, fits)" in src
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
    assert "and tick - last_walk >= a.walk_every:" in src and dh.WALK_EVERY_S == 1.2


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
    assert 'ev({"kind": "box_model", "choice": a.box_model, **boxes.model})' in src
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
    assert '"cpu" if a.box_detector == "cpu" else "gpu")' in src
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
    assert "return skip_b(foot) or not in_view(foot[0], foot[1] - BODY_UP)" in src
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
