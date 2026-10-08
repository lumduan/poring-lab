"""scripts/route_preview.py: the LIVE route preview is anchored to the WORLD (Batt 2026-10-08). The
route stays map cells and is re-projected from the character's current position; the consumed part
fades; display only."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
MS = 1_000_000


@pytest.fixture(scope="module")
def rp() -> ModuleType:
    spec = importlib.util.spec_from_file_location("route_preview", SCRIPTS / "route_preview.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["route_preview"] = mod
    spec.loader.exec_module(mod)
    return mod


class Cam:  # 30 px per cell east, 20 px per cell north; the character's feet at (640, 360)
    def project(self, cells: Any, alt: Any = None) -> np.ndarray:
        c = np.asarray(cells, dtype=float)
        return np.stack([640 + 30 * c[:, 0], 360 - 20 * c[:, 1]], axis=1)


def preview(rp: ModuleType, sent: list[str]) -> Any:
    return rp.LivePreview(sent.append, Cam(), None, (80, 77, 1280, 720), (1440, 900), "t")


def px(pt: dict[str, Any]) -> tuple[float, float]:
    return round(pt["x"] * 1440 - 80, 1), round(pt["y"] * 900 - 77, 1)


def test_the_walk_timing_is_the_engines(rp: ModuleType) -> None:
    tl = rp.timeline((0, 0), [(1, 1), (2, 1)], 0, 150)
    assert [t // MS for _, t in tl] == [0, 210, 360]  # a diagonal 1.4 x 150, then a straight 150
    assert rp.position_at(tl, 105 * MS) == (0.5, 0.5)
    assert rp.position_at(tl, 10_000 * MS) == (2.0, 1.0)


def test_while_walking_the_feet_stay_centred_and_the_goal_comes_closer(rp: ModuleType) -> None:
    """The bug: a route computed once in screen pixels floats while the camera follows us. Live,
    the line starts at OUR feet (screen centre) and the goal ring slides towards us."""
    lp = preview(rp, [])
    lp.set_route((100, 100), [(106, 100)], (106, 100), click=(103, 100))
    m0 = lp.build(0)
    assert px(m0["points"][0]) == (640.0, 360.0)
    goal0 = next(px(p) for p in m0["points"] if p["kind"] == "goal")
    assert goal0 == (640.0 + 180, 360.0)
    lp.walk((100, 100), [(101, 100), (102, 100), (103, 100)], 0, 150)
    t = int(rp.WALK_START_S * 1e9) + 300 * MS  # two cells walked
    m = lp.build(t)
    assert px(m["points"][0]) == (640.0, 360.0)  # still our feet
    goal = next(px(p) for p in m["points"] if p["kind"] == "goal")
    assert goal == (640.0 + 120, 360.0)  # the goal is now 4 cells away: anchored to the world
    assert not any(p["kind"] == "click" for p in m["points"])  # the click is spent


def test_the_walked_stretch_fades_and_is_dropped(rp: ModuleType) -> None:
    lp = preview(rp, [])
    lp.set_route((100, 100), [(106, 100)], (106, 100))
    lp.walk((100, 100), [(101, 100), (102, 100), (103, 100)], 0, 150)
    t0 = int(rp.WALK_START_S * 1e9)
    for k in range(0, 8):
        m = lp.build(t0 + k * 50 * MS)
    assert m["passed"] and all(0 <= s["age_ms"] < 400 for s in m["passed"])
    late = lp.build(t0 + 2_000 * MS)  # long arrived: nothing walked recently
    assert late["passed"] == []
    assert px(late["points"][0]) == (640.0, 360.0)


def test_a_fix_snaps_and_clear_sends_an_empty_live_preview(rp: ModuleType) -> None:
    sent: list[str] = []
    lp = preview(rp, sent)
    lp.set_route((100, 100), [(106, 100)], (106, 100))
    lp.walk((100, 100), [(101, 100)], 0, 150)
    lp.snap((104, 100))  # /where says we are on (104,100)
    m = lp.build(10 * MS)
    goal = next(px(p) for p in m["points"] if p["kind"] == "goal")
    assert goal == (640.0 + 60, 360.0)
    lp.clear()
    last = json.loads(sent[-1])
    assert last["live"] is True and last["points"] == [] and lp.build(20 * MS) is None


def test_the_route_is_cut_where_it_leaves_the_view_and_ui_windows_travel_as_clip(
    rp: ModuleType,
) -> None:
    lp = preview(rp, [])
    lp.set_route((100, 100), [(150, 100)], (150, 100))  # 50 cells east: far off screen
    m = lp.build(0)
    xs = [px(p)[0] for p in m["points"]]
    assert max(xs) == pytest.approx(1280.0)  # drawn up to the edge of the game region
    assert not any(p["kind"] == "goal" for p in m["points"])  # an off-screen goal is not drawn
    assert len(m["clip"]) == len(rp.UI_WINDOWS)


def test_the_message_is_a_valid_display_only_route_preview(rp: ModuleType) -> None:
    from poring_env.protocol import RoutePreview

    sent: list[str] = []
    lp = preview(rp, sent)
    lp.set_route((100, 100), [(104, 100)], (104, 100), click=(102, 100))
    lp.walk((100, 100), [(101, 100), (102, 100)], 0, 150)
    for k in range(6):
        m = lp.build(int(rp.WALK_START_S * 1e9) + k * 50 * MS)
        lp._send(dict(m))
    msg = RoutePreview.model_validate_json(sent[-1])
    assert msg.live and msg.points[0].kind == "feet" and msg.passed and msg.clip
