"""hp_percent.py (3.96b S1b): the HP percent text read by fixed-pitch cells, and its labels."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import hp_percent as hp  # noqa: E402

RNG = np.random.default_rng(0)
GLY = {ch: RNG.random((hp.Y1 - hp.Y0, hp.DW)) > 0.5 for ch in "0123456789"}
GLY["%"] = RNG.random((hp.Y1 - hp.Y0, hp.PW)) > 0.5


def frame(text: str) -> np.ndarray:
    f = np.full((720, 1280, 3), 255, np.uint8)
    band = np.zeros((hp.Y1 - hp.Y0, 1280), bool)
    for i, ch in enumerate(text[:-1]):
        band[:, hp.X0 + hp.PITCH * i : hp.X0 + hp.PITCH * i + hp.DW] = GLY[ch]
    p0 = hp.X0 + hp.PITCH * (len(text) - 1)
    band[:, p0 : p0 + hp.PW] = GLY["%"]
    f[hp.Y0 : hp.Y1][band] = 0
    return f


def test_one_two_and_three_digit_reads() -> None:
    for t, want in (("7%", 7), ("42%", 42), ("100%", 100)):
        assert hp.read(frame(t), GLY) == want, t


def test_no_percent_sign_or_an_impossible_value_is_none() -> None:
    assert hp.read(np.full((720, 1280, 3), 255, np.uint8), GLY) is None
    assert hp.read(frame("042%"), GLY) is None  # a leading zero
    assert hp.read(frame("120%"), GLY) is None  # over 100


def test_a_label_needs_a_stable_percent_and_optionally_a_fresh_packet() -> None:
    s = 10**9
    ser = [(0, 5260), (10 * s, 2630)]  # 100 % until 10 s, then 50 %
    assert hp.stable_label(ser, 5 * s, 5260) == 100
    assert hp.stable_label(ser, int(9.8 * s), 5260) is None  # the change is inside +-0.5 s
    assert hp.stable_label(ser, 12 * s, 5260) == 50
    assert hp.stable_label(ser, 12 * s, 5260, fresh_s=1.0) is None  # the last packet is 2 s old
    assert hp.stable_label(ser, int(10.6 * s), 5260, fresh_s=1.0) == 50
