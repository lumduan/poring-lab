"""scripts/stage5b2_ab.py: stage 5b-2's live A/B (live-blocks.md 14) -- the one box played by
run()'s own driver (A = B5b-1) against the same box plus its hunt tab (B = B5b-2): the plan's
refusals before any input, the drive's own score line and the pre-registered bar. NOT run live."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import huntstate_check as hc  # noqa: E402
import stage5b2_ab as ab  # noqa: E402


def _base() -> str:
    try:
        return hc.git_show(hc.DRIVE_BASE, hc.TARGET)
    except (subprocess.CalledProcessError, OSError):
        pytest.skip(f"git cannot show {hc.DRIVE_BASE} here (a shallow checkout)")


def test_the_plan_alternates_the_two_boxes_with_the_same_runner_and_settings(
    tmp_path: Path,
) -> None:
    doc = ab.plan_doc("s", 3, 20, "alternate", tmp_path / "s", base_text=_base(), seeds=10)
    assert isinstance(doc, dict), doc
    assert [r["arm"] for r in doc["runs"]] == ["A", "B", "B", "A", "A", "B"]
    assert doc["arms"]["A"]["loop"] is None and doc["arms"]["B"]["loop"] == "hunt_loop"
    assert doc["arms"]["A"]["box"] == doc["arms"]["B"]["box"]  # run() gets the same arguments
    assert doc["arms"]["A"]["project_hash"] != doc["arms"]["B"]["project_hash"]
    assert doc["vals"]["alarm_fast"] is True and doc["bar"] is ab.BAR
    assert doc["drive_base"] == "bb6d41eb" and doc["trace_scenarios"] == 23
    for r in doc["runs"]:
        argv = r["argv"]
        assert str(tmp_path / "s" / f"project-{r['arm']}.json") in argv
        assert "scripts/flow_play.py" in argv and "scripts/runner_pin.py" not in argv
    norm = [[x for x in r["argv"] if not x.startswith(str(tmp_path)) and x not in (
        doc["arms"]["A"]["project_hash"], doc["arms"]["B"]["project_hash"]) and "-r0" not in x]
        for r in doc["runs"]]  # fmt: skip
    assert all(v == norm[0] for v in norm)  # the same command but the box and the labels


def test_the_box_difference_is_the_hunt_tab_alone() -> None:
    a = json.loads(ab.PROJECTS["A"].read_text())
    b = json.loads(ab.PROJECTS["B"].read_text())
    assert ab.box_difference(a, b) is None
    assert ab.box_difference(a, a) == "B has no hunt tab"
    assert ab.box_difference(b, b) is not None  # A with a hunt tab
    bent = json.loads(json.dumps(b))
    bent["max_runtime_s"] = 60
    assert "more than its hunt tab" in str(ab.box_difference(a, bent))
    loop = json.loads(json.dumps(b))
    hunt = next(t for t in loop["nodes"][0]["tabs"] if t["name"] == "hunt")
    hunt["defs"][0]["body"][0]["body"][1]["block"] = "wait_kill"  # no recipe: not the canonical
    assert "not the canonical loop" in str(ab.box_difference(a, loop))


def test_the_plan_refuses_a_runner_whose_no_drive_program_is_not_5b1s(tmp_path: Path) -> None:
    bent = hc.TARGET.read_text().replace('hs.mode = "search"', 'hs.mode = "rest"', 1)
    got = ab.plan_doc("s", 1, 20, "alternate", tmp_path / "s", runner_text=bent,
                      base_text=_base(), seeds=0)  # fmt: skip
    assert isinstance(got, str) and "is not 5b-1's (huntstate_check.py drive)" in got


def _sc(label: str, arm: str, pair: int, **kw: Any) -> ab.Score5b2:
    base = {"found": True, "minutes": 20.0, "kills": 70, "loot_steps": 30, "openers": 60,
            "gaps_ms": [200.0] * 50, "kinds": {"hp_read": 6000, "kill": 70}}  # fmt: skip
    base.update(kw)
    s = ab.Score5b2(label, arm, pair)
    for k, v in base.items():
        setattr(s, k, v)
    return s


def _drove(**e: Any) -> dict[str, Any]:
    return {"drive_starts": 1, "drive_ends": [{"kind": "drive", "what": "end", "ended": "time_box",
                                               "passed": {}, **e}]}  # fmt: skip


def test_the_bar_passes_equal_arms_and_names_a_drive_that_passed_a_step() -> None:
    kinds = {"hp_read", "kill"}
    ok = [_sc(f"r{i}{x}", x, i, kills=70 + (i if x == "B" else 0), **(_drove() if x == "B" else {}))
          for i in (1, 2, 3) for x in ("A", "B")]  # fmt: skip
    v = ab.verdict(ok, 20, kinds)
    assert v["verdict"] == "PASS", v["lines"]
    assert v["lines"]["drive"] == {"B_drove": 3, "problems": [], "pass": True}
    assert v["lines"]["deaths"]["pass"] is True  # 0 vs 0: never a strict "<" against a zero arm
    bad = [*ok[:-1], _sc("r3B", "B", 3, **_drove(passed={"loot": 1}))]
    v2 = ab.verdict(bad, 20, kinds)
    assert v2["verdict"] == "FAIL" and "it passed steps" in v2["lines"]["drive"]["problems"][0]
    spin = [*ok[:-1], _sc("r3B", "B", 3, **_drove(ended="spin"))]
    assert ab.verdict(spin, 20, kinds)["lines"]["drive"]["pass"] is False
    a_drove = [_sc("r1A", "A", 1, **_drove()), *ok[1:]]
    assert ab.verdict(a_drove, 20, kinds)["lines"]["drive"]["pass"] is False
    few = ok[:4]  # two pairs: kills and loot unjudged
    assert ab.verdict(few, 20, kinds)["verdict"] == "INCONCLUSIVE"


def test_the_drive_record_is_the_only_new_kind_allowed() -> None:
    kinds = {"hp_read", "kill"}
    runs = [_sc(f"r{i}{x}", x, i, **(_drove() | {"kinds": {"hp_read": 6000, "kill": 70,
            "drive": 2}} if x == "B" else {})) for i in (1, 2, 3) for x in ("A", "B")]  # fmt: skip
    v = ab.verdict(runs, 20, kinds)
    assert v["lines"]["kinds"] == {"new_in_B": [], "pass": True}
    runs[1].kinds = {**runs[1].kinds, "surprise": 1}
    assert ab.verdict(runs, 20, kinds)["lines"]["kinds"]["new_in_B"] == ["surprise"]


def test_score_drive_reads_the_runner_sessions_records() -> None:
    sc = ab.Score5b2("r1B", "B", 1)
    ab.score_drive(sc, [{"kind": "drive", "what": "start", "version": "9.55"},
                        {"kind": "hp_read"},
                        {"kind": "drive", "what": "end", "ended": "run_end", "passed": {},
                         "ticks": 4000}])  # fmt: skip
    assert sc.drive_starts == 1 and sc.drive_ends[0]["ended"] == "run_end"
    assert sc.doc()["drive_ends"] == [{"ended": "run_end", "words": None, "ticks": 4000,
                                       "passed": {}}]  # fmt: skip
    assert ab.VERSION == "9.55" and ab.canonical_loop([]) is False
