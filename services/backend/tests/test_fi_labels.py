"""The floor-item label pass on xmas_dun02 (scripts/fi_labels.py; docs/planning/xmas02-detector.md
Amendment O / O1, tools T-O1 and T-O3): the pure parts on SYNTHETIC data only (no client pixel,
no packet capture). The real-data positive cases (FIT p31's 204 / 233 / 15, frame 1157) run on
the NAS recordings, outside the suite."""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import fi_labels as fl  # noqa: E402
import item_labels as il  # noqa: E402
import map_labels as ml  # noqa: E402

from poring_dataset.render import SpritePrediction  # noqa: E402

S = 1_000_000_000
SIZE = (1280, 720)
SPEC = fl.XMAS02_FI


def test_the_spec_is_o1s_accepted_defaults() -> None:
    """O-D2 (O.3): anchor (-4, +2), scale 1.0, colour fit +-10, T_item 0.65, the FIT bar,
    item-class's 2.2 / 0.6 s; seeds 61 / 63; the params path of O.3 (g)."""
    assert SPEC.anchor_px == (-4.0, 2.0) and SPEC.scale == 1.0 and SPEC.r_label == 10
    assert SPEC.t_item == 0.65 and SPEC.bar == (-31.0, 10.0, 28.0, 18.0)
    assert (SPEC.d_appear_s, SPEC.d_gone_s, SPEC.stack_iou) == (2.2, 0.6, 0.5)
    assert (SPEC.pack_seed, SPEC.eval_seed, SPEC.salt) == (61, 63, "xmas02-fi")
    assert SPEC.params == Path("/dev/shm/poring-lab-tmp/xmas-fi/params.json")
    assert SPEC.mspec is ml.XMAS02 and SPEC.eval_suffixes == ml.XMAS02_FIT
    assert fl.CLASS_NAME == "floor_item" and fl.RULE == "xmas02-fi-1"
    assert (fl.G2_BAR_PX, fl.G2_MIN_FITS) == (3.0, 30)


@pytest.mark.parametrize("sid", [
    "20261106T162044-rdp-xmas02-xw5", "20261106T171533-rdp-xmas02-xp1", ml.XMAS02_X2,
    "20261109T212445-rdp-gb-gw3", "20261111T090000-rdp-hunt-xmas02-fiT4",
    "20261111T100000-rdp-hunt-xmas02-fiT5", "20261111T110000-rdp-hunt-xmas02-fiT6",
    "20261109T075431-rdp-s3-xmas02-p30",
])  # fmt: skip
def test_test_gw3_fit_and_p30_are_refused_by_name_for_train_and_val(sid: str) -> None:
    for split in ("train", "val"):
        assert fl.role_refusal(SPEC, sid, split, False) is not None


def test_fit_is_val_only_and_val_is_fit_only() -> None:
    p31, p38 = "20261109T082234-rdp-hunt-xmas02-p31", "20261109T133046-rdp-hunt-xmas02-p38"
    assert fl.role_refusal(SPEC, p31, "val", False) is None
    assert "VAL only" in str(fl.role_refusal(SPEC, p31, "train", False))
    assert fl.role_refusal(SPEC, p38, "train", False) is None
    assert "FIT only" in str(fl.role_refusal(SPEC, p38, "val", False))
    for sid in (
        "20261108T235614-rdp-s2-xmas_dun02-p20",
        "20261109T143541-rdp-hunt-xmas02-p39",
        "20261106T151122-rdp-xmas02-xw2",
        "20261109T210933-rdp-gb-gw2",
    ):
        assert fl.role_refusal(SPEC, sid, "train", False) is None  # TRAIN by the join rule


def test_eval_test_reads_the_fit_held_out_and_nothing_else() -> None:
    assert fl.role_refusal(SPEC, "20261111T090000-rdp-hunt-xmas02-fiT4", None, True) is None
    for sid in (
        "20261109T082234-rdp-hunt-xmas02-p31",
        "20261109T133046-rdp-hunt-xmas02-p38",
        "20261106T162044-rdp-xmas02-xw5",
        "20261109T212445-rdp-gb-gw3",
    ):
        assert fl.role_refusal(SPEC, sid, None, True) is not None


