"""The floor-item tools at 1920 x 1080 (scripts/fi_labels.py; docs/planning/xmas02-items-1080.md,
tools T-I1, T-I2, T-I4): the 1080 spec, its fit (fit-1080) and freeze (freeze-1080), round 6's
pack -- on SYNTHETIC data only (no client pixel, no packet capture, no 1080 item data exists
yet). The 720 spec's own behaviour is pinned by test_fi_labels.py, unchanged."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import fi_labels as fl  # noqa: E402
import gef10_items as gi  # noqa: E402
import item_labels as il  # noqa: E402
import map_labels as ml  # noqa: E402
import rec_paths  # noqa: E402

from poring_dataset.render import SpritePrediction  # noqa: E402

S = 1_000_000_000
SIZE = (1280, 720)
SPEC = fl.XMAS02_FI_1080
FIT = "20261120T214246-rdp-xmas02-ifF"
TRAIN = "20261121T010000-rdp-xmas02-ifT1"
STAGING = "20261121T030000-rdp-xmas02-ifs1"
HELD = ("20261121T050000-rdp-xmas02-ifH1", "20261121T060000-rdp-xmas02-ifH2",
        "20261121T070000-rdp-xmas02-ifsH1",
        # Amendment 16's one extension
        "20261121T100000-rdp-xmas02-ifsH2", "20261121T101000-rdp-xmas02-ifH3",
        "20261121T103000-rdp-xmas02-ifH4")  # fmt: skip
# Amendment 22: round 7's NEW held-out (refused for TRAIN by name like round 6's)
HELD7 = ("20261122T010000-rdp-xmas02-ifH5", "20261122T020000-rdp-xmas02-ifH10",
         "20261122T030000-rdp-xmas02-ifsH3", "20261122T040000-rdp-xmas02-ifsH4")  # fmt: skip
LAB_720 = {"backend": "rdp", "game_region": [80, 77, 1280, 720], "server": "lab-rathena",
           "format": "png", "recorder_version": 8}  # fmt: skip
VIRTUAL = {"backend": "rdp", "game_region": [rec_paths.VIRTUAL_X0, 0, 1280, 720],
           "server": "lab-rathena", "format": "png", "recorder_version": 8,
           "client_view": {"rect": [0, 0, 1920, 1080], "mode": "fullscreen", "world_scale": 1.5,
                           "world_centre": [960.0, 540.0], "panels": []}}  # fmt: skip


# --- T-I1: the spec and its roles --------------------------------------------------------------


def test_the_1080_spec_reads_every_pixel_constant_from_its_params() -> None:
    """T-I1: the 1080 monster params (9c73278f), FIT ifF, the held-out by name, no pixel constant
    of its own (they come from items-params-1080.json), the 720 spec untouched."""
    assert (SPEC.anchor_px, SPEC.scale, SPEC.r_label, SPEC.t_item, SPEC.bar) == (None,) * 5
    assert SPEC.monster_params == Path("/dev/shm/poring-lab-tmp/x1080/fit/params-1080.json")
    assert SPEC.monster_params_sha256.startswith("9c73278f8c1aca1f")
    assert SPEC.params == Path("/dev/shm/poring-lab-tmp/i1080/items-params-1080.json")
    assert SPEC.val_suffixes == ("-xmas02-ifF",) == SPEC.absent_suffixes
    assert SPEC.eval_suffixes == (
        "-xmas02-ifH1",
        "-xmas02-ifH2",
        "-xmas02-ifsH1",
        "-xmas02-ifH3",
        "-xmas02-ifH4",
        "-xmas02-ifsH2",
        *fl.R7_HELD_OUT,
    )  # Amendment 16; + round 7's new held-out (Amendment 22)
    assert (SPEC.screen, SPEC.world_scale) == ("1080", rec_paths.VIEW_1080["world_scale"]) == \
        ("1080", 1.5)  # fmt: skip
    assert SPEC.rule == fl.RULE_1080 == "xmas02-fi-1-1080" and fl.RULE == "xmas02-fi-1"
    assert SPEC.mspec is ml.XMAS02 and SPEC.name == "xmas_dun02"
    assert (SPEC.pack_seed, SPEC.eval_seed, SPEC.salt) == (71, None, "xmas02-fi")
    assert (SPEC.sprites, SPEC.resnames) == (fl.XMAS02_FI.sprites, fl.XMAS02_FI.resnames)
    assert SPEC.drop_species == fl.XMAS02_FI.drop_species and SPEC.params_v2 is None
    old = fl.XMAS02_FI  # the 720 spec: its own constants and the new fields' 720 defaults
    assert (old.screen, old.world_scale, old.work) == ("720", 1.0, fl.FI)
    assert old.anchor_px == (-4.0, 2.0) and old.t_item == 0.65 and old.eval_seed == 63
    assert fl.FI_MAPS["xmas_dun02"] is old  # freeze / freeze-v2's key: the 720 rule
    assert fl.FI_SPECS[("xmas_dun02", "1080")] is SPEC
    assert fl.MAP_NAMES == ["xmas_dun02"]  # --map takes map names only


def test_the_cache_tells_the_two_rules_apart_and_refuses_both_rules_held_out() -> None:
    """build_frame_cache (T-I3) finds a params file's rule among FI_MAPS' values by its map and
    rule NAME (each screen's rule has its own), then by its monster_params_sha256; and refuses
    as TRAIN any session that SOME rule of the map refuses as TRAIN by name (role_refusal)."""
    rules = [s for s in fl.FI_MAPS.values() if s.name == "xmas_dun02"]
    assert rules == [fl.XMAS02_FI, SPEC] and [s.rule for s in rules] == [fl.RULE, fl.RULE_1080]
    shas = {s.monster_params_sha256[:8] for s in rules}
    assert shas == {"d4cc0a5d", "9c73278f"}  # what freeze_params / freeze-1080 record

    def train_refused(sid: str) -> bool:
        return any(fl.role_refusal(s, sid, "train", False) is not None for s in rules)

    for sid in (FIT, *HELD, "20261112T090000-rdp-hunt-xmas02-fiH1",
                "20261109T082234-rdp-hunt-xmas02-p31"):  # fmt: skip
        assert train_refused(sid), sid
    for sid in (TRAIN, STAGING, "20261109T133046-rdp-hunt-xmas02-p38",
                "20261110T211700-rdp-xmas02-fs2"):  # fmt: skip
        assert not train_refused(sid), sid
    # and each rule's FIT is VAL under its own rule only
    assert fl.role_refusal(SPEC, FIT, "val", False) is None
    assert fl.role_refusal(fl.XMAS02_FI, FIT, "val", False) is not None


@pytest.mark.parametrize("sid", [*HELD, *HELD7, "20261106T162044-rdp-xmas02-xw5",
                                 "20261120T090000-rdp-xmas02-v1T",
                                 "20261112T090000-rdp-hunt-xmas02-fiH1"])  # fmt: skip
def test_1080_held_out_test_and_the_720_held_out_are_refused_for_train_and_val(sid: str) -> None:
    for split in ("train", "val"):
        assert SPEC and fl.role_refusal(SPEC, sid, split, False) is not None


def test_1080_fit_is_val_only_and_val_is_ifF_only() -> None:
    assert fl.role_refusal(SPEC, FIT, "val", False) is None
    assert "FIT (ifF) is VAL only" in str(fl.role_refusal(SPEC, FIT, "train", False))
    for sid in (TRAIN, STAGING):
        assert fl.role_refusal(SPEC, sid, "train", False) is None
        assert "FIT only" in str(fl.role_refusal(SPEC, sid, "val", False))
    p31 = "20261109T082234-rdp-hunt-xmas02-p31"  # the 720 FIT is not the 1080 VAL
    assert "FIT only" in str(fl.role_refusal(SPEC, p31, "val", False))
    for sid in HELD:  # the held-out, read only by --eval-test
        assert "ifH1 / ifH2 / ifsH1" in str(fl.role_refusal(SPEC, sid, "train", False))
        assert fl.role_refusal(SPEC, sid, None, True) is None
    for sid in (FIT, TRAIN, "20261112T090000-rdp-hunt-xmas02-fiH1"):
        assert fl.role_refusal(SPEC, sid, None, True) is not None


def test_the_720_spec_refuses_the_1080_held_out_by_name(tmp_path: Path) -> None:
    """A 1080 held-out under the 720 spec (any role) is refused by NAME before anything is read
    (foreign_refusal, in the label pass); role_refusal stays each spec's own roles (the frame
    cache asks both rules), the 720 spec's own names keep their old reasons (test_fi_labels.py)."""
    old = fl.XMAS02_FI
    for sid in HELD:
        assert "1080 floor items' held-out" in str(fl.foreign_refusal(old, sid))
        assert fl.foreign_refusal(SPEC, sid) is None
        assert fl.role_refusal(old, sid, "train", False) is None  # not the 720 rule's role
        assert fl.role_refusal(old, sid, None, True) is not None
        with pytest.raises(SystemExit, match="1080 floor items' held-out.*refused"):
            fl.main(["label", str(tmp_path / sid), "--split", "train", "--params",
                     str(tmp_path / "no-params.json"),
                     "--out", str(tmp_path / "o.json")])  # fmt: skip
    fsh1 = "20261112T110000-rdp-xmas02-fsH1"
    assert "720 floor items' held-out" in str(fl.foreign_refusal(SPEC, fsh1))
    assert "TEST" in str(fl.role_refusal(SPEC, fsh1, "train", False))  # the map's TEST names it
    for sid in (FIT, TRAIN, "20261109T133046-rdp-hunt-xmas02-p38"):
        assert fl.foreign_refusal(old, sid) is None and fl.foreign_refusal(SPEC, sid) is None


