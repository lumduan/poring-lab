"""map_routes: Batt's per-map PATROL ROUTES (2026-10-22, the Crusader's demo in orcsdun01: a fixed
circuit walked in ONE direction) -- the loader (fail closed, INERT without a file, map_zones' own
review rules), the proof on the map (waypoints outside the zones, every leg connected, its length)
and the pure walking helpers (reached, next, resume AHEAD, join). The fixture is a SYNTHETIC map: a
ring corridor around a central block, like orcsdun01's loop, with a side room behind a door."""

from __future__ import annotations

import hashlib
import json
import struct
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import map_routes as mr  # noqa: E402
import map_zones as mz  # noqa: E402

H, W = 60, 60
RING = [[10, 10], [49, 10], [49, 49], [10, 49]]  # anticlockwise: east, north, west, south


def ring_map() -> Any:
    """60 x 60 cells, [y, x], y north: the walkable square x, y 5..54 minus the BLOCK (x, y
    20..39) -- a ring corridor 15 cells wide -- plus a SIDE ROOM (x 56..58, y 25..34) joined to the
    ring's east side by a 1-cell door at y 30 (x 55)."""
    ok = np.zeros((H, W), dtype=bool)
    ok[5:55, 5:55] = True
    ok[20:40, 20:40] = False
    ok[25:35, 56:59] = True
    ok[30, 55] = True
    return ok


def zones_of(no_cross: Any = (), no_enter: Any = ()) -> mz.Zones:
    return mz.Zones(
        map="fix_map", reviewed_by="batt", reviewed="2026-10-22",
        no_cross=tuple(mz.NoCross(f"nc{i}", "n", tuple(map(tuple, p)))
                       for i, p in enumerate(no_cross)),
        no_enter=tuple(mz.NoEnter(f"ne{i}", "n", tuple(map(tuple, p)))
                       for i, p in enumerate(no_enter)),
    )  # fmt: skip


def route(wps: Any, kind: str = "loop", rid: str = "ring") -> mr.Route:
    return mr.Route(rid, kind, "n", tuple(tuple(c) for c in wps))


def routes_of(*rs: mr.Route) -> mr.Routes:
    return mr.Routes(map="fix_map", reviewed_by="batt", reviewed="2026-10-22", source="synthetic",
                     routes=rs)  # fmt: skip


GOOD = """\
map: fix_map
reviewed_by: batt
reviewed: 2026-10-22
source: synthetic, drawn for the test
routes:
  - id: ring
    kind: loop
    note: round the block, anticlockwise
    waypoints: [[10, 10], [49, 10], [49, 49], [10, 49]]
  - id: east-path
    kind: path
    note: the east side only
    waypoints: [[49, 10], [49, 49]]
"""


def write(tmp: Path, text: str, name: str = "fix_map.yaml") -> Path:
    p = tmp / name
    p.write_text(text)
    return p


# --- the loader -----------------------------------------------------------------------------------


def test_no_file_is_none(tmp_path: Path) -> None:
    assert mr.load("fix_map", tmp_path) is None
    assert mr.load("fix_map", tmp_path / "missing-dir") is None


def test_a_good_file_loads_with_its_sha256(tmp_path: Path) -> None:
    p = write(tmp_path, GOOD)
    r = mr.load("fix_map", tmp_path, shape=(H, W))
    assert r is not None
    assert (r.reviewed_by, r.reviewed, r.path, r.delegation) == ("batt", "2026-10-22", str(p), "")
    assert r.sha256 == hashlib.sha256(p.read_bytes()).hexdigest()
    assert r.source == "synthetic, drawn for the test"
    ring, east = r.routes
    assert (ring.id, ring.kind, ring.loop) == ("ring", "loop", True)
    assert ring.note == "round the block, anticlockwise"
    assert ring.waypoints == ((10, 10), (49, 10), (49, 49), (10, 49))  # the listed order
    assert ring.legs() == [(0, 1), (1, 2), (2, 3), (3, 0)]  # the closing leg last
    assert (east.kind, east.loop, east.legs()) == ("path", False, [(0, 1)])
    s = mr.summary(r)
    assert s["routes"] == [
        {"id": "ring", "kind": "loop", "waypoints": 4, "legs": 4},
        {"id": "east-path", "kind": "path", "waypoints": 2, "legs": 1},
    ]
    assert "delegation" not in s and s["sha256"] == r.sha256
    closed = GOOD.replace("[10, 49]]\n  - id", "[10, 49], [10, 10]]\n  - id")
    write(tmp_path, closed)
    again = mr.load("fix_map", tmp_path)
    assert again is not None and again.routes[0].waypoints == ring.waypoints  # closing one dropped
    quoted = GOOD.replace("reviewed: 2026-10-22", 'reviewed: "2026-10-22"')
    assert mr.parse(yaml.safe_load(quoted), "fix_map").reviewed == "2026-10-22"


