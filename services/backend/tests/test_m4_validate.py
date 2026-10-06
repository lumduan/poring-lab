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


# --- the re-run (phase3-plan §5b), pre-registered before its session ------------------------


def test_the_local_background_is_the_last_gap_before_the_spawn() -> None:
    ev = [
        {"t_mono_ns": 1, "block": "outdoor-top", "scene": "outdoor", "species": None,
         "event": "background_start"},
        {"t_mono_ns": 5, "block": "outdoor-top", "scene": "outdoor", "species": None,
         "event": "background_end"},
        {"t_mono_ns": 10, "block": "outdoor-top", "scene": "outdoor", "species": "poring",
         "event": "spawned", "cell": [261, 114]},
        {"t_mono_ns": 50, "block": "outdoor-top", "scene": "outdoor", "species": "poring",
         "event": "killed"},
        {"t_mono_ns": 55, "block": "outdoor-top", "scene": "outdoor", "species": "poring",
         "event": "background_end"},
        {"t_mono_ns": 60, "block": "outdoor-top", "scene": "outdoor", "species": "poring",
         "event": "spawned", "cell": [262, 114]},
        {"t_mono_ns": 90, "block": "outdoor-top", "scene": "outdoor", "species": "poring",
         "event": "killed"},
    ]  # fmt: skip
    first, second = m4.windows(ev)
    assert first["background_local"] == [(1, 5)] and second["background_local"] == [(50, 55)]
    assert (first["spawn_index"], second["spawn_index"]) == (0, 1)  # the A/A halves: even / odd
    assert second["cell"] == [262, 114]


def test_the_pre_registered_exclusions() -> None:
    roi = (500.0, 400.0, 700.0, 600.0)
    pred = (580.0, 460.0, 620.0, 500.0)
    keep = (582.0, 462.0, 619.0, 499.0)
    assert m4.exclusion(keep, pred, roi, False) is None
    assert m4.exclusion((500.0, 462.0, 619.0, 499.0), pred, roi, False) == "roi_edge"
    assert m4.exclusion((560.0, 440.0, 640.0, 520.0), pred, roi, False) == "merged_area"  # 4x
    assert m4.exclusion(keep, pred, roi, True) == "occluder"
    ui_roi = (0.0, 0.0, 300.0, 400.0)  # under the Basic Information window (0,0,222,325)
    assert m4.exclusion((100.0, 100.0, 140.0, 140.0), (100.0, 100.0, 140.0, 140.0), ui_roi,
                        False) == "ui"  # fmt: skip
    edge_roi = (-10.0, 600.0, 200.0, 800.0)
    assert m4.exclusion((0.0, 650.0, 40.0, 690.0), (0.0, 650.0, 40.0, 690.0), edge_roi,
                        False) == "screen_edge"  # fmt: skip


def test_the_rerun_summary_is_per_species_with_aa_halves_counts_and_k() -> None:
    rows = []
    for species, k in (("poring", 0.1333), ("lunatic", 0.1335)):
        for third in ("top", "bottom"):
            for spawn in range(6):
                for _ in range(4):
                    rows.append({"block": f"outdoor-{third}", "scene": "outdoor", "third": third,
                                 "species": species, "spawn": spawn, "box_kind": "opaque",
                                 "iou": 0.9, "edges": [1, 1, 1, 1], "ratio_h": 0.95,
                                 "ratio_w": 1.0, "scale": 1.0, "k_h": k, "k_w": k})  # fmt: skip
    out = m4.summarise(rows, per_species=True)
    cond = out["conditions"]["outdoor/top/poring"]
    assert cond["enough"] and cond["spawns"] == 6 and cond["n"] == 24 and cond["aa"]["pass"]
    assert out["outdoor_top_vs_bottom/poring"]["pass"]
    assert out["k"]["within_2pct_of"] == ["nostalro"] and out["k"]["pass"]
    few = m4.summarise(rows[:12], per_species=True)  # 3 spawns: below the pre-registered minimum
    assert not few["conditions"]["outdoor/top/poring"]["enough"]
    off = m4.summarise([{**r, "k_h": 0.15} for r in rows], per_species=True)
    assert not off["k"]["pass"]  # within neither prior: a finding, never a fit


def test_reconstruction_keeps_a_thin_attached_tuft_and_drops_noise() -> None:
    """M4 re-run step 1 (2026-10-06): the 1-px opening deleted the Poring's tuft (1-2 px wide), so
    the observed box stopped below the top the client draws. Opening by reconstruction grows back
    what is connected to the surviving body; isolated specks still go."""
    mask = np.zeros((40, 40), bool)
    mask[20:35, 10:30] = True  # the body
    mask[12:20, 19] = True  # a 1-px-wide tuft attached to its top
    mask[3, 3] = True  # an isolated speck
    opened, rec = m4.opened(mask), m4.reconstructed(mask)
    assert not opened[12:20, 19].any() and rec[12:20, 19].all()  # the tuft: lost vs kept
    assert not opened[3, 3] and not rec[3, 3]  # the speck: gone in both
    assert rec[20:35, 10:30].all()
    frame = np.zeros((60, 60, 3), np.uint8)
    frame[mask[:40, :40].nonzero()] = 200
    bg = np.zeros_like(frame)
    pred = (10.0, 15.0, 30.0, 35.0)
    assert m4.observed_box(frame, bg, pred, 20.0, "open")[1] == 20  # top at the body
    assert m4.observed_box(frame, bg, pred, 20.0, "reconstruct")[1] == 12  # top at the tuft
