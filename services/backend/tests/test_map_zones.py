"""map_zones: Batt's per-map forbidden zones (2026-10-20 ~21:0x, "map traps") -- the loader (fail
closed, INERT without a file), the masks, the routes that keep them, the click refusal, the way
out, and the runner's call sites (hunt_flow.py). The fixture is a SYNTHETIC map: an open field, a
wall band with a 2-cell-wide entrance, and a big room behind it."""

from __future__ import annotations

import hashlib
import math
import random
import struct
import sys
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import hunt_core as hc  # noqa: E402
import map_zones as mz  # noqa: E402

H, W = 60, 60
FIELD = (30, 20)  # a field cell south of the entrance
ROOM = (30, 45)  # a room cell north of it
ENTRY_LINE = [[28, 35], [31, 35]]  # across the entrance (x 29..30, y 31..35), at the room
ROOM_POLY = [[16, 36], [44, 36], [44, 54], [16, 54]]


def fixture_map() -> Any:
    """60 x 60 cells, [y, x], y north: the OPEN FIELD (x 2..57, y 2..30), a WALL band (y 31..35)
    open only at the ENTRANCE (x 29..30), the BIG ROOM (x 16..44, y 36..54) behind it."""
    ok = np.zeros((H, W), dtype=bool)
    ok[2:31, 2:58] = True
    ok[36:55, 16:45] = True
    ok[31:36, 29:31] = True
    return ok


def zones_of(no_cross: Any = (), no_enter: Any = ()) -> mz.Zones:
    return mz.Zones(
        map="fix_map", reviewed_by="batt", reviewed="2026-10-21",
        no_cross=tuple(mz.NoCross(f"nc{i}", "n", tuple(map(tuple, p)))
                       for i, p in enumerate(no_cross)),
        no_enter=tuple(mz.NoEnter(f"ne{i}", "n", tuple(map(tuple, p)))
                       for i, p in enumerate(no_enter)),
    )  # fmt: skip


GOOD = """\
map: fix_map
reviewed_by: batt
reviewed: 2026-10-21
no_cross:
  - id: nc1
    note: across the entrance
    points: [[28, 35], [31, 35]]
no_enter:
  - id: ne1
    note: the room itself
    polygon: [[16, 36], [44, 36], [44, 54], [16, 54], [16, 36]]
"""


def write(tmp: Path, text: str, name: str = "fix_map.yaml") -> Path:
    p = tmp / name
    p.write_text(text)
    return p


# --- the loader -----------------------------------------------------------------------------------


def test_no_file_is_none_and_every_function_is_inert_without_zones(tmp_path: Path) -> None:
    assert mz.load("fix_map", tmp_path) is None
    ok = fixture_map()
    area = ok.copy()
    ok_z, area_z = mz.apply(ok, area, None)
    assert ok_z is ok and area_z is area  # the very same objects, unchanged
    assert mz.route_grid(ok, None) is ok
    assert mz.path_violates([(0, 0), (5, 5)], None) is None
    assert mz.segment_violates((0, 0), (5, 5), None) is None
    assert mz.walk_why(None, ok, FIELD, ROOM) is None
    assert not mz.in_no_enter(None, ROOM)


def test_a_good_file_loads_with_its_sha256(tmp_path: Path) -> None:
    p = write(tmp_path, GOOD)
    z = mz.load("fix_map", tmp_path, shape=(H, W))
    assert z is not None
    assert (z.reviewed_by, z.reviewed, z.path) == ("batt", "2026-10-21", str(p))
    assert z.sha256 == hashlib.sha256(p.read_bytes()).hexdigest()
    assert z.no_cross[0].points == ((28, 35), (31, 35))
    assert z.no_cross[0].note == "across the entrance"
    assert len(z.no_enter[0].polygon) == 4  # the explicit closing point is dropped
    quoted = GOOD.replace("reviewed: 2026-10-21", 'reviewed: "2026-10-21"')
    assert mz.parse(yaml.safe_load(quoted), "fix_map").reviewed == "2026-10-21"


