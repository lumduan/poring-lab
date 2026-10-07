"""scripts/walk8.py (walk@8, demonstrations 3.14): the route is planned once from the structure;
only the click point is probed; a covered click point moves along the polyline at once; the belief
is checked against the structure -- against walk@6/7's fake client (test_walk6/7.py)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[2] / "scripts"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mods() -> tuple[ModuleType, ModuleType, ModuleType]:
    sys.path.insert(0, str(SCRIPTS))
    for name in ("walk5", "walk6", "reloc2", "walk7", "walk8"):
        _load(name, SCRIPTS / f"{name}.py")
    f = _load("fakes_walk6", HERE / "test_walk6.py")
    t7 = _load("fakes_walk7", HERE / "test_walk7.py")
    return sys.modules["walk8"], f, t7


@pytest.fixture
def fake(mods: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    w8, f, t7 = mods
    for mod in (w8, w8.w6, w8.w5):
        monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(w8.r, "game_region", lambda: (f.GX, f.GY, 1280, 720))
    monkeypatch.setattr(w8.r, "desktop", lambda: (1440, 900))
    monkeypatch.setattr(w8.r, "ns", lambda: 0)
    return w8, f, t7


def ring() -> np.ndarray:  # the fake client's no-entry ring, in walk5's 64 x 64 probe crop
    yy, xx = np.mgrid[0:64, 0:64]
    return (np.hypot(xx - 36, yy - 42) >= 9) & (np.hypot(xx - 36, yy - 42) <= 12)


BAND = (100, 60, 1180, 680)


class Ws:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send(self, text: str) -> None:
        self.sent.append(json.loads(text))


def sim(fake: Any, true: tuple[int, int], **kw: Any) -> Any:
    w8, f, t7 = fake
    s = t7.World(f, w8, true, **kw)
    s.client.ws = Ws()
    return s


def test_waypoints_are_the_polyline_corners_and_the_goal(fake: Any) -> None:
    w8, _, _ = fake
    path = [(1, 0), (2, 0), (3, 0), (4, 1), (5, 2), (5, 3)]
    assert w8.waypoints((0, 0), path) == [(3, 0), (5, 2), (5, 3)]


def test_a_unit_on_an_intermediate_cell_refuses_nothing(fake: Any) -> None:
    """walk@6 refused this run (every cell had to show the walk cursor); units never block
    movement in RO, so walk@8 clicks straight past it."""
    w8, _, _ = fake
    s = sim(fake, (10, 18), monsters={(12, 18)})
    did = w8.walk_route(s.pr, s.w, (16, 18), BAND, 3, lambda *a: None, ring(),
                        relocalise=lambda *a: {"ok": True})  # fmt: skip
    assert did.get("arrived_belief") and s.client.true == (16, 18), did
    assert did["covered"] == 0 and s.client.attacked == []


def test_a_covered_click_point_moves_along_the_polyline_at_once(fake: Any) -> None:
    w8, _, _ = fake
    s = sim(fake, (10, 18), monsters={(13, 18)})  # exactly the first click point (3 cells)
    did = w8.walk_route(s.pr, s.w, (16, 18), BAND, 3, lambda *a: None, ring(),
                        relocalise=lambda *a: {"ok": True})  # fmt: skip
    assert did.get("arrived_belief") and s.client.true == (16, 18), did
    assert did["covered"] >= 1 and s.client.attacked == []
    ends = [tuple(e["end"]) for e in did["events"] if e.get("clicked")]
    assert (13, 18) not in ends


def test_a_wrong_belief_is_caught_by_direct_evidence_and_fixed(fake: Any) -> None:
    """walk@8 (overnight): the structure-probe alignment is OFF (reloc2's geometry failed
    relocalise@2); a no-entry sign on a PLANNED (GAT-walkable) cell is the evidence instead, and
    the belief is fixed (/where in the runs) before going on."""
    w8, _, _ = fake
    s = sim(fake, (11, 18))
    s.walk[18, 12:17] = False  # the truth's own row is blocked ahead of it ...
    s.w.position = (11, 19)  # ... but we believe we stand one row south, on an open row
    calls: list[tuple[int, int]] = []

    def fix(agent: Any, screen: Any, w: Any, mask: Any, band: Any) -> dict[str, Any]:
        calls.append(w.position)
        w.position = s.client.true
        return {"ok": True, "to": list(s.client.true)}

    did = w8.walk_route(s.pr, s.w, (16, 19), BAND, 3, lambda *a: None, ring(), relocalise=fix)
    assert calls and calls[0] == (11, 19), did
    assert [e["why"] for e in did["events"] if "relocalise" in e][0] == "noentry"
    assert did.get("arrived_belief") and s.client.true == (16, 19), did


def test_an_unknown_shape_never_waits_and_never_substitutes(fake: Any) -> None:
    """walk@7 waited on unknown reads in CLEAN rooms and substituted goals nobody had taken."""
    w8, f, _ = fake
    s = sim(fake, (10, 18))
    f.SPRITES["blob"] = [([(dx, dy) for dy in range(-3, 9) for dx in range(-3, 9)], (40, 200, 240))]
    base = s.client.shape_at
    s.client.shape_at = lambda c: "blob" if c[0] >= 12 else base(c)  # unknown from x = 12 on
    did = w8.walk_route(s.pr, s.w, (13, 18), BAND, 3, lambda *a: None, ring(),
                        relocalise=lambda *a: {"ok": True}, clock=t7_clock())  # fmt: skip
    assert did["decline"] == "no_click_point" and did["waited_s"] == 0, did
    assert did["substitute"] is None


def test_a_unit_that_stays_on_the_goal_gets_a_substitute_after_its_patience(fake: Any) -> None:
    w8, _, _ = fake
    s = sim(fake, (10, 18), monsters={(13, 18)})  # never leaves
    did = w8.walk_route(s.pr, s.w, (13, 18), BAND, 3, lambda *a: None, ring(),
                        relocalise=lambda *a: {"ok": True}, clock=t7_clock())  # fmt: skip
    assert did.get("arrived_belief") and did["waited_s"] > 0, did
    sub = tuple(did["substitute"])
    assert max(abs(sub[0] - 13), abs(sub[1] - 18)) == 1 and s.client.true == sub
    assert s.client.attacked == []


def t7_clock() -> Any:
    t = [0.0]

    def clock() -> float:
        t[0] += 0.5
        return t[0]

    return clock


def test_the_planned_route_is_previewed_for_the_human(fake: Any) -> None:
    w8, _, _ = fake
    s = sim(fake, (10, 18))
    w8.walk_route(s.pr, s.w, (14, 14), BAND, 3, lambda *a: None, ring(),
                  relocalise=lambda *a: {"ok": True}, label="walk@8 route 7")  # fmt: skip
    sent = [m for m in s.client.ws.sent if m["type"] == "route_preview"]
    assert sent and sent[0]["label"] == "walk@8 route 7"
    kinds = [p["kind"] for p in sent[0]["points"]]
    assert kinds[0] == "start" and "goal" in kinds and kinds[-1] == "click"
    assert all(0.0 <= p["x"] <= 1.0 and 0.0 <= p["y"] <= 1.0 for m in sent for p in m["points"])


def door() -> list[tuple[int, int]]:  # the warp cursor: a door (a rectangle) over the hotspot
    return [(dx, dy) for dy in range(-6, 12) for dx in range(-4, 6)]


def test_a_portal_is_taken_by_a_click_on_the_warp_cursor(fake: Any) -> None:
    """The cross-map walk (Batt, ~20:00): the click whose intent is the portal expects the WARP
    shape -- every other click still expects the walk cursor."""
    w8, f, _ = fake
    f.SPRITES["warp"] = [(door(), (225, 225, 235))]
    s = sim(fake, (10, 18))
    portal = (14, 18)
    base = s.client.shape_at
    s.client.shape_at = lambda c: "warp" if c == portal else base(c)
    s.pr.refs = f.refs_for(w8.w6, ["walk", "sword", "noentry", "talk", "warp"])
    did = w8.walk_route(s.pr, s.w, portal, BAND, 3, lambda *a: None, ring(),
                        relocalise=lambda *a: {"ok": True}, expect_goal="warp")  # fmt: skip
    assert did.get("arrived_belief") and did.get("portal"), did
    last = [e for e in did["events"] if e.get("clicked")][-1]
    assert tuple(last["end"]) == portal and last["outcome"] == "portal"
    assert s.client.attacked == []


def test_after_a_fix_an_unnamed_walk_cursor_may_be_clicked(fake: Any) -> None:
    """The 23:35 pilot: pews hid the marker (17-27 px) on cells whose belief /where had just
    confirmed twice; with the belief CONFIRMED, the walk cursor (re-checked) is enough."""
    w8, _, _ = fake
    s = sim(fake, (10, 18), hidden={(12, 18), (13, 18), (11, 18)})
    fixes: list[tuple[int, int]] = []

    def fix(agent: Any, screen: Any, w: Any, mask: Any, band: Any) -> dict[str, Any]:
        fixes.append(w.position)
        return {"ok": True, "to": list(w.position)}

    did = w8.walk_route(s.pr, s.w, (13, 18), BAND, 3, lambda *a: None, ring(), relocalise=fix)
    assert did.get("arrived_belief") and s.client.true == (13, 18), did
    assert fixes and any(e.get("outcome") == "unnamed_after_fix" for e in did["events"])
    assert s.client.attacked == []


def test_without_a_fix_an_unnamed_walk_cursor_is_not_clicked(fake: Any) -> None:
    w8, _, _ = fake
    s = sim(fake, (10, 18), hidden={(12, 18), (13, 18), (11, 18)})
    did = w8.walk_route(s.pr, s.w, (13, 18), BAND, 3, lambda *a: None, ring(),
                        relocalise=lambda *a: {"ok": False})  # fmt: skip
    assert not did.get("arrived_belief") and s.client.clicks == [], did
