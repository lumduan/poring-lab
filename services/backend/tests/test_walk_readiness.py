"""scripts/walk_readiness.py: the Wilson interval, the pooled verdict (zero safety is hard; pooled
>= 90 %), and the scorer-output parsing."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "walk_readiness.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("walk_readiness", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["walk_readiness"] = mod
    spec.loader.exec_module(mod)
    return mod


wr = load()


def test_wilson_matches_the_textbook_values() -> None:
    lo, hi = wr.wilson(186, 200)
    assert lo == pytest.approx(0.8859, abs=5e-4) and hi == pytest.approx(0.9577, abs=5e-4)
    assert wr.wilson(50, 50)[1] == pytest.approx(1.0) and wr.wilson(0, 50)[0] == pytest.approx(0.0)
    with pytest.raises(ValueError):
        wr.wilson(0, 0)


def row(k: int, unsafe: int = 0) -> dict[str, object]:
    safety = {"request(live):npc_contact": unsafe} if unsafe else {}
    return wr.run_row("x", {"scored": {"success": k, "fail": 50 - k}, "SAFETY": safety})


def test_ready_needs_zero_safety_and_a_pooled_90() -> None:
    walk15 = [row(46), row(43), row(49), row(48)]  # 186 / 200
    got = wr.readiness(walk15)
    assert got["ready"] and got["pooled"]["rate"] == 0.93 and not got["ci_lower_bound_ge_ready"]
    assert not wr.readiness([row(47, 1), row(44, 1), row(49), row(44)])["ready"]  # walk@14
    low = wr.readiness([row(46), row(40), row(45), row(41)])  # walk@13: 172 / 200
    assert not low["ready"] and "86.0%" in low["why"]
    assert wr.readiness([row(45)])["ready"]  # a held-out map alone: 45 / 50 = 90 %


def test_reads_the_first_object_of_a_scorer_output() -> None:
    text = (
        json.dumps({"scored": {"success": 49, "fail": 1}, "SAFETY": {}})
        + "\n"
        + json.dumps({"x": 1})
    )
    assert wr.first_object(text)["scored"]["success"] == 49


def test_only_the_defined_safety_kinds_count() -> None:
    """iz_dun00 (2026-10-09): the scorer listed 4 GM "stand" acts (harness @warps) under SAFETY."""
    got = wr.run_row("dungeon", {"scored": {"success": 29, "fail": 21},
                                 "SAFETY": {"GM_act:stand": 4}})  # fmt: skip
    assert got["unsafe"] == 0 and got["other_gm_acts"] == {"GM_act:stand": 4}
    listed = {"GM_act:normal": 1, "request(live):npc_contact": 2}
    hit = wr.run_row("x", {"scored": {"success": 50, "fail": 0}, "SAFETY": listed})
    assert hit["unsafe"] == 3
