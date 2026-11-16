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


# --- S7: the post-vanish windows (the client still draws a unit after its vanish packet) --------


def test_in_post_vanish_is_after_a_vanish_and_within_the_window() -> None:
    gone = [10 * 10**9, 50 * 10**9]
    assert not q.in_post_vanish(10 * 10**9, gone, 5.0)  # the vanish's own instant: not after it
    assert q.in_post_vanish(int(10.1e9), gone, 5.0) and q.in_post_vanish(15 * 10**9, gone, 5.0)
    assert not q.in_post_vanish(int(15.1e9), gone, 5.0)
    assert not q.in_post_vanish(5 * 10**9, gone, 5.0)  # before any vanish
    assert not q.in_post_vanish(12 * 10**9, gone, None)  # S6's definition


def test_session_vanishes_reads_died_and_out_of_sight_of_the_alarm_species() -> None:
    pk = [{"type": "entity_appear", "gid": 1, "job": KNIGHT},
          {"type": "entity_appear", "gid": 2, "job": MYST},
          {"type": "entity_appear", "gid": 3, "job": GOB},
          {"type": "entity_vanish", "gid": 1, "reason": 1, "t_mono_ns": 30},
          {"type": "entity_vanish", "gid": 2, "reason": 1, "t_mono_ns": 20},  # not an alarm species
          {"type": "entity_vanish", "gid": 3, "reason": 0, "t_mono_ns": 10},  # out of sight: counts
          {"type": "entity_vanish", "gid": 3, "reason": 3, "t_mono_ns": 8},  # warped: not
          {"type": "entity_vanish", "gid": 3, "reason": 1, "t_mono_ns": 5},
          {"type": "entity_vanish", "gid": 9, "reason": 1, "t_mono_ns": 7}]  # fmt: skip
    assert q.session_vanishes(pk) == [5, 10, 30]
    assert q.session_vanishes(pk, reasons=(1,)) == [5, 30]


def test_post_vanish_frames_leave_the_alarm_free_set_only() -> None:
    """The party vanishes at t 12.5; frames 13-17.4 (inside 5 s) carry no unit yet a box is drawn
    (fires at 13 and 14): S6 counts them false, S7 sets them apart. Frame 30 (outside) fires falsely
    under both. A new party at 17 (6 s after the last party frame: a new visit) opens INSIDE the
    window: counted; the visits and their detection are S6's."""
    rows = [(10.0, [KNIGHT], [("k", 0.9)]), (11.0, [KNIGHT], [("k", 0.9)]),
            (13.0, [], [("k", 0.9)]), (14.0, [], [("k", 0.8)]), (15.0, [], []),
            (17.0, [GOB], [("g", 0.9)]), (17.4, [], []), (30.0, [], [("g", 0.9)])]  # fmt: skip
    units, frames = world(rows)
    s6 = q.alarm_view(units, frames, ACLS)
    s7 = q.alarm_view(units, frames, ACLS, vanishes={"": [int(12.5e9)]}, post_vanish_s=5.0)
    assert (s6["alarm_free_frames"], s6["false_fires"]) == (5, 3)
    assert (s7["alarm_free_frames"], s7["false_fires"], s7["false_fire_frames"]) == \
        (1, 1, ["f007"])  # fmt: skip
    assert (s7["post_vanish_frames"], s7["post_vanish_fires"], s7["post_vanish_frame_keys"]) == \
        (4, 2, ["f002", "f003", "f004", "f006"])  # fmt: skip
    assert set(s6["false_fire_frames"]) - set(s7["false_fire_frames"]) == {"f002", "f003"}
    assert s7["visits_opened_in_post_vanish"] == 1 and s6["visits_opened_in_post_vanish"] == 0
    assert s7["visits"] == s6["visits"] and s7["n_visits"] == s6["n_visits"] == 2
    with pytest.raises(SystemExit, match="needs the vanishes"):
        q.alarm_view(units, frames, ACLS, post_vanish_s=5.0)


def test_vanishes_cli_and_alarm_needs_both_options(tmp_path: Path) -> None:
    import gzip

    rec = tmp_path / "S"
    rec.mkdir()
    with gzip.open(rec / "packets.jsonl.gz", "wt") as fh:
        for e in ({"type": "entity_appear", "gid": 1, "job": KNIGHT},
                  {"type": "entity_vanish", "gid": 1, "reason": 1, "t_mono_ns": 42}):  # fmt: skip
            fh.write(json.dumps(e) + "\n")
    out = tmp_path / "v.json"
    assert q.main(["vanishes", str(rec), "--out", str(out)]) == 0
    doc = json.loads(out.read_text())
    assert doc["sessions"]["S"]["vanishes_ns"] == [42] and doc["reasons"] == [0, 1]
    assert q.main(["vanishes", str(rec), "--reasons", "0", "--out", str(out)]) == 0
    assert json.loads(out.read_text())["sessions"]["S"]["vanishes_ns"] == []
    with pytest.raises(SystemExit, match="come together"):
        q.main(["alarm", "--held-out", "u", "p", "--cache-manifest", str(out), "--out", "x",
                "--post-vanish-s", "5"])  # fmt: skip
