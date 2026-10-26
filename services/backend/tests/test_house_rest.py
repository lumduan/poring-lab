"""--rest house (docs/planning/gef10-house-rest.md): the pure planning of a rest inside an orc house
(in_orcs01) -- the door / exit pairing, the sealed-room rule that keeps the dungeon warps out of
reach, the exit click cell and its screen point, the approach cells, the door choice, the pixel
map-change tracker, the trip's closed transition table -- and the runner's and the judge's hooks.
Synthetic grids only; one test reads the real local data when it is there (skipped otherwise)."""

from __future__ import annotations

import ast
import itertools
import json
import sys
from argparse import Namespace
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import dungeon_judge as dj  # noqa: E402
import house_rest as hr  # noqa: E402
import map_zones as mz  # noqa: E402

from poring_dataset import camera as cam  # noqa: E402

NS = 1_000_000_000


def _w(name: str, x: int, y: int, sx: int, sy: int, to: str, tx: int, ty: int) -> dict[str, object]:
    return {"name": name, "x": x, "y": y, "span_x": sx, "span_y": sy, "to_map": to, "to_x": tx,
            "to_y": ty}  # fmt: skip


# data/kb/warps.json's rows for the two maps (rAthena npc/pre-re/warps/fields/geffen_fild.txt and
# npc/warps/dungeons/orcsdun.txt), restated as in test_map_prep.py's GEF10_SPANS; the runner reads
# the real file at run time
KB = {
    "gef_fild10": [
        _w("geff11-1", 251, 371, 5, 2, "gef_fild09", 225, 28),
        _w("geff12", 104, 21, 5, 2, "gef_fild11", 114, 360),
        _w("geff05-1", 370, 56, 2, 5, "gef_fild03", 21, 52),
        _w("gef018", 136, 331, 1, 1, "in_orcs01", 122, 171),
        _w("gef019", 138, 284, 1, 1, "in_orcs01", 29, 114),
        _w("gef020", 215, 51, 1, 1, "in_orcs01", 162, 53),
        _w("gef021", 223, 205, 1, 1, "in_orcs01", 108, 89),
        _w("gef022", 63, 337, 1, 1, "in_orcs01", 30, 157),
        _w("geff19-1", 27, 219, 1, 1, "gef_fild14", 367, 219),
    ],
    "in_orcs01": [
        _w("orc001", 108, 86, 3, 2, "gef_fild10", 223, 203),
        _w("orc002", 124, 171, 1, 3, "gef_fild10", 138, 329),
        _w("orc003", 162, 55, 4, 1, "gef_fild10", 214, 53),
        _w("orc004", 29, 116, 4, 1, "gef_fild10", 137, 286),
        _w("orc005", 30, 154, 3, 2, "gef_fild10", 65, 335),
        _w("orc01", 30, 182, 2, 1, "orcsdun01", 32, 170),
        _w("orc02", 108, 114, 2, 1, "orcsdun02", 180, 17),
    ],
}
# (door) -> (arrival, exit, the exit's return cell, the click cell = the exit's centre)
EXPECTED = {
    "gef018": ((122, 171), "orc002", (138, 329), (124, 171)),
    "gef019": ((29, 114), "orc004", (137, 286), (29, 116)),
    "gef020": ((162, 53), "orc003", (214, 53), (162, 55)),
    "gef021": ((108, 89), "orc001", (223, 203), (108, 86)),
    "gef022": ((30, 157), "orc005", (65, 335), (30, 154)),
}
# the touch NPCs the pre-renewal server loads in in_orcs01 (npc/quests/newgears/2004_headgears.txt
# Orc Warrior#1 / Orc Hero#1, 2008_headgears.txt Orc Lady#2008hat03): cell, touch span
NPCS = [((31, 93), 2), ((162, 33), 2), ((119, 106), 2)]