def test_label_refuses_by_name_before_reading(tmp_path: Path) -> None:
    """TEST / gw3 / fiT / p30 names are refused BEFORE the params or the session are opened
    (the params file does not even exist here); --eval-test refuses without a frozen model."""
    missing = tmp_path / "no-params.json"
    for name in (
        "20261106T162044-rdp-xmas02-xw5",
        "20261109T212445-rdp-gb-gw3",
        "20261111T090000-rdp-hunt-xmas02-fiT4",
        "20261109T075431-rdp-s3-xmas02-p30",
    ):
        with pytest.raises(SystemExit, match="refused"):
            fl.main(["label", str(tmp_path / name), "--split", "train", "--params", str(missing),
                     "--out", str(tmp_path / "o.json")])  # fmt: skip
    params = tmp_path / "params.json"
    params.write_text(json.dumps({"rule": fl.RULE, "map": "xmas_dun02", "status": "FROZEN"}))
    fit = str(tmp_path / "20261111T090000-rdp-hunt-xmas02-fiT4")
    with pytest.raises(SystemExit, match="frozen item model"):
        fl.main(["label", fit, "--eval-test", "--params", str(params), "--out", "o.json"])
    with pytest.raises(SystemExit, match="no frozen model"):
        fl.main(
            [
                "label",
                fit,
                "--eval-test",
                "--model",
                str(tmp_path / "last.pt"),
                "--model-sha256",
                "0" * 64,
                "--params",
                str(params),
                "--out",
                "o.json",
            ]
        )
    weights = tmp_path / "last.pt"
    weights.write_bytes(b"not the model")
    with pytest.raises(SystemExit, match="not the frozen"):
        fl.main(["label", fit, "--eval-test", "--model", str(weights), "--model-sha256",
                 "0" * 64, "--params", str(params), "--out", "o.json"])  # fmt: skip
    with pytest.raises(SystemExit, match="refused"):  # --eval-test on a TRAIN name
        fl.main(["label", str(tmp_path / "20261109T133046-rdp-hunt-xmas02-p38"), "--eval-test",
                 "--params", str(params), "--out", "o.json"])  # fmt: skip
    with pytest.raises(SystemExit, match="split"):
        fl.main(["label", fit, "--params", str(params), "--out", "o.json"])


def test_load_params_needs_the_frozen_rule(tmp_path: Path) -> None:
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"rule": fl.RULE, "map": "xmas_dun02", "status": "PROPOSED"}))
    with pytest.raises(SystemExit, match="FROZEN"):
        fl.load_params(p, SPEC)
    p.write_text(json.dumps({"rule": "xmas02-o3h-t", "map": "xmas_dun02", "status": "FROZEN"}))
    with pytest.raises(SystemExit, match="not xmas02-fi-1"):
        fl.load_params(p, SPEC)


def test_freeze_params_records_o1s_values_and_refuses_other_monster_params() -> None:
    monster = {"status": "FROZEN", "offset_ms": 120.0}
    table = {"911": {"resname": "a", "act_sha256": "1", "spr_sha256": "2"}, "4206": None}
    doc = fl.freeze_params(SPEC, table, monster, SPEC.monster_params_sha256, {"commit": "x"})
    assert doc["status"] == "FROZEN" and doc["rule"] == "xmas02-fi-1"
    assert doc["anchor_px"] == [-4.0, 2.0] and doc["scale"] == 1.0 and doc["r_label"] == 10
    assert doc["t_item"] == 0.65 and doc["bar_px"] == [-31.0, 10.0, 28.0, 18.0]
    assert doc["offset_ms"] == 120.0 and doc["items_unsprited"] == [4206]
    assert doc["sub_table"]["OX"][3] == -0.189 and doc["commit"] == "x"
    with pytest.raises(SystemExit, match="frozen monster params"):
        fl.freeze_params(SPEC, table, monster, "0" * 64, {})
    with pytest.raises(SystemExit, match="frozen monster params"):
        fl.freeze_params(SPEC, table, {"status": "PROPOSED", "offset_ms": 1.0},
                         SPEC.monster_params_sha256, {})  # fmt: skip


def test_freeze_writes_once(tmp_path: Path) -> None:
    out = tmp_path / "params.json"
    out.write_text("{}")
    with pytest.raises(SystemExit, match="frozen ONCE"):
        fl.main(["freeze", "--out", str(out)])


def test_at_scale_keeps_the_anchor_and_rescales_the_box() -> None:
    p = SpritePrediction((90.0, 80.0, 110.0, 100.0), (100.0, 100.0), 0.5, 1.0, 0, 0, 0, 0, True,
                         "opaque")  # fmt: skip
    q = fl.at_scale(p, 1.0)
    assert q.scale == 1.0 and q.anchor_px == (100.0, 100.0)
    assert q.box == (80.0, 60.0, 120.0, 100.0)


def _reasons(**kw: Any) -> tuple[list[str], list[int]]:
    base: dict[str, Any] = {"preds": {1: (600.0, 300.0, 612.0, 312.0)}, "phases": ["on"],
                            "me": (640.0, 420.0), "units": [], "size": SIZE, "rects": [],
                            "bar": SPEC.bar, "stack_iou": 0.5}  # fmt: skip
    base.update(kw)
    return fl.frame_reasons(**base)