LOOP = "waypoints: [[10, 10], [49, 10], [49, 49], [10, 49]]"


@pytest.mark.parametrize(
    ("change", "why"),
    [
        (lambda t: t + "speed: 3\n", "unknown key"),
        (lambda t: t.replace("map: fix_map", "map: orcsdun01"), "the file's name"),
        (lambda t: t.replace("reviewed_by: batt\n", ""), "no reviewed_by: a routes file"),
        (lambda t: t.replace("reviewed_by: batt", "reviewed_by: Claude"), "never approves routes"),
        (lambda t: t.replace("reviewed: 2026-10-22\n", ""), "reviewed"),
        (lambda t: t.replace("reviewed: 2026-10-22", "reviewed: '2026-13-40'"), "not a date"),
        (lambda t: t.replace("source: synthetic, drawn for the test\n", ""), "source"),
        (lambda t: t.replace("source: synthetic, drawn for the test", "source: ''"), "source"),
        (lambda t: t.split("routes:")[0] + "routes: []\n", "at least one route"),
        (lambda t: t.split("routes:")[0] + "routes: ring\n", "at least one route"),
        (lambda t: t.split("routes:")[0] + "routes: [3]\n", "a mapping"),
        (lambda t: t.replace("    note: the east side only\n", ""), "keys must be"),
        (lambda t: t.replace("    kind: path\n", "    kind: path\n    speed: 2\n"), "keys must be"),
        (lambda t: t.replace("id: ring", "id: Ring"), "is not 1-40 of"),
        (lambda t: t.replace("id: ring", "id: the ring"), "is not 1-40 of"),
        (lambda t: t.replace("id: ring", "id: 3"), "is not 1-40 of"),
        (lambda t: t.replace("id: east-path", "id: ring"), "duplicate id"),
        (lambda t: t.replace("kind: loop", "kind: circle"), "loop or path"),
        (lambda t: t.replace(LOOP, "waypoints: [[10, 10], [49, 10]]"), "a loop needs at least 3"),
        (lambda t: t.replace("[[49, 10], [49, 49]]", "[[49, 10]]"), "a path needs at least 2"),
        (lambda t: t.replace(LOOP, "waypoints: 3"), "a list of"),
        (lambda t: t.replace("[49, 49], [10, 49]]", "[49, 49.0], [10, 49]]"), "two integers"),
        (lambda t: t.replace("[49, 49], [10, 49]]", "[49, true], [10, 49]]"), "two integers"),
        (lambda t: t.replace("[49, 49], [10, 49]]", "[49, 60], [10, 49]]"), "off the map"),
        (lambda t: t.replace("[49, 49], [10, 49]]", "[49, 49], [49, 49]]"), "repeats the one"),
        (lambda t: t.replace(LOOP, "waypoints: [[10, 10], [49, 10], [10, 10]]"), "is its first"),
        (lambda t: t.replace("[[49, 10], [49, 49]]", "[[49, 10], [49, 49], [49, 10]]"),
         "is its first"),
        (lambda t: t.replace(LOOP, "waypoints: [[10, 10], [30, 10], [49, 10], [20, 10]]"),
         "back and forth"),
        (lambda t: t.replace("note: the east side only", "note: ''"), "note"),
        (lambda t: "map: [unclosed\n", "not readable YAML"),
        (lambda t: "- just a list\n", "not a mapping"),
    ],
)  # fmt: skip
def test_a_wrong_file_refuses_the_run(tmp_path: Path, change: Any, why: str) -> None:
    write(tmp_path, change(GOOD))
    with pytest.raises(mr.RouteError, match=why):
        mr.load("fix_map", tmp_path, shape=(H, W))


