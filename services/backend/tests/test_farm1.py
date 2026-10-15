"""farm1.py's pure parts (Batt 2026-10-15 ~20:25: engage like a player)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import farm1  # noqa: E402

from poring_dataset import deathcell as dcm  # noqa: E402

S = 1_000_000_000


@dataclass
class Box:
    x0: float
    y0: float
    x1: float
    y1: float


def at(u: float, v: float, w: float = 36, h: float = 36) -> Box:
    return Box(u - w / 2, v - h, u + w / 2, v)


def test_focus_is_still_only_after_half_a_second_of_fresh_still_frames() -> None:
    fo = farm1.Focus((100.0, 100.0))
    fo.update(0, [at(100, 100), at(400, 300)])
    fo.update(S // 4, [at(101, 100)])
    assert fo.still(S // 4) is None  # 0.25 s of stillness
    fo.update(S * 6 // 10, [at(101, 101)])
    assert fo.still(S * 6 // 10) is not None
    assert fo.still(S * 6 // 10 + S) is None  # the latest frame is no longer fresh
    assert not fo.hopped


def test_focus_drops_a_hop_and_ignores_far_boxes() -> None:
    fo = farm1.Focus((100.0, 100.0))
    fo.update(0, [at(100, 100)])
    fo.update(S // 3, [at(400, 300)])  # outside the focus window: another monster
    assert len(fo.seen) == 1 and not fo.hopped
    fo.update(S * 2 // 3, [at(160, 100)])  # 60 px: it hopped
    assert fo.hopped
    assert fo.unseen_s(S * 2) is not None


def test_size_gate_scales_by_the_camera() -> None:
    assert farm1.native_size(at(0, 0, 37, 36), 1.0) < farm1.MAX_NATIVE_PX  # Poring / Drops
    assert farm1.native_size(at(0, 0, 51, 53), 1.0) > farm1.MAX_NATIVE_PX  # Creamy
    assert farm1.native_size(at(0, 0, 46, 48), 0.9) > farm1.MAX_NATIVE_PX  # a far Creamy


def test_damage_cue_counts_new_white_pixels_above_the_box_only() -> None:
    before = np.zeros((200, 200, 3), np.uint8)
    after = before.copy()
    box = at(100, 150)  # y0 = 114
    after[80:100, 90:110] = 255  # numbers above the box
    after[130:140, 90:110] = 255  # inside the box: not counted (a white Lunatic)
    assert farm1.damage_cue(before, after, box) == 400


def test_gone_needs_frames_and_time() -> None:
    sight = [dcm.Sighting(0, (0, 0, 1, 1))] + [dcm.Sighting(k * S // 4, None) for k in (1, 2, 3)]
    assert not farm1._gone(sight, S)  # 3 frames, 1.0 s
    assert farm1._gone(sight, 2 * S)  # 3 frames, 2.0 s
