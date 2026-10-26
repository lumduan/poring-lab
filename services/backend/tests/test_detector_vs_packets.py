"""The live detector against the packet truth (scripts/detector_vs_packets.py,
docs/planning/gef10-round2.md 4): the pure parts on SYNTHETIC boxes (no packets, no pixels)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import detector_vs_packets as dv  # noqa: E402

S = 1_000_000_000


def unit(gid: int, box: Any, job: int = 1273, in_view: bool = True) -> dict[str, Any]:
    return {"gid": gid, "job": job, "box": box, "state": "idle", "cell": (10, 10),
            "in_view": in_view}  # fmt: skip


def test_dist_bins_are_rounded_chebyshev_cells() -> None:
    assert dv.chebyshev((10, 10), (13, 5.4)) == 4.6
    assert [dv.dist_bin(d) for d in (0, 5.4, 5.5, 10.49, 10.5, 15.4, 15.5, 30)] == [
        "0-5", "0-5", "6-10", "6-10", "11-15", "11-15", "16+", "16+"]  # fmt: skip
    with pytest.raises(ValueError):
        dv.dist_bin(-3)


def test_recall_is_any_detection_centre_in_the_box_and_one_to_one_beside() -> None:
    """Two overlapping units and ONE detection between them: both are hit (the brief's recall),
    one is matched one-to-one (the nearer centre); a unit out of view is not scored."""
    a = unit(1, (100, 100, 160, 180))
    b = unit(2, (130, 100, 190, 180))
    far = unit(3, (600, 100, 660, 180), in_view=False)
    det = [(150, 110, 170, 170)]  # centre (160, 140): inside a (its edge) and b, b's centre
    rows, verdicts = dv.score_capture([a, b, far], det)
    assert [(r["gid"], r["hit"], r["hit_1to1"]) for r in rows] == [(1, True, False),
                                                                   (2, True, True)]  # fmt: skip
    assert verdicts == ["tp"]


def test_precision_verdicts_tp_dying_self_other() -> None:
    """A detection on a unit out of view is still a true one (the sprite is drawn); the rest are
    split: on a dying unit, on our own character, elsewhere."""
    off = unit(1, (0, 0, 40, 40), in_view=False)
    nosheet = {"gid": 2, "job": 1023, "box": None, "in_view": False}
    dets = [
        (10, 10, 30, 30),
        (300, 300, 320, 320),
        (630, 330, 650, 380),
        (900, 500, 920, 520),
        (45, 10, 65, 30),
    ]  # the last: centre (55, 20), 15 px right of the unit's box
    rows, verdicts = dv.score_capture([off, nosheet], dets, dying=[(290, 290, 330, 330)],
                                      self_box=(620, 300, 660, 380))  # fmt: skip
    assert rows == [] and verdicts == ["tp", "dying", "self", "other", "near_unit"]


def test_a_unit_with_no_detection_is_a_miss() -> None:
    rows, verdicts = dv.score_capture([unit(1, (100, 100, 160, 180))], [])
    assert rows[0]["hit"] is False and rows[0]["hit_1to1"] is False and verdicts == []
    assert dv.tally(rows) == {"n": 1, "hit": 0, "recall": 0.0, "hit_1to1": 0, "recall_1to1": 0.0}
    assert dv.tally([])["recall"] is None


def test_episodes_cut_at_gaps_and_time_the_first_hit() -> None:
    rows = [
        {"gid": 7, "job": 1023, "t": 0 * S, "hit": False, "dist": 12.0},
        {"gid": 7, "job": 1023, "t": 1 * S, "hit": False, "dist": 11.0},
        {"gid": 7, "job": 1023, "t": 2 * S, "hit": True, "dist": 10.0},
        {"gid": 7, "job": 1023, "t": 10 * S, "hit": False, "dist": 4.0},  # a new episode: > 2 s
        {"gid": 8, "job": 1031, "t": 1 * S, "hit": True, "dist": 3.0},
    ]  # fmt: skip
    eps = dv.episodes(rows)
    got = sorted((e["gid"], e["t0"], e["captures"], e["dist0"], e["delay_s"]) for e in eps)
    assert got == [(7, 0, 3, 12.0, 2.0), (7, 10 * S, 1, 4.0, None), (8, 1 * S, 1, 3.0, 0.0)]


def test_species_keys_and_percentiles() -> None:
    assert dv.species_key(1273) == "1273 Orc Lady" and dv.species_key(1190) == "other"
    assert dv.percentile([100.0, 200.0, 300.0], 50) == 200.0 and dv.percentile([], 95) is None