@pytest.mark.parametrize(
    ("change", "why"),
    [
        (lambda t: t.replace("reviewed_by: batt\n", ""), "no reviewed_by"),
        (lambda t: t.replace("reviewed_by: batt", "reviewed_by: ''"), "no reviewed_by"),
        (lambda t: t.replace("reviewed_by: batt", "reviewed_by: Claude"), "never approves"),
        (lambda t: t.replace("reviewed_by: batt", "reviewed_by: claude-agent"), "never approves"),
        (lambda t: t.replace("reviewed: 2026-10-21\n", ""), "reviewed"),
        (lambda t: t.replace("reviewed: 2026-10-21", "reviewed: yesterday"), "reviewed"),
        (lambda t: t.replace("reviewed: 2026-10-21", "reviewed: '2026-13-40'"), "not a date"),
        (lambda t: t.replace("map: fix_map", "map: prt_fild08"), "the file's name"),
        (lambda t: t + "no_enters: []\n", "unknown key"),
        (lambda t: t.replace("id: ne1", "id: nc1"), "duplicate id"),
        (lambda t: t.replace("[[28, 35], [31, 35]]", "[[28, 35]]"), "at least 2"),
        (
            lambda t: t.replace(
                "[[16, 36], [44, 36], [44, 54], [16, 54], [16, 36]]", "[[16, 36], [44, 36]]"
            ),
            "at least 3",
        ),
        (lambda t: t.replace("[31, 35]", "[31, 60]"), "off the map"),
        (lambda t: t.replace("[31, 35]", "[31.0, 35]"), "two integers"),
        (lambda t: t.replace("[31, 35]", "[true, 35]"), "two integers"),
        (
            lambda t: t.replace("[[28, 35], [31, 35]]", "[[28, 35], [28, 35], [31, 35]]"),
            "repeats the one before",
        ),
        (
            lambda t: t.replace(
                "[[16, 36], [44, 36], [44, 54], [16, 54], [16, 36]]",
                "[[16, 36], [20, 40], [24, 44]]",
            ),
            "no area",
        ),
        (
            lambda t: t.replace(
                "[[16, 36], [44, 36], [44, 54], [16, 54], [16, 36]]",
                "[[16, 36], [44, 50], [44, 36], [16, 54]]",
            ),
            "cross",
        ),
        (lambda t: t.replace("    note: the room itself\n", ""), "keys must be"),
        (lambda t: t.replace("note: the room itself", "note: ''"), "note"),
        (lambda t: t.replace("polygon:", "points:"), "keys must be"),
        (
            lambda t: (
                t.replace("no_cross:\n", "no_cross: 3\n").split("  - id: nc1")[0] + "no_enter: []\n"
            ),
            "a list",
        ),
        (lambda t: "map: [unclosed\n", "not readable YAML"),
    ],
)
def test_a_wrong_file_refuses_the_run(tmp_path: Path, change: Any, why: str) -> None:
    write(tmp_path, change(GOOD))
    with pytest.raises(mz.ZoneError, match=why):
        mz.load("fix_map", tmp_path, shape=(H, W))


def test_a_yml_beside_and_a_bad_map_name_refuse(tmp_path: Path) -> None:
    write(tmp_path, GOOD, "fix_map.yml")
    with pytest.raises(mz.ZoneError, match=r"\.yaml"):
        mz.load("fix_map", tmp_path)
    with pytest.raises(mz.ZoneError, match="file name"):
        mz.load("../etc/passwd", tmp_path)


DELEGATED = GOOD.replace(
    "reviewed_by: batt\n",
    'reviewed_by: "agent (delegated by batt, 2026-10-21)"\n'
    'delegation: "Batt 2026-10-21, decision 1: zone authoring delegated"\n',
)