def test_frame_reasons_are_o3d_exclusions() -> None:
    assert _reasons() == ([], [1])
    assert _reasons(phases=["on", "settling"])[0] == ["item_settling"]
    assert _reasons(phases=["vanishing"])[0] == ["item_vanishing"]
    # the FIT bar: (-31, +10, +28, +18) from our anchor (640, 420): x 609-668, y 430-438
    assert _reasons(preds={1: (620.0, 420.0, 632.0, 434.0)})[0] == ["under_self", "under_bar"]
    assert _reasons(preds={1: (650.0, 436.0, 660.0, 446.0)})[0] == ["under_bar"]
    assert _reasons(preds={1: (650.0, 440.0, 660.0, 452.0)})[0] == []  # below the bar
    # the old gef10 bar (-36, 0, +36, +24) would have caught it: the FIT bar is narrower
    assert _reasons(preds={1: (604.0, 440.0, 608.0, 444.0)})[0] == []
    assert _reasons(units=[(606.0, 330.0)])[0] == ["under_unit"]
    assert _reasons(preds={1: (600.0, 300.0, 612.0, 312.0),
                           2: (601.0, 301.0, 613.0, 313.0)})[0] == ["stacked"]  # fmt: skip
    assert _reasons(rects=[(590, 290, 40, 40)]) == ([], [])  # wholly inside a window: hidden
    assert _reasons(rects=[(605, 290, 40, 40)])[0] == ["ui_partial"]
    assert _reasons(preds={1: (1275.0, 300.0, 1287.0, 312.0)})[0] == ["edge_partial"]


def test_g2_clear_and_summary() -> None:
    me = (640.0, 420.0)
    clear = (500.0, 300.0, 512.0, 312.0)
    assert fl.g2_clear(clear, me, [], [], SIZE, [], SPEC.bar, None)
    assert not fl.g2_clear(clear, me, [], [], SIZE, [], SPEC.bar, "model")
    assert not fl.g2_clear(clear, me, [], [(505.0, 305.0, 515.0, 315.0)], SIZE, [], SPEC.bar, None)
    assert not fl.g2_clear((10.0, 300.0, 22.0, 312.0), me, [], [], SIZE, [], SPEC.bar, None)
    assert not fl.g2_clear(clear, me, [(506.0, 400.0)], [], SIZE, [], SPEC.bar, None)
    fits = [{"session": "s", "floor_id": i % 7, "dx": d, "dy": -d} for i, d in
            enumerate([0, 1, 1, 2, -1, 5] * 5)]  # fmt: skip
    g = fl.g2_summary(fits)
    assert g["n"] == 30 and g["median_abs_dx"] == 1.0 and g["verdict"] == "PASS"
    assert fl.g2_summary(fits[:29])["verdict"] == "NOT_ENOUGH"
    far = [{**f, "dx": 4} for f in fits]
    assert fl.g2_summary(far)["verdict"] == "FAIL"
    assert fl.g2_summary([])["verdict"] == "NOT_ENOUGH"


def _frame(fid: int, status: str, items: list[dict[str, Any]], reasons: list[str] | None = None,
           n_near: int | None = 1) -> dict[str, Any]:  # fmt: skip
    return {"frame_id": fid, "t": fid * S, "shard": "shard-000000.tar", "offset": fid,
            "size": 10, "status": status, "reasons": reasons or [], "items": items,
            "n_near": n_near}  # fmt: skip


def _item(fid: int, rel: list[float] | None, under: str | None = None, clear: bool = True,
          dx: int = 1) -> dict[str, Any]:  # fmt: skip
    return {"floor_id": fid, "item_id": 911, "box": [10.0, 10.0, 21.0, 22.0], "ncc": 0.9,
            "dx": dx, "dy": -1, "rel": rel, "under": under, "g2_clear": clear}  # fmt: skip


def test_count_labels_is_o4s_table() -> None:
    frames = [
        _frame(1, "keep", [_item(1, [1, 0]), _item(2, [-4, 2], "model")]),
        _frame(2, "keep", [_item(1, [1, 0])]),
        _frame(3, "exclude", [_item(3, [0, 1], clear=False)], ["under_self", "under_bar"]),
        _frame(4, "keep", [], n_near=0),
        _frame(5, "keep", [], n_near=1),  # an item wholly behind the UI: a negative
        _frame(6, "exclude", [], ["ui_layout_mismatch"], n_near=None),
    ]
    c = fl.count_labels(frames)
    assert c["kept_frames_with_items"] == 2 and c["item_labels"] == 3 and c["floor_items"] == 2
    assert c["by_distance"] == {"within_1": 2, "2_5": 1}
    assert c["under_model_kept"] == 1 and c["negatives"] == 2 and c["excluded_frames"] == 2
    assert c["frame_exclusions"] == {"under_self": 1, "under_bar": 1, "ui_layout_mismatch": 1}
    assert c["frames_with_items_near"] == 4
    rows = fl.g2_rows(frames, "s")
    assert len(rows) == 3 and all(r["session"] == "s" for r in rows)  # every CLEAR fitted view