def test_label_spec_1080_refuses_by_name_before_reading(tmp_path: Path) -> None:
    missing = tmp_path / "no-params.json"  # never opened: the NAME decides first
    for name, split in ((HELD[0], "train"), (HELD[2], "val"), (FIT, "train"), (TRAIN, "val")):
        with pytest.raises(SystemExit, match="refused"):
            fl.main(["label", str(tmp_path / name), "--spec", "1080", "--split", split,
                     "--params", str(missing), "--out", str(tmp_path / "o.json")])  # fmt: skip


def test_screen_refusal_keeps_each_spec_on_its_own_screen() -> None:
    assert rec_paths.path_of(LAB_720) == "lab-720" and rec_paths.path_of(VIRTUAL) == "virtual-1080"
    assert fl.screen_refusal(fl.XMAS02_FI, LAB_720) is None
    assert "labels lab-720 only" in str(fl.screen_refusal(fl.XMAS02_FI, VIRTUAL))
    assert fl.screen_refusal(SPEC, VIRTUAL) is None
    assert "labels virtual-1080 only" in str(fl.screen_refusal(SPEC, LAB_720))
    other = dataclasses.replace(SPEC, world_scale=1.25)  # a 900p spec would not read 1080 frames
    assert "world scale 1.5" in str(fl.screen_refusal(other, VIRTUAL))


def test_load_params_keeps_the_screens_apart(tmp_path: Path) -> None:
    """Two guards: the rule's name and the file's screen."""
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"rule": fl.RULE, "map": "xmas_dun02", "status": "FROZEN"}))
    assert fl.load_params(p, fl.XMAS02_FI)["status"] == "FROZEN"  # a 720 file: no "screen"
    with pytest.raises(SystemExit, match="not xmas02-fi-1-1080 params"):
        fl.load_params(p, SPEC)
    assert fl.spec_for_params(json.loads(p.read_text())) is fl.XMAS02_FI
    p.write_text(json.dumps({"rule": fl.RULE_1080, "map": "xmas_dun02", "status": "FROZEN"}))
    with pytest.raises(SystemExit, match="720 params, not the 1080"):  # no "screen"
        fl.load_params(p, SPEC)
    p.write_text(json.dumps({"rule": fl.RULE, "map": "xmas_dun02", "status": "FROZEN",
                             "screen": "1080"}))  # fmt: skip
    with pytest.raises(SystemExit, match="1080 params, not the 720"):
        fl.load_params(p, fl.XMAS02_FI)
    p.write_text(json.dumps({"rule": fl.RULE_1080, "map": "xmas_dun02", "status": "FROZEN",
                             "screen": "1080"}))  # fmt: skip
    assert fl.load_params(p, SPEC)["screen"] == "1080"
    with pytest.raises(SystemExit, match="not xmas02-fi-1 params"):
        fl.load_params(p, fl.XMAS02_FI)
    assert fl.spec_for_params(json.loads(p.read_text())) is SPEC
    with pytest.raises(SystemExit, match="no floor-item rule"):
        fl.spec_for_params({"map": "xmas_dun02", "screen": "900"})


