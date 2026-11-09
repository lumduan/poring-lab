"""scripts/walk_refusals.py (rogue-xmas02.md 4AE): the server's ignored walk requests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import walk_refusals as wr  # noqa: E402

S = 1_000_000_000


def test_classify_answers_by_a_move_within_0_3_s() -> None:
    pk = [{"type": "self_move_request", "t_mono_ns": 10 * S},
          {"type": "self_move", "t_mono_ns": 10 * S + S // 10},
          {"type": "self_move_request", "t_mono_ns": 20 * S},
          {"type": "self_move", "t_mono_ns": 21 * S},  # too late: ignored
          {"type": "self_move_request", "t_mono_ns": 99 * S}]  # outside the window  # fmt: skip
    assert wr.classify(pk, 0, 50 * S) == [(10 * S, True), (20 * S, False)]


def test_stuck_spans_need_three_in_a_row() -> None:
    reqs = [(1 * S, False), (2 * S, False), (3 * S, True),  # two: not a span
            (4 * S, False), (5 * S, False), (9 * S, False), (10 * S, True),
            (11 * S, False), (12 * S, False), (13 * S, False)]  # open at the end  # fmt: skip
    assert wr.stuck_spans(reqs, 0) == [{"start_s": 4.0, "span_s": 5.0, "n": 3},
                                       {"start_s": 11.0, "span_s": 2.0, "n": 3}]  # fmt: skip


def test_strike_requests_by_class_and_first_request() -> None:
    ev = [{"kind": "strike", "by": "box", "t_ns": 10 * S},
          {"kind": "strike", "by": "box", "t_ns": 20 * S},
          {"kind": "strike", "by": "box", "t_ns": 30 * S},
          {"kind": "strike", "by": "ring", "t_ns": 40 * S}]  # not a box strike  # fmt: skip
    reqs = [(10 * S + S // 2, False), (20 * S - S // 2, True)]
    got = wr.strike_requests(ev, reqs, {10 * S: "D", 20 * S: "K", 30 * S: "D"})
    assert got == {"D:ignored": 1, "D:none": 1, "K:answered": 1}


def test_unsent_walks_need_a_request_soon_after_the_click() -> None:
    ev = [{"kind": "walk", "clicked": True, "t_ns": 10 * S},  # request at +0.5 s: sent
          {"kind": "walk", "clicked": True, "t_ns": 20 * S},  # nothing within 1.2 s: unsent
          {"kind": "walk", "clicked": False, "t_ns": 30 * S},  # not clicked: not counted
          {"kind": "strike", "t_ns": 40 * S}]  # fmt: skip
    got = wr.unsent_walks(ev, [10 * S + S // 2, 22 * S])
    assert got == {"walk_clicks": 2, "unsent": 1, "unsent_share": 0.5}