def test_a_yml_beside_and_a_bad_map_name_refuse(tmp_path: Path) -> None:
    write(tmp_path, GOOD, "fix_map.yml")
    with pytest.raises(mr.RouteError, match=r"\.yaml"):
        mr.load("fix_map", tmp_path)
    with pytest.raises(mr.RouteError, match="file name"):
        mr.load("../etc/passwd", tmp_path)


DELEGATED = GOOD.replace(
    "reviewed_by: batt\n",
    'reviewed_by: "agent (delegated by batt, 2026-10-22)"\n'
    'delegation: "Batt 2026-10-22 overnight brief, item A: patrol routes delegated"\n',
)


def test_the_review_is_the_zone_files_own_delegated_rules(tmp_path: Path) -> None:
    """The same rules through the same code (map_zones.review, Batt 2026-10-21 decision 1): the
    agent's name passes ONLY as 'agent (delegated by <person>, YYYY-MM-DD)' with a delegation
    note; every other agent-like reviewer is refused, and the messages are map_zones' own with
    'routes' for 'zones'."""
    write(tmp_path, DELEGATED)
    r = mr.load("fix_map", tmp_path, shape=(H, W))
    assert r is not None and r.reviewed_by == "agent (delegated by batt, 2026-10-22)"
    assert r.delegation.startswith("Batt 2026-10-22") and mr.summary(r)["delegation"]
    note = 'delegation: "Batt 2026-10-22 overnight brief, item A: patrol routes delegated"\n'
    for bad, why in (
        (DELEGATED.replace(note, ""), "needs a `delegation` note"),
        (DELEGATED.replace("delegated by batt", "delegated by claude"), "never approves routes"),
        (DELEGATED.replace("delegated by batt", "approved by batt"), "never approves routes"),
        (DELEGATED.replace("batt, 2026-10-22)", "batt)"), "never approves routes"),
        (DELEGATED.replace("batt, 2026-10-22)", "batt, 2026-13-40)"), "not a date"),
        (GOOD.replace("reviewed_by: batt\n", 'reviewed_by: batt\ndelegation: "x"\n'),
         "only a delegated reviewer"),
    ):  # fmt: skip
        write(tmp_path, bad)
        with pytest.raises(mr.RouteError) as got:
            mr.load("fix_map", tmp_path, shape=(H, W))
        assert why in str(got.value)
        data = yaml.safe_load(bad)
        with pytest.raises(mz.ZoneError) as zone:  # map_zones' own verdict on the same review
            mz.review(data, str(tmp_path / "fix_map.yaml"))
        mine, theirs = str(got.value).split(": ", 1)[1], str(zone.value).split(": ", 1)[1]
        assert mine == theirs.replace("zones", "routes")


def test_every_committed_routes_file_loads() -> None:
    """The repo's routes files (written under a person's review or recorded delegation) load;
    none is a .yml; the README is there."""
    assert mr.ROUTES_DIR.name == "routes" and (mr.ROUTES_DIR / "README.md").exists()
    assert not list(mr.ROUTES_DIR.glob("*.yml"))
    for p in sorted(mr.ROUTES_DIR.glob("*.yaml")):
        r = mr.load(p.stem)
        assert r is not None and r.routes, p.name


# --- the proof on the map -------------------------------------------------------------------------


def test_the_ring_proves_with_each_legs_length() -> None:
    ok = ring_map()
    rep = mr.prove(routes_of(route(RING)), ok, None)
    assert rep["ok"] and rep["problems"] == []
    (r,) = rep["routes"]
    assert [(leg["from"], leg["to"], leg["steps"], leg["cost"]) for leg in r["legs"]] == [
        (0, 1, 39, 39.0), (1, 2, 39, 39.0), (2, 3, 39, 39.0), (3, 0, 39, 39.0)]  # fmt: skip
    assert (r["total_steps"], r["total_cost"]) == (156, 156.0)
    diag = mr.prove(routes_of(route([[10, 10], [15, 15], [10, 18]])), ok, None)["routes"][0]
    assert [leg["steps"] for leg in diag["legs"]] == [5, 5, 8]
    assert [leg["cost"] for leg in diag["legs"]] == [7.0, 6.2, 8.0]  # a diagonal step = 1.4