def test_a_delegated_review_loads_only_in_its_exact_form(tmp_path: Path) -> None:
    """Batt 2026-10-21 (decision 1): "I DELEGATE the zone authoring to you ... reviewed_by:
    "agent (delegated by batt, 2026-10-21)", plus a note pointing to this decision; keep
    fail-closed loading" -- the agent's name passes ONLY in that form with a delegation note."""
    write(tmp_path, DELEGATED)
    z = mz.load("fix_map", tmp_path, shape=(H, W))
    assert z is not None and z.reviewed_by == "agent (delegated by batt, 2026-10-21)"
    assert z.delegation.startswith("Batt 2026-10-21")
    assert mz.summary(z, (H, W))["delegation"] == z.delegation
    for bad, why in (
        (DELEGATED.replace('delegation: "Batt 2026-10-21, decision 1: zone authoring delegated"\n',
                           ""), "needs a `delegation` note"),
        (DELEGATED.replace("delegated by batt", "delegated by claude"), "never approves"),
        (DELEGATED.replace("delegated by batt", "approved by batt"), "never approves"),
        (DELEGATED.replace("batt, 2026-10-21)", "batt)"), "never approves"),
        (DELEGATED.replace("batt, 2026-10-21)", "batt, 2026-13-40)"), "not a date"),
        (DELEGATED.replace('"agent (delegated', '"agent and claude (delegated'), "never approves"),
        (GOOD.replace("reviewed_by: batt\n", 'reviewed_by: batt\ndelegation: "x"\n'),
         "only a delegated reviewer"),
    ):  # fmt: skip
        write(tmp_path, bad)
        with pytest.raises(mz.ZoneError, match=why):
            mz.load("fix_map", tmp_path, shape=(H, W))


def test_the_repo_ships_prt_fild08_under_batts_recorded_delegation() -> None:
    """Batt authors the files -- or delegates one, recorded in it (2026-10-21: prt_fild08)."""
    assert mz.ZONES_DIR.name == "map_zones" and (mz.ZONES_DIR / "README.md").exists()
    assert not list(mz.ZONES_DIR.glob("*.yml"))
    assert sorted(p.name for p in mz.ZONES_DIR.glob("*.yaml")) == ["prt_fild08.yaml"]
    z = mz.load("prt_fild08")
    assert z is not None and z.reviewed_by == "agent (delegated by batt, 2026-10-21)"
    assert "decision 1" in z.delegation
    assert [(c.id, c.points) for c in z.no_cross] == [
        ("c1-door", ((322, 88), (318, 91))), ("c3-door", ((50, 36), (46, 36)))]  # fmt: skip
    assert z.no_enter == ()


def test_a_line_seals_the_room_and_cuts_off_nothing_else() -> None:
    """The fixture's room behind its entrance line is cut off whole (both connectivities); the
    field loses nothing; a second door makes nothing sealed; ``prove`` says the same."""
    ok = fixture_map()
    z = zones_of(no_cross=[ENTRY_LINE])
    after = mz.route_grid(ok, z)
    room = np.zeros_like(ok)
    room[36:55, 16:45] = True
    for corner in (False, True):
        cut = mz.sealed_off(ok, after, corner)
        assert cut[ROOM[1], ROOM[0]] and not cut[FIELD[1], FIELD[0]]
        assert (cut & ~room).sum() <= 6  # at most the door cells behind the line
    pr = mz.prove(z, ok, server=ok, area=ok, free=ok, samples=40)
    for k in ("no_corner_rule", "corner_rule"):
        assert pr[k]["newly_unreachable"] == 0
        assert [c["borders"] for c in pr[k]["cut"]] == [["nc0"]]
    assert pr["clicks"][0]["into_refused"] == "40/40"
    assert pr["spawn"]["in_cut"] == pr["no_corner_rule"]["cut_cells"]
    two = ok.copy()
    two[31:36, 40:42] = True  # a second door: the line seals nothing now
    assert not mz.sealed_off(two, mz.route_grid(two, z)).any()
    assert mz.sealed_off(ok, ok).sum() == 0  # no zones cut: nothing sealed


