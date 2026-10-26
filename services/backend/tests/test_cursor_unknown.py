"""cursor_unknown.py (2026-10-26, docs/planning/gef10-cursor-unknown.md): the offline split of the
walk cursor's UNKNOWN reads. Its pure parts, on synthetic events and packets."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import cursor_unknown as cu  # noqa: E402

NS = cu.NS


def test_test2_runs_and_watches_are_refused_by_name() -> None:
    for tag in ("a9", "a10", "a11", "w3", "w3b"):
        assert cu.refused_tag(tag)
    for tag in ("a2", "a8", "a5b", "b1", "a1"):
        assert not cu.refused_tag(tag)


def test_the_read_starts_before_the_event_by_the_window_it_ran() -> None:
    assert cu.read_start({"t_ns": 10 * NS, "clicked": False}) == 10 * NS - int(0.37 * NS)
    assert cu.read_start({"t_ns": 10 * NS, "clicked": True}) == 10 * NS - int(0.15 * NS)


def test_motion_state_from_the_moving_spans() -> None:
    moving = [(1 * NS, 3 * NS), (10 * NS, 12 * NS)]
    assert cu.motion_state(int(0.5 * NS), moving) == ("none", None)
    assert cu.motion_state(2 * NS, moving) == ("moving", 0.0)
    assert cu.motion_state(int(3.5 * NS), moving)[0] == "stop<1s"
    assert cu.motion_state(int(4.5 * NS), moving)[0] == "stop1-2s"
    st, since = cu.motion_state(int(9 * NS), moving)
    assert st == "stand>=2s" and since == 6.0


def test_a_monster_on_beside_or_in_front_of_the_target() -> None:
    to = (100, 100)
    assert cu.near_kind(to, (100, 100)) == "on"
    assert cu.near_kind(to, (101, 99)) == "ring1"
    assert cu.near_kind(to, (100, 98)) == "front"  # 2 cells south: its body drawn up over it
    assert cu.near_kind(to, (101, 97)) == "front"
    assert cu.near_kind(to, (100, 102)) is None  # 2 cells north: drawn above, not over it
    assert cu.near_kind(to, (103, 100)) is None


def test_monster_at_uses_the_live_span_and_the_drawn_picture() -> None:
    pk = [{"type": "entity_appear", "objtype": 5, "gid": 7, "t_mono_ns": 1 * NS, "x": 50, "y": 50},
          {"type": "entity_vanish", "gid": 7, "t_mono_ns": 5 * NS}]  # fmt: skip
    alive = cu.alive_spans(pk)
    pos = {7: [(1 * NS, (50, 50), 1023)]}
    assert cu.monster_at((50, 50), 2 * NS, pos, alive) == "on"
    assert cu.monster_at((50, 50), 6 * NS, pos, alive) is None  # vanished
    # 0.45 s after the vanish the drawn picture (t - LAG) still shows it
    assert cu.monster_at((50, 51), 5 * NS + int(0.3 * NS), pos, alive) == "ring1"


def test_frame_cause_order() -> None:
    wide = {"sword": 0.3, "pickup": 0.05, "walk": 0.97}
    narrow = {"sword": 0.3, "pickup": 0.05, "walk": 0.55}
    full_ok = {"sword": 0.3, "pickup": 0.05, "walk": 0.9}
    none = {"sword": 0.2, "pickup": 0.03, "walk": 0.2}
    assert cu.frame_cause(wide, wide, 40, 0.0) == "noentry ring"
    assert cu.frame_cause({**none, "sword": 0.8}, none, 0, 0.0) == "sword"
    assert cu.frame_cause(wide, wide, 0, 0.0) == "wide arrow"
    assert cu.frame_cause(narrow, full_ok, 0, 0.0) == "narrow arrow"
    assert cu.frame_cause(narrow, {**narrow, "walk": 0.7}, 0, 0.0) == "partial"
    assert cu.frame_cause(none, none, 0, 0.9) == "arrow off the point"
    assert cu.frame_cause(none, none, 0, 0.3) == "no arrow"
