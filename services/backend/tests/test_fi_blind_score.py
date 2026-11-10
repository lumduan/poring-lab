"""T-O3's scorer (scripts/fi_blind_score.py; docs/planning/xmas02-detector.md Amendment O.5,
ACCEPTED by O1 2026-11-10): T2-items per stratum, the two bars from EACH labeller, the two
pre-registered fallbacks and the round's verdict. The positive case: a SYNTHETIC answer file per
stratum, each with a known count."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import fi_blind_score as bs  # noqa: E402

SIZES = {"N": 15, "F": 15, "M": 10}


def key(eval_test: bool = False) -> dict[str, Any]:
    """O.5's pack: 15 N, 15 F, 10 M item crops + 10 plain and 10 hard E crops (60)."""
    crops: dict[str, Any] = {}
    i = 0
    for s, n in SIZES.items():
        for _ in range(n):
            i += 1
            crops[f"{i:03d}"] = {"truth": "item", "stratum": s, "kind": "item"}
    for kind in ("plain", "hard"):
        for _ in range(10):
            i += 1
            crops[f"{i:03d}"] = {"truth": "none", "stratum": "E", "kind": kind}
    return {"eval_test": eval_test, "crops": crops}


def answers(k: dict[str, Any], bad: dict[str, int] | None = None, how: str = "off",
            neg_yes: int = 0) -> dict[str, dict[str, Any]]:  # fmt: skip
    """Every crop right, except the first ``bad[s]`` item crops of stratum s (answered ``how``:
    "off" = yes / off, "no", "unsure", "missing") and the first ``neg_yes`` HARD E crops (yes)."""
    bad = dict(bad or {})
    out: dict[str, dict[str, Any]] = {}
    hard = 0
    for c, x in k["crops"].items():
        s = x["stratum"]
        if x["truth"] == "item":
            if bad.get(s, 0) > 0:
                bad[s] -= 1
                if how == "missing":
                    continue
                out[c] = ({"crop": c, "q1": "yes", "q2": "off"} if how == "off"
                          else {"crop": c, "q1": how, "q2": "-"})  # fmt: skip
            else:
                out[c] = {"crop": c, "q1": "yes", "q2": "good"}
        else:
            if x["kind"] == "hard" and hard < neg_yes:
                hard += 1
                out[c] = {"crop": c, "q1": "yes", "q2": "loose"}
            else:
                out[c] = {"crop": c, "q1": "no", "q2": "-"}
    return out


def test_perfect_answers_pass_with_exact_per_stratum_counts() -> None:
    k = key()
    r = bs.labeller(k, answers(k))
    assert r["verdict"] == "PASS"
    ps = r["per_stratum"]
    assert (ps["N"]["n"], ps["F"]["n"], ps["M"]["n"], ps["E"]["n"], ps["all"]["n"]) == (
        15,
        15,
        10,
        20,
        60,
    )
    assert ps["all"]["good"] == 40 and ps["all"]["present_right"] == 60
    assert ps["E"]["right_plain"] == 10 and ps["E"]["right_hard"] == 10


def test_a_weak_stratum_inside_the_pooled_bar_still_passes() -> None:
    k = key()
    r = bs.labeller(k, answers(k, {"N": 3}))  # 37 / 40 good = 0.925
    assert r["verdict"] == "PASS" and r["per_stratum"]["N"]["good_share"] == 0.8


def test_fallback_near_when_n_fails_and_f_m_pass() -> None:
    k = key()
    r = bs.labeller(k, answers(k, {"N": 6}))  # 34 / 40 = 0.85; without N: 25 / 25, 45 / 45
    assert r["verdict"] == "FALLBACK_NEAR" and r["without"] == "N"
    assert r["per_stratum"]["N"]["good_share"] == 0.6
    assert r["bars_without"]["good"] == 25 and r["bars_without"]["n"] == 45