# --- coordinates and masks ------------------------------------------------------------------------


def test_y_is_north_and_grids_are_indexed_y_x() -> None:
    """The convention end to end: a GAT tile (x, y) is walkable()[y, x] (no flip), and a zone point
    (x, y) is mask[y, x]. A SYNTHETIC 3 x 2 GAT (no client data): tile x=2, y=1 is a wall."""
    from poring_dataset import gat as gatmod

    tiles = b"".join(struct.pack("<4fHH", 0, 0, 0, 0, 1 if (x, y) == (2, 1) else 0, 0)
                     for y in range(2) for x in range(3))  # fmt: skip
    g = gatmod.parse(struct.pack("<4sBBII", b"GRAT", 1, 2, 3, 2) + tiles)
    walk = g.walkable()
    assert walk.shape == (2, 3) and not walk[1, 2] and walk[0, 2] and walk[1, 0]
    z = zones_of(no_enter=[[[5, 40], [7, 40], [7, 42], [5, 42]]])
    m = mz.no_enter_mask(z, (H, W))
    assert m[40:43, 5:8].all() and int(m.sum()) == 9 and not m[5:8, 40:43].any()


def test_no_enter_takes_the_cells_whose_centre_is_inside_or_on_the_edge() -> None:
    z = zones_of(no_enter=[ROOM_POLY])
    m = mz.no_enter_mask(z, (H, W))
    assert int(m.sum()) == 29 * 19 and m[36:55, 16:45].all()  # the boundary cells count
    tri = [[10, 10], [20, 10], [10, 20]]
    mt = mz.no_enter_mask(zones_of(no_enter=[tri]), (H, W))
    assert mt[10, 20] and mt[20, 10] and mt[15, 15] and not mt[16, 15]  # (15, 15) on the edge
    rng = random.Random(7)
    for _ in range(60):  # the vectorised mask = the scalar test, every cell
        poly = [(rng.randint(0, 25), rng.randint(0, 25)) for _ in range(rng.randint(3, 6))]
        pm = mz._poly_mask(poly, (30, 30))
        assert all(bool(pm[y, x]) == mz.in_polygon((x, y), poly)
                   for y in range(30) for x in range(30))  # fmt: skip


def test_supercover_closed_takes_corner_cells_open_does_not() -> None:
    assert sorted(mz.supercover((0, 0), (3, 0))) == [(0, 0), (1, 0), (2, 0), (3, 0)]
    diag = set(mz.supercover((0, 0), (2, 2)))
    assert diag == {(0, 0), (1, 1), (2, 2), (1, 0), (0, 1), (2, 1), (1, 2)}
    assert set(mz.supercover((0, 0), (2, 2), closed=False)) == {(0, 0), (1, 1), (2, 2)}
    shallow = set(mz.supercover((0, 0), (4, 1), closed=False))
    assert shallow == {(0, 0), (1, 0), (2, 0), (2, 1), (3, 1), (4, 1)}


