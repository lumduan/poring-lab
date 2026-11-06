"""xmas_dun02's TERRAIN occluders, the label rule's ``o3h-t`` candidate (docs/planning/
xmas02-detector.md 4f, D10; tool gap T-4): orc_labels_fix.TerrainOccluders / terrain_test and
their wiring into map_labels (threshold / freeze / check / labels), on SYNTHETIC GAT bytes and the
lab's fitted outdoor camera, plus a REAL positive case on xmas_dun02's client GAT (read from
/dev/shm at run time, skipped when it is absent; client data is never committed). Every map
without the terrain switch keeps its behaviour (gef_fild10, pay_fild07)."""

from __future__ import annotations

import json
import struct
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from poring_dataset import camera as cm
from poring_dataset import gat as gatmod
from poring_dataset import render as rd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import map_labels as ml  # noqa: E402
import orc_labels_fix as olf  # noqa: E402

CAM_JSON = cm.load_camera_json(Path(cm.__file__).parent / "camera_rdp.json")
CAM = cm.map_camera(CAM_JSON, "xmas_dun02", frozenset())  # the outdoor camera (yaw ~0)
LABEL = (30, 30)


def gat_bytes(alt: np.ndarray, types: np.ndarray | None = None) -> bytes:
    """A GAT 1.2, ``alt[y, x]`` UP positive (every corner at -alt: RO's negative-up axis)."""
    h, w = alt.shape
    tiles = np.zeros(w * h, gatmod.TILE)
    for corner in ("sw", "se", "nw", "ne"):
        tiles[corner] = -alt.ravel()
    tiles["type"] = (np.zeros_like(alt, dtype=np.uint16) if types is None else types).ravel()
    return struct.pack("<4sBBII", b"GRAT", 1, 2, w, h) + tiles.tobytes()


def world(tmp: Path, blocks: dict[tuple[int, int], float], size: int = 60,
          floor: float = 0.0) -> tuple[olf.TerrainOccluders, rd.Scene]:  # fmt: skip
    """A flat map at ``floor`` with ``blocks`` {(x, y): altitude}; the camera on LABEL."""
    alt = np.full((size, size), floor, dtype=float)
    for (x, y), a in blocks.items():
        alt[y, x] = a
    path = tmp / "m.gat"
    path.write_bytes(gat_bytes(alt))
    assert CAM is not None
    scene = rd.Scene(CAM, (float(LABEL[0]), float(LABEL[1])), gatmod.parse(path.read_bytes()))
    return olf.TerrainOccluders(path), scene


def box_at(scene: rd.Scene, cell: tuple[float, float], w: float = 30.0,
           h: float = 60.0) -> tuple[float, float, float, float]:  # fmt: skip
    """A label box ``w`` x ``h`` px standing on the cell's projected anchor (Cookie's size)."""
    (u, v), _z = rd.anchor_and_depth(scene, cell)
    return (u - w / 2, v - h, u + w / 2, v)


def row_of(y: int, alt: float, xs: tuple[int, ...] = (29, 30, 31)) -> dict[tuple[int, int], float]:
    return {(x, y): alt for x in xs}


# --- the occluders (4f) ------------------------------------------------------------------------


def test_a_raised_block_south_of_the_label_hides_it_and_the_same_block_north_does_not(
    tmp_path: Path,
) -> None:
    """Gat.altitude is UP positive (the corners are stored negative): a block 30 units up, 2
    cells SOUTH (y 28 < the label's 30, nearer the yaw-0 camera), draws its top above the label's
    feet: under terrain, its rise 30. The same block 2 cells NORTH (y 32) is behind the label:
    not under. The cell box spans the label's floor to the block's top."""
    t, scene = world(tmp_path, row_of(28, 30.0))
    assert t.alt[28, 30] == 30.0 and t.alt[30, 30] == 0.0  # up positive, as the camera uses it
    box = box_at(scene, LABEL)
    assert t.rise(scene, box, LABEL) == 30.0 and t.hit(scene, box, LABEL)
    cells, floor = t.candidates(LABEL)
    assert floor == 0.0 and sorted(map(tuple, cells.tolist())) == [(29, 28), (30, 28), (31, 28)]
    cb = t.cell_boxes(scene, cells, floor)
    assert (cb[:, 1] < box[3]).all() and (cb[:, 3] > box[3]).all()  # top above the feet
    t2, scene2 = world(tmp_path, row_of(32, 30.0))
    assert len(t2.candidates(LABEL)[0]) == 0  # north: never a candidate
    assert t2.rise(scene2, box_at(scene2, LABEL), LABEL) is None
    assert not t2.hit(scene2, box_at(scene2, LABEL), LABEL)


