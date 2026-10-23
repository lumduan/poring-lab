"""blind_score.py (orcsdun01-detector.md section 5's bars): per species, each labeller's good and
species-right shares; the pass needs both bars from every labeller."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import blind_score as bs  # noqa: E402

KEY = {"letters": {"A": 1153, "B": 1005},
       "crops": {f"{i:03d}": {"mob": 1153 if i <= 10 else 1005} for i in range(1, 21)}}  # fmt: skip


def answers(good_zombie: int, right_bat: int) -> dict:
    out = {}
    for i in range(1, 21):
        c = f"{i:03d}"
        if i <= 10:
            out[c] = {"q1": "yes", "q2": "good" if i <= good_zombie else "off", "q3": "A"}
        else:
            out[c] = {"q1": "yes", "q2": "good", "q3": "B" if i - 10 <= right_bat else "A"}
    return out


def test_both_bars_per_species() -> None:
    r = bs.per_species(KEY, answers(good_zombie=9, right_bat=10))
    assert r[1153]["good"] == 0.9 and r[1153]["pass"]  # 9 / 10 good = the bar
    assert r[1005]["species"] == 1.0 and r[1005]["pass"]
    r = bs.per_species(KEY, answers(good_zombie=8, right_bat=9))
    assert not r[1153]["pass"] and r[1153]["off"] == 2  # 8 / 10 good
    assert not r[1005]["pass"]  # 9 / 10 species right < 95 %


def test_both_good_needs_both_labellers_and_the_right_species() -> None:
    a, b = answers(10, 10), answers(9, 10)
    assert len(bs.both_good(KEY, a, b)) == 19  # b's crop 010 is "off"


def test_round4_restricts_the_key_to_one_candidates_sample() -> None:
    """3i: a crop counts for every sample it is in; the controls stay in, deciding nothing."""
    key = {"letters": {"A": 1153, "B": 1005, "C": 1002}, "candidates": ["o3", "1c"],
           "crops": {**{f"{i:03d}": {"mob": 1153, "samples": ["o3", "1c"] if i <= 5 else ["o3"]}
                        for i in range(1, 11)},
                     "011": {"mob": 1002, "samples": ["o3", "1c"], "control": True}}}  # fmt: skip
    ans = {f"{i:03d}": {"q1": "yes", "q2": "good" if i <= 5 else "off", "q3": "A"}
           for i in range(1, 11)}  # fmt: skip
    ans["011"] = {"q1": "yes", "q2": "off", "q3": "B"}  # a failing control decides nothing
    one = bs.restrict(key, "1c")
    assert sorted(one["crops"]) == ["001", "002", "003", "004", "005", "011"]
    v1c = bs.verdict(one, {"A": ans, "B": ans})
    assert v1c["candidate_pass"] and v1c["species_pass"]["Poring"] is False
    vo3 = bs.verdict(bs.restrict(key, "o3"), {"A": ans, "B": ans})
    assert not vo3["candidate_pass"]  # 5 / 10 Orc Zombie crops good
    import pytest

    with pytest.raises(SystemExit):
        bs.restrict(key, "o3h")


def test_a_key_without_samples_scores_as_before() -> None:
    assert "candidate_pass" in bs.verdict(KEY, {"A": answers(9, 10)})
    assert bs.verdict(KEY, {"A": answers(9, 10)})["candidate_pass"]
