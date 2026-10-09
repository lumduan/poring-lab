"""scripts/loot1.py (loot@1, demonstrations 3.20 / 3.20a): the pure parts -- the spots, the target
track and its death rule, the UI exclusion and the runtime check's combination."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[2].parent / "scripts"
S = 1_000_000_000


@pytest.fixture(scope="module")
def loot1() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("loot1", SCRIPTS / "loot1.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["loot1"] = mod
    spec.loader.exec_module(mod)
    return mod


def box(u: float, v: float, score: float = 0.9) -> Any:
    return SimpleNamespace(x0=u - 15, y0=v - 30, x1=u + 15, y1=v, score=score, cls="monster")


def test_spots_are_open_apart_seeded_and_fresh(loot1: Any) -> None:
    walk = np.ones((200, 300), dtype=bool)
    walk[100:110, 260:270] = False  # an obstacle in the region
    a = loot1.spots(walk, 7, 30)
    assert a == loot1.spots(walk, 7, 30) and a != loot1.spots(walk, 8, 30)
    assert len(a) == 30 and len(set(a)) == 30
    for i, p in enumerate(a):
        x0, y0, x1, y1 = loot1.REGION
        assert x0 <= p[0] <= x1 and y0 <= p[1] <= y1
        c = loot1.CLEAR
        assert walk[p[1] - c : p[1] + c + 1, p[0] - c : p[0] + c + 1].all()
        for q in a[:i]:
            assert max(abs(p[0] - q[0]), abs(p[1] - q[1])) >= loot1.APART
    assert len(loot1.spots(walk, 7, 10_000)) < 10_000  # fewer when the region cannot hold n


def test_the_track_follows_the_nearest_box_and_misses_far_ones(loot1: Any) -> None:
    t = loot1.Track((640.0, 400.0))
    t.update(1 * S, [box(650, 405), box(900, 400)])
    assert t.foot == (650.0, 405.0)
    t.update(2 * S, [box(900, 400)])  # only a far box: not the target
    assert t.sightings[-1].box is None and t.last_seen_ns == 1 * S


def test_death_needs_a_sighting_after_the_attack_then_frames_and_time_unseen(loot1: Any) -> None:
    t = loot1.Track((640.0, 400.0))
    t.update(10 * S, [box(640, 400)])
    attack = 11 * S
    for k in range(5):  # the detector lost it right after the click: never "dead"
        t.update(attack + k * S // 5, [])
    assert not t.gone(attack + 2 * S, attack)
    t.update(13 * S, [box(642, 401)])  # seen fighting after the click
    t.update(13 * S + S // 5, [])
    t.update(13 * S + 2 * S // 5, [])
    assert not t.gone(13 * S + S // 2, attack)  # 2 frames
    t.update(13 * S + 3 * S // 5, [])
    assert not t.gone(13 * S + 3 * S // 5, attack)  # 3 frames but 0.6 s
    assert t.gone(14 * S + S // 10, attack)  # 3 frames and >= GONE_S
    assert not t.gone(14 * S + S // 10, None)  # no attack, no death


def test_ui_windows_are_never_clicked(loot1: Any) -> None:
    x0, y0, x1, y1 = loot1.route_preview.UI_WINDOWS[0]
    assert loot1.in_ui((x0 + x1) / 2, (y0 + y1) / 2)
    assert loot1.in_ui(x1 + loot1.UI_PAD - 1, y0 + 1)
    assert not loot1.in_ui(640, 384)


def test_either_runtime_signal_is_enough(loot1: Any) -> None:
    f = loot1.runtime_obtained
    assert f((737, 2030), (738, 2030), False) == {"obtained": True, "weight_rose": True,
                                                  "cue": False}  # fmt: skip
    assert f((737, 2030), (737, 2030), True)["obtained"]  # sub-resolution: the cue alone
    assert not f((737, 2030), (737, 2030), False)["obtained"]
    assert not f(None, (738, 2030), False)["obtained"]  # no baseline: weight cannot count
    assert not f((737, 2030), (736, 2030), False)["obtained"]


def test_the_gm_cell_comes_from_two_equal_minimap_reads(
    loot1: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """3.20a amendment (Batt 2026-10-09): no /where in loot@1; the minimap readout, passive."""
    from poring_env import selfpos

    walk = np.ones((200, 300), dtype=bool)
    frame = np.zeros((4, 4, 4), np.uint8)
    rig = SimpleNamespace(screen=SimpleNamespace(grab=lambda *a: (0, frame)), walkable=walk,
                          digits=None)  # fmt: skip
    monkeypatch.setattr(loot1.time, "sleep", lambda s: None)
    monkeypatch.setattr(loot1.r, "game_region", lambda: (0, 0, 4, 4))
    for reads, want in (([(270, 104), (270, 104)], "ok"), ([(270, 104), (271, 104)], "disagree"),
                        ([None, None], "unread"), ([(290, 104)] * 2, "implausible")):  # fmt: skip
        it = iter(reads)
        monkeypatch.setattr(selfpos, "read_minimap",
                            lambda img, t, it=it: SimpleNamespace(xy=next(it)))  # fmt: skip
        got = loot1.minimap_cell(rig, (271, 103))
        assert got["why"] == want and (got["xy"] is not None) == (want == "ok"), got