def test_a_block_below_the_step_does_not_hide_and_the_report_steps_see_it(tmp_path: Path) -> None:
    """The step is 10 units over the label's OWN cell: a block 8 up is under terrain only at the
    reported step 5; a block 15 up at 5 and 10, not 20; a label on a 20-unit platform with a
    25-unit block 1 cell south of it rises 5 only. A block beside the label's column, off its
    box, and one beyond the window are not searched or not hit."""
    t, scene = world(tmp_path, row_of(29, 8.0))
    box = box_at(scene, LABEL)
    assert t.rise(scene, box, LABEL) == 8.0 and not t.hit(scene, box, LABEL)
    t, scene = world(tmp_path, row_of(29, 15.0))
    r = t.rise(scene, box_at(scene, LABEL), LABEL)
    assert r == 15.0 and [r >= s for s in (5.0, 10.0, 20.0)] == [True, True, False]
    assert t.hit(scene, box_at(scene, LABEL), LABEL)
    plat = {(x, y): 20.0 for x in range(26, 35) for y in range(28, 33)} | row_of(29, 25.0)
    t, scene = world(tmp_path, plat)
    assert t.rise(scene, box_at(scene, LABEL), LABEL) == 5.0  # relative to the label's floor
    assert not t.hit(scene, box_at(scene, LABEL), LABEL)
    t, scene = world(tmp_path, {(36, 29): 40.0, (30, 30 - olf.TERRAIN_SOUTH - 1): 200.0})
    assert t.rise(scene, box_at(scene, LABEL), LABEL) is None  # 6 columns east: off the box
    assert len(t.candidates(LABEL)[0]) == 1  # the far one lies outside the window


def test_the_terrain_rule_refuses_what_it_cannot_judge(tmp_path: Path) -> None:
    """No GAT file; a scene without its GAT (flat ground would call everything clear); a camera
    turned to the indoor yaw (south is no longer nearer the camera)."""
    with pytest.raises(SystemExit, match="not extracted"):
        olf.TerrainOccluders(tmp_path / "none.gat")
    t, scene = world(tmp_path, row_of(28, 30.0))
    box = box_at(scene, LABEL)
    with pytest.raises(SystemExit, match="GAT"):
        t.rise(rd.Scene(scene.camera, scene.player, None), box, LABEL)
    assert CAM is not None
    indoor = cm.map_camera(CAM_JSON, "xmas_dun02", frozenset({"xmas_dun02"}))
    assert indoor is not None and abs(np.degrees(indoor.yaw)) > 40
    with pytest.raises(SystemExit, match="yaw"):
        t.rise(rd.Scene(indoor, scene.player, scene.gat), box, LABEL)


def model_occluders(t: olf.TerrainOccluders | None, model_box: bool) -> olf.Occluders:
    """An Occluders with ONE model (a 1-cell, 40-unit pillar at (40, 20), far from LABEL) or
    none, without an RSW file (the reader is tested in test_orc_labels_fix)."""
    o = olf.Occluders.__new__(olf.Occluders)
    o.models = []
    if model_box:
        o.models = [(7, "pillar.rsm", np.array([[39.5, 19.5], [40.5, 20.5]]),
                     np.array([0.0, 40.0]))]  # fmt: skip
    o._cache, o.terrain = {}, t
    return o


def test_under_names_a_model_first_then_terrain_and_is_hit_without_terrain(tmp_path: Path) -> None:
    t, scene = world(tmp_path, row_of(28, 30.0))
    box = box_at(scene, LABEL)
    on_model = box_at(scene, (40.0, 20.0))
    o = model_occluders(t, True)
    assert o.hit(scene, on_model) == 7 and o.under(scene, on_model, (40.0, 20.0)) == "model"
    assert o.hit(scene, box) is None and o.under(scene, box, LABEL) == "terrain"
    assert o.terrain_rise(scene, box, LABEL) == 30.0
    off = model_occluders(None, True)  # every map without the switch: the models' test alone
    assert off.under(scene, box, LABEL) is None and off.terrain_rise(scene, box, LABEL) is None
    assert off.under(scene, on_model, (40.0, 20.0)) == "model"