def test_no_cross_raster_admits_no_diagonal_leak() -> None:
    """The CLOSED supercover: no 8-connected step between two cells off the raster meets the line
    (hunt_core.astar's diagonal rule or not -- zone_path / unstall_cells' BFS have none); every
    adjacent pair checked on random polylines."""
    rng = random.Random(20261020)
    for _ in range(150):
        pts = [(rng.randint(1, 18), rng.randint(1, 18)) for _ in range(rng.randint(2, 4))]
        pts = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
        if len(pts) < 2:
            continue
        z = zones_of(no_cross=[pts])
        nc = mz.no_cross_mask(z, (20, 20))
        segs = z.no_cross[0].segments()
        for y in range(20):
            for x in range(20):
                if nc[y, x]:
                    continue
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        q = (x + dx, y + dy)
                        if (dx or dy) and 0 <= q[0] < 20 and 0 <= q[1] < 20 and not nc[q[1], q[0]]:
                            assert not any(mz.segments_meet((x, y), q, s, t) for s, t in segs)
    # a 45-degree wall across the whole grid: neither A* nor a rule-free 8-connected BFS gets over
    z = zones_of(no_cross=[[[0, 0], [29, 29]]])
    open_ = np.ones((30, 30), dtype=bool) & ~mz.no_cross_mask(z, (30, 30))
    assert hc.astar(open_, (20, 5), (5, 20)) is None
    seen, q = {(20, 5)}, deque([(20, 5)])
    while q:
        c = q.popleft()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (c[0] + dx, c[1] + dy)
                if 0 <= n[0] < 30 and 0 <= n[1] < 30 and open_[n[1], n[0]] and n not in seen:
                    seen.add(n)
                    q.append(n)
    assert (5, 20) not in seen and all(x > y for x, y in seen)


def test_apply_cuts_the_area_and_the_stand_grid() -> None:
    ok = fixture_map()
    area = ok.copy()
    z = zones_of(no_cross=[ENTRY_LINE], no_enter=[ROOM_POLY])
    ok_z, area_z = mz.apply(ok, area, z)
    assert not ok_z[35, 29] and not ok_z[35, 30] and ok_z[45, 30]  # the room stays standable
    assert not area_z[45, 30] and not area_z[35, 29] and area_z[20, 30] and area_z[33, 30]
    assert ok.sum() == fixture_map().sum() and area.sum() == ok.sum()  # inputs untouched
    rg = mz.route_grid(ok, z)
    assert not rg[45, 30] and not rg[35, 30] and rg[20, 30]
    s = mz.summary(dataclass_with_file(z), (H, W), ok, area)
    assert s["no_cross"] == ["nc0"] and s["no_enter"] == ["ne0"] and s["no_enter_cells"] == 551
    assert s["no_cross_cells"] == 4 and s["ok_removed"] == 2  # the line's 2 walkable cells
    assert s["area_removed"] == 551 + 2


def dataclass_with_file(z: mz.Zones) -> mz.Zones:
    import dataclasses

    return dataclasses.replace(z, path="x.yaml", sha256="0" * 64)


# --- routes, clicks, the way out ------------------------------------------------------------------


def octile(path: Any) -> float:
    return sum(
        hc.STEP_MS[a[0] != b[0] and a[1] != b[1]] for a, b in zip(path, path[1:], strict=False)
    )


def test_a_route_is_planned_around_a_line_and_none_when_it_seals_the_room() -> None:
    ok = fixture_map()
    wall = zones_of(no_cross=[[[20, 5], [20, 25]]])  # a wall in the open field, open at both ends
    ok_z, _ = mz.apply(ok, ok.copy(), wall)
    straight = hc.astar(ok, (15, 15), (25, 15))
    assert straight is not None and mz.path_violates(straight, wall) == "no_cross"
    around = hc.astar(ok_z, (15, 15), (25, 15))
    assert around is not None and mz.path_violates(around, wall) is None
    assert any(y < 5 or y > 25 for _x, y in around) and len(around) > len(straight)
    sealed = zones_of(no_cross=[ENTRY_LINE])
    ok_s, area_s = mz.apply(ok, ok.copy(), sealed)
    assert hc.astar(ok, FIELD, ROOM) is not None  # without the zones: through the entrance
    assert hc.astar(ok_s, FIELD, ROOM) is None and hc.astar(area_s, FIELD, ROOM) is None


