"""scripts/map_prep.py (the map-agnostic hunt-map prep, docs/planning/payf07-prep.md) on SYNTHETIC
grids; the per-area zone click proof (orc_dungeon_prep.zone_clicks, generalised to any map); and
the committed pay_fild07 zones DRAFT: the loader refuses it until a person reviews it, and its
geometry (proved on a test-reviewer copy in tmp, never committed) covers every warp span + 4; and
the committed gef_fild10 zones (delegated 2026-10-25, docs/planning/gef10-prep.md): every warp
span and every script-NPC cell + 4, each arrival inside, the proposed stands outside."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import map_prep as mp  # noqa: E402
import map_zones as mz  # noqa: E402
import orc_dungeon_prep as odp  # noqa: E402

# --- pure parts ------------------------------------------------------------------------------


def test_clearance_is_the_largest_all_walkable_square() -> None:
    m = np.ones((9, 9), dtype=bool)
    m[0, 0] = False
    c = mp.clearance(m, max_r=6)
    assert c[4, 4] == 3  # the 7 x 7 square; the 9 x 9 one holds the hole at (0, 0)
    assert c[1, 1] == 0  # its 3 x 3 square holds the hole
    assert c[0, 0] == -1  # off the mask
    assert c[2, 2] == 1 and c[3, 3] == 2
    assert c[4, 1] == 1  # the map's edge counts as not walkable
    m[4, 6] = False
    assert mp.clearance(m, max_r=6)[4, 4] == 1  # a hole 2 cells east caps it at r = 1


def test_pick_fallback_is_the_nearest_clear_cell_far_enough() -> None:
    area = np.ones((50, 50), dtype=bool)
    clear = np.zeros((50, 50), dtype=np.int64)
    for x, y in [(10, 25), (25, 37), (45, 25), (27, 25)]:  # distances 15, 12, 20 and 2
        clear[y, x] = 10
    assert mp.pick_fallback(area, clear, (25, 25), min_sep=5, min_clear=10) == (25, 37)
    assert mp.pick_fallback(area, clear, (25, 25), min_sep=13, min_clear=10) == (10, 25)
    assert mp.pick_fallback(area, clear, (25, 25), min_sep=21, min_clear=10) is None
    area[37, 25] = False  # not in the area
    assert mp.pick_fallback(area, clear, (25, 25), min_sep=5, min_clear=10) == (10, 25)
    assert mp.pick_fallback(area, clear, (25, 25), min_sep=5, min_clear=11) is None


def test_open_neighbours_and_span_distance() -> None:
    ok = np.ones((5, 5), dtype=bool)
    ok[1, 1] = False
    assert mp.open_neighbours(ok, (2, 2)) == 7 and mp.open_neighbours(ok, (0, 0)) == 2
    warps = [{"x": 10, "y": 10, "span_x": 2, "span_y": 1}]
    assert mp.span_distance((10, 10), warps) == 0 and mp.span_distance((12, 11), warps) == 0
    assert mp.span_distance((15, 10), warps) == 3 and mp.span_distance((10, 14), warps) == 3
    assert mp.span_distance((0, 0), []) is None


def _zones(tmp_path: Path, polys: list[list[list[int]]], name: str = "syn_map",
           shape: tuple[int, int] = (40, 60)) -> mz.Zones:  # fmt: skip
    items = "".join(
        f'  - id: a{i}\n    note: "area {i}"\n    polygon: {p}\n' for i, p in enumerate(polys)
    )
    (tmp_path / f"{name}.yaml").write_text(
        f"map: {name}\nreviewed_by: tester\nreviewed: 2026-10-24\nno_cross: []\nno_enter:\n{items}"
    )
    z = mz.load(name, tmp_path, shape)
    assert z is not None
    return z


def test_runner_area_keeps_warps_off_and_drops_zones_and_sealed_cells(tmp_path: Path) -> None:
    ok = np.ones((80, 100), dtype=bool)
    warps = [{"x": 50, "y": 40, "span_x": 1, "span_y": 1}]
    z = _zones(tmp_path, [[[22, 22], [30, 22], [30, 30], [22, 30]]], shape=ok.shape)
    area, okr = mp.runner_area(ok, warps, z)
    assert not area[40, 50] and not area[40, 39] and area[40, 38]  # the span + 10 kept off
    assert not area[25, 25] and not okr[25, 25] and okr[40, 50]  # a zone cell; the warp stays
    # the search area: 20 cells off every edge (60 x 40), minus the span box (23 x 23), minus
    # the area (9 x 9); the route grid: everything but the area
    assert area.sum() == 60 * 40 - 23 * 23 - 9 * 9
    assert okr.sum() == ok.sum() - 9 * 9
    # a line that seals a room: the room leaves the area and the route grid
    (tmp_path / "syn_seal.yaml").write_text(
        "map: syn_seal\nreviewed_by: tester\nreviewed: 2026-10-24\nno_cross:\n"
        "  - id: door\n    note: \"the door\"\n    points: [[60, 30], [60, 31]]\n")  # fmt: skip
    room = np.zeros((80, 100), dtype=bool)
    room[20:60, 20:80] = True
    room[20:60, 60] = False  # a wall at x 60 ...
    room[30:32, 60] = True  # ... with a 2-cell door at y 30-31
    zs = mz.load("syn_seal", tmp_path, room.shape)
    assert zs is not None
    area_s, okr_s = mp.runner_area(room, [], zs)
    assert not area_s[45, 70] and not okr_s[45, 70]  # the room east of the door is sealed off


def test_components_counts_both_connectivities() -> None:
    m = np.zeros((5, 5), dtype=bool)
    m[0, 0] = m[1, 1] = True  # diagonal only: one piece without the corner rule, two with it
    m[4, 4] = True
    c = mp.components(m)
    assert c["no_corner_rule"] == {"n": 2, "largest": [2, 1]}
    assert c["corner_rule"] == {"n": 3, "largest": [1, 1, 1]}


# --- the zone click proof, any map -----------------------------------------------------------


def test_zone_clicks_refuses_every_click_into_an_area_and_onto_its_span(tmp_path: Path) -> None:
    both = np.ones((40, 60), dtype=bool)
    z = _zones(tmp_path, [[[40, 10], [52, 10], [52, 22], [40, 22]]])
    warps = [{"x": 46, "y": 16, "span_x": 2, "span_y": 2}]
    rows = odp.zone_clicks(z, both, warps, samples=50, seed=0)
    assert len(rows) == 1
    r = rows[0]
    assert (r["walkable_in_area"], r["warp_span_cells"]) == (13 * 13, 25)
    assert r["into_refused"] == "50/50" and r["onto_span_refused"] == "50/50"
    assert set(r["into_reasons"]) == {"dest_no_enter"}
    # an area with no warp inside says so instead of sampling the span leg
    z2 = _zones(tmp_path, [[[5, 5], [12, 5], [12, 12], [5, 12]]], "syn_two")
    r2 = odp.zone_clicks(z2, both, warps, samples=10, seed=0)[0]
    assert r2["warp_span_cells"] == 0 and r2["onto_span_refused"] is None
    assert r2["into_refused"] == "10/10"


# --- the committed pay_fild07 zones (a DRAFT until Batt delegated it, 2026-10-24 ~11:3x) ------

PAY07_SPANS = {  # data/kb/warps.json (rAthena npc/pre-re/warps/fields/payon_fild.txt)
    "warp-pay_fild01": (16, 200, 3, 3),
    "warp-pay_fild03": (163, 17, 5, 2),
    "warp-pay_fild08": (280, 382, 4, 2),
    "warp-pay_fild10": (382, 290, 2, 5),
}
PAY07_ARRIVALS = [(23, 207), (167, 20), (280, 379), (379, 290)]  # from the neighbouring maps


def test_the_pay_fild07_zones_carry_batts_recorded_delegation() -> None:
    """Batt 2026-10-24 ~11:3x: "ok" to the delegation asked in the 11:13 report (item 2)."""
    z = mz.load("pay_fild07", mz.ZONES_DIR, (400, 400))
    assert z is not None and z.reviewed_by == "agent (delegated by batt, 2026-10-24)"
    data = yaml.safe_load((mz.ZONES_DIR / "pay_fild07.yaml").read_text())
    assert "11:13 report item 2" in data["delegation"]


def test_the_pay_fild07_draft_geometry_covers_every_span_plus_four(tmp_path: Path) -> None:
    text = (mz.ZONES_DIR / "pay_fild07.yaml").read_text()
    (tmp_path / "pay_fild07.yaml").write_text(text)
    z = mz.load("pay_fild07", tmp_path, (400, 400))
    assert z is not None and not z.no_cross
    assert [n.id for n in z.no_enter] == list(PAY07_SPANS)
    for ne, (x, y, sx, sy) in PAY07_SPANS.items():
        item = next(n for n in z.no_enter if n.id == ne)
        for cx in range(x - sx - 4, x + sx + 5):
            for cy in range(y - sy - 4, y + sy + 5):
                assert mz.in_polygon((cx, cy), item.polygon), (ne, cx, cy)
        # exactly the span + 4: the next ring outside is not in the area
        assert not mz.in_polygon((x - sx - 5, y), item.polygon)
        assert not mz.in_polygon((x + sx + 5, y), item.polygon)
        assert not mz.in_polygon((x, y - sy - 5), item.polygon)
        assert not mz.in_polygon((x, y + sy + 5), item.polygon)
    for c in PAY07_ARRIVALS:
        assert mz.in_no_enter(z, c), c
    for c in [(198, 202), (198, 182)]:  # the proposed START and FALLBACK stands (payf07-prep 5)
        assert not mz.in_no_enter(z, c)


# --- the committed gef_fild10 zones (delegated by Batt 2026-10-25 ~13:1x, gef10-prep.md 4) ------

GEF10_SPANS = {  # data/kb/warps.json (rAthena npc/pre-re/warps/fields/geffen_fild.txt)
    "warp-gef_fild09": (251, 371, 5, 2),
    "warp-gef_fild11": (104, 21, 5, 2),
    "warp-gef_fild03": (370, 56, 2, 5),
    "warp-gef_fild14": (27, 219, 1, 1),
    "door-in_orcs01-136-331": (136, 331, 1, 1),
    "door-in_orcs01-138-284": (138, 284, 1, 1),
    "door-in_orcs01-215-51": (215, 51, 1, 1),
    "door-in_orcs01-223-205": (223, 205, 1, 1),
    "door-in_orcs01-63-337": (63, 337, 1, 1),
}
GEF10_NPCS = {  # data/kb/npc_cells.json: the 5 dialog NPCs (no touch area), a span of 0
    "npc-kafra-73-340": (73, 340, 0, 0),
    "npc-board-69-340": (69, 340, 0, 0),
    "npc-board-109-23": (109, 23, 0, 0),
    "npc-orcsmemory-242-202": (242, 202, 0, 0),
    "npc-orcsmemory-238-202": (238, 202, 0, 0),
}
# from the neighbouring maps' warp lines and the 5 houses' (npc/warps/dungeons/orcsdun.txt)
GEF10_ARRIVALS = [(251, 368), (104, 24), (367, 56), (31, 219), (138, 329), (137, 286), (214, 53),
                  (223, 203), (65, 335)]  # fmt: skip
GEF10_WEST = {"door-in_orcs01-63-337": 2}  # + 2 more west: the pocket (56-57, 334) is inside


def test_the_gef_fild10_zones_carry_batts_recorded_delegation() -> None:
    """Batt 2026-10-25 ~13:1x, his answer to the parent's question: "Delegate gef_fild10 zones"."""
    z = mz.load("gef_fild10", mz.ZONES_DIR, (400, 400))
    assert z is not None and z.reviewed_by == "agent (delegated by batt, 2026-10-25)"
    assert str(z.reviewed) == "2026-10-25"
    data = yaml.safe_load((mz.ZONES_DIR / "gef_fild10.yaml").read_text())
    assert "Delegate gef_fild10 zones" in data["delegation"]


