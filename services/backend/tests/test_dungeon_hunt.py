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
    assert dh.VERSION == "dungeon@8"  # @8 = @7 + --char rogue (2026-10-25)
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
    assert (rogue["max_hp"], rogue["max_sp"]) == (2146, 336)
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
