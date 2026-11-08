"""scripts/gpu_live_parity.py: boxes match one to one only within the same class and species; the
server's mode (--ov-preproc) is read from its step log, never assumed."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import gpu_live_parity as glp  # noqa: E402


def test_the_same_box_of_another_class_or_species_is_no_match() -> None:
    a = [10.0, 10.0, 50.0, 60.0, 0.9, "monster", "cookie"]
    cpu = [a, [100.0, 10.0, 140.0, 60.0, 0.8, "player", None]]
    gpu = [[10.5, 10.0, 50.0, 60.0, 0.9, "monster", "cookie"],
           [100.0, 10.0, 140.0, 60.0, 0.8, "npc", None],
           [10.0, 10.0, 50.0, 60.0, 0.7, "monster", "cookie_xmas"]]  # fmt: skip
    m = glp.match_same_class(cpu, gpu, 0.7)
    assert [(i, j) for i, j, _ in m] == [(0, 0)]


def test_one_to_one_greedy_from_the_best_pair() -> None:
    c = [[0.0, 0.0, 10.0, 10.0, 0.9, "monster", None], [1.0, 0.0, 11.0, 10.0, 0.9, "monster", None]]
    g = [[0.0, 0.0, 10.0, 10.0, 0.9, "monster", None]]
    m = glp.match_same_class(c, g, 0.5)
    assert [(i, j) for i, j, _ in m] == [(0, 0)] and m[0][2] == 1.0


START = {"detect_server": "listening", "t": "2026-11-08T05:00:00+0000",
         "socket": "/detect/detect.sock", "models": {"v1": "32b448a1d197"},
         "imgsz": [736, 1280], "backend": "openvino", "device": "GPU", "ov_preproc": "gpu",
         "precision": "f32"}  # fmt: skip


def step_log(tmp_path: Path, start: dict[str, object] | None) -> Path:
    """A guarded step's log as the worker writes it: a runtime warning, the start line, stats."""
    lines = ["WARNING: Resizable BAR not detected for device 0000:0c:00.0"]
    if start is not None:
        lines.append(json.dumps(start))
    lines += [json.dumps({"detect_server": "stats", "ov_preproc": "gpu", "frames": 0}), '{"cut']
    p = tmp_path / "poring-guarded-execdev-vision.log"
    p.write_text("\n".join(lines))
    return p


def test_the_servers_start_line_is_read_from_its_step_log(tmp_path: Path) -> None:
    assert glp.server_start(step_log(tmp_path, START)) == START
    assert glp.server_start(step_log(tmp_path, None)) is None


def test_a_server_in_another_mode_is_refused_before_any_work(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "no-refs.json"  # never read: the check comes first
    base = ["--refs", str(missing), "--out", str(tmp_path / "o.json")]
    log = step_log(tmp_path, {**START, "ov_preproc": "cpu"})
    assert glp.main([*base, "--server-log", str(log), "--expect-ov-preproc", "gpu"]) == 2
    assert "REFUSED" in capsys.readouterr().err
    log = step_log(tmp_path, None)  # no start line (yet): refused too
    assert glp.main([*base, "--server-log", str(log), "--expect-ov-preproc", "cpu"]) == 2
    with pytest.raises(SystemExit):
        glp.main([*base, "--expect-ov-preproc", "gpu"])  # it needs the log
    assert not (tmp_path / "o.json").exists()