def rooms() -> np.ndarray:
    """A synthetic in_orcs01 shaped like the real one's five rooms (each a rectangle round its
    arrival and its exit); gef021's and gef022's rooms reach up to their dungeon warp (the real
    map: orc02 / orc01 24 steps from the arrival), the other three are closed boxes."""
    g = np.zeros((200, 200), dtype=bool)

    def box(x0: int, x1: int, y0: int, y1: int) -> None:
        g[y0 : y1 + 1, x0 : x1 + 1] = True

    box(112, 128, 162, 178)  # gef018: arrival 122,171, exit 123-125 x 168-174
    box(20, 38, 90, 120)  # gef019: arrival 29,114, exit 25-33 x 115-117 (Orc Warrior#1 at 31,93)
    box(150, 170, 30, 58)  # gef020: arrival 162,53, exit 158-166 x 54-56 (Orc Hero#1 at 162,33)
    box(100, 122, 82, 116)  # gef021: up to orc02 (106-110 x 113-115) and Orc Lady (119,106)
    box(24, 40, 150, 184)  # gef022: up to orc01 (28-32 x 181-183)
    return g


def test_the_five_doors_pair_with_their_own_exits_and_the_dungeon_warps_are_forbidden() -> None:
    hs = {h.name: h for h in hr.houses(KB)}
    assert sorted(hs) == sorted(EXPECTED)
    for name, (arrival, exit_, back, _click) in EXPECTED.items():
        h = hs[name]
        assert (h.arrival, h.exit.name, h.back) == (arrival, exit_, back)
        assert h.exit.cheb_to(h.arrival) <= hr.EXIT_NEAR
    assert [w.name for w in hr.forbidden_warps(KB)] == ["orc01", "orc02"]


def test_a_door_without_exactly_one_matching_exit_refuses() -> None:
    kb = json.loads(json.dumps(KB))
    kb["in_orcs01"] = [w for w in kb["in_orcs01"] if w["name"] != "orc003"]
    with pytest.raises(ValueError, match="gef020"):
        hr.houses(kb)
    kb2 = json.loads(json.dumps(KB))
    kb2["in_orcs01"].append(_w("orc003b", 162, 51, 4, 1, "gef_fild10", 215, 54))
    with pytest.raises(ValueError, match="2 matching exits"):
        hr.houses(kb2)


def test_only_the_sealed_rooms_are_usable_and_every_click_is_far_from_the_dungeon_warps() -> None:
    g = rooms()
    fb = hr.forbidden_warps(KB)
    rows = {h.name: hr.room_check(h, g, fb, NPCS) for h in hr.houses(KB)}
    usable = {n for n, c in rows.items() if hr.usable_why(c) is None}
    assert usable == {"gef018", "gef019", "gef020"}
    assert rows["gef021"]["steps"]["corner_rule"]["orc02"] == 24
    assert rows["gef022"]["steps"]["corner_rule"]["orc01"] == 24
    assert "not sealed" in str(hr.usable_why(rows["gef022"]))
    for name, (_a, _e, _b, click) in EXPECTED.items():
        c = rows[name]
        assert tuple(c["click"]) == click
        assert c["steps"]["corner_rule"]["click"] in (2, 3)  # 2-3 steps from the arrival
        # the brief's check, for ALL five houses: the clicked exit cell >= 10 cells from both
        assert min(c["forbidden_cheb_from_click"].values()) >= hr.FORBIDDEN_MIN
        assert min(c["npc_cheb_from_click"]) >= 10  # and from every touch NPC
    for name in usable:
        assert all(rows[name]["steps"][k][w] is None for k in ("corner_rule", "no_corner_rule")
                   for w in ("orc01", "orc02"))  # fmt: skip


def test_a_room_that_reaches_a_dungeon_warp_only_corner_to_corner_is_not_sealed() -> None:
    """The client cannot cut that corner (rAthena's rule), but the room counts as sealed only
    when NEITHER rule reaches a forbidden cell."""
    g = rooms()
    h = next(h for h in hr.houses(KB) if h.name == "gef018")
    g[179, 129] = True  # one cell diagonal to the room's corner (128,178) ...
    g[180:186, 129:140] = True  # ... opening into a corridor ...
    g[186:190, 130:140] = True
    kb = json.loads(json.dumps(KB))
    kb["in_orcs01"].append(_w("orc09", 135, 188, 1, 1, "orcsdun01", 1, 1))  # ... a dungeon warp
    fb = hr.forbidden_warps(kb)
    c = hr.room_check(h, g, fb)
    assert c["steps"]["corner_rule"]["orc09"] is None
    assert c["steps"]["no_corner_rule"]["orc09"] is not None
    assert c["sealed"] is False and hr.usable_why(c) is not None