def test_a_waypoint_on_a_wall_or_in_a_zone_is_refused() -> None:
    ok = ring_map()
    door = [[55, 28], [55, 32]]  # a no-cross line on the side room's door
    warp = [[44, 44], [52, 44], [52, 52], [44, 52]]  # a no-enter area at the NE corner
    z = zones_of(no_cross=[door], no_enter=[warp])
    for wp, why in (
        ([30, 30], "not walkable"),  # inside the block
        ([48, 48], "inside no-enter area 'ne0'"),
        ([55, 30], "on no-cross line 'nc0'"),
        ([57, 30], "sealed off by the zones"),  # the side room behind the door line
        ([70, 30], "off the map (60 x 60 cells)"),
    ):  # fmt: skip
        rep = mr.prove(routes_of(route([[10, 10], [49, 10], wp])), ok, z)
        assert not rep["ok"]
        assert any(f"waypoint 2 {wp}: {why}" in p for p in rep["problems"]), rep["problems"]
    assert mr.closed_why((10, 10), ok, z) is None and mr.closed_why((10, 10), ok, None) is None


def test_every_leg_must_be_connected_on_the_route_grid() -> None:
    """A leg is walked on the walkable cells minus the zones: a waypoint on an island, or a ring
    cut twice by no-cross lines, leaves legs unconnected; the closing leg of a loop counts."""
    ok = ring_map()
    ok[1:3, 1:3] = True  # an island off the ring
    rep = mr.prove(routes_of(route([[10, 10], [49, 10], [49, 49], [2, 2]])), ok, None)
    assert [p.split(":")[0] for p in rep["problems"]] == [
        "route 'ring' leg 2 -> 3 ([49, 49] -> [2, 2])",
        "route 'ring' leg 3 -> 0 ([2, 2] -> [10, 10])",  # the closing leg
    ]
    assert rep["routes"][0]["total_steps"] is None and rep["routes"][0]["legs"][0]["steps"] == 39
    # one wall across the corridor: the ring is still one piece, the leg goes round the other way
    west = [[4, 30], [20, 30]]
    one = mr.prove(routes_of(route(RING)), ring_map(), zones_of(no_cross=[west]))
    assert one["ok"] and one["routes"][0]["legs"][3]["steps"] > 39
    # two walls: the west side is cut off from the rest; its waypoint is sealed, its legs cut
    east = [[39, 30], [55, 30]]
    two = mr.prove(routes_of(route([[10, 10], [49, 10], [49, 49], [10, 49], [10, 45]])),
                   ring_map(), zones_of(no_cross=[west, east]))  # fmt: skip
    assert not two["ok"] and any("not connected" in p for p in two["problems"])


def test_the_route_grid_is_the_runners() -> None:
    """map_zones.route_grid minus what the zones seal off (dungeon_hunt.py's okr): the side room
    behind its door line is not on it; without zones it is the walkable grid."""
    ok = ring_map()
    rg = mr.route_grid(ok, zones_of(no_cross=[[[55, 28], [55, 32]]]))
    assert not rg[30, 57] and not rg[30, 55] and rg[10, 10]
    assert (mr.route_grid(ok, None) == ok).all() and mr.route_grid(ok, None) is not ok


# --- walking --------------------------------------------------------------------------------------


SQ = route(RING)


def test_reached_next_and_prev() -> None:
    assert mr.reached((12, 8), (10, 10)) and not mr.reached((13, 10), (10, 10))
    assert mr.reached((13, 10), (10, 10), tol=3)
    assert [mr.next_index(SQ, i) for i in range(4)] == [1, 2, 3, 0]  # cyclic
    assert [mr.prev_index(SQ, i) for i in range(4)] == [3, 0, 1, 2]
    p = route([[0, 0], [10, 0], [20, 0]], "path")
    assert [mr.next_index(p, i) for i in range(3)] == [1, 2, None]  # None past a path's end
    assert [mr.prev_index(p, i) for i in range(3)] == [None, 0, 1]
    with pytest.raises(IndexError):
        mr.next_index(SQ, 4)