def test_fallback_model_when_m_fails_and_n_f_pass() -> None:
    k = key()
    r = bs.labeller(k, answers(k, {"M": 5}))  # 35 / 40 = 0.875; M 0.5
    assert r["verdict"] == "FALLBACK_MODEL" and r["per_stratum"]["M"]["good_share"] == 0.5
    assert bs.labeller(k, answers(k, {"M": 4}))["verdict"] == "PASS"  # 36 / 40 = 0.90


def test_any_other_failure_fails() -> None:
    k = key()
    assert bs.labeller(k, answers(k, {"F": 5}))["verdict"] == "FAIL"  # F fails: no fallback
    assert bs.labeller(k, answers(k, {"N": 6, "M": 5}))["verdict"] == "FAIL"  # two strata
    r = bs.labeller(k, answers(k, neg_yes=4))  # 56 / 60 = 0.933 present right: E's hard ones
    assert r["verdict"] == "FAIL" and r["per_stratum"]["E"]["neg_yes"] == 4
    assert r["per_stratum"]["E"]["right_hard"] == 6
    assert bs.labeller(k, answers(k, neg_yes=3))["verdict"] == "PASS"  # 57 / 60 = 0.95


def test_unsure_and_missing_answers_are_wrong() -> None:
    """4 F crops: answered yes / off they are still item-present right (60 / 60) and good is 36 /
    40 = 0.90: PASS; answered unsure, no or not at all, present right is 56 / 60 < 0.95: FAIL
    (and F's 11 / 15 rules out every fallback)."""
    k = key()
    assert bs.labeller(k, answers(k, {"F": 4}, how="off"))["verdict"] == "PASS"
    for how in ("unsure", "no", "missing"):
        r = bs.labeller(k, answers(k, {"F": 4}, how=how))
        assert r["verdict"] == "FAIL", how
        assert r["per_stratum"]["F"]["good"] == 11
        assert r["per_stratum"]["all"]["present_right"] == 56


def test_round_verdict() -> None:
    assert bs.round_verdict(["PASS", "PASS"]) == "PASS"
    assert bs.round_verdict(["PASS", "FALLBACK_NEAR"]) == "FALLBACK_NEAR"
    assert bs.round_verdict(["FALLBACK_MODEL", "FALLBACK_MODEL"]) == "FALLBACK_MODEL"
    assert bs.round_verdict(["FALLBACK_NEAR", "FALLBACK_MODEL"]) == "FAIL"
    assert bs.round_verdict(["FAIL", "PASS"]) == "FAIL"
    assert bs.round_verdict([]) == "FAIL"


def test_score_two_labellers_and_the_evaluation_pack(tmp_path: Path) -> None:
    k = key()
    a, b = answers(k), answers(k, {"N": 6})
    res = bs.score(k, {"A": a, "B": b})
    assert res["verdict"] == "FALLBACK_NEAR" and res["both_good"] == 34
    assert res["agreement"]["n"] == 60 and res["agreement"]["q1"] == 60
    assert bs.score(k, {"A": a})["verdict"] == "FAIL"  # O.5 needs two labellers
    ev = key(eval_test=True)
    res = bs.score(ev, {"A": answers(ev), "B": answers(ev, {"F": 2})})
    assert res["verdict"] is None and res["both_good"] == 38
    assert len(bs.both_good(ev, [answers(ev), answers(ev, {"F": 2})])) == 38
    kp = tmp_path / "key.json"
    kp.write_text(json.dumps(ev))
    files = []
    for name, an in (("a", answers(ev)), ("b", answers(ev, {"M": 1}))):
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(list(an.values())))
        files.append(str(p))
    out = tmp_path / "both.json"
    assert bs.main(["--key", str(kp), *files, "--both-good", str(out)]) == 0
    assert len(json.loads(out.read_text())) == 39


@pytest.mark.parametrize("s", ["N", "F", "M"])
def test_each_item_stratum_alone(s: str) -> None:
    """One stratum's crops wrong at a time, the others perfect: each stratum's own count is the
    one that moved (the assertion names which)."""
    k = key()
    r = bs.labeller(k, answers(k, {s: 2}))
    for t in ("N", "F", "M"):
        want = SIZES[t] - (2 if t == s else 0)
        assert r["per_stratum"][t]["good"] == want, t
