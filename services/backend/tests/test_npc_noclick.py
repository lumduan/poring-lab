"""scripts/npc_noclick.py (walk@17 item 5, Batt 2026-10-09 ~16:15): the L3 NO-CLICK layer, on
synthetic L3 files (ids and paths invented; real L3 is GPL-derived and never committed) and the
committed RDP camera on FLAT ground (a real GAT is client data)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]


def load() -> ModuleType:
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(ROOT / "packages/poring_dataset/src"))
    spec = importlib.util.spec_from_file_location("npc_noclick", ROOT / "scripts/npc_noclick.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["npc_noclick"] = mod
    spec.loader.exec_module(mod)
    return mod


nc = load()


def camera() -> object:
    from poring_dataset import camera as cam

    cj = json.loads((ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    return cam.camera_from_json(cj["camera"])


def world(pos: tuple[int, int]) -> SimpleNamespace:
    return SimpleNamespace(camera=camera(), gat=None, position=pos)


def kb(tmp: Path, complete: bool | None = None) -> Path:
    (tmp / "bindings").mkdir(parents=True)
    (tmp / "route.json").write_text(json.dumps({"npcs": {
        "guides": [{"file": "npc/a.txt", "line": 3, "map": "town", "x": 54, "y": 87,
                    "sprite": "105"},
                   {"file": "npc/a.txt", "line": 9, "map": "town", "x": 40, "y": 40,
                    "sprite": "111"},  # HIDDEN_NPC: never drawn, never clicked
                   {"file": "npc/b.txt", "line": 1, "map": "elsewhere", "x": 1, "y": 1,
                    "sprite": "90"}]}}))  # fmt: skip
    (tmp / "bindings/lab-rathena.json").write_text(
        json.dumps(
            {
                "npc": {
                    "positions": {
                        "npcs": [
                            {
                                "name": "x",
                                "map": "town",
                                "x": 54,
                                "y": 87,
                                "file": "npc/a.txt",
                                "line": 3,
                            },
                            {
                                "name": "y",
                                "map": "town",
                                "x": 60,
                                "y": 80,
                                "file": "npc/c.txt",
                                "line": 5,
                            },
                        ]
                    }
                }
            }
        )
    )
    if complete is not None:
        (tmp / "npc_cells.json").write_text(
            json.dumps(
                {
                    "maps": {
                        "town": {
                            "complete": complete,
                            "npcs": [
                                {"x": 55, "y": 90, "sprite": "722", "file": "npc/g.txt", "line": 7},
                                {
                                    "x": 58,
                                    "y": 92,
                                    "sprite": "705",
                                    "file": "npc/w.txt",
                                    "line": 9,
                                    "drawn": "conditional",
                                },
                            ],
                        }
                    }
                }
            )
        )
    return tmp


def test_l3_npcs_merge_the_lists_by_cell_and_drop_undrawn_sprites(tmp_path: Path) -> None:
    npcs, cov = nc.load_l3_npcs("town", kb(tmp_path))
    assert [n.cell for n in npcs] == [(54, 87), (60, 80)]  # (40, 40) is a HIDDEN_NPC
    assert npcs[0].sprite == "105" and npcs[0].key == "npc/a.txt:3"
    assert cov["complete"] is False and cov["counts"] == {"route.json": 2, "bindings": 2}


def test_only_the_complete_list_declares_coverage(tmp_path: Path) -> None:
    npcs, cov = nc.load_l3_npcs("town", kb(tmp_path, complete=True))
    assert cov["complete"] is True
    assert (55, 90) in [n.cell for n in npcs]
    marks = {n.cell: n.drawn for n in npcs}
    assert marks[(58, 92)] == "conditional" and marks[(55, 90)] is True  # kept, but marked
    with pytest.raises(SystemExit):
        nc.NoClickLayer.for_map("town", kb(tmp_path / "partial", complete=False),
                                require_complete=True)  # fmt: skip
    assert nc.NoClickLayer.for_map("town", tmp_path, require_complete=True).complete


def npc(cell: tuple[int, int], sprite: str | None = None) -> object:
    return nc.StaticNpc("prontera", cell, f"test:{cell[0]},{cell[1]}", sprite, "test")


def test_the_two_town_contact_clicks_are_refused() -> None:
    """3.29a's evidence (session 20261009T140625): both walk@15 clicks that became npc_contact
    lie inside the PROVISIONAL footprint of the NPC they contacted (flat camera)."""
    flag, guide = npc((155, 190), "722"), npc((154, 187), "105")
    layer = nc.NoClickLayer([flag, guide])
    got = layer.refuse_point(world((161, 192)), 464.9, 360.9)  # route 48, cell (156, 192)
    assert got is not None and got["refused"] == nc.REASON and got["cell"] == [155, 190]
    got = layer.refuse_point(world((155, 186)), 568.3, 291.9)  # route 55's substitute (153, 189)
    assert got is not None and got["cell"] == [154, 187]
    # far from both: a plain walk click
    assert layer.refuse_point(world((155, 186)), 900.0, 500.0) is None


def test_a_layer_without_the_npc_protects_nothing() -> None:
    """The L3 KB of 2026-10-09 lacks prontera's guild flags: contact 1 is NOT refused by it."""
    layer = nc.NoClickLayer([npc((154, 187), "105")])
    assert layer.refuse_point(world((161, 192)), 464.9, 360.9) is None


def test_filter_points_and_the_cell_answer() -> None:
    layer = nc.NoClickLayer([npc((154, 187))])
    w = world((155, 186))
    ((fu, fv),) = w.camera.project([[154 - 155, 187 - 186]])
    kept, refused = layer.filter_points(w, [(fu, fv - 40), (fu + 200, fv)])
    assert kept == [(fu + 200, fv)] and refused[0]["refused"] == nc.REASON
    assert layer.cell_refused(w, (154, 187), []) == nc.REASON  # the NPC's own cell, always
    assert layer.cell_refused(w, (154, 189), [(fu, fv - 40)]) == nc.REASON  # every point refused
    assert layer.cell_refused(w, (160, 187), [(fu + 200, fv)]) is None
    assert layer.cell_refused(w, (160, 187), []) is None  # no points: the caller's no_safe_point


def test_a_measured_footprint_replaces_the_provisional_one() -> None:
    small = nc.Footprint(10, 10, 20, 5, "measured (test)")
    layer = nc.NoClickLayer([npc((154, 187), "105")], footprints={"105": small})
    w = world((155, 186))
    ((fu, fv),) = w.camera.project([[-1, 1]])
    assert layer.refuse_point(w, fu + 30, fv - 40) is None  # inside PROVISIONAL, outside small
    assert nc.NoClickLayer([npc((154, 187), "105")]).refuse_point(w, fu + 30, fv - 40)


def test_near_cells_are_the_npc_cells_and_their_neighbours() -> None:
    near = nc.NoClickLayer([npc((10, 10))]).near_cells()
    assert len(near) == 9 and (11, 11) in near and (12, 10) not in near
    assert len(nc.NoClickLayer([npc((10, 10))]).near_cells(2)) == 25


def test_the_provisional_footprint_says_so() -> None:
    assert nc.PROVISIONAL.source.startswith("PROVISIONAL")
    x0, y0, x1, y1 = nc.PROVISIONAL.box(100.0, 200.0)
    assert (x0, y0, x1, y1) == (40.0, 35.0, 160.0, 236.0)