def test_a_click_across_a_line_is_refused() -> None:
    ok = fixture_map()
    line = zones_of(no_cross=[ENTRY_LINE])
    assert mz.walk_why(line, ok, (30, 30), (30, 37)) == "straight_no_cross"
    # the straight line misses the line (it runs into the wall band); the CLIENT's own path goes
    # through the entrance and crosses it
    assert mz.segment_violates((20, 30), (20, 40), line) is None
    assert mz.walk_why(line, ok, (20, 30), (20, 40)) == "route_no_cross"
    assert mz.walk_why(line, None, (20, 30), (20, 40)) is None  # no proxy grid: straight only
    assert mz.walk_why(line, ok, (25, 25), (35, 20)) is None  # a click in the field
    room = zones_of(no_enter=[ROOM_POLY])
    assert mz.walk_why(room, ok, (30, 30), (30, 40)) == "dest_no_enter"
    assert mz.walk_why(room, ok, (30, 40), (30, 45)) == "dest_no_enter"  # targets / loot: strict
    assert mz.walk_why(room, ok, (30, 40), (30, 45), exit_ok=True) is None  # inside: the way out
    assert mz.walk_why(room, ok, (30, 40), (30, 30), exit_ok=True) is None
    corner = zones_of(no_enter=[[[10, 10], [12, 10], [12, 12], [10, 12]]])
    assert mz.walk_why(corner, np.ones((H, W), bool), (8, 14), (14, 8)) == "straight_no_enter"


def test_path_rules_touch_start_and_runs() -> None:
    z = zones_of(no_cross=[[[10, 0], [10, 20]]], no_enter=[[[30, 30], [40, 30], [40, 40]]])
    assert mz.path_violates([(9, 5), (10, 5)], z) == "no_cross"  # stepping ONTO the line
    assert mz.path_violates([(10, 5), (11, 5), (12, 5)], z) is None  # stepping OFF it
    assert mz.path_violates([(10, 5), (10, 6)], z) == "no_cross"  # a run along it
    assert mz.path_violates([(10, 20), (10, 21)], z) is None  # off its end, along its direction
    assert mz.path_violates([(9, 5), (11, 5)], z) == "no_cross"
    assert mz.path_violates([(28, 30), (29, 30), (30, 30)], z) == "no_enter"  # its corner cell
    assert mz.path_violates([(35, 32), (36, 31), (37, 29)], z) is None  # from inside, out
    two = zones_of(no_enter=[[[0, 0], [5, 0], [5, 5], [0, 5]], [[7, 0], [9, 0], [9, 5], [7, 5]]])
    assert mz.path_violates([(4, 2), (5, 2), (6, 2), (7, 2)], two) == "no_enter"  # another area


def test_the_way_out_is_the_shortest_and_never_crosses_a_line() -> None:
    ok = fixture_map()
    room = zones_of(no_enter=[ROOM_POLY])
    ok_z, area_z = mz.apply(ok, ok.copy(), room)
    here = (30, 50)
    out = mz.exit_path(ok_z, area_z, here, room)
    assert out is not None and out[0] == here and area_z[out[-1][1], out[-1][0]]
    assert out[-1] in ((29, 35), (30, 35))  # the corridor's first cell outside the room
    assert not any(area_z[y, x] for x, y in out[:-1])  # it stops at the first area cell
    assert mz.path_violates(out, room) is None  # from inside: leaving is no entry
    cands = [(x, y) for y in range(28, 36) for x in range(2, 58) if area_z[y, x]]
    best = min(octile(p) for c in cands if (p := hc.astar(ok, here, c)) is not None)
    assert math.isclose(octile(out), best)
    both = zones_of(no_cross=[ENTRY_LINE], no_enter=[ROOM_POLY])
    ok_b, area_b = mz.apply(ok, ok.copy(), both)
    assert mz.exit_path(ok_b, area_b, here, both) is None  # the line seals the only way out
    assert mz.exit_path(ok_z, area_z, FIELD, room) == [FIELD]  # in the area already


