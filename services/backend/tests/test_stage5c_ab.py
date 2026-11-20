"""scripts/stage5c_ab.py: stage 5c's live A/B (live-blocks.md 15.8) -- the hunt box (A = B5b-2)
against the ready-made box as functions in tabs (B = B5c): the plan's refusals before any input, the
drive line for both arms and the pre-registered bar. NOT run live here."""

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
import stage5c_ab as ab  # noqa: E402


def _base() -> str:
    try:
        return hc.git_show(hc.DRIVE_BASE, hc.TARGET)
    except (subprocess.CalledProcessError, OSError):
        pytest.skip(f"git cannot show {hc.DRIVE_BASE} here (a shallow checkout)")


def test_the_plan_alternates_the_two_shapes_with_the_same_runner(tmp_path: Path) -> None:
    doc = ab.plan_doc("s", 3, 20, "alternate", tmp_path / "s", base_text=_base(), seeds=5)
    assert isinstance(doc, dict), doc
    assert [r["arm"] for r in doc["runs"]] == ["A", "B", "B", "A", "A", "B"]
    assert doc["arms"]["A"]["box"] == doc["arms"]["B"]["box"] and doc["arms"]["B"]["left_out"] == []
    assert doc["arms"]["A"]["loop"] == doc["arms"]["B"]["loop"] == "hunt_loop"
    assert doc["vals"]["alarm_fast"] is True and doc["bar"] is ab.BAR
    assert doc["trace_scenarios"] == 2 * (13 + 5)
    for r in doc["runs"]:
        assert str(tmp_path / "s" / f"project-{r['arm']}.json") in r["argv"]


def _boxes() -> tuple[dict[str, Any], dict[str, Any]]:
    """The arms as the tool builds them (live-blocks 18.10 #1: B is the functions box with
    fly_first set to the hunt box's value, off; the fixture itself holds it on)."""
    return ab.arm_doc("A"), ab.arm_doc("B")


def test_b_is_the_ready_made_box_with_fly_first_off_and_the_fixture_alone_differs() -> None:
    raw = json.loads(ab.PROJECTS["B"].read_text())
    a, b = _boxes()
    assert "more than its shape" in str(ab.box_difference(a, raw))  # the fixture: fly_first ON
    assert ab.box_difference(a, b) is None  # the arm: the shape alone
    tab = next(t for t in b["nodes"][0]["tabs"] if t["name"] == "safety")
    assert tab["vars"]["fly_first"]["value"] is False
    assert tab["vars"]["fly_first_hp"]["value"] is False  # 18.13: the hunt box's value too
    assert tab["vars"]["fly_first_land"]["value"] is False  # 18.18: and this one
    raw_safety = next(t for t in raw["nodes"][0]["tabs"] if t["name"] == "safety")
    assert all(raw_safety["vars"][v]["value"] is True for _tab_name, v in ab.B_SAME_AS_A)
    # 18.15: the fixture names the deployed model (xmas02v1080 since 2026-11-20, 1080 Amendment
    # 24); B names A's model (xmas02), as s5c measured
    assert (
        ab.box_model_of(raw) == "xmas02v1080"
        and ab.box_model_of(b) == ab.box_model_of(a) == "xmas02"
    )


def _tab(d: dict[str, Any], name: str) -> dict[str, Any]:
    return next(t for t in d["nodes"][0]["tabs"] if t["name"] == name)


def test_the_box_difference_is_the_shape_alone() -> None:
    a, b = _boxes()
    assert ab.box_difference(a, b) is None
    assert "does not start its hunt core with hunt_loop()" in str(ab.box_difference(a, a))
    roles = json.loads(json.dumps(b))
    _tab(roles, "hunt")["vars"]["role_heal"] = {"kind": "lit", "value": "fly_wing"}
    assert "do not name exactly the functions" in str(ab.box_difference(a, roles))
    short = json.loads(json.dumps(b))
    _tab(short, "tick")["defs"][0]["body"] = [x for x in _tab(short, "tick")["defs"][0]["body"]
                                              if x["block"] != "step_loot"]  # fmt: skip
    assert "not the full hunt_tick()" in str(ab.box_difference(a, short))
    other = json.loads(json.dumps(b))
    other["max_runtime_s"] = 60
    assert "more than its shape" in str(ab.box_difference(a, other))


def test_the_plan_refuses_a_runner_whose_no_drive_program_is_not_5b1s(tmp_path: Path) -> None:
    bent = hc.TARGET.read_text().replace('hs.mode = "search"', 'hs.mode = "rest"', 1)
    got = ab.plan_doc("s", 1, 20, "alternate", tmp_path / "s", runner_text=bent,
                      base_text=_base(), seeds=0)  # fmt: skip
    assert isinstance(got, str) and "is not 5b-1's (huntstate_check.py drive)" in got


def _sc(label: str, arm: str, pair: int, **kw: Any) -> ab.Score5c:
    base = {"found": True, "minutes": 20.0, "kills": 70, "loot_steps": 30, "openers": 60,
            "gaps_ms": [200.0] * 50, "kinds": {"hp_read": 6000, "kill": 70, "drive": 2},
            "drive_starts": 1, "drive_ends": [{"kind": "drive", "what": "end",
                                               "ended": "run_end", "passed": {}}]}  # fmt: skip
    base.update(kw)
    s = ab.Score5c(label, arm, pair)
    for k, v in base.items():
        setattr(s, k, v)
    return s


def test_the_bar_judges_the_drive_of_both_arms() -> None:
    kinds = {"hp_read", "kill"}
    ok = [_sc(f"r{i}{x}", x, i) for i in (1, 2, 3) for x in ("A", "B")]
    v = ab.verdict(ok, 20, kinds)
    assert v["verdict"] == "PASS", v["lines"]
    assert v["lines"]["drive"] == {"drove": {"A": 3, "B": 3}, "problems": [], "pass": True}
    a_no = [_sc("r1A", "A", 1, drive_starts=0, drive_ends=[]), *ok[1:]]
    assert ab.verdict(a_no, 20, kinds)["lines"]["drive"]["pass"] is False
    end = {"what": "end", "ended": "run_end", "passed": {}, "left_out": ["loot"]}
    left = [*ok[:-1], _sc("r3B", "B", 3, drive_ends=[end])]
    v2 = ab.verdict(left, 20, kinds)
    assert v2["verdict"] == "FAIL" and "left out" in v2["lines"]["drive"]["problems"][0]
    slow = [
        _sc(f"r{i}{x}", x, i, **({"gaps_ms": [206.0] * 50} if x == "B" else {}))
        for i in (1, 2, 3)
        for x in ("A", "B")
    ]  # a B tick 6 ms slower: the median line fails
    assert ab.verdict(slow, 20, kinds)["lines"]["pace"]["pass"] is False
    assert ab.verdict(ok[:4], 20, kinds)["verdict"] == "INCONCLUSIVE"
    assert ab.VERSION == "9.56" and ab.BAR["pace_ms"] == 5.0 and ab.BAR["pace_p95"] is False
