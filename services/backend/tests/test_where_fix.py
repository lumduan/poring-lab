"""scripts/where_fix.py: the /where line read from pixels (where@1, demonstrations 3.13) -- with
synthetic glyphs (the real templates are client pixels in data/, never in the repo)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def wf() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("where_fix", SCRIPTS / "where_fix.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def glyph_set() -> dict[str, np.ndarray]:
    rng = np.random.default_rng(7)
    out = {}
    for ch in "0123456789,:(x)":
        g = rng.random((13, 6)) < 0.4
        g[:, 0] = True  # every glyph touches its own first column: no empty column inside
        out[ch] = g
    return out


def render(text: str, glyphs: dict[str, np.ndarray], wf: ModuleType) -> np.ndarray:
    cols = []
    for ch in text:
        cols.append(glyphs[ch] if ch != " " else np.zeros((13, 3), bool))
        cols.append(np.zeros((13, 1), bool))
    line = np.concatenate(cols, axis=1)
    area = np.zeros((55, 640, 3), np.uint8)
    area[40:53, 5 : 5 + line.shape[1]][line] = wf.YELLOW
    return area


def test_the_trailing_coordinates_are_read(wf: ModuleType) -> None:
    g = glyph_set()
    t = {k: v for k, v in g.items() if k in "0123456789,"}
    assert wf.parse(render("(x) : 104, 122", g, wf), t) == (104, 122)


def test_an_unknown_glyph_inside_the_number_is_no_fix_never_a_guess(wf: ModuleType) -> None:
    g = glyph_set()
    t = {k: v for k, v in g.items() if k in "0123456789,"}
    area = render("(x) : 104, 122", g, wf)
    area[44:48, 70:73] = (0, 0, 0)  # damage a glyph of 122
    got = wf.parse(area, t)
    assert got is None or got == (104, 122)  # a damaged digit is never read as another number
    t2 = dict(t)
    del t2["2"]
    assert wf.parse(render("(x) : 104, 122", g, wf), t2) is None


def test_a_missing_answer_is_no_fix_never_the_previous_line(
    wf: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If /where did not print, the newest yellow line is the PREVIOUS answer: reading it would be a
    confidently wrong fix (the 22:02 stop). The chat area must change after typing."""
    g = glyph_set()
    t = {k: v for k, v in g.items() if k in "0123456789,"}
    old = render("(x) : 104, 122", g, wf)
    monkeypatch.setattr(wf.time, "sleep", lambda s: None)
    monkeypatch.setattr(wf.r, "activate_client", lambda a, s: None)
    monkeypatch.setattr(wf.r, "ns", lambda: 0)
    monkeypatch.setattr(wf, "stable_area", lambda screen: old)  # nothing new ever appears
    monkeypatch.setattr(wf.r, "chat_line", lambda a, s, text, **k: None)
    got = wf.fix(None, None, t)
    assert got["xy"] is None and got["why"] == "no new chat line"

    def refuse(a: object, s: object, text: str, **k: object) -> None:
        raise wf.r.Stop("the chat input did not open: nothing typed")

    monkeypatch.setattr(wf.r, "chat_line", refuse)
    got = wf.fix(None, None, t)
    assert got["xy"] is None and got["why"].startswith("chat:")


# --- where@2 ------------------------------------------------------------------------------------


def v2_templates(wf: ModuleType) -> dict[str, np.ndarray]:
    g = glyph_set()
    return {k: wf.ink_box(v) for k, v in g.items() if k in "0123456789,"}


def test_v2_reads_the_number_after_the_colon_s_space(wf: ModuleType) -> None:
    assert wf.parse_v2(render("(x) : 104, 122", glyph_set(), wf), v2_templates(wf)) == (104, 122)


def test_v2_never_shortens_a_number_when_a_digit_fails(wf: ModuleType) -> None:
    """where@1's WRONG: 109 read as 9 -- the leading digits failed and the parser kept the rest."""
    t = v2_templates(wf)
    del t["1"]  # the leading 1 of 104 (and of 122) cannot be read
    assert wf.parse_v2(render("(x) : 104, 122", glyph_set(), wf), t) is None


@pytest.mark.parametrize(
    ("reads", "belief", "why"),
    [
        ([(10, 12), (10, 13)] * 3, (10, 12), "disagree"),
        ([(30, 30), (30, 30)] * 3, (10, 12), "implausible"),
        ([(10, 11), (10, 11)] * 3, (10, 12), "not_walkable"),
        ([None, None] * 3, (10, 12), "unparsed"),
    ],
)
def test_v2_gates_reject_and_never_guess(
    wf: ModuleType, monkeypatch: pytest.MonkeyPatch, reads: list, belief: tuple, why: str
) -> None:
    walk = np.ones((40, 40), dtype=bool)
    walk[11, 10] = False
    it = iter(reads)
    frames = iter(range(1000))
    monkeypatch.setattr(wf.time, "sleep", lambda s: None)
    monkeypatch.setattr(wf.r, "activate_client", lambda a, s: None)
    monkeypatch.setattr(wf.r, "ns", lambda: 0)
    monkeypatch.setattr(wf.r, "chat_line", lambda a, s, text, **k: None)
    monkeypatch.setattr(wf, "stable_area", lambda screen: np.full((55, 640, 3), next(frames) % 255,
                                                                   np.uint8))  # fmt: skip
    monkeypatch.setattr(wf, "text_mask_v2", lambda a: a[..., 0] % 2 == 1)  # every grab is "new"
    monkeypatch.setattr(wf, "parse_v2", lambda a, t: next(it))
    monkeypatch.setattr(wf, "newest_is_yellow", lambda a: True)
    got = wf.fix_v2(None, None, {}, belief, walk)
    assert got["xy"] is None and why in got["rejects"], got


def test_v2_accepts_two_agreeing_plausible_reads(
    wf: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    walk = np.ones((40, 40), dtype=bool)
    it = iter([(11, 13), (11, 13)])
    frames = iter(range(1000))
    monkeypatch.setattr(wf.time, "sleep", lambda s: None)
    monkeypatch.setattr(wf.r, "activate_client", lambda a, s: None)
    monkeypatch.setattr(wf.r, "ns", lambda: 0)
    monkeypatch.setattr(wf.r, "chat_line", lambda a, s, text, **k: None)
    monkeypatch.setattr(wf, "stable_area", lambda screen: np.full((55, 640, 3), next(frames) % 255,
                                                                   np.uint8))  # fmt: skip
    monkeypatch.setattr(wf, "text_mask_v2", lambda a: a[..., 0] % 2 == 1)
    monkeypatch.setattr(wf, "parse_v2", lambda a, t: next(it))
    monkeypatch.setattr(wf, "newest_is_yellow", lambda a: True)
    typed: list[str] = []
    monkeypatch.setattr(wf.r, "chat_line", lambda a, s, text, **k: typed.append(text))
    assert wf.fix_v2(None, None, {}, (10, 12), walk)["xy"] == (11, 13)
    assert typed == [wf.SEPARATOR, "/where", wf.SEPARATOR, "/where"]  # never 2 /where in a row


def test_an_old_where_line_under_a_newer_message_is_never_read(wf: ModuleType) -> None:
    """The client refused a 4th /where in a row (red) and /ex answers in cyan: the newest YELLOW
    line is then an OLD answer, and the newest line of all is not yellow."""
    g = glyph_set()
    area = render("(x) : 104, 122", g, wf)
    assert wf.newest_is_yellow(area)
    area[53:55, 10:60] = (255, 230, 0)  # a cyan line below it (BGR)
    assert not wf.newest_is_yellow(area)
