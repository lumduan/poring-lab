"""scripts/cursor_diag.py: the hover-only diagnostic reports WHY the cursor read unknown -- the
best reference's IoU and colour agreement even when the colour check failed."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[2] / "scripts"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mods() -> tuple[ModuleType, ModuleType, ModuleType]:
    sys.path.insert(0, str(SCRIPTS))
    for name in ("walk5", "walk6", "reloc2", "where_fix", "walk7", "walk8", "walk9", "walk10"):
        _load(name, SCRIPTS / f"{name}.py")
    f = _load("fakes_walk6", HERE / "test_walk6.py")
    return _load("cursor_diag", SCRIPTS / "cursor_diag.py"), sys.modules["walk6"], f


def test_a_colour_shifted_cursor_keeps_its_shape_and_reports_the_colour_miss(mods: tuple) -> None:
    diag, w6, f = mods
    refs = f.refs_for(w6, ["walk", "sword"])
    a, b = f.crop_pair(w6, "walk")
    clean = diag.explain(refs, a, w6.cursor_mask(a, b))
    assert clean["shape"] == "walk" and clean["best"]["cls"] == "walk"
    assert clean["best"]["col"] >= w6.MIN_COL
    m = w6.cursor_mask(a, b)[..., None]
    tinted = np.where(m, 255 - a, a).astype(np.uint8)  # the same sprite, its colours inverted
    out = diag.explain(refs, tinted, w6.cursor_mask(tinted, b))
    assert out["shape"] == "unknown" and out["why"] == "no_match"
    assert out["best"]["cls"] == "walk" and out["best"]["iou"] >= w6.MIN_IOU
    assert out["best"]["col"] < w6.MIN_COL and out["best"]["diff_p50"] >= w6.COL_TOL
