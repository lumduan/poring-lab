"""gef_fild10's floor-item FIT measurement (docs/planning/gef10-detector.md 8;
scripts/gef10_items.py): the pure parts on SYNTHETIC data."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import gef10_items as gi  # noqa: E402

S = 1_000_000_000
SIZE = (1280, 720)


def test_parse_resnames_cp949() -> None:
    raw = "7053#사이파#\n// a comment\n931#오크전사의증표#\nbad#x#\n12#\n".encode("cp949")
    assert gi.parse_resnames(raw) == {7053: "사이파", 931: "오크전사의증표"}


def test_self_box_and_inside() -> None:
    assert gi.self_box((100.0, 200.0)) == (79.0, 122.0, 121.0, 204.0)
    assert gi.inside((100, 100, 120, 120), SIZE, [])
    assert not gi.inside((10, 100, 30, 120), SIZE, [])  # < 30 px from the frame's edge
    assert not gi.inside((100, 100, 120, 120), SIZE, [(140, 100, 50, 50)])  # 20 px from a window
    assert gi.inside((100, 100, 120, 120), SIZE, [(151, 100, 50, 50)])


def _reason(**kw: Any) -> str | None:
    base: dict[str, Any] = {"item_box": (600.0, 300.0, 615.0, 320.0), "me": (640.0, 420.0),
                            "units": [], "others": [], "size": SIZE, "rects": [],
                            "under_model": False, "age_ns": 3 * S, "left_ns": 5 * S}  # fmt: skip
    base.update(kw)
    return gi.sample_reason(**base)


def test_sample_reasons_in_order() -> None:
    assert _reason() is None
    assert _reason(age_ns=2 * S) == "young"
    assert _reason(left_ns=S // 2) == "vanishing_soon"
    assert _reason(left_ns=None) is None  # ended by our map change: no vanish margin
    assert _reason(me=(607.0, 380.0)) == "under_self"  # our box reaches 74 + 4 px up
    assert _reason(item_box=(600.0, 425.0, 615.0, 440.0)) == "under_self_bar"
    assert _reason(units=[(607.0, 400.0)]) == "under_unit"  # 100 px up from its feet
    assert _reason(others=[(610.0, 310.0, 625.0, 330.0)]) == "near_item"
    assert _reason(item_box=(5.0, 300.0, 20.0, 320.0)) == "ui_or_edge"
    assert _reason(under_model=True) == "under_model"


def test_summarize_anchor_floor_and_stop() -> None:
    few = [{"ncc": 0.9, "dx": -5, "dy": 1}] * 11
    assert gi.summarize(few)["STOP"] == "11 samples < 12"
    rows = ([{"ncc": 0.9, "dx": -5, "dy": 1}] * 10 + [{"ncc": 0.5, "dx": -4, "dy": 0}] * 5
            + [{"ncc": 0.99, "dx": 10, "dy": 0}] * 3 + [{"ncc": None}])  # fmt: skip
    s = gi.summarize(rows)
    assert s["samples"] == 19 and s["fitted"] == 18 and s["not_at_edge"] == 15
    assert s["anchor_px"] == [-5.0, 1.0] and s["t_item"] == 0.5
    assert s["mad_px"] == [0.0, 0.0]


# --- round 3 (docs/planning/gef10-round3.md): freeze, labels, G2 ---------------------------------


def test_anchored_moves_the_window_and_the_render_point() -> None:
    from poring_dataset.render import SpritePrediction

    p = SpritePrediction(box=(100.0, 200.0, 114.0, 222.0), anchor_px=(107.0, 222.0), scale=0.98,
                         depth=50.0, action=0, direction=0, action_index=0, motion=0,
                         phase_known=True, box_kind="opaque")  # fmt: skip
    q = gi.anchored(p, (-3.0, 1.0))
    assert q.box == (97.0, 201.0, 111.0, 223.0) and q.anchor_px == (104.0, 223.0)
    assert q.scale == p.scale and q.motion == p.motion and p.box == (100.0, 200.0, 114.0, 222.0)


def _lr(
    boxes: dict[int, tuple[float, float, float, float]], **kw: Any
) -> tuple[list[str], list[int]]:
    base: dict[str, Any] = {"phases": ["on"] * len(boxes), "me": (640.0, 420.0), "units": [],
                            "size": SIZE, "rects": []}  # fmt: skip
    base.update(kw)
    return gi.label_reasons(boxes, **base)


def test_label_reasons_are_8s_item_exclusions() -> None:
    clear = (600.0, 300.0, 615.0, 320.0)
    assert _lr({1: clear}) == ([], [1])
    assert _lr({1: clear}, phases=["on", "settling"])[0] == ["item_settling"]
    assert _lr({1: clear}, phases=["on", "vanishing"])[0] == ["item_vanishing"]
    # at our feet: under our box and our HP bar (E3's (0, 0) views)
    feet = (632.0, 405.0, 648.0, 425.0)
    assert set(_lr({1: feet})[0]) == {"under_self", "under_self_bar"}
    # a unit's generic box (60 px wide, 100 px up to 6 px down from its anchor)
    assert _lr({1: clear}, units=[(607.0, 380.0)])[0] == ["under_unit"]
    assert _lr({1: clear}, units=[(700.0, 380.0)])[0] == []
    # two items stacked (IoU >= 0.5)
    assert "stacked" in _lr({1: clear, 2: (601.0, 301.0, 616.0, 321.0)})[0]
    assert _lr({1: clear, 2: (700.0, 300.0, 715.0, 320.0)}) == ([], [1, 2])
    # the UI: wholly behind it = not drawn (no label, no exclusion); partly = excluded
    assert _lr({1: clear}, rects=[(590, 290, 40, 40)]) == ([], [])
    assert _lr({1: clear}, rects=[(610, 290, 40, 40)])[0] == ["ui_partial"]
    assert _lr({1: (-5.0, 300.0, 10.0, 320.0)})[0] == ["edge_partial"]


def test_freeze_needs_12_samples_from_4_floor_items() -> None:
    measure = {"pooled": {"anchor_px": [-3.0, 1.0], "t_item": 0.79}}
    rows = [{"part": "E3:spots=0-3", "floor_id": 100 + i % 4, "reason": None, "ncc": 0.9,
             "dx": -3, "dy": 1} for i in range(12)]  # fmt: skip
    got = gi.freeze_params(measure, rows)
    assert got["anchor_px"] == [-3.0, 1.0] and got["t_item"] == 0.79 and got["floor_items"] == 4
    assert got["r_label"] == 6 and "STOP" not in got
    one_item = [{**r, "floor_id": 100} for r in rows]
    assert "floor items < 4" in gi.freeze_params(measure, one_item)["STOP"]
    assert (
        gi.freeze_params({"pooled": {"STOP": "3 samples < 12"}}, rows)["STOP"] == "3 samples < 12"
    )
    edge = [{**r, "dx": 10} for r in rows]  # at the +-10 search edge: not a sample
    assert gi.freeze_params(measure, edge)["samples"] == 0


def test_g2_is_the_median_offset_at_the_frozen_anchor() -> None:
    ok = [{"part": "e3b", "floor_id": i, "dx": d, "dy": -d} for i, d in enumerate([0, 1, 2, 3, 9])]
    g = gi.g2_summary(ok)
    assert g["verdict"] == "PASS" and g["median_abs_dx"] == 2 and g["n"] == 5
    far = [{**r, "dx": r["dx"] + 4} for r in ok]
    assert gi.g2_summary(far)["verdict"] == "STOP"
    assert gi.g2_summary([])["verdict"] == "NO_DATA"


def test_train_refuses_every_test_and_g2_reads_only_test3() -> None:
    import pytest

    spec = gi.ml.GEF10
    e3, e3b = "20261028T151136-rdp-stage-gef10-e3", "20261029T110813-rdp-stage-gef10-e3b"
    gi.check_role(spec, e3, None, "train")
    for sid in (e3b, "20261026T050000-rdp-rogue-a9", "20261025T190000-rdp-rogue-a7"):
        with pytest.raises(SystemExit):
            gi.check_role(spec, sid, None, "train")
    gi.check_role(spec, e3b, None, "test3")
    for sid in (e3, "20261026T050000-rdp-rogue-a9"):
        with pytest.raises(SystemExit):
            gi.check_role(spec, sid, None, "test3")