def test_segments_are_sampled_one_cell_per_step() -> None:
    assert mr.seg_cells((0, 0), (5, 2)) == [(0, 0), (1, 0), (2, 1), (3, 1), (4, 2), (5, 2)]
    assert mr.seg_cells((5, 2), (0, 0)) == mr.seg_cells((0, 0), (5, 2))[::-1]  # symmetric
    assert mr.seg_cells((3, 3), (3, 3)) == [(3, 3)]
    for a, b in (((0, 0), (7, -3)), ((-4, 9), (6, 1)), ((2, 2), (2, 11))):
        cells = mr.seg_cells(a, b)
        assert cells[0] == a and cells[-1] == b and len(cells) == mr.cheb(a, b) + 1
        assert all(mr.cheb(c, d) == 1 for c, d in zip(cells, cells[1:], strict=False))
    assert mr.seg_dist((20, 13), (10, 10), (49, 10)) == 3
    assert mr.seg_dist((5, 10), (10, 10), (49, 10)) == 5  # behind the segment: its end


def test_resume_takes_the_next_waypoint_ahead() -> None:
    """k = the last waypoint reached or passed; the answer is k+1 unless k+1 counts as passed."""
    # on the leg k -> k+1, short of k+1: k+1
    assert mr.resume_index(SQ, (20, 11), 0) == 1
    assert mr.resume_index(SQ, (40, 16), 0) == 1  # nearer the leg 0 -> 1 (6) than 1 -> 2 (9)
    # past the corner, along the leg k+1 -> k+2: k+1 counts as passed, the answer is k+2
    assert mr.resume_index(SQ, (47, 14), 0) == 2  # 2 from the leg 1 -> 2, 4 from the leg 0 -> 1
    assert mr.resume_index(SQ, (31, 11), 0, tol=0) == 1  # tol 0: not reached, nearer leg 0 -> 1
    # within tol of k+1: passed
    assert mr.resume_index(SQ, (51, 11), 0) == 2
    assert mr.resume_index(SQ, (47, 8), 0) == 2
    # a tie keeps k+1 (strictly closer only)
    assert mr.resume_index(SQ, (44, 15), 0) == 1  # 5 from both legs


def test_resume_wraps_on_a_loop_and_ends_on_a_path() -> None:
    assert mr.resume_index(SQ, (10, 30), 3) == 0  # on the closing leg: the first waypoint
    assert mr.resume_index(SQ, (15, 11), 3) == 1  # past the first: the second
    assert mr.resume_index(SQ, (11, 51), 2) == 0  # within tol of 3: passed, wrap to 0
    p = route([[0, 0], [10, 0], [20, 0]], "path")
    assert mr.resume_index(p, (15, 3), 1) == 2
    assert mr.resume_index(p, (19, 1), 1) is None  # the end reached: nothing left
    assert mr.resume_index(p, (5, 0), 2) is None  # past the end: nothing left (never back)
    assert mr.resume_index(p, (14, 2), 0) == 2  # 4 from 1 (not reached), nearer the leg 1 -> 2


def test_resume_never_turns_back() -> None:
    """Exhaustive on the ring: from ANY cell, after any k, the answer is k+1 or k+2 (cyclic) --
    never k or a waypoint behind it, even when the walker stands behind k (a fight pulled it
    back)."""
    for k in range(4):
        ahead = {(k + 1) % 4, (k + 2) % 4}
        for y in range(0, 60, 3):
            for x in range(0, 60, 3):
                assert mr.resume_index(SQ, (x, y), k) in ahead, (x, y, k)
    assert mr.resume_index(SQ, (20, 10), 1) == 2  # behind k = 1 on the leg 0 -> 1: still 2


