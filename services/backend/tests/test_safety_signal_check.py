"""scripts/safety_signal_check.py: the positive case needs BOTH our request and the server's act
from us, inside the window after the click (Batt, 2026-10-08: prove a signal can fire)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def ssc() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "safety_signal_check", SCRIPTS / "safety_signal_check.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_positive_case_needs_the_request_and_the_act_in_the_window(ssc: ModuleType) -> None:
    gm, mob, t = 2000002, 110023393, 10_000_000_000
    req = {"type": "attack_request", "target_gid": mob, "t_mono_ns": t + 100_000_000}
    act = {
        "type": "act",
        "kind": "normal",
        "src_gid": gm,
        "target_gid": mob,
        "t_mono_ns": t + 900_000_000,
    }
    late = {**act, "t_mono_ns": t + 9_000_000_000}
    theirs = {**act, "src_gid": mob, "target_gid": gm}
    assert ssc.judge_attack([req, act], t)["pass"] is True
    assert ssc.judge_attack([act], t)["pass"] is False  # the blind sensor: acts but no request
    assert ssc.judge_attack([req, late], t)["pass"] is False  # outside the 5 s window
    assert ssc.judge_attack([req, theirs], t)["pass"] is False  # the monster hit US


def test_rec0_judges_each_cancel_and_needs_the_control_to_see_the_attack_continue(
    ssc: ModuleType,
) -> None:
    """§3.19: a trial succeeds with no GM hit in [t_cancel+0.3 s, +5 s] and no attack request
    after t_cancel; a cancel 'stops an attack' at >= 9/10 only if C0 shows the attack continuing."""
    S = 1_000_000_000
    gm = ssc.GM_AID

    def hit(t: float) -> dict[str, Any]:
        return {"type": "act", "src_gid": gm, "kind": "normal", "t_mono_ns": int(t * S)}

    trials: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for k in range(10):  # C0: no cancel, the hits continue
        tc = 100 * k + 10
        trials.append({"k": k, "condition": "C0", "t_cancel": tc * S})
        events += [hit(tc + 0.8), hit(tc + 1.6)]
    for k in range(10):  # C4: the attack stops (one swing in flight before +0.3 s is allowed)
        tc = 2000 + 100 * k
        trials.append({"k": 10 + k, "condition": "C4", "t_cancel": tc * S})
        events.append(hit(tc + 0.1))
    for k in range(10):  # C1: after the 2-cell walk the attack resumes in 3 trials
        tc = 4000 + 100 * k
        trials.append({"k": 20 + k, "condition": "C1", "t_cancel": tc * S})
        if k < 3:
            events += [{"type": "attack_request", "t_mono_ns": int((tc + 0.5) * S)}, hit(tc + 1.0)]
    v = ssc.judge_rec0(trials, events)
    assert v["control_proven"] and v["per_condition"]["C0"]["continued"] == 10
    assert v["stops_an_attack"]["C4"] and v["per_condition"]["C4"]["success"] == 10
    assert not v["stops_an_attack"]["C1"] and v["per_condition"]["C1"]["success"] == 7
    no_control = ssc.judge_rec0([t for t in trials if t["condition"] != "C0"], events)
    assert not no_control["stops_an_attack"]["C4"]  # without the positive control, nothing passes


def test_rec0b_counts_only_engaged_trials_with_one_rule_for_every_condition(
    ssc: ModuleType,
) -> None:
    """§3.22: INCLUDED = an attack request AND the GM's first hit between the attack click and the
    cancel, for every condition (C0 too); the bar runs on included trials, >= 10 of them."""
    S = 1_000_000_000
    gm = ssc.GM_AID

    def hit(t: float) -> dict[str, Any]:
        return {"type": "act", "src_gid": gm, "kind": "normal", "t_mono_ns": int(t * S)}

    def req(t: float) -> dict[str, Any]:
        return {"type": "attack_request", "t_mono_ns": int(t * S)}

    trials: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    t0 = 10.0
    for cond, n_engaged, n_missed, continues in (("C0", 10, 3, True), ("C4", 11, 2, False),
                                                 ("C1", 9, 0, False)):  # fmt: skip
        for k in range(n_engaged + n_missed):
            th, tc = t0, t0 + 0.8
            trials.append(
                {"k": len(trials), "condition": cond, "t_hit": th * S, "t_cancel": tc * S}
            )
            if k < n_engaged:  # engaged: the request and the first hit before the cancel
                events += [req(th + 0.2), hit(th + 0.5)]
                if continues:
                    events += [hit(tc + 1.0), hit(tc + 2.0)]
            t0 += 100.0
    v = ssc.judge_rec0b(trials, events)
    pc = v["per_condition"]
    assert (pc["C0"]["attempts"], pc["C0"]["included"]) == (13, 10)  # the misses do not count
    assert v["control_proven"] and pc["C0"]["continued"] == 10
    assert v["stops_an_attack"]["C4"] and pc["C4"]["success"] == 11
    assert not v["stops_an_attack"]["C1"] and "C1" in v["not_enough_engaged"]  # 9 < 10 engaged
