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