# --- the pixel constants: the rule and their readers --------------------------------------------


def test_constants_1080_scale_the_native_bar_only() -> None:
    """The bar is native-size: the 720 FIT bar's size / 1.5, about its own centre (BAR_ABOUT_1080,
    Amendment 3: the measured place) or about her foot point (the first guess); her body, the
    search, the margin and the unit box are world-size: unchanged. At world scale 1.0 the rule IS
    720."""
    assert fl.BAR_ABOUT_1080 == "centre"
    c = fl.constants_1080(1.5)
    assert c["bar_about"] == "centre" and c["bar_px"] == c["bar_px_by_about"]["centre"]
    feet = fl.constants_1080(1.5, "feet")["bar_px"]
    assert feet == [round(-31 / 1.5, 4), round(10 / 1.5, 4), round(28 / 1.5, 4), 12.0]
    assert c["bar_720_px"] == [-31.0, 10.0, 28.0, 18.0]
    centre = c["bar_px_by_about"]["centre"]  # (-1.5, 14) +- (29.5, 4) / 1.5
    assert centre == [round(-1.5 - 29.5 / 1.5, 4), round(14 - 4 / 1.5, 4),
                      round(-1.5 + 29.5 / 1.5, 4), round(14 + 4 / 1.5, 4)]  # fmt: skip
    for box in (feet, centre):
        width, height = box[2] - box[0], box[3] - box[1]
        assert abs(width - 59 / 1.5) < 1e-3 and abs(height - 8 / 1.5) < 1e-3
    assert fl.constants_1080(1.5, "centre")["bar_px"] == centre == c["bar_px"]
    assert "its centre" in fl.constants_1080(1.5, "centre")["rule"]["bar_px"]
    assert "about its centre" in c["rule"]["bar_px"]
    with pytest.raises(SystemExit, match="feet or centre"):
        fl.constants_1080(1.5, "top")
    assert c["self_box"] == {"w": 34.0, "h": 74.0, "pad": 4.0}
    assert (c["r_label"], c["margin_px"], c["unit_box"]) == (10, 30.0, list(gi.UNIT_BOX))
    for about in ("feet", "centre"):
        assert fl.constants_1080(1.0, about)["bar_px"] == [-31.0, 10.0, 28.0, 18.0]
    assert set(c["rule"]) == {"bar_px", "self_box", "r_label", "margin_px", "unit_box"}


def test_the_self_box_and_margin_come_from_a_1080_params_file_only() -> None:
    me = (640.0, 420.0)
    v720 = {"self_box": {"w": 34.0, "h": 74.0, "pad": 4.0}, "g2": {"margin_px": 30.0}}
    assert fl.self_box_of(v720, me) == gi.self_box(me) and fl.margin_of(v720) == fl.MARGIN_PX
    odd = {"self_box": {"w": 99.0, "h": 9.0, "pad": 0.0}, "g2": {"margin_px": 5.0}}
    assert fl.self_box_of(odd, me) == gi.self_box(me)  # no "screen": the 720 path, as before
    assert fl.margin_of(odd) == fl.MARGIN_PX
    p1080 = {**odd, "screen": "1080"}
    assert fl.self_box_of(p1080, me) == (640.0 - 49.5, 411.0, 640.0 + 49.5, 420.0)
    assert fl.margin_of(p1080) == 5.0
    with pytest.raises(KeyError):  # a 1080 file without its own box fails closed
        fl.self_box_of({"screen": "1080"}, me)


def test_frame_reasons_and_g2_clear_defaults_are_the_720_boxes() -> None:
    me, b = (640.0, 420.0), (620.0, 420.0, 632.0, 434.0)
    preds = {1: b}
    args = (preds, ["on"], me, [], SIZE, [], fl.XMAS02_FI.bar, 0.5)
    assert fl.frame_reasons(*args) == fl.frame_reasons(*args, gi.self_box(me))
    assert fl.frame_reasons(*args)[0] == ["under_self", "under_bar"]
    far = (100.0, 100.0, 140.0, 140.0)  # a self box away from the item: under_bar alone
    assert fl.frame_reasons(*args, far)[0] == ["under_bar"]
    clear = (500.0, 300.0, 512.0, 312.0)
    bar = fl.XMAS02_FI.bar
    assert bar is not None
    assert fl.g2_clear(clear, me, [], [], SIZE, [], bar, None)
    assert not fl.g2_clear(clear, me, [], [], SIZE, [], bar, None, margin=301.0)
    assert not fl.g2_clear(clear, me, [], [], SIZE, [], bar, None, selfb=(490.0, 290.0, 520.0,
                                                                          320.0))  # fmt: skip


class _Fake:
    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


PRED = SpritePrediction((494.0, 294.0, 505.0, 306.0), (500.0, 300.0), 1.0, 1.0, 0, 0, 0, 0, True,
                        "opaque")  # fmt: skip


