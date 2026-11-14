"""dungeon_hunt.py --defend-box (dungeon@9.39, rogue-xmas02.md 4DM; Batt 2026-11-12 "use my
technique"): a fight a hit on us started first strikes the live detector's nearest box."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402

SRC = (ROOT / "scripts" / "dungeon_hunt.py").read_text()


def test_the_constants() -> None:
    assert (dh.DEFEND_BOX_PX, dh.DEFEND_BOX_VERSION) == (110.0, "9.39")
    assert dh.DEFEND_BOX_PX < dh.BOX_TARGET_PX  # ~3 cells, not the box path's ~6


def test_it_needs_the_box_strike() -> None:
    ns = argparse.Namespace
    assert dh.defend_box_refused(ns(defend_box=False, box_strike=False)) is None
    assert dh.defend_box_refused(ns(defend_box=True, box_strike=True)) is None
    why = dh.defend_box_refused(ns(defend_box=True, box_strike=False))
    assert why is not None and "--box-strike" in why


BASE = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
        "rest": "spot", "npc_guard": True, "miss_cue": False}  # fmt: skip


def test_the_record_only_when_on() -> None:
    off = dh.fixes_of(argparse.Namespace(**BASE))
    assert "defend_box" not in off
    on = dh.fixes_of(argparse.Namespace(**BASE, defend_box=True))
    assert on["defend_box"] == [110.0, "9.39"]


def test_the_fight_tries_it_once_after_the_box_path_and_before_the_scan() -> None:
    i_box = SRC.index('box_fight["tried"] = True  # dungeon@8.8: once per box fight')
    i_def = SRC.index('box_fight["defend_tried"] = True  # dungeon@9.39: once per fight')
    i_scan = SRC.index('found = scan("defend", ring(1), "sword")', i_def)
    assert i_box < i_def < i_scan
    assert SRC.count("box_target(DEFEND_BOX_PX)") == 1
    # only a fight WITHOUT a box (one the Battle Log or an HP drop started) takes it
    assert 'and box_fight.get("box") is None\n' in SRC[i_def - 400 : i_def]


def test_the_near_mode_skips_the_value_repick_and_the_walk_up() -> None:
    i0 = SRC.index("        def box_target(radius_px: float | None = None)")
    body = SRC[i0 : SRC.index("        def ", i0 + 50)]
    assert "if radius_px is not None:  # dungeon@9.39 (--defend-box): the box beside us" in body
    assert "and near_b is not None and radius_px is None:  # 9.28 (4CB)" in body
    assert 'getattr(a, "far_approach", False) and hs.here is not None and radius_px is None' in body