# --- the decision (o3h-t = o3h with terrain treated as a model) --------------------------------


def fate(gid: int, under: bool, terrain: bool, ncc: float | None = 0.7,
         fail: str | None = None) -> olf.LabelFate:  # fmt: skip
    fit = None if ncc is None else (ncc, 0, 0, 0)
    return olf.LabelFate(gid, 1265, under, None, fit, fail, box=(0, 0, 10, 10), raw=(0, 0, 10, 10),
                         terrain=terrain, terrain_rise=30.0 if terrain else None)  # fmt: skip


def test_o3h_t_judges_a_label_under_terrain_as_o3h_judges_one_under_a_model() -> None:
    fates = [
        fate(1, False, False, 0.30),  # clear, a weak fit: kept (the floor is the label file's)
        fate(2, False, True, 0.70),  # under terrain, fits well
        fate(3, False, True, 0.50),  # under terrain, below T_h 0.6
        fate(4, False, True, None, fail="unfit"),  # under terrain, the fit fails
        fate(5, True, True, 0.50),  # under a model AND terrain: the model's rule
        fate(6, True, False, 0.70),  # under a model, fits well
    ]

    def run(rule: str) -> tuple[set[int], dict[int, str]]:
        kept, ex = olf.decide(fates, rule, False, 0.6)
        return {f.gid for f in kept}, {g: why for g, _m, why in ex}

    k, ex = run("o3h")  # terrain changes nothing under o3h
    assert k == {1, 2, 3, 6} and ex == {4: "unfit", 5: "occluded_model"}
    k, ex = run("o3h-t")
    assert k == {1, 2, 6}
    assert ex == {3: "occluded_terrain", 4: "occluded_terrain", 5: "occluded_model"}
    same = [olf.LabelFate(f.gid, f.mob, f.under, f.pre, f.fit, f.fail, box=f.box, raw=f.raw)
            for f in fates]  # the same fates without the terrain flags: o3h-t is o3h  # fmt: skip
    assert olf.decide(same, "o3h-t", False, 0.6) == olf.decide(same, "o3h", False, 0.6)
    assert olf.OCCLUSIONS == ("1c", "o3h", "o3")  # orcsdun01's 3i candidates are unchanged


def test_o3h_t_needs_the_terrain_occluders() -> None:
    lab = SimpleNamespace(timeline=SimpleNamespace(events=()), size=(1280, 720), ui_rects=())
    params = {"offset_ms": 120.0, "anchors_px": {}, "fit_px": {}, "tau": 0.092, "o3h_tau": 0.6}
    with pytest.raises(SystemExit, match="terrain"):
        olf.FixLabeler(lab, params, model_occluders(None, False), rule="fix2",  # type: ignore[arg-type]
                       occlusion="o3h-t", map_name="xmas_dun02")  # fmt: skip
    olf.FixLabeler(lab, params, model_occluders(None, False), rule="fix2",  # type: ignore[arg-type]
                   occlusion="o3h", map_name="xmas_dun02")  # fmt: skip


# --- the adoption test (4f, FIT) -----------------------------------------------------------------


def spread(n: int, lo: float, hi: float) -> list[float]:
    return [round(lo + (hi - lo) * i / (n - 1), 4) for i in range(n)]


def test_the_adoption_test_needs_all_three_conditions() -> None:
    """ADOPT when n under terrain >= 30, the median NCC lower by >= 0.05 and the two-sided
    Mann-Whitney p < 0.01; each failing ALONE refuses; the rise decides at each step."""
    rest = [(v, None) for v in spread(200, 0.55, 0.85)]  # median 0.70
    ok = olf.terrain_test(rest + [(v, 30.0) for v in spread(40, 0.45, 0.65)])
    assert ok["adopt"] and all(ok["conditions"].values())
    assert ok["n_under"] == 40 and ok["median_drop"] == pytest.approx(0.15)
    few = olf.terrain_test(rest + [(v, 30.0) for v in spread(29, 0.45, 0.65)])
    assert few["conditions"] == {"n_under": False, "median_drop": True, "mann_whitney": True}
    assert not few["adopt"]
    near = [(v, None) for v in spread(200, 0.595, 0.605)]
    small = olf.terrain_test(near + [(v, 30.0) for v in spread(200, 0.555, 0.565)])
    assert small["median_drop"] == pytest.approx(0.04) and small["mann_whitney_p_two_sided"] < 1e-6
    assert small["conditions"] == {"n_under": True, "median_drop": False, "mann_whitney": True}
    wide = [(v, None) for v in spread(201, 0.10, 1.00)]  # median 0.55, very spread
    noisy = olf.terrain_test(wide + [(v, 30.0) for v in spread(31, 0.05, 0.95)])
    assert noisy["median_drop"] == pytest.approx(0.05)  # exactly at the bar: passes
    assert noisy["conditions"] == {"n_under": True, "median_drop": True, "mann_whitney": False}
    # the step picks who is under: rise 7 is "under" at 5 only, rise 15 at 5 and 10
    rows = rest + [(v, 7.0) for v in spread(40, 0.45, 0.65)]
    assert olf.terrain_test(rows, 5.0)["n_under"] == 40 and olf.terrain_test(rows)["n_under"] == 0
    rows = rest + [(v, 15.0) for v in spread(40, 0.45, 0.65)]
    assert [olf.terrain_test(rows, s)["n_under"] for s in (5.0, 10.0, 20.0)] == [40, 40, 0]


