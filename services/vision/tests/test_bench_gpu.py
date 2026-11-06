"""poring_vision.bench_gpu (Batt 2026-11-07): the pure parts, without a GPU."""

from __future__ import annotations

import pytest

from poring_vision import bench_gpu as bg


def test_calls_that_span_an_r3_pause_are_left_out() -> None:
    kept, paused = bg.split_paused([12.0, 15.5, 60_000.0, 999.9, 1000.0])
    assert kept == [12.0, 15.5, 999.9] and paused == 2


def test_weights_are_name_equals_path_each_name_once() -> None:
    assert bg.parse_weights(["v1=/a.pt", "xmas02=/b.pt"]) == {"v1": "/a.pt", "xmas02": "/b.pt"}
    for bad in (["v1"], ["=/a.pt"], ["v1="], ["v1=/a", "v1=/b"]):
        with pytest.raises(SystemExit):
            bg.parse_weights(bad)


def test_the_summary_drops_paused_calls_from_every_part() -> None:
    walls = [10.0, 20.0, 5000.0]
    speeds = [{"preprocess": 1.0, "inference": 8.0, "postprocess": 1.0},
              {"preprocess": 2.0, "inference": 16.0, "postprocess": 2.0},
              {"preprocess": 3.0, "inference": 4000.0, "postprocess": 3.0}]  # fmt: skip
    s = bg.summarise(walls, speeds)
    assert s["paused_calls"] == 1 and s["wall_ms"]["n"] == 2 and s["wall_ms"]["max"] == 20.0
    assert s["inference_ms"]["n"] == 2 and s["inference_ms"]["max"] == 16.0
    assert bg.IOU == 0.5 and bg.CONF == 0.25 and bg.IMGSZ == (736, 1280)  # unit_detector's
