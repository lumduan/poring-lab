"""scripts/m4_validate.py: the M4 measurement (observed box by background differencing) and its
summary, on synthetic frames -- no client pixels committed."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]


def load() -> ModuleType:
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "m4_validate", ROOT / "scripts" / "m4_validate.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["m4_validate"] = mod
    spec.loader.exec_module(mod)
    return mod


m4 = load()


def scene() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(1)
    bg = np.clip(rng.normal((60, 120, 80), 4, (720, 1280, 3)), 0, 255).astype(np.uint8)
    frame = bg.copy()
    frame[300:340, 600:645] = (120, 120, 240)  # a 45 x 40 sprite
    frame[200, 100] = 255  # an isolated speck: the opening removes it
    return frame, bg


def test_the_observed_box_is_the_sprite_and_not_the_noise() -> None:
    frame, bg = scene()
    box = m4.observed_box(frame, bg, (590.0, 290.0, 655.0, 350.0), 622.0)
    assert box == (600, 300, 645, 340)


def test_no_change_under_the_anchor_column_is_no_box() -> None:
    frame, bg = scene()
    assert m4.observed_box(frame, bg, (800.0, 500.0, 840.0, 540.0), 820.0) is None


def test_iou_and_the_summary_verdicts() -> None:
    assert m4.iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert abs(m4.iou((0, 0, 10, 10), (5, 0, 15, 10)) - 1 / 3) < 1e-9
    rows = []
    for third, ratio in (("top", 0.80), ("bottom", 0.80), ("centre", 0.80)):
        for i in range(20):
            rows.append({"block": "outdoor-1" if i % 2 else "outdoor-2", "scene": "outdoor",
                         "third": third, "box_kind": "opaque", "iou": 0.9, "edges": [1, 1, 2, 1],
                         "ratio_h": ratio, "ratio_w": ratio, "scale": 0.9})  # fmt: skip
    out = m4.summarise(rows)
    assert out["iou_edge_verdicts"] == "applied"
    assert out["groups"]["outdoor/top"]["pass_iou"] and out["groups"]["outdoor/top"]["pass_edges"]
    assert out["outdoor_top_vs_bottom"]["pass"]  # the same ratio top and bottom: perspective right
    quad = m4.summarise([{**r, "box_kind": "quad"} for r in rows])
    assert quad["iou_edge_verdicts"].startswith("not comparable")
    assert "pass_iou" not in quad["groups"]["outdoor/top"]


def test_windows_pair_spawns_with_their_background() -> None:
    ev = [
        {"t_mono_ns": 1, "block": "outdoor-1", "scene": "outdoor", "species": None,
         "event": "background_start"},
        {"t_mono_ns": 5, "block": "outdoor-1", "scene": "outdoor", "species": None,
         "event": "background_end"},
        {"t_mono_ns": 10, "block": "outdoor-1", "scene": "outdoor", "species": "poring",
         "event": "spawned"},
        {"t_mono_ns": 50, "block": "outdoor-1", "scene": "outdoor", "species": "poring",
         "event": "killed"},
    ]  # fmt: skip
    (w,) = m4.windows(ev)
    assert (w["t0"], w["t1"], w["species"], w["background"]) == (10, 50, "poring", [(1, 5)])


def test_a_png_session_offers_the_h264_interface_measure_uses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-10-05: RDP-mode recordings are PNG shards; m4_validate reads them like H.264 ones."""
    frames = [({"frame_id": 7, "t_mono_ns": 100}, np.zeros((2, 2, 3), np.uint8)),
              ({"frame_id": 9, "t_mono_ns": 300}, np.ones((2, 2, 3), np.uint8))]  # fmt: skip
    monkeypatch.setattr(m4, "read_shard", lambda path: iter(frames))
    s = m4.PngSession(tmp_path, {"shards": ["shard-000000.tar"]})
    assert [(u.t_ns, u.frame_id) for u in s.units] == [(100, 7), (300, 9)]
    assert s.usable() == [7, 9]
    ((meta, img),) = list(s.frames([9]))
    assert meta["frame_id"] == 9 and int(img.max()) == 1
