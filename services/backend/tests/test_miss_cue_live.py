"""miss_cue_live (rogue-gef10 Amendments S and W): a Miss onset or engage is true only after a
monster's act on us within 3 s; 9.1's re-engage loop (an engage on the tick after a fight end)
is counted apart. The loop's shape is 4.05 c6's (181.8-182.9 s: 12 engage / end pairs)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import miss_cue_live as ml  # noqa: E402

S = 1_000_000_000


def test_true_only_after_an_act_on_us_within_three_seconds() -> None:
    acts = [10 * S, 20 * S]
    assert ml.truth([10 * S, 12 * S, 13 * S + 1, 9 * S, 21 * S], acts) == [
        True, True, False, False, True]  # fmt: skip
    assert ml.truth([5 * S], []) == [False]


def _c6_like() -> list[dict]:
    ev = [{"t_ns": 0, "kind": "run_start"},
          {"t_ns": 100 * S, "kind": "miss_cue"},
          {"t_ns": 100 * S, "kind": "engage", "by": "miss_cue"},  # a true first engage
          {"t_ns": 104 * S, "kind": "kill"},
          {"t_ns": 104 * S, "kind": "fight_end", "why": "quiet kill"}]  # fmt: skip
    t = 104 * S
    for _ in range(12):  # the loop: engage and end again on every 0.1 s tick
        t += S // 10
        ev += [{"t_ns": t, "kind": "engage", "by": "miss_cue"},
               {"t_ns": t, "kind": "fight_end", "why": "quiet kill"}]  # fmt: skip
    ev += [{"t_ns": 200 * S, "kind": "miss_cue"},  # no act on us before it: a false onset
           {"t_ns": 200 * S, "kind": "engage", "by": "miss_cue"}]  # fmt: skip
    return ev


def test_the_91_loop_is_counted_apart_and_a_lone_false_engage_is_counted() -> None:
    ev = _c6_like()
    assert ml.loop_flags(ev) == [False] + [True] * 12 + [False]
    out = ml.summary(ev, [99 * S], 0, 360 * S)
    assert out["onsets"] == 2 and out["onsets_false"] == 1
    assert out["engages"] == 14 and out["engages_loop"] == 12
    assert out["engages_true"] == 1 and out["engages_false"] == 1
    assert out["false_per_36min"] == 6.0  # 1 false in 6 min