def test_the_exit_click_is_the_centre_else_the_widest_margin_cell_nearest_the_arrival() -> None:
    h = next(h for h in hr.houses(KB) if h.name == "gef022")  # orc005: 27-33 x 152-156
    g = rooms()
    assert hr.exit_click(h, g) == (30, 154)
    g2 = g.copy()
    g2[154, 30] = False
    assert hr.exit_click(h, g2) in {(29, 154), (31, 154)}  # margin 1 (y) like the centre's row
    g3 = g.copy()
    g3[152:157, 27:34] = False
    assert hr.exit_click(h, g3) is None


def _cj() -> dict[str, object]:
    return json.loads((ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                      .read_text())  # fmt: skip


class FlatGat:
    def relative_altitude(self, origin: tuple[int, int], offsets: np.ndarray) -> np.ndarray:
        return np.zeros(len(offsets))


def test_the_exit_point_is_the_indoor_cameras_projection_on_a_flat_floor() -> None:
    """in_orcs01 is an indoor map (the client's table): the camera rotated ~46 degrees and closer.
    Its floor is flat between every arrival and its click (the real GAT: 0.0 relative altitude),
    so the point is the flat projection; the character stands at the screen centre."""
    cj = _cj()
    icam = cam.map_camera(cj, "in_orcs01", frozenset({"in_orcs01"}))
    ocam = cam.map_camera(cj, "gef_fild10", frozenset({"in_orcs01"}))
    assert icam is not None and ocam is not None and icam.yaw != ocam.yaw
    hs = {h.name: h for h in hr.houses(KB)}
    for name, (_a, _e, _b, click) in EXPECTED.items():
        h = hs[name]
        flat = hr.exit_point(icam, None, h, click)
        assert hr.exit_point(icam, FlatGat(), h, click) == pytest.approx(flat)
        here = hr.exit_point(icam, None, hr.House(hr.Warp("x", h.door.cell, (1, 1), "in_orcs01",
                                                          click), h.exit), click)  # fmt: skip
        assert here == pytest.approx((icam.cx, icam.cy))  # rel (0, 0) = the screen centre
        assert 30 <= flat[0] <= 1250 and 30 <= flat[1] <= 690  # in the game view
        d = np.hypot(flat[0] - icam.cx, flat[1] - icam.cy)
        assert 40 < d < 200  # 2-3 cells away: a short, unambiguous click
    # north (+y) is drawn UP on screen, east (+x) to the right (gef019: +2 north; gef018: +2 east)
    u19, v19 = hr.exit_point(icam, None, hs["gef019"], EXPECTED["gef019"][3])
    u18, v18 = hr.exit_point(icam, None, hs["gef018"], EXPECTED["gef018"][3])
    assert v19 < icam.cy and u18 > icam.cx


def _field() -> tuple[np.ndarray, mz.Zones]:
    ok = np.ones((60, 60), dtype=bool)
    z = mz.Zones(map="t", reviewed_by="x", reviewed="2026-10-26", no_enter=(
        mz.NoEnter("door-a", "", ((25, 25), (35, 25), (35, 35), (25, 35))),
        mz.NoEnter("npc", "", ((37, 26), (45, 26), (45, 34), (37, 34))),
    ), no_cross=(mz.NoCross("wall", "", ((24, 20), (24, 30))),))  # fmt: skip
    return ok, z


def test_the_approach_cells_lie_outside_every_area_and_the_door_click_enters_only_its_own() -> None:
    ok, z = _field()
    door = hr.Warp("d", (30, 30), (1, 1), "in_orcs01", (5, 5))
    h = hr.House(door, hr.Warp("e", (5, 3), (1, 1), "t", (30, 27)))
    okr = mz.route_grid(ok, z)
    free = hr.door_free(mz.apply(ok, ok, z)[0], ok, door)
    cells = hr.approach_cells(h, okr, free, z)
    assert cells and all(okr[c[1], c[0]] and not mz.in_no_enter(z, c) for c in cells)
    assert all(max(abs(c[0] - 30), abs(c[1] - 30)) <= hr.APPROACH_R for c in cells)
    zw = hr.zones_without(z, door)
    assert [p.id for p in zw.no_enter] == ["npc"] and zw.no_cross == z.no_cross
    assert all(mz.walk_why(zw, free, c, door.cell) is None for c in cells)
    assert (30, 23) in cells and (30, 37) in cells  # straight in from the south / the north
    assert (23, 26) not in cells  # behind the wall: its walk would cross the no-cross line
    assert all(not mz.in_no_enter(z, c) for c in cells)  # never from inside the NPC's area


def test_the_door_click_grid_opens_only_the_chosen_doors_touch_area() -> None:
    both = np.ones((60, 60), dtype=bool)
    ok = both.copy()
    door = hr.Warp("d", (30, 30), (1, 1), "in_orcs01", (5, 5))
    other = hr.Warp("o", (10, 10), (1, 1), "in_orcs01", (6, 6))
    for w in (door, other):  # the stand grid keeps every warp span off
        for c in w.cells():
            ok[c[1], c[0]] = False
    g = hr.door_free(ok, both, door)
    assert all(g[c[1], c[0]] for c in door.cells())
    assert not any(g[c[1], c[0]] for c in other.cells())
    assert not ok[30, 30]  # a new array: the stand grid itself is untouched


def test_the_door_is_chosen_by_route_steps_not_by_distance_and_within_the_bound() -> None:
    g = np.ones((80, 80), dtype=bool)
    g[0:70, 40] = False  # a wall east of us, open only at the south end
    a = hr.House(hr.Warp("a", (50, 10), (1, 1), "in_orcs01", (1, 1)), hr.Warp("ea", (1, 3), (1, 1),
                 "t", (50, 12)))  # fmt: skip
    b = hr.House(hr.Warp("b", (10, 40), (1, 1), "in_orcs01", (2, 2)), hr.Warp("eb", (2, 4), (1, 1),
                 "t", (10, 42)))  # fmt: skip
    here = (38, 10)  # 12 cells from a's approach (50,10) as the crow flies, but behind the wall
    got = hr.choose(here, [(a, [(48, 10)]), (b, [(12, 40)])], g, max_steps=200)
    assert got is not None and got[0].name == "b" and got[2] == 30
    assert hr.choose(here, [(a, [(48, 10)])], g, max_steps=200)[2] > 60  # type: ignore[index]
    assert hr.choose(here, [(a, [(48, 10)]), (b, [(12, 40)])], g, max_steps=20) is None
    tie = hr.choose((10, 10), [(b, [(10, 14)]), (a, [(10, 6)])], g, max_steps=50)
    assert tie is not None and tie[0].name == "a"  # equal steps: the door's name decides


def reads(seq: list[tuple[float, bool, tuple[int, int] | None, float]], tr: hr.Transition) -> str:
    out = "wait"
    for t, ok_, xy, m in seq:
        out = tr.step(t, ok_, xy, m)
        if out != "wait":
            return out
    return out


def test_batts_own_door_step_reads_as_inside_from_pixels() -> None:
    """His demo frames, 2026-10-26 10:05:5x (5 Hz): the readout until +0.54 s, the loading screen
    +0.76..+3.77 s (HP unread, mean 175), one black frame, then HP read, NO readout, mean 26-39."""
    seq = [(0.2 * i, True, (66, 332), 105.0) for i in range(4)]
    seq += [(0.76 + 0.2 * i, False, None, 175.0) for i in range(16)]
    seq += [(3.94, False, None, 8.0)]
    seq += [(4.15 + 0.2 * i, True, None, 27.0 + i) for i in range(12)]
    tr = hr.Transition("inside", 0.0)
    assert reads(seq, tr) == "inside"
    assert tr.gap_t0 == pytest.approx(0.76) and tr.gap_t1 == pytest.approx(4.15)


def test_every_other_outcome_of_the_door_step_is_named() -> None:
    gap = [(0.5 + 0.2 * i, False, None, 175.0) for i in range(10)]  # a 2-s load
    after = 2.6
    # a readout after the load: another map with a minimap -> STOP
    got = reads(gap + [(after, True, (200, 40), 110.0)], hr.Transition("inside", 0.0))
    assert got.startswith("stop:") and "another map" in got
    # no readout but a BRIGHT frame for long: an unknown map -> STOP
    bright = [(after + 0.2 * i, True, None, 110.0) for i in range(30)]
    assert reads(gap + bright, hr.Transition("inside", 0.0)).startswith("stop:no minimap")
    # no load at all within ENTER_MAX_S: the warp did not fire
    still = [(0.2 * i, True, (66, 332), 105.0) for i in range(50)]
    assert reads(still, hr.Transition("inside", 0.0)) == "none"
    # a short blink of Basic Info is not a load
    xy = (66, 332)
    blink = [(0.2, True, xy, 105.0), (0.4, False, None, 105.0), (0.6, True, xy, 105.0)]
    tr = hr.Transition("inside", 0.0)
    assert reads(blink, tr) == "wait" and tr.gap_t0 is None and tr.gap_t1 is None
    # a loading screen that never ends
    hang = [(0.5 + i, False, None, 175.0) for i in range(25)]
    assert reads(hang, hr.Transition("inside", 0.0)).startswith("stop:the loading screen")
    # Basic Info lost again after the load
    lost = [(after, True, None, 27.0), (after + 0.2, False, None, 27.0)]
    assert reads(gap + lost, hr.Transition("inside", 0.0)).startswith("stop:Basic Info")


def test_the_exit_step_reads_back_only_at_the_houses_return_cell() -> None:
    gap = [(0.5 + 0.2 * i, False, None, 175.0) for i in range(10)]
    after = 2.6
    back = (138, 329)
    assert reads(gap + [(after, True, (137, 330), 105.0)],
                 hr.Transition("back", 0.0, back=back)) == "back"  # fmt: skip
    got = reads(gap + [(after, True, (30, 182), 105.0)], hr.Transition("back", 0.0, back=back))
    assert got.startswith("stop:readout")
    # a bright field frame whose readout does not read (a roof behind it): own knowledge after
    # BACK_READ_S -- the sealed room's ONLY warp is its own exit
    bright = [(after + 0.25 * i, True, None, 105.0) for i in range(40)]
    assert reads(gap + bright, hr.Transition("back", 0.0, back=back)) == "back"
    dark = [(after + 0.25 * i, True, None, 30.0) for i in range(40)]
    assert reads(gap + dark, hr.Transition("back", 0.0, back=back)).startswith("stop:still a dark")
    assert reads([(0.2 * i, True, None, 30.0) for i in range(50)],
                 hr.Transition("back", 0.0, back=back)) == "none"  # fmt: skip


def test_an_unasked_load_on_the_field_is_a_bar_unless_a_fly_wing_or_our_click_explains_it() -> None:
    assert hr.gap_unexpected(2.5, since_fly_s=1e9, since_click_s=1e9, fly_jump_s=15.0)
    assert not hr.gap_unexpected(1.5, since_fly_s=1e9, since_click_s=1e9, fly_jump_s=15.0)
    assert not hr.gap_unexpected(12.4, since_fly_s=0.6, since_click_s=1e9, fly_jump_s=15.0)
    assert not hr.gap_unexpected(5.0, since_fly_s=1e9, since_click_s=1.0, fly_jump_s=15.0)


def test_the_trip_follows_its_table_and_anything_else_stops() -> None:
    t = hr.Trip()
    for e in ("rest_wanted", "door_click", "inside", "sat", "done", "exit_click", "exit_click",
              "back", "resumed"):  # fmt: skip
        t.advance(e)
    assert t.state == "field"
    assert [s for s, _e, _n in t.log] == ["field", "walk", "door", "inside", "rest", "exit",
                                          "exit", "exit", "back"]  # fmt: skip
    events = sorted({e for _s, e in hr.NEXT})
    for s, e in itertools.product(hr.STATES, events):
        t2 = hr.Trip(state=s)
        if (s, e) in hr.NEXT:
            assert t2.advance(e) == hr.NEXT[(s, e)]
        else:
            with pytest.raises(hr.TripStop):
                t2.advance(e)
    # the field logic (sustain's Fly Wing, the position rules) is off from the door click until
    # the field's readout is back; never a Fly Wing inside (in_orcs01: noteleport)
    assert {s for s in hr.STATES if hr.Trip(state=s).off_field} == {"door", "inside", "rest",
                                                                   "exit", "back"}  # fmt: skip
    # a retry: no load after the door click -> walk -> click again; the exit only from rest
    t3 = hr.Trip(state="door")
    assert t3.advance("none") == "walk" and t3.advance("door_click") == "door"
    with pytest.raises(hr.TripStop):
        hr.Trip(state="walk").advance("exit_click")


def test_the_runners_house_decisions() -> None:
    assert dh.house_trip_why(None, None) == "hp unread"
    assert "0.25" in str(dh.house_trip_why(0.25, ("h", (1, 1), 10)))
    assert "no sealed door" in str(dh.house_trip_why(0.5, None))
    assert dh.house_trip_why(0.5, ("h", (1, 1), 10)) is None
    hist = [(0.0, (5, 5)), (0.2, (6, 5)), (0.4, (7, 5)), (0.6, (7, 5)), (1.0, (7, 5))]
    assert dh.still_since(hist, 1.2) == pytest.approx(0.8)
    assert dh.still_since([], 1.0) == 0.0


def test_the_default_run_records_no_rest_field_and_house_mode_does() -> None:
    a = Namespace(plant_sweep=False, box_ignore=2, ag_match=40.0, walk_trust=True, rest="spot")
    assert dh.fixes_of(a) == {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0,
                              "walk_trust": True}  # fmt: skip
    a.rest = "house"
    assert dh.fixes_of(a)["rest"] == "house"


def test_the_runner_reaches_the_house_code_only_with_rest_house() -> None:
    src = (ROOT / "scripts" / "dungeon_hunt.py").read_text()
    tree = ast.parse(src)
    # the CLI default is today's rest
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") == "add_argument" and n.args
             and isinstance(n.args[0], ast.Constant) and n.args[0].value == "--rest"]  # fmt: skip
    assert len(calls) == 1
    kw = {k.arg: k.value for k in calls[0].keywords}
    assert isinstance(kw["default"], ast.Constant) and kw["default"].value == "spot"
    # the two new world clicks go through the runner's ONE click path (click_at, FrameGuard),
    # once each: the door click and the exit click (test_click_census counts `.click(`)
    assert src.count('click_at(u_, v_, "house_door")') == 1
    assert src.count('click_at(u_, v_, "house_exit")') == 1
    assert "trip = hr.Trip() if house_on else None" in src
    assert 'house_on = a.rest == "house"' in src


