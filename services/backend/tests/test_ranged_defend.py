"""ranged-attacker-1080.md (Batt 2026-11-21, his clip: "it scans around itself, but it is shot from
afar; detect the monsters on the screen, know which one attacks"): the defend box takes the nearest
SHOOTER first -- a species whose KB attack range is >= 3, within that range + 1 cell -- with the box
path's own skip test; else the runner's own pick. A player switch, off by default."""

from __future__ import annotations

import json
import sys
import threading
import time
import types
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import flow_play as fp  # noqa: E402

GRID = [(dx, dy) for dx in range(-12, 13) for dy in range(-10, 11)]


def uv() -> list[tuple[float, float]]:
    """A linear stand-in for the camera: one cell = 40 px east, 30 px north; her foot (640, 400)."""
    return [(640 + dx * 40, 400 - dy * 30) for dx, dy in GRID]


def box(cell: tuple[int, int], species: str) -> Any:
    fx, fy = 640 + cell[0] * 40, 400 - cell[1] * 30
    return types.SimpleNamespace(x0=fx - 15, y0=fy - 60, x1=fx + 15, y1=fy, score=0.9,
                                 cls="monster", species=species)  # fmt: skip


def test_the_kb_names_the_species_that_shoot(tmp_path: Path) -> None:
    kb = tmp_path / "mobs.json"
    kb.write_text(json.dumps({
        "1248": {"aegis": "CRUISER", "attack_range": 7},
        "1249": {"aegis": "MYSTCASE", "attack_range": 1},
        "1251": {"aegis": "KNIGHT_OF_WINDSTORM", "attack_range": 2},
        "1": {"aegis": "", "attack_range": 9},  # no name: never
    }))  # fmt: skip
    assert fp.ranged_reach(kb) == {"cruiser": 7}
    assert fp.ranged_reach(tmp_path / "none.json") == {}


def test_the_nearest_shooter_in_its_reach_and_never_a_skipped_one() -> None:
    reach = {"cruiser": 7}
    near_case, far_cruiser = box((1, 0), "mystcase"), box((6, 2), "cruiser")

    def no(cx: float, cy: float) -> bool:
        return False

    got = fp.ranged_pick([near_case, far_cruiser], (640, 400), reach, uv(), GRID, no, None)
    assert (
        got is not None and got[0] is far_cruiser and got[1] == 6
    )  # the shooter, not the near one
    out_of_reach = box((9, 0), "cruiser")  # 9 > 7 + 1
    assert fp.ranged_pick([out_of_reach], (640, 400), reach, uv(), GRID, no, None) is None
    edge = box((8, 1), "cruiser")  # 8 = 7 + RANGED_MARGIN
    assert fp.ranged_pick([edge], (640, 400), reach, uv(), GRID, no, None) is not None
    two = [box((5, 0), "cruiser"), box((3, 1), "cruiser")]
    assert fp.ranged_pick(two, (640, 400), reach, uv(), GRID, no, None)[0] is two[1]  # type: ignore[index]
    # the box path's own test refuses it (out of view, out of reach): passed over
    assert fp.ranged_pick([far_cruiser], (640, 400), reach, uv(), GRID, no, lambda f: True) is None
    # her own box is never a target
    assert fp.ranged_pick([far_cruiser], (640, 400), reach, uv(), GRID, lambda x, y: True,
                          None) is None  # fmt: skip


class FakeWatch:
    def __init__(self, got: list[Any]) -> None:
        self.lock = threading.Lock()
        self.last = (time.monotonic(), got)
        self.last_species: str | None = None
        self.last_pick: Any = None
        self.calls: list[float] = []

    def near(self, px: Any, max_px: float, fresh_s: float, skip: Any = None,
             values: Any = None) -> Any:  # fmt: skip
        self.calls.append(max_px)
        return ("own", max_px)


def fake_dh() -> Any:
    return types.SimpleNamespace(BoxWatch=FakeWatch, DEFEND_BOX_PX=110.0, BOX_SCREEN_PX=4000.0,
                                 BOX_GRID=GRID, self_box=lambda x, y: False,
                                 box_species=lambda b: b.species)  # fmt: skip