def _harness(monkeypatch: pytest.MonkeyPatch, prm: dict[str, Any], *, items: bool = True,
             reads: list[int] | None = None) -> _Fake:  # fmt: skip
    """_label_frame's job on ONE frame with one floor item ON the floor (or none), with fakes for
    the session, the camera and the fit (colour_fit answers from the prediction's scale)."""
    t = 100 * S
    floor = il.Floor(5, 911, 60, 70, 6, 6, "fall", t - 10 * S, t + 30 * S, True)
    world = _Fake(self_pos=(57.0, 70.0), entities=[])
    scene = _Fake(player=(57.0, 70.0))
    sess = _Fake(lab=_Fake(timeline=_Fake(frame_world=lambda tw: world), size=SIZE, ui_rects=()),
                 scene=lambda w: scene, layout_ok=lambda bgr: True)  # fmt: skip
    sheet = object()

    class Sheets:
        def __call__(self, iid: int) -> Any:
            return sheet

        def any(self, iid: int) -> Any:
            return sheet

    def project(sc: Any, cell: Any) -> tuple[tuple[float, float], float]:
        return ((640.0, 420.0) if tuple(cell) == sc.player else (500.0, 300.0)), 1.0

    def read(ref: Any) -> np.ndarray:
        if reads is not None:
            reads.append(int(ref.frame_id))
        return np.zeros((720, 1280, 3), np.uint8)

    def fit(bgr: Any, valid: Any, sh: Any, p: SpritePrediction, r: int) -> tuple[float, int, int]:
        # the best NCC at scale 1.05, the offset moving with the scale; at +-r = the edge
        return round(0.9 - abs(p.scale - 1.05), 4), int(round((p.scale - 1.0) * 40)), -1

    monkeypatch.setattr(fl, "anchor_and_depth", project)
    monkeypatch.setattr(
        fl, "_predict", lambda sh, cell, sc, prm: dataclasses.replace(PRED, scale=prm["scale"])
    )
    monkeypatch.setattr(fl, "_units", lambda *a: [])
    monkeypatch.setattr(fl, "colour_fit", fit)
    monkeypatch.setattr(ml, "read_png", read)
    job = {
        "sess": sess,
        "floors": [floor] if items else [],
        "sheets": Sheets(),
        "occluders": _Fake(under=lambda *a: None),
        "params": prm,
        "eval_test": False,
    }
    monkeypatch.setattr(fl.olf, "_JOB", job)
    return _Fake(ref=_Fake(frame_id=7, t_mono_ns=t, shard=Path("shard-000000.tar"), offset=0,
                           size=1), job=job)  # fmt: skip


def _prm1080(**kw: Any) -> dict[str, Any]:
    c = fl.constants_1080(1.5)
    base = fl.fit_base_params(SPEC, c, 120.0)
    return {**base, "scale": 1.0, "anchor_px": [0.0, 0.0], "r_label": 10, "t_item": 0.65, **kw}