def test_the_judge_allows_exactly_the_runners_recorded_house_trip() -> None:
    t = 100 * NS
    events = [{"t_ns": t, "kind": "house_door", "arrival": [122, 171]},
              {"t_ns": t + 300 * NS, "kind": "house_exit", "back": [138, 329]}]  # fmt: skip
    allow = dj.house_allow(events, "gef_fild10")
    assert [(m, c) for _t, m, c in allow] == [("in_orcs01", (122, 171)),
                                              ("gef_fild10", (138, 329))]  # fmt: skip

    def mc(dt_s: float, m: str, x: int, y: int) -> dict[str, object]:
        return {"type": "map_change", "t_mono_ns": t + int(dt_s * NS), "map": f"{m}.gat",
                "x": x, "y": y, "gm_command": False}  # fmt: skip

    trip = [mc(4, "in_orcs01", 122, 171), mc(305, "gef_fild10", 138, 329)]
    hb = dj.hard_bars(trip, 0, t + 1000 * NS, "gef_fild10", allow=allow)
    assert hb["map_changes_house"] == 2 and hb["map_changes_other"] == 0 and hb["pass"]
    assert hb["map_changes_same_map"] == 0
    # the dungeon, another house's arrival, too late, or a second entry: still bars
    for bad in (mc(4, "orcsdun01", 32, 170), mc(4, "in_orcs01", 30, 157),
                mc(40, "in_orcs01", 122, 171)):  # fmt: skip
        hb2 = dj.hard_bars([bad], 0, t + 1000 * NS, "gef_fild10", allow=allow)
        assert hb2["map_changes_other"] == 1 and not hb2["pass"]
    hb3 = dj.hard_bars([trip[0], mc(10, "in_orcs01", 122, 171)], 0, t + 1000 * NS, "gef_fild10",
                       allow=allow)  # fmt: skip
    assert hb3["map_changes_house"] == 1 and hb3["map_changes_other"] == 1
    # without house events the judge's record is the one it always was (no new key)
    assert "map_changes_house" not in dj.hard_bars(trip, 0, t + 1000 * NS, "gef_fild10")
    assert dj.house_allow([{"t_ns": 1, "kind": "rest_start"}], "gef_fild10") == []


