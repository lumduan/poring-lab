"""hp_percent.py (3.96b S1b): the HP percent text read by fixed-pitch cells, and its labels."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

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


# --- this client's own fonts (2026-11-20) ---------------------------------------------------------
def _thin_font() -> dict[str, np.ndarray]:
    """A made-up thin font: each glyph 9 rows, its own width (the live client's style)."""

    def g(rows: list[str]) -> np.ndarray:
        return np.array([[c == "#" for c in r] for r in rows], bool)

    one = g(["..#", ".##", "#.#", "..#", "..#", "..#", "..#", "..#", "..."])
    zero = g([".###.", "#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###.", "....."])
    five = g(["#####", "#....", "####.", "....#", "....#", "....#", "#...#", ".###.", "....."])
    pct = g(
        [
            "##...#.",
            "##..#..",
            "...#...",
            "..#....",
            ".#...##",
            "#....##",
            ".......",
            ".......",
            ".......",
        ]
    )  # fmt: skip  (ink in every column, like the client's own '%')
    return {"1": one, "0": zero, "5": five, "%": pct}


def _draw(font: dict[str, np.ndarray], text: str, x: int = hp.X0, y: int = hp.Y0) -> np.ndarray:
    img = np.full((200, 400, 3), 255, np.uint8)
    for ch in text:
        gl = font[ch]
        img[y : y + gl.shape[0], x : x + gl.shape[1]][gl] = 0
        x += gl.shape[1] + 1
    img[y : y + 8, hp.X0 - 6 : hp.X0 - 3] = 0  # the bar's right end, left of the search
    return img


def test_read_falls_back_to_this_clients_font(monkeypatch: pytest.MonkeyPatch) -> None:
    font = _thin_font()
    monkeypatch.setattr(hp, "client_fonts", lambda folder=None: {"live": font})
    lab = {
        "%": np.zeros((9, hp.PW), bool),
        **{str(d): np.zeros((9, hp.DW), bool) for d in range(10)},
    }
    for text, want in (("100%", 100), ("50%", 50), ("5%", 5), ("15%", 15)):
        assert hp.read(_draw(font, text), lab) == want
    assert hp.read(_draw(font, "105%"), lab) is None  # over 100
    assert hp.read(_draw(font, "05%"), lab) is None  # a leading zero
    assert hp.read_font(hp.ink(_draw(font, "100")), font) is None  # no closing '%'
    monkeypatch.setattr(hp, "client_fonts", lambda folder=None: {})
    assert hp.read(_draw(font, "100%"), lab) is None  # no font: as before


def test_learn_font_needs_one_run_per_character() -> None:
    font = _thin_font()
    img = _draw(font, "1050")
    got: dict[str, np.ndarray] = {}
    res = hp.learn_font(img, hp.Y0, hp.X0 - 1, hp.X0 + 30, "1 0 5 0", got)
    assert res["learned"] == ["1", "0", "5"] and not res["clashes"]
    assert hp.learn_font(img, hp.Y0, hp.X0 - 1, hp.X0 + 30, "105", {})["learned"] == []  # 4 runs
    other = dict(got)
    other["5"] = ~other["5"]
    assert hp.learn_font(img, hp.Y0, hp.X0 - 1, hp.X0 + 30, "1050", other)["clashes"] == ["5"]


def test_client_fonts_read_from_files(tmp_path: Path) -> None:
    font = _thin_font()
    np.savez(tmp_path / f"{hp.FONT_PREFIX}live.npz",
             **{("pct" if k == "%" else f"d{k}"): v for k, v in font.items()})  # fmt: skip
    (tmp_path / f"{hp.FONT_PREFIX}broken.npz").write_bytes(b"no")
    got = hp.client_fonts(tmp_path)
    assert list(got) == ["live"] and set(got["live"]) == {"0", "1", "5", "%"}
