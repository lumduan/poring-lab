"""walk_judge.py (rogue-xmas02.md 4G): the patrol walk's numbers from a session's events. Its
positive case on REAL sessions (run before 4G's commit): pilot p2 gives 7 dead-end Fly Wings and
138 no-entry carves in 414 walk decisions; X2 gives 5 dead ends + 2 position-unread and 116
carves."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import walk_judge as wj  # noqa: E402

S = 10**9


def _walk(t: int, frm: list[int], to: list[int], clicked: bool, red: int = 0,
          ring: list[int] | None = None) -> dict[str, object]:  # fmt: skip
    e: dict[str, object] = {"t_ns": t * S, "kind": "walk", "from": frm, "to": to,
                            "clicked": clicked, "why": "search", "red": red}  # fmt: skip
    if ring is not None:
        e["ring"] = ring
    return e


def test_the_walk_judge_counts_carves_flies_uncarves_and_the_ring_reads() -> None:
    evs = [
        {"t_ns": 0, "kind": "run_start"},
        _walk(1, [7, 21], [7, 28], True, 0, [0, 0, 0, 0]),
        _walk(2, [7, 24], [7, 31], False, 600, [0, 0, 0, 0]),  # refused: no ring, not a carve
        _walk(3, [7, 24], [8, 31], False, 300, [200, 0, 1, 0]),  # the ring: carved
        {"t_ns": 3 * S, "kind": "noentry_carve", "at": [7, 24], "to": [8, 31], "r": 0},
        # a red-only click that walked (the next click is from another cell)
        _walk(4, [7, 24], [7, 30], True, 900, [10, 80, 0, 0]),
        _walk(5, [7, 27], [7, 33], True, 0, [0, 0, 0, 0]),
        # a red-only click followed by a stall at its cell: a ring the rule may have missed
        _walk(6, [7, 27], [6, 33], True, 400, [30, 0, 0, 0]),
        _walk(7, [7, 27], [6, 33], True, 400, [30, 0, 0, 0]),
        {"t_ns": 7 * S, "kind": "stall", "at": [7, 27], "to": [6, 33]},
        {"t_ns": 8 * S, "kind": "uncarve", "at": [7, 27], "cells": 26, "why": "dead_end"},
        {"t_ns": 9 * S, "kind": "escape", "how": "fly", "why": "dead_end"},
        {"t_ns": 10 * S, "kind": "escape", "how": "fly", "why": "pos_unread"},
        {"t_ns": 11 * S, "kind": "patrol", "event": "reached", "i": 1, "next": 2},
        {"t_ns": 60 * S, "kind": "run_end"},
    ]
    out = wj.judge(evs)
    assert out["minutes"] == 1.0 and out["walk_decisions"] == 7 and out["walk_clicks"] == 5
    assert out["noentry_carves"] == 1 and out["carve_share"] == round(1 / 7, 3)
    assert out["dead_end_flies"] == 1 and out["flies"] == {"dead_end": 1, "pos_unread": 1}
    assert out["uncarves"] == 1 and out["stalls"] == 1
    assert out["ring_logged"] == 7 and out["ring_seen"] == 1
    assert out["red_only_clicks"] == 3 and out["red_only_stalled"] == 1
    assert out["waypoints_reached"] == 1 and out["reached_per_min"] == 1.0


def test_a_session_before_the_ring_logs_no_ring_reads() -> None:
    """dungeon@8.5 sessions (p1, p2, X2) logged red only on refused / trusted walks, no ring."""
    evs = [{"t_ns": 0, "kind": "run_start"}, _walk(1, [7, 21], [7, 28], False, 600),
           {"t_ns": 1 * S, "kind": "noentry_carve", "at": [7, 21], "to": [7, 28]},
           {"t_ns": 120 * S, "kind": "run_end"}]  # fmt: skip
    out = wj.judge(evs)
    assert out["ring_logged"] == 0 and out["red_only_clicks"] == 0 and out["carve_share"] == 1.0


def test_the_move_requests_come_from_the_packets_when_given() -> None:
    """p3: 124 of 456 walk clicks sent no self_move_request; 93 of 95 at (0, +7)."""
    evs = [
        {"t_ns": 0, "kind": "run_start"},
        _walk(1, [13, 27], [13, 34], True),  # straight north: no request follows
        _walk(3, [13, 27], [14, 34], True),  # aside: its request 2 ms before the log line
        {**_walk(5, [14, 34], [15, 41], True), "dodge": "side+1"},
        {"t_ns": 60 * S, "kind": "run_end"},
    ]
    pk = [{"t_mono_ns": 3 * S - 2_000_000, "type": "self_move_request", "x": 14, "y": 34},
          {"t_mono_ns": 5 * S + 100_000_000, "type": "self_move_request", "x": 15, "y": 41},
          {"t_mono_ns": 1 * S + 900_000_000, "type": "self_move", "x0": 1, "y0": 1}]  # fmt: skip
    out = wj.judge(evs, pk)
    assert out["unsent_clicks"] == 1 and out["unsent_share"] == round(1 / 3, 3)
    assert out["column_clicks"] == 1 and out["column_unsent"] == 1
    assert out["dodges"] == {"side+1": 1}
    assert "unsent_clicks" not in wj.judge(evs)  # events alone: no move-request columns


def test_a_hunt_flow_sessions_column_clicks_are_counted_by_arm() -> None:
    """4K: v56's A / B logs `col` on the walk clicks in the GM's own column; before v56 such a
    click is "column" by its pixel. Positive case on the real v54 / v55 sessions (run before 4K's
    commit, the 8 v54 / v55 sessions): "column" 217 of 784 unsent, "other" 17 of 9,055."""
    clicks = [
        {"t": 1 * S, "u": 649.5, "v": 204.0, "kind": "walk", "col": "nudged"},
        {"t": 3 * S, "u": 640.4, "v": 204.0, "kind": "walk", "col": "ab_off"},
        {"t": 5 * S, "u": 640.4, "v": 204.0, "kind": "walk"},  # before v56: by its pixel
        {"t": 7 * S, "u": 845.5, "v": 361.7, "kind": "walk"},
        {"t": 9 * S, "u": 600.0, "v": 300.0, "kind": "strike"},  # not a walk click
    ]
    pk = [{"t_mono_ns": 1 * S + 50_000_000, "type": "self_move_request"},
          {"t_mono_ns": 7 * S + 550_000_000, "type": "self_move_request"}]  # fmt: skip
    out = wj.column_ab(clicks, pk)
    assert out["nudged"] == {"clicks": 1, "unsent": 0, "unsent_share": 0.0}
    assert out["ab_off"]["unsent"] == 1 and out["column"]["unsent"] == 1
    assert out["other"] == {"clicks": 1, "unsent": 0, "unsent_share": 0.0}  # +0.55 s: within