def test_the_gef_fild10_geometry_covers_every_span_and_npc_plus_four() -> None:
    z = mz.load("gef_fild10", mz.ZONES_DIR, (400, 400))
    assert z is not None and not z.no_cross
    want = {**GEF10_SPANS, **GEF10_NPCS}
    assert [n.id for n in z.no_enter] == list(want)
    for ne, (x, y, sx, sy) in want.items():
        item = next(n for n in z.no_enter if n.id == ne)
        west = GEF10_WEST.get(ne, 0)
        for cx in range(x - sx - 4 - west, x + sx + 5):
            for cy in range(y - sy - 4, y + sy + 5):
                assert mz.in_polygon((cx, cy), item.polygon), (ne, cx, cy)
        # exactly the span + 4 (+ the recorded west extension): the next ring is not in the area
        assert not mz.in_polygon((x - sx - 5 - west, y), item.polygon)
        assert not mz.in_polygon((x + sx + 5, y), item.polygon)
        assert not mz.in_polygon((x, y - sy - 5), item.polygon)
        assert not mz.in_polygon((x, y + sy + 5), item.polygon)
    for c in GEF10_ARRIVALS:
        assert mz.in_no_enter(z, c), c
    for c in [(186, 179), (186, 159)]:  # the proposed START and FALLBACK stands (gef10-prep 5)
        assert not mz.in_no_enter(z, c)