def test_mann_whitney_keeps_its_rounding_unless_asked() -> None:
    import gef10_r2_measure as r2m

    a, b = spread(30, 0.4, 0.6), spread(30, 0.45, 0.65)
    p = r2m.mann_whitney(a, b, ndigits=None)
    assert p is not None and r2m.mann_whitney(a, b) == round(p, 4) and p != round(p, 4)


# --- map_labels: the switch, threshold's report, freeze's rule, check's two rules ---------------


def test_only_xmas_dun02_switches_the_terrain_rule_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Merged with the XMAS02 MapSpec (T-2): it alone sets ``terrain``; every older map is off."""
    assert {n for n, spec in ml.MAPS.items() if spec.terrain} == {"xmas_dun02"}
    gat: list[Any] = []
    monkeypatch.setattr(olf, "TerrainOccluders", lambda path: gat.append(path) or "terrain")
    monkeypatch.setattr(olf, "Occluders", lambda *a, **k: k["terrain"])
    from poring_dataset.camera import GAT_DIR

    assert ml.occluders(ml.XMAS02) == "terrain" and gat == [GAT_DIR / "xmas_dun02.gat"]
    seen: dict[str, Any] = {}
    monkeypatch.setattr(olf, "Occluders", lambda *a, **k: seen.update(a=a, k=k) or "occl")
    assert ml.occluders(ml.GEF10) == "occl" and seen["k"] == {"terrain": None}
    assert seen["a"] == (ml.GEF10.rsw, ml.GEF10.models, ml.GEF10.cells)


def test_a_map_with_the_switch_gets_its_gat_terrain(monkeypatch: pytest.MonkeyPatch,
                                                    tmp_path: Path) -> None:  # fmt: skip
    import dataclasses

    (tmp_path / "gef_fild10.gat").write_bytes(gat_bytes(np.zeros((4, 4))))
    monkeypatch.setattr(cm, "GAT_DIR", tmp_path)
    seen: dict[str, Any] = {}
    monkeypatch.setattr(olf, "Occluders", lambda *a, **k: seen.update(k=k) or "occl")
    ml.occluders(dataclasses.replace(ml.GEF10, terrain=True))
    t = seen["k"]["terrain"]
    assert isinstance(t, olf.TerrainOccluders) and t.gat_path == tmp_path / "gef_fild10.gat"
    assert t.step == 10.0 and t.report_steps == (5.0, 20.0)


def trow(mob: int, ncc: float, rise: float | None, under: bool = False, pre: str | None = None,
         crowded: bool = False) -> dict[str, Any]:  # fmt: skip
    return {"mob": mob, "ncc": ncc, "under": under, "pre": pre, "fail": None, "crowded": crowded,
            "terrain": rise is not None and rise >= 10.0, "terrain_rise": rise}  # fmt: skip


def test_threshold_reports_both_rules_and_the_test_on_4es_set() -> None:
    """o3h-t's T_h leaves out the labels under terrain; the test's population is 4e's set (clear
    of the models, no 2b / 2c / engaged / facing_unknown, uncrowded); 5 / 20 reported."""
    rows = [trow(1249, v, None) for v in spread(200, 0.55, 0.85)]
    rows += [trow(1265, v, 30.0) for v in spread(40, 0.30, 0.50)]
    rows += [trow(1248, 0.10, 30.0, under=True), trow(1248, 0.10, 30.0, pre="facing_unknown"),
             trow(1248, 0.10, 30.0, crowded=True)]  # outside the population  # fmt: skip
    rep = ml.terrain_report(rows, alone=True, t_h=0.4)
    assert rep["adoption_test"]["n_under"] == 40 and rep["adoption_test"]["n_rest"] == 200
    assert rep["adoption_test"]["adopt"] and rep["rule"] == "o3h-t"
    assert rep["o3h_t_tau"] == ml.percentile(spread(200, 0.55, 0.85), 5)
    assert rep["rule_tau"] == rep["o3h_t_tau"] and rep["o3h_tau"] == 0.4
    assert set(rep["reported_steps"]) == {"5.0", "20.0"}
    assert rep["per_species"]["1265"] == {"fates": 40, "under_terrain": 40,
                                          "under_terrain_only": 40}  # fmt: skip
    assert rep["per_species"]["1248"]["under_terrain_only"] == 2
    few = ml.terrain_report(rows[:200] + rows[200:225], alone=True, t_h=0.4)
    assert not few["adoption_test"]["adopt"] and few["rule"] == "o3h" and few["rule_tau"] == 0.4


def test_scored_rows_per_rule() -> None:
    rows = [
        {"gid": 1},
        {"gid": 2, "under": "terrain", "o3h_t": False},
        {"gid": 3, "under": "terrain", "o3h_t": True},
        {"gid": 4, "under": "model", "o3h_t": True},
    ]
    assert [r["gid"] for r in ml.scored_rows(rows, "o3h")] == [1, 2, 3, 4]
    assert [r["gid"] for r in ml.scored_rows(rows, "o3h-t")] == [1, 3, 4]
    plain = [{"gid": 1}, {"gid": 2}]  # a map without terrain: every row either way
    assert ml.scored_rows(plain, "o3h-t") == plain


class FakeOccl:
    def __init__(self, terrain: bool, gat_sha: str = "g" * 64) -> None:
        self.terrain = SimpleNamespace(step=10.0) if terrain else None
        self.files = {"m.rsm": "f" * 64}
        self.gat_sha = gat_sha

    def provenance(self) -> dict[str, Any]:
        out: dict[str, Any] = {"rsw_sha256": "r" * 64, "model_files_sha256": self.files}
        if self.terrain is not None:
            out["terrain"] = {"gat_sha256": self.gat_sha, "step": 10.0}
        return out


def freeze_args(tmp: Path, threshold: dict[str, Any]) -> SimpleNamespace:
    off = tmp / "offset.json"
    off.write_text(json.dumps({"offset_ms": 120.0, "parts": ["/x/xw1"]}))
    th = tmp / "threshold.json"
    th.write_text(json.dumps({"offset_ms": 120.0, "o3h_tau": 0.5, **threshold}))
    return SimpleNamespace(map="pay_fild07", threshold=th, offset=off, proposed=False,
                           decision=None, engaged=None, engaged_variant=None)  # fmt: skip


def test_freeze_takes_the_rule_and_t_h_the_fit_test_chose(monkeypatch: pytest.MonkeyPatch,
                                                         tmp_path: Path) -> None:  # fmt: skip
    """No switch: o3h and threshold's T_h, the file's keys as before. With it: the threshold
    file's 4f rule and its T_h (o3h-t's own set when adopted); a threshold file measured without
    terrain is refused."""
    import dataclasses

    monkeypatch.setattr(ml, "occluders", lambda spec: FakeOccl(spec.terrain))
    plain = ml.cmd_freeze(freeze_args(tmp_path, {}))
    assert plain["occlusion"] == "o3h" and plain["o3h_tau"] == 0.5
    assert "occlusion_chosen_by" not in plain and "terrain" not in plain["occluders"]
    monkeypatch.setitem(ml.MAPS, "pay_fild07", dataclasses.replace(ml.PAYF07, terrain=True))
    terr = {"terrain": {"rule": "o3h-t", "rule_tau": 0.55, "o3h_t_tau": 0.55}}
    got = ml.cmd_freeze(freeze_args(tmp_path, terr))
    assert got["occlusion"] == "o3h-t" and got["o3h_tau"] == 0.55
    assert got["occluders"]["terrain"]["gat_sha256"] == "g" * 64
    kept = ml.cmd_freeze(freeze_args(tmp_path, {"terrain": {"rule": "o3h", "rule_tau": 0.5}}))
    assert kept["occlusion"] == "o3h" and kept["o3h_tau"] == 0.5
    with pytest.raises(SystemExit, match="terrain"):
        ml.cmd_freeze(freeze_args(tmp_path, {}))


def test_frozen_occluders_check_the_gat_of_a_terrain_map(monkeypatch: pytest.MonkeyPatch) -> None:
    def params(prov: dict[str, Any]) -> dict[str, Any]:
        return {"occluders": prov}

    monkeypatch.setattr(ml, "occluders", lambda spec: FakeOccl(False))
    assert ml.frozen_occluders(params(FakeOccl(False).provenance()), ml.GEF10) is not None
    with pytest.raises(SystemExit, match="terrain"):  # o3h-t params on a map without the switch
        ml.frozen_occluders(params(FakeOccl(True).provenance()), ml.GEF10)
    monkeypatch.setattr(ml, "occluders", lambda spec: FakeOccl(True, "h" * 64))
    with pytest.raises(SystemExit, match="terrain"):
        ml.frozen_occluders(params(FakeOccl(True).provenance()), ml.GEF10)
    with pytest.raises(SystemExit, match="terrain"):  # frozen before the switch existed
        ml.frozen_occluders(params(FakeOccl(False).provenance()), ml.GEF10)


# --- the check's rows: both rules from one pass --------------------------------------------------


def check_job(monkeypatch: pytest.MonkeyPatch, terrain: bool, fits: dict[int, float],
              occlusion: str = "o3h") -> Any:  # fmt: skip
    """A fake session for orc_labels_fix._check_rows: gid 1 clear, gid 2 under a model, gids 3
    and 4 under terrain only (fit NCC ``fits``), the scoring stubbed (c1 0.5: never low)."""
    ents = {g: SimpleNamespace(gid=g, job=1265, x=10.0 + g, y=10.0, objtype=5, hidden=False)
            for g in (1, 2, 3, 4)}  # fmt: skip
    cand = {g: (ents[g], None, "sheet", SimpleNamespace(box=(100.0 * g, 0.0, 100.0 * g + 30, 60.0)),
                (0, "fix2:test")) for g in ents}  # fmt: skip
    world = SimpleNamespace(entities=list(ents.values()), self_pos=(5, 5))
    scene = SimpleNamespace(camera=SimpleNamespace(yaw=0.0))

    def standing(sess: Any, tw: int, anchors: Any, occl: Any, dropped: Any, rule: Any,
                 under: Any) -> Any:  # fmt: skip
        under.extend([cand[2], cand[3], cand[4]] if terrain else [cand[2]])
        return world, scene, {}, [cand[1]]

    occl = SimpleNamespace(terrain=SimpleNamespace(step=10.0) if terrain else None,
                           hit=lambda scene, box: 7 if box[0] == 200.0 else None)  # fmt: skip
    monkeypatch.setattr(olf, "standing_candidates", standing)
    monkeypatch.setattr(olf.label_check, "score", lambda bgr, sheet, pred: 0.5)
    monkeypatch.setattr(olf.occ, "best_offset", lambda *a, **k: None)
    monkeypatch.setattr(olf, "predict", lambda *a, **k: None)
    monkeypatch.setattr(olf, "fit_label", lambda grey, valid, sheet, pred, r:
                        (fits[int(pred.box[0] // 100)], 0, 0, 0))  # fmt: skip
    tl = SimpleNamespace(frame_world=lambda t: SimpleNamespace(self_pos=(5, 5)))
    lab = SimpleNamespace(timeline=tl, size=(1280, 720), ui_rects=())
    sess = SimpleNamespace(layout_ok=lambda bgr: True, lab=lab)
    olf._JOB.clear()
    olf._JOB.update(sess=sess, occluders=occl, offset_ms=120.0, anchors={}, facing_rule=None,
                    occlusion=occlusion, tau=0.092, o3h_tau=0.6,
                    reader=lambda ref: np.zeros((720, 1280, 3), np.uint8))  # fmt: skip
    return SimpleNamespace(frame_id=5, t_mono_ns=10 * 1_000_000_000)


def test_the_check_scores_both_rules_from_one_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """With terrain: the label under terrain whose fit passes T_h is scored by both rules; the
    one below it is scored by o3h only (``o3h_t`` False); the model's label is o3h's either way.
    Without terrain (every map today): the rows carry no new key, the counters are o3h's."""
    fits = {2: 0.7, 3: 0.7, 4: 0.5}
    ref = check_job(monkeypatch, True, fits)
    rows, dropped, _ = olf._check_rows(ref)
    got = {r["gid"]: (r["under"], r["o3h_t"]) for r in rows}
    assert got == {1: (None, True), 2: ("model", True), 3: ("terrain", True), 4: ("terrain", False)}
    assert dropped["under_terrain_kept"] == 1 and dropped["occluded_terrain:1265"] == 1
    assert dropped["under_model_kept"] == 1 and "occluded_model" not in dropped
    assert [r["gid"] for r in ml.scored_rows(rows, "o3h-t")] == [1, 2, 3]
    ref = check_job(monkeypatch, True, fits, occlusion="o3h-t")  # the frozen o3h-t: the same rows
    assert olf._check_rows(ref)[0] == rows
    ref = check_job(monkeypatch, False, {2: 0.5})
    rows, dropped, _ = olf._check_rows(ref)
    assert [r["gid"] for r in rows] == [1] and not {"under", "o3h_t"} & set(rows[0])
    assert dropped == Counter({"occluded_model": 1, "occluded_model:1265": 1,
                               "frame_with_standing": 1})  # fmt: skip
    olf._JOB.clear()