def test_the_way_out_enters_no_other_area() -> None:
    """Area B touches A's south side, across A's shortest way out: the path goes round."""
    ok = np.ones((40, 40), dtype=bool)
    a_sq = [[10, 10], [20, 10], [20, 20], [10, 20]]
    b_bar = [[8, 6], [22, 6], [22, 9], [8, 9]]
    one = zones_of(no_enter=[a_sq])
    two = zones_of(no_enter=[a_sq, b_bar])
    here = (15, 11)
    short = mz.exit_path(*mz.apply(ok, ok.copy(), one), here, one)
    assert short is not None and short[-1] == (15, 9) and len(short) == 3
    ok2, area2 = mz.apply(ok, ok.copy(), two)
    out = mz.exit_path(ok2, area2, here, two)
    assert out is not None and mz.path_violates(out, two) is None
    assert not any(mz.in_polygon(c, [tuple(p) for p in b_bar]) for c in out)
    free_b = ok & ~mz.no_enter_mask(zones_of(no_enter=[b_bar]), (40, 40))
    best = min(octile(p) for c in zip(*np.nonzero(area2.T), strict=True)
               if max(abs(int(c[0]) - 15), abs(int(c[1]) - 15)) <= 8
               and (p := hc.astar(free_b, here, (int(c[0]), int(c[1])))) is not None)  # fmt: skip
    assert math.isclose(octile(out), best)


def test_a_target_in_a_zone_and_its_walk_in() -> None:
    """The runner's target rule, as its pure parts: a cell in a no-enter area is never engaged;
    in strike range, nor one whose walk-in (the client's path from the GM) breaks a zone."""
    ok = fixture_map()
    room = zones_of(no_enter=[ROOM_POLY])
    assert mz.in_no_enter(room, ROOM) and not mz.in_no_enter(room, FIELD)
    line = zones_of(no_cross=[ENTRY_LINE])
    assert mz.walk_why(line, ok, (29, 32), (30, 37)) == "straight_no_cross"  # just past the line
    assert mz.walk_why(line, ok, (29, 28), (31, 26)) is None


# --- the runner (hunt_flow.py): the call sites ------------------------------------------------


def _src() -> str:
    return (Path(mz.__file__).resolve().parent / "hunt_flow.py").read_text()


def _body(src: str, start: str, end: str) -> str:
    return src.split(start, 1)[1].split(end, 1)[0]


def test_the_runner_is_inert_without_a_zones_file() -> None:
    src = _src()
    body = _body(src, "def zone_why(", "def walk_click(")
    first = body.split('"""')[2].split()[:4]
    assert first == ["if", "zones", "is", "None:"] and body.split('"""')[2].split()[4:6] == [
        "return", "None"]  # fmt: skip
    assert "okr: Any = ok\n" in src and "z_seen: Any = None" in src
    setup = _body(src, "zones = mz.load(MAP, shape=ok.shape)", 'if MAP == "prt_fild08":')
    i_if = setup.index("if zones is not None:")
    for mut in ("mz.apply(", "okr = mz.route_grid(ok, zones)", "ok0 = mz.route_grid(ok0, zones)",
                "z_seen = ", "z_free = "):  # fmt: skip
        assert setup.index(mut) > i_if, mut  # only with zones
    assert "area_s = area if zones is None else main_component(area)" in setup
    # Batt 2026-10-21: a sealed room leaves the area and the routes (only with zones)
    for mut in ("z_cut = mz.sealed_off(ok, okr)", "area = area & ~z_cut", "okr = okr & ~z_cut",
                "ok0 = mz.route_grid(ok0, zones) & ~z_cut"):  # fmt: skip
        assert setup.index(mut) > i_if, mut
    assert setup.index("z_cut = mz.sealed_off(ok, okr)") < setup.index("z_seen = area0_ & ~area")
    assert "if zones is not None:  # map traps: the file this run enforces" in src
    assert '**({"map_zones": dict(zone_n)} if zones is not None else {}),' in src
    assert 'plan["escape"] = "zone_exit" if z_exit_ else False' in src
    assert "if okr is not ok:" in src
    assert "map zones are enforced by the pipelined" in src  # v1's loop never runs with zones


