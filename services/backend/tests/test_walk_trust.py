"""walk_trust.py (2026-10-26, docs/planning/gef10-cursor-unknown.md): the trusted walk cell and the
walk decision behind dungeon_hunt's ``--walk-trust`` (OFF by default). SYNTHETIC grids and zones
only: an open 40 x 40 field, one no-enter square (an NPC's grown area) and one NPC cell."""

from __future__ import annotations

import ast
import itertools
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import map_zones as mz  # noqa: E402
import walk_trust as wt  # noqa: E402

H, W = 40, 40
NPC = (30, 30)
NPC_AREA = [[26, 26], [34, 26], [34, 34], [26, 34]]  # the NPC's cell grown by 4, as the zones do


def field() -> Any:
    ok = np.zeros((H, W), dtype=bool)
    ok[1:39, 1:39] = True
    return ok


def zones(no_enter: Any = (NPC_AREA,)) -> mz.Zones:
    return mz.Zones(map="syn", reviewed_by="batt", reviewed="2026-10-26", no_cross=(),
                    no_enter=tuple(mz.NoEnter(f"ne{i}", "n", tuple(map(tuple, p)))
                                   for i, p in enumerate(no_enter)))  # fmt: skip


def why(here: tuple[int, int], aim: tuple[int, int], **kw: Any) -> str | None:
    ok = kw.pop("route_ok", field())
    carved = kw.pop("carved", np.zeros_like(ok))
    return wt.trust_why(here, aim, route_ok=ok, carved=carved, zones=kw.pop("zones", zones()),
                        npcs=kw.pop("npcs", [NPC]), **kw)  # fmt: skip


def test_lead_cells_follow_the_walk_direction_beyond_the_aim() -> None:
    assert wt.lead_cells((10, 10), (17, 10), 3) == [(17, 10), (18, 10), (19, 10), (20, 10)]
    assert wt.lead_cells((10, 10), (5, 15), 2) == [(5, 15), (4, 16), (3, 17)]
    assert wt.lead_cells((10, 10), (10, 10), 4) == [(10, 10)]  # no direction: the aim alone


def test_an_open_field_cell_far_from_the_npc_is_trusted() -> None:
    assert why((5, 5), (12, 5)) is None
    assert why((5, 5), (12, 12)) is None


def test_off_the_route_grid_or_carved_aims_are_not_trusted() -> None:
    ok = field()
    ok[5, 12] = False
    assert why((5, 5), (12, 5), route_ok=ok) == "off_grid"
    carved = np.zeros_like(field())
    carved[5, 12] = True
    assert why((5, 5), (12, 5), carved=carved) == "off_grid"
    assert why((5, 5), (45, 5)) == "off_grid"  # off the map


def test_a_wall_beyond_the_aim_ends_the_landing_cells_there() -> None:
    ok = field()
    ok[5, 14:] = False  # a wall 2 cells beyond the aim: the walk cannot land past it
    assert why((5, 5), (12, 5), route_ok=ok) is None


def test_a_landing_cell_inside_the_no_enter_area_is_not_trusted() -> None:
    # the aim (24, 30) is outside the NPC's area, but a click made while moving east lands up to
    # 4 cells further: (26..28, 30) are inside it
    assert why((17, 30), (24, 30), npcs=[], lead=4) == "no_enter"
    assert why((17, 30), (24, 30), npcs=[], lead=1) is None  # (25, 30): still outside


def test_a_landing_cell_near_an_npc_is_not_trusted_even_without_a_zone() -> None:
    # landing cells (19..23, 30): the nearest is 7 cells from the NPC (30, 30), not < NPC_MIN 6
    assert why((10, 30), (19, 30), zones=zones(()), lead=4) is None
    # landing cells (21..25, 30): (25, 30) is 5 cells from it
    assert why((10, 30), (21, 30), zones=zones(()), lead=4) == "npc"
    assert why((10, 30), (21, 30), zones=zones(()), lead=4, npcs=[]) is None  # no NPC on the map


def test_a_fresh_box_near_the_point_refuses_first() -> None:
    assert why((5, 5), (12, 5), box_near=True) == "box"


def test_decide_with_the_option_off_is_the_old_gate_for_every_verdict() -> None:
    legacy = {
        "clear": ("click", "clear"),
        "sword": ("engage", "sword"),
        "noentry": ("carve", "cursor noentry"),
        "unknown": ("refuse", "cursor unknown"),
    }
    for (verdict, want), red, trusted in itertools.product(legacy.items(), (0, 30), (True, False)):
        assert wt.decide(verdict, red, trusted=trusted, enabled=False, noentry_red=25) == want


def test_decide_with_the_option_on_changes_only_an_unknown() -> None:
    on = {"trusted": True, "enabled": True, "noentry_red": 25}
    assert wt.decide("clear", 0, **on) == ("click", "clear")
    assert wt.decide("sword", 0, **on) == ("engage", "sword")
    assert wt.decide("noentry", 30, **on) == ("carve", "cursor noentry")
    assert wt.decide("unknown", 0, **on) == ("click", "trusted")
    assert wt.decide("unknown", 25, **on) == ("carve", "cursor unknown + red")  # the ring's red
    assert wt.decide("unknown", 0, trusted=False, enabled=True, noentry_red=25) == (
        "refuse",
        "cursor unknown",
    )


def test_the_runner_wires_the_option_off_by_default() -> None:
    src = (ROOT / "scripts" / "dungeon_hunt.py").read_text()
    tree = ast.parse(src)
    found = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and getattr(n.func, "attr", "") == "add_argument"
        and n.args
        and isinstance(n.args[0], ast.Constant)
        and n.args[0].value == "--walk-trust"
    ]
    assert len(found) == 1
    kw = {k.arg: k.value for k in found[0].keywords}
    assert isinstance(kw["default"], ast.Constant) and kw["default"].value is False
    # the decision goes through walk_trust.decide with the flag, and the trust only on UNKNOWN
    assert "wtr.decide(" in src and "enabled=a.walk_trust" in src
    assert 'if a.walk_trust and res["verdict"] == "unknown":' in src


def test_walk_trust_reads_no_packets() -> None:
    src = (ROOT / "scripts" / "walk_trust.py").read_text()
    assert "poring_packets" not in src and "packets.jsonl" not in src
