"""poring_vision.detect_bench (bot-server-migration.md 19): its pure helpers, on the host."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from poring_vision import detect_bench as db


def test_parse_configs() -> None:
    assert db.parse_configs("live, f16") == ["live", "f16"]
    for bad in ("", "live,live", "fp8", "live,cpu"):
        with pytest.raises(SystemExit):
            db.parse_configs(bad)


def test_canvas_of_pads_rows_like_pad_canvas() -> None:
    img = np.full((720, 1280, 3), 7, np.uint8)
    c = db.canvas_of(img)
    assert c.shape == (736, 1280, 3) and c.dtype == np.uint8
    assert (c[:8] == 114).all() and (c[728:] == 114).all() and (c[8:728] == 7).all()
    with pytest.raises(ValueError):
        db.canvas_of(np.zeros((720, 1000, 3), np.uint8))  # would need the resize
    with pytest.raises(ValueError):
        db.canvas_of(np.zeros((800, 1280, 3), np.uint8))


def head(n: int = 10, nc: int = 2) -> np.ndarray:
    return np.zeros((1, 4 + nc, n), np.float32)


def test_raw_diff_counts_only_anchors_above_conf() -> None:
    a, b = head(), head()
    a[0, :4, 3] = [100, 200, 30, 40]
    b[0, :4, 3] = [100.5, 199.0, 30, 40]
    a[0, 4, 3], b[0, 4, 3] = 0.80, 0.78
    a[0, :4, 7], b[0, :4, 7] = 999, 0  # below conf in both: ignored
    a[0, 5, 5], b[0, 5, 5] = 0.26, 0.24  # crosses the threshold: one box could vanish
    d = db.raw_diff(a, b, 0.25)
    assert d["box_px"] == pytest.approx(1.0) and d["score"] == pytest.approx(0.02, abs=1e-6)
    assert d["cross"] == 1 and d["n_ref"] == 2 and d["n_got"] == 1
    assert db.raw_diff(head(), head()) == {"box_px": 0.0, "score": 0.0, "cross": 0,
                                           "n_ref": 0, "n_got": 0}  # fmt: skip
    with pytest.raises(ValueError):
        db.raw_diff(head(10), head(11))


def test_freq_reader(tmp_path: Path) -> None:
    (tmp_path / "card1").mkdir()
    (tmp_path / "card1" / "gt_act_freq_mhz").write_text("2450\n")
    assert db.freq_reader(str(tmp_path / "card*" / "gt_act_freq_mhz"))() == 2450
    assert db.freq_reader(str(tmp_path / "none*" / "x"))() is None