# --- the REAL map: xmas_dun02's client GAT (in /dev/shm at run time) --------------------------

XMAS_GAT = cm.GAT_DIR / "xmas_dun02.gat"


def test_real_xmas_dun02_blocks_hide_the_floor_behind_them() -> None:
    """The client GAT (the plan's: 260 x 260, sha256 4cf9265fcce2fec4...). Cells are picked from
    it, never listed here: (a) every walkable FLOOR cell (altitude < 10) with a NON-walkable
    cell rising >= 20 one or two cells SOUTH in its own column (the near face of a block: its
    top projects above the label's feet at the 45-degree camera) is under terrain for a
    Cookie-sized box; (b) a walkable floor cell with such a block one or two cells NORTH and no
    cell rising >= 5 in the window south of it is not; (c) the window finds exactly the rise of a
    whole-map scan on a sample of every walkable cell."""
    if not XMAS_GAT.exists():
        pytest.skip("xmas_dun02's client GAT is not extracted here")
    import hashlib

    raw = XMAS_GAT.read_bytes()
    assert hashlib.sha256(raw).hexdigest().startswith("4cf9265fcce2fec4")
    g = olf._cached_gat(gatmod.parse(raw))
    t = olf.TerrainOccluders(XMAS_GAT)
    full = olf.TerrainOccluders(XMAS_GAT, south=260, side=260)
    a, w = t.alt, g.walkable()
    assert CAM is not None

    def rise(x: int, y: int, occl: olf.TerrainOccluders = t) -> float | None:
        scene = rd.Scene(CAM, (float(x), float(y)), g)
        return occl.rise(scene, box_at(scene, (float(x), float(y))), (x, y))

    rng = np.random.default_rng(4)
    floor = w & (a < 10)
    south = np.zeros_like(w)
    north = np.zeros_like(w)
    for d in (1, 2):
        block = (~w) & (a >= 20)
        south[d:, :] |= block[:-d, :] & (a[:-d, :] - a[d:, :] >= 20)
        north[:-d, :] |= block[d:, :] & (a[d:, :] - a[:-d, :] >= 20)
    picks = np.argwhere(floor & south)
    assert len(picks) > 500
    for y, x in picks[rng.choice(len(picks), 150, replace=False)]:
        r = rise(int(x), int(y))
        assert r is not None and r >= 20, (int(x), int(y), r)
    quiet = []
    for y, x in np.argwhere(floor & north & ~south):
        y0 = max(0, y - t.south)
        win = a[y0:y, max(0, x - t.side) : x + t.side + 1]
        if win.size and (win - a[y, x]).max() < 5:
            quiet.append((int(x), int(y)))
    assert len(quiet) >= 20
    for x, y in quiet[:: max(1, len(quiet) // 60)]:
        assert rise(x, y) is None
    cells = np.argwhere(w)
    sample = cells[rng.choice(len(cells), 120, replace=False)]
    got = [(rise(int(x), int(y)), rise(int(x), int(y), full)) for y, x in sample]
    assert all(a_ == b_ for a_, b_ in got)
    assert sum(r is not None for r, _ in got) > 10  # the sample does meet terrain
