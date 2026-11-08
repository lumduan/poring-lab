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