def test_strata_partition_n_first() -> None:
    assert fl.stratum_of({"rel": [1, -1], "under": "model"}) == "N"
    assert fl.stratum_of({"rel": [0, 1], "under": None}) == "N"
    assert fl.stratum_of({"rel": [2, 0], "under": None}) == "F"
    assert fl.stratum_of({"rel": [-5, 3], "under": "terrain"}) == "M"
    assert fl.stratum_of({"rel": None, "under": None}) == "F"


def test_draw_strata_is_seeded_sized_and_caps_three_per_floor_item() -> None:
    cands = [{"session": f"s{i % 2}", "frame_id": i, "floor_id": i % 5, "stratum": s}
             for i in range(200) for s in ("N", "F", "M")[i % 3:i % 3 + 1]]  # fmt: skip
    picks = fl.draw_strata(cands, fl.PACK_N, 61, "xmas02-fi")
    assert picks == fl.draw_strata(cands, fl.PACK_N, 61, "xmas02-fi")
    assert picks != fl.draw_strata(cands, fl.PACK_N, 62, "xmas02-fi")
    per = Counter((p["session"], p["floor_id"]) for p in picks)
    # only 10 (session, floor id) pairs exist: 3 each at most = 30 crops over the whole pack,
    # taken by the strata in order (N, F, then M finds every pair spent)
    assert max(per.values()) == 3 and len(per) == 10 and len(picks) == 30
    assert Counter(p["stratum"] for p in picks) == {"N": 15, "F": 15}
    rich = [{"session": "s", "frame_id": i, "floor_id": i, "stratum": "NFM"[i % 3]}
            for i in range(300)]  # fmt: skip
    got = Counter(p["stratum"] for p in fl.draw_strata(rich, fl.PACK_N, 61, "xmas02-fi"))
    assert got == {"N": 15, "F": 15, "M": 10}