def test_the_defend_pick_takes_the_shooter_and_every_other_call_is_the_runners(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(fp, "ranged_reach", lambda path=fp.KB_MOBS: {"cruiser": 7})
    dh = fake_dh()
    w = FakeWatch([box((1, 0), "mystcase"), box((6, 2), "cruiser")])
    logged: list[dict[str, Any]] = []
    vals = {"defend_ranged": True}
    with fp.ranged_defend(dh, vals, logged.append, uv=uv):
        got = dh.BoxWatch.near(w, (640, 400), 110.0, 2.8)
        assert got == (865, 280, 895, 340) and w.last_species == "cruiser"
        assert logged == [{"kind": "ranged_defend", "species": "cruiser", "cells": 6, "d_px": 247}]
        assert dh.BoxWatch.near(w, (640, 400), 4000.0, 2.8) == ("own", 4000.0)  # not a defend call
        w.last = (time.monotonic(), [box((1, 0), "mystcase")])  # no shooter: the runner's own
        assert dh.BoxWatch.near(w, (640, 400), 110.0, 2.8) == ("own", 110.0)
        w.last = (time.monotonic() - 10, [box((6, 2), "cruiser")])  # a stale read: the runner's
        assert dh.BoxWatch.near(w, (640, 400), 110.0, 2.8) == ("own", 110.0)
    assert dh.BoxWatch is FakeWatch and FakeWatch.near.__name__ == "near"  # restored


def test_the_box_paths_skip_test_is_reused_for_the_shooter(monkeypatch: Any) -> None:
    monkeypatch.setattr(fp, "ranged_reach", lambda path=fp.KB_MOBS: {"cruiser": 7})
    dh = fake_dh()
    w = FakeWatch([box((6, 2), "cruiser")])
    with fp.ranged_defend(dh, {"defend_ranged": True}, uv=uv):
        dh.BoxWatch.near(w, (640, 400), 4000.0, 2.8, lambda f: True)  # an engage-screen call
        assert dh.BoxWatch.near(w, (640, 400), 110.0, 2.8) == ("own", 110.0)  # out of reach


def test_off_is_unchanged(monkeypatch: Any) -> None:
    dh = fake_dh()
    saved = dh.BoxWatch.near
    with fp.ranged_defend(dh, {"defend_ranged": False}, uv=uv):
        assert dh.BoxWatch.near is saved
    with fp.ranged_defend(dh, {}, uv=uv):
        assert dh.BoxWatch.near is saved


def test_the_scorers_pure_lines() -> None:
    import ranged_ab_score as rs

    s = 10**9
    ev = [{"t_ns": 0, "kind": "run_start"}, {"t_ns": 1800 * s, "kind": "run_end"},
          {"t_ns": 5 * s, "kind": "scan", "purpose": "defend", "ms": 3000},
          {"t_ns": 9 * s, "kind": "scan", "purpose": "loot", "ms": 9000}]  # fmt: skip
    assert rs.defend_scan_s_h(ev) == 6.0  # 3 s in half an hour
    assert rs.r2_line([400.0, 420.0], [200.0, 250.0])["verdict"] == "PASS"
    assert rs.r2_line([400.0, 420.0], [350.0, 330.0])["verdict"] == "FAIL"
    assert rs.r2_line([400.0], [200.0])["verdict"] == "INCONCLUSIVE"
    ok = {"verdict": "PASS"}
    bad = {"verdict": "FAIL"}
    assert rs.overall({"kills_h": ok, "defend_scans": ok, "deaths": ok, "errors": ok}) == "JOINS"
    assert rs.overall({"kills_h": bad, "defend_scans": ok, "deaths": ok,
                       "errors": ok}) == "FASTER, NOT MORE"  # fmt: skip
    assert rs.overall({"kills_h": ok, "defend_scans": ok, "deaths": bad, "errors": ok}) == "WORSE"
    picks = [{"t_ns": 10 * s}, {"t_ns": 30 * s}, {"t_ns": 50 * s}]
    pk = [{"type": "self_move_request", "t_mono_ns": int(10.3 * s)},
          {"type": "attack_request", "t_mono_ns": int(11.0 * s)},
          {"type": "self_move_request", "t_mono_ns": int(31 * s)}]  # fmt: skip
    assert dict(rs.pick_fates(picks, pk)) == {"attacked": 1, "walked": 1, "none": 1}
