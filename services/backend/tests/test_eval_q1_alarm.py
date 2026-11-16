"""scripts/eval_q1.py, xmas02-detector.md Amendment S6: the alarm bar -- the runner's fire rule
(one alarm-class box >= 0.7, or two in a row >= 0.25), visits from the packets (a party unit on
screen), detection within 2.5 s of a visit's first frame, false fires on alarm-free frames, the
three lines with their minimums and the verdict. Synthetic units and detections only."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import eval_q1 as q  # noqa: E402

GOB, KNIGHT, GARM, MYST = 1607, 1251, 1515, 1249
ACLS = ["g", "k", "gb"]


def u(mob: int) -> dict[str, Any]:
    return {"gid": mob, "mob": mob, "region": [0, 0, 50, 50], "kept_box": None}


def box(cls: str, conf: float) -> dict[str, Any]:
    return {"cls": cls, "x1": 0, "y1": 0, "x2": 10, "y2": 10, "conf": conf}


def world(rows: list[tuple[float, list[int], list[tuple[str, float]]]]
          ) -> tuple[dict[str, Any], dict[str, Any]]:  # fmt: skip
    units, frames = {}, {}
    for i, (t, mobs, dets) in enumerate(rows):
        fk = f"f{i:03d}"
        units[fk] = {"t": int(t * 1e9), "units": [u(m) for m in mobs]}
        frames[fk] = [box(c, s) for c, s in dets]
    return units, frames


def test_fire_rule_solo_or_two_in_a_row() -> None:
    units, frames = world([
        (0.0, [], [("g", 0.3)]),  # one low box: no fire
        (1.0, [], [("k", 0.3)]),  # low after low, 1 s apart: confirm (classes may differ)
        (2.0, [], [("myst", 0.9)]),  # not an alarm class
        (3.0, [], [("gb", 0.71)]),  # solo
        (5.0, [], [("g", 0.3)]),  # low after a high, but 2 s apart: no
        (6.0, [], [("g", 0.2)]),  # below conf (predict_dir keeps >= 0.25 anyway)
    ])  # fmt: skip
    order = sorted(units)
    f = q.alarm_fires(order, units, frames, ACLS)
    assert [f[k] for k in order] == [None, "confirm", None, "solo", None, None]


def test_a_pair_never_spans_two_sessions() -> None:
    """The Goblin-free held-outs pool sessions: frames of two sessions 1 s apart on their own clocks
    are not a two-in-a-row pair, and a visit never spans two sessions."""
    units = {"A.000000001": {"t": 10**9, "units": [u(KNIGHT)]},
             "B.000000001": {"t": 2 * 10**9, "units": [u(KNIGHT)]}}  # fmt: skip
    frames = {"A.000000001": [box("g", 0.3)], "B.000000001": [box("g", 0.3)]}
    f = q.alarm_fires(sorted(units), units, frames, ACLS)
    assert f == {"A.000000001": None, "B.000000001": None}
    assert q.alarm_view(units, frames, ACLS)["n_visits"] == 2


def test_visits_detection_and_false_fires() -> None:
    """Visit 1 (t 10-13): the knight first, a solo fire at 12 (2 s: detected). Visit 2 (t 30-34):
    Goblins, the first fire at 33 (3 s: NOT detected), its Goblin-led delay 1 s from the Goblin's
    first frame at 32. Alarm-free frames: t 0-2, 20-21 (a Garm Baby at 22-23 is not free); a fire
    at t 21 is false."""
    rows = [(0.0, [MYST], []), (1.0, [], []), (2.0, [], [("gb", 0.3)]),
            (10.0, [KNIGHT], []), (11.0, [KNIGHT], [("k", 0.3)]), (12.0, [KNIGHT], [("k", 0.8)]),
            (13.0, [KNIGHT, GOB], []),
            (20.0, [], [("g", 0.3)]), (21.0, [], [("g", 0.4)]),
            (22.0, [GARM], [("gb", 0.9)]), (23.0, [GARM], []),
            (30.0, [KNIGHT], []), (31.0, [KNIGHT], []), (32.0, [GOB], [("g", 0.3)]),
            (33.0, [GOB], [("g", 0.75)]), (34.0, [GOB], [])]  # fmt: skip
    units, frames = world(rows)
    v = q.alarm_view(units, frames, ACLS)
    # 11.0: 0.3 after a frame with no box: no fire; 12.0: solo -> 2.0 s after the visit's start
    assert [(r["delay_s"], r["detected"], r["first_fire"]) for r in v["visits"]] == \
        [(2.0, True, "solo"), (3.0, False, "solo")]  # fmt: skip
    assert [r["goblin_delay_s"] for r in v["visits"]] == [0.0, 1.0]  # visit 1 fired before
    assert (v["n_visits"], v["detected"]) == (2, 1)
    # free: t 0, 1, 2, 20, 21 (MYST is not an alarm species); 21 fires (confirm after 20)
    assert (v["alarm_free_frames"], v["false_fires"], v["alarm_free_frames_with_a_box"]) == \
        (5, 1, 3)  # fmt: skip
    del frames["f000"]
    with pytest.raises(SystemExit, match="lacks 1 units frames"):
        q.alarm_view(units, frames, ACLS)


def held(n: int, k: int, free: int, false: int) -> dict[str, Any]:
    return {"n_visits": n, "detected": k, "alarm_free_frames": free, "false_fires": false}


def test_bars_minimums_and_verdict() -> None:
    ok = q.alarm_bars(held(30, 27, 100, 1), [held(0, 0, 60, 0), held(0, 0, 60, 1)])
    assert ok["verdict"] == "PASS"
    assert ok["lines"]["detection"]["rate"] == 0.9
    assert ok["lines"]["false_goblin_free"] == {
        "alarm_free_frames": 120, "false_fires": 1, "rate": 0.0083,
        "bar": "<= 1/100 of >= 50", "judged": True, "pass": True}  # fmt: skip
    assert q.alarm_bars(held(30, 26, 100, 1), [held(0, 0, 120, 0)])["verdict"] == "FAIL"
    assert q.alarm_bars(held(30, 27, 100, 2), [held(0, 0, 120, 0)])["verdict"] == "FAIL"
    assert q.alarm_bars(held(30, 27, 100, 0), [held(0, 0, 120, 2)])["verdict"] == "FAIL"
    few = q.alarm_bars(held(29, 29, 100, 0), [held(0, 0, 120, 0)])
    assert few["verdict"] == "INCONCLUSIVE" and few["lines"]["detection"]["pass"] is None
    assert q.alarm_bars(held(40, 40, 49, 0), [held(0, 0, 120, 0)])["verdict"] == "INCONCLUSIVE"
    assert q.alarm_bars(held(40, 40, 50, 0), [held(0, 0, 49, 0)])["verdict"] == "INCONCLUSIVE"
    # at 50 alarm-free frames, 1 % allows no false fire
    assert q.alarm_bars(held(40, 40, 50, 1), [held(0, 0, 120, 0)])["verdict"] == "FAIL"
    # a failed judged line decides even when another is unjudged
    assert q.alarm_bars(held(29, 20, 100, 5), [held(0, 0, 120, 0)])["verdict"] == "FAIL"


def test_alarm_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest = {"names": {"0": "player", "1": "npc", "2": "warp", "3": "garm_baby",
                          "4": "g_gobline_xmas", "5": "knight_of_windstorm"},
                "classes": {"mode": "species", "fixed": {"player": 0, "npc": 1, "warp": 2},
                            "monster_first_id": 3, "monsters": [GARM, GOB, KNIGHT]}}  # fmt: skip
    (tmp_path / "m.json").write_text(json.dumps(manifest))
    rows = [(float(t), [KNIGHT], [("knight_of_windstorm", 0.9)]) for t in range(3)]
    units, frames = world(rows)
    for fk in frames:
        for d in frames[fk]:
            d["cls"] = "knight_of_windstorm"
    (tmp_path / "u.json").write_text(json.dumps({"frames": units}))
    (tmp_path / "p.json").write_text(json.dumps({"imgsz": 1280, "conf": 0.25, "frames": frames}))
    out = tmp_path / "a.json"
    up, pp, mp = (str(tmp_path / f) for f in ("u.json", "p.json", "m.json"))
    argv = ["alarm", "--held-out", up, pp, "--free", up, pp, "--cache-manifest", mp]
    assert q.main([*argv, "--out", str(out)]) == 0
    doc = json.loads(out.read_text())
    assert doc["alarm_classes"] == ["g_gobline_xmas", "knight_of_windstorm", "garm_baby"]
    assert doc["held_out"]["n_visits"] == 1 and doc["verdict"] == "INCONCLUSIVE"
    assert json.loads(capsys.readouterr().out)["verdict"] == "INCONCLUSIVE"
    del manifest["names"]["5"]
    manifest["classes"]["monsters"] = [GARM, GOB]
    (tmp_path / "m.json").write_text(json.dumps(manifest))
    with pytest.raises(SystemExit, match="no class for"):
        q.main(
            [
                "alarm",
                "--held-out",
                str(tmp_path / "u.json"),
                str(tmp_path / "p.json"),
                "--cache-manifest",
                str(tmp_path / "m.json"),
                "--out",
                str(out),
            ]
        )
