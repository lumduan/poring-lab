"""scripts/stage10_ab.py: s10ab, the stale re-fire fix's live A/B (live-blocks.md 18.17) -- the
ready-made box as it is (A, fly_first_land off) against it with fly_first_land on (B): the plan's
refusals before any input (one setting apart; the five proofs), the stale re-fires from the
runner's records, the judged lines. NOT run live here."""

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
import stage5c_ab as s5c  # noqa: E402
import stage9_ab as s9  # noqa: E402
import stage10_ab as ab  # noqa: E402

S = 1_000_000_000


def _bases() -> dict[str, str]:
    try:
        return {k: hc.git_show(rev, hc.TARGET) for k, rev in (
            ("drive", hc.DRIVE_BASE), ("check", hc.BASE_REV), ("flag", hc.FLAG_BASE),
            ("pick", hc.PICK_BASE), ("land", hc.LAND_BASE))}  # fmt: skip
    except (subprocess.CalledProcessError, OSError):
        pytest.skip("git cannot show the bases here (a shallow checkout)")


# --- the plan ------------------------------------------------------------------------------------
def test_the_plan_alternates_two_copies_differing_in_fly_first_land_alone(tmp_path: Path) -> None:
    doc = ab.plan_doc("s", 4, 20, "alternate", tmp_path / "s", bases=_bases(), seeds=3)
    assert isinstance(doc, dict), doc
    assert [r["arm"] for r in doc["runs"]] == ["A", "B", "B", "A", "A", "B", "B", "A"]
    va, vb = doc["vals"]["A"], doc["vals"]["B"]
    assert {k for k in va if va[k] != vb[k]} == {"fly_first_land"}
    assert va["fly_first_land"] is False and vb["fly_first_land"] is True
    assert va["fly_first"] is True and va["fly_first_hp"] is True and va["FF_LAND_S"] == 0.75
    assert doc["arms"]["A"]["box"] == doc["arms"]["B"]["box"]
    assert doc["arms"]["A"]["box"]["box_model"]["id"] == "xmas02sk"
    assert doc["land_base"] == hc.LAND_BASE and doc["bar"] is ab.BAR and ab.BAR["land_s"] == 0.75
    for r in doc["runs"]:
        assert str(tmp_path / "s" / f"runner-config-{r['arm']}.json") in r["argv"]


def test_the_arms_differ_in_their_fly_first_land_block_alone() -> None:
    a, b = ab.arm_doc("A", 20), ab.arm_doc("B", 20)
    assert ab.box_difference(a, b) is None
    assert "does not hold fly_first_land = True" in str(ab.box_difference(a, a))
    off = json.loads(json.dumps(b))
    next(t for t in off["nodes"][0]["tabs"] if t["name"] == "safety")["vars"]["fly_first_hp"] = {
        "kind": "lit", "value": False}  # fmt: skip
    assert "fly_first_hp = True" in str(ab.box_difference(a, off))
    gb = json.loads(json.dumps(b))
    s5c.set_box_model(gb, "xmas02")
    assert "use_model is not xmas02sk" in str(ab.box_difference(a, gb))
    other = json.loads(json.dumps(b))
    next(t for t in other["nodes"][0]["tabs"] if t["name"] == "safety")["vars"]["FF_LAND_S"] = {
        "kind": "lit", "value": 1.0}  # fmt: skip
    assert "more than its fly_first_land block" in str(ab.box_difference(a, other))


def test_the_plan_refuses_an_old_runner_or_a_failed_land_proof(tmp_path: Path) -> None:
    bases = _bases()
    text = hc.TARGET.read_text()
    old = text.replace('FLY_LAND_VERSION = "9.60"', 'FLY_LAND_VERSION = "9.59"', 1)
    got = ab.plan_doc("s", 1, 20, "alternate", tmp_path, runner_text=old, bases=bases, seeds=0)
    assert isinstance(got, str) and "is not dungeon@9.60" in got
    bent = text.replace("FF_REARM_S = 1.0", "FF_REARM_S = 1.5", 1)  # a 9.57 line, no branch
    got2 = ab.plan_doc("s", 1, 20, "alternate", tmp_path, runner_text=bent, bases=bases, seeds=0)
    assert isinstance(got2, str) and "huntstate_check" in got2 and "fails" in got2