def test_every_walk_click_passes_the_zone_gate_first() -> None:
    body = _body(_src(), "def walk_click(", "in_range_since: dict")
    i_z = body.index(
        "zw_ = zone_why(seg[0], to, exit_ok=True) or zone_why(pos_box[0], to, exit_ok=True)"
    )
    assert i_z < body.index("cursor_gate.gated_click(") and i_z < body.index("agent.click(")
    assert '"why": "zone"' in body[i_z : i_z + 400] and "return False" in body[i_z : i_z + 400]


def test_targets_and_the_attack_click_check_the_zones() -> None:
    src = _src()
    strike = _body(src, "def strike(tr: Track, here: Cell, again: bool) -> bool:", "done_ids: set")
    i_z = strike.index("zs_ = zone_why(here, tr.predict(r.ns()))")
    assert i_z < strike.index("agent.click(") and i_z < strike.index('split.to("striking"')
    burst = _body(src, "def run_burst(", "def species_now(")  # the burst's re-clicks too
    assert burst.index("zone_why(here, tr.predict(r.ns()))") < burst.index("agent.click(")
    loop = _body(src, "in_rng = cheb(pos, tcell) <= s_range or in_zone", "if in_rng:")
    assert '"target_no_enter" if mz.in_no_enter(zones, tc_z)' in loop
    assert '"target_sealed" if (0 <= tc_z[0] < wz_' in loop and "z_cut[tc_z[1], tc_z[0]]" in loop
    assert "zone_why(pos, tcell) if in_rng else None" in loop and "banned.append" in loop
    for route in ("zone_path(okr, pos, tcell, rz_)", 'approach_path(okr, pos, tcell, prm["short"])',
                  'cont_click(ap, okr, "steer", tcell,', "hc.astar(okr, here_, c_)",
                  "hc.astar(okr, here_, pc_)"):  # fmt: skip
        assert route in src, route
    assert src.count('approach_path(okr, pos, tcell, prm["short"])') == 2
    assert src.count('approach_path(ok, pos, tcell, prm["short"])') == 1  # v1's (refused)


def test_every_loot_click_path_skips_zone_cells() -> None:
    src = _src()
    for start, end, check, before in (
        ("def loot_gm_steps(", "def loot_fixed_run(", "zone_why(ref, c_g)",
         "sn_g, px_g = hover(c_g, ref, passes, 0)"),
        ("def loot_hand_steps(", "def gm_ref(", "zone_why(mp_h, c_h)", "csw_h.check("),
        ("def loot_fixed_run(", "def loot_blobs_run(", "zone_why(mp_, c_l)", "agent.click("),
        ("def loot_blobs_run(", "def loot_sweep(", "zone_why(mp_, c_b)", "agent.click("),
        ("def loot_sweep(", "def gate_risks(", "zone_why(here2, cell)", "agent.click("),
    ):  # fmt: skip
        body = _body(src, start, end)
        assert body.index(check) < body.index(before), start
    after = _body(src, "def loot_after(", "def hand_still(")
    assert after.index("zone_why(here2, (dead_.cell[0] + dx_") < after.index("loot1.loot(")


def test_the_way_back_uses_the_exit_path_only_with_zones() -> None:
    plan = _body(_src(), "def planner() -> None:", "def quick_fix() -> Cell:")
    i_z = plan.index("elif zones is not None:")
    i_exit = plan.index("pz_ = mz.exit_path(ok, area, here_, zones)")
    i_back = plan.index("back = hc.nearest_in(area, ok, here_)")
    assert i_z < i_exit < i_back  # the old nearest-cell way back stays for no zones
