"""crusader.py (Batt 2026-10-21: the name + job check before every command on the dedicated
Crusader, a 2nd character on the GM account): the pure identity check."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import crusader as cr  # noqa: E402


def frame(name_val: int, job_val: int) -> np.ndarray:
    f = np.zeros((720, 1280, 3), np.uint8)
    x0, y0, x1, y1 = cr.NAME_BOX
    f[y0:y1, x0:x1] = name_val
    x0, y0, x1, y1 = cr.JOB_BOX
    f[y0:y1, x0:x1] = job_val
    return f


def test_only_the_right_name_and_job_pass() -> None:
    ref = frame(200, 100)
    name_ref = cr.crop(ref, cr.NAME_BOX)
    jobs = {"novice": cr.crop(ref, cr.JOB_BOX), "swordman": cr.crop(frame(200, 30), cr.JOB_BOX)}
    assert cr.identity(ref, name_ref, jobs, "novice")["ok"]
    other = cr.identity(frame(90, 100), name_ref, jobs, "novice")  # another character's name
    assert (other["ok"], other["why"]) == (False, "name")
    wrong_job = cr.identity(ref, name_ref, jobs, "swordman")  # still a Novice on screen
    assert (wrong_job["ok"], wrong_job["why"]) == (False, "job")
    assert not cr.identity(ref, name_ref, jobs, "crusader")["ok"]  # no reference yet: refused


def test_a_few_noisy_pixels_still_match_but_a_changed_line_does_not() -> None:
    ref = frame(200, 100)
    name_ref = cr.crop(ref, cr.NAME_BOX)
    jobs = {"novice": cr.crop(ref, cr.JOB_BOX)}
    noisy = ref.copy()
    noisy[23, 5 : 5 + cr.MATCH] = 0  # MATCH codec-noise pixels
    assert cr.identity(noisy, name_ref, jobs, "novice")["ok"]
    noisy[24, 5:6] = 0  # one more
    assert not cr.identity(noisy, name_ref, jobs, "novice")["ok"]
    assert cr.differing(name_ref, name_ref[:, :-1]) > cr.MATCH  # a shape mismatch never matches