def test_the_1080_label_frame_uses_its_params_self_box_and_margin(
        monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    h = _harness(monkeypatch, _prm1080())
    row = fl._label_frame(h.ref)  # type: ignore[arg-type]
    assert row["status"] == "keep" and row["items"][0]["g2_clear"] is True
    h = _harness(monkeypatch, _prm1080(self_box={"w": 400.0, "h": 200.0, "pad": 0.0}))
    row = fl._label_frame(h.ref)  # type: ignore[arg-type]
    assert row["reasons"] == ["under_self"] and row["items"][0]["g2_clear"] is False
    h = _harness(monkeypatch, _prm1080(g2={"margin_px": 300.0}))
    row = fl._label_frame(h.ref)  # type: ignore[arg-type]
    assert row["status"] == "keep" and row["items"][0]["g2_clear"] is False  # margin: G2 only
    prm720 = {k: v for k, v in _prm1080(self_box={"w": 400.0, "h": 200.0, "pad": 0.0}).items()
              if k != "screen"}  # fmt: skip
    h = _harness(monkeypatch, prm720)  # no "screen": the 720 box, whatever the file says
    assert fl._label_frame(h.ref)["status"] == "keep"  # type: ignore[arg-type]
    reads: list[int] = []
    h = _harness(monkeypatch, _prm1080(), reads=reads)
    fl._label_frame(h.ref, np.zeros((720, 1280, 3), np.uint8))  # type: ignore[arg-type]
    assert reads == []  # a frame passed in is not read again


# --- T-I2: fit-1080 ----------------------------------------------------------------------------


def test_fit_frame_reads_once_and_runs_the_label_rule_at_every_scale(
        monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    base = _prm1080(t_item=-1.0)
    grid = {s: {**base, "scale": s, "anchor_px": [0.0, 0.0], "r_label": 10}
            for s in fl.FIT_SCALES_1080}  # fmt: skip
    reads: list[int] = []
    h = _harness(monkeypatch, grid[1.0], reads=reads)
    h.job["fit_params"] = grid
    calls: list[float] = []
    orig = fl._label_frame

    def counted(ref: Any, bgr: Any = None) -> dict[str, Any]:
        calls.append(float(fl.olf._JOB["params"]["scale"]))
        return orig(ref, bgr)

    monkeypatch.setattr(fl, "_label_frame", counted)
    out = fl._fit_frame(h.ref)  # type: ignore[arg-type]
    assert reads == [7] and calls == list(fl.FIT_SCALES_1080)
    assert sorted(out["fits"]) == [f"{s:.2f}" for s in fl.FIT_SCALES_1080]
    at = {k: v[0] for k, v in out["fits"].items()}
    assert at["1.05"]["ncc"] == 0.9 and at["1.05"]["dx"] == 2 and not at["1.05"]["edge"]
    assert at["0.85"]["dx"] == -6 and at["1.15"]["edge"] is False
    assert all(v["g2_clear"] for v in at.values())
    reads.clear()
    calls.clear()
    h = _harness(monkeypatch, grid[1.0], items=False, reads=reads)
    h.job["fit_params"] = grid
    monkeypatch.setattr(fl, "_label_frame", counted)
    out = fl._fit_frame(h.ref)  # type: ignore[arg-type]
    assert out == {"frame_id": 7, "n_near": 0, "fits": {}} and len(calls) == 1 and reads == [7]


def _view(fid: int, ncc: float, dx: int, dy: int, *, clear: bool = True, edge: bool = False,
          floor: int | None = None) -> dict[str, Any]:  # fmt: skip
    return {"frame_id": fid, "floor_id": fid % 9 if floor is None else floor, "item_id": 911,
            "ncc": ncc, "dx": dx, "dy": dy, "g2_clear": clear, "edge": edge}  # fmt: skip


def test_fit_constants_picks_the_best_scale_then_the_anchor() -> None:
    """The scale with the highest median NCC over the views clear at EVERY scale; the anchor =
    the median (dx, dy) of its clear views, the edge fits left out; NOT_ENOUGH under 30."""
    per: dict[float, list[dict[str, Any]]] = {}
    for s in fl.FIT_SCALES_1080:
        rows = [_view(i, round(0.9 - abs(s - 1.05) + (i % 3) * 0.01, 4), -3 + i % 3, 1)
                for i in range(40)]  # fmt: skip
        rows.append(_view(100, 0.99, 0, 0, clear=s == 1.05))  # clear at one scale only
        rows += [_view(200 + i, 0.5, 10, 0, edge=True, clear=s != 0.85) for i in range(5)]
        rows.append(_view(300, 0.99, 0, 0, clear=False))  # never clear: not a view of the fit
        per[s] = rows
    got = fl.fit_constants(per)
    assert got["verdict"] == "READY" and got["best_scale"] == 1.05
    assert got["common_views"] == 40  # 41 clear at 1.05, the 5 edge ones not clear at 0.85
    assert got["anchor"]["dx"] == -2.0 and got["anchor"]["dy"] == 1.0
    assert got["anchor"]["n"] == 41 and got["anchor"]["edge_left_out"] == 5
    assert got["scales"]["1.05"]["median_ncc_common"] == 0.91
    tie = {0.95: [_view(i, 0.8, 0, 0) for i in range(30)],
           1.05: [_view(i, 0.8, 1, 1) for i in range(30)]}  # fmt: skip
    assert fl.fit_constants(tie)["best_scale"] == 0.95  # equally near 1.0: the smaller
    tie[1.0] = [_view(i, 0.8, 2, 2) for i in range(30)]
    assert fl.fit_constants(tie)["best_scale"] == 1.0  # nearer 1.0
    short = {s: v[:29] for s, v in tie.items()}
    assert fl.fit_constants(short)["verdict"] == "NOT_ENOUGH"
    assert fl.fit_constants({1.0: []})["verdict"] == "NOT_ENOUGH"
    edges = {1.0: [_view(i, 0.8, 10, 0, edge=True) for i in range(40)]}
    assert fl.fit_constants(edges)["anchor"] is None  # every fit at the edge: no anchor


def test_absent_rates_weight_each_sprite_by_its_views_and_t_item_is_the_720_rule() -> None:
    """T_item = the smallest 0.05 step whose absent pass rate <= 0.5 %, the rate of the 720
    study's own-sprite control (each sprite's rate weighted by its share of FIT's clear views):
    a bare-floor sprite nobody saw on FIT (7269-like) moves rate_all, not T_item."""
    groups = {911: [911], 4206: [4206, 4235], 7269: [7269]}
    weights = fl.view_weights([911] * 90 + [4235] * 10 + [12345] * 5, groups)
    assert weights == {911: 0.9, 4206: 0.1}  # 4235 counts for its sprite 4206; 12345: none
    fits = {
        911: [0.40] * 398 + [0.61, 0.66],  # 911: 1 in 400 >= 0.65, 0 >= 0.70
        4206: [0.30] * 399 + [0.72],  # 4206: 1 in 400 >= 0.70, 0 >= 0.75
        7269: [0.87] * 300 + [0.2] * 100,
    }  # bare floor: 75 % >= 0.85
    rows = fl.absent_rates(fits, weights)
    by = {r["t"]: r for r in rows}
    assert [r["t"] for r in rows] == list(fl.T_GRID) and fl.T_GRID[0] == 0.05
    assert by[0.65]["rate_views"] == round(0.9 * 1 / 400 + 0.1 * 1 / 400, 5)
    assert by[0.6]["rate_views"] == round(0.9 * 2 / 400 + 0.1 * 1 / 400, 5)  # 0.0049: meets
    assert by[0.55]["meets_rule"] is True and by[0.5]["meets_rule"] is True  # 0.0048 <= 0.005
    assert by[0.45]["meets_rule"] is True and by[0.4]["meets_rule"] is False  # 911's 398 at 0.40
    assert by[0.85]["rate_all"] == round(300 / 1200, 5)  # pooled: the bare-floor sprite
    assert fl.t_item_of(rows) == 0.45
    assert fl.t_item_of(fl.absent_rates({1: [0.99] * 10}, {1: 1.0})) == 1.0
    assert fl.t_item_of(fl.absent_rates({1: [1.0] * 10}, {1: 1.0})) is None
    assert fl.absent_rates(fits, {})[0]["rate_views"] is None  # no views: no rule
    seen_only = fl.absent_rates({911: [0.1] * 10}, {911: 0.5, 4206: 0.5})  # 4206: no fit
    assert seen_only[0]["rate_views"] == 1.0  # renormalised over the sprites with fits


def test_bar_pixels_and_the_bar_check() -> None:
    """The check counts the bar-coloured pixels inside each candidate box: a bar drawn where the
    "centre" rule puts it (the 720 place, the 1080 size) lies mostly outside the "feet" box."""
    me = (640.0, 420.0)
    boxes = fl.constants_1080(1.5)["bar_px_by_about"]
    mask = np.zeros((24, 75), bool)  # the window's pixels (origin = its top-left)
    origin = (601, 422)  # me + (-39, +2)
    # a bar at the "feet" box: x -20 .. +18, y +7 .. +12 from her foot point
    mask[7 - 2 : 12 - 2, -20 + 39 : 18 + 39] = True
    got = fl.bar_pixels(mask, origin, me, boxes)
    assert got["n"] == 5 * 38 and got["bbox"] == [-20.0, 7.0, 18.0, 12.0]
    assert got["inside"]["feet"] == got["n"] and got["inside"]["centre"] < got["n"] / 2
    low = np.zeros((24, 75), bool)  # a bar at the 720 place, 1080 size: x -20 .. +18, y 12 .. 16
    low[12 - 2 : 16 - 2, -20 + 39 : 18 + 39] = True
    at_centre = fl.bar_pixels(low, origin, me, boxes)
    assert at_centre["inside"]["centre"] == at_centre["n"]
    assert at_centre["inside"]["feet"] < at_centre["n"] / 2
    assert fl.bar_pixels(np.zeros((3, 3), bool), origin, me, boxes) == {
        "n": 0, "bbox": None, "inside": {"feet": 0, "centre": 0}}  # fmt: skip
    few = {"n": 3, "bbox": [0, 0, 1, 1], "inside": {"feet": 0, "centre": 0}}
    chk = fl.bar_check([got, got, None, few], boxes, "feet", [-31.0, 10.0, 28.0, 18.0])
    assert chk["available"] and chk["frames_read"] == 3 and chk["frames_with_bar"] == 2
    assert chk["median_bbox_px"] == [-20.0, 7.0, 18.0, 12.0] and chk["rule_about"] == "feet"
    assert chk["share_inside"]["feet"] == 1.0 and chk["median_bbox_inside_rule_box"] is True
    assert "_bar_mask" in chk["reader"] and chk["rule_bar_px"] == boxes["feet"]
    bad = fl.bar_check([at_centre] * 3, boxes, "feet", [-31.0, 10.0, 28.0, 18.0])
    assert bad["median_bbox_inside_rule_box"] is False and bad["share_inside"]["centre"] == 1.0
    assert (
        fl.bar_check([at_centre] * 3, boxes, "centre", [-31.0, 10.0, 28.0, 18.0])[
            "median_bbox_inside_rule_box"
        ]
        is True
    )
    none = fl.bar_check([None], boxes, "feet", [-31.0, 10.0, 28.0, 18.0])
    assert none["frames_with_bar"] == 0 and none["median_bbox_px"] is None


def test_the_repos_bar_reader_reads_her_bar_colours() -> None:
    """route_preview._bar_mask (the reader the check uses): the green HP and blue SP rows."""
    import route_preview as rp

    img = np.full((4, 3, 3), (86, 125, 202), np.uint8)  # the orange floor (BGR)
    img[0, :] = (40, 200, 40)  # green HP
    img[1, :] = (220, 60, 40)  # blue SP
    m = rp._bar_mask(img)
    assert m[0].all() and m[1].all() and not m[2:].any()


def test_fit_1080_refuses_by_name_and_inside_the_repo_before_reading(tmp_path: Path) -> None:
    for name in (TRAIN, HELD[0], "20261109T082234-rdp-hunt-xmas02-p31"):
        with pytest.raises(SystemExit, match="refused .fit-1080 reads the FIT session only"):
            fl.main(["fit-1080", str(tmp_path / name), "--out", str(tmp_path / "r.json")])
    with pytest.raises(SystemExit, match="never inside the repo"):
        fl.main(["fit-1080", str(tmp_path / FIT), "--out", str(ROOT / "fit.json")])


# --- T-I2: freeze-1080 ----------------------------------------------------------------------------


MONSTER = {"status": "FROZEN", "offset_ms": 120.0}
TABLE = {"911": {"resname": "a", "act_sha256": "1", "spr_sha256": "2"}, "4206": None}


def _report(**kw: Any) -> dict[str, Any]:
    """A READY fit-1080 report (synthetic; the shape cmd_fit_1080 writes)."""
    rep: dict[str, Any] = {
        "kind": "fit-1080", "rule": fl.RULE_1080, "screen": "1080", "world_scale": 1.5,
        "session": FIT, "monster_params_sha256": fl.X1080_MONSTER_SHA256,
        "rule_constants": json.loads(json.dumps(fl.constants_1080(1.5))),
        "fit": {"best_scale": 1.05, "anchor": {"dx": -3.0, "dy": 1.5, "n": 120},
                "verdict": "READY"},
        "absent": {"t_item": 0.6, "max_rate": fl.ABSENT_MAX_RATE, "points": 400, "seed": "s",
                   "point_rule": "p", "sub_rule": "q", "fit": "f", "t_item_rule": "r",
                   "per_sprite": {"911": {"rate": 0.0}}, "items_excluded": [7269]},
        "items": TABLE, "drops": "d.json", "drops_sha256": "dd", "sprites_dir": "/dev/shm/x",
        "resnames": "r.txt", "resnames_sha256": "rr",
        "occluders": {"rsw_sha256": "rsw", "terrain": None},
        "bar_check": {"share_inside": {"centre": 0.986, "feet": 0.152}},
        "fitted_at": "2026-11-21 01:00:00 ICT", "commit": "abc", "verdict": "READY",
    }  # fmt: skip
    rep.update(kw)
    return rep


def test_freeze_1080_refuses_a_bar_box_that_misses_the_bar_on_ifF() -> None:
    """Amendment 3: the frozen bar box (BAR_ABOUT_1080, "centre") must hold >= 95 % of the bar's
    pixels on the FIT session, else nothing is frozen."""
    assert fl.BAR_INSIDE_MIN == 0.95
    for bad in ({"share_inside": {"centre": 0.94}}, {"share_inside": {}}, None):
        with pytest.raises(SystemExit, match="bar check on the FIT session"):
            fl.freeze_1080_params(SPEC, _report(bar_check=bad), "f" * 64, MONSTER,
                                  fl.X1080_MONSTER_SHA256, {"commit": "x"})  # fmt: skip


def test_freeze_1080_params_writes_the_fitted_and_the_rule_constants(tmp_path: Path) -> None:
    doc = fl.freeze_1080_params(SPEC, _report(), "f" * 64, MONSTER, fl.X1080_MONSTER_SHA256,
                                {"commit": "x"})  # fmt: skip
    assert (doc["rule"], doc["status"], doc["screen"]) == (fl.RULE_1080, "FROZEN", "1080")
    assert doc["map"] == "xmas_dun02"
    assert doc["anchor_px"] == [-3.0, 1.5] and doc["scale"] == 1.05 and doc["t_item"] == 0.6
    assert doc["bar_px"] == fl.constants_1080(1.5)["bar_px"] and doc["r_label"] == 10
    assert doc["self_box"] == {"w": 34.0, "h": 74.0, "pad": 4.0}
    assert doc["g2"] == {"bar_px": 3.0, "min_fits": 30, "margin_px": 30.0}
    assert doc["offset_ms"] == 120.0 and doc["monster_params_sha256"] == fl.X1080_MONSTER_SHA256
    assert doc["version"] == 2 and doc["items_excluded"] == [7269]
    assert doc["items_unsprited"] == [4206] and doc["fit_report_sha256"] == "f" * 64
    assert doc["fit_session"] == FIT and doc["commit"] == "x"
    assert (doc["d_appear_s"], doc["d_gone_s"], doc["stack_iou"]) == (2.2, 0.6, 0.5)
    p = tmp_path / "items-params-1080.json"
    p.write_text(json.dumps(doc))
    prm = fl.load_params(p, SPEC)
    me = (640.0, 420.0)
    assert fl.self_box_of(prm, me) == gi.self_box(me) and fl.margin_of(prm) == 30.0


@pytest.mark.parametrize("change,match", [
    ({"kind": "label"}, "not a fit-1080 report"),
    ({"screen": "720"}, "not a fit-1080 report"),
    ({"session": TRAIN}, "not a report of the FIT session"),
    ({"session": "20261109T082234-rdp-hunt-xmas02-p31"}, "not a report of the FIT session"),
    ({"monster_params_sha256": "0" * 64}, "other monster params"),
    ({"rule": "xmas02-fi-1"}, "another rule"),
    ({"verdict": "NOT_ENOUGH"}, "says NOT_ENOUGH"),
    ({"rule_constants": {**fl.constants_1080(1.5), "r_label": 16}}, "rule constants"),
])  # fmt: skip
def test_freeze_1080_params_refuses_another_report(change: dict[str, Any], match: str) -> None:
    with pytest.raises(SystemExit, match=match):
        fl.freeze_1080_params(SPEC, _report(**change), "f" * 64, MONSTER,
                              fl.X1080_MONSTER_SHA256, {})  # fmt: skip
    with pytest.raises(SystemExit, match="frozen monster params"):
        fl.freeze_1080_params(SPEC, _report(), "f" * 64, MONSTER, "0" * 64, {})


def test_freeze_1080_writes_once_prints_its_sha_and_refuses_inside_the_repo(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    out = tmp_path / "items-params-1080.json"
    out.write_text("{}")
    with pytest.raises(SystemExit, match="frozen ONCE"):
        fl.main(["freeze-1080", "--fit", "r.json", "--out", str(out)])
    with pytest.raises(SystemExit, match="never inside the repo"):
        fl.main(["freeze-1080", "--fit", "r.json", "--out", str(ROOT / "p.json")])
    monster = tmp_path / "params-1080.json"
    monster.write_text(json.dumps(MONSTER))
    msha = hashlib.sha256(monster.read_bytes()).hexdigest()
    spec = dataclasses.replace(SPEC, monster_params=monster, monster_params_sha256=msha)
    monkeypatch.setattr(fl, "XMAS02_FI_1080", spec)
    monkeypatch.setattr(fl, "frozen_sheets", lambda prm: None)
    monkeypatch.setattr(
        fl.ml, "occluders", lambda mspec: _Fake(provenance=lambda: {"rsw_sha256": "rsw"})
    )
    rep = tmp_path / "fit.json"
    rep.write_text(json.dumps(_report(monster_params_sha256=msha)))
    new = tmp_path / "new" / "items-params-1080.json"
    assert fl.main(["freeze-1080", "--fit", str(rep), "--out", str(new)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["sha256"] == hashlib.sha256(new.read_bytes()).hexdigest()
    assert printed["fit_report_sha256"] == hashlib.sha256(rep.read_bytes()).hexdigest()
    assert fl.load_params(new, spec)["anchor_px"] == [-3.0, 1.5]
    with pytest.raises(SystemExit, match="frozen ONCE"):
        fl.main(["freeze-1080", "--fit", str(rep), "--out", str(new)])
    monkeypatch.setattr(
        fl.ml, "occluders", lambda mspec: _Fake(provenance=lambda: {"rsw_sha256": "other"})
    )
    with pytest.raises(SystemExit, match="RSW differs"):
        fl.main(["freeze-1080", "--fit", str(rep), "--out", str(tmp_path / "again.json")])


# --- T-I4: round 6's pack ------------------------------------------------------------------------


def test_round_refusal_keeps_rounds_1_to_5_on_720_and_6_on_1080() -> None:
    for rnd in (1, 2, 3, 4, 5):
        assert fl.round_refusal(fl.XMAS02_FI, rnd, True) is None
    assert "--spec 1080" in str(fl.round_refusal(fl.XMAS02_FI, 6, True))
    assert fl.round_refusal(SPEC, 6, True) is None and fl.round_refusal(SPEC, 1, False) is None
    assert "720 round" in str(fl.round_refusal(SPEC, 5, True))
    assert "--round 6" in str(fl.round_refusal(SPEC, 1, True))


def test_pack_round6_takes_its_seed_from_the_cli(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    def pack(*extra: str) -> None:
        fl.main(["pack", "x.json", "--params", "p.json", "--out", str(tmp_path / "o.json"),
                 *extra])  # fmt: skip

    with pytest.raises(SystemExit, match="--spec 1080"):
        pack("--seed", "1", "--round", "6", "--eval-test")
    with pytest.raises(SystemExit, match="720 round"):
        pack("--spec", "1080", "--seed", "69", "--round", "5", "--eval-test")
    with pytest.raises(SystemExit, match="is --round 6"):
        pack("--spec", "1080", "--seed", "63", "--eval-test")
    with pytest.raises(SystemExit, match="evaluation's pack only"):
        pack("--spec", "1080", "--seed", "1", "--round", "6")
    with pytest.raises(SystemExit, match="pre-registered seed is 71"):
        pack("--spec", "1080", "--seed", "61")
    fake = tmp_path / "instructions.txt"
    fake.write_text("other instructions")
    monkeypatch.setattr(fl, "INSTRUCTIONS", fake)
    for seed in ("71", "12345"):  # past the seed check, whatever the seed: the next check stops
        with pytest.raises(SystemExit, match="pinned instructions"):
            pack("--spec", "1080", "--seed", seed, "--round", "6", "--eval-test")
    with pytest.raises(SystemExit, match="pinned instructions"):  # T2 at its seed 71
        pack("--spec", "1080", "--seed", "71")


def test_round6_pack_draws_natural_first_slot_and_staging_second() -> None:
    import fi_eval as fe

    assert fl.R6_STAGING == fe.R6_STAGING  # + round 7's new held-out (Amendment 22)
    assert set(fl.IF_HELD_OUT) == set(fe.R6_HELD_OUT) | set(fe.R7_HELD_OUT)
    assert set(fe.R6_PILOTS) | set(fl.R6_STAGING) | set(fl.R7_HELD_OUT) == set(SPEC.eval_suffixes)
    c = {"frame_id": 1, "floor_id": 1, "stratum": "N", "rel": [1.0, 0.0], "under": None}
    nat = [{**c, "session": HELD[i % 2], "frame_id": i, "floor_id": i} for i in range(90)]
    stg = [{**c, "session": HELD[2], "frame_id": i, "floor_id": 1000 + i} for i in range(80)]
    got = fl.r2_picks(nat + stg, True, 4242, SPEC.salt, fl.R6_STAGING)
    assert sum(g["aura"] for g in got) == 70  # the first slot (natural) capped at 70
    assert sum(not g["aura"] for g in got) == 50  # the staging capped at 50
    assert Counter(g["session"] for g in got if not g["aura"]) == {HELD[2]: 50}
    assert fl.pack_short(got[:60], {}, True, True) == {"aura": 10, "no_aura": 50}


def test_check_pack_docs_keeps_the_screens_apart() -> None:
    base = {"rule": fl.RULE_1080, "params_sha256": "p"}
    held = {**base, "session": HELD[0], "split": "eval", "eval_test": True, "screen": "1080"}
    fl.check_pack_docs(SPEC, [held], True, "p")
    with pytest.raises(SystemExit, match="720 labels, not the 1080"):
        fl.check_pack_docs(SPEC, [{k: v for k, v in held.items() if k != "screen"}], True, "p")
    train = {**base, "session": TRAIN, "split": "train", "screen": "1080"}
    fit = {**base, "session": FIT, "split": "val", "screen": "1080"}
    fl.check_pack_docs(SPEC, [fit, train], False, "p")  # T2 (section 6)'s pool
    with pytest.raises(SystemExit, match="not xmas02-fi-1 labels"):  # the rule's name first
        fl.check_pack_docs(fl.XMAS02_FI, [train], False, "p")
    with pytest.raises(SystemExit, match="1080 labels, not the 720"):  # then the screen
        fl.check_pack_docs(fl.XMAS02_FI, [{**train, "rule": fl.RULE}], False, "p")


# --- Amendment 22: round 7's pack (xmas02fi6 + the fi7 rule, scored on a NEW held-out) ----------


def test_round7_names_pinned_to_fi_eval_and_refused_for_train() -> None:
    import fi_eval as fe

    assert fl.R7_PILOTS == fe.R7_PILOTS and fl.R7_STAGING == fe.R7_STAGING
    assert fl.R7_HELD_OUT == fe.R7_HELD_OUT and fl.R7_EVAL_SEED == 74
    assert set(fl.R7_HELD_OUT) <= set(SPEC.eval_suffixes)
    for sid in HELD7:
        assert "held-out" in str(fl.role_refusal(SPEC, sid, "train", False))
        assert fl.role_refusal(SPEC, sid, None, True) is None  # --eval-test reads it
        assert fl.foreign_refusal(fl.XMAS02_FI, sid) is not None  # never under the 720 spec


def test_round_refusal_puts_round_7_on_1080_only() -> None:
    assert "--spec 1080" in str(fl.round_refusal(fl.XMAS02_FI, 7, True))
    assert fl.round_refusal(SPEC, 7, True) is None
    assert "--round 7" in str(fl.round_refusal(SPEC, 1, True))


def test_round7_pack_reads_its_own_held_out_only() -> None:
    assert fl.round_docs_refusal(7, [{"session": s} for s in HELD7]) is None
    assert "not round 7's held-out" in str(fl.round_docs_refusal(7, [{"session": HELD[0]}]))
    assert fl.round_docs_refusal(6, [{"session": HELD[0]}]) is None  # round 6: unchanged
    assert (
        fl.seed_source(7, True, True) == "Amendment 22" and fl.seed_source(6, True, True) == "O15"
    )


def test_pack_round7_takes_the_plans_seed_74(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    def pack(*extra: str) -> None:
        fl.main(["pack", "x.json", "--params", "p.json", "--out", str(tmp_path / "o.json"),
                 *extra])  # fmt: skip

    with pytest.raises(SystemExit, match="--spec 1080"):
        pack("--seed", "74", "--round", "7", "--eval-test")
    with pytest.raises(SystemExit, match="evaluation's pack only"):
        pack("--spec", "1080", "--seed", "74", "--round", "7")
    with pytest.raises(SystemExit, match="pre-registered seed is 74"):
        pack("--spec", "1080", "--seed", "73", "--round", "7", "--eval-test")
    fake = tmp_path / "instructions.txt"
    fake.write_text("other instructions")
    monkeypatch.setattr(fl, "INSTRUCTIONS", fake)
    with pytest.raises(SystemExit, match="pinned instructions"):  # past the seed check
        pack("--spec", "1080", "--seed", "74", "--round", "7", "--eval-test")


def test_round7_pack_draws_natural_first_slot_and_staging_second() -> None:
    c = {"frame_id": 1, "floor_id": 1, "stratum": "N", "rel": [1.0, 0.0], "under": None}
    nat = [{**c, "session": HELD7[i % 2], "frame_id": i, "floor_id": i} for i in range(90)]
    stg = [{**c, "session": HELD7[2 + i % 2], "frame_id": i, "floor_id": 1000 + i}
           for i in range(80)]  # fmt: skip
    got = fl.r2_picks(nat + stg, True, fl.R7_EVAL_SEED, SPEC.salt, fl.R7_STAGING)
    assert sum(g["aura"] for g in got) == 70  # the natural slot capped at 70
    assert sum(not g["aura"] for g in got) == 50  # the stagings capped at 50
    assert {g["session"] for g in got if not g["aura"]} == set(HELD7[2:])
