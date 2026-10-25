"""gef10 round-2 measurement (docs/planning/gef10-round2-measure.md; scripts/gef10_r2_measure.py):
the pure parts on SYNTHETIC data (no client pixels, no GAT)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import gef10_r2_measure as m  # noqa: E402

from poring_dataset.shards import encode_png  # noqa: E402


def grass(h: int = 180, w: int = 1280, seed: int = 7) -> np.ndarray:
    """A textured green-brown ground, like the field behind the notice."""
    rng = np.random.default_rng(seed)
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[..., 0] = rng.integers(60, 140, (h, w))
    img[..., 1] = rng.integers(80, 160, (h, w))
    img[..., 2] = rng.integers(40, 110, (h, w))
    return img


def draw_notice(img: np.ndarray, x0: int, y0: int, x1: int, y1: int, text: bool = True) -> None:
    """The client's notice as measured on FIT frames: a white box (outer edge x0..x1-1,
    y0..y1-1), a 1-px grey (~192) border line 2 px inside it, white inside, an icon and text."""
    img[y0:y1, x0:x1] = 255
    g = (192, 192, 192)
    img[y0 + 2, x0 + 4 : x1 - 4] = g
    img[y1 - 3, x0 + 4 : x1 - 4] = g
    img[y0 + 4 : y1 - 4, x0 + 2] = g
    img[y0 + 4 : y1 - 4, x1 - 3] = g
    if text:
        img[y0 + 5 : y0 + 25, x0 + 15 : x0 + 35] = (120, 90, 200)  # the item icon
        for k in range(x0 + 45, x1 - 20, 9):  # glyphs
            img[y0 + 10 : y0 + 20, k : k + 5] = 0


def test_finds_the_measured_notice() -> None:
    img = grass()
    draw_notice(img, 541, 76, 732, 106)
    assert m.find_notices(img) == [(541.0, 76.0, 732.0, 106.0)]


def test_finds_a_wider_notice_and_not_a_plain_frame() -> None:
    img = grass(seed=3)
    assert m.find_notices(img) == []  # the negative case: ground only
    draw_notice(img, 541, 76, 800, 106)
    assert m.find_notices(img) == [(541.0, 76.0, 800.0, 106.0)]


def test_rejects_look_alikes() -> None:
    img = grass(seed=5)
    img[76:106, 541:732] = 255  # white, but no border line
    assert m.find_notices(img) == []
    img = grass(seed=5)
    img[90, 400:700] = 192  # a lone grey line on the ground
    assert m.find_notices(img) == []
    img = grass(seed=5)
    draw_notice(img, 541, 76, 571, 106, text=False)  # too short a border (< MIN_RUN)
    assert m.find_notices(img) == []
    img = grass(h=400, seed=5)
    draw_notice(img, 541, 300, 732, 330)  # outside the top band
    assert m.find_notices(img) == []


def test_overlap_and_cover() -> None:
    n = (541.0, 76.0, 732.0, 106.0)
    assert m.overlap_area((500.0, 28.0, 565.0, 118.0), n) == 24.0 * 30.0
    assert m.overlap_area((500.0, 106.0, 565.0, 150.0), n) == 0.0  # touching is no overlap
    assert m.covered_share((560.0, 80.0, 570.0, 100.0), [n]) == 1.0
    assert m.covered_share((500.0, 110.0, 520.0, 130.0), [n]) == 0.0
    assert m.overlap_area(m.grown((530.0, 110.0, 540.0, 130.0), 16.0), n) > 0


def test_step_map_and_near_step() -> None:
    alt = np.zeros((10, 10))
    alt[:, 7:] = 40.0  # a plateau east of x 6 (a cliff between x 6 and 7)
    step = m.step_map(alt)
    assert step[5, 6] == 40.0 and step[5, 7] == 40.0
    assert step[5, 5] == 0.0 and step[5, 9] == 0.0
    assert not m.near_step(step, (4, 5), 1, 10.0)
    assert m.near_step(step, (4, 5), 2, 10.0)  # x 6 is within 2
    assert not m.near_step(step, (4, 5), 2, 40.0)  # strictly greater than H
    assert m.nearest_step(step, (2, 5), 10.0) == 4
    assert m.nearest_step(np.zeros((5, 5)), (2, 2), 1.0) is None


def test_label_flags_and_removed() -> None:
    alt = np.zeros((20, 20))
    alt[:, 15:] = 40.0
    step = m.step_map(alt)
    notice = [(541.0, 76.0, 732.0, 106.0)]
    fl = m.label_flags((500.0, 28.0, 565.0, 118.0), notice, (12, 10), step, 10.0)
    assert fl["notice"] and fl["terrain_r2"] and not fl["terrain_r1"]
    assert m.removed(fl, "N") and m.removed(fl, "T") and m.removed(fl, "NT")
    fl = m.label_flags((100.0, 300.0, 140.0, 340.0), notice, (5, 10), step, 10.0)
    assert not (fl["notice"] or fl["terrain_r1"] or fl["terrain_r2"])
    assert not m.removed(fl, "NT")
    fl = m.label_flags((100.0, 300.0, 140.0, 340.0), [], None, step, 10.0)
    assert fl["terrain_r2"] is None and not m.removed(fl, "T")


def test_refuses_test_parts() -> None:
    assert m.refuse_test("20261025T200922-rdp-rogue-pilot") == "FIT"
    assert m.refuse_test("20261026T014529-rdp-w2") == "TRAIN"
    for part in ("20261026T010738-rdp-rogue-a7", "20261026T023132-rdp-rogue-a8",
                 "20261025T195325-rdp-ow1:spots=11,12,13,14", "20261025T195325-rdp-ow1",
                 "20261026T031500-rdp-rogue-a9", "20261026T030500-rdp-rogue-a5b",
                 "20261025T120000-rdp-unknown"):  # fmt: skip
        with pytest.raises(SystemExit):
            m.refuse_test(part)


def test_pickup_times_and_neighbours() -> None:
    ev = [{"type": "pickup_result", "ok": True, "t_mono_ns": 5},
          {"type": "pickup_result", "ok": False, "t_mono_ns": 7},
          {"type": "act", "t_mono_ns": 8},
          {"type": "pickup_result", "ok": True, "t_mono_ns": 2}]  # fmt: skip
    times = m.pickup_times(ev)
    assert times == [2, 5]
    assert m.last_before(times, 4) == 2 and m.last_before(times, 1) is None
    assert m.first_after(times, 2) == 5 and m.first_after(times, 5) is None


def test_validation_cases() -> None:
    n = [541.0, 76.0, 732.0, 106.0]
    part = {"part": "p", "frames": [
        {"frame_id": 1, "pickup_age_s": 1.2, "notices": [n]},   # positive, detected
        {"frame_id": 2, "pickup_age_s": 3.9, "notices": []},    # positive, missed
        {"frame_id": 3, "pickup_age_s": 6.0, "notices": []},    # the fade zone: not scored
        {"frame_id": 4, "pickup_age_s": None, "notices": []},   # negative, clear
        {"frame_id": 5, "pickup_age_s": 12.0, "notices": [n]},  # negative, detected
    ]}  # fmt: skip
    v = m.validation([part])
    assert v["positive"]["n"] == 2 and v["positive"]["detected"] == 1
    assert v["positive"]["listed"] == {"missed": ["p#2"]}
    assert v["negative"]["n"] == 2 and v["negative"]["clear"] == 1
    assert v["negative"]["listed"] == {"detected": ["p#5"]}
    assert v["by_pickup_age_s"]["1-2"] == {"frames": 1, "detected": 1}


def test_read_top_rows(tmp_path: Path) -> None:
    img = grass(h=200, w=64)
    data = encode_png(img)  # BGR in, RGB in the file
    blob = b"\0" * 100 + data + b"\0" * 50
    shard = tmp_path / "shard.tar"
    shard.write_bytes(blob)
    top = m.read_top_rows(shard, 100, len(data), rows=30)
    assert top.shape == (30, 64, 3)
    assert np.array_equal(top, img[:30, :, ::-1])
    with pytest.raises(ValueError):
        m.read_top_rows(shard, 0, len(data), rows=30)
