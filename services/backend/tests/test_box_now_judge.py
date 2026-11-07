"""scripts/box_now_judge.py: pilot p8's bars (rogue-xmas02.md 4N). p7's real counts (19 box misses
of 25 box fights, its section 5 row) are the E2 positive case, checked by hand on its events."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import box_now_judge as bj  # noqa: E402

LOG = [
    "[13:00:00] R3 schedule started [13:00:00 ICT / 06:00:00 UTC]",
    "[13:03:00] R3 pause poring-lab-vision-worker-1 [13:03:00 ICT / 06:03:00 UTC]",
    "[13:06:00] R3 unpause poring-lab-vision-worker-1 [13:06:00 ICT / 06:06:00 UTC]",
    "[13:09:00] R3 pause poring-lab-vision-worker-1 [13:09:00 ICT / 06:09:00 UTC]",
]


def at(hms: str) -> float:
    return datetime.fromisoformat(f"2026-11-07T{hms}+07:00").timestamp()


def test_the_off_windows_come_from_the_steps_r3_lines() -> None:
    w = bj.r3_off_windows(LOG, "2026-11-07")
    assert w == [(at("13:03:00"), at("13:06:00")), (at("13:09:00"), float("inf"))]
    assert bj.paused(at("13:04:00"), w) and not bj.paused(at("13:07:00"), w)


def test_g1_counts_only_gpu_requests_outside_the_off_windows() -> None:
    w = bj.r3_off_windows(LOG, "2026-11-07")
    rows = [{"t_wall": at("13:01:00"), "prefer": "gpu", "path": "gpu"}] * 9 + [
        {"t_wall": at("13:01:30"), "prefer": "gpu", "path": "cpu", "reason": "down"},
        {"t_wall": at("13:04:00"), "prefer": "gpu", "path": "cpu", "reason": "TimeoutError: x"},
        {"t_wall": at("13:02:00"), "prefer": "cpu", "path": "cpu"},  # the CPU arm: not asked
    ]
    g = bj.g1(rows, w)
    assert (g["asked_outside_off"], g["gpu"], g["share"], g["pass"]) == (10, 9, 0.9, True)
    assert g["not_gpu_reasons"] == {"down": 1} and g["asked_in_off"] == 1


def test_e2_and_g2_from_the_events() -> None:
    ev = [{"kind": "engage", "by": "box"}] * 4 + [{"kind": "engage", "by": "battle_log"}]
    ev += [{"kind": "box_miss"}] * 2
    ev += [
        {"kind": "box_target", "arm": "gpu", "path": "gpu", "fresh": True, "box": [1, 2, 3, 4],
         "verdicts": ["sword"], "struck": True, "boxes_after_ms": 40, "det_ms": 30.0,
         "hover_from_grab_ms": 50},
        {"kind": "box_target", "arm": "cpu", "path": "cpu", "fresh": True, "box": None,
         "verdicts": [], "struck": False, "boxes_after_ms": 260, "det_ms": 220.0},
        {"kind": "box_target", "arm": "gpu", "path": "cpu", "fresh": True, "box": [1, 2, 3, 4],
         "verdicts": ["unknown"], "struck": False, "boxes_after_ms": 300, "det_ms": 230.0},
    ]  # fmt: skip
    r = bj.judge(ev, [], [])
    assert r["e2"] == {"box_fights": 4, "box_misses": 2, "share": 0.5, "pass": True}
    assert r["g2"] == {"gpu_p50_ms": 40.0, "cpu_p50_ms": 280.0, "pass": True}
    assert r["by_arm"]["gpu"]["n"] == 2 and r["by_path"]["cpu"]["n"] == 2
    assert r["by_path"]["gpu"]["struck_of_hovered"] == 1.0
    assert r["by_arm"]["cpu"]["hovered"] == 0 and r["by_arm"]["cpu"]["struck_of_hovered"] is None