# --- the committed xmas_dun02 zones (Batt's order 2026-11-05 ~13:2x; xmas02-prep.md 2) ----------

XMAS02_SPAN = (129, 130, 1, 1)  # data/kb/warps.json: xmas_dun2-2 -> xmas_dun01, the only warp
XMAS02_ARRIVAL = (131, 130)  # from xmas_dun01 (npc/warps/dungeons/xmas_dun.txt:18): ONE step east
XMAS02_DTS = (130, 123)  # the Kafra dungeon teleport's arrival (npc/kafras/dts_warper.txt)
XMAS02_STANDS = [(7, 21), (114, 23)]  # START (the edge loop's waypoint 0) and FALLBACK (74)


def test_the_xmas_dun02_zones_cite_batts_edge_order() -> None:
    """The keep-out is the safety necessity of Batt's edge technique (rogue-xmas02.md 0)."""
    z = mz.load("xmas_dun02", mz.ZONES_DIR, (260, 260))
    assert z is not None and z.reviewed_by == "agent (delegated by batt, 2026-11-05)"
    assert str(z.reviewed) == "2026-11-05"
    data = yaml.safe_load((mz.ZONES_DIR / "xmas_dun02.yaml").read_text())
    assert "walk along the edge of the map, going clockwise" in data["delegation"]


def test_the_xmas_dun02_geometry_covers_the_exit_warp_plus_four() -> None:
    z = mz.load("xmas_dun02", mz.ZONES_DIR, (260, 260))
    assert z is not None and not z.no_cross
    (item,) = z.no_enter
    assert item.id == "warp-xmas_dun01"
    x, y, sx, sy = XMAS02_SPAN
    for cx in range(x - sx - 4, x + sx + 5):
        for cy in range(y - sy - 4, y + sy + 5):
            assert mz.in_polygon((cx, cy), item.polygon), (cx, cy)
    # exactly the span + 4: the next ring outside is not in the area
    for c in [(x - sx - 5, y), (x + sx + 5, y), (x, y - sy - 5), (x, y + sy + 5)]:
        assert not mz.in_polygon(c, item.polygon), c
    assert mz.in_no_enter(z, XMAS02_ARRIVAL)  # never stand one step from the trigger
    assert not mz.in_no_enter(z, XMAS02_DTS)
    for c in XMAS02_STANDS:
        assert not mz.in_no_enter(z, c), c