def test_the_real_rooms_when_the_local_data_is_there() -> None:
    """The real in_orcs01 (client GAT + the server's map cache, generated locally, never
    committed): three sealed rooms, two holding a dungeon warp 24 steps from the arrival."""
    from poring_dataset import walkable as wk

    kb_path = ROOT / "data" / "kb" / "warps.json"
    if not kb_path.exists() or not (cam.GAT_DIR / "in_orcs01.gat").exists():
        pytest.skip("no local L3 / in_orcs01 GAT (generated at run time, never committed)")
    try:
        _gat, both = wk.load_both("in_orcs01")
    except (OSError, ValueError) as e:
        pytest.skip(f"no server map cache: {e}")
    rows = {r_["house"]: r_ for r_ in hr.table(json.loads(kb_path.read_text()), both, NPCS)}
    assert {n for n, r_ in rows.items() if r_["usable_why"] is None} == {"gef018", "gef019",
                                                                         "gef020"}  # fmt: skip
    assert rows["gef022"]["steps"]["corner_rule"]["orc01"] == 24
    assert rows["gef021"]["steps"]["corner_rule"]["orc02"] == 24
    for r_ in rows.values():
        assert min(r_["forbidden_cheb_from_click"].values()) >= hr.FORBIDDEN_MIN


