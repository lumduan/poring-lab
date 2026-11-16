"""scripts/stage8_ab.py: s8ab, the HP Fly Wing first's live A/B (live-blocks.md 18.11) -- the box
with fly_first ON (A) against it with fly_first_hp ON too (B): the plan's refusals before any
input (the three proofs), the HP line and when it is judgeable, the pre-registered extension,
deaths reported. NOT run live here."""

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
import stage7_ab as s7  # noqa: E402
import stage8_ab as ab  # noqa: E402

S = 1_000_000_000


def _bases() -> tuple[str, str, str]:
    try:
        return (hc.git_show(hc.DRIVE_BASE, hc.TARGET), hc.git_show(hc.BASE_REV, hc.TARGET),
                hc.git_show(hc.FLAG_BASE, hc.TARGET))  # fmt: skip
    except (subprocess.CalledProcessError, OSError):
        pytest.skip("git cannot show the bases here (a shallow checkout)")


def test_the_plan_alternates_two_copies_differing_in_fly_first_hp_alone(tmp_path: Path) -> None:
    d, c, f = _bases()
    doc = ab.plan_doc("s", 4, 20, "alternate", tmp_path / "s", base_text=d, check_base=c,
                      flag_base=f, seeds=3)  # fmt: skip
    assert isinstance(doc, dict), doc
    assert [r["arm"] for r in doc["runs"]] == ["A", "B", "B", "A", "A", "B", "B", "A"]
    va, vb = doc["vals"]["A"], doc["vals"]["B"]
    assert va["fly_first"] is True and vb["fly_first"] is True
    assert va["fly_first_hp"] is False and vb["fly_first_hp"] is True
    assert {k for k in va if va[k] != vb[k]} == {"fly_first_hp"}
    assert doc["flag_base"] == hc.FLAG_BASE and doc["bar"] is ab.BAR
    for r in doc["runs"]:
        assert str(tmp_path / "s" / f"runner-config-{r['arm']}.json") in r["argv"]


def test_the_arms_differ_in_their_fly_first_hp_block_alone() -> None:
    a, b = ab.arm_doc("A", 20), ab.arm_doc("B", 20)
    assert ab.box_difference(a, b) is None
    assert "does not hold fly_first_hp = True" in str(ab.box_difference(a, a))
    off = json.loads(json.dumps(b))
    next(t for t in off["nodes"][0]["tabs"] if t["name"] == "safety")["vars"]["fly_first"] = {
        "kind": "lit", "value": False}  # fmt: skip
    assert "fly_first = True" in str(ab.box_difference(a, off))
    other = json.loads(json.dumps(b))
    other["max_runtime_s"] = 60
    assert "more than its fly_first_hp block" in str(ab.box_difference(a, other))


def test_the_plan_refuses_a_runner_that_is_not_9_58_or_whose_flag_proof_fails(
    tmp_path: Path,
) -> None:
    d, c, f = _bases()
    text = hc.TARGET.read_text()
    old = text.replace('FLY_FIRST_HP_VERSION = "9.58"', 'FLY_FIRST_HP_VERSION = "9.57"', 1)
    got = ab.plan_doc("s", 1, 20, "alternate", tmp_path, runner_text=old, base_text=d,
                      check_base=c, flag_base=f, seeds=0)  # fmt: skip
    assert isinstance(got, str) and "is not dungeon@9.58" in got
    bent = text.replace("FF_REARM_S = 1.0", "FF_REARM_S = 1.5", 1)  # a 9.57 line, no branch
    got2 = ab.plan_doc("s", 1, 20, "alternate", tmp_path, runner_text=bent, base_text=d,
                       check_base=c, flag_base=f, seeds=0)  # fmt: skip
    assert isinstance(got2, str) and "huntstate_check flag fails" in got2


def _sc(label: str, arm: str, pair: int, **kw: Any) -> s7.Score7:
    base = {"found": True, "minutes": 20.0, "kills": 70, "loot_steps": 30, "openers": 60,
            "gaps_ms": [200.0] * 50, "kinds": {"hp_read": 6000, "kill": 70, "drive": 2},
            "drive_starts": 1, "drive_ends": [{"kind": "drive", "what": "end",
                                               "ended": "run_end", "passed": {}}]}  # fmt: skip
    base.update(kw)
    s = s7.Score7(label, arm, pair)
    for k, v in base.items():
        setattr(s, k, v)
    return s


def _hp(bare: bool, req: float | None = 0.08, keys: list[str] | None = None) -> s7.Fly:
    return s7.Fly(10 * S, 10 * S, "rate 1200 at hp 0.40", "hp", req, keys or [], False,
                  {"hp": True, "bare": bare})  # fmt: skip


def _boss() -> s7.Fly:
    return s7.Fly(10 * S, 10 * S, "garm", "alarm", 0.08, [], False, {"score": 0.8})


def test_the_hp_line_needs_one_bare_hp_fly_and_judges_every_one() -> None:
    kinds = {"hp_read", "kill"}
    flies = {("B", 1): [_hp(True), _boss()], ("B", 2): [_hp(False)]}
    ok = [_sc(f"r{i}{x}", x, i, flies_ff=flies.get((x, i), [_boss()] if x == "A" else []))
          for i in (1, 2, 3, 4) for x in ("A", "B")]  # fmt: skip
    v = ab.verdict(ok, 20, kinds)
    assert v["verdict"] == "PASS", v["lines"]
    line = v["lines"]["fly_first_hp"]
    assert (line["flies"], line["judged"], line["bare"], line["pass"]) == (2, 2, 1, True)
    assert v["lines"]["report"]["boss_fly_first"]["A"]["flies"] == 4
    assert "fly_first" not in v["lines"]  # the boss line is reported, not judged, here
    # only armed HP flies: B and A play the same program there -> INCONCLUSIVE
    armed = [_sc(f"r{i}{x}", x, i, flies_ff=[_hp(False)] if x == "B" else [])
             for i in (1, 2, 3, 4) for x in ("A", "B")]  # fmt: skip
    v2 = ab.verdict(armed, 20, kinds)
    assert v2["verdict"] == "INCONCLUSIVE" and v2["lines"]["fly_first_hp"]["pass"] is None
    # the extension: a bare HP fly in an --also block makes the HP line judgeable
    also = [_sc("x1B", "B", 1, flies_ff=[_hp(True)])]
    assert ab.verdict(armed, 20, kinds, also=also)["verdict"] == "PASS"
    # a weapon key before an HP Fly Wing, or no request: FAIL, judgeable or not
    v3 = ab.verdict([*armed[:7], _sc("r4B", "B", 4, flies_ff=[_hp(False, keys=["F5"])])], 20,
                    kinds)  # fmt: skip
    assert v3["verdict"] == "FAIL" and "weapon key" in v3["lines"]["fly_first_hp"]["problems"][0]
    dead = [*armed[:7], _sc("r4B", "B", 4, deaths=2, flies_ff=[_hp(True)])]
    v4 = ab.verdict(dead, 20, kinds)
    assert v4["verdict"] == "PASS" and v4["lines"]["report"]["deaths"]["B"] == 2  # never judged
