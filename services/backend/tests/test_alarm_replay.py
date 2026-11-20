"""scripts/alarm_replay.py (goblin-alarm-1080.md section 4): the runner's alarm rule replayed
offline -- today's, the near-her rule (A) and confirm 3 -- and the held-out bars."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import alarm_replay as ar  # noqa: E402

S = 1_000_000_000


def box(cx: float, cy: float, score: float, cls: str = "g_gobline_xmas") -> list[Any]:
    return [cx - 20, cy - 30, cx + 20, cy + 30, score, cls]


def test_its_rule_is_the_runner_s_own() -> None:
    import dungeon_hunt as dh

    assert (ar.FOOT_PX, ar.BODY_UP) == (dh.FOOT_PX, dh.BODY_UP)

    class B:
        def __init__(self, b: list[Any]) -> None:
            self.b, self.score = b, b[4]

    cases = [([box(900, 300, 0.4)], 1, 2, 0.7), ([box(900, 300, 0.4)], 2, 2, 0.7),
             ([box(900, 300, 0.75)], 1, 2, 0.7), ([box(900, 300, 0.4), box(200, 300, 0.8)], 1,
                                                  2, 0.7), ([], 3, 2, 0.7),
             ([box(900, 300, 0.75)], 1, 2, None)]  # fmt: skip
    for boxes, streak, need, solo in cases:
        want = dh.alarm_seen((10.0, [B(b) for b in boxes]), 10.0, streak=streak, need=need,
                             solo=solo)  # fmt: skip
        got = ar.seen(boxes, streak, need, solo)
        assert (want.b if want is not None else None) == got, (boxes, streak, need, solo)


def test_the_settings_come_from_the_session_s_start_record() -> None:
    start = {
        "fixes": {"garm_fly": [["garm_baby"], 1.5, "9.19b", 2], "alarm_fast": [0.7, True, "9.53"]},
        "box_model": {"alarm": ["garm_baby", "g_gobline_xmas", "knight_of_windstorm"]},
    }
    st = ar.settings(start)
    assert st == {
        "on": True,
        "need": 2,
        "solo": 0.7,
        "hud": True,
        "classes": ("garm_baby", "g_gobline_xmas", "knight_of_windstorm"),
    }
    assert ar.settings({"fixes": {"garm_fly": [["garm_baby"], 1.5, "9.19"]}})["need"] == 1
    assert ar.settings({})["on"] is False


def test_the_feed_is_both_streams_in_time_order_with_the_alarm_classes_only() -> None:
    main = [{"t_ns": 3, "boxes": [box(900, 300, 0.5), box(640, 336, 0.9, "player")]}]
    hud = [{"t_ns": 1, "boxes": []}, {"t_ns": 5, "boxes": [box(100, 100, 0.6, "garm_baby")]}]
    cls = ("garm_baby", "g_gobline_xmas")
    fd = ar.feed(main, hud, True, cls)
    assert [t for t, _ in fd] == [1, 3, 5]
    assert [len(b) for _, b in fd] == [0, 1, 1]  # the player box is not an alarm
    assert [t for t, _ in ar.feed(main, hud, False, cls)] == [3]


def test_rule_a_keeps_far_boxes_and_sure_near_ones() -> None:
    near_low = box(641, 336 + 30, 0.78)  # 30 px from her body, under NEAR_SOLO
    near_high = box(641 + 20, 336, 0.9)
    far = box(641 + 200, 336, 0.3)
    assert ar.near_filter([near_low, near_high, far]) == [near_high, far]
    assert ar.her_px(box(641 + 60, 336, 0.5)) == 60.0
    assert ar.near_filter([box(641 + 60, 336, 0.5)]) == []  # at NEAR_PX: still near
    assert ar.near_filter([box(641 + 61, 336, 0.5)]) != []


def test_the_rules_on_one_feed() -> None:
    near = box(650, 340, 0.45)  # her fight's neighbour
    far_true = box(1000, 200, 0.95, "garm_baby")
    fd = [
        (0 * S, [near]),
        (1 * S, [near]),
        (2 * S, [near]),  # a streak of 3 near boxes
        (5 * S, []),
        (10 * S, [far_true]),  # solo: at once
        (15 * S, []),
        (20 * S, [near]),
        (21 * S, [far_true]),
    ]  # the streak counts the near too
    today = ar.qualifying(fd, "today", 2, 0.7)
    assert [t // S for t, _ in today] == [1, 2, 10, 21]
    a = ar.qualifying(fd, "near", 2, 0.7)
    assert [t // S for t, _ in a] == [10, 21]
    c3 = ar.qualifying(fd, "confirm3", 2, 0.7)
    assert [t // S for t, _ in c3] == [2, 10, 21]
    eps = ar.episodes(today)
    assert [t // S for t, _ in eps] == [1, 10, 21]  # 2 s after 1 s: the same episode


def test_lost_true_episodes_and_the_tally() -> None:
    today = [
        {"t_ns": 10 * S, "judged": "true", "cls": "garm_baby", "cells": 9},
        {"t_ns": 30 * S, "judged": "false", "cls": "g_gobline_xmas", "nearest_job": 1249},
        {"t_ns": 50 * S, "judged": "true", "cls": "g_gobline_xmas", "cells": 1},
    ]
    near = [{"t_ns": 11 * S, "judged": "true", "cls": "garm_baby", "cells": 9}]
    assert [e["t_ns"] for e in ar.lost(today, near)] == [50 * S]
    t = ar.tally(today, 0.5)
    assert t["episodes"] == 3 and t["false"] == 1 and t["true"] == 2 and t["false_h"] == 2.0
    assert t["false_by_nearest_job"] == {"1249": 1}


def test_the_bars() -> None:
    def out(today_h: float, near_h: float, lost: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "rules": {"today": {"false_h": today_h}, "near": {"false_h": near_h}},
            "lost": {"near": lost},
        }

    assert ar.verdict(out(15.0, 4.5, []))["verdict"] == "PASS"  # 30 % exactly
    assert ar.verdict(out(15.0, 4.6, []))["false_h"]["verdict"] == "FAIL"
    v = ar.verdict(out(15.0, 1.0, [{"cells": 1}]))
    assert v["verdict"] == "PASS" and v["true_lost"]["lost"] == 1  # beside her: reported only
    assert ar.verdict(out(15.0, 1.0, [{"cells": 4}]))["verdict"] == "FAIL"


def test_a_replay_over_a_series_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = tmp_path / "20261121T010000-demo-dungeon-rogue-xmas_dun02-patrol-P2-L-play-r01B-hunt1"
    d.mkdir()
    start = {
        "t_ns": 0,
        "kind": "run_start",
        "fixes": {"garm_fly": [["garm_baby"], 1.5, "9.19b", 2], "alarm_fast": [0.7, True, "9.53"]},
        "box_model": {"alarm": ["garm_baby", "g_gobline_xmas"]},
    }
    (d / "events.jsonl").write_text(
        json.dumps(start) + "\n" + json.dumps({"t_ns": 3600 * S, "kind": "end"}) + "\n"
    )
    rows = [{"t_ns": t * S, "boxes": [box(650, 340, 0.45)]} for t in (100, 101, 102)]
    rows += [{"t_ns": 500 * S, "boxes": [box(1000, 200, 0.95, "garm_baby")]}]
    (d / "detections.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (d / "detections_hud.jsonl").write_text("")

    class FakeJudge:
        def __init__(self, packets: Any) -> None:
            pass

        def judge(self, t_ns: int, b: Any) -> dict[str, Any]:
            return ({"judged": "true", "cells": 10} if b[5] == "garm_baby"
                    else {"judged": "false", "nearest_job": 1249})  # fmt: skip

    monkeypatch.setattr(ar, "Judge", FakeJudge)
    got = ar.replay(["L-play"], demo=tmp_path)
    assert got["hours"] == 1.0 and len(got["sessions"]) == 1
    assert got["rules"]["today"]["false"] == 1 and got["rules"]["today"]["true"] == 1
    assert got["rules"]["near"]["false"] == 0 and got["rules"]["near"]["true"] == 1
    assert got["lost"]["near"] == [] and got["verdict"]["verdict"] == "PASS"


def test_a_session_without_its_start_record_is_refused(tmp_path: Path) -> None:
    d = tmp_path / "x-L-play-r01B-hunt1"
    d.mkdir()
    (d / "events.jsonl").write_text(json.dumps({"t_ns": 0, "kind": "walk"}) + "\n")
    with pytest.raises(SystemExit, match="no start record"):
        ar.replay_session(d)