def test_the_multi_source_steps_are_the_nearest_sources_and_one_source_is_steps_from() -> None:
    g = np.ones((20, 20), dtype=bool)
    g[0:15, 10] = False  # a wall, open at the south end (y >= 15)
    d = hr.steps_from_many(g, [(2, 2), (18, 2)])
    assert d[2, 5] == 3 and d[2, 15] == 3  # each side: its own source
    d1 = hr.steps_from_many(g, [(2, 2)])
    assert (d1 == hr.steps_from(g, (2, 2))).all() and d1[2, 15] > 20  # around the wall
    assert (hr.steps_from_many(g, [(10, 2)]) == -1).all()  # a source off the grid reaches nothing


def test_rest_decisions_take_the_last_position_read_before_each_rest_go() -> None:
    evs = [{"kind": "rest_go", "pct": 50},  # no position yet: skipped
           {"kind": "hp_read", "pos": [5, 6]}, {"kind": "hp_read", "pos": None},
           {"kind": "rest_go", "pct": 44}, {"kind": "hp_read", "pos": [7, 8]},
           {"kind": "rest_go", "pct": None}]  # fmt: skip
    assert hr.rest_decisions(evs) == [((5, 6), 44), ((7, 8), None)]


def test_the_runners_start_up_refuses_any_other_map() -> None:
    with pytest.raises(SystemExit, match="only gef_fild10"):
        dh.house_setup("orcsdun01", ROOT / "data" / "kb", None, None, None, {}, (1280, 720),
                       lambda u, v: False)  # fmt: skip


