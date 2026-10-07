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
