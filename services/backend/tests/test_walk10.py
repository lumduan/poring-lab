"""scripts/walk10.py (walk@10, demonstrations 3.17): walk@9 (its tests, kept) + click points from
the client's PICKING (tier A / B / none), one fix trusting several shifted clicks, 4 fixes a
route.
The picking model itself is tested on synthetic GATs in poring_dataset's test_picking.py; here the
fake camera's cell centres stand in for it (``TIERS`` sets a cell's tier)."""

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
    for name in ("walk5", "walk6", "reloc2", "where_fix", "walk7", "walk8", "walk9", "walk10"):
        _load(name, SCRIPTS / f"{name}.py")
    f = _load("fakes_walk6", HERE / "test_walk6.py")
    t7 = _load("fakes_walk7", HERE / "test_walk7.py")
    return sys.modules["walk10"], f, t7


@pytest.fixture
def fake(mods: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    w9, f, t7 = mods
    for mod in (w9, w9.w6, w9.w5):
        monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(w9.r, "game_region", lambda: (f.GX, f.GY, 1280, 720))
    monkeypatch.setattr(w9.r, "desktop", lambda: (1440, 900))
    monkeypatch.setattr(w9.r, "ns", lambda: 0)
    monkeypatch.setattr(w9, "moved", lambda a, b: (True, 1.0))  # the fake floor does not scroll
    TIERS.clear()

    def points(w: Any, end: tuple[int, int]) -> tuple[list[tuple[float, float]], str]:
        tier = TIERS.get(end, "A")
        if tier == "none":
            return [], "none"
        nb = np.array([(end[0] + dx, end[1] + dy) for dx, dy in w9.rr.NB9], dtype=float)
        return w9.rr.in_cell_points(w.project(nb)), tier

    monkeypatch.setattr(w9, "pick_points", points)
    return w9, f, t7


TIERS: dict[tuple[int, int], str] = {}


class Ws:
    def send(self, text: str) -> None:
        json.loads(text)


def sim(fake: Any, true: tuple[int, int], **kw: Any) -> Any:
    w9, f, t7 = fake
    s = t7.World(f, w9, true, **kw)
    s.client.ws = Ws()
    s.pr = w9.Prober9(s.client, s.client, s.pr.refs)
    return s


def ring() -> np.ndarray:
    yy, xx = np.mgrid[0:64, 0:64]
    return (np.hypot(xx - 36, yy - 42) >= 9) & (np.hypot(xx - 36, yy - 42) <= 12)


BAND = (100, 60, 1180, 680)


def test_moved_sees_a_scrolled_scene_and_not_a_still_one(mods: Any) -> None:
    w9, _, _ = mods
    rng = np.random.default_rng(3)
    scene = rng.integers(0, 255, (720, 1280, 3), dtype=np.uint8)
    assert w9.moved(scene, scene.copy())[0] is False
    still = scene.copy()
    still[300:330, 600:620] = 255  # the cursor and a candle: a small change
    assert w9.moved(scene, still)[0] is False
    assert w9.moved(scene, np.roll(scene, (24, 35), axis=(0, 1)))[0] is True


def test_static_green_in_the_parked_frame_is_not_the_marker(fake: Any) -> None:
    """walk@8 route 6: the same 43 px of green 'confirmed' two different targets. The same hover
    with and without a green decoration in the scene must read the same chevrons."""
    w9, _, _ = fake
    u, v = 700 - 80 + 4, 380 - 77 + 4

    def read(with_deco: bool) -> dict[str, Any]:
        s = sim(fake, (10, 18))
        real_grab = s.client.grab

        def grab(x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray]:
            fid, img = real_grab(x, y, w, h)
            img = img.copy()
            sx, sy = 708 - x, 392 - y  # a green decoration fixed in the SCENE
            if with_deco and 0 <= sx < w - 8 and 0 <= sy < h - 8:
                img[sy : sy + 8, sx : sx + 8, :3] = (110, 200, 110)
            return fid, img

        s.client.grab = grab
        s.pr.park()
        s.pr.hover(u, v)
        return s.pr.read(u, v)

    clean, deco = read(False), read(True)
    assert deco["static_green_px"] > clean["static_green_px"]
    assert deco["marker_px"] == clean["marker_px"] and deco["comps"] == clean["comps"]


def test_an_all_unconfirmed_round_asks_where_then_clicks(fake: Any) -> None:
    """walk@8 route 15: the goal, the last candidate, unconfirmed under pews -> declined 1 short."""
    w9, _, _ = fake
    s = sim(fake, (10, 18), hidden={(11, 18), (12, 18), (13, 18)})
    fixes: list[tuple[int, int]] = []

    def fix(agent: Any, screen: Any, w: Any, mask: Any, band: Any) -> dict[str, Any]:
        fixes.append(w.position)
        return {"ok": True, "to": list(w.position)}

    did = w9.walk_route(s.pr, s.w, (11, 18), BAND, 3, lambda *a: None, ring(), relocalise=fix)
    assert did.get("arrived_belief") and s.client.true == (11, 18), did
    assert [e["why"] for e in did["events"] if "relocalise" in e] == ["unconfirmed_round"]


def test_a_click_that_did_not_walk_is_blocked_once_the_fix_confirms_it(
    fake: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    w9, _, _ = fake
    s = sim(fake, (10, 18))
    real_click = s.client.click
    dead = {(13, 18)}  # clicking this cell walks nowhere (the server refuses it)

    def click(x: int, y: int) -> None:
        if s.client.cell_under(x, y) in dead:
            s.client.clicks.append((x, y))
            return
        real_click(x, y)

    s.client.click = click
    calls = iter([(False, 0.01)] + [(True, 0.9)] * 20)
    monkeypatch.setattr(w9, "moved", lambda a, b: next(calls))

    def fix(agent: Any, screen: Any, w: Any, mask: Any, band: Any) -> dict[str, Any]:
        w.position = s.client.true
        return {"ok": True, "to": list(s.client.true)}

    did = w9.walk_route(s.pr, s.w, (15, 18), BAND, 3, lambda *a: None, ring(), relocalise=fix)
    assert [e["why"] for e in did["events"] if "relocalise" in e][0] == "no_move"
    assert [e["blocked"] for e in did["events"] if "blocked" in e] == [[13, 18]]
    assert did.get("arrived_belief") and s.client.true == (15, 18), did


def test_one_fix_trusts_the_belief_for_several_shifted_clicks(fake: Any) -> None:
    """walk@9 route 25: the pew corridor hid the marker cell after cell, every step asked its own
    fix, and the 2-fix limit ended the route. walk@10: one fix, up to TRUST_CLICKS clicks."""
    w10, _, _ = fake
    hidden = {(x, 18) for x in range(11, 20)}
    s = sim(fake, (10, 18), hidden=hidden)
    fixes: list[tuple[int, int]] = []

    def fix(agent: Any, screen: Any, w: Any, mask: Any, band: Any) -> dict[str, Any]:
        fixes.append(w.position)
        return {"ok": True, "to": list(w.position)}

    did = w10.walk_route(s.pr, s.w, (19, 18), BAND, 3, lambda *a: None, ring(), relocalise=fix)
    assert did.get("arrived_belief") and s.client.true == (19, 18), did
    assert len(fixes) == 1, fixes  # 3 runs of 3 cells: one fix covers them all
    assert sum(e.get("outcome") == "unnamed_after_fix" for e in did["events"]) == 3


def fix_to_truth(s: Any, fixes: list[Any]) -> Any:
    def fix(agent: Any, screen: Any, w: Any, mask: Any, band: Any) -> dict[str, Any]:
        fixes.append(w.position)
        w.position = s.client.true
        return {"ok": True, "to": list(s.client.true)}

    return fix


def test_a_tier_b_point_is_never_clicked_unnamed_even_after_a_fix(fake: Any) -> None:
    """The strip behind a kneeler row (tier B): only the chevrons naming the cell may click it."""
    w10, _, _ = fake
    s = sim(fake, (10, 18), hidden={(11, 18)})
    TIERS[(11, 18)] = "B"
    fixes: list[Any] = []
    did = w10.walk_route(s.pr, s.w, (11, 18), BAND, 3, lambda *a: None, ring(),
                         relocalise=fix_to_truth(s, fixes), fixed_at_start=True)  # fmt: skip
    assert s.client.true == (10, 18) and not did.get("arrived_belief"), did
    assert not any(e.get("outcome") == "unnamed_after_fix" for e in did["events"])
    assert did.get("decline") in ("relocalise_limit", "click_limit"), did


def test_a_cell_no_pixel_picks_is_skipped_for_the_next_point(fake: Any) -> None:
    w10, _, _ = fake
    s = sim(fake, (10, 18))
    TIERS[(13, 18)] = "none"
    did = w10.walk_route(s.pr, s.w, (15, 18), BAND, 3, lambda *a: None, ring(),
                         relocalise=fix_to_truth(s, []))  # fmt: skip
    assert did.get("arrived_belief") and s.client.true == (15, 18), did
    assert [e["outcome"] for e in did["events"] if e.get("end") == [13, 18]] == ["no_safe_point"]
    assert all(e.get("end") != [13, 18] or not e.get("clicked") for e in did["events"])


def test_a_named_neighbour_at_a_pick_safe_point_is_doubt_not_a_hop(
    fake: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """walk@6-9 hopped to the neighbour's pixel; at a point the picking model puts in the cell, a
    neighbour name means the belief (or the naming) is off: ask /where, never hop."""
    w10, _, _ = fake
    s = sim(fake, (10, 18))
    real = w10.named8
    wrong = iter([(1, 0)] * 5)  # the first round's reads name the east neighbour

    def named(w: Any, rel: Any, p: Any) -> Any:
        return next(wrong, None) or real(w, rel, p)

    monkeypatch.setattr(w10, "named8", named)
    fixes: list[Any] = []
    did = w10.walk_route(s.pr, s.w, (13, 18), BAND, 3, lambda *a: None, ring(),
                         relocalise=fix_to_truth(s, fixes))  # fmt: skip
    first_click = next(i for i, e in enumerate(did["events"]) if e.get("clicked"))
    first_fix = next(i for i, e in enumerate(did["events"]) if "relocalise" in e)
    assert did["events"][first_fix]["why"] == "neighbour" and first_fix < first_click
    assert did.get("arrived_belief") and s.client.true == (13, 18), did


def test_a_neighbour_named_again_right_after_a_fix_blocks_that_cell_never_clicks_it(
    fake: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """walk@10 pilot route 3: every pick-safe point of (87,111) named the same neighbour while four
    correct fixes confirmed the belief. The model and the marker disagree about that cell: it is
    blocked for the route (re-planned around), and a disputed GOAL declines -- never a click."""
    w10, _, _ = fake
    s = sim(fake, (10, 18))
    real = w10.named8
    disputed = {(12, 18)}

    def named(w: Any, rel: Any, p: Any) -> Any:
        end = (w.position[0] + rel[0], w.position[1] + rel[1])
        return (1, 0) if end in disputed else real(w, rel, p)

    monkeypatch.setattr(w10, "named8", named)
    fixes: list[Any] = []
    did = w10.walk_route(s.pr, s.w, (14, 18), BAND, 2, lambda *a: None, ring(),
                         relocalise=fix_to_truth(s, fixes))  # fmt: skip
    assert [e["blocked"] for e in did["events"] if "blocked" in e] == [[12, 18]]
    assert all(not (e.get("end") == [12, 18] and e.get("clicked")) for e in did["events"])
    assert len(fixes) == 1 and did.get("arrived_belief") and s.client.true == (14, 18), did
    s2 = sim(fake, (10, 18))
    disputed.clear()
    disputed.add((12, 18))
    did2 = w10.walk_route(s2.pr, s2.w, (12, 18), BAND, 3, lambda *a: None, ring(),
                          relocalise=fix_to_truth(s2, []))  # fmt: skip
    assert did2.get("decline") == "goal_disputed" and s2.client.true == (10, 18), did2