def test_the_runners_start_up_on_the_real_local_data() -> None:
    """The start-up the runner would make with --rest house (skipped without the local data): the
    three sealed houses with their approach cells and exit pixels; gef021 / gef022 refused."""
    if not (ROOT / "data" / "kb" / "warps.json").exists() or not all(
            (cam.GAT_DIR / f"{m}.gat").exists() for m in ("in_orcs01", "gef_fild10")):  # fmt: skip
        pytest.skip("no local L3 / client GATs (generated at run time, never committed)")
    try:
        ok, okr, zones, _both = hr.field_grids("gef_fild10")
        hs, ap, px, rec = dh.house_setup("gef_fild10", ROOT / "data" / "kb", ok, okr, zones,
                                         _cj(), (1280, 720), lambda u, v: False)  # fmt: skip
    except (OSError, ValueError) as e:
        pytest.skip(f"local data incomplete: {e}")
    assert [h.name for h in hs] == ["gef018", "gef019", "gef020"]
    assert sorted(rec["refused"]) == ["gef021", "gef022"]
    assert all("not sealed" in w for w in rec["refused"].values())
    assert px["gef018"] == pytest.approx((709.0, 312.0), abs=0.1)
    assert px["gef019"] == pytest.approx((569.9, 313.8), abs=0.1)
    assert px["gef020"] == pytest.approx((569.9, 313.8), abs=0.1)
    assert all(len(v) >= 60 for v in ap.values())
    assert all(not mz.in_no_enter(zones, c) and okr[c[1], c[0]] for v in ap.values() for c in v)
