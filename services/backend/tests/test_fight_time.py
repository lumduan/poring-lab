"""scripts/fight_time.py (rogue-xmas02.md 4AF): where the fight time goes."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import fight_time as ft  # noqa: E402

S = 1_000_000_000


def test_fights_pair_engage_with_the_next_end() -> None:
    ev = [{"kind": "engage", "t_ns": 1 * S}, {"kind": "engage", "t_ns": 2 * S},
          {"kind": "fight_end", "t_ns": 5 * S}, {"kind": "fight_end", "t_ns": 6 * S},
          {"kind": "engage", "t_ns": 10 * S}, {"kind": "fight_end", "t_ns": 12 * S}]  # fmt: skip
    assert ft.fights(ev) == [(1 * S, 5 * S), (10 * S, 12 * S)]


def test_our_kills_need_our_hit_before_the_death() -> None:
    pk = [
        {"type": "act", "src_gid": ft.OUR_GID, "target_gid": 7, "t_mono_ns": 3 * S},
        {"type": "entity_vanish", "gid": 7, "reason": 1, "t_mono_ns": 4 * S},
        {"type": "entity_vanish", "gid": 8, "reason": 1, "t_mono_ns": 5 * S},  # not ours
        {"type": "act", "src_gid": ft.OUR_GID, "target_gid": 9, "t_mono_ns": 7 * S},
        {"type": "entity_vanish", "gid": 9, "reason": 0, "t_mono_ns": 6 * S},
    ]  # walked off
    assert ft.our_kills(pk) == [4 * S]


def test_summary_after_kill_and_nokill() -> None:
    fs = [(1 * S, 10 * S), (20 * S, 25 * S), (30 * S, 40 * S)]
    got = ft.summary(fs, [4 * S, 39 * S + S // 2])
    assert got == {"fights": 3, "kill_fights": 2, "after_kill_p50_s": 3.25,
                   "after_kill_total_s": 6.5, "nokill_fights": 1,
                   "nokill_total_s": 5.0}  # fmt: skip


def test_hit_gap_kills_match_a_death_just_before() -> None:
    ev = [{"kind": "kill", "by": "hit_gap", "t_ns": 10 * S},  # death at 8.5: matched
          {"kind": "kill", "by": "hit_gap", "t_ns": 20 * S},  # nothing 0-3 s before: false
          {"kind": "kill", "by": "exp_line", "t_ns": 30 * S}]  # not inferred  # fmt: skip
    got = ft.hit_gap_match(ev, [8 * S + S // 2, 21 * S])
    assert got == {"hit_gap_kills": 2, "hit_gap_matched": 1, "hit_gap_share": 0.5}
    assert ft.hit_gap_match([], [])["hit_gap_share"] is None


def test_loot_summary_pickups_and_scans_without_a_kill() -> None:
    pk = [{"type": "floor_item_appear"}, {"type": "floor_item_appear"},
          {"type": "pickup_request"}]  # fmt: skip
    ev = [
        {"kind": "loot_step", "hovered": 3, "t_ns": 20 * S},  # a death at 15 s: with a kill
        {"kind": "loot_step", "hovered": 2, "t_ns": 50 * S},  # nothing in 10 s: without
        {"kind": "loot_step", "hovered": 0, "t_ns": 60 * S},
    ]  # no hover: not counted
    got = ft.loot_summary(ev, pk, [15 * S])
    assert got == {
        "floor_items": 2,
        "pickups": 1,
        "pickup_share": 0.5,
        "loot_steps_hovering": 2,
        "loot_steps_without_kill": 1,
    }


def test_our_kills_follow_each_life_of_a_reused_gid() -> None:
    """2026-11-09: the server reuses gids; a later spawn's death must not hide the earlier kill."""
    pk = [
        {"type": "act", "src_gid": ft.OUR_GID, "target_gid": 7, "t_mono_ns": 1 * S},
        {"type": "entity_vanish", "gid": 7, "reason": 1, "t_mono_ns": 2 * S},  # our kill
        {"type": "entity_vanish", "gid": 7, "reason": 1, "t_mono_ns": 50 * S},  # a later life,
        {"type": "act", "src_gid": ft.OUR_GID, "target_gid": 7, "t_mono_ns": 60 * S},  # not hit
        {"type": "entity_vanish", "gid": 7, "reason": 1, "t_mono_ns": 61 * S},
    ]  # our kill again
    assert ft.our_kills(pk) == [2 * S, 61 * S]


def test_loot_order_counts_looted_kills_and_instant_ends() -> None:
    """L3 / L4 (rogue-xmas02.md 4AT): kills followed by a loot step with a list within 5 s, and
    engages a quiet-kill fight_end closed in under 50 ms (p38's loop: 1,057 of 1,144)."""
    ev = [{"kind": "kill", "t_ns": 10 * S},
          {"kind": "loot_step", "list_kills": 1, "t_ns": 11 * S},  # looted at +1 s
          {"kind": "kill", "t_ns": 20 * S},
          {"kind": "loot_step", "list_kills": 0, "t_ns": 21 * S},  # an empty list: not looted
          {"kind": "engage", "t_ns": 30 * S},
          {"kind": "fight_end", "why": "quiet kill", "t_ns": 30 * S + 10_000_000},  # instant
          {"kind": "engage", "t_ns": 40 * S},
          {"kind": "fight_end", "why": "quiet kill", "t_ns": 42 * S},  # a real fight
          {"kind": "loot_click", "why": "list", "t_ns": 43 * S},
          {"kind": "loot_click", "why": "scan_hand", "t_ns": 44 * S}]  # fmt: skip
    got = ft.loot_order(ev)
    assert got["kills_looted_5s"] == 1 and got["kills_events"] == 2 and got["looted_share"] == 0.5
    assert got["engages"] == 2 and got["instant_ends"] == 1 and got["instant_share"] == 0.5
    assert got["loot_clicks_by"] == {"list": 1, "scan_hand": 1}


def test_quiet_scans_counts_defend_scans_without_a_hit_before_and_hits_taken() -> None:
    """Q1 / S1 (rogue-xmas02.md 4AW): a defend scan is quiet when no act on us came in the 5 s
    before its START (event time minus ms); S1 = damaging acts on us per 10 min of the run."""
    ev = [{"kind": "run_start", "t_ns": 0},
          {"kind": "scan", "purpose": "defend", "ms": 2000, "found": None, "t_ns": 12 * S},
          {"kind": "scan", "purpose": "defend", "ms": 1000, "found": [1, 2], "t_ns": 31 * S},
          {"kind": "scan", "purpose": "loot", "ms": 1000, "found": None, "t_ns": 50 * S},
          {"kind": "run_end", "t_ns": 600 * S}]  # fmt: skip
    pk = [{"type": "act", "target_gid": ft.OUR_GID, "damage": 30, "t_mono_ns": 7 * S},  # < 5 s
          {"type": "act", "target_gid": ft.OUR_GID, "damage": 0, "t_mono_ns": 20 * S},  # a miss
          {"type": "act", "target_gid": 99, "damage": 50, "t_mono_ns": 29 * S}]  # fmt: skip
    got = ft.quiet_scans(ev, pk)
    assert got["quiet_defend_scans"] == 1 and got["quiet_defend_found"] == 1  # the 2nd scan only
    assert got["hits_taken_per10"] == 1.0  # one damaging hit in 10 min
