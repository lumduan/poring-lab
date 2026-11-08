"""scripts/detect_speed.py (rogue-xmas02.md 4T): p13's D1 / D2 summary."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import detect_speed as ds  # noqa: E402


def test_detections_counts_paths_and_gpu_times() -> None:
    rows = [{"path": "gpu", "ms": m} for m in (10.0, 20.0, 30.0, 40.0)] + [
        {"path": "fallback", "ms": 120.0}]  # fmt: skip
    got = ds.detections(rows)
    assert got["calls"] == 5 and got["paths"] == {"gpu": 4, "fallback": 1}
    assert got["gpu_share"] == pytest.approx(0.8)
    assert got["gpu_ms_p50"] == 25.0 and got["gpu_ms_p95"] == 40.0
    assert ds.detections([])["gpu_ms_p50"] is None


def test_box_targets_medians_and_struck() -> None:
    ev = [{"kind": "box_target", "det_ms": 60, "boxes_after_ms": 85, "verdict_from_grab_ms": 300,
           "struck": True},
          {"kind": "box_target", "det_ms": 70, "boxes_after_ms": 95, "struck": False},
          {"kind": "strike", "det_ms": 999}]  # fmt: skip
    got = ds.box_targets(ev)
    assert got["box_targets"] == 2 and got["struck"] == 1
    assert got["det_ms_p50"] == 65.0 and got["boxes_after_ms_p50"] == 90.0
    assert got["verdict_from_grab_ms_p50"] == 300.0 and got["verdict_from_grab_ms_n"] == 1
    assert got["hover_from_grab_ms_p50"] is None


def test_main_reads_a_session(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "detections.jsonl").write_text(json.dumps({"path": "gpu", "ms": 20.5}) + "\n\n")
    (tmp_path / "events.jsonl").write_text(json.dumps({"kind": "box_target", "det_ms": 18}) + "\n")
    assert ds.main([str(tmp_path)]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["gpu_ms_p50"] == 20.5 and rep["det_ms_p50"] == 18.0