def test_hard_pick_takes_the_highest_fits_one_per_frame() -> None:
    pts = [{"session": "s", "frame_id": i // 2, "ncc": v} for i, v in
           enumerate([0.1, 0.9, 0.8, 0.7, 0.75, 0.2, None, 0.95])]  # fmt: skip
    got = fl.hard_pick(pts, 3)
    assert [p["ncc"] for p in got] == [0.95, 0.9, 0.8]
    assert len({p["frame_id"] for p in got}) == 3


def test_absent_cell_keeps_away_from_us_items_and_units() -> None:
    rng = random.Random(5)
    for _ in range(200):
        c = fl.absent_cell((100.0, 100.0), [(104.0, 100.0)], [(96.0, 96.0)], rng)
        assert c is not None
        assert fl.cheb(c, (100, 100)) > 1 and fl.cheb(c, (104, 100)) > 3
        assert fl.cheb(c, (96, 96)) > 2
        assert abs(c[0] - 100) <= 7 and abs(c[1] - 100) <= 5
    crowd = [(100.0 + dx, 100.0 + dy) for dx in range(-8, 9, 3) for dy in range(-6, 7, 3)]
    assert fl.absent_cell((100.0, 100.0), crowd, [], random.Random(1)) is None


def test_kill_rows_attribute_falls_on_the_death_cell() -> None:
    def floor(fid: int, x: int, y: int, t: float, kind: str = "fall") -> il.Floor:
        return il.Floor(fid, 911, x, y, 6, 6, kind, int(t * S), int((t + 20) * S), True)

    floors = [floor(1, 50, 50, 9.75), floor(2, 51, 49, 9.75), floor(3, 50, 50, 5.0),
              floor(4, 54, 50, 9.8), floor(5, 50, 50, 9.8, "in_sight")]  # fmt: skip
    rows = fl.kill_rows(
        [
            {"t": 10 * S, "gid": 7, "job": 1248, "cell": [50, 50]},
            {"t": 30 * S, "gid": 8, "job": 1249, "cell": None},
        ],
        floors,
    )
    assert rows[0]["drops"] == [1, 2] and rows[1]["drops"] == []


def _sheet_sprite(monkeypatch: pytest.MonkeyPatch) -> np.ndarray:
    """A 9 x 8 RGBA sprite (a two-colour gem) as the one frame compose_frame returns."""
    rgba = np.zeros((8, 9, 4), np.uint8)
    rgba[1:7, 2:8, :3] = (200, 40, 220)
    rgba[2:5, 3:6, :3] = (30, 230, 90)
    rgba[0:8, 3:6, :3] = (240, 240, 40)
    rgba[1:7, 2:8, 3] = 255
    rgba[0:8, 3:6, 3] = 255
    monkeypatch.setattr(fl, "compose_frame", lambda spr, act, ai, m: (rgba, (4.5, 4.0)))
    return rgba


class _Sheet:
    spr = act = None


def test_colour_fit_finds_the_drawn_offset(monkeypatch: pytest.MonkeyPatch) -> None:
    """The sprite pasted 2 px right and 1 px up of its prediction on a noisy floor: the colour
    fit finds (+2, -1) at NCC ~1; an empty floor scores far lower; off the frame: None."""
    rgba = _sheet_sprite(monkeypatch)
    rng = np.random.default_rng(3)
    bgr = rng.integers(60, 120, (200, 300, 3)).astype(np.uint8)
    empty = bgr.copy()
    ax, ay = 150.0, 100.0
    x0, y0 = int(ax - 4.5) + 2, int(ay - 4.0) - 1
    a = rgba[..., 3] > 0
    patch = bgr[y0 : y0 + 8, x0 : x0 + 9]
    patch[a] = rgba[..., 2::-1][a]  # RGB -> the frame's BGR
    p = SpritePrediction((ax - 4.5, ay - 4.0, ax + 4.5, ay + 4.0), (ax, ay), 1.0, 1.0, 0, 0, 0,
                         0, True, "opaque")  # fmt: skip
    valid = np.ones((200, 300), bool)
    ncc, dx, dy = fl.colour_fit(bgr, valid, _Sheet(), p, 10)  # type: ignore[arg-type]
    assert (dx, dy) == (2, -1) and ncc > 0.99
    got = fl.colour_fit(empty, valid, _Sheet(), p, 10)  # type: ignore[arg-type]
    assert got is not None and got[0] < 0.65
    off = SpritePrediction((-60.0, -60.0, -50.0, -50.0), (-55.0, -55.0), 1.0, 1.0, 0, 0, 0, 0,
                           True, "opaque")  # fmt: skip
    assert fl.colour_fit(bgr, valid, _Sheet(), off, 2) is None  # type: ignore[arg-type]
    rgb_t, op = fl.rendered_rgb(_Sheet(), p, (145, 96, 155, 104))  # type: ignore[arg-type]
    assert op.sum() == int(a.sum()) and rgb_t.shape == (8, 10, 3)


def test_reference_sheet_draws_each_distinct_sprite_on_both_tiles(
        monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    _sheet_sprite(monkeypatch)
    img, n = fl.reference_sheet({911: _Sheet(), 912: _Sheet()})  # type: ignore[dict-item]
    assert n == 1  # identical images once
    assert img.dtype == np.uint8 and img.shape[2] == 3
    flat = img.reshape(-1, 3)
    for tile in (fl.TILE_ORANGE, fl.TILE_PALE):
        assert (flat == np.array(tile, np.uint8)).all(axis=1).any()


def test_order_entries_is_one_seeded_order() -> None:
    e = [{"stratum": s, "session": "a", "frame_id": i, "floor_id": i, "kind": "item"}
         for i, s in enumerate("NNFFMMEE")]  # fmt: skip
    o = fl.order_entries(e, 61, "xmas02-fi")
    assert o == fl.order_entries(list(reversed(e)), 61, "xmas02-fi")
    assert sorted(x["frame_id"] for x in o) == list(range(8))
    assert o != fl.order_entries(e, 63, "xmas02-fi")


def test_check_pack_docs_keeps_the_roles_apart() -> None:
    base = {"rule": fl.RULE, "params_sha256": "p"}
    fit = {**base, "session": "20261109T082234-rdp-hunt-xmas02-p31", "split": "val"}
    train = {**base, "session": "20261109T133046-rdp-hunt-xmas02-p38", "split": "train"}
    held = {**base, "session": "20261111T090000-rdp-hunt-xmas02-fiT4", "split": "eval",
            "eval_test": True}  # fmt: skip
    fl.check_pack_docs(SPEC, [fit, train], False, "p")
    fl.check_pack_docs(SPEC, [held], True, "p")
    with pytest.raises(SystemExit, match="T2-items"):
        fl.check_pack_docs(SPEC, [fit, held], False, "p")
    with pytest.raises(SystemExit, match="eval-test fiT labels only"):
        fl.check_pack_docs(SPEC, [train], True, "p")
    with pytest.raises(SystemExit, match="frozen params"):
        fl.check_pack_docs(SPEC, [train], False, "other")
    with pytest.raises(SystemExit, match="T2-items"):  # a TRAIN file relabelled as val
        fl.check_pack_docs(SPEC, [{**train, "split": "val"}], False, "p")


def test_pack_refuses_another_seed_and_changed_instructions(tmp_path: Path,
                                                             monkeypatch: pytest.MonkeyPatch
                                                             ) -> None:  # fmt: skip
    with pytest.raises(SystemExit, match="pre-registered seed is 61"):
        fl.main(["pack", "x.json", "--params", "p.json", "--seed", "21", "--out", "o.json"])
    with pytest.raises(SystemExit, match="pre-registered seed is 63"):
        fl.main(["pack", "x.json", "--params", "p.json", "--seed", "61", "--eval-test",
                 "--out", "o.json"])  # fmt: skip
    fake = tmp_path / "instructions.txt"
    fake.write_text("other instructions")
    monkeypatch.setattr(fl, "INSTRUCTIONS", fake)
    with pytest.raises(SystemExit, match="pinned instructions"):
        fl.main(["pack", "x.json", "--params", "p.json", "--seed", "61", "--out", "o.json"])


def test_the_committed_instructions_are_the_pinned_ones() -> None:
    import hashlib

    assert hashlib.sha256(fl.INSTRUCTIONS.read_bytes()).hexdigest() == fl.INSTRUCTIONS_SHA256


def test_refs_cover_judged_and_i4_frames(tmp_path: Path) -> None:
    doc = {"session": "S", "eval_test": True, "frames": [
        _frame(1, "keep", [], n_near=0), _frame(2, "exclude", [], ["no_scene"], n_near=None),
        _frame(3, "exclude", [], ["under_bar"])],
        "kills": [{"drops": [], "i4": {"frame_id": 9, "shard": "shard-000001.tar", "offset": 5,
                                       "size": 7}}, {"drops": [1], "i4": None}]}  # fmt: skip
    lab = tmp_path / "l.json"
    lab.write_text(json.dumps(doc))
    refs = tmp_path / "refs.json"
    fl.main(["refs", str(lab), "--refs-out", str(refs), "--out", str(tmp_path / "o.json")])
    got = json.loads(refs.read_text())
    assert sorted(got) == ["S.000000001", "S.000000003", "S.000000009"]
    assert got["S.000000009"] == {"path": "/datasets/S/shard-000001.tar", "offset": 5, "size": 7}
    lab.write_text(json.dumps({**doc, "eval_test": False}))
    with pytest.raises(SystemExit, match="eval-test label files only"):
        fl.main(["refs", str(lab), "--refs-out", str(refs), "--out", str(tmp_path / "o.json")])


# --- params v2 (Amendment O3): the absent rule ---------------------------------------------------


def test_absent_rule_excludes_an_id_over_one_percent_and_keeps_one_under() -> None:
    """O3: an id whose sprite fits >= T_item on MORE than 1 % of the absent points is excluded
    (every id sharing that sprite too); exactly 1 %, none, or no fit at all: kept."""
    groups = {7269: [7269], 911: [911], 4206: [4206, 4235], 50: [50], 60: [60]}
    fits = {
        7269: [0.87] * 44 + [0.5] * 15,  # 44 / 59 = 74.6 %
        911: [0.60] * 59,  # 0 %
        4206: [0.66] + [0.3] * 58,  # 1 / 59 = 1.7 % > 1 %: both card ids go
        50: [0.65] + [0.1] * 99,  # exactly 1 / 100 = 1 %: kept (not MORE than 1 %)
    }  # 60: no fit at all -> kept
    excluded, rows = fl.absent_rule(fits, groups, 0.65)
    assert excluded == [4206, 4235, 7269]
    assert rows["7269"]["rate"] == round(44 / 59, 4) and rows["7269"]["excluded"]
    assert rows["911"]["pass"] == 0 and not rows["911"]["excluded"]
    assert rows["50"]["rate"] == 0.01 and not rows["50"]["excluded"]
    assert rows["60"]["n"] == 0 and not rows["60"]["excluded"]
    assert rows["4206"]["ids"] == [4206, 4235]


def test_absent_groups_key_each_sprite_by_its_smallest_id() -> None:
    table = {"4235": {"act_sha256": "c", "spr_sha256": "d"},
             "4206": {"act_sha256": "c", "spr_sha256": "d"},
             "911": {"act_sha256": "a", "spr_sha256": "b"}, "1": None}  # fmt: skip
    assert fl.absent_groups(table) == {911: [911], 4206: [4206, 4235]}


def test_frozen_sheets_leave_out_the_excluded_ids_but_still_draw_them(tmp_path: Path) -> None:
    import hashlib

    spr = tmp_path / "spr"
    spr.mkdir()
    table = {}
    for iid in (911, 7269):
        (spr / f"r{iid}.act").write_bytes(b"act")
        (spr / f"r{iid}.spr").write_bytes(b"spr")
        table[str(iid)] = {"resname": f"r{iid}", "act_sha256": hashlib.sha256(b"act").hexdigest(),
                           "spr_sha256": hashlib.sha256(b"spr").hexdigest()}  # fmt: skip
    orig = (fl.parse_act, fl.parse_spr)
    try:
        fl.parse_act = lambda b: "A"  # type: ignore[assignment]
        fl.parse_spr = lambda b: "S"  # type: ignore[assignment]
        sh = fl.frozen_sheets({"items": table, "sprites_dir": str(spr),
                               "items_excluded": [7269]})  # fmt: skip
        v1 = fl.frozen_sheets({"items": table, "sprites_dir": str(spr)})
    finally:
        fl.parse_act, fl.parse_spr = orig
    assert sh(911) is not None and sh(7269) is None and sh.any(7269) is not None
    assert sorted(sh.sheets) == [911] and sorted(sh.all) == [911, 7269]
    assert sorted(v1.sheets) == [911, 7269] and v1.excluded == frozenset()


class _Fake:
    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


def _one_item_frame(monkeypatch: pytest.MonkeyPatch, item_id: int,
                    excluded: tuple[int, ...]) -> dict[str, Any]:  # fmt: skip
    """_label_frame on ONE frame with one floor item ON the floor (fakes for the session, the
    camera and the fit): what the rule writes for it."""
    t = 100 * S
    floor = il.Floor(5, item_id, 60, 70, 6, 6, "fall", t - 10 * S, t + 30 * S, True)
    world = _Fake(self_pos=(57.0, 70.0), entities=[])
    scene = _Fake(player=(57.0, 70.0))
    sess = _Fake(lab=_Fake(timeline=_Fake(frame_world=lambda tw: world), size=SIZE, ui_rects=()),
                 scene=lambda w: scene, layout_ok=lambda bgr: True)  # fmt: skip
    sheet = object()

    class Sheets:
        def __call__(self, iid: int) -> Any:
            return None if iid in excluded else sheet

        def any(self, iid: int) -> Any:
            return sheet

    def project(sc: Any, cell: Any) -> tuple[tuple[float, float], float]:
        return ((640.0, 420.0) if tuple(cell) == sc.player else (500.0, 300.0)), 1.0

    pred = SpritePrediction((494.0, 294.0, 505.0, 306.0), (500.0, 300.0), 1.0, 1.0, 0, 0, 0, 0,
                            True, "opaque")  # fmt: skip
    monkeypatch.setattr(fl, "anchor_and_depth", project)
    monkeypatch.setattr(fl, "_predict", lambda sh, cell, sc, prm: pred)
    monkeypatch.setattr(fl, "_units", lambda *a: [])
    monkeypatch.setattr(fl, "colour_fit", lambda *a: (0.9, 1, -1))
    monkeypatch.setattr(ml, "read_png", lambda ref: np.zeros((720, 1280, 3), np.uint8))
    prm = {"d_appear_s": 2.2, "d_gone_s": 0.6, "offset_ms": 120.0, "bar_px": list(SPEC.bar),
           "stack_iou": 0.5, "r_label": 10, "t_item": 0.65}  # fmt: skip
    monkeypatch.setattr(fl.olf, "_JOB", {"sess": sess, "floors": [floor], "sheets": Sheets(),
                                         "occluders": _Fake(under=lambda *a: None),
                                         "params": prm, "eval_test": False})  # fmt: skip
    ref = _Fake(frame_id=7, t_mono_ns=t, shard=Path("shard-000000.tar"), offset=0, size=1)
    return fl._label_frame(ref)  # type: ignore[arg-type]


def test_a_frame_holding_an_excluded_id_is_excluded_with_its_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kept = _one_item_frame(monkeypatch, 911, excluded=(7269,))
    assert kept["status"] == "keep" and [i["item_id"] for i in kept["items"]] == [911]
    assert "unsprited_ids" not in kept
    gone = _one_item_frame(monkeypatch, 7269, excluded=(7269,))
    assert gone["status"] == "exclude" and gone["reasons"] == ["item_unsprited"]
    assert gone["items"] == [] and gone["unsprited_ids"] == [7269]
    v1 = _one_item_frame(monkeypatch, 7269, excluded=())  # v1: the same frame was labelled
    assert v1["status"] == "keep" and [i["item_id"] for i in v1["items"]] == [7269]


def test_freeze_v2_refuses_before_measuring(tmp_path: Path) -> None:
    out = tmp_path / "v2.json"
    out.write_text("{}")
    with pytest.raises(SystemExit, match="frozen ONCE"):
        fl.main(["freeze-v2", "--v1", "p.json", "--labels", "l.json", "--out", str(out)])
    v1 = tmp_path / "v1.json"
    v1.write_text(json.dumps({"rule": fl.RULE, "map": "xmas_dun02", "status": "FROZEN",
                              "version": 2, "items_excluded": []}))  # fmt: skip
    with pytest.raises(SystemExit, match="built from the v1"):
        fl.main(["freeze-v2", "--v1", str(v1), "--labels", "l.json", "--out",
                 str(tmp_path / "new.json")])  # fmt: skip
    v1.write_text(json.dumps({"rule": fl.RULE, "map": "xmas_dun02", "status": "FROZEN"}))
    sha = __import__("hashlib").sha256(v1.read_bytes()).hexdigest()
    lab = tmp_path / "l.json"
    lab.write_text(json.dumps({"rule": fl.RULE, "params_sha256": sha, "split": "train",
                               "session": "20261109T133046-rdp-hunt-xmas02-p38"}))  # fmt: skip
    with pytest.raises(SystemExit, match="O3: the rule is fixed on FIT"):
        fl.main(["freeze-v2", "--v1", str(v1), "--labels", str(lab), "--out",
                 str(tmp_path / "new.json")])  # fmt: skip
    lab.write_text(json.dumps({"rule": fl.RULE, "params_sha256": "0" * 64, "split": "train",
                               "session": "20261109T133046-rdp-hunt-xmas02-p38"}))  # fmt: skip
    with pytest.raises(SystemExit, match="not xmas02-fi-1 labels under"):
        fl.main(["freeze-v2", "--v1", str(v1), "--labels", str(lab), "--out",
                 str(tmp_path / "new.json")])  # fmt: skip
    assert SPEC.params_v2 == Path("/dev/shm/poring-lab-tmp/xmas-fi/params-v2.json")
    assert (fl.ABSENT_POINTS, fl.ABSENT_SEED, fl.ABSENT_MAX_RATE) == (60, "per-sprite", 0.01)


def test_o15_round2_pack_draws_near_first_and_the_eval_by_aura() -> None:
    """O15: T2-r2 = 40 item crops, N first (then F, M), <= 3 per floor item; the evaluation's pack
    = up to 70 aura + 50 no-aura crops by session NAME, each keeping its N / F / M stratum."""
    import fi_eval as fe

    assert fl.R2_NOAURA == fe.R2_NOAURA
    assert (fl.R2_PACK_SEED, fl.R2_EVAL_SEED) == (65, 66)

    def c(sid: str, fid: int, floor: int, st: str) -> dict[str, Any]:
        return {"session": sid, "frame_id": fid, "floor_id": floor, "stratum": st,
                "rel": [1.0, 0.0] if st == "N" else [3.0, 0.0], "under": None}  # fmt: skip

    fs2, fs3 = "20261110T211700-rdp-xmas02-fs2", "20261110T221000-rdp-xmas02-fs3"
    cands = ([c(fs2, i, i // 4, "N") for i in range(60)] + [c(fs3, i, 100 + i, "F")
             for i in range(30)])  # fmt: skip
    got = fl.r2_picks(cands, False, 65, "xmas02-fi")
    assert len(got) == 40
    per = Counter((g["session"], g["floor_id"]) for g in got)
    assert max(per.values()) <= 3
    n_n = sum(g["stratum"] == "N" for g in got)
    assert n_n == 15 * 3 or n_n == 40  # 15 floor items x 3 near crops at most, then F fills
    assert [g["stratum"] for g in got] == sorted((g["stratum"] for g in got),
                                                 key="NFM".index)  # fmt: skip
    ta, tn = "20261110T233000-rdp-xmas02-fsTa", "20261110T230000-rdp-xmas02-fsTn"
    ev = [c(ta, i, i, "N") for i in range(90)] + [c(tn, i, 500 + i, "N") for i in range(20)]
    got = fl.r2_picks(ev, True, 66, "xmas02-fi")
    assert sum(g["aura"] for g in got) == 70 and sum(not g["aura"] for g in got) == 20
    assert fl.pack_short(got, {}, True, True) == {"no_aura": 30}
    assert fl.pack_short(got[:10], {}, False, True) == {"items": 30}