# --- the stale re-fires from the runner's records -------------------------------------------------
def _fly(t_key: float, grab: float | None, src: str = "alarm", cls: str = "garm_baby") -> dict:
    return {
        "kind": "fly_first",
        "what": "fly",
        "why": "garm",
        "src": src,
        "t_key_ns": int(t_key * S),
        "t_read_ns": int(t_key * S),
        "sight": None if grab is None else {"t_ns": int(grab * S), "cls": cls, "score": 0.9},
    }


def test_a_stale_re_fire_is_a_sighting_grabbed_before_the_previous_key_plus_the_window() -> None:
    ev = [{"kind": "run_start", "fixes": {"fly_first_land": [0.75, "9.60"]}},
          _fly(10.0, 9.9), _fly(12.4, 10.3),  # grabbed 0.3 s after the key at 10.0: stale
          _fly(30.0, 29.9), _fly(32.4, 32.2),  # grabbed 2.2 s after: fresh (r07B's)
          {"kind": "fly_first", "what": "land", "t_key_ns": int(50.0 * S)},  # an HP / end fly
          _fly(52.3, 50.5),  # 0.5 s after that Fly Wing: stale
          _fly(70.0, None, src="line")]  # a boss line: no sighting, not judged  # fmt: skip
    assert ab.land_of(ev) == 0.75 and ab.land_of([]) == ab.LAND_S
    assert ab.land_of([{"kind": "run_start", "fixes": {"fly_first_land": [1.2, "9.60"]}}]) == 1.2
    stale, n = ab.refires_of(ev, ab.land_of(ev))
    assert n == 5 and [(x.after_prev_s, x.prev_key_ns) for x in stale] == [
        (0.3, int(10.0 * S)), (0.5, int(50.0 * S))]  # fmt: skip
    assert ab.refires_of(ev, 0.2)[0] == []  # a narrower window: none of them


def _sc(label: str, arm: str, pair: int, **kw: Any) -> ab.Score10:
    base = {"found": True, "minutes": 20.0, "kills": 70, "loot_steps": 30, "openers": 60,
            "gaps_ms": [200.0] * 50, "kinds": {"hp_read": 6000, "kill": 70, "drive": 2},
            "drive_starts": 1, "drive_ends": [{"kind": "drive", "what": "end",
                                               "ended": "run_end", "passed": {}}],
            "alarm_flies": 3}  # fmt: skip
    base.update(kw)
    s = ab.Score10(label, arm, pair)
    for k, v in base.items():
        setattr(s, k, v)
    return s


def _stale(n: int) -> list[ab.Refire]:
    return [ab.Refire(10 * S, int(10.3 * S), 10 * S, 0.75, "garm_baby") for _ in range(n)]


def test_b_must_have_no_stale_re_fire_and_deaths_are_judged() -> None:
    kinds = {"hp_read", "kill"}
    ok = [_sc(f"r{i}{x}", x, i, stale=_stale(1) if x == "A" else []) for i in (1, 2, 3, 4)
          for x in ("A", "B")]  # fmt: skip
    v = ab.verdict(ok, 20, kinds)
    assert v["verdict"] == "PASS", v["lines"]
    line = v["lines"]["stale"]
    assert (line["A"]["stale"], line["B"]["stale"], line["pass"]) == (4, 0, True)
    bad = [*ok[:7], _sc("r4B", "B", 4, stale=_stale(1))]
    vb = ab.verdict(bad, 20, kinds)
    assert vb["verdict"] == "FAIL"
    assert vb["lines"]["stale"]["pass"] is False and vb["lines"]["stale"]["B"]["where"]
    none = [_sc(f"r{i}{x}", x, i, alarm_flies=0) for i in (1, 2, 3, 4) for x in ("A", "B")]
    vn = ab.verdict(none, 20, kinds)
    assert vn["verdict"] == "INCONCLUSIVE" and vn["lines"]["stale"]["pass"] is None
    dead = [*ok[:7], _sc("r4B", "B", 4, deaths=1)]
    vd = ab.verdict(dead, 20, kinds)
    assert vd["verdict"] == "FAIL" and vd["lines"]["deaths"]["pass"] is False
    both = [*ok[:6], _sc("r4A", "A", 4, deaths=1), _sc("r4B", "B", 4, deaths=1)]
    assert ab.verdict(both, 20, kinds)["lines"]["deaths"]["pass"] is True  # <=, not <
    assert "false_flies_h" in v["lines"]["report"] and "false_flies_h" not in v["lines"]
    assert s9.BAR["deaths"] == ab.BAR["deaths"]
