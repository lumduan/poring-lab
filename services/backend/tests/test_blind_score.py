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