def test_entry_joins_at_the_nearest_waypoint_or_the_one_past_it() -> None:
    assert mr.entry_index(SQ, (21, 9)) == 1  # nearest 0, past it on the leg 0 -> 1: 1
    assert mr.entry_index(SQ, (51, 16)) == 2  # nearest 1, past it on the leg 1 -> 2: 2
    assert mr.entry_index(SQ, (10, 10)) == 1  # standing on 0: reached, the next
    assert mr.entry_index(SQ, (29, 29)) == 0  # the middle: nearest 0, as far from both its legs
    assert mr.entry_index(SQ, (8, 40)) == 0  # nearest 3, past it on the closing leg 3 -> 0: 0
    assert mr.entry_index(SQ, (30, 51)) == 3  # nearest 2 (19 cells), past it on the leg 2 -> 3
    p = route([[0, 0], [10, 0], [20, 0]], "path")
    assert mr.entry_index(p, (2, 5)) == 0  # a path's first: its leg not nearer than itself
    assert mr.entry_index(p, (5, 1)) == 1  # a tie 0 / 1 -> 0, but past it on the leg 0 -> 1
    assert mr.entry_index(p, (20, 1)) is None  # at a path's end: nothing left


# --- the CLI --------------------------------------------------------------------------------------


def run_cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], *argv: str
            ) -> tuple[int, dict[str, Any]]:  # fmt: skip
    monkeypatch.setattr(sys, "argv", ["map_routes.py", *argv])
    rc = mr.main()
    return rc, json.loads(capsys.readouterr().out)


def test_check_prints_the_files_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                       capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    rc, out = run_cli(monkeypatch, capsys, "check", "fix_map", "--root", str(tmp_path))
    assert (rc, out) == (0, {"ok": True, "file": None, "note": "no routes file: INERT"})
    write(tmp_path, GOOD)
    rc, out = run_cli(monkeypatch, capsys, "check", "fix_map", "--root", str(tmp_path))
    assert rc == 0 and out["ok"] and [r["id"] for r in out["routes"]] == ["ring", "east-path"]
    write(tmp_path, GOOD.replace("kind: loop", "kind: circle"))
    rc, out = run_cli(monkeypatch, capsys, "check", "fix_map", "--root", str(tmp_path))
    assert rc == 1 and not out["ok"] and "loop or path" in out["error"]


def test_prove_loads_the_stand_grid_like_the_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``prove`` reads the map's GAT from camera.GAT_DIR and anim_region.stand_grid, as
    dungeon_hunt.py does. Here a SYNTHETIC GAT (no client data) and a stand grid stand-in."""
    from poring_dataset import camera as cam

    ok = ring_map()
    tiles = b"".join(struct.pack("<4fHH", 0, 0, 0, 0, 0 if ok[y, x] else 1, 0)
                     for y in range(H) for x in range(W))  # fmt: skip
    gats = tmp_path / "gat"
    gats.mkdir()
    (gats / "fix_map.gat").write_bytes(struct.pack("<4sBBII", b"GRAT", 1, 2, W, H) + tiles)
    monkeypatch.setattr(cam, "GAT_DIR", gats)
    stand = types.ModuleType("anim_region")
    stand.stand_grid = lambda m, gat: np.asarray(gat.walkable(), dtype=bool)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anim_region", stand)
    write(tmp_path, GOOD)
    rc, out = run_cli(monkeypatch, capsys, "prove", "fix_map", "--root", str(tmp_path))
    assert rc == 0 and out["ok"] and out["zones"] is None and out["grid"]["shape"] == [H, W]
    assert [r["total_steps"] for r in out["routes"]] == [156, 39]
    write(tmp_path, GOOD.replace("[49, 49], [10, 49]]", "[30, 30], [10, 49]]"))
    rc, out = run_cli(monkeypatch, capsys, "prove", "fix_map", "--root", str(tmp_path))
    assert rc == 1 and not out["ok"] and "waypoint 2 [30, 30]: not walkable" in out["problems"][0]
    monkeypatch.setattr(cam, "GAT_DIR", tmp_path / "no-gat")
    rc, out = run_cli(monkeypatch, capsys, "prove", "fix_map", "--root", str(tmp_path))
    assert rc == 2 and "no stand grid" in out["error"]
